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


def test_pc4_reflects_collected(tmp_path):
    c, store = make(tmp_path)
    store.set_collected({"1011"})
    feats = c.get("/api/pc4").json()["features"]
    by_code = {
        f["properties"]["postcode"][:4]: f["properties"]["collected"] for f in feats
    }
    assert by_code["1011"] is True
    assert by_code["1012"] is False


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
