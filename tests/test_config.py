from postcodejager.config import load_settings


def test_defaults_and_overrides():
    s = load_settings({"STRAVA_CLIENT_ID": "42"})
    assert s.strava_client_id == "42"
    assert s.brouter_base_url.startswith("https://brouter")
    assert s.strava_redirect_uri.endswith("/auth/callback")
    assert s.pc4_url.startswith("http")
    assert s.pc4_path.endswith("pc4.geojson")
    assert s.db_path.endswith(".sqlite")


def test_gpx_track_type_default_and_override():
    assert load_settings({}).gpx_track_type == "cycling"  # tagged out of the box
    assert load_settings({"GPX_TRACK_TYPE": "Road cycling"}).gpx_track_type == "Road cycling"
    assert load_settings({"GPX_TRACK_TYPE": ""}).gpx_track_type == ""  # blank = neutral
