from postcodejager.geo import decode_polyline, haversine_m, densify


def test_decode_polyline_matches_known_value():
    # Google's canonical example encodes 3 points.
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert pts == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]


def test_haversine_known_distance():
    assert haversine_m((52.0, 4.0), (52.0, 4.0)) == 0
    d = haversine_m((52.0, 4.0), (52.01, 4.0))
    assert 1100 < d < 1130  # ~1.11 km per 0.01 deg latitude


def test_densify_inserts_points_for_large_gap():
    pts = [(52.0, 4.0), (52.0, 4.0 + 0.05)]  # ~3.4 km gap
    dense = densify(pts, max_gap_m=300)
    assert dense[0] == pts[0] and dense[-1] == pts[-1]
    gaps = [haversine_m(dense[i], dense[i + 1]) for i in range(len(dense) - 1)]
    assert max(gaps) <= 300 + 1e-6


def test_densify_keeps_short_segments():
    pts = [(52.0, 4.0), (52.0005, 4.0)]  # ~55 m
    assert densify(pts, max_gap_m=300) == pts
