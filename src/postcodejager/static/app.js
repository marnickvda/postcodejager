"use strict";

// === Local-first state =======================================================
// Everything personal (token, collected postcodes, selection) lives here, in
// the browser. The backend is stateless; it only does compute.
function lsGet(key, fallback) {
  try {
    const v = localStorage.getItem("pcj." + key);
    return v == null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}
function lsSet(key, val) {
  localStorage.setItem("pcj." + key, JSON.stringify(val));
}
function lsDel(key) {
  localStorage.removeItem("pcj." + key);
}

let token = lsGet("token", null); // {access_token, refresh_token, expires_at}
let collectedSet = new Set(lsGet("collected", [])); // PC4 already ridden
let selectedSet = new Set(lsGet("planned", [])); // PC4 selected for a route
let lastSync = lsGet("lastSync", null); // epoch seconds
let totalPc4 = 0; // number of PC4 areas (from the geometry)

function saveToken(t) {
  token = t || null;
  if (t) lsSet("token", t);
  else lsDel("token");
}
const saveCollected = () => lsSet("collected", [...collectedSet]);
const savePlanned = () => lsSet("planned", [...selectedSet]);

async function postJSON(url, obj) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj),
  });
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

// === Map setup ===============================================================
const map = L.map("map").setView([52.1, 5.1], 8); // centered on the Netherlands

// CARTO basemaps: clean, free, no API key. Swap "voyager" for positron /
// dark_matter to change the look. https://leaflet-extras.github.io/leaflet-providers/preview/
L.tileLayer(
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
  {
    subdomains: "abcd",
    maxZoom: 20,
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, © <a href="https://carto.com/attributions">CARTO</a>',
  }
).addTo(map);

let pc4Layer = null;
let routeLayer = null;
let importedLayer = null;
const selMarkers = {}; // code -> checkmark marker
let lastRoutePoints = null;
let lastClearedSelection = null;

// --- map legend (static content) --------------------------------------------
const legend = L.control({ position: "bottomleft" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML =
    '<div class="legend-row"><span class="sw sw-sel"></span>Geselecteerd</div>' +
    '<div class="legend-row"><span class="sw sw-done"></span>Afgevinkt</div>' +
    '<div class="legend-row"><span class="sw sw-open"></span>Open</div>' +
    '<div class="legend-row"><span class="ln ln-route"></span>Route</div>' +
    '<div class="legend-row"><span class="ln ln-import"></span>Geïmporteerd</div>';
  return div;
};
legend.addTo(map);

// --- first-run welcome overlay (connect button lives here) ------------------
const welcome = document.createElement("div");
welcome.id = "welcome";
welcome.className = "welcome hidden";
welcome.innerHTML =
  '<div class="welcome-card">' +
  '<img src="/static/icon.svg" width="40" height="40" alt="" />' +
  "<h2>Welkom bij Postcodejager</h2>" +
  "<p>Verbind je Strava om te zien welke postcodes je al hebt gereden. Alles blijft lokaal in deze browser.</p>" +
  '<a id="connect-btn" class="btn btn-strava" href="/auth/login">Verbind met Strava</a>' +
  '<ol class="welcome-steps">' +
  "<li>Verbind Strava — je ritten laden automatisch in.</li>" +
  "<li>Klik postcodes, of sleep met Shift een gebied, om mee te nemen.</li>" +
  "<li>Bereken een route en exporteer de GPX.</li>" +
  "</ol></div>";
map.getContainer().appendChild(welcome);

// --- map loading indicator --------------------------------------------------
const mapLoading = document.createElement("div");
mapLoading.className = "map-loading";
mapLoading.innerHTML = '<span class="mini-spin"></span>Postcodes laden…';
map.getContainer().appendChild(mapLoading);

// === Helpers =================================================================
function showMessage(text, isError) {
  const el = document.getElementById("message");
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.classList.remove("hidden");
}
function clearMessage() {
  document.getElementById("message").classList.add("hidden");
}

function pc4Style(feature) {
  const code = feature.properties.postcode;
  if (selectedSet.has(code)) {
    return { color: "#e85d0a", weight: 3, fillColor: "#ff6a13", fillOpacity: 0.55 };
  }
  const collected = collectedSet.has(code);
  return {
    color: collected ? "#2e7d32" : "#9aa0a6",
    weight: 1,
    fillColor: collected ? "#2e7d32" : "#c8ccd1",
    fillOpacity: collected ? 0.35 : 0.12,
  };
}

function featureLabel(f) {
  const code = f.properties.postcode;
  const state = selectedSet.has(code)
    ? "geselecteerd"
    : collectedSet.has(code)
      ? "afgevinkt"
      : "open";
  return `${code} — ${state}`;
}

const fmtPct = (n) =>
  n.toLocaleString("nl-NL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

// === Status / connection (rendered from local state) =========================
function renderStatus() {
  const connected = !!token;
  const pill = document.getElementById("conn-status");
  pill.textContent = connected ? "verbonden" : "niet verbonden";
  pill.className = "pill " + (connected ? "pill-on" : "pill-off");
  document.getElementById("welcome").classList.toggle("hidden", connected);
  document.getElementById("connect-btn").classList.toggle("hidden", connected);
  document.getElementById("refresh-btn").classList.toggle("hidden", !connected);
  document.getElementById("collected-count").textContent = collectedSet.size;
  document.getElementById("total-count").textContent = totalPc4 || "–";
  const pct = totalPc4 ? (collectedSet.size / totalPc4) * 100 : 0;
  document.getElementById("percent").textContent = fmtPct(pct) + "%";
  document.getElementById("bar-fill").style.transform = "scaleX(" + pct / 100 + ")";
  document.getElementById("last-sync").textContent = lastSync
    ? new Date(lastSync * 1000).toLocaleDateString("nl-NL")
    : "nooit";
}

// === Hover hint (own element; never gets stuck) ==============================
const hint = document.createElement("div");
hint.className = "hover-hint";
hint.style.display = "none";
map.getContainer().appendChild(hint);

function showHint(containerPoint, text) {
  hint.textContent = text;
  hint.style.left = containerPoint.x + "px";
  hint.style.top = containerPoint.y - 12 + "px";
  hint.style.display = "block";
}
function hideHint() {
  hint.style.display = "none";
}
map.on("zoomstart movestart", hideHint);
map.getContainer().addEventListener("mouseleave", hideHint);

// === Geometry + collected/province rendering =================================
async function loadGeometry() {
  mapLoading.classList.remove("hidden");
  const geo = await (await fetch("/api/pc4/geometry")).json();
  totalPc4 = geo.features.length;
  if (pc4Layer) map.removeLayer(pc4Layer);
  pc4Layer = L.geoJSON(geo, {
    style: pc4Style,
    onEachFeature: (f, layer) => {
      const code = f.properties.postcode;
      layer.on("mousemove", (e) => showHint(e.containerPoint, featureLabel(f)));
      layer.on("mouseover", () => {
        if (!selectedSet.has(code)) layer.setStyle({ weight: 3, color: "#5f6368" });
        layer.bringToFront();
      });
      layer.on("mouseout", () => {
        hideHint();
        layer.setStyle(pc4Style(f));
      });
      layer.on("click", () => toggleSelect(code, layer));
    },
  }).addTo(map);
  // restore persisted selection markers
  pc4Layer.eachLayer((l) => {
    if (selectedSet.has(l.feature.properties.postcode)) addSelMarker(l.feature.properties.postcode, l);
  });
  mapLoading.classList.add("hidden");
  renderStatus();
  refreshSelectionUI();
  loadProvinces();
}

async function loadProvinces() {
  const { provinces } = await postJSON("/api/provinces", {
    collected: [...collectedSet],
  });
  const list = document.getElementById("prov-list");
  list.innerHTML = "";
  for (const p of provinces) {
    const li = document.createElement("li");
    li.className = "prov-row";
    const head = document.createElement("div");
    head.className = "prov-head";
    const name = document.createElement("span");
    name.className = "prov-name";
    name.textContent = p.name;
    const meta = document.createElement("span");
    meta.className = "prov-meta";
    meta.textContent = `${fmtPct(p.percent)}% · ${p.collected}/${p.total}`;
    head.append(name, meta);
    const bar = document.createElement("div");
    bar.className = "bar bar-sm";
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.transform = "scaleX(" + p.percent / 100 + ")";
    bar.appendChild(fill);
    li.append(head, bar);
    list.appendChild(li);
  }
}

// === Selection ===============================================================
function addSelMarker(code, layer) {
  if (selMarkers[code]) return;
  selMarkers[code] = L.marker(layer.getBounds().getCenter(), {
    icon: L.divIcon({
      className: "",
      html: '<div class="sel-check" aria-hidden="true">✓</div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    }),
    interactive: false,
    keyboard: false,
  }).addTo(map);
}
function removeSelMarker(code) {
  if (selMarkers[code]) {
    map.removeLayer(selMarkers[code]);
    delete selMarkers[code];
  }
}
function restyleCode(code) {
  if (!pc4Layer) return;
  pc4Layer.eachLayer((l) => {
    if (l.feature.properties.postcode === code) l.setStyle(pc4Style(l.feature));
  });
}

function refreshSelectionUI() {
  const codes = [...selectedSet].sort();
  document.getElementById("sel-count").textContent = `${codes.length} geselecteerd`;
  document.getElementById("route-btn").textContent = codes.length
    ? `Bereken route (${codes.length})`
    : "Bereken route";
  const list = document.getElementById("sel-list");
  list.innerHTML = "";
  for (const code of codes) {
    const li = document.createElement("li");
    li.className = "chip";
    const label = document.createElement("span");
    label.textContent = code;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", `Verwijder ${code}`);
    btn.textContent = "×";
    btn.addEventListener("click", () => deselectCode(code));
    li.append(label, btn);
    list.appendChild(li);
  }
  updateImpact();
}

async function updateImpact() {
  const box = document.getElementById("impact");
  if (!selectedSet.size) {
    box.classList.add("hidden");
    return;
  }
  const d = await postJSON("/api/selection/impact", {
    collected: [...collectedSet],
    planned: [...selectedSet],
  });
  if (!d.new) {
    box.classList.add("hidden");
    return;
  }
  box.querySelector(".impact-main").textContent =
    `+${fmtPct(d.increase)}% — van ${fmtPct(d.current_percent)}% naar ${fmtPct(d.projected_percent)}%`;
  box.querySelector(".impact-provs").textContent = d.provinces
    .map((p) => `${p.name} +${fmtPct(p.increase)}%`)
    .join(" · ");
  box.classList.remove("hidden");
}

function toggleSelect(code, layer) {
  if (selectedSet.has(code)) {
    selectedSet.delete(code);
    removeSelMarker(code);
  } else {
    selectedSet.add(code);
    addSelMarker(code, layer);
  }
  savePlanned();
  layer.setStyle(pc4Style(layer.feature));
  refreshSelectionUI();
}

function deselectCode(code) {
  selectedSet.delete(code);
  savePlanned();
  removeSelMarker(code);
  restyleCode(code);
  refreshSelectionUI();
}

function clearRoute() {
  if (routeLayer) {
    map.removeLayer(routeLayer);
    routeLayer = null;
  }
  lastRoutePoints = null;
  document.getElementById("route-result").classList.add("hidden");
}

function clearSelection() {
  if (!selectedSet.size) return;
  lastClearedSelection = [...selectedSet];
  Object.keys(selMarkers).forEach(removeSelMarker);
  selectedSet = new Set();
  savePlanned();
  if (pc4Layer) pc4Layer.setStyle(pc4Style);
  clearRoute();
  refreshSelectionUI();
  showUndo(`${lastClearedSelection.length} postcodes gewist.`);
}

function showUndo(text) {
  const el = document.getElementById("message");
  el.classList.remove("error", "hidden");
  el.textContent = text + " ";
  const undo = document.createElement("button");
  undo.type = "button";
  undo.className = "link-btn";
  undo.textContent = "Ongedaan maken";
  undo.addEventListener("click", undoClear);
  el.appendChild(undo);
}

function undoClear() {
  if (!lastClearedSelection) return;
  lastClearedSelection.forEach((c) => selectedSet.add(c));
  lastClearedSelection = null;
  savePlanned();
  if (pc4Layer)
    pc4Layer.eachLayer((l) => {
      const c = l.feature.properties.postcode;
      if (selectedSet.has(c)) {
        addSelMarker(c, l);
        l.setStyle(pc4Style(l.feature));
      }
    });
  refreshSelectionUI();
  clearMessage();
}

// --- box select (Shift + drag) ----------------------------------------------
map.boxZoom.disable();
let boxStart = null;
let boxRect = null;
document.addEventListener("keydown", (e) => {
  if (e.key === "Shift") map.getContainer().classList.add("box-mode");
});
document.addEventListener("keyup", (e) => {
  if (e.key === "Shift") map.getContainer().classList.remove("box-mode");
});
map.on("mousedown", (e) => {
  if (!e.originalEvent.shiftKey || !pc4Layer) return;
  hideHint();
  boxStart = e.latlng;
  map.dragging.disable();
  boxRect = L.rectangle([boxStart, boxStart], {
    color: "#e85d0a",
    weight: 1,
    fillColor: "#ff6a13",
    fillOpacity: 0.12,
    interactive: false,
  }).addTo(map);
});
map.on("mousemove", (e) => {
  if (boxStart && boxRect) boxRect.setBounds(L.latLngBounds(boxStart, e.latlng));
});
map.on("mouseup", () => {
  if (!boxStart) return;
  const bounds = boxRect.getBounds();
  map.removeLayer(boxRect);
  boxRect = null;
  boxStart = null;
  map.dragging.enable();
  let changed = false;
  pc4Layer.eachLayer((l) => {
    const code = l.feature.properties.postcode;
    if (!selectedSet.has(code) && bounds.contains(l.getBounds().getCenter())) {
      selectedSet.add(code);
      addSelMarker(code, l);
      l.setStyle(pc4Style(l.feature));
      changed = true;
    }
  });
  if (changed) {
    savePlanned();
    refreshSelectionUI();
  }
});

// === Strava: connect / sync ==================================================
async function validAccessToken() {
  if (!token) return null;
  const now = Math.floor(Date.now() / 1000);
  if (token.expires_at && token.expires_at <= now + 60 && token.refresh_token) {
    try {
      saveToken(await postJSON("/api/strava/refresh", { refresh_token: token.refresh_token }));
    } catch (e) {
      showMessage("Token verversen mislukt: " + e.message, true);
    }
  }
  return token ? token.access_token : null;
}

async function handleOAuthRedirect() {
  const code = new URLSearchParams(location.search).get("code");
  if (!code) return;
  try {
    saveToken(await postJSON("/api/strava/exchange", { code }));
  } catch (e) {
    showMessage("Strava-koppeling mislukt: " + e.message, true);
  }
  history.replaceState({}, "", "/");
  renderStatus();
}

async function sync({ background = false } = {}) {
  if (!token) return;
  if (!background) clearMessage();
  const btn = document.getElementById("refresh-btn");
  const pill = document.getElementById("conn-status");
  btn.classList.add("spinning");
  btn.disabled = true;
  pill.textContent = "synchroniseren…";
  try {
    const at = await validAccessToken();
    const data = await postJSON("/api/sync", { access_token: at, after: lastSync });
    data.collected.forEach((c) => collectedSet.add(c));
    saveCollected();
    lastSync = Math.max(lastSync || 0, data.latest || 0);
    lsSet("lastSync", lastSync);
    if (pc4Layer) pc4Layer.setStyle(pc4Style);
    renderStatus();
    loadProvinces();
    updateImpact();
    if (!background || data.activities > 0) {
      showMessage(`${data.activities} nieuwe ritten verwerkt.`);
    }
  } catch (e) {
    showMessage("Sync mislukt: " + e.message, true);
    renderStatus();
  } finally {
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
}

// === Route + GPX =============================================================
async function computeRoute() {
  clearMessage();
  if (selectedSet.size < 2) {
    showMessage("Selecteer minstens 2 postcodes op de kaart.", true);
    return;
  }
  const btn = document.getElementById("route-btn");
  btn.disabled = true;
  btn.textContent = "Bezig…";
  try {
    const data = await postJSON("/api/route/auto", {
      planned: [...selectedSet],
      collected: [...collectedSet],
      loop: document.getElementById("loop-toggle").checked,
    });
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data.geojson, {
      style: { color: "#1565c0", weight: 4, opacity: 0.9 },
    }).addTo(map);
    lastRoutePoints = data.geojson.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    document.getElementById("route-distance").textContent =
      (data.distance_m / 1000).toFixed(1) + " km";
    document.getElementById("route-new").textContent = data.new_count + " nieuw";
    document.getElementById("route-result").classList.remove("hidden");
  } catch (e) {
    showMessage("Routeren mislukt: " + e.message, true);
  } finally {
    btn.disabled = false;
    refreshSelectionUI();
  }
}

async function exportGpx() {
  clearMessage();
  if (!lastRoutePoints) {
    showMessage("Bereken eerst een route.", true);
    return;
  }
  try {
    const res = await fetch("/api/export/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        points: lastRoutePoints,
        name: "Postcodejager " + new Date().toLocaleDateString("nl-NL"),
      }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "postcodejager-route.gpx";
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showMessage("Export mislukt: " + e.message, true);
  }
}

async function onGpxChosen(e) {
  const file = e.target.files[0];
  if (!file) return;
  clearMessage();
  try {
    const res = await fetch("/api/import/gpx", {
      method: "POST",
      headers: { "Content-Type": "application/gpx+xml" },
      body: await file.text(),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    if (importedLayer) map.removeLayer(importedLayer);
    importedLayer = L.geoJSON(data.geojson, {
      style: { color: "#7b1fa2", weight: 4, opacity: 0.9, dashArray: "6 5" },
    }).addTo(map);
    const bounds = importedLayer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
    const newCodes = data.crossed.filter((c) => !collectedSet.has(c));
    document.getElementById("import-new").textContent = newCodes.length + " nieuw";
    document.getElementById("import-crossed").textContent =
      data.crossed.length + " postcodes";
    document.getElementById("import-result").classList.remove("hidden");
    const codes = newCodes.length ? ": " + newCodes.join(", ") : "";
    showMessage(`Deze route pakt ${newCodes.length} nieuwe postcodes${codes}.`);
  } catch (err) {
    showMessage("Import mislukt: " + err.message, true);
  } finally {
    e.target.value = "";
  }
}

function clearImport() {
  if (importedLayer) {
    map.removeLayer(importedLayer);
    importedLayer = null;
  }
  document.getElementById("import-result").classList.add("hidden");
  clearMessage();
}

// === Wire up =================================================================
document.getElementById("refresh-btn").addEventListener("click", () => sync());
document.getElementById("route-btn").addEventListener("click", computeRoute);
document.getElementById("clear-btn").addEventListener("click", clearSelection);
document.getElementById("export-btn").addEventListener("click", exportGpx);
document
  .getElementById("import-btn")
  .addEventListener("click", () => document.getElementById("gpx-input").click());
document.getElementById("gpx-input").addEventListener("change", onGpxChosen);
document.getElementById("import-clear").addEventListener("click", clearImport);

renderStatus();
loadGeometry();
handleOAuthRedirect().then(() => {
  if (token) sync({ background: true });
});
