import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from siteiq.engine import (
    load_authority_registry, load_rule_profile, match_far_rule,
    calculate_setbacks, calculate_rectangular_proxy, build_scenarios, build_report
)


def test_rmp_regulation_3_4_applies_lower_of_area_cap_and_road_far():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = match_far_rule(profile, "Residential (Main)", 2200, 18.5)
    assert result["status"] == "candidate_match_requires_verification"
    assert result["maximum_far"] == 2.5
    assert result["maximum_far_area_m2"] == 5500.0
    assert result["matched_rule"]["details"]["limiting_factor"] == "road width"


def test_far_band_gap_does_not_guess_at_exact_road_width_boundary():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = match_far_rule(profile, "Commercial (Business)", 1200, 9.0)
    assert result["status"] == "no_matching_far_band"
    assert result["maximum_far"] is None


def test_table10_single_row_candidate_matches_both_bands():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = match_far_rule(profile, "Residential (Main)", 1500, 20)
    assert result["status"] == "candidate_match_requires_verification"
    assert result["matched_rule"]["far"] == 2.5


def test_far_not_selected_if_zone_unknown():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = match_far_rule(profile, "Not verified", 1500, 20)
    assert result["status"] == "zone_not_supported"


def test_table8_setback_formula_uses_nominal_dimensions():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = calculate_setbacks(profile, 2200, 33, 68, 12, False)
    assert result["front_m"] == 8.16
    assert result["rear_m"] == 5.44
    assert result["left_m"] == 2.64
    assert result["right_m"] == 2.64
    assert result["status"] == "nominal_calculation_requires_site_geometry_check"


def test_table9_height_band():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    result = calculate_setbacks(profile, 2200, 33, 68, 17, False)
    assert result["all_round_m"] == 6.0


def test_scenario_math_transparent():
    result = build_scenarios(2200, [{"name":"A", "height_m":12, "floors":4, "footprint_m2":1000}], max_far_benchmark=2.5)[0]
    assert result["gross_concept_area_m2"] == 4000
    assert result["achieved_gross_far_ratio"] == 1.818
    assert result["far_capacity_m2"] == 5500
    assert result["scenario_headroom_m2"] == 1500


def test_single_plot_flag_is_conditional_and_no_guidance_value_invented():
    site = {
        "authority_key":"bengaluru_rmp2015", "project_name":"Test", "site_area_m2":2200,
        "road_width_m":18.5, "zone":"Residential (Main)", "proposed_use":"Residential apartments",
        "approval_path":"Not sure / needs confirmation", "scenarios":[],
    }
    report = build_report(site, registry=load_authority_registry())
    assert report["single_plot"]["park_option_m2"] == 220
    assert report["single_plot"]["guidance_value_charge_pct"] == 10
    assert report["single_plot"]["status"] == "applicability_needs_confirmation"


def test_unconfigured_authority_never_reuses_bengaluru_rules():
    site = {
        "authority_key":"mysuru_development_authority", "site_area_m2":2200,
        "road_width_m":18.5, "zone":"Residential (Main)", "proposed_use":"Residential apartments",
        "scenarios":[]
    }
    report = build_report(site, registry=load_authority_registry())
    assert report["far"]["status"] == "not_configured"
    assert report["setbacks"]["status"] == "not_configured"


def test_rectangular_proxy_is_explicit_and_labelled_non_statutory():
    site = {
        "frontage_m":33, "depth_m":68, "shape_type":"Regular rectangular",
        "geometry_mode":"Rectangular proxy (preliminary only)"
    }
    setbacks = {"front_m":8.16, "rear_m":5.44, "left_m":2.64, "right_m":2.64}
    result = calculate_rectangular_proxy(site, setbacks)
    assert result["status"] == "indicative_rectangular_proxy_only"
    assert result["area_m2"] == 1507.97
    assert "not a statutory" in result["message"]


def test_build_report_calculates_setbacks_for_each_option_height():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    site = {
        "authority_key":"bengaluru_rmp2015", "project_name":"Nandi test",
        "site_area_m2":2200, "road_width_m":18.5,
        "frontage_m":33, "depth_m":68, "shape_type":"Irregular / non-rectangular",
        "zone":"Residential (Main)", "proposed_use":"Residential apartments",
        "height_for_setback_m":12, "stilt":False,
        "scenarios":[
            {"name":"Option 01", "height_m":12, "floors":4, "footprint_m2":1483, "assumed_far":2.5, "stilt":False},
            {"name":"Option 02", "height_m":15, "floors":5, "footprint_m2":1271, "assumed_far":2.5, "stilt":False},
            {"name":"Option 03", "height_m":18, "floors":6, "footprint_m2":1106, "assumed_far":2.5, "stilt":False},
        ]
    }
    report = build_report(site, registry=load_authority_registry(), profile=profile)
    one, two, three = report["scenarios"]
    assert one["setback_result"]["front_m"] == 8.16
    assert one["setback_result"]["rear_m"] == 5.44
    assert one["setback_result"]["left_m"] == 2.64
    assert one["setback_summary"] == "Front 8.16 / Rear 5.44 / Sides 2.64, 2.64 m"
    assert two["setback_result"]["all_round_m"] == 5.0
    assert two["setback_result"]["front_m"] == 5.0
    assert two["setback_summary"] == "5.00 m all sides"
    assert three["setback_result"]["all_round_m"] == 6.0
    assert three["setback_result"]["right_m"] == 6.0
    assert three["setback_summary"] == "6.00 m all sides"
    assert "authority_check" in two["setback_status"]
    assert "authority_check" in three["setback_status"]


def test_unconfigured_authority_scenario_setbacks_stay_unresolved():
    site = {
        "authority_key":"mysuru_development_authority", "site_area_m2":2200,
        "road_width_m":18.5, "frontage_m":33, "depth_m":68,
        "zone":"Residential (Main)", "proposed_use":"Residential apartments",
        "scenarios":[{"name":"Option 02", "height_m":15, "floors":5, "footprint_m2":1200, "assumed_far":2.5, "stilt":False}]
    }
    report = build_report(site, registry=load_authority_registry())
    opt = report["scenarios"][0]
    assert opt["setback_result"]["status"] == "not_configured"
    assert opt["setback_summary"] == "Not determined"


def test_option_stilt_setting_is_used_independently_from_site_level_default():
    profile = load_rule_profile("bengaluru_rmp2015_partial")
    site = {
        "authority_key":"bengaluru_rmp2015", "site_area_m2":2200, "road_width_m":18.5,
        "frontage_m":33, "depth_m":68, "zone":"Residential (Main)",
        "proposed_use":"Residential apartments", "stilt":False,
        "scenarios":[
            {"name":"No stilt", "height_m":15, "floors":5, "footprint_m2":1200, "assumed_far":2.5, "stilt":False},
            {"name":"With stilt", "height_m":15, "floors":5, "footprint_m2":1200, "assumed_far":2.5, "stilt":True},
        ]
    }
    report = build_report(site, registry=load_authority_registry(), profile=profile)
    no_stilt, with_stilt = report["scenarios"]
    assert no_stilt["setback_result"]["all_round_m"] == 5.0
    assert no_stilt["stilt"] is False
    assert with_stilt["stilt"] is True
    assert with_stilt["setback_result"]["all_round_m"] is None
    assert with_stilt["setback_result"]["front_m"] is not None
