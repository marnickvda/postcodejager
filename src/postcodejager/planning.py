"""Order waypoints into a sensible, smooth visiting sequence.

A greedy nearest-neighbour pass strings the selected postcode centroids
together; a 2-opt improvement pass then removes crossings so the route flows
instead of zig-zagging. This is a good-enough heuristic for a handful of
waypoints, not a full TSP solver.
"""
from .geo import haversine_m

# Above this many waypoints, 2-opt's O(n^2) passes get expensive; fall back to
# nearest-neighbour only so route planning stays responsive.
TWO_OPT_MAX = 80


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


def path_length(points: list[tuple[float, float]], loop: bool) -> float:
    """Total length in meters; if ``loop`` add the closing edge back to start."""
    if len(points) < 2:
        return 0.0
    total = sum(haversine_m(points[i], points[i + 1]) for i in range(len(points) - 1))
    if loop:
        total += haversine_m(points[-1], points[0])
    return total


def two_opt(
    points: list[tuple[float, float]], loop: bool = False
) -> list[tuple[float, float]]:
    """Improve an ordering by repeatedly reversing segments that shorten it.

    Removes self-crossings, so the resulting path/loop flows smoothly.
    """
    if len(points) < 4 or len(points) > TWO_OPT_MAX:
        return list(points)
    route = list(points)
    n = len(route)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for k in range(i + 1, n):
                candidate = route[:i] + route[i : k + 1][::-1] + route[k + 1 :]
                if path_length(candidate, loop) + 1e-6 < path_length(route, loop):
                    route = candidate
                    improved = True
    return route


def plan_order(
    points: list[tuple[float, float]], loop: bool = True
) -> list[tuple[float, float]]:
    """Nearest-neighbour seed, then 2-opt — the ordering used for routing."""
    return two_opt(order_nearest_neighbour(points), loop=loop)
