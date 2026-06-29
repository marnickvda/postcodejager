"""Application settings, loaded from environment with sensible defaults."""
import os
import pathlib
from dataclasses import dataclass

# PC4 postcode areas (CBS / Kadaster, CC BY 4.0) via the OpenDataSoft Explore API.
DEFAULT_PC4_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-netherlands-postcode-pc4/exports/geojson"
)


def apply_dotenv(path: str = ".env") -> None:
    """Load ``KEY=VALUE`` lines from a .env file into os.environ.

    Existing environment variables win (``setdefault``). Used by the run
    entrypoints; tests stay hermetic by not calling this.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Settings:
    strava_client_id: str
    strava_client_secret: str
    strava_redirect_uri: str
    brouter_base_url: str
    brouter_profile: str
    gpx_track_type: str
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
        # Discipline hint written to the GPX <type>; blank keeps it neutral.
        gpx_track_type=e.get("GPX_TRACK_TYPE", "cycling"),
        data_dir=data_dir,
        pc4_path=e.get("PC4_PATH", os.path.join(data_dir, "pc4.geojson")),
        db_path=e.get("DB_PATH", os.path.join(data_dir, "postcodejager.sqlite")),
        pc4_url=e.get("PC4_URL", DEFAULT_PC4_URL),
    )
