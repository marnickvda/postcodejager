"""Download CBS PC4 boundary GeoJSON into the local data directory.

Usage: python scripts/fetch_pc4.py
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from postcodejager.config import apply_dotenv, load_settings  # noqa: E402
from postcodejager.postcodes import download_pc4_geojson, load_pc4  # noqa: E402


def main() -> None:
    apply_dotenv()
    settings = load_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    print(f"Downloading PC4 GeoJSON from:\n  {settings.pc4_url}")
    download_pc4_geojson(settings.pc4_path, settings.pc4_url)
    index = load_pc4(settings.pc4_path)
    print(f"Saved {settings.pc4_path} with {len(index.codes())} PC4 areas.")


if __name__ == "__main__":
    main()
