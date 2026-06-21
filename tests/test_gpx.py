import xml.etree.ElementTree as ET

import pytest

from postcodejager.gpx import build_gpx, parse_gpx_points


def test_gpx_is_valid_xml_with_points():
    xml = build_gpx([(52.37, 4.90), (52.38, 4.91)], "Testrit")
    root = ET.fromstring(xml)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    pts = root.findall(".//g:trkpt", ns)
    assert len(pts) == 2
    assert float(pts[0].attrib["lat"]) == 52.37
    assert float(pts[0].attrib["lon"]) == 4.90
    assert root.find(".//g:trk/g:name", ns).text == "Testrit"


def test_parse_gpx_points_roundtrip():
    xml = build_gpx([(52.37, 4.90), (52.38, 4.91)], "Rit")
    assert parse_gpx_points(xml) == [(52.37, 4.90), (52.38, 4.91)]


def test_parse_gpx_rejects_doctype():
    with pytest.raises(ValueError):
        parse_gpx_points(
            '<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY x "y">]><gpx></gpx>'
        )
