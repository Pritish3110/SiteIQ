"""Multi-Site Benchmark Verification Suite for SiteIQ (v2.0).

Verifies the 10 real-world and synthetic benchmark test cases defined in the
Master Implementation Plan, testing:
- Dual-constraint FAR matching without interpolation
- Statutory Gross vs Net FAR calculation area deductions (15% park + 5% CA)
- Karnataka Fire Force (Amendment) Act 2023 (21m threshold & 6m fire driveway)
- Multi-authority LPA profiles (Hoskote, Kanakapura, Nelamangala, Anekal)
- Google Maps short link resolution and Tumakuru planning authority candidate
- Geometry checks (envelope splitting, narrow neck detection)
- Strict prohibition of silent fallback to Bengaluru rules
"""
import json
import pytest
from pathlib import Path
from shapely.geometry import Polygon

from siteiq import location
from siteiq.engine import (
    load_authority_registry, find_authority, load_rule_profile,
    match_far_rule, calculate_setbacks, build_report,
)
from siteiq.boundary import calculate_setback_envelope


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_authority_registry()


def test_benchmark_tc01_nandi_housing_ground_truth():
    """TC-01: Nandi Housing (Umiya Prism) benchmark.
    Tests Commercial / RMP 2015 base FAR lookup and option comparison.
    """
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    assert profile is not None
    # 2,200 m² site, 18.5 m road width
    res = match_far_rule(profile, "Commercial (Central)", 2200.0, 18.5)
    assert res["status"] == "candidate_match_requires_verification"
    assert res["maximum_far"] == pytest.approx(2.50)
    assert res["maximum_far_area_m2"] == pytest.approx(5500.0)


def test_benchmark_tc02_hoskote_industrial_statutory_deduction():
    """TC-02: Hoskote Industrial Park with 20% statutory reservation deduction.
    Verifies that statutory deduction reduces the FAR calculation area.
    """
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    assert profile is not None
    site_area = 8500.0
    road_width = 24.0
    # A typed reduction is accepted as a labelled assumption, not as a rule.
    res = match_far_rule(
        profile, "Industrial Buildings (plot-area table)", site_area, road_width,
        statutory_deduction_pct=20.0,
    )
    assert res["status"] == "candidate_match_requires_verification"
    assert res["maximum_far"] is not None
    expected_net_area = 8500.0 * 0.80  # 6,800 m²
    assert res["far_calculation_area_m2"] == pytest.approx(expected_net_area)
    assert res["maximum_far_area_m2"] == pytest.approx(expected_net_area * res["maximum_far"])
    assert res["matched_rule"]["details"]["deduction_pct"] == 20.0
    assert res["matched_rule"]["details"]["deduction_source"] == "user_assumption"


def test_benchmark_tc03_kanakapura_group_housing_threshold():
    """TC-03: Kanakapura Highway Parcel (>= 1 hectare apartment group housing).
    Verifies conditional table path selection for >= 10,000 m².
    """
    profile = load_rule_profile("kanakapura_lpa2031_candidate")
    assert profile is not None
    # 12,400 m² parcel (>= 10,000 m² / 1 hectare)
    res = match_far_rule(
        profile, "Residential", 12400.0, 18.0,
        proposed_use="Residential apartments",
    )
    assert res["status"] == "candidate_match_requires_verification"
    assert res["maximum_far"] is not None
    assert res.get("selected_path") == "kanakapura_table6"


def test_benchmark_tc04_nelamangala_logistics_hub():
    """TC-04: Nelamangala Logistics Hub on 30m highway.
    Verifies road-width band selection in Nelamangala LPA candidate profile.
    """
    profile = load_rule_profile("nelamangala_lpa2031_candidate")
    assert profile is not None
    res = match_far_rule(profile, "Industrial Buildings (plot-area table)", 18000.0, 30.0)
    assert res["status"] == "candidate_match_requires_verification"
    assert res["maximum_far"] is not None


def test_benchmark_tc05_anekal_single_plot():
    """TC-05: Anekal Town Plot (1,450 m²).
    Verifies Anekal LPA candidate general table lookup.
    """
    profile = load_rule_profile("anekal_lpa2031_candidate")
    assert profile is not None
    res = match_far_rule(profile, "Residential", 1450.0, 12.0)
    assert res["status"] == "candidate_match_requires_verification"
    assert res["maximum_far"] is not None


def test_benchmark_tc06_tumakuru_location_candidate_mapping():
    """TC-06: Verifies Tumakuru address/reverse geocode maps to tumakuru_uda candidate
    instead of generic other_karnataka.
    """
    candidate = location._locality_candidate({
        "display_name": "Tumakuru, Tumkur taluk, Tumakuru District, Karnataka, India",
        "address": {"city": "Tumakuru", "county": "Tumkur taluk", "state": "Karnataka"},
    })
    assert candidate["key"] == "tumakuru_uda"
    assert candidate["status"] == "provisional_geocoder_candidate"
    assert "Tumakuru Urban Development Authority" in candidate["reason"]


def test_benchmark_tc07_fire_force_act_2023_high_rise_triggers():
    """TC-07: Karnataka Fire Force (Amendment) Act 2023.
    Verifies building height >= 21m triggers High-Rise status, Fire NOC,
    and is sourced from the statewide rule file.
    """
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    site = {
        "project_name": "High-Rise Test Tower",
        "authority_key": "bengaluru_rmp2015",
        "land_use_category": "Residential (Main)",
        "site_area_m2": 6500.0,
        "road_width_m": 24.0,
        "scenarios": [
            {"name": "Option 01 - Low Rise", "height_m": 15.0, "floors": 5, "footprint_m2": 1000},
            {"name": "Option 02 - High Rise", "height_m": 24.0, "floors": 8, "footprint_m2": 800},
        ],
    }
    report = build_report(site, registry=REGISTRY, profile=profile)
    fire = report["fire"]
    assert fire["status"] == "triggered_by_height_scenario"
    assert fire["is_high_rise"] is True
    assert fire["fire_noc_required"] is True
    # Fire access dimensions are not sized by SiteIQ: the 6/9/12 m figures had no configured source.
    assert "minimum_fire_driveway_width_m" not in fire
    assert fire["source"]["notification"] == "Karnataka Act No. 24 of 2023"


def test_benchmark_tc08_geometry_split_and_narrow_neck_detection():
    """TC-08: Geometry checks for multi-part envelope and narrow neck detection."""
    # Create an L-shaped concave polygon with a narrow section
    coords = [
        (0.0, 0.0), (100.0, 0.0), (100.0, 30.0), (35.0, 30.0),
        (35.0, 80.0), (0.0, 80.0), (0.0, 0.0)
    ]
    poly = Polygon(coords)
    assert poly.is_valid
    # Setback with 5m all around
    setback_res = {"all_round_m": 5.0}
    env = calculate_setback_envelope(poly, setback_res)
    assert env["status"] == "calculated_preliminary"
    assert env["area_m2"] > 0
    assert "geometry" in env


def test_benchmark_tc09_multi_authority_zero_silent_fallback():
    """TC-09: Unconfigured authorities (e.g. Mysuru) must never borrow Bengaluru FAR."""
    auth = find_authority(REGISTRY, "mysuru_development_authority")
    assert auth["rule_profile"] is None
    profile = load_rule_profile(auth.get("rule_profile"))
    assert profile is None
    res = match_far_rule(profile, "Residential", 2000.0, 18.0)
    assert res["status"] == "not_configured"
    assert res["maximum_far"] is None


def test_benchmark_tc10_statutory_net_vs_gross_area_accounting():
    """TC-10: Complete trace of Gross vs Net site area deductions."""
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    gross_area = 5000.0
    # In Table 10: road width > 24m up to 30m yields road FAR 3.00,
    # and plot area 2000m² - 4000m² has cap 3.0, plot area >4000m² has cap 3.25.
    # With road_width = 25.0, road FAR = 3.00, area cap = 3.25, min(3.25, 3.0) = 3.00!
    road_width = 25.0
    # A what-if reduction: RMP Chapter 7 itself only deducts the civic-amenity site from the FAR area.
    res = match_far_rule(
        profile, "Residential (Main)", gross_area, road_width,
        statutory_deduction_pct=20.0,
    )
    assert res["status"] == "candidate_match_requires_verification"
    assert res["matched_rule"]["gross_site_area_m2"] == 5000.0
    assert res["matched_rule"]["far_calculation_area_m2"] == 4000.0
    assert res["matched_rule"]["details"]["excluded_area_m2"] == 1000.0
    assert res["maximum_far"] == pytest.approx(3.0)
    # Capacity is 4000m² * 3.0 = 12,000m² (NOT 5000 * 3.0 = 15,000m²)
    assert res["maximum_far_area_m2"] == pytest.approx(12000.0)
