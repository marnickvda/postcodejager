"""Build a neutral GPX track.

A plain ``<trk>`` works both for Komoot import and for direct sideload to a
Garmin/Wahoo bike computer.
"""
import gpxpy
import gpxpy.gpx


def build_gpx(points: list[tuple[float, float]], name: str) -> str:
    """Return GPX 1.1 XML for a single track through the ``(lat, lon)`` points."""
    gpx = gpxpy.gpx.GPX()
    gpx.version = "1.1"
    gpx.creator = "Postcodejager"

    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)
    for lat, lon in points:
        segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))
    return gpx.to_xml()
