"""PC4 postcode-area boundaries with a fast point-in-polygon index.

GeoJSON coordinates are ``[lon, lat]``; this module's public API takes and
returns ``(lat, lon)`` to match the rest of the codebase.
"""
import json

from shapely.geometry import Point, mapping, shape
from shapely.ops import nearest_points
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

    def __init__(self, polygons: dict, provinces: dict | None = None):
        # polygons: code -> shapely geometry in lon/lat coordinates
        self._polys = polygons
        self._provinces = provinces or {}  # code -> province name
        self._codes = list(polygons)
        self._geoms = [polygons[c] for c in self._codes]
        self._tree = STRtree(self._geoms)

    @classmethod
    def from_geojson(cls, data: dict) -> "PC4Index":
        polys: dict = {}
        provinces: dict = {}
        for feat in data["features"]:
            props = feat.get("properties", {})
            code = _code_of(props)
            polys[code] = shape(feat["geometry"])
            prov = props.get("prov_name")
            if prov:
                provinces[code] = str(prov)
        return cls(polys, provinces)

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

    def province_of(self, code: str) -> str | None:
        return self._provinces.get(code)

    def entry_point(
        self, code: str, target: tuple[float, float]
    ) -> tuple[float, float]:
        """A point inside area ``code`` near the route corridor ``target``.

        ``target`` is a ``(lat, lon)`` hint for where the route passes. The route
        only needs to touch the area, so instead of its centre we return the
        point closest to ``target`` nudged just inside the edge — large areas get
        clipped at the boundary instead of forcing a deep detour to the middle.
        """
        poly = self._polys[code]
        tp = Point(target[1], target[0])
        if poly.contains(tp):
            return (target[0], target[1])
        near = nearest_points(poly, tp)[0]  # boundary point closest to target
        rep = poly.representative_point()  # a point guaranteed inside
        x = near.x + 0.25 * (rep.x - near.x)
        y = near.y + 0.25 * (rep.y - near.y)
        return (y, x)

    def codes_by_province(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for code, prov in self._provinces.items():
            out.setdefault(prov, set()).add(code)
        return out

    def to_feature_collection(
        self, collected: set[str], simplify_tolerance: float | None = None
    ) -> dict:
        """GeoJSON for display, each area tagged with ``collected`` (bool).

        ``simplify_tolerance`` (degrees) thins geometry for lighter payloads;
        ``None`` keeps full resolution.
        """
        features = []
        for code in self._codes:
            geom = self._polys[code]
            if simplify_tolerance:
                geom = geom.simplify(simplify_tolerance, preserve_topology=True)
            features.append(
                {
                    "type": "Feature",
                    "properties": {"postcode": code, "collected": code in collected},
                    "geometry": mapping(geom),
                }
            )
        return {"type": "FeatureCollection", "features": features}


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
