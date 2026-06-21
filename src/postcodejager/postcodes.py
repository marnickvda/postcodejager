"""PC4 postcode-area boundaries with a fast point-in-polygon index.

GeoJSON coordinates are ``[lon, lat]``; this module's public API takes and
returns ``(lat, lon)`` to match the rest of the codebase.
"""
import json

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

# Property keys that may hold the 4-digit code across data sources.
CODE_PROP_CANDIDATES = ("postcode", "pc4", "pc4_code", "PC4", "postcode4")


def _code_of(props: dict) -> str:
    for key in CODE_PROP_CANDIDATES:
        value = props.get(key)
        if value is not None:
            return str(value).strip()[:4]
    raise KeyError(f"no PC4 code property in {list(props)}")


class PC4Index:
    """Spatial index over PC4 polygons for point-in-polygon lookups."""

    def __init__(self, polygons: dict):
        # polygons: code -> shapely geometry in lon/lat coordinates
        self._polys = polygons
        self._codes = list(polygons)
        self._geoms = [polygons[c] for c in self._codes]
        self._tree = STRtree(self._geoms)

    @classmethod
    def from_geojson(cls, data: dict) -> "PC4Index":
        polys: dict = {}
        for feat in data["features"]:
            code = _code_of(feat.get("properties", {}))
            polys[code] = shape(feat["geometry"])
        return cls(polys)

    def codes(self) -> set[str]:
        return set(self._codes)

    def code_for_point(self, point: tuple[float, float]) -> str | None:
        """Return the PC4 code containing ``(lat, lon)``, or ``None``."""
        p = Point(point[1], point[0])  # shapely wants (x=lon, y=lat)
        for idx in self._tree.query(p):
            if self._geoms[idx].contains(p):
                return self._codes[idx]
        return None

    def codes_for_points(self, points: list[tuple[float, float]]) -> set[str]:
        found: set[str] = set()
        for pt in points:
            code = self.code_for_point(pt)
            if code:
                found.add(code)
        return found

    def centroid(self, code: str) -> tuple[float, float]:
        """A representative interior point of the area, as ``(lat, lon)``."""
        c = self._polys[code].representative_point()
        return (c.y, c.x)


def download_pc4_geojson(dest: str, url: str, http=None) -> str:
    """Download a PC4 GeoJSON to ``dest`` and return the path."""
    import httpx

    client = http or httpx.Client(timeout=120)
    resp = client.get(url)
    resp.raise_for_status()
    with open(dest, "w") as f:
        f.write(resp.text)
    return dest


def load_pc4(path: str) -> PC4Index:
    with open(path) as f:
        return PC4Index.from_geojson(json.load(f))
