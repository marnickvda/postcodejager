import xml.etree.ElementTree as ET

from postcodejager.gpx import build_gpx


def test_gpx_is_valid_xml_with_points():
    xml = build_gpx([(52.37, 4.90), (52.38, 4.91)], "Testrit")
    root = ET.fromstring(xml)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    pts = root.findall(".//g:trkpt", ns)
    assert len(pts) == 2
    assert float(pts[0].attrib["lat"]) == 52.37
    assert float(pts[0].attrib["lon"]) == 4.90
    assert root.find(".//g:trk/g:name", ns).text == "Testrit"
