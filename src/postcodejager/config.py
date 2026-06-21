"""Application settings, loaded from environment with sensible defaults."""
import os
from dataclasses import dataclass

# CBS PC4 areas (CC BY 4.0), served as GeoJSON via the Opendatasoft Explore API.
DEFAULT_PC4_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-netherlands-postcode-pc4/exports/geojson"
)


@dataclass
class Settings:
    strava_client_id: str
    strava_client_secret: str
    strava_redirect_uri: str
    brouter_base_url: str
    brouter_profile: str
    data_dir: str
    pc4_path: str
    db_path: str
    pc4_url: str


def load_settings(env: dict | None = None) -> Settings:
    e = dict(os.environ)
    if env:
        e.update(env)

    data_dir = e.get("DATA_DIR", "data")
    return Settings(
        strava_client_id=e.get("STRAVA_CLIENT_ID", ""),
        strava_client_secret=e.get("STRAVA_CLIENT_SECRET", ""),
        strava_redirect_uri=e.get(
            "STRAVA_REDIRECT_URI", "http://localhost:8000/auth/callback"
        ),
        brouter_base_url=e.get("BROUTER_BASE_URL", "https://brouter.de/brouter"),
        brouter_profile=e.get("BROUTER_PROFILE", "trekking"),
        data_dir=data_dir,
        pc4_path=e.get("PC4_PATH", os.path.join(data_dir, "pc4.geojson")),
        db_path=e.get("DB_PATH", os.path.join(data_dir, "postcodejager.sqlite")),
        pc4_url=e.get("PC4_URL", DEFAULT_PC4_URL),
    )
