"""HTTP contract tests for the local API."""
import json

import pytest
from fastapi.testclient import TestClient

from siteiq import __version__, location
from siteiq.api import app

client = TestClient(app)
KML = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>Plot</name><Polygon><outerBoundaryIs><LinearRing><coordinates>77.78,13.07 77.781,13.07 77.781,13.071 77.78,13.071 77.78,13.07</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'


def body(**overrides):
    base = {"project_name": "API test", "authority_key": "bengaluru_rmp2015", "land_use_category": "Residential (Main)", "proposed_use": "Residential apartments", "site_area_m2": 2200.0, "road_width_m": 18.5, "scenarios": [{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 1000}]}
    base.update(overrides)
    return base


def boundary():
    parsed = client.post("/api/boundary/parse", files={"file": ("plot.kml", KML)}).json()
    candidate = parsed["candidates"][0]
    valid = client.post("/api/boundary/validate", json={"candidate": candidate}).json()
    v = valid["validation"]
    return {"source_file": "plot.kml", "source_type": "kml", "points_m": valid["points_m"], "holes_m": valid["holes_m"], "area_m2": v["area_m2"], "perimeter_m": v["perimeter_m"], "vertex_count": v["vertex_count"], "is_convex": v["is_convex"], "front_edges": [0], "rear_edges": [2], "source_points_wgs84": candidate["source_points_wgs84"]}


def test_meta_lists_authorities_without_a_default():
    data = client.get("/api/meta").json()
    assert data["version"] == __version__
    assert len(data["authorities"]) == 25
    assert sum(a["has_rules"] for a in data["authorities"]) == 5


def test_other_websites_cannot_call_the_api():
    assert client.post("/api/admin/layers/authority", files={"file": ("x.geojson", b"{}")}, headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/meta", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/meta", headers={"origin": "http://localhost:5173"}).status_code == 200


def test_authority_detail():
    assert client.get("/api/authorities/hoskote_planning_authority").json()["source_status"] == "official_source_found_pending_review"
    assert client.get("/api/authorities/nope").status_code == 404


def test_bad_inputs_are_rejected():
    assert client.post("/api/assess", json=body(site_area_m2=-1)).status_code == 422
    assert client.post("/api/assess", json=body(unknown_field=1)).status_code == 422
    assert client.post("/api/assess", json=body(statutory_deduction_pct=80)).status_code == 422
    assert client.post("/api/assess", json=body(authority_key="nope")).status_code == 422
    assert client.post("/api/assess", content='{"site_area_m2": NaN}', headers={"content-type": "application/json"}).status_code == 422


def test_failed_location_lookup_returns_an_error_not_a_stale_result(monkeypatch):
    monkeypatch.setattr(location, "coordinates_from_map_url", lambda url, resolve_short_link=True: {"coordinates": None, "warning": "failed"})
    response = client.post("/api/location/identify", json={"map_url": "https://maps.app.goo.gl/x", "coordinates": "13.0, 77.5"})
    assert response.status_code == 422 and "could not be resolved" in response.json()["detail"]


def test_boundary_point_overrides_typed_inputs(monkeypatch):
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {"display_name": "x", "address": {"state": "Karnataka"}, "source": "test"})
    data = client.post("/api/location/identify", json={"map_url": "https://maps.app.goo.gl/x", "boundary_point_lonlat": [77.78, 13.07]}).json()
    assert data["location_source"] == "Imported boundary"
    assert data["coordinates"]["latitude"] == pytest.approx(13.07)


def test_upload_errors_are_clear():
    assert client.post("/api/boundary/parse", files={"file": ("plot.dwg", b"x")}).status_code == 422
    assert client.post("/api/boundary/parse", files={"file": ("plot.kml", b"<not xml")}).status_code == 422


def test_full_flow_with_boundary_and_every_export():
    payload = body(boundary=boundary(), scenarios=[{"name": "A", "height_m": 15, "floors": 5, "basement_levels": 1}, {"name": "B", "height_m": 18, "floors": 6, "footprint_m2": 500}])
    report = client.post("/api/assess", json=payload).json()
    assert report["boundary_analysis"]["options"][0]["envelope"]["status"] == "calculated_preliminary"
    assert report["verdict"]["total"] > 20
    for kind, magic in {"report-pdf": b"%PDF", "board-pdf": b"%PDF", "report-pptx": b"PK", "board-pptx": b"PK"}.items():
        response = client.post(f"/api/export/{kind}", json=payload)
        assert response.status_code == 200 and response.content.startswith(magic)
        assert response.headers["x-siteiq-fingerprint"] == report["input_fingerprint"]
    assessed = json.loads(client.post("/api/export/assessment-json", json=payload).content)
    assert assessed["maximum_far"] == report["maximum_far"]
    assert b"SITE_BOUNDARY" in client.post("/api/export/envelopes-dxf", json=payload).content


def test_dxf_export_needs_a_boundary():
    assert client.post("/api/export/envelopes-dxf", json=body()).status_code == 422


def test_export_values_match_the_assessment():
    import fitz
    payload = body()
    report = client.post("/api/assess", json=payload).json()
    pdf = fitz.open(stream=client.post("/api/export/report-pdf", json=payload).content, filetype="pdf")
    text = " ".join(page.get_text() for page in pdf)
    assert f"{report['maximum_far_area_m2']:,.0f}" in text
    assert "COMPLIANCE REGISTER" in text
