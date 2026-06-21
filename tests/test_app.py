import json
import pathlib

import httpx
import polyline
import respx
from fastapi.testclient import TestClient

from postcodejager.app import create_app
from postcodejager.config import load_settings
from postcodejager.gpx import build_gpx
from postcodejager.postcodes import PC4Index

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"

# BRouter emits 3D coords: [lon, lat, elevation].
BROUTER_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"track-length": "3500"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[4.905, 52.37, 1.0], [4.935, 52.37, 2.0]],
            },
        }
    ],
}

STRAVA_RE = r"https://www\.strava\.com/.*"


def client():
    idx = PC4Index.from_geojson(json.loads(FIX.read_text()))
    settings = load_settings({"BROUTER_BASE_URL": "https://brouter.test/brouter"})
    return TestClient(create_app(settings, lambda: idx))


# --- geometry ---------------------------------------------------------------
def test_geometry_endpoint_is_cacheable():
    r = client().get("/api/pc4/geometry")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert {f["properties"]["postcode"][:4] for f in feats} == {"1011", "1012"}
    assert "max-age" in r.headers.get("cache-control", "")


# --- stateless compute over browser-supplied state --------------------------
def test_provinces_from_collected():
    by = {
        p["name"]: p
        for p in client().post("/api/provinces", json={"collected": ["1011"]}).json()[
            "provinces"
        ]
    }
    assert by["Noord-Holland"]["collected"] == 1
    assert by["Noord-Holland"]["percent"] == 100.0
    assert by["Utrecht"]["collected"] == 0


def test_selection_impact():
    body = client().post(
        "/api/selection/impact", json={"collected": ["1011"], "planned": ["1012"]}
    ).json()
    assert body["new"] == 1
    assert body["current_percent"] == 50.0
    assert body["projected_percent"] == 100.0
    provs = {p["name"]: p for p in body["provinces"]}
    assert provs["Utrecht"]["new"] == 1
    assert "Noord-Holland" not in provs


def test_route_auto_through_selected():
    with respx.mock(assert_all_mocked=False) as router:
        router.get(url__regex=r"https://brouter\.test/brouter.*").mock(
            return_value=httpx.Response(200, json=BROUTER_GEOJSON)
        )
        r = client().post(
            "/api/route/auto",
            json={"planned": ["1011", "1012"], "collected": ["1011"], "loop": True},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["new_codes"] == ["1012"]  # 1011 already collected
    assert body["distance_m"] == 3500.0


def test_route_auto_requires_at_least_two():
    assert client().post("/api/route/auto", json={"planned": ["1011"]}).status_code == 400


def test_route_auto_hides_raw_error():
    with respx.mock(assert_all_mocked=False) as router:
        router.get(url__regex=r"https://brouter\.test/brouter.*").mock(
            return_value=httpx.Response(500, text="brouter-internal-boom")
        )
        r = client().post("/api/route/auto", json={"planned": ["1011", "1012"]})
    assert r.status_code == 502
    assert "brouter-internal-boom" not in r.json()["detail"]


def test_import_gpx_returns_crossed():
    gpx = build_gpx([(52.37, 4.905), (52.37, 4.935)], "Rit")
    body = client().post(
        "/api/import/gpx", content=gpx, headers={"Content-Type": "application/gpx+xml"}
    ).json()
    assert body["crossed"] == ["1011", "1012"]
    assert body["geojson"]["geometry"]["type"] == "LineString"


def test_import_gpx_rejects_garbage():
    assert client().post("/api/import/gpx", content="not gpx").status_code == 400


def test_export_track_returns_gpx():
    r = client().post(
        "/api/export/track",
        json={"points": [[52.37, 4.90], [52.38, 4.91]], "name": "Rit"},
    )
    assert r.status_code == 200
    assert "<gpx" in r.text
    assert "attachment" in r.headers.get("content-disposition", "")


# --- Strava (mocked; secret stays server-side) ------------------------------
def test_strava_exchange():
    with respx.mock(assert_all_mocked=False) as router:
        router.post("https://www.strava.com/oauth/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "AT", "refresh_token": "RT", "expires_at": 9}
            )
        )
        r = client().post("/api/strava/exchange", json={"code": "xyz"})
    assert r.json()["access_token"] == "AT"


def test_sync_computes_collected():
    poly = polyline.encode([(52.37, 4.905), (52.37, 4.935)])
    page1 = [
        {
            "id": 1,
            "name": "rit",
            "start_date": "2026-06-20T08:00:00Z",
            "map": {"summary_polyline": poly},
        }
    ]
    with respx.mock(assert_all_mocked=False) as router:
        router.get("https://www.strava.com/api/v3/athlete/activities").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=[]),
            ]
        )
        r = client().post("/api/sync", json={"access_token": "AT"})
    body = r.json()
    assert set(body["collected"]) == {"1011", "1012"}
    assert body["activities"] == 1
