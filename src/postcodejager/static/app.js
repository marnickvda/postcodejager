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
const saveStart = () => (startPoint ? lsSet("startPoint", startPoint) : lsDel("startPoint"));
const saveEnd = () => (endPoint ? lsSet("endPoint", endPoint) : lsDel("endPoint"));

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
// Limit the map to the Netherlands plus a little margin: no panning/zooming out
// to the rest of the world, and no tile requests beyond this box.
const NL_BOUNDS = L.latLngBounds([50.4, 2.8], [53.9, 7.6]);
const map = L.map("map", {
  maxBounds: NL_BOUNDS,
  maxBoundsViscosity: 1.0,
  minZoom: 7,
}).setView([52.1, 5.1], 8);

// CARTO basemaps: clean, free, no API key. Swap "voyager" for positron /
// dark_matter to change the look. https://leaflet-extras.github.io/leaflet-providers/preview/
L.tileLayer(
  "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
  {
    subdomains: "abcd",
    maxZoom: 20,
    bounds: NL_BOUNDS,
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
let startPoint = lsGet("startPoint", null); // [lat, lon] or null — route start/home
let endPoint = lsGet("endPoint", null); // [lat, lon] or null — point-to-point finish
let startMarker = null;
let endMarker = null;
let placeMode = null; // "start" | "end" | null — next map click sets that point

// --- route editing (session-only) ---
let editMode = false;
let editWaypoints = []; // [{ ll: [lat, lon], via: bool }] — distinct, no loop-close dup
let lastWaypoints = null; // raw waypoints from the last route (loops include the closing dup)
let lastLoop = true; // loop-ness of the last computed route
let baseNewCount = 0; // new_count of the last computed route — the edit baseline
let handleMarkers = []; // draggable waypoint handles
let ghostMarkers = []; // midpoint "insert a via" ghosts
let rerouteInFlight = false;
let reroutePending = false;

// Cache-buster for the day-cached geometry endpoints. Bump when the shape of
// the served features changes (e.g. a new property) so clients refetch instead
// of serving a stale copy. v2 added each area's `prov` (province) field.
const DATA_VERSION = "2";

// === Provinces ===============================================================
const PROVINCE_COLORS = {
  Drenthe: "#9A6324",
  Flevoland: "#42A5F5",
  Fryslân: "#1B998B",
  Gelderland: "#E6194B",
  Groningen: "#F032E6",
  Limburg: "#911EB4",
  "Noord-Brabant": "#000075",
  "Noord-Holland": "#800000",
  Overijssel: "#808000",
  Utrecht: "#BC5090",
  Zeeland: "#00838F",
  "Zuid-Holland": "#3D348B",
};
const PROVINCE_UNKNOWN = "Onbekend";
const PROVINCE_UNKNOWN_COLOR = "#9aa0a6";

let provinceLayer = null;
const codeProvince = new Map(); // PC4 code -> province name

function provinceColor(name) {
  return PROVINCE_COLORS[name] || PROVINCE_UNKNOWN_COLOR;
}
function provinceOf(code) {
  return codeProvince.get(code) || PROVINCE_UNKNOWN;
}

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
  '<a id="connect-btn" class="strava-connect" href="/auth/login"><img src="/static/strava-connect.svg" alt="Connect with Strava" /></a>' +
  '<ol class="welcome-steps">' +
  "<li>Verbind Strava: je ritten laden automatisch in.</li>" +
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
  return `${code} · ${state}`;
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
  const geo = await (await fetch("/api/pc4/geometry?v=" + DATA_VERSION)).json();
  totalPc4 = geo.features.length;
  if (pc4Layer) map.removeLayer(pc4Layer);
  pc4Layer = L.geoJSON(geo, {
    style: pc4Style,
    onEachFeature: (f, layer) => {
      const code = f.properties.postcode;
      if (f.properties.prov) codeProvince.set(code, f.properties.prov);
      layer.on("mousemove", (e) => showHint(e.containerPoint, featureLabel(f)));
      layer.on("mouseover", () => {
        if (!selectedSet.has(code)) layer.setStyle({ weight: 3, color: "#5f6368" });
        layer.bringToFront();
      });
      layer.on("mouseout", () => {
        hideHint();
        layer.setStyle(pc4Style(f));
      });
      layer.on("click", (e) => {
        if (editMode) return; // editing handles, not toggling postcodes
        if (placeMode) {
          placeEndpointAt(e.latlng);
          return; // placing a start/end pin, not toggling this postcode
        }
        toggleSelect(code, layer);
      });
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
  loadProvinceBoundaries();
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
    const dot = document.createElement("span");
    dot.className = "prov-dot";
    dot.style.background = provinceColor(p.name);
    const nameText = document.createElement("span");
    nameText.textContent = p.name;
    name.append(dot, nameText);
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

async function loadProvinceBoundaries() {
  const geo = await (await fetch("/api/provinces/geometry?v=" + DATA_VERSION)).json();
  if (provinceLayer) map.removeLayer(provinceLayer);
  provinceLayer = L.geoJSON(geo, {
    interactive: false, // clicks pass through to the postcode areas beneath
    style: (f) => ({
      color: provinceColor(f.properties.name),
      weight: 3,
      opacity: 0.9,
      fill: false,
    }),
  }).addTo(map);
  provinceLayer.bringToFront();
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

  // group codes by province name
  const byProv = new Map();
  for (const code of codes) {
    const prov = provinceOf(code);
    if (!byProv.has(prov)) byProv.set(prov, []);
    byProv.get(prov).push(code);
  }
  // province groups alphabetically, "Onbekend" last
  const provNames = [...byProv.keys()].sort((a, b) => {
    if (a === PROVINCE_UNKNOWN) return 1;
    if (b === PROVINCE_UNKNOWN) return -1;
    return a.localeCompare(b, "nl");
  });

  for (const prov of provNames) {
    const group = document.createElement("div");
    group.className = "sel-group";

    const head = document.createElement("div");
    head.className = "sel-group-head";
    const dot = document.createElement("span");
    dot.className = "prov-dot";
    dot.style.background = provinceColor(prov);
    const label = document.createElement("span");
    label.textContent = prov;
    head.append(dot, label);

    const ul = document.createElement("ul");
    ul.className = "chips";
    for (const code of byProv.get(prov)) {
      const li = document.createElement("li");
      li.className = "chip";
      const codeLabel = document.createElement("span");
      codeLabel.textContent = code;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("aria-label", `Verwijder ${code}`);
      btn.textContent = "×";
      btn.addEventListener("click", () => deselectCode(code));
      li.append(codeLabel, btn);
      ul.appendChild(li);
    }

    group.append(head, ul);
    list.appendChild(group);
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
    `+${fmtPct(d.increase)}% (van ${fmtPct(d.current_percent)}% naar ${fmtPct(d.projected_percent)}%)`;
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
// A plain click while placing a start/end point sets it (clicks that miss every
// PC4 polygon only reach the map, so this catches those).
map.on("click", (e) => {
  if (placeMode) placeEndpointAt(e.latlng);
});
map.on("mousedown", (e) => {
  if (editMode) return; // no shift-drag selection while editing the route
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

// === Route start / end points ===============================================
const isLoop = () => document.getElementById("loop-toggle").checked;
const fmtCoord = (p) => (p ? `${p[0].toFixed(4)}, ${p[1].toFixed(4)}` : "niet gezet");

function endpointIcon(label, cls) {
  return L.divIcon({
    className: "route-pin " + cls,
    html: label,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

function makeEndpointMarker(point, label, cls, onMove) {
  const marker = L.marker(point, {
    icon: endpointIcon(label, cls),
    draggable: true,
    zIndexOffset: 1000,
    keyboard: false,
  }).addTo(map);
  marker.on("dragend", () => {
    const ll = marker.getLatLng();
    onMove([ll.lat, ll.lng]);
    saveStart();
    saveEnd();
    updateEndpointUI();
  });
  return marker;
}

function renderEndpoints() {
  if (startMarker) map.removeLayer(startMarker);
  startMarker = startPoint
    ? makeEndpointMarker(startPoint, "S", "pin-start", (p) => (startPoint = p))
    : null;
  if (endMarker) map.removeLayer(endMarker);
  endMarker =
    endPoint && !isLoop()
      ? makeEndpointMarker(endPoint, "F", "pin-end", (p) => (endPoint = p))
      : null;
  updateEndpointUI();
}

function updateEndpointUI() {
  document.getElementById("end-row").classList.toggle("hidden", isLoop());
  document.getElementById("start-coord").textContent = fmtCoord(startPoint);
  document.getElementById("end-coord").textContent = fmtCoord(endPoint);
  document.getElementById("clear-start-btn").classList.toggle("hidden", !startPoint);
  document.getElementById("clear-end-btn").classList.toggle("hidden", !endPoint);
}

function setPlaceMode(mode) {
  placeMode = mode;
  map.getContainer().classList.toggle("placing", !!mode);
  document.getElementById("set-start-btn").setAttribute("aria-pressed", String(mode === "start"));
  document.getElementById("set-end-btn").setAttribute("aria-pressed", String(mode === "end"));
  if (mode) {
    showMessage(`Klik op de kaart om het ${mode === "start" ? "startpunt" : "eindpunt"} te zetten.`);
  }
}

// Set the pending start/end from a map click. placeMode is consumed (set to
// null), so a duplicate event from a polygon + map click is harmless.
function placeEndpointAt(latlng) {
  if (placeMode === "start") {
    startPoint = [latlng.lat, latlng.lng];
    saveStart();
  } else if (placeMode === "end") {
    endPoint = [latlng.lat, latlng.lng];
    saveEnd();
  } else {
    return;
  }
  setPlaceMode(null);
  clearMessage();
  renderEndpoints();
}

// === Route editing ===========================================================
const ROLE_CLASS = { start: "h-start", end: "h-end", via: "h-via", anchor: "h-anchor" };

function setRouteNew(cur) {
  const el = document.getElementById("route-new");
  el.textContent = (cur !== baseNewCount ? `${baseNewCount} → ${cur}` : `${cur}`) + " nieuw";
}

function handleRole(i) {
  const n = editWaypoints.length;
  if (startPoint && i === 0) return "start";
  if (!lastLoop && endPoint && i === n - 1) return "end";
  return editWaypoints[i].via ? "via" : "anchor";
}

function clearHandles() {
  handleMarkers.forEach((m) => map.removeLayer(m));
  ghostMarkers.forEach((m) => map.removeLayer(m));
  handleMarkers = [];
  ghostMarkers = [];
}

function renderHandles() {
  clearHandles();
  editWaypoints.forEach((w, i) => {
    const m = L.marker(w.ll, {
      icon: L.divIcon({
        className: "route-handle " + ROLE_CLASS[handleRole(i)],
        iconSize: [16, 16],
        iconAnchor: [8, 8],
      }),
      draggable: true,
      zIndexOffset: 1200,
      keyboard: false,
    }).addTo(map);
    m.on("dragend", () => {
      const prev = cloneWaypoints();
      const ll = m.getLatLng();
      editWaypoints[i].ll = [ll.lat, ll.lng];
      reroute(prev);
    });
    m.on("click", () => deleteHandle(i)); // no-op until Task 3
    handleMarkers.push(m);
  });
  renderGhosts(); // no-op until Task 4
}

// Filled in by later tasks; defined now so renderHandles() is written once.
function deleteHandle(i) {
  if (!editMode) return;
  const role = handleRole(i);
  if (role === "start" || role === "end") return; // anchors aren't deletable
  if (editWaypoints.length <= 2) return; // keep a routable minimum
  const prev = cloneWaypoints();
  editWaypoints.splice(i, 1);
  reroute(prev);
}
function ghostPairs() {
  const n = editWaypoints.length;
  const pairs = [];
  for (let i = 0; i < n - 1; i++) pairs.push([i, i + 1]);
  if (lastLoop && n >= 2) pairs.push([n - 1, 0]); // closing leg
  return pairs;
}

function renderGhosts() {
  ghostPairs().forEach(([a, b]) => {
    const pa = editWaypoints[a].ll;
    const pb = editWaypoints[b].ll;
    const mid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2];
    const g = L.marker(mid, {
      icon: L.divIcon({ className: "route-ghost", iconSize: [12, 12], iconAnchor: [6, 6] }),
      draggable: true,
      zIndexOffset: 1100,
      keyboard: false,
    }).addTo(map);
    g.on("dragend", () => {
      const prev = cloneWaypoints();
      const ll = g.getLatLng();
      const at = b === 0 ? editWaypoints.length : b; // closing leg inserts at the end
      editWaypoints.splice(at, 0, { ll: [ll.lat, ll.lng], via: true });
      reroute(prev);
    });
    ghostMarkers.push(g);
  });
}

const cloneWaypoints = () => editWaypoints.map((w) => ({ ll: [...w.ll], via: w.via }));

async function reroute(revertTo) {
  if (rerouteInFlight) {
    reroutePending = true;
    return;
  }
  rerouteInFlight = true;
  const snapshot = revertTo || cloneWaypoints();
  const editBtn = document.getElementById("edit-btn");
  editBtn.textContent = "Bezig…";
  try {
    const pts = editWaypoints.map((w) => w.ll);
    if (lastLoop) pts.push(editWaypoints[0].ll); // re-close the loop
    const data = await postJSON("/api/route/manual", {
      waypoints: pts,
      collected: [...collectedSet],
    });
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data.geojson, {
      style: { color: "#1565c0", weight: 4, opacity: 0.9 },
    }).addTo(map);
    lastRoutePoints = data.geojson.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    lastWaypoints = data.waypoints;
    document.getElementById("route-distance").textContent =
      (data.distance_m / 1000).toFixed(1) + " km";
    setRouteNew(data.new_count);
  } catch (e) {
    editWaypoints = snapshot; // revert so handles match the unchanged line
    showMessage("Routeren mislukt: " + e.message, true);
  } finally {
    rerouteInFlight = false;
    if (editMode) {
      editBtn.textContent = "Klaar met aanpassen";
      renderHandles();
      if (reroutePending) {
        reroutePending = false;
        reroute();
      }
    } else {
      reroutePending = false;
    }
  }
}

function enterEditMode() {
  if (!lastWaypoints) return;
  editMode = true;
  const seed = lastLoop ? lastWaypoints.slice(0, -1) : lastWaypoints.slice();
  editWaypoints = seed.map((ll) => ({ ll: [ll[0], ll[1]], via: false }));
  if (startMarker) {
    map.removeLayer(startMarker);
    startMarker = null;
  }
  if (endMarker) {
    map.removeLayer(endMarker);
    endMarker = null;
  }
  map.getContainer().classList.add("editing");
  document.getElementById("edit-btn").textContent = "Klaar met aanpassen";
  renderHandles();
}

function exitEditMode() {
  editMode = false;
  clearHandles();
  map.getContainer().classList.remove("editing");
  document.getElementById("edit-btn").textContent = "Route aanpassen";
  renderEndpoints(); // restore the start/end markers
}

function toggleEditMode() {
  editMode ? exitEditMode() : enterEditMode();
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
    const loop = isLoop();
    const data = await postJSON("/api/route/auto", {
      planned: [...selectedSet],
      collected: [...collectedSet],
      loop,
      start: startPoint,
      end: loop ? null : endPoint,
    });
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data.geojson, {
      style: { color: "#1565c0", weight: 4, opacity: 0.9 },
    }).addTo(map);
    lastRoutePoints = data.geojson.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    lastWaypoints = data.waypoints;
    lastLoop = loop;
    baseNewCount = data.new_count;
    if (editMode) exitEditMode(); // a fresh compute resets any edit session
    document.getElementById("route-distance").textContent =
      (data.distance_m / 1000).toFixed(1) + " km";
    setRouteNew(data.new_count);
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
document.getElementById("edit-btn").addEventListener("click", toggleEditMode);
document
  .getElementById("import-btn")
  .addEventListener("click", () => document.getElementById("gpx-input").click());
document.getElementById("gpx-input").addEventListener("change", onGpxChosen);
document.getElementById("import-clear").addEventListener("click", clearImport);
document
  .getElementById("set-start-btn")
  .addEventListener("click", () => setPlaceMode(placeMode === "start" ? null : "start"));
document
  .getElementById("set-end-btn")
  .addEventListener("click", () => setPlaceMode(placeMode === "end" ? null : "end"));
document.getElementById("clear-start-btn").addEventListener("click", () => {
  startPoint = null;
  saveStart();
  renderEndpoints();
});
document.getElementById("clear-end-btn").addEventListener("click", () => {
  endPoint = null;
  saveEnd();
  renderEndpoints();
});
document.getElementById("loop-toggle").addEventListener("change", renderEndpoints);

renderStatus();
renderEndpoints();
loadGeometry();
handleOAuthRedirect().then(() => {
  if (token) sync({ background: true });
});
