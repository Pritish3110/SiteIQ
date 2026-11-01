import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shapely.geometry import Polygon
from siteiq.boundary import (
    polygon_from_candidate, calculate_setback_envelope, candidate_edge_lengths,
    parse_uploaded_boundary, export_boundary_dxf,
)


def test_candidate_requires_confirmation_for_open_line():
    c = {"points": [(0,0),(20,0),(20,20)], "closed": False, "scale_to_m": 1.0}
    poly, status = polygon_from_candidate(c)
    assert poly is None
    assert status["status"] == "open_boundary"
    poly, status = polygon_from_candidate(c, close_open=True)
    assert poly is not None
    assert status["status"] == "valid"
    assert status["notes"]


def test_polygon_uses_scale_and_reports_area_and_perimeter():
    c = {"points": [(0,0),(40000,0),(40000,30000),(0,30000)], "closed": True, "scale_to_m": 0.001}
    poly, status = polygon_from_candidate(c)
    assert status["status"] == "valid"
    assert round(status["area_m2"], 3) == 1200.0
    assert round(status["perimeter_m"], 3) == 140.0


def test_invalid_self_intersection_not_silently_repaired():
    c = {"points": [(0,0),(10,10),(0,10),(10,0)], "closed": True, "scale_to_m": 1.0}
    poly, status = polygon_from_candidate(c)
    assert poly is None
    assert status["status"] == "invalid_geometry"


def test_uniform_5m_inset_for_rectangle():
    poly = Polygon([(0,0),(40,0),(40,50),(0,50)])
    result = calculate_setback_envelope(poly, {"all_round_m": 5.0})
    assert result["status"] == "calculated_preliminary"
    assert round(result["area_m2"], 3) == 1200.0
    assert result["geometry_type"] == "Polygon"


def test_variable_edge_setbacks_uses_front_rear_edges():
    poly = Polygon([(0,0),(33,0),(33,68),(0,68)])
    sb = {"front_m": 8.16, "rear_m": 5.44, "left_m": 2.64, "right_m": 2.64}
    result = calculate_setback_envelope(poly, sb, front_edges=[0], rear_edges=[2])
    expected = (33 - 2*2.64) * (68 - 8.16 - 5.44)
    assert result["status"] == "calculated_preliminary"
    assert abs(result["area_m2"] - expected) < 0.5


def test_variable_setbacks_require_front_edge_classification():
    poly = Polygon([(0,0),(33,0),(33,68),(0,68)])
    sb = {"front_m": 8.16, "rear_m": 5.44, "left_m": 2.64, "right_m": 2.64}
    result = calculate_setback_envelope(poly, sb)
    assert result["status"] == "frontage_classification_required"


def test_dxf_import_extracts_closed_polyline():
    import ezdxf
    from io import StringIO
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.modelspace().add_lwpolyline([(0,0),(40000,0),(40000,30000),(0,30000)], close=True, dxfattribs={"layer":"SITE"})
    buf = StringIO(); doc.write(buf)
    candidates, meta = parse_uploaded_boundary("site.dxf", buf.getvalue().encode("utf-8"))
    assert len(candidates) == 1
    assert candidates[0]["scale_to_m"] == 0.001
    poly, status = polygon_from_candidate(candidates[0])
    assert status["status"] == "valid"
    assert round(status["area_m2"]) == 1200


def test_dxf_export_roundtrips_layers():
    import ezdxf
    from io import StringIO
    poly = Polygon([(0,0),(10,0),(10,20),(0,20)])
    raw = export_boundary_dxf(poly, {})
    doc = ezdxf.read(StringIO(raw.decode("utf-8")))
    assert len(list(doc.modelspace().query('LWPOLYLINE[layer=="SITE_BOUNDARY"]'))) == 1
    assert int(doc.header["$INSUNITS"]) == 6


def test_kml_polygon_is_projected_to_metres():
    kml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
    77.5000,12.9000,0 77.5010,12.9000,0 77.5010,12.9010,0 77.5000,12.9010,0 77.5000,12.9000,0
    </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
    candidates, meta = parse_uploaded_boundary("test.kml", kml)
    assert len(candidates) == 1
    assert candidates[0]["source_units"].startswith("WGS84 projected")
    poly, status = polygon_from_candidate(candidates[0])
    assert status["status"] == "valid"
    assert 11_000 < status["area_m2"] < 13_000


def test_vector_pdf_rectangle_requires_manual_calibration():
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=500, height=400)
    page.draw_rect(fitz.Rect(50, 50, 350, 250), color=(0,0,0), width=1)
    data = doc.tobytes()
    doc.close()
    candidates, meta = parse_uploaded_boundary("vector.pdf", data)
    assert candidates
    candidate = candidates[0]
    assert candidate["source_type"] == "pdf"
    assert candidate["scale_to_m"] is None
    poly, status = polygon_from_candidate(candidate, scale_to_m=0.1)
    assert status["status"] == "valid"
    assert round(status["area_m2"]) == 600


def test_kml_polygon_preserves_wgs84_centroid_for_location_lookup():
    kml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Hoskote test</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
    77.7826482467,13.0744051246,0 77.7818835655,13.0744278830,0 77.7821781731,13.0719106518,0 77.7829740806,13.0728906855,0 77.7826482467,13.0744051246,0
    </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>'''
    candidates, _ = parse_uploaded_boundary("hoskote.kml", kml)
    assert len(candidates) == 1
    centroid = candidates[0]["source_centroid_wgs84"]
    assert abs(centroid[0] - 77.7823976) < 0.0001
    assert abs(centroid[1] - 13.0733543) < 0.0001
    assert candidates[0]["source_geometry_valid_wgs84"] is True


def test_open_kml_linestring_has_location_anchor_but_stays_open_for_area_validation():
    kml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Hoskote open perimeter</name><LineString><coordinates>
    77.7820,13.0730,0 77.7830,13.0730,0 77.7830,13.0740,0 77.7825,13.0745,0
    </coordinates></LineString></Placemark></Document></kml>'''
    candidates, _ = parse_uploaded_boundary("hoskote_open.kml", kml)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["closed"] is False
    assert candidate["source_location_point_wgs84"] is not None
    assert candidate["source_centroid_wgs84"] is None
    poly, validation = polygon_from_candidate(candidate, close_open=False)
    assert poly is None
