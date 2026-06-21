"""Geometry helpers: polyline decoding, distances, and densification.

All coordinates are ``(lat, lon)`` tuples in degrees.
"""
import math

import polyline as _polyline

EARTH_RADIUS_M = 6371000.0


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google/Strava encoded polyline into ``(lat, lon)`` points."""
    if not encoded:
        return []
    return [(round(lat, 6), round(lon, 6)) for lat, lon in _polyline.decode(encoded)]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in meters between two ``(lat, lon)`` points."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def densify(
    points: list[tuple[float, float]], max_gap_m: float = 300.0
) -> list[tuple[float, float]]:
    """Insert interpolated points so consecutive gaps are at most ``max_gap_m``.

    Keeps the original vertices; linearly interpolates in lat/lon, which is an
    acceptable approximation at the sub-kilometer scale used for postcode hits.
    """
    if len(points) < 2:
        return list(points)
    out: list[tuple[float, float]] = [points[0]]
    for a, b in zip(points, points[1:]):
        dist = haversine_m(a, b)
        if dist > max_gap_m:
            steps = math.ceil(dist / max_gap_m)
            for i in range(1, steps):
                t = i / steps
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out
