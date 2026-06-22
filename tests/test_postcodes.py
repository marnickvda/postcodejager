import json
import pathlib

from postcodejager.geo import haversine_m
from postcodejager.postcodes import PC4Index, province_fc

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"


def _square_index(code: str, lat0: float, lon0: float, size_deg: float) -> PC4Index:
    """A PC4Index holding a single square area for entry-point tests."""
    return PC4Index.from_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"postcode": code},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon0, lat0],
                                [lon0 + size_deg, lat0],
                                [lon0 + size_deg, lat0 + size_deg],
                                [lon0, lat0 + size_deg],
                                [lon0, lat0],
                            ]
                        ],
                    },
                }
            ],
        }
    )


def load():
    return PC4Index.from_geojson(json.loads(FIX.read_text()))


def test_codes():
    assert load().codes() == {"1011", "1012"}


def test_point_inside_first_square():
    assert load().code_for_point((52.37, 4.91)) == "1011"


def test_point_inside_second_square():
    assert load().code_for_point((52.37, 4.93)) == "1012"


def test_point_outside_returns_none():
    assert load().code_for_point((52.0, 4.0)) is None


def test_codes_for_points():
    idx = load()
    assert idx.codes_for_points([(52.37, 4.91), (52.37, 4.93), (0, 0)]) == {"1011", "1012"}


def test_centroid_within_polygon():
    idx = load()
    lat, lon = idx.centroid("1011")
    assert idx.code_for_point((lat, lon)) == "1011"


def test_entry_point_near_edge_and_inside():
    idx = load()
    cen = idx.centroid("1011")  # ~ (52.37, 4.91)
    ep = idx.entry_point("1011", (52.37, 4.80))  # corridor far to the west
    assert idx.code_for_point(ep) == "1011"  # still inside the area
    assert ep[1] < cen[1]  # nearer the west edge than the centre


def test_entry_point_target_inside_unchanged():
    idx = load()
    inside = idx.centroid("1011")
    assert idx.entry_point("1011", inside) == inside


def test_entry_point_dips_at_least_1km_into_typical_area():
    # ~2.7 km wide (E-W) — a realistic PC4 size that still fits a 1 km-deep point.
    idx = _square_index("9999", 51.98, 5.00, 0.04)
    ep = idx.entry_point("9999", (52.0, 4.0))  # corridor far to the west
    assert idx.code_for_point(ep) == "9999"  # inside the area
    west_edge = (ep[0], 5.00)  # nearest boundary is the west edge
    assert haversine_m(ep, west_edge) >= 950.0  # at least ~1 km in
    assert ep[1] < 5.02  # but stays on the corridor side, not a deep detour


def test_entry_point_small_area_goes_as_deep_as_possible():
    # ~1.1 km square — too thin to fit a 1 km-deep point, so just stay interior.
    idx = _square_index("8888", 52.0, 5.0, 0.01)
    ep = idx.entry_point("8888", (52.005, 4.0))  # corridor to the west
    assert idx.code_for_point(ep) == "8888"  # still a valid interior point


def test_provinces():
    idx = load()
    assert idx.province_of("1011") == "Noord-Holland"
    assert idx.codes_by_province() == {
        "Noord-Holland": {"1011"},
        "Utrecht": {"1012"},
    }


def test_to_feature_collection_includes_province():
    idx = load()
    props = {
        f["properties"]["postcode"]: f["properties"]
        for f in idx.to_feature_collection(set())["features"]
    }
    assert props["1011"]["prov"] == "Noord-Holland"
    assert props["1012"]["prov"] == "Utrecht"


def test_to_feature_collection_prov_is_none_when_missing():
    idx = PC4Index.from_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"postcode": "0000"},  # no prov_name
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[4.90, 52.30], [4.91, 52.30], [4.91, 52.31], [4.90, 52.31], [4.90, 52.30]]
                        ],
                    },
                }
            ],
        }
    )
    assert idx.to_feature_collection(set())["features"][0]["properties"]["prov"] is None


# Official CBS provincie GeoJSON stores prov_name as a single-element list and
# carries extra properties; province_fc unwraps the name and trims the rest.
RAW_PROVINCE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "prov_name": ["Drenthe"],
                "prov_code": "22",
                "geo_point_2d": [6.05, 52.85],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[6.0, 52.8], [6.1, 52.8], [6.1, 52.9], [6.0, 52.9], [6.0, 52.8]]
                ],
            },
        }
    ],
}


def test_province_fc_unwraps_name_and_trims_properties():
    f = province_fc(RAW_PROVINCE)["features"][0]
    assert f["properties"] == {"name": "Drenthe"}  # only name; extras dropped
    assert f["geometry"]["type"] == "Polygon"


def test_province_fc_accepts_plain_string_name():
    raw = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"prov_name": "Utrecht"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[5.0, 52.0], [5.1, 52.0], [5.1, 52.1], [5.0, 52.1], [5.0, 52.0]]
                    ],
                },
            }
        ],
    }
    assert province_fc(raw)["features"][0]["properties"]["name"] == "Utrecht"
