"""Strava OAuth and activity fetching.

Only the authenticated athlete's own data is used (scope ``activity:read_all``),
in line with Strava's API agreement for personal tools.
"""
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import httpx

from .geo import decode_polyline

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
DEFAULT_SCOPE = "activity:read_all"


def build_authorize_url(
    client_id: str, redirect_uri: str, scope: str = DEFAULT_SCOPE
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": scope,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


@dataclass
class Activity:
    id: int
    name: str
    start_epoch: int
    polyline: str


def _parse_epoch(start_date: str) -> int:
    cleaned = start_date.replace("Z", "+00:00")
    return int(datetime.fromisoformat(cleaned).timestamp())


def parse_activity(obj: dict) -> Activity:
    return Activity(
        id=int(obj["id"]),
        name=obj.get("name", ""),
        start_epoch=_parse_epoch(obj["start_date"]),
        polyline=(obj.get("map") or {}).get("summary_polyline") or "",
    )


class StravaClient:
    def __init__(self, client_id: str, client_secret: str, http=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = http or httpx.Client(timeout=60)

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        resp = self._http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def refresh(self, refresh_token: str) -> dict:
        resp = self._http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_activities(
        self, access_token: str, after: int | None = None
    ) -> list[Activity]:
        headers = {"Authorization": f"Bearer {access_token}"}
        out: list[Activity] = []
        page = 1
        while True:
            params: dict = {"per_page": 200, "page": page}
            if after is not None:
                params["after"] = after
            resp = self._http.get(ACTIVITIES_URL, params=params, headers=headers)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for obj in batch:
                activity = parse_activity(obj)
                if activity.polyline:
                    out.append(activity)
            page += 1
        return out

    def tracks_for(
        self, activities: list[Activity]
    ) -> list[list[tuple[float, float]]]:
        return [decode_polyline(a.polyline) for a in activities]
