import json
import pathlib

import httpx
import respx
from fastapi.testclient import TestClient

from postcodejager.app import create_app
from postcodejager.config import load_settings
from postcodejager.gpx import build_gpx
from postcodejager.postcodes import PC4Index
from postcodejager.storage import Store

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"

BROUTER_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"track-length": "3500"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[4.905, 52.37], [4.935, 52.37]],
            },
        }
    ],
}


def make(tmp_path):
    idx = PC4Index.from_geojson(json.loads(FIX.read_text()))
    store = Store(str(tmp_path / "db.sqlite"))
    settings = load_settings({"BROUTER_BASE_URL": "https://brouter.test/brouter"})
    app = create_app(settings, store, lambda: idx)
    return TestClient(app), store


def test_status_initial(tmp_path):
    c, _ = make(tmp_path)
    r = c.get("/api/status")
    assert r.status_code == 200
    assert r.json()["connected"] is False
    assert r.json()["collected_count"] == 0
    assert r.json()["total_count"] == 2  # fixture has 2 PC4 areas


def test_status_reports_total_and_collected(tmp_path):
    c, store = make(tmp_path)
    store.set_collected({"1011"})
    body = c.get("/api/status").json()
    assert body["collected_count"] == 1
    assert body["total_count"] == 2


def test_geometry_endpoint_is_cacheable(tmp_path):
    c, _ = make(tmp_path)
    r = c.get("/api/pc4/geometry")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert len(feats) == 2
    assert {f["properties"]["postcode"][:4] for f in feats} == {"1011", "1012"}
    assert "max-age" in r.headers.get("cache-control", "")


def test_collected_endpoint(tmp_path):
    c, store = make(tmp_path)
    assert c.get("/api/collected").json()["collected"] == []
    store.set_collected({"1011"})
    assert c.get("/api/collected").json()["collected"] == ["1011"]


def test_planned_toggle_get_clear(tmp_path):
    c, _ = make(tmp_path)
    assert c.get("/api/planned").json()["planned"] == []
    assert c.post("/api/planned/toggle", json={"code": "1011"}).json()["planned"] == ["1011"]
    c.post("/api/planned/toggle", json={"code": "1012"})
    assert c.get("/api/planned").json()["planned"] == ["1011", "1012"]
    c.post("/api/planned/toggle", json={"code": "1011"})  # toggle off
    assert c.get("/api/planned").json()["planned"] == ["1012"]
    c.post("/api/planned/clear")
    assert c.get("/api/planned").json()["planned"] == []


def test_route_auto_through_selected(tmp_path):
    c, store = make(tmp_path)
    store.set_planned({"1011", "1012"})
    with respx.mock(assert_all_mocked=False) as router:
        router.get(url__regex=r"https://brouter\.test/brouter.*").mock(
            return_value=httpx.Response(200, json=BROUTER_GEOJSON)
        )
        r = c.post("/api/route/auto")
    assert r.status_code == 200
    body = r.json()
    assert body["new_count"] == 2
    assert sorted(body["new_codes"]) == ["1011", "1012"]
    assert body["distance_m"] == 3500.0


def test_route_auto_requires_at_least_two(tmp_path):
    c, store = make(tmp_path)
    store.set_planned({"1011"})
    assert c.post("/api/route/auto").status_code == 400


def test_import_gpx_counts_new_postcodes(tmp_path):
    c, store = make(tmp_path)
    gpx = build_gpx([(52.37, 4.905), (52.37, 4.935)], "Rit")  # crosses 1011 & 1012
    body = c.post(
        "/api/import/gpx", content=gpx, headers={"Content-Type": "application/gpx+xml"}
    ).json()
    assert body["new_count"] == 2
    assert body["new_codes"] == ["1011", "1012"]

    store.set_collected({"1011"})  # now only 1012 is new
    body2 = c.post(
        "/api/import/gpx", content=gpx, headers={"Content-Type": "application/gpx+xml"}
    ).json()
    assert body2["new_count"] == 1
    assert body2["new_codes"] == ["1012"]
    assert body2["already_count"] == 1


def test_import_gpx_rejects_garbage(tmp_path):
    c, _ = make(tmp_path)
    assert c.post("/api/import/gpx", content="not gpx").status_code == 400


def test_export_track_returns_gpx(tmp_path):
    c, _ = make(tmp_path)
    r = c.post(
        "/api/export/track",
        json={"points": [[52.37, 4.90], [52.38, 4.91]], "name": "Rit"},
    )
    assert r.status_code == 200
    assert "<gpx" in r.text
    assert "attachment" in r.headers.get("content-disposition", "")
