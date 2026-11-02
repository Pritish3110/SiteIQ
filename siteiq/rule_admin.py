"""Check rule profiles and record a reviewer's sign-off.

    python -m siteiq.rule_admin validate
    python -m siteiq.rule_admin sign-off hoskote_lpa2031_candidate --reviewer "Name, CoA no." --effective-from 2026-01-01 --note "Checked against..."
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

from .engine import CALCULATING_STATUSES, RULES_DIR, load_authority_registry, load_json

LIFECYCLE = CALCULATING_STATUSES | {"draft_only", "superseded", "withdrawn_or_stayed", "not_configured"}
FAR_METHODS = {"area_cap_and_road_width", "road_width", "plot_area", "fixed", "special_no_generic_far", "inherit_surrounding_zone"}


def profile_paths() -> list[Path]:
    registry = load_authority_registry()
    wanted = {a["rule_profile"] for a in registry["authorities"] if a.get("rule_profile")}
    return [p for p in sorted(RULES_DIR.glob("*.json")) if load_json(p).get("profile_key") in wanted]


def _band_problems(rows: Iterable[dict], label: str) -> list[str]:
    problems = []
    for row in rows or []:
        low, high = row.get("min", 0), row.get("max")
        if high is not None and low is not None and high < low:
            problems.append(f"{label}: band {low} to {high} runs backwards")
    return problems


def validate_profile(profile: dict) -> list[str]:
    """Return every structural problem in a profile. An empty list means it is well formed."""
    problems = []
    for key in ("profile_key", "profile_name", "source_status", "sources", "land_use_categories"):
        if not profile.get(key):
            problems.append(f"missing {key}")
    status = profile.get("source_status")
    if status not in LIFECYCLE:
        problems.append(f"unknown source_status {status!r}")
    for field in ("effective_from", "effective_to"):
        if profile.get(field):
            try:
                date.fromisoformat(profile[field])
            except ValueError:
                problems.append(f"{field} is not a date: {profile[field]!r}")
    if status == "verified_operative" and not profile.get("reviewed_by"):
        problems.append("verified_operative needs reviewed_by")
    source_ids = {s.get("id") for s in profile.get("sources", [])}
    if len(source_ids) != len(profile.get("sources", [])):
        problems.append("source ids are not unique")
    seen = set()
    def check_rule(rule: dict, label: str) -> None:
        if rule.get("source_id") and rule["source_id"] not in source_ids:
            problems.append(f"{label}: source_id {rule['source_id']!r} is not in sources")
    for category in profile.get("land_use_categories", []):
        label = category.get("label", "?")
        if label in seen:
            problems.append(f"duplicate category {label}")
        seen.add(label)
        for variant in [category] + category.get("conditional_paths", []):
            name = f"{label} / {variant.get('id', 'base')}"
            check_rule(variant, name)
            if variant.get("method") not in FAR_METHODS:
                problems.append(f"{name}: unknown method {variant.get('method')!r}")
            if variant.get("method") in {"road_width", "area_cap_and_road_width"} and not variant.get("road_far_bands"):
                problems.append(f"{name}: road_far_bands is empty")
            if variant.get("method") in {"plot_area", "area_cap_and_road_width"} and not variant.get("plot_area_far_caps"):
                problems.append(f"{name}: plot_area_far_caps is empty")
            problems += _band_problems(variant.get("road_far_bands"), f"{name} road bands")
            problems += _band_problems(variant.get("plot_area_far_caps"), f"{name} area bands")
    for key in ("height_limits",):
        for rule in profile.get(key) or []:
            check_rule(rule, key)
    for key in ("apartment_rules", "basement_limits", "parking_rule", "ramp_rule", "premium_far_rule", "far_exclusions", "electrical_clearance", "building_separation", "accessibility_rule", "services_rule", "housing_typology_rule", "setback_low_rise_table", "stilt_definition"):
        if profile.get(key):
            check_rule(profile[key], key)
    return problems


def validate_all() -> dict[str, list[str]]:
    return {path.name: validate_profile(load_json(path)) for path in profile_paths()}


def sign_off(profile_key: str, reviewer: str, effective_from: str | None = None, note: str = "", on_date: str | None = None, rules_dir: Path = RULES_DIR) -> Path:
    """Mark a profile as reviewed, keeping a dated record. A profile with problems cannot be signed off."""
    if not reviewer.strip():
        raise ValueError("A reviewer's name is required.")
    path = next((p for p in sorted(rules_dir.glob("*.json")) if load_json(p).get("profile_key") == profile_key), None)
    if path is None:
        raise ValueError(f"No rule profile called {profile_key}.")
    profile = load_json(path)
    problems = validate_profile(profile)
    if problems:
        raise ValueError("Fix these first: " + "; ".join(problems))
    stamp = on_date or date.today().isoformat()
    if effective_from:
        date.fromisoformat(effective_from)
        profile["effective_from"] = effective_from
    profile.setdefault("review_history", []).append({"date": stamp, "reviewer": reviewer.strip(), "from_status": profile.get("source_status"), "to_status": "verified_operative", "note": note})
    profile.update(source_status="verified_operative", reviewed_by=reviewer.strip(), last_reviewed=stamp, profile_version=stamp)
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    signing = commands.add_parser("sign-off")
    signing.add_argument("profile")
    signing.add_argument("--reviewer", required=True)
    signing.add_argument("--effective-from")
    signing.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if args.command == "validate":
        results = validate_all()
        for name, problems in results.items():
            print(f"{name}: {'OK' if not problems else '; '.join(problems)}")
        return 1 if any(results.values()) else 0
    try:
        path = sign_off(args.profile, args.reviewer, args.effective_from, args.note)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Signed off {path.name}. Commit this change so the review stays in the project history.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
