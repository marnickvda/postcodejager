"""Order waypoints into a sensible visiting sequence.

A greedy nearest-neighbour pass is a good-enough heuristic for stringing a
handful of selected postcode centroids into a route; it is not a full TSP
solver, which is out of scope for v1.
"""
from .geo import haversine_m


def order_nearest_neighbour(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Greedy nearest-neighbour ordering of ``(lat, lon)`` points from the first."""
    if len(points) <= 2:
        return list(points)
    remaining = list(points)
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1]
        nxt = min(range(len(remaining)), key=lambda i: haversine_m(last, remaining[i]))
        ordered.append(remaining.pop(nxt))
    return ordered
