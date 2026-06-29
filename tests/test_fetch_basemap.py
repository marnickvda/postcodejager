import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.fetch_basemap import build_extract_cmd


def test_build_extract_cmd_has_bbox_maxzoom_and_io():
    cmd = build_extract_cmd(
        "https://maps.protomaps.com/builds/20260628.pmtiles", "data/nl.pmtiles"
    )
    assert cmd[:2] == ["pmtiles", "extract"]
    assert "https://maps.protomaps.com/builds/20260628.pmtiles" in cmd
    assert "data/nl.pmtiles" in cmd
    assert "--bbox=3.0,50.7,7.3,53.7" in cmd
    assert "--maxzoom=15" in cmd
