import csv
import json
from pathlib import Path

from siteiq.engine import load_authority_registry, load_rule_profile, find_authority

ROOT = Path(__file__).resolve().parents[1]


def test_registry_has_bmrda_lpa_discovery_entries():
    registry = load_authority_registry()
    keys = {a["key"] for a in registry["authorities"]}
    expected = {
        "anekal_planning_authority",
        "biaapa",
        "channapatna_planning_authority",
        "doddaballapura_planning_authority",
        "hoskote_planning_authority",
        "kanakapura_planning_authority",
        "magadi_planning_authority",
        "nelamangala_planning_authority",
        "strr_planning_authority",
        "gbda_bmr_draft_reference",
        "ramanagara_urban_development_authority",
    }
    assert expected <= keys


def test_draft_uniform_regulations_are_not_active_rules():
    candidate_path = ROOT / "rules" / "candidate_profiles" / "bmrda_uniform_zoning_udd559_draft_2026.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["status"] == "DRAFT_ONLY_NOT_ENABLED_FOR_AUTOMATIC_CALCULATIONS"
    assert candidate["date"] == "2026-03-24"
    assert load_rule_profile("bmrda_uniform_zoning_udd559_draft_2026") is None


def test_kanakapura_master_plan_has_provisional_candidate_profile_not_official_activation():
    registry = load_authority_registry()
    authority = find_authority(registry, "kanakapura_planning_authority")
    assert authority.get("rule_profile") == "kanakapura_lpa2031_candidate"
    profile = load_rule_profile(authority["rule_profile"])
    assert profile is not None
    assert profile["rule_source_quality"] == "official_authority_copy_pending_review"
    assert "PROVISIONAL" in profile["profile_status"]
    # An old review-candidate metadata file remains as source history, not the active profile.
    candidate_path = ROOT / "rules" / "candidate_profiles" / "kanakapura_mp2031_review_candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["status"] == "NOT_ENABLED_FOR_AUTOMATIC_CALCULATIONS"
    assert any("77.323792" in question for question in candidate["verification_questions"])


def test_unconfigured_authorities_do_not_borrow_bengaluru_profile():
    registry = load_authority_registry()
    for key in ("mysuru_development_authority", "hubballi_dharwad_udau", "bda_lpa"):
        authority = find_authority(registry, key)
        assert authority.get("rule_profile") is None
        assert load_rule_profile(authority.get("rule_profile") or "") is None


def test_four_lpa_profiles_are_enabled_as_provisional_candidates_only():
    registry = load_authority_registry()
    for key in ("hoskote_planning_authority", "kanakapura_planning_authority", "nelamangala_planning_authority", "anekal_planning_authority"):
        authority = find_authority(registry, key)
        profile = load_rule_profile(authority.get("rule_profile"))
        assert profile is not None
        assert profile["rule_source_quality"] == "official_authority_copy_pending_review"
        assert "provisional" in authority["status"]


def test_coverage_csv_tracks_authority_status_and_far_activation():
    path = ROOT / "rules" / "authority_coverage_matrix.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 20
    assert all("status" in row and "profile_can_calculate_far" in row for row in rows)
    kpa = next(row for row in rows if row["authority_key"] == "kanakapura_planning_authority")
    assert kpa["profile_can_calculate_far"] == "yes_provisional"
    hoskote = next(row for row in rows if row["authority_key"] == "hoskote_planning_authority")
    assert hoskote["profile_can_calculate_far"] == "yes_provisional"
    assert next(row for row in rows if row["authority_key"] == "mysuru_development_authority")["profile_can_calculate_far"] == "no"
