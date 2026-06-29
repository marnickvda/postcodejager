"""Extract a Netherlands-only Protomaps basemap into the local data directory.

Usage: python scripts/fetch_basemap.py [PLANET_URL]

PLANET_URL is a Protomaps planet build, e.g. one listed at
https://maps.protomaps.com/builds (or set BASEMAP_PLANET_URL). Only the bytes
for the Netherlands bounding box are downloaded, not the whole planet.
Requires the `pmtiles` CLI (go-pmtiles) on PATH.
"""
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from postcodejager.config import apply_dotenv, load_settings  # noqa: E402

NL_BBOX = "3.0,50.7,7.3,53.7"  # min_lon,min_lat,max_lon,max_lat
MAXZOOM = 15


def build_extract_cmd(
    planet_url: str, out_path: str, bbox: str = NL_BBOX, maxzoom: int = MAXZOOM
) -> list[str]:
    """The `pmtiles extract` argv that cuts the NL region out of a planet build."""
    return [
        "pmtiles",
        "extract",
        planet_url,
        out_path,
        f"--bbox={bbox}",
        f"--maxzoom={maxzoom}",
    ]


def main() -> None:
    apply_dotenv()
    settings = load_settings()
    planet_url = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASEMAP_PLANET_URL", "")
    )
    if not planet_url:
        sys.exit(
            "Set a planet build URL: python scripts/fetch_basemap.py <URL>\n"
            "Pick the latest from https://maps.protomaps.com/builds "
            "(or set BASEMAP_PLANET_URL)."
        )
    if shutil.which("pmtiles") is None:
        sys.exit(
            "The `pmtiles` CLI is not on PATH. Install go-pmtiles: "
            "https://github.com/protomaps/go-pmtiles/releases"
        )
    os.makedirs(settings.data_dir, exist_ok=True)
    out_path = os.path.join(settings.data_dir, "nl.pmtiles")
    cmd = build_extract_cmd(planet_url, out_path)
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"Saved {out_path} ({size_mb:.0f} MB).")


if __name__ == "__main__":
    main()
