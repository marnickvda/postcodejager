import itertools

from postcodejager.geo import haversine_m
from postcodejager.planning import (
    order_areas,
    order_nearest_neighbour,
    path_length,
    plan_order,
    through_waypoints,
    two_opt,
)
from postcodejager.postcodes import PC4Index

# A unit square (lat, lon); side ~ 1.1 km.
A, B, C, D = (52.0, 5.0), (52.0, 5.01), (52.01, 5.01), (52.01, 5.0)


def _square(code: str, lat0: float, lon0: float, size: float = 0.01) -> dict:
    return {
        "type": "Feature",
        "properties": {"postcode": code},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon0, lat0],
                    [lon0 + size, lat0],
                    [lon0 + size, lat0 + size],
                    [lon0, lat0 + size],
                    [lon0, lat0],
                ]
            ],
        },
    }


def _index(*features: dict) -> PC4Index:
    return PC4Index.from_geojson(
        {"type": "FeatureCollection", "features": list(features)}
    )


# Three areas at the corners of a triangle, so every area has distinct
# previous/next neighbours (no degenerate collinear U-turns).
def _triangle_index() -> PC4Index:
    return _index(
        _square("A", 52.00, 5.00),
        _square("B", 52.00, 5.04),
        _square("C", 52.04, 5.02),
    )


def brute_optimal(points, loop):
    return min(path_length(list(p), loop) for p in itertools.permutations(points))


def test_order_visits_closest_first():
    # Same longitude; start at the south point, should walk north in order.
    pts = [(52.0, 5.0), (52.3, 5.0), (52.1, 5.0), (52.2, 5.0)]
    out = order_nearest_neighbour(pts)
    assert out[0] == (52.0, 5.0)
    assert out == [(52.0, 5.0), (52.1, 5.0), (52.2, 5.0), (52.3, 5.0)]


def test_short_lists_unchanged():
    assert order_nearest_neighbour([]) == []
    assert order_nearest_neighbour([(1.0, 1.0)]) == [(1.0, 1.0)]
    assert order_nearest_neighbour([(1.0, 1.0), (2.0, 2.0)]) == [(1.0, 1.0), (2.0, 2.0)]


def test_two_opt_removes_a_crossing():
    crossing = [A, C, B, D]  # zig-zag with an X
    out = two_opt(crossing, loop=False)
    assert set(out) == set(crossing)  # same points, reordered
    assert path_length(out, loop=False) < path_length(crossing, loop=False)


def test_two_opt_reaches_optimal_open_path():
    pts = [A, C, B, D]
    out = two_opt(pts, loop=False)
    assert abs(path_length(out, loop=False) - brute_optimal(pts, loop=False)) < 1e-6


def test_plan_order_loop_is_short_and_complete():
    pts = [A, C, B, D]
    out = plan_order(pts, loop=True)
    assert set(out) == {A, B, C, D}
    assert abs(path_length(out, loop=True) - brute_optimal(pts, loop=True)) < 1e-6


def test_through_waypoints_all_lie_inside_selected_areas():
    idx = _triangle_index()
    wps = through_waypoints(["A", "B", "C"], idx, loop=True)
    assert all(idx.code_for_point(wp) in {"A", "B", "C"} for wp in wps)


def test_through_waypoints_threads_through_each_area():
    idx = _triangle_index()
    wps = through_waypoints(["A", "B", "C"], idx, loop=True)
    # Distinct entry + exit per area (2 × 3) plus the closing point back to start.
    assert len(wps) == 7
    assert wps[0] == wps[-1]  # loop closes


def test_through_waypoints_entry_faces_prev_exit_faces_next():
    idx = _triangle_index()
    wps = through_waypoints(["A", "B", "C"], idx, loop=True)
    # Order is [A_enter, A_exit, B_enter, B_exit, C_enter, C_exit, close].
    b_enter, b_exit = wps[2], wps[3]
    a_cen, c_cen = idx.centroid("A"), idx.centroid("C")  # B's prev and next
    assert haversine_m(b_enter, a_cen) < haversine_m(b_exit, a_cen)  # enter → prev
    assert haversine_m(b_exit, c_cen) < haversine_m(b_enter, c_cen)  # exit → next


def test_through_waypoints_collapses_when_entry_equals_exit():
    # In a 2-area loop both neighbours are the same area, so entry and exit
    # coincide — each area contributes a single waypoint, not a micro-spur.
    idx = _index(_square("A", 52.00, 5.00), _square("B", 52.00, 5.04))
    wps = through_waypoints(["A", "B"], idx, loop=True)
    assert len(wps) == 3  # 1 (A) + 1 (B) + closing
    assert wps[0] == wps[-1]


def test_through_waypoints_open_path_does_not_close():
    idx = _triangle_index()
    wps = through_waypoints(["A", "B", "C"], idx, loop=False)
    assert wps[0] != wps[-1]  # open path: no return to start
    assert all(idx.code_for_point(wp) in {"A", "B", "C"} for wp in wps)


def test_through_waypoints_empty_is_empty():
    assert through_waypoints([], _triangle_index(), loop=True) == []


# A south-to-north line of areas, for anchoring tests.
LINE = [(52.0, 5.0), (52.3, 5.0), (52.1, 5.0), (52.2, 5.0)]


def test_order_areas_without_anchors_matches_plan_order():
    pts = [A, C, B, D]
    assert order_areas(pts, loop=True) == plan_order(pts, loop=True)
    assert order_areas(pts, loop=False) == plan_order(pts, loop=False)


def test_order_areas_loop_starts_near_home():
    home = (51.9, 5.0)  # just south of the southernmost area
    out = order_areas(LINE, loop=True, start=home)
    assert set(out) == set(LINE)
    # Home's nearest area is the southernmost; in a loop it neighbours home,
    # i.e. it is the first area out or the last one back.
    assert (52.0, 5.0) in (out[0], out[-1])


def test_order_areas_p2p_respects_fixed_endpoints():
    start, end = (51.9, 5.0), (52.4, 5.0)  # south of all areas / north of all
    out = order_areas(LINE, loop=False, start=start, end=end)
    assert out == [(52.0, 5.0), (52.1, 5.0), (52.2, 5.0), (52.3, 5.0)]


def test_through_waypoints_loop_bookends_with_start():
    idx = _triangle_index()
    home = (51.99, 5.00)
    wps = through_waypoints(["A", "B", "C"], idx, loop=True, start=home)
    assert wps[0] == home and wps[-1] == home  # ride out from home, back to home


def test_through_waypoints_p2p_bookends_with_start_and_end():
    idx = _triangle_index()
    start, end = (51.99, 5.00), (52.06, 5.03)
    wps = through_waypoints(["A", "B", "C"], idx, loop=False, start=start, end=end)
    assert wps[0] == start and wps[-1] == end
