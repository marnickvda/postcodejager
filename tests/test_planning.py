import itertools

from postcodejager.planning import (
    order_nearest_neighbour,
    path_length,
    plan_order,
    two_opt,
)

# A unit square (lat, lon); side ~ 1.1 km.
A, B, C, D = (52.0, 5.0), (52.0, 5.01), (52.01, 5.01), (52.01, 5.0)


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
