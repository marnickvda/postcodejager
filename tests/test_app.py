import json
import pathlib

import httpx
import respx
from fastapi.testclient import TestClient

from postcodejager.app import create_app
from postcodejager.config import load_settings
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


def test_route_counts_new_postcodes(tmp_path):
    c, _ = make(tmp_path)
    # assert_all_mocked=False lets the TestClient->app request pass through while
    # the app's internal BRouter call is mocked.
    with respx.mock(assert_all_mocked=False) as router:
        router.get(url__regex=r"https://brouter\.test/brouter.*").mock(
            return_value=httpx.Response(200, json=BROUTER_GEOJSON)
        )
        r = c.post("/api/route", json={"waypoints": [[52.37, 4.905], [52.37, 4.935]]})
    assert r.status_code == 200
    body = r.json()
    assert body["new_count"] == 2
    assert sorted(body["new_codes"]) == ["1011", "1012"]
    assert body["distance_m"] == 3500.0


def test_export_returns_gpx_attachment(tmp_path):
    c, _ = make(tmp_path)
    with respx.mock(assert_all_mocked=False) as router:
        router.get(url__regex=r"https://brouter\.test/brouter.*").mock(
            return_value=httpx.Response(200, json=BROUTER_GEOJSON)
        )
        r = c.post(
            "/api/export",
            json={"waypoints": [[52.37, 4.905], [52.37, 4.935]], "name": "Rit"},
        )
    assert r.status_code == 200
    assert "<gpx" in r.text
    assert "attachment" in r.headers.get("content-disposition", "")
