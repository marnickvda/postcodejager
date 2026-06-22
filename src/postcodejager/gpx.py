"""Build a neutral GPX track.

A plain ``<trk>`` works both for Komoot import and for direct sideload to a
Garmin/Wahoo bike computer.
"""
import gpxpy
import gpxpy.gpx


def parse_gpx_points(xml: str) -> list[tuple[float, float]]:
    """Extract all track and route points from GPX as ``(lat, lon)`` tuples.

    Rejects ``DOCTYPE``/``ENTITY`` declarations up front to avoid XXE and
    billion-laughs attacks from untrusted uploads before handing off to gpxpy.
    """
    lowered = xml.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("GPX met DOCTYPE/ENTITY wordt geweigerd")
    gpx = gpxpy.parse(xml)
    points: list[tuple[float, float]] = []
    for track in gpx.tracks:
        for segment in track.segments:
            points.extend((p.latitude, p.longitude) for p in segment.points)
    for route in gpx.routes:
        points.extend((p.latitude, p.longitude) for p in route.points)
    return points


def build_gpx(
    points: list[tuple[float, float]], name: str, track_type: str | None = None
) -> str:
    """Return GPX 1.1 XML for a single track through the ``(lat, lon)`` points.

    ``track_type`` sets the optional ``<type>`` discipline hint (e.g. ``cycling``)
    that import apps like Strava/Komoot read to pre-select the sport. Left unset,
    the track stays neutral so it sideloads cleanly to any bike computer.
    """
    gpx = gpxpy.gpx.GPX()
    gpx.version = "1.1"
    gpx.creator = "Postcodejager"

    track = gpxpy.gpx.GPXTrack(name=name)
    if track_type:
        track.type = track_type
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)
    for lat, lon in points:
        segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))
    return gpx.to_xml()
