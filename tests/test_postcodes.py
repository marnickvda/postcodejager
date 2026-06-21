import json
import pathlib

from postcodejager.postcodes import PC4Index

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"


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


def test_provinces():
    idx = load()
    assert idx.province_of("1011") == "Noord-Holland"
    assert idx.codes_by_province() == {
        "Noord-Holland": {"1011"},
        "Utrecht": {"1012"},
    }
