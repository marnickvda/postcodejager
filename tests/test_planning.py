from postcodejager.planning import order_nearest_neighbour


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
