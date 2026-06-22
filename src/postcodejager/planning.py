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


def _nn_from(
    points: list[tuple[float, float]], seed: tuple[float, float]
) -> list[tuple[float, float]]:
    """Greedy nearest-neighbour ordering, starting from the point nearest ``seed``."""
    remaining = list(points)
    first = min(range(len(remaining)), key=lambda i: haversine_m(seed, remaining[i]))
    ordered = [remaining.pop(first)]
    while remaining:
        last = ordered[-1]
        nxt = min(range(len(remaining)), key=lambda i: haversine_m(last, remaining[i]))
        ordered.append(remaining.pop(nxt))
    return ordered


def _two_opt_pinned(
    seq: list[tuple[float, float]], *, loop: bool, lo: int, hi: int
) -> list[tuple[float, float]]:
    """2-opt over ``seq``, only reversing within the window ``[lo, hi]``.

    Nodes outside the window (anchored start/end) keep their positions while the
    movable middle is optimised. With ``lo=0, hi=len-1`` this is plain 2-opt.
    """
    if hi - lo < 2 or len(seq) > TWO_OPT_MAX:
        return list(seq)
    route = list(seq)
    improved = True
    while improved:
        improved = False
        for i in range(lo, hi):
            for k in range(i + 1, hi + 1):
                candidate = route[:i] + route[i : k + 1][::-1] + route[k + 1 :]
                if path_length(candidate, loop) + 1e-6 < path_length(route, loop):
                    route = candidate
                    improved = True
    return route


def order_areas(
    points: list[tuple[float, float]],
    *,
    loop: bool,
    start: tuple[float, float] | None = None,
    end: tuple[float, float] | None = None,
) -> list[tuple[float, float]]:
    """Order area points, optionally anchored to a fixed ``start`` and/or ``end``.

    The anchors are coordinates the route begins/ends at (a home or finish), not
    areas themselves: nearest-neighbour is seeded from ``start`` and a pinned
    2-opt keeps the anchors at the ends while the middle is optimised. ``end`` is
    only honoured for an open path (it coincides with ``start`` in a loop). With
    no anchors this is exactly :func:`plan_order`.
    """
    if start is None and end is None:
        return plan_order(points, loop=loop)
    if not points:
        return []
    ordered = _nn_from(points, start if start is not None else points[0])
    head = [start] if start is not None else []
    tail = [end] if (end is not None and not loop) else []
    seq = head + ordered + tail
    seq = _two_opt_pinned(seq, loop=loop, lo=len(head), hi=len(seq) - 1 - len(tail))
    return seq[len(head) : len(seq) - len(tail)]


# Entry and exit waypoints closer than this collapse to one point, so an area
# the route can't meaningfully thread through doesn't add a tiny back-and-forth.
COLLAPSE_M = 40.0


def through_waypoints(
    ordered_codes: list[str],
    idx,
    *,
    loop: bool,
    start: tuple[float, float] | None = None,
    end: tuple[float, float] | None = None,
):
    """Entry/exit waypoints that thread the route *through* each ordered area.

    For each area, emit a waypoint just inside the edge facing the previous area
    and another just inside the edge facing the next one, so the route flows
    through the polygon instead of diving to a single interior point and back
    out. The two collapse to one for areas too small — or too sandwiched between
    same-direction neighbours — to thread. Neighbour targets wrap around for a
    loop and clamp at the ends for an open path. ``idx`` is a ``PC4Index`` (uses
    ``centroid`` and ``entry_point``).

    ``start``/``end`` are optional fixed coordinates the route begins/ends at. A
    loop rides out from ``start`` and back to it (``end`` ignored); an open path
    runs from ``start`` to ``end``. Without anchors a loop closes on its first
    area and an open path is left open — the original behaviour.
    """
    n = len(ordered_codes)
    if n == 0:
        return []
    cents = [idx.centroid(c) for c in ordered_codes]
    areas: list[tuple[float, float]] = []
    for i, code in enumerate(ordered_codes):
        if loop:
            prev_c, next_c = cents[(i - 1) % n], cents[(i + 1) % n]
        else:
            prev_c, next_c = cents[max(0, i - 1)], cents[min(n - 1, i + 1)]
        enter = idx.entry_point(code, prev_c)
        leave = idx.entry_point(code, next_c)
        areas.append(enter)
        if haversine_m(enter, leave) > COLLAPSE_M:
            areas.append(leave)
    if loop:
        if start is not None:
            return [start, *areas, start]  # out from home, back to home
        return [*areas, areas[0]]  # no anchor: close on the first area
    head = [start] if start is not None else []
    tail = [end] if end is not None else []
    return [*head, *areas, *tail]
