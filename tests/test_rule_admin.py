"""Rule profiles stay well formed, and sign-off is deliberate and recorded."""
import json
import shutil

import pytest

from siteiq.engine import RULES_DIR, load_json, match_far_rule
from siteiq.rule_admin import main, sign_off, validate_all, validate_profile

RMP = "bengaluru_rmp2015_partial.json"


def test_every_shipped_profile_is_well_formed():
    results = validate_all()
    assert len(results) == 5
    assert not {k: v for k, v in results.items() if v}


@pytest.mark.parametrize("change,message", [
    ({"source_status": "maybe"}, "unknown source_status"),
    ({"effective_from": "soon"}, "not a date"),
    ({"source_status": "verified_operative", "reviewed_by": None}, "needs reviewed_by"),
])
def test_bad_profiles_are_caught(change, message):
    profile = load_json(RULES_DIR / RMP)
    profile.update(change)
    assert any(message in p for p in validate_profile(profile))


def test_unknown_source_reference_is_caught():
    profile = load_json(RULES_DIR / RMP)
    profile["land_use_categories"][0]["source_id"] = "nope"
    assert any("nope" in p for p in validate_profile(profile))


def test_backwards_band_is_caught():
    profile = load_json(RULES_DIR / RMP)
    profile["land_use_categories"][0]["road_far_bands"][0].update(min=20, max=10)
    assert any("backwards" in p for p in validate_profile(profile))


@pytest.fixture
def rules_copy(tmp_path):
    shutil.copy(RULES_DIR / RMP, tmp_path / RMP)
    return tmp_path


def test_sign_off_sets_status_and_keeps_a_record(rules_copy):
    path = sign_off("bengaluru_rmp2015_partial", "A. Architect, CoA 123", "2026-01-05", "Checked Tables 8 to 21", "2026-11-03", rules_dir=rules_copy)
    profile = json.loads(path.read_text(encoding="utf-8"))
    assert profile["source_status"] == "verified_operative" and profile["reviewed_by"] == "A. Architect, CoA 123"
    assert profile["review_history"][-1] == {"date": "2026-11-03", "reviewer": "A. Architect, CoA 123", "from_status": "official_source_found_pending_review", "to_status": "verified_operative", "note": "Checked Tables 8 to 21"}
    assert match_far_rule(profile, "Residential (Main)", 2200, 18)["maximum_far"] == 2.25


def test_sign_off_needs_a_reviewer_and_a_known_profile(rules_copy):
    with pytest.raises(ValueError, match="reviewer"):
        sign_off("bengaluru_rmp2015_partial", "  ", rules_dir=rules_copy)
    with pytest.raises(ValueError, match="No rule profile"):
        sign_off("nope", "A", rules_dir=rules_copy)


def test_broken_profile_cannot_be_signed_off(rules_copy):
    path = rules_copy / RMP
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["source_status"] = "maybe"
    path.write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(ValueError, match="Fix these first"):
        sign_off("bengaluru_rmp2015_partial", "A", rules_dir=rules_copy)


def test_command_line_validate(capsys):
    assert main(["validate"]) == 0
    assert "OK" in capsys.readouterr().out
