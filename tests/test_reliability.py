"""Regression tests for the reliability gaps found in the v0.5.0 audit (IDs C1-C9, H1-H11)."""
import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, shape

from siteiq import __version__, location
from siteiq.boundary import calculate_setback_envelope, parse_kml, polygon_from_candidate
from siteiq.checks import summarise
from siteiq.engine import build_report, calculate_setbacks, load_authority_registry, load_rule_profile, match_far_rule
from siteiq.service import assess, input_fingerprint, nominal_dimensions

RMP = "bengaluru_rmp2015_partial"
L_SHAPE = Polygon([(0, 0), (100, 0), (100, 30), (35, 30), (35, 80), (0, 80)])
DUMBBELL = Polygon([(0, 0), (40, 0), (40, 18), (60, 18), (60, 0), (100, 0), (100, 40), (60, 40), (60, 22), (40, 22), (40, 40), (0, 40)])


def payload(**overrides):
    base = {
        "project_name": "Test", "authority_key": "bengaluru_rmp2015", "land_use_category": "Residential (Main)",
        "proposed_use": "Residential apartments", "site_area_m2": 2200.0, "road_width_m": 18.5,
        "scenarios": [{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 1000}],
    }
    base.update(overrides)
    return base


def check(report, check_id, option=None):
    return next(c for c in report["compliance_checks"] if c["id"] == check_id and (option is None or c["option"] == option))


# C3: rule status gate
@pytest.mark.parametrize("status", ["draft_only", "superseded", "withdrawn_or_stayed", "not_configured", None])
def test_non_calculating_status_never_returns_far(status):
    profile = copy.deepcopy(load_rule_profile(RMP))
    profile["source_status"] = status
    result = match_far_rule(profile, "Residential (Main)", 2200, 18)
    assert result["status"] == "rule_status_blocked"
    assert result["maximum_far"] is None


def test_expired_profile_never_returns_far():
    profile = copy.deepcopy(load_rule_profile(RMP))
    profile["effective_to"] = "2020-01-01"
    assert match_far_rule(profile, "Residential (Main)", 2200, 18)["status"] == "rule_status_blocked"


def test_no_shipped_profile_claims_verified_status():
    registry = load_authority_registry()
    for authority in registry["authorities"]:
        if authority.get("rule_profile"):
            assert load_rule_profile(authority["rule_profile"])["source_status"] != "verified_operative"


# C4: locality text
@pytest.mark.parametrize("address,expected", [
    ({"suburb": "Kanakapura Road", "city": "Bengaluru", "state": "Karnataka"}, "bengaluru_rmp2015"),
    ({"suburb": "Magadi Road", "city": "Bengaluru", "state": "Karnataka"}, "bengaluru_rmp2015"),
    ({"village": "Vijayapura", "state_district": "Bengaluru Rural", "state": "Karnataka"}, "other_karnataka"),
    ({"county": "Hoskote taluk", "state_district": "Bengaluru Rural", "state": "Karnataka"}, "hoskote_planning_authority"),
])
def test_locality_candidates(address, expected):
    assert location._locality_candidate({"address": address})["key"] == expected


# C5: deductions
def test_typed_reduction_is_labelled_an_assumption_and_rule_reduction_is_not():
    hoskote = load_rule_profile("hoskote_lpa2031_candidate")
    rule = match_far_rule(hoskote, "Residential", 12000, 18, proposed_use="Residential apartments")
    assert rule["far_calculation_area_m2"] == 11400
    assert rule["matched_rule"]["details"]["deduction_source"] == "configured_rule"
    typed = match_far_rule(hoskote, "Residential", 12000, 18, proposed_use="Residential apartments", statutory_deduction_pct=20)
    assert typed["matched_rule"]["details"]["deduction_source"] == "user_assumption"


def test_reduction_out_of_range_is_refused():
    assert match_far_rule(load_rule_profile(RMP), "Residential (Main)", 300, 9, statutory_deduction_pct=80)["status"] == "invalid_input"


def test_gross_area_on_large_site_is_flagged():
    report = assess(payload(site_area_m2=5000.0))
    assert check(report, "far.deduction")["status"] == "REFER"


# C6: thresholds and area accuracy
def test_near_threshold_area_is_flagged():
    report = assess(payload(site_area_m2=4000.0, road_width_m=40.0, scenarios=[{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 1000}]))
    flag = check(report, "rule.sensitivity.area")
    assert flag["status"] == "REFER" and "3.25" in flag["message"]


def test_clear_of_threshold_is_not_flagged():
    report = assess(payload(site_area_m2=3000.0, road_width_m=27.0))
    assert not [c for c in report["compliance_checks"] if c["id"].startswith("rule.sensitivity")]


@pytest.mark.parametrize("lon", [75.0, 77.9, 78.4])
def test_kml_area_is_within_a_hundredth_percent_of_geodesic(lon):
    from pyproj import Geod
    ring = [(lon, 13.0), (lon + 0.001, 13.0), (lon + 0.001, 13.001), (lon, 13.001)]
    text = " ".join(f"{x},{y},0" for x, y in ring + ring[:1])
    kml = f'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>{text}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'.encode()
    candidates, _ = parse_kml(kml)
    area = polygon_from_candidate(candidates[0])[0].area
    geodesic = abs(Geod(ellps="WGS84").polygon_area_perimeter(*zip(*ring))[0])
    assert abs(area - geodesic) / geodesic < 1e-4


# C7: cross-checks
def test_implausible_floors_and_excess_coverage_fail():
    report = assess(payload(site_area_m2=5000.0, road_width_m=18.0, scenarios=[{"name": "A", "height_m": 9, "floors": 40, "footprint_m2": 4999}]))
    assert check(report, "option.inputs", "A")["status"] == "FAIL"
    assert check(report, "option.coverage", "A")["status"] == "FAIL"
    assert check(report, "option.far", "A")["status"] == "FAIL"
    assert report["verdict"]["code"] == "BLOCKED"


def test_auto_footprint_respects_coverage_limit():
    square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    boundary = {"points_m": [list(p) for p in list(square.exterior.coords)[:-1]], "holes_m": [], "area_m2": square.area, "perimeter_m": square.length, "vertex_count": 4, "is_convex": True, "use_computed_area": True, "front_edges": [0], "rear_edges": [2]}
    report = assess(payload(site_area_m2=square.area, road_width_m=31.0, land_use_category="Commercial (Business)", boundary=boundary, scenarios=[{"name": "A", "height_m": 15, "floors": 5}]))
    option = report["scenarios"][0]
    assert option["footprint_source"] == "coverage limit"


def test_derived_footprint_over_capacity_states_the_limit_instead_of_failing():
    square = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    boundary = {"points_m": [list(p) for p in list(square.exterior.coords)[:-1]], "holes_m": [], "area_m2": square.area, "perimeter_m": square.length, "vertex_count": 4, "is_convex": True, "use_computed_area": True, "front_edges": [0], "rear_edges": [2]}
    report = assess(payload(site_area_m2=square.area, road_width_m=31.0, land_use_category="Commercial (Business)", proposed_use="Commercial / office", boundary=boundary, scenarios=[{"name": "A", "height_m": 30, "floors": 10}]))
    result = check(report, "option.far", "A")
    assert result["status"] == "REFER" and "per floor fits" in result["message"]


# C8: holes
def test_kml_holes_reduce_area():
    kml = b"""<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>77.78,13.07 77.782,13.07 77.782,13.072 77.78,13.072 77.78,13.07</coordinates></LinearRing></outerBoundaryIs><innerBoundaryIs><LinearRing><coordinates>77.7805,13.0705 77.7815,13.0705 77.7815,13.0715 77.7805,13.0715 77.7805,13.0705</coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark></kml>"""
    candidates, meta = parse_kml(kml)
    poly, validation = polygon_from_candidate(candidates[0])
    outer = Polygon(poly.exterior).area
    assert poly.area == pytest.approx(outer * 0.75, rel=0.001)
    assert validation["hole_count"] == 1 and meta["inner_rings"] == 1


# C9: fire is statewide and carries no unsourced dimensions
def test_fire_trigger_applies_in_lpa_profiles():
    report = build_report({"project_name": "x", "authority_key": "hoskote_planning_authority", "land_use_category": "Residential", "site_area_m2": 3000.0, "road_width_m": 18.0, "scenarios": [{"name": "A", "height_m": 30, "floors": 10, "footprint_m2": 500}]})
    assert report["fire"]["fire_noc_required"] is True
    assert "minimum_fire_driveway_width_m" not in report["fire"]


@pytest.mark.parametrize("height,expected", [(14.9, "below_configured_high_rise_threshold"), (15, "nbc_band_requires_confirmation"), (20.9, "nbc_band_requires_confirmation"), (21, "triggered_by_height_scenario")])
def test_fire_bands(height, expected):
    report = build_report({"project_name": "x", "authority_key": "bengaluru_rmp2015", "land_use_category": "Residential (Main)", "site_area_m2": 3000.0, "road_width_m": 18.0, "scenarios": [{"name": "A", "height_m": height, "floors": 3, "footprint_m2": 500}]})
    assert report["fire"]["status"] == expected


# H2 and H11
def test_dimensions_come_from_the_tagged_road_edge():
    rotated = Polygon([(0, 0), (30, 40), (-40, 92.5), (-70, 52.5)])
    width, depth = nominal_dimensions(rotated, [0])
    assert width == pytest.approx(50, abs=0.01)
    assert depth == pytest.approx(87.5, abs=0.01)


def test_table8_height_excludes_the_stilt_when_its_height_is_known():
    profile = load_rule_profile(RMP)
    known = calculate_setbacks(profile, 2000, 40, 50, 13.5, True, zone="Residential (Main)", stilt_height_m=2.4)
    assert known["front_m"] == pytest.approx(6.0) and known["all_round_m"] is None


def test_small_plot_up_to_15m_uses_table8():
    result = calculate_setbacks(load_rule_profile(RMP), 240, 12, 20, 15, True, zone="Residential (Main)")
    assert result["front_m"] == pytest.approx(1.0) and result["rear_m"] == pytest.approx(0.8)


# H3
def test_narrow_neck_is_found_inside_a_large_envelope():
    result = calculate_setback_envelope(DUMBBELL, {"all_round_m": 1.0})
    assert result["has_narrow_neck"] is True and result["warnings"]


def test_wide_rectangle_has_no_narrow_neck():
    assert calculate_setback_envelope(Polygon([(0, 0), (50, 0), (50, 40), (0, 40)]), {"all_round_m": 3.0})["has_narrow_neck"] is False


# H4 and edge indexing
@pytest.mark.parametrize("poly", [L_SHAPE, Polygon(list(L_SHAPE.exterior.coords)[::-1]), DUMBBELL, Polygon([(0, 0), (50, 0), (60, 30), (10, 40)])])
@pytest.mark.parametrize("d", [1.0, 3.0, 5.0])
def test_equal_edge_setbacks_match_a_mitred_inward_buffer(poly, d):
    result = calculate_setback_envelope(poly, {"front_m": d, "rear_m": d, "left_m": d, "right_m": d}, front_edges=[0])
    assert shape(result["geometry"]).symmetric_difference(poly.buffer(-d, join_style="mitre")).area < 0.01


def test_strip_stays_on_its_own_edge_on_a_concave_plot():
    result = calculate_setback_envelope(L_SHAPE, {"front_m": 10.0, "rear_m": 3.0, "left_m": 3.0, "right_m": 3.0}, front_edges=[2])
    # The 10 m strip belongs to the re-entrant edge; it must not reach the far end of the long leg's line.
    assert result["area_m2"] == pytest.approx(3251.0, abs=1.0)


def test_front_edge_identity_survives_clockwise_rings():
    rect = [(0, 0), (40, 0), (40, 30), (0, 30)]
    ccw = calculate_setback_envelope(Polygon(rect), {"front_m": 8.0, "rear_m": 2.0, "left_m": 2.0, "right_m": 2.0}, front_edges=[0])
    cw_ring = rect[::-1]  # Edge 0 of this ring is the x=0 side.
    cw = calculate_setback_envelope(Polygon(cw_ring), {"front_m": 8.0, "rear_m": 2.0, "left_m": 2.0, "right_m": 2.0}, front_edges=[0])
    assert shape(ccw["geometry"]).bounds == pytest.approx((2, 8, 38, 28))
    assert shape(cw["geometry"]).bounds == pytest.approx((2, 2, 38, 28)) or shape(cw["geometry"]).bounds[2] < 40


def test_no_build_depth_is_removed_along_the_named_edge():
    square = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
    result = calculate_setback_envelope(square, {"all_round_m": 2.0}, edge_extra_m={0: 10.0})
    assert shape(result["geometry"]).bounds == pytest.approx((2, 12, 38, 38))


# H5
def test_closed_linestring_is_closed():
    kml = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString><coordinates>77.78,13.07 77.781,13.07 77.781,13.071 77.78,13.071 77.78,13.07</coordinates></LineString></Placemark></kml>'
    candidate = parse_kml(kml)[0][0]
    assert candidate["closed"] is True
    assert polygon_from_candidate(candidate)[1]["status"] == "valid"


def test_kml_21_namespace_and_placemark_names_are_read():
    kml = b'<kml xmlns="http://earth.google.com/kml/2.1"><Placemark><name>Plot 7</name><Polygon><outerBoundaryIs><LinearRing><coordinates>77.78,13.07 77.781,13.07 77.781,13.071 77.78,13.07</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'
    candidates = parse_kml(kml)[0]
    assert len(candidates) == 1 and "Plot 7" in candidates[0]["label"]


def test_entity_declarations_are_refused():
    with pytest.raises(ValueError):
        parse_kml(b'<!DOCTYPE kml [<!ENTITY a "b">]><kml/>')


def test_concave_kml_lookup_point_is_inside_the_parcel():
    text = "77.78,13.07 77.79,13.07 77.79,13.071 77.781,13.071 77.781,13.08 77.78,13.08 77.78,13.07"
    kml = f'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>{text}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>'.encode()
    candidate = parse_kml(kml)[0][0]
    from shapely.geometry import Point
    assert Polygon(candidate["source_points_wgs84"]).contains(Point(candidate["source_location_point_wgs84"]))


# H6
@pytest.mark.parametrize("text", ["Plot 12 34 Cross Road", "12", "abc", "95, 181"])
def test_text_that_is_not_a_coordinate_is_rejected(text):
    assert location.parse_coordinate_text(text) is None


def test_dms_coordinates_are_parsed():
    lat, lon = location.parse_coordinate_text("13°19'47\"N 77°06'44\"E")
    assert lat == pytest.approx(13.3297, abs=0.001) and lon == pytest.approx(77.1122, abs=0.001)


def test_swapped_and_out_of_state_coordinates_stop_the_lookup(tmp_path):
    with pytest.raises(RuntimeError, match="swapped"):
        location.auto_identify_site(coordinates_text="77.5946, 12.9716", authority_layer=tmp_path / "a", zone_layer=tmp_path / "z")
    with pytest.raises(RuntimeError, match="outside Karnataka"):
        location.auto_identify_site(coordinates_text="28.6139, 77.2090", authority_layer=tmp_path / "a", zone_layer=tmp_path / "z")


# H7
class FakeResponse:
    def __init__(self, status, headers=None, body=b"", url=""):
        self.status_code, self.headers, self._body, self.url, self.encoding = status, headers or {}, body, url, "utf-8"

    def iter_content(self, _):
        yield self._body

    def close(self):
        pass


def test_redirect_off_the_allowlist_is_not_followed(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        return FakeResponse(302, {"Location": "https://evil.example/landing"})
    monkeypatch.setattr(location.requests, "get", fake_get)
    result = location.coordinates_from_map_url("https://maps.app.goo.gl/abc")
    assert result["coordinates"] is None and "PermissionError" in result["warning"]
    assert calls == ["https://maps.app.goo.gl/abc"]


def test_numbers_in_page_scripts_are_not_treated_as_the_site(monkeypatch):
    monkeypatch.setattr(location.requests, "get", lambda url, **k: FakeResponse(200, body=b"<html><script>[12.9715987, 77.5945627]</script></html>"))
    assert location.coordinates_from_map_url("https://maps.app.goo.gl/abc")["coordinates"] is None


def test_redirect_to_pin_resolves_without_fetching_the_page(monkeypatch):
    target = "https://www.google.com/maps/place/x/@13.3,77.1,800m/data=!3m2!4m4!3m3!8m2!3d13.3296889!4d77.11215"
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(302, {"Location": target})
    monkeypatch.setattr(location.requests, "get", fake_get)
    result = location.coordinates_from_map_url("https://maps.app.goo.gl/abc")
    assert result["coordinates"] == (13.3296889, 77.11215) and result["precision"] == "pin"
    assert len(calls) == 1


def test_viewport_only_link_warns():
    result = location.coordinates_from_map_url("https://www.google.com/maps/@13.3,77.1,15z")
    assert result["precision"] == "viewport" and "not a dropped pin" in result["warning"]


# H9
def test_auto_footprint_far_ratio_uses_the_same_denominator_as_the_engine():
    square = Polygon([(0, 0), (120, 0), (120, 100), (0, 100)])
    boundary = {"points_m": [list(p) for p in list(square.exterior.coords)[:-1]], "holes_m": [], "area_m2": square.area, "perimeter_m": square.length, "vertex_count": 4, "is_convex": True, "use_computed_area": True, "front_edges": [0], "rear_edges": [2]}
    report = assess({"project_name": "x", "authority_key": "hoskote_planning_authority", "land_use_category": "Residential", "proposed_use": "Residential apartments", "site_area_m2": square.area, "road_width_m": 18.0, "boundary": boundary, "scenarios": [{"name": "A", "height_m": 15, "floors": 5}]})
    option = report["scenarios"][0]
    assert report["far"]["far_calculation_area_m2"] == pytest.approx(11400)
    assert option["achieved_far_ratio"] == pytest.approx(option["gross_concept_area_m2"] / 11400, abs=0.001)


# H10
def _write_layer(tmp_path, features):
    path = tmp_path / "authority.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def _authority(key, ring):
    return {"type": "Feature", "properties": {"authority_key": key}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def test_parcel_straddling_two_authorities_is_detected(tmp_path):
    layer = _write_layer(tmp_path, [_authority("a", [[77, 13], [77.5, 13], [77.5, 13.5], [77, 13.5], [77, 13]]), _authority("b", [[77.5, 13], [78, 13], [78, 13.5], [77.5, 13.5], [77.5, 13]])])
    parcel = [[77.499, 13.2], [77.501, 13.2], [77.501, 13.202], [77.499, 13.202]]
    result = location.parcel_jurisdiction_diagnostics(parcel, authority_layer=layer)
    assert result["status"] == "straddles_authorities"
    assert {r["authority_key"] for r in result["authorities"]} == {"a", "b"}


def test_invalid_authority_polygon_still_matches_on_a_working_copy(tmp_path):
    bowtie = [[77, 13], [78, 14], [78, 13], [77, 14], [77, 13]]
    layer = _write_layer(tmp_path, [_authority("a", bowtie)])
    result = location._point_matches(layer, 13.5, 77.9, "authority")
    assert result["status"] == "matched_polygon_layer" and result["invalid_features_repaired"] == 1


# Regulations read from the primary documents
@pytest.mark.parametrize("road,height,expected", [(8.0, 16, "FAIL"), (8.0, 15, "PASS")])
def test_road_below_9m_limits_height(road, height, expected):
    report = assess(payload(road_width_m=road, scenarios=[{"name": "A", "height_m": height, "floors": 5, "footprint_m2": 100}]))
    assert check(report, "option.height.road_below_9m", "A")["status"] == expected


@pytest.mark.parametrize("area,ring,units,expected", [
    (300, "III", 6, "PASS"), (300, "III", 7, "FAIL"), (500, "III", 9, "FAIL"), (500, "III", 8, "PASS"), (500, "I", 40, "PASS"), (150, "I", 2, "FAIL"),
])
def test_apartment_rules_follow_the_2026_amendment(area, ring, units, expected):
    report = assess(payload(site_area_m2=float(area), road_width_m=12.0, rmp_ring=ring, dwelling_units=units))
    assert check(report, "option.apartment", "A")["status"] == expected


def test_apartment_needs_a_9m_road():
    report = assess(payload(road_width_m=8.0, rmp_ring="I"))
    assert check(report, "option.apartment", "A")["status"] == "FAIL"


@pytest.mark.parametrize("drain,required", [("primary", 15.0), ("secondary", 10.0), ("tertiary", 5.0)])
def test_drain_buffers_follow_udd_468(drain, required):
    overlays = {"drain": {"status": "present", "drain_class": drain, "edge": 0, "extra_setback_m": required - 1}}
    assert check(assess(payload(overlays=overlays)), "overlay.drain")["status"] == "FAIL"
    overlays["drain"]["extra_setback_m"] = required
    assert check(assess(payload(overlays=overlays)), "overlay.drain")["status"] == "REFER"


def test_drain_buffer_not_assumed_outside_bengaluru_region():
    report = assess(payload(authority_key="mysuru_development_authority", overlays={"drain": {"status": "present", "drain_class": "primary", "edge": 0, "extra_setback_m": 1}}))
    assert check(report, "overlay.drain")["status"] == "NOT_CONFIGURED"


def test_basement_rules():
    report = assess(payload(scenarios=[{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 500, "basement_levels": 6}]))
    assert check(report, "option.basement", "A")["status"] == "FAIL"
    report = assess(payload(overlays={"flood_prone": {"status": "present"}}, scenarios=[{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 500, "basement_levels": 1}]))
    assert check(report, "option.basement", "A")["status"] == "FAIL"


def test_parking_for_apartments_counts_visitors():
    report = assess(payload(dwelling_units=20, average_unit_area_m2=120.0, scenarios=[{"name": "A", "height_m": 12, "floors": 4, "footprint_m2": 500, "basement_levels": 1}]))
    assert check(report, "option.parking", "A")["value"] == 22
    assert "3.5 m" in check(report, "option.ramps", "A")["message"]


def test_parking_part_area_rule():
    # 200 m² unit: one space per 150 m² plus one because the 50 m² remainder is not above 75 m².
    report = assess(payload(dwelling_units=10, average_unit_area_m2=200.0))
    assert check(report, "option.parking", "A")["value"] == 11


def test_eia_trigger_counts_basements():
    report = assess(payload(site_area_m2=10000.0, road_width_m=31.0, scenarios=[{"name": "A", "height_m": 30, "floors": 10, "footprint_m2": 1900, "basement_levels": 2}]))
    assert check(report, "option.eia", "A")["status"] == "REFER"


# The verdict framework
def test_unknowns_never_read_as_clear():
    report = assess(payload())
    assert report["verdict"]["code"] in {"INCOMPLETE", "BLOCKED"}
    assert check(report, "overlay.lake")["status"] == "NEEDS_INPUT"


def test_verdict_precedence():
    make = lambda s: {"id": "x", "status": s}
    assert summarise([make("PASS")])["code"] == "READY_FOR_REVIEW"
    assert summarise([make("PASS"), make("REFER")])["code"] == "PROVISIONAL"
    assert summarise([make("REFER"), make("NOT_CONFIGURED")])["code"] == "PROVISIONAL"
    assert summarise([make("REFER"), make("NEEDS_INPUT")])["code"] == "INCOMPLETE"
    assert summarise([make("NEEDS_INPUT"), make("FAIL")])["code"] == "BLOCKED"


def test_fully_answered_provisional_profile_cannot_reach_ready_for_review():
    overlays = {k: {"status": "absent"} for k in ("lake", "drain", "ht_line", "airport", "heritage", "railway", "defence", "highway", "flood_prone", "road_widening")}
    square = Polygon([(0, 0), (50, 0), (50, 44), (0, 44)])
    boundary = {"points_m": [list(p) for p in list(square.exterior.coords)[:-1]], "holes_m": [], "area_m2": square.area, "perimeter_m": square.length, "vertex_count": 4, "is_convex": True, "use_computed_area": True, "front_edges": [0], "rear_edges": [2]}
    report = assess(payload(boundary=boundary, area_stated_m2=2200.0, overlays=overlays, authority_confirmed=True, zone_confirmed=True, road_width_source="notified", land_status="converted", prior_sanction="none", rmp_ring="I", dwelling_units=20, average_unit_area_m2=100.0, location={"authority": {}}))
    assert report["verdict"]["counts"]["NEEDS_INPUT"] == 0
    assert report["verdict"]["code"] == "PROVISIONAL"


def test_fingerprint_changes_with_any_input():
    assert input_fingerprint(payload()) != input_fingerprint(payload(road_width_m=6.0))
    assert assess(payload())["input_fingerprint"] == input_fingerprint(payload())


def test_report_is_stamped_with_current_version():
    assert assess(payload())["application"]["version"] == __version__


def test_every_rule_table_has_no_overlapping_bands():
    registry = load_authority_registry()
    from siteiq.engine import _find_band
    for authority in registry["authorities"]:
        profile = load_rule_profile(authority["rule_profile"]) if authority.get("rule_profile") else None
        for category in (profile or {}).get("land_use_categories", []):
            for path in [category] + category.get("conditional_paths", []):
                for table in ("road_far_bands", "plot_area_far_caps"):
                    rows = path.get(table) or []
                    for value in [r.get(k) for r in rows for k in ("min", "max")]:
                        if value is not None and value > 0:
                            assert len(_find_band(rows, value)) <= 1, (authority["key"], category["label"], table, value)
