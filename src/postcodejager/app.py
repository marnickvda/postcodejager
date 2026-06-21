"""FastAPI app wiring the core modules into a local web tool."""
import logging
import pathlib
import threading
import time

from fastapi import Body, FastAPI, HTTPException, Request
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
from .storage import Store
from .strava import StravaClient, build_authorize_url

logger = logging.getLogger("postcodejager")

STATIC_DIR = pathlib.Path(__file__).parent / "static"
# Degrees of geometry simplification for the display layer (~100 m). Keeps the
# (gzipped) PC4 payload light; membership is still computed at full resolution.
DISPLAY_SIMPLIFY = 0.001


class ToggleRequest(BaseModel):
    code: str


class CodesRequest(BaseModel):
    codes: list[str]


class TrackRequest(BaseModel):
    points: list[tuple[float, float]]
    name: str = "Postcodejager route"


def create_app(
    settings: Settings,
    store: Store,
    index_provider,
    strava_client: StravaClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Postcodejager")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    strava = strava_client or StravaClient(
        settings.strava_client_id, settings.strava_client_secret
    )

    def _access_token() -> str:
        token = store.load_token()
        if not token:
            raise HTTPException(status_code=400, detail="Niet verbonden met Strava")
        if token.get("expires_at", 0) <= time.time() + 60 and token.get("refresh_token"):
            token = strava.refresh(token["refresh_token"])
            store.save_token(token)
        return token["access_token"]

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/api/status")
    def status():
        return {
            "connected": store.load_token() is not None,
            "collected_count": len(store.get_collected()),
            "total_count": len(index_provider().codes()),
            "last_sync": store.get_last_sync(),
        }

    @app.get("/auth/login")
    def login():
        url = build_authorize_url(settings.strava_client_id, settings.strava_redirect_uri)
        return RedirectResponse(url)

    @app.get("/auth/callback")
    def callback(code: str):
        token = strava.exchange_code(code, settings.strava_redirect_uri)
        store.save_token(token)
        return RedirectResponse("/")

    @app.post("/sync")
    def sync():
        access_token = _access_token()
        activities = strava.fetch_activities(access_token, after=store.get_last_sync())
        seen = store.seen_activity_ids()
        fresh = [a for a in activities if a.id not in seen]
        tracks = strava.tracks_for(fresh)
        codes = coverage_mod.collected_from_tracks(tracks, index_provider())
        store.set_collected(codes)
        for activity in fresh:
            store.mark_activity(activity.id)
        store.set_last_sync(int(time.time()))
        return {"added": len(fresh), "collected_count": len(store.get_collected())}

    # The simplified geometry is expensive to build and never changes, so
    # compute it once and let the browser cache it. "Collected" state is served
    # separately (small + dynamic) so reopening the page needs no geometry
    # download and a sync only refreshes the small list.
    geometry_cache: dict = {}
    geometry_lock = threading.Lock()

    def geometry_fc() -> dict:
        # Lock so a cold-start burst builds the simplified geometry once, not
        # once per concurrent request.
        with geometry_lock:
            if "fc" not in geometry_cache:
                geometry_cache["fc"] = index_provider().to_feature_collection(
                    set(), simplify_tolerance=DISPLAY_SIMPLIFY
                )
            return geometry_cache["fc"]

    @app.get("/api/pc4/geometry")
    def pc4_geometry():
        return JSONResponse(
            geometry_fc(),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/collected")
    def collected():
        return {"collected": sorted(store.get_collected())}

    @app.get("/api/provinces")
    def provinces():
        collected = store.get_collected()
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

    # --- planned selection (postcodes to include in the next route) -------
    @app.get("/api/planned")
    def planned():
        return {"planned": sorted(store.get_planned())}

    @app.post("/api/planned/toggle")
    def planned_toggle(req: ToggleRequest):
        return {"planned": sorted(store.toggle_planned(req.code))}

    @app.post("/api/planned/add")
    def planned_add(req: CodesRequest):
        return {"planned": sorted(store.add_planned(set(req.codes)))}

    @app.post("/api/planned/clear")
    def planned_clear():
        store.clear_planned()
        return {"planned": []}

    @app.post("/api/route/auto")
    def route_auto(loop: bool = Body(True, embed=True)):
        idx = index_provider()
        planned = [c for c in store.get_planned() if c in idx.codes()]
        if len(planned) < 2:
            raise HTTPException(
                status_code=400,
                detail="Selecteer minstens 2 postcodes voor een route",
            )
        # Order the centroids into a smooth tour (nearest-neighbour + 2-opt),
        # and close the loop back to the start when requested.
        ordered = planning_mod.plan_order(
            [idx.centroid(c) for c in planned], loop=loop
        )
        waypoints = ordered + ([ordered[0]] if loop else [])
        try:
            result = routing_mod.route(
                waypoints,
                base_url=settings.brouter_base_url,
                profile=settings.brouter_profile,
            )
        except Exception as exc:  # log the detail, show the user a clean message
            logger.warning("route_auto failed: %r", exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "Routeren mislukt. Liggen de postcodes te ver uit elkaar of is "
                    "de routeserver even niet bereikbaar? Probeer het opnieuw."
                ),
            )
        new = routing_mod.new_postcodes(result.points, idx, store.get_collected())
        line = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in result.points],
            },
        }
        return {
            "geojson": line,
            "distance_m": result.distance_m,
            "new_count": len(new),
            "new_codes": sorted(new),
            "selected_count": len(planned),
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
        idx = index_provider()
        crossed = coverage_mod.collected_from_tracks([points], idx)
        collected = store.get_collected()
        new = sorted(crossed - collected)
        line = {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in points],
            },
        }
        return {
            "new_count": len(new),
            "new_codes": new,
            "crossed_count": len(crossed),
            "already_count": len(crossed & collected),
            "geojson": line,
        }

    @app.post("/api/export/track")
    def export_track(req: TrackRequest):
        xml = build_gpx(req.points, req.name)
        return Response(
            content=xml,
            media_type="application/gpx+xml",
            headers={"Content-Disposition": 'attachment; filename="route.gpx"'},
        )

    return app
