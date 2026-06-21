"use strict";

// --- map setup --------------------------------------------------------------
const map = L.map("map").setView([52.1, 5.1], 8); // centered on the Netherlands

// CARTO basemaps: clean, free, no API key — a calm backdrop makes the colored
// postcode overlay pop. Swap "voyager" for an alternative to change the look:
//   voyager      — light, modern, with labels (default)
//   positron     — very light grey, minimal (max overlay contrast)
//   dark_matter  — dark theme
// Browse more styles at https://leaflet-extras.github.io/leaflet-providers/preview/
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
let collectedSet = new Set(); // PC4 codes already ridden (from Strava)
let selectedSet = new Set(); // PC4 codes selected to include in the next route
const selMarkers = {}; // code -> checkmark marker
let lastRoutePoints = null; // [[lat,lon],...] of the last computed route
let lastClearedSelection = null; // snapshot for "undo clear"

// --- helpers ----------------------------------------------------------------
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
  // Selected is the actionable state, so it gets the strongest treatment
  // (and a checkmark marker — never color alone).
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

// --- data loading -----------------------------------------------------------
async function loadStatus() {
  const res = await fetch("/api/status");
  const s = await res.json();
  const pill = document.getElementById("conn-status");
  pill.textContent = s.connected ? "verbonden" : "niet verbonden";
  pill.className = "pill " + (s.connected ? "pill-on" : "pill-off");
  // When connected, hide the connect button and show the small refresh button.
  document.getElementById("connect-btn").classList.toggle("hidden", s.connected);
  document.getElementById("refresh-btn").classList.toggle("hidden", !s.connected);
  document.getElementById("collected-count").textContent = s.collected_count;
  document.getElementById("total-count").textContent = s.total_count;
  const pct = s.total_count ? (s.collected_count / s.total_count) * 100 : 0;
  document.getElementById("percent").textContent =
    pct.toLocaleString("nl-NL", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }) + "%";
  document.getElementById("bar-fill").style.transform = "scaleX(" + pct / 100 + ")";
  document.getElementById("last-sync").textContent = s.last_sync
    ? new Date(s.last_sync * 1000).toLocaleDateString("nl-NL")
    : "nooit";
  return s;
}

// Custom hover hint: a plain DOM element we fully control. Leaflet's own
// tooltips get left "stuck" when a mouseout is missed during zoom/pan/resize;
// toggling display on our own element can never get stuck.
function featureLabel(f) {
  const code = f.properties.postcode;
  const state = selectedSet.has(code)
    ? "geselecteerd"
    : collectedSet.has(code)
      ? "afgevinkt"
      : "open";
  return `${code} — ${state}`;
}

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

// Any view change or the cursor leaving the map hides the hint.
map.on("zoomstart movestart", hideHint);
map.getContainer().addEventListener("mouseleave", hideHint);

// Geometry is fetched once and browser-cached; collected state is small and
// refreshed on its own, then applied by restyling the existing layer.
async function loadGeometry() {
  const res = await fetch("/api/pc4/geometry");
  const geo = await res.json();
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
        layer.setStyle(pc4Style(f)); // revert the transient hover highlight
      });
      layer.on("click", () => toggleSelect(code, layer));
    },
  }).addTo(map);
}

async function loadCollected() {
  const res = await fetch("/api/collected");
  const data = await res.json();
  collectedSet = new Set(data.collected);
  if (pc4Layer) pc4Layer.setStyle(pc4Style);
}

// --- selection --------------------------------------------------------------
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
}

// The server owns the planned set; we sync our local copy from its response.
async function persistToggle(code) {
  const res = await fetch("/api/planned/toggle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  selectedSet = new Set((await res.json()).planned);
}

async function toggleSelect(code, layer) {
  await persistToggle(code);
  if (selectedSet.has(code)) addSelMarker(code, layer);
  else removeSelMarker(code);
  layer.setStyle(pc4Style(layer.feature));
  refreshSelectionUI();
}

async function deselectCode(code) {
  await persistToggle(code); // code was selected, so this removes it
  removeSelMarker(code);
  restyleCode(code);
  refreshSelectionUI();
}

async function loadPlanned() {
  const res = await fetch("/api/planned");
  selectedSet = new Set((await res.json()).planned);
  if (pc4Layer) {
    pc4Layer.eachLayer((l) => {
      const code = l.feature.properties.postcode;
      if (selectedSet.has(code)) addSelMarker(code, l);
      l.setStyle(pc4Style(l.feature));
    });
  }
  refreshSelectionUI();
}

async function clearSelection() {
  if (!selectedSet.size) return;
  lastClearedSelection = [...selectedSet];
  await fetch("/api/planned/clear", { method: "POST" });
  Object.keys(selMarkers).forEach(removeSelMarker);
  selectedSet = new Set();
  if (pc4Layer) pc4Layer.setStyle(pc4Style);
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

async function undoClear() {
  if (!lastClearedSelection) return;
  for (const code of lastClearedSelection) {
    await fetch("/api/planned/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
  }
  lastClearedSelection = null;
  await loadPlanned();
  clearMessage();
}

// --- actions ----------------------------------------------------------------
// background=true is used for the silent auto-sync on page load: it only
// surfaces a message when something actually changed (or on error).
async function sync({ background = false } = {}) {
  if (!background) clearMessage();
  const btn = document.getElementById("refresh-btn");
  const pill = document.getElementById("conn-status");
  btn.classList.add("spinning");
  btn.disabled = true;
  pill.textContent = "synchroniseren…";
  try {
    const res = await fetch("/sync", { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    await loadStatus(); // resets pill + counts
    await loadCollected(); // geometry stays cached; just restyle
    if (!background || data.added > 0) {
      showMessage(`${data.added} nieuwe ritten verwerkt.`);
    }
  } catch (err) {
    showMessage(`Sync mislukt: ${err.message}`, true);
    await loadStatus();
  } finally {
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
}

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
    const res = await fetch("/api/route/auto", { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data.geojson, {
      style: { color: "#1565c0", weight: 4, opacity: 0.9 },
    }).addTo(map);
    // remember the snapped route geometry so export needs no re-routing
    lastRoutePoints = data.geojson.geometry.coordinates.map(([lon, lat]) => [
      lat,
      lon,
    ]);
    document.getElementById("route-distance").textContent =
      (data.distance_m / 1000).toFixed(1) + " km";
    document.getElementById("route-new").textContent = data.new_count + " nieuw";
    document.getElementById("route-result").classList.remove("hidden");
  } catch (err) {
    showMessage(`Routeren mislukt: ${err.message}`, true);
  } finally {
    btn.disabled = false;
    refreshSelectionUI(); // restore the "Bereken route (N)" label
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
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "postcodejager-route.gpx";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showMessage(`Export mislukt: ${err.message}`, true);
  }
}

// --- wire up ----------------------------------------------------------------
document.getElementById("refresh-btn").addEventListener("click", () => sync());
document.getElementById("route-btn").addEventListener("click", computeRoute);
document.getElementById("clear-btn").addEventListener("click", clearSelection);
document.getElementById("export-btn").addEventListener("click", exportGpx);

loadCollected()
  .then(loadGeometry)
  .then(loadPlanned);
loadStatus().then((s) => {
  if (s.connected) sync({ background: true }); // silent auto-sync on load
});
