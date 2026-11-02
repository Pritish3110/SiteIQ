import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from siteiq import __version__
from siteiq.engine import (
    load_authority_registry, load_rule_profile, match_far_rule,
    calculate_setbacks, calculate_basement_setbacks, build_report,
)


def test_hoskote_general_residential_far_uses_road_width_table():
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    result = match_far_rule(profile, "Residential", 2200, 18.5, proposed_use="Residential apartments")
    assert result["status"] == "candidate_match_requires_verification"
    assert result["maximum_far"] == 2.25
    assert result["maximum_far_area_m2"] == 4950.0
    assert result["rule_source_quality"] == "official_authority_copy_pending_review"
    assert result["source"]["id"] == "base_zr_table4"


def test_hoskote_group_housing_conditional_path_uses_net_far_area():
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    area = 20684.0
    result = match_far_rule(profile, "Residential", area, 36, proposed_use="Residential apartments")
    assert result["status"] == "candidate_match_requires_verification"
    assert result["maximum_far"] == 2.75
    assert result["selected_path"] == "hoskote_table5"
    assert result["far_calculation_area_m2"] == round(area * 0.95, 2)
    assert result["maximum_far_area_m2"] == round(area * 0.95 * 2.75, 2)
    assert result["matched_rule"]["details"]["deduction_pct"] == 5.0


def test_hoskote_group_housing_below_minimum_road_width_does_not_assign_far():
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    result = match_far_rule(profile, "Residential", 20684, 10, proposed_use="Residential apartments")
    assert result["status"] == "minimum_road_width_not_met"
    assert result["maximum_far"] is None


def test_anekal_group_housing_uses_table_6_of_the_published_plan_on_gross_area():
    profile = load_rule_profile("anekal_lpa2031_candidate")
    result = match_far_rule(profile, "Residential", 20684, 18.5, proposed_use="Residential apartments")
    assert result["maximum_far"] == 2.5
    assert result["far_calculation_area_m2"] == 20684
    assert any("gross area" in c for c in result["conditions"])


def test_lpa_height_setbacks_follow_lpa_table_3_not_bengaluru_area_override():
    # Published Table 2 note: plots of 4,000 m² and above need at least 5.0 m, which lifts the 4.5 m Table 3 row.
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    result12 = calculate_setbacks(profile, 20684, 120, 171, 12, False, zone="Residential")
    result15 = calculate_setbacks(profile, 20684, 120, 171, 15, False, zone="Residential")
    result18 = calculate_setbacks(profile, 20684, 120, 171, 18, False, zone="Residential")
    assert result12["all_round_m"] == 5.0
    assert result15["all_round_m"] == 5.0
    assert result18["all_round_m"] == 6.0
    assert result15["source"]["id"] == "base_zr_table3"


def test_lpa_basement_rules_come_from_their_own_plan():
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    building = calculate_setbacks(profile, 2200, 33, 68, 15, False, zone="Residential")
    basement = calculate_basement_setbacks(profile, "Residential", 2200, building, 1)
    assert (basement["front_m"], basement["rear_m"], basement["left_m"]) == (5.0, 2.0, 2.0)


def test_premium_far_is_optional_scenario_and_does_not_change_base_far():
    profile = load_rule_profile("hoskote_lpa2031_candidate")
    result = match_far_rule(profile, "Residential", 20684, 18.5, proposed_use="Residential apartments")
    assert result["maximum_far"] == 2.5  # road >18 to 24 m group-housing band
    premium = result["premium_far"]
    assert premium["status"] == "premium_far_plus_tdr_candidate"
    assert premium["maximum_additional_far_factor"] == 0.6
    assert premium["potential_total_far_candidate"] == 4.0
    assert result["maximum_far"] == 2.5  # premium FAR remains separate from the base benchmark


def test_group_housing_build_report_uses_net_area_for_capacity_and_option_yield():
    registry = load_authority_registry()
    site = {
        "authority_key": "hoskote_planning_authority", "project_name": "Hoskote group housing test",
        "site_area_m2": 20684, "road_width_m": 36, "land_use_category": "Residential",
        "zone": "Residential", "proposed_use": "Residential apartments", "frontage_m": 120,
        "depth_m": 171, "shape_type": "Irregular / non-rectangular", "height_for_setback_m": 15,
        "scenarios": [{"name":"Option 01","height_m":15,"floors":5,"footprint_m2":10000,"stilt":False,"basement_levels":1}],
    }
    report = build_report(site, registry=registry)
    assert report["application"]["version"] == __version__
    assert report["maximum_far"] == 2.75
    assert report["maximum_far_area_m2"] == round(20684 * 0.95 * 2.75, 2)
    assert "provisional rule" in report["scenarios"][0]["benchmark_source"]
    assert report["scenarios"][0]["far_capacity_m2"] == round(20684 * 0.95 * 2.75, 2)
    assert report["scenarios"][0]["achieved_gross_far_ratio"] == round(50000 / (20684 * 0.95), 3)


def test_kanakapura_and_nelamangala_profiles_return_provisional_group_housing_candidates():
    for key in ("kanakapura_lpa2031_candidate", "nelamangala_lpa2031_candidate"):
        profile = load_rule_profile(key)
        result = match_far_rule(profile, "Residential", 15000, 20, proposed_use="Residential apartments")
        assert result["status"] == "candidate_match_requires_verification"
        assert result["maximum_far"] == 2.5
        assert result["selected_path"] in {"kanakapura_table6", "nelamangala_table5"}
        assert result["rule_source_quality"] == "official_authority_copy_pending_review"


def test_provisional_lpa_group_housing_scenario_labels_net_far_basis():
    registry = load_authority_registry()
    site = {
        "authority_key": "hoskote_planning_authority", "project_name": "Hoskote net basis report test",
        "site_area_m2": 20684.0, "road_width_m": 36, "land_use_category": "Residential",
        "zone": "Not verified", "proposed_use": "Residential apartments", "frontage_m": 120,
        "depth_m": 171, "shape_type": "Irregular / non-rectangular", "height_for_setback_m": 15,
        "scenarios": [{"name":"Option 01","height_m":15,"floors":5,"footprint_m2":10000,"stilt":False,"basement_levels":1}],
    }
    report = build_report(site, registry=registry)
    option = report["scenarios"][0]
    assert report["far"]["rule_source_quality"] == "official_authority_copy_pending_review"
    assert report["maximum_far"] == 2.75
    assert option["far_ratio_basis"].startswith("net FAR calculation area")
    assert option["far_calculation_area_m2"] == round(20684 * 0.95, 2)
    assert option["achieved_far_ratio"] == round(50000 / (20684 * 0.95), 3)
    assert "provisional rule" in option["benchmark_source"]
