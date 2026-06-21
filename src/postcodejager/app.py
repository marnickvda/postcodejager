"""FastAPI app wiring the core modules into a local web tool."""
import pathlib
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import coverage as coverage_mod
from . import routing as routing_mod
from .config import Settings
from .gpx import build_gpx
from .storage import Store
from .strava import StravaClient, build_authorize_url

STATIC_DIR = pathlib.Path(__file__).parent / "static"
# Degrees of geometry simplification for the display layer (~30 m).
DISPLAY_SIMPLIFY = 0.0003


class RouteRequest(BaseModel):
    waypoints: list[tuple[float, float]]


class ExportRequest(BaseModel):
    waypoints: list[tuple[float, float]]
    name: str = "Postcodejager route"


def create_app(
    settings: Settings,
    store: Store,
    index_provider,
    strava_client: StravaClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Postcodejager")
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

    @app.get("/api/pc4")
    def pc4():
        collected = store.get_collected()
        return index_provider().to_feature_collection(
            collected, simplify_tolerance=DISPLAY_SIMPLIFY
        )

    @app.post("/api/route")
    def plan_route(req: RouteRequest):
        try:
            result = routing_mod.route(
                req.waypoints,
                base_url=settings.brouter_base_url,
                profile=settings.brouter_profile,
            )
        except Exception as exc:  # surface routing failures to the UI
            raise HTTPException(status_code=502, detail=f"Routeren mislukt: {exc}")
        collected = store.get_collected()
        new = routing_mod.new_postcodes(result.points, index_provider(), collected)
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
        }

    @app.post("/api/export")
    def export(req: ExportRequest):
        try:
            result = routing_mod.route(
                req.waypoints,
                base_url=settings.brouter_base_url,
                profile=settings.brouter_profile,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Routeren mislukt: {exc}")
        xml = build_gpx(result.points, req.name)
        return Response(
            content=xml,
            media_type="application/gpx+xml",
            headers={"Content-Disposition": 'attachment; filename="route.gpx"'},
        )

    return app
