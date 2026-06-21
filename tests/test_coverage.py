import json
import pathlib

from postcodejager.coverage import collected_from_tracks
from postcodejager.postcodes import PC4Index

FIX = pathlib.Path(__file__).parent / "fixtures" / "pc4_sample.geojson"


def idx():
    return PC4Index.from_geojson(json.loads(FIX.read_text()))


def test_track_crossing_both_squares_collects_both():
    # Sparse endpoints across both squares; densify must fill the gap.
    track = [(52.37, 4.905), (52.37, 4.935)]
    assert collected_from_tracks([track], idx()) == {"1011", "1012"}


def test_track_outside_collects_nothing():
    assert collected_from_tracks([[(0.0, 0.0), (0.1, 0.1)]], idx()) == set()
