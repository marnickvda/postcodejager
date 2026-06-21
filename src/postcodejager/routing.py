"""Route waypoints over paved ways via BRouter and count new postcodes."""
from dataclasses import dataclass

import httpx

from .coverage import collected_from_tracks
from .postcodes import PC4Index


@dataclass
class Route:
    points: list[tuple[float, float]]  # (lat, lon)
    distance_m: float


def route(
    waypoints: list[tuple[float, float]],
    *,
    base_url: str,
    profile: str = "trekking",
    http=None,
) -> Route:
    """Call BRouter for a route through ``(lat, lon)`` waypoints.

    BRouter expects ``lon,lat`` pairs joined by ``|`` in the ``lonlats`` query
    parameter and returns GeoJSON with ``[lon, lat]`` coordinates.
    """
    lonlats = "|".join(f"{lon},{lat}" for lat, lon in waypoints)
    params = {
        "lonlats": lonlats,
        "profile": profile,
        "alternativeidx": "0",
        "format": "geojson",
    }
    client = http or httpx.Client(timeout=60)
    resp = client.get(base_url, params=params)
    resp.raise_for_status()
    data = resp.json()
    feature = data["features"][0]
    coords = feature["geometry"]["coordinates"]
    # BRouter returns [lon, lat] or [lon, lat, elevation]; keep lon/lat only.
    points = [(c[1], c[0]) for c in coords]
    distance_m = float(feature["properties"].get("track-length", 0))
    return Route(points=points, distance_m=distance_m)


def new_postcodes(
    route_points: list[tuple[float, float]],
    index: PC4Index,
    already_collected: set[str],
    max_gap_m: float = 300.0,
) -> set[str]:
    """PC4 codes the route crosses that are not already collected."""
    crossed = collected_from_tracks([route_points], index, max_gap_m=max_gap_m)
    return crossed - set(already_collected)
