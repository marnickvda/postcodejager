import httpx
import respx

from postcodejager.strava import StravaClient, build_authorize_url, parse_activity


def test_authorize_url_contains_scope_and_client():
    url = build_authorize_url("123", "http://localhost:8000/auth/callback")
    assert "client_id=123" in url
    assert "activity%3Aread_all" in url or "activity:read_all" in url


def test_parse_activity_reads_summary_polyline():
    a = parse_activity(
        {
            "id": 5,
            "name": "Rit",
            "start_date": "2026-06-20T08:00:00Z",
            "map": {"summary_polyline": "_p~iF~ps|U"},
        }
    )
    assert a.id == 5
    assert a.name == "Rit"
    assert a.polyline == "_p~iF~ps|U"
    assert a.start_epoch > 0


@respx.mock
def test_exchange_code_returns_token():
    respx.post("https://www.strava.com/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "AT", "refresh_token": "RT", "expires_at": 999}
        )
    )
    c = StravaClient("id", "secret")
    tok = c.exchange_code("code", "http://localhost:8000/auth/callback")
    assert tok["access_token"] == "AT"


@respx.mock
def test_fetch_activities_filters_empty_polyline_and_paginates():
    page1 = [
        {
            "id": 1,
            "name": "a",
            "start_date": "2026-06-20T08:00:00Z",
            "map": {"summary_polyline": "_p~iF~ps|U"},
        },
        {
            "id": 2,
            "name": "b",
            "start_date": "2026-06-20T09:00:00Z",
            "map": {"summary_polyline": ""},
        },
    ]
    respx.get("https://www.strava.com/api/v3/athlete/activities").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=[]),
        ]
    )
    c = StravaClient("id", "secret")
    acts = c.fetch_activities("AT")
    assert [a.id for a in acts] == [1]


def test_tracks_for_decodes_polylines():
    c = StravaClient("id", "secret")
    a = parse_activity(
        {"id": 1, "name": "x", "start_date": "2026-06-20T08:00:00Z",
         "map": {"summary_polyline": "_p~iF~ps|U"}}
    )
    tracks = c.tracks_for([a])
    assert tracks == [[(38.5, -120.2)]]
