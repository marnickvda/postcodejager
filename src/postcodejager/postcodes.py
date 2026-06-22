"""PC4 postcode-area boundaries with a fast point-in-polygon index.

GeoJSON coordinates are ``[lon, lat]``; this module's public API takes and
returns ``(lat, lon)`` to match the rest of the codebase.
"""
import json
import math

from shapely.geometry import Point, mapping, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

# Property keys that may hold the 4-digit code across data sources.
CODE_PROP_CANDIDATES = ("postcode", "pc4", "pc4_code", "PC4", "postcode4")

# How far inside an area we aim to route, so a leg dips meaningfully into the
# postcode instead of clipping its edge. Capped by how deep the area allows.
MIN_ENTRY_DEPTH_M = 1000.0
_M_PER_DEG_LAT = 111_320.0  # metres per degree of latitude (≈constant)


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
        """A point well inside area ``code`` near the route corridor ``target``.

        ``target`` is a ``(lat, lon)`` hint for where the route passes. We aim
        for the closest point to that corridor that still lies at least
        ``MIN_ENTRY_DEPTH_M`` from the boundary, so each leg dips meaningfully
        into the postcode instead of clipping its edge — while staying on the
        corridor side rather than detouring to the centre. Areas too small to
        hold such a point fall back to going as deep as they allow.
        """
        poly = self._polys[code]
        tp = Point(target[1], target[0])
        # Express the target depth in degrees using the (shorter) longitude
        # scale, so the guaranteed clearance is at least MIN_ENTRY_DEPTH_M in
        # every direction. Buffering inward shrinks the area by that band; any
        # point left inside is then >= the target depth from the edge.
        m_per_deg = _M_PER_DEG_LAT * math.cos(math.radians(target[0]))
        depth_deg = MIN_ENTRY_DEPTH_M / m_per_deg
        inner = poly.buffer(-depth_deg)
        # Thin areas can't hold a 1 km-deep point; relax until something is left.
        while inner.is_empty and depth_deg > 1e-5:
            depth_deg /= 2
            inner = poly.buffer(-depth_deg)
        if inner.is_empty:
            return self.centroid(code)  # degenerate sliver: best-effort interior
        p = nearest_points(inner, tp)[0]  # deepest-enough point nearest the corridor
        return (p.y, p.x)

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
                    "properties": {
                        "postcode": code,
                        "collected": code in collected,
                        "prov": self._provinces.get(code),
                    },
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


def province_fc(raw: dict, simplify_tolerance: float | None = None) -> dict:
    """Display FeatureCollection from the official CBS provincie GeoJSON.

    Keeps one Feature per province with ``properties = {"name": <prov_name>}``
    (the source stores ``prov_name`` as a single-element list and carries extra
    fields) and an optionally simplified geometry. ``simplify_tolerance``
    (degrees) thins geometry for a lighter payload.
    """
    features = []
    for feat in raw["features"]:
        pn = feat.get("properties", {}).get("prov_name")
        name = pn[0] if isinstance(pn, list) else pn
        geom = shape(feat["geometry"])
        if simplify_tolerance:
            geom = geom.simplify(simplify_tolerance, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": mapping(geom),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def load_province_fc(path: str, simplify_tolerance: float | None = None) -> dict:
    """Load and transform the bundled CBS provincie GeoJSON for display."""
    with open(path) as f:
        return province_fc(json.load(f), simplify_tolerance)
