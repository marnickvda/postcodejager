"""Turn GPS tracks into the set of PC4 areas they pass through."""
from .geo import densify
from .postcodes import PC4Index


def collected_from_tracks(
    tracks: list[list[tuple[float, float]]],
    index: PC4Index,
    max_gap_m: float = 300.0,
) -> set[str]:
    """Return the set of PC4 codes touched by any of the ``(lat, lon)`` tracks."""
    collected: set[str] = set()
    for track in tracks:
        dense = densify(track, max_gap_m=max_gap_m)
        collected |= index.codes_for_points(dense)
    return collected
