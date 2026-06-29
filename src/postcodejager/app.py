"""FastAPI app — a stateless compute backend.

All user state (Strava tokens, collected postcodes, the selection) lives in the
browser's localStorage. The backend only does work that needs Python/shapely,
the PC4 data, or the Strava client secret: token exchange, fetching+matching
rides, routing, and GPX. It stores nothing.
"""
import logging
import pathlib
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import coverage as coverage_mod
from . import planning as planning_mod
from . import routing as routing_mod
from .config import Settings
from .gpx import build_gpx, parse_gpx_points
from .postcodes import load_province_fc
from .strava import StravaClient, build_authorize_url

logger = logging.getLogger("postcodejager")

STATIC_DIR = pathlib.Path(__file__).parent / "static"
# Province boundaries (Kadaster, CC0) from OpenDataSoft, bundled with the package.
PROVINCE_GEOJSON = pathlib.Path(__file__).parent / "data" / "provinces.geojson"
# Degrees of geometry simplification for the display layer (~100 m).
DISPLAY_SIMPLIFY = 0.001


class ExchangeRequest(BaseModel):
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SyncRequest(BaseModel):
    access_token: str
    after: int | None = None


class RouteRequest(BaseModel):
    planned: list[str]
    collected: list[str] = []
    loop: bool = True
    start: tuple[float, float] | None = None  # (lat, lon) the route begins/ends at
    end: tuple[float, float] | None = None  # (lat, lon) finish for a point-to-point


class ManualRouteRequest(BaseModel):
    waypoints: list[tuple[float, float]]  # ordered (lat, lon)
    collected: list[str] = []


class CollectedRequest(BaseModel):
    collected: list[str] = []


class ImpactRequest(BaseModel):
    collected: list[str] = []
    planned: list[str] = []


class TrackRequest(BaseModel):
    points: list[tuple[float, float]]
    name: str = "Postcodejager route"


def create_app(
    settings: Settings,
    index_provider,
    strava_client=None,
    rate_limit: int = 120,
    rate_window: int = 60,
) -> FastAPI:
    app = FastAPI(title="Postcodejager")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Simple per-IP rate limit on the API to curb abuse of the Strava/BRouter
    # proxying (in-memory; honours X-Forwarded-For behind the Caddy proxy).
    hits: dict[str, list[float]] = {}

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            fwd = request.headers.get("x-forwarded-for")
            ip = (
                fwd.split(",")[0].strip()
                if fwd
                else (request.client.host if request.client else "?")
            )
            now = time.time()
            cutoff = now - rate_window
            q = hits.setdefault(ip, [])
            while q and q[0] < cutoff:
                q.pop(0)
            if len(q) >= rate_limit:
                return JSONResponse(
                    {"detail": "Te veel verzoeken. Probeer het zo opnieuw."},
                    status_code=429,
                )
            q.append(now)
        return await call_next(request)
    strava = strava_client or StravaClient(
        settings.strava_client_id, settings.strava_client_secret
    )

    geometry_cache: dict = {}
    geometry_lock = threading.Lock()

    def geometry_fc() -> dict:
        with geometry_lock:
            if "fc" not in geometry_cache:
                geometry_cache["fc"] = index_provider().to_feature_collection(
                    set(), simplify_tolerance=DISPLAY_SIMPLIFY
                )
            return geometry_cache["fc"]

    provinces_geometry_cache: dict = {}
    provinces_geometry_lock = threading.Lock()

    def provinces_geometry_fc() -> dict:
        with provinces_geometry_lock:
            if "fc" not in provinces_geometry_cache:
                provinces_geometry_cache["fc"] = load_province_fc(
                    str(PROVINCE_GEOJSON), simplify_tolerance=DISPLAY_SIMPLIFY
                )
            return provinces_geometry_cache["fc"]

    def _line(points) -> dict:
        return {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in points],
            },
        }

    # --- pages ------------------------------------------------------------
    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/privacy")
    def privacy():
        return FileResponse(str(STATIC_DIR / "privacy.html"))

    @app.get("/voorwaarden")
    def voorwaarden():
        return FileResponse(str(STATIC_DIR / "voorwaarden.html"))

    @app.get("/auth/login")
    def login():
        url = build_authorize_url(settings.strava_client_id, settings.strava_redirect_uri)
        return RedirectResponse(url)

    @app.get("/auth/callback")
    def callback():
        # The browser reads ?code= and finishes the exchange; just serve the app.
        return FileResponse(str(STATIC_DIR / "index.html"))

    # --- Strava (the client secret never leaves the server) ---------------
    @app.post("/api/strava/exchange")
    def strava_exchange(req: ExchangeRequest):
        try:
            return strava.exchange_code(req.code, settings.strava_redirect_uri)
        except Exception as exc:
            logger.warning("strava exchange failed: %r", exc)
            raise HTTPException(status_code=502, detail="Strava-koppeling mislukt.")

    @app.post("/api/strava/refresh")
    def strava_refresh(req: RefreshRequest):
        try:
            return strava.refresh(req.refresh_token)
        except Exception as exc:
            logger.warning("strava refresh failed: %r", exc)
            raise HTTPException(status_code=502, detail="Token verversen mislukt.")

    @app.post("/api/sync")
    def sync(req: SyncRequest):
        try:
            activities = strava.fetch_activities(req.access_token, after=req.after)
        except Exception as exc:
            logger.warning("sync failed: %r", exc)
            raise HTTPException(status_code=502, detail="Ophalen van ritten mislukt.")
        codes = coverage_mod.collected_from_tracks(
            strava.tracks_for(activities), index_provider()
        )
        latest = max((a.start_epoch for a in activities), default=req.after or 0)
        return {
            "collected": sorted(codes),
            "latest": latest,
            "activities": len(activities),
        }

    # --- geometry (static, browser-cacheable) -----------------------------
    @app.get("/api/pc4/geometry")
    def pc4_geometry():
        return JSONResponse(
            geometry_fc(), headers={"Cache-Control": "public, max-age=86400"}
        )

    @app.get("/api/provinces/geometry")
    def provinces_geometry_endpoint():
        return JSONResponse(
            provinces_geometry_fc(),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # --- stateless compute over browser-supplied state --------------------
    @app.post("/api/provinces")
    def provinces(req: CollectedRequest):
        collected = set(req.collected)
        rows = []
        for name, codes in index_provider().codes_by_province().items():
            total = len(codes)
            done = len(codes & collected)
            rows.append(
                {
                    "name": name,
                    "total": total,
                    "collected": done,
                    "percent": round(done / total * 100, 1) if total else 0.0,
                }
            )
        rows.sort(key=lambda r: r["name"])
        return {"provinces": rows}

    @app.post("/api/selection/impact")
    def selection_impact(req: ImpactRequest):
        idx = index_provider()
        collected = set(req.collected)
        new = (set(req.planned) & idx.codes()) - collected
        total = len(idx.codes())
        provinces = []
        for name, codes in idx.codes_by_province().items():
            prov_new = len(codes & new)
            if prov_new:
                provinces.append(
                    {
                        "name": name,
                        "new": prov_new,
                        "total": len(codes),
                        "increase": round(prov_new / len(codes) * 100, 1),
                    }
                )
        provinces.sort(key=lambda p: -p["increase"])
        pct = lambda n: round(n / total * 100, 1) if total else 0.0  # noqa: E731
        return {
            "new": len(new),
            "current_percent": pct(len(collected)),
            "projected_percent": pct(len(collected) + len(new)),
            "increase": pct(len(new)),
            "provinces": provinces,
        }

    @app.post("/api/route/auto")
    def route_auto(req: RouteRequest):
        idx = index_provider()
        planned = [c for c in req.planned if c in idx.codes()]
        if len(planned) < 2:
            raise HTTPException(
                status_code=400,
                detail="Selecteer minstens 2 postcodes voor een route",
            )
        start = tuple(req.start) if req.start else None
        end = tuple(req.end) if (req.end and not req.loop) else None
        cents = [idx.centroid(c) for c in planned]
        ordered_pts = planning_mod.order_areas(
            cents, loop=req.loop, start=start, end=end
        )
        code_by_pt = {cents[i]: planned[i] for i in range(len(planned))}
        ordered_codes = [code_by_pt[p] for p in ordered_pts]
        # Thread the route through each area with entry/exit waypoints, anchored
        # out from / back to the start (loop) or start→end (point-to-point), so
        # it flows instead of diving into each centre and back out again.
        waypoints = planning_mod.through_waypoints(
            ordered_codes, idx, loop=req.loop, start=start, end=end
        )
        try:
            result = routing_mod.route(
                waypoints,
                base_url=settings.brouter_base_url,
                profile=settings.brouter_profile,
            )
        except Exception as exc:
            logger.warning("route_auto failed: %r", exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "Routeren mislukt. Liggen de postcodes te ver uit elkaar of is "
                    "de routeserver even niet bereikbaar? Probeer het opnieuw."
                ),
            )
        new = routing_mod.new_postcodes(result.points, idx, set(req.collected))
        return {
            "geojson": _line(result.points),
            "distance_m": result.distance_m,
            "new_count": len(new),
            "new_codes": sorted(new),
            "selected_count": len(planned),
            "waypoints": [list(w) for w in waypoints],
        }

    @app.post("/api/route/manual")
    def route_manual(req: ManualRouteRequest):
        idx = index_provider()
        waypoints = [tuple(w) for w in req.waypoints]
        if len(waypoints) < 2:
            raise HTTPException(
                status_code=400,
                detail="Een route heeft minstens 2 punten nodig",
            )
        try:
            result = routing_mod.route(
                waypoints,
                base_url=settings.brouter_base_url,
                profile=settings.brouter_profile,
            )
        except Exception as exc:
            logger.warning("route_manual failed: %r", exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "Routeren mislukt. Liggen de punten te ver uit elkaar of is "
                    "de routeserver even niet bereikbaar? Probeer het opnieuw."
                ),
            )
        new = routing_mod.new_postcodes(result.points, idx, set(req.collected))
        return {
            "geojson": _line(result.points),
            "distance_m": result.distance_m,
            "new_count": len(new),
            "new_codes": sorted(new),
            "waypoints": [list(w) for w in waypoints],
        }

    @app.post("/api/import/gpx")
    async def import_gpx(request: Request):
        text = (await request.body()).decode("utf-8", errors="replace")
        try:
            points = parse_gpx_points(text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Kon GPX niet lezen: {exc}")
        if len(points) < 2:
            raise HTTPException(status_code=400, detail="Geen route gevonden in GPX")
        crossed = coverage_mod.collected_from_tracks([points], index_provider())
        return {"crossed": sorted(crossed), "geojson": _line(points)}

    @app.post("/api/export/track")
    def export_track(req: TrackRequest):
        xml = build_gpx(req.points, req.name, track_type=settings.gpx_track_type or None)
        return Response(
            content=xml,
            media_type="application/gpx+xml",
            headers={"Content-Disposition": 'attachment; filename="route.gpx"'},
        )

    return app
