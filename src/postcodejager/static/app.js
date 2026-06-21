"use strict";

// --- map setup --------------------------------------------------------------
const map = L.map("map").setView([52.1, 5.1], 8); // centered on the Netherlands
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "© OpenStreetMap-bijdragers",
}).addTo(map);

let pc4Layer = null;
let routeLayer = null;
const waypoints = []; // array of L.marker, in order

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
  const collected = feature.properties.collected;
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
}

// Custom hover hint: a plain DOM element we fully control. Leaflet's own
// tooltips get left "stuck" when a mouseout is missed during zoom/pan/resize;
// toggling display on our own element can never get stuck.
function featureLabel(f) {
  return `${f.properties.postcode} — ${
    f.properties.collected ? "afgevinkt" : "open"
  }`;
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

async function loadPC4() {
  const res = await fetch("/api/pc4");
  const geo = await res.json();
  if (pc4Layer) map.removeLayer(pc4Layer);
  pc4Layer = L.geoJSON(geo, {
    style: pc4Style,
    onEachFeature: (f, layer) => {
      layer.on("mousemove", (e) => showHint(e.containerPoint, featureLabel(f)));
      layer.on("mouseout", hideHint);
    },
  }).addTo(map);
}

// --- waypoints --------------------------------------------------------------
function renumber() {
  waypoints.forEach((m, i) => {
    m.setIcon(
      L.divIcon({
        className: "",
        html: `<div class="wp-marker">${i + 1}</div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      })
    );
  });
  document.getElementById("wp-count").textContent = `${waypoints.length} punten`;
}

function addWaypoint(latlng) {
  const marker = L.marker(latlng, { draggable: true }).addTo(map);
  marker.on("dragend", () => {}); // position read live at route time
  marker.on("contextmenu", () => removeWaypoint(marker));
  waypoints.push(marker);
  renumber();
}

function removeWaypoint(marker) {
  const i = waypoints.indexOf(marker);
  if (i >= 0) {
    map.removeLayer(marker);
    waypoints.splice(i, 1);
    renumber();
  }
}

function clearWaypoints() {
  waypoints.forEach((m) => map.removeLayer(m));
  waypoints.length = 0;
  if (routeLayer) {
    map.removeLayer(routeLayer);
    routeLayer = null;
  }
  document.getElementById("route-result").classList.add("hidden");
  renumber();
}

map.on("click", (e) => addWaypoint(e.latlng));

// --- actions ----------------------------------------------------------------
async function sync() {
  clearMessage();
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.textContent = "Bezig met synchroniseren…";
  try {
    const res = await fetch("/sync", { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    showMessage(`${data.added} nieuwe ritten verwerkt.`);
    await loadStatus();
    await loadPC4();
  } catch (err) {
    showMessage(`Sync mislukt: ${err.message}`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Synchroniseer ritten";
  }
}

function waypointCoords() {
  return waypoints.map((m) => [m.getLatLng().lat, m.getLatLng().lng]);
}

async function computeRoute() {
  clearMessage();
  if (waypoints.length < 2) {
    showMessage("Plaats minstens 2 waypoints.", true);
    return;
  }
  const btn = document.getElementById("route-btn");
  btn.disabled = true;
  btn.textContent = "Bezig…";
  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ waypoints: waypointCoords() }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data.geojson, {
      style: { color: "#ff6a13", weight: 4, opacity: 0.9 },
    }).addTo(map);
    document.getElementById("route-distance").textContent =
      (data.distance_m / 1000).toFixed(1) + " km";
    document.getElementById("route-new").textContent =
      data.new_count + " nieuw";
    document.getElementById("route-result").classList.remove("hidden");
  } catch (err) {
    showMessage(`Routeren mislukt: ${err.message}`, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Bereken route";
  }
}

async function exportGpx() {
  clearMessage();
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        waypoints: waypointCoords(),
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
document.getElementById("sync-btn").addEventListener("click", sync);
document.getElementById("route-btn").addEventListener("click", computeRoute);
document.getElementById("clear-btn").addEventListener("click", clearWaypoints);
document.getElementById("export-btn").addEventListener("click", exportGpx);

loadStatus();
loadPC4();
