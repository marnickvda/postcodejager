import json
import pathlib

import httpx
import respx

from postcodejager.postcodes import PC4Index
from postcodejager.routing import new_postcodes, route

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"

BROUTER_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"track-length": "3500", "filtered ascend": "5"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[4.905, 52.37], [4.935, 52.37]],
            },
        }
    ],
}


@respx.mock
def test_route_parses_points_and_distance():
    respx.get(url__regex=r"https://brouter\.test/brouter.*").mock(
        return_value=httpx.Response(200, json=BROUTER_GEOJSON)
    )
    r = route([(52.37, 4.905), (52.37, 4.935)], base_url="https://brouter.test/brouter")
    assert r.distance_m == 3500.0
    assert r.points[0] == (52.37, 4.905)  # converted back to (lat, lon)


def test_new_postcodes_excludes_already_collected():
    idx = PC4Index.from_geojson(json.loads(FIX.read_text()))
    pts = [(52.37, 4.905), (52.37, 4.935)]
    assert new_postcodes(pts, idx, already_collected={"1011"}) == {"1012"}
