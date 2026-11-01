"""SiteIQ MVP core calculations.

The calculation layer has no Streamlit dependency so it can be unit-tested in isolation.
Only explicitly configured rule profiles may produce regulatory candidates. User-entered
FARs and footprints are presented as what-if scenarios, never as entitlements.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "rules"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_authority_registry() -> dict:
    return load_json(RULES_DIR / "authority_registry.json")


def load_rule_profile(profile_key: str) -> Optional[dict]:
    """Load a rule profile by key, if present."""
    candidates = list(RULES_DIR.glob("*.json"))
    for path in candidates:
        if path.name == "authority_registry.json":
            continue
        data = load_json(path)
        if data.get("profile_key") == profile_key:
            return data
    return None


def find_authority(registry: dict, key: str) -> dict:
    for authority in registry.get("authorities", []):
        if authority.get("key") == key:
            return authority
    raise KeyError(f"Unknown authority key: {key}")


def _band_contains(value: float, minimum: float, maximum: Optional[float], min_exclusive: bool) -> bool:
    if min_exclusive:
        lower_ok = value > minimum
    else:
        lower_ok = value >= minimum
    upper_ok = True if maximum is None else value <= maximum
    return lower_ok and upper_ok


# --- Rule-catalog lookup helpers (v0.4.0) ---
def land_use_categories(profile: Optional[dict]) -> list[dict]:
    """Land-use categories configured for this authority profile only."""
    return list((profile or {}).get("land_use_categories", []))


def category_by_label(profile: Optional[dict], zone: str | None) -> Optional[dict]:
    if not profile or not zone:
        return None
    token = str(zone).strip().casefold()
    for item in land_use_categories(profile):
        if token in {str(item.get("label", "")).strip().casefold(), str(item.get("key", "")).strip().casefold()}:
            return item
    # Legacy aliases only map to the same explicit category; no cross-authority fallback.
    aliases = {
        "residential main": "Residential (Main)",
        "residential (main)": "Residential (Main)",
        "residential mixed": "Residential (Mixed)",
        "residential (mixed)": "Residential (Mixed)",
        "public / semi-public": "Public and Semi-public (P&SP)",
        "public and semi public": "Public and Semi-public (P&SP)",
        "industrial (hi-tech)": "Industrial (Hi-Tech)",
        "industrial hi-tech": "Industrial (Hi-Tech)",
    }
    alias = aliases.get(token)
    if alias:
        for item in land_use_categories(profile):
            if item.get("label", "").casefold() == alias.casefold():
                return item
    return None


def _get_bounds(band: dict, prefix: str = "") -> tuple[float, Optional[float], bool, bool]:
    """Return low/high/inclusive metadata for generic or legacy regulatory bands."""
    low = band.get("min", band.get(prefix + "min", 0))
    high = band.get("max", band.get(prefix + "max"))
    low_ex = band.get("min_exclusive", band.get(prefix + "min_exclusive", False))
    high_ex = band.get("max_exclusive", False)
    return float(low or 0), (float(high) if high is not None else None), bool(low_ex), bool(high_ex)


def _matches_band(value: float, band: dict, prefix: str = "") -> bool:
    low, high, low_ex, high_ex = _get_bounds(band, prefix)
    low_ok = value > low if low_ex else value >= low
    high_ok = True if high is None else (value < high if high_ex else value <= high)
    return low_ok and high_ok


def _find_band(rows: list[dict], value: float, prefix: str = "") -> list[dict]:
    return [row for row in rows or [] if _matches_band(float(value), row, prefix)]


def _band_desc(band: dict, kind: str) -> str:
    if kind == "road":
        low, high, low_ex, high_ex = _get_bounds(band, "road_")
        label = band.get("upper_label")
        if label:
            return label
        low_s = f"> {low:g}" if low_ex else f">= {low:g}"
        high_s = "no upper limit" if high is None else (f"< {high:g}" if high_ex else f"<= {high:g}")
        return f"road width {low_s} to {high_s} m"
    low, high, low_ex, high_ex = _get_bounds(band, "plot_")
    low_s = f"> {low:g}" if low_ex else f">= {low:g}"
    high_s = "no upper limit" if high is None else (f"< {high:g}" if high_ex else f"<= {high:g}")
    return f"plot area {low_s} to {high_s} m²"


def _coverage_result(profile: dict, category: dict, site_area_m2: float, road_width_m: float) -> dict:
    amendment = profile.get("coverage_amendment", {})
    if amendment and site_area_m2 <= float(amendment.get("site_area_max_m2", 4000)):
        return {
            "status": "chapter4_coverage_not_considered_for_area_up_to_4000",
            "coverage_pct": None,
            "message": amendment.get("status", "Chapter 4 coverage limits are not considered for this site-area band under the supplied amendment."),
            "source": source_by_id(profile, amendment.get("source_id")),
        }
    method = category.get("coverage_method")
    pct = category.get("coverage_fixed_pct")
    matched = None
    if pct is None and category.get("coverage_bands"):
        measure = road_width_m if method == "road_width" else site_area_m2
        matched_rows = _find_band(category.get("coverage_bands", []), measure)
        if len(matched_rows) == 1:
            matched = matched_rows[0]
            pct = matched.get("coverage_pct")
    if pct is None:
        return {"status": "not_configured", "coverage_pct": None, "message": "No coverage value has been configured for this land-use category.", "source": source_by_id(profile, category.get("source_id"))}
    return {
        "status": "table_value_requires_verification",
        "coverage_pct": float(pct),
        "message": "Coverage value transcribed from the selected table. Confirm its current applicability and the table's zone/use conditions.",
        "matched_band": matched,
        "source": source_by_id(profile, category.get("source_id")),
    }


def match_far_rule(profile: Optional[dict], zone: str, site_area_m2: float, road_width_m: float, surrounding_zone: str | None = None, proposed_use: str | None = None) -> dict:
    """Select the best configured FAR rule for a land-use category, with no interpolation.

    Every positive result is labelled a candidate from the configured source profile. It is
    not an authority approval or legal entitlement. Area/road bands are handled according to
    the table's own structure rather than forcing every table into a single paired-row model.
    """
    if not profile:
        return {"status": "not_configured", "message": "No rule profile is configured for this planning authority. FAR was not calculated.", "matched_rule": None, "candidate_rules": [], "source": None, "maximum_far": None}
    cat = category_by_label(profile, zone)
    if not cat:
        return {"status": "zone_not_supported", "message": "Choose a land-use category from the selected authority's configured rule catalogue. No category was inferred.", "matched_rule": None, "candidate_rules": [], "source": None, "maximum_far": None}

    # Some LPA plans have a special Group Housing table for apartment projects at
    # >=1 hectare. Resolve that path explicitly rather than reusing the general
    # residential table. No generic value is inferred when a profile marks a path
    # as unresolved because source copies conflict.
    original_cat = cat
    selected_path = None
    for path in cat.get("conditional_paths", []):
        when = path.get("when", {})
        if site_area_m2 < float(when.get("site_area_min_m2", 0)):
            continue
        contains = [str(x).casefold() for x in when.get("proposed_use_contains_any", [])]
        use_text = (proposed_use or "").casefold()
        if contains and not any(term in use_text for term in contains):
            continue
        selected_path = path
        cat = {**cat, **{k: v for k, v in path.items() if k not in {"id", "when", "label"}}}
        cat["key"] = original_cat.get("key")
        cat["label"] = original_cat.get("label")
        cat["conditional_path_id"] = path.get("id")
        cat["conditional_path_label"] = path.get("label", path.get("table", "Conditional rule path"))
        cat["conditions"] = list(original_cat.get("conditions", [])) + list(path.get("conditions", []))
        cat["far_interpretation"] = path.get("far_interpretation", original_cat.get("far_interpretation", ""))
        break

    method = cat.get("method")
    source = source_by_id(profile, cat.get("source_id"))
    coverage = _coverage_result(profile, cat, site_area_m2, road_width_m)
    base = {
        "category": cat.get("label"), "category_key": cat.get("key"), "table": cat.get("table"),
        "coverage": coverage, "conditions": cat.get("conditions", []),
        "far_interpretation": cat.get("far_interpretation", ""), "source": source,
        "profile_name": profile.get("profile_name"),
        "profile_status": profile.get("profile_status", ""),
        "rule_source_quality": profile.get("rule_source_quality", "unspecified"),
        "selected_path": cat.get("conditional_path_label"),
    }

    # Eligibility checks are explicit; a table cannot be applied outside its scope.
    eligibility = cat.get("eligibility", {})
    max_area = eligibility.get("plot_area_max_m2")
    if max_area is not None and site_area_m2 > float(max_area):
        return {**base, "status": "outside_configured_table_scope", "message": f"This table is configured only up to {float(max_area):,.0f} m². A different development-plan or special pathway may apply; SiteIQ did not reuse this FAR.", "matched_rule": None, "candidate_rules": [], "maximum_far": None}
    min_area = eligibility.get("plot_area_min_m2")
    if min_area is not None and site_area_m2 < float(min_area):
        return {**base, "status": "outside_configured_table_scope", "message": f"This table is configured from {float(min_area):,.0f} m² and above. SiteIQ did not reuse this FAR.", "matched_rule": None, "candidate_rules": [], "maximum_far": None}
    min_road = eligibility.get("road_width_min_m")
    if min_road is not None and road_width_m < float(min_road):
        return {**base, "status": "minimum_road_width_not_met", "message": f"This rule path requires an abutting road of at least {float(min_road):g} m. The entered road width is {road_width_m:g} m, so this FAR row was not applied.", "matched_rule": None, "candidate_rules": [], "maximum_far": None}

    if method == "special_no_generic_far":
        return {**base, "status": "special_case_no_generic_far", "message": cat.get("far_interpretation", "The source has no general FAR rule configured for this category."), "matched_rule": None, "candidate_rules": [], "maximum_far": None}

    if method == "inherit_surrounding_zone":
        if not surrounding_zone or surrounding_zone in {zone, "Not verified", "Not selected"}:
            return {**base, "status": "surrounding_zone_required", "message": "Commercial Axes inherits FAR from the officially verified surrounding zone. Select that surrounding zone before SiteIQ can look up FAR.", "matched_rule": None, "candidate_rules": [], "maximum_far": None}
        inherited = match_far_rule(profile, surrounding_zone, site_area_m2, road_width_m, proposed_use=proposed_use)
        inherited["inherited_from_zone"] = surrounding_zone
        inherited["category"] = cat.get("label")
        inherited["table"] = cat.get("table") + f" (inherits {surrounding_zone})"
        inherited["conditions"] = cat.get("conditions", []) + inherited.get("conditions", [])
        inherited["far_interpretation"] = cat.get("far_interpretation", "") + " Selected FAR inherited from the chosen surrounding zone."
        return inherited

    matched_rows = []
    far_value = None
    details: dict = {}
    message = ""
    if method == "area_cap_and_road_width":
        area_rows = _find_band(cat.get("plot_area_far_caps", []), site_area_m2)
        road_rows = _find_band(cat.get("road_far_bands", []), road_width_m)
        if len(area_rows) == 1 and len(road_rows) == 1:
            area_far = float(area_rows[0]["far"])
            road_far = float(road_rows[0]["far"])
            far_value = min(area_far, road_far)
            matched_rows = [area_rows[0], road_rows[0]]
            details = {"plot_area_far_cap": area_far, "road_width_far": road_far, "limiting_factor": "road width" if road_far <= area_far else "plot area"}
            message = f"The table's road-width FAR is {road_far:.2f}; the plot-area FAR cap is {area_far:.2f}. SiteIQ uses the lower value, {far_value:.2f}, following the source's road-width and plot-area limit notes. Confirm the zone and operative table before design freeze."
        else:
            reasons = []
            if len(area_rows) != 1: reasons.append("plot area did not match exactly one configured FAR cap band")
            if len(road_rows) != 1: reasons.append("road width did not match exactly one configured FAR band")
            return {**base, "status": "no_matching_far_band", "message": "SiteIQ could not identify a unique FAR band: " + "; ".join(reasons) + ". No interpolation or nearest-band guess was used.", "matched_rule": None, "candidate_rules": area_rows + road_rows, "maximum_far": None}
    elif method == "road_width":
        rows = _find_band(cat.get("road_far_bands", []), road_width_m)
        if len(rows) != 1:
            return {**base, "status": "no_matching_far_band", "message": "The road width does not match exactly one configured FAR band. Check the table wording and ask the authority to resolve any boundary gap.", "matched_rule": None, "candidate_rules": rows, "maximum_far": None}
        far_value = float(rows[0]["far"])
        matched_rows = rows
        details = {"road_width_far": far_value, "limiting_factor": "road width"}
        message = f"The selected table gives FAR {far_value:.2f} for the entered road-width band, within the table's configured plot-area scope. Confirm the zone and current operative table."
    elif method == "plot_area":
        rows = _find_band(cat.get("plot_area_far_caps", []), site_area_m2)
        if len(rows) != 1:
            return {**base, "status": "no_matching_far_band", "message": "Plot area does not match exactly one configured FAR band. No interpolation was used.", "matched_rule": None, "candidate_rules": rows, "maximum_far": None}
        row_min_road = rows[0].get("min_road_width_m")
        if row_min_road is not None and road_width_m < float(row_min_road):
            return {**base, "status": "minimum_road_width_not_met", "message": f"The matched plot-area row requires a minimum road width of {float(row_min_road):g} m; entered road width is {road_width_m:g} m. No FAR has been assigned.", "matched_rule": None, "candidate_rules": rows, "maximum_far": None}
        far_value = float(rows[0]["far"])
        matched_rows = rows
        details = {"plot_area_far": far_value, "limiting_factor": "plot area", "minimum_road_width_m": row_min_road}
        message = f"The selected table gives FAR {far_value:.2f} for the entered plot-area band. Road-width or special-use restrictions outside this table may still apply."
    elif method == "fixed":
        far_value = float(cat["fixed_far"])
        details = {"fixed_far": far_value}
        message = f"The selected table states maximum FAR {far_value:.2f}. Confirm that the site is officially within this category and that no other provision limits it."
    else:
        return {**base, "status": "rule_method_not_configured", "message": f"The FAR method '{method}' is not implemented. SiteIQ did not infer a result.", "matched_rule": None, "candidate_rules": [], "maximum_far": None}

    area_basis = cat.get("far_area_basis", {"type": "gross_site_area"}) or {"type": "gross_site_area"}
    calculation_area = float(site_area_m2)
    deduction_pct = 0.0
    if area_basis.get("type") == "net_after_deduction_pct":
        deduction_pct = float(area_basis.get("deduct_pct", 0) or 0)
        calculation_area = float(site_area_m2) * (1.0 - deduction_pct / 100.0)
        details.update({
            "gross_site_area_m2": round(float(site_area_m2), 2),
            "far_calculation_area_m2": round(calculation_area, 2),
            "excluded_area_m2": round(float(site_area_m2) - calculation_area, 2),
            "deduction_pct": deduction_pct,
            "area_basis_note": area_basis.get("reason", "FAR uses the net site area as configured in the selected table."),
        })
        message += f" FAR capacity is calculated on {calculation_area:,.2f} m² after the configured {deduction_pct:g}% deduction; verify that the stated deduction and reservation basis match the operative plan."
    capacity = calculation_area * float(far_value)
    matched = {
        "id": cat.get("key"), "far": float(far_value), "maximum_far": float(far_value),
        "area_capacity_m2": round(capacity, 2), "table": cat.get("table"),
        "source_id": cat.get("source_id"), "details": details,
        "matched_bands": matched_rows, "gross_site_area_m2": round(float(site_area_m2), 2),
        "far_calculation_area_m2": round(calculation_area, 2), "far_area_basis": area_basis,
        "conditional_path_id": cat.get("conditional_path_id"),
    }
    result = {**base, "status": "candidate_match_requires_verification", "message": message, "matched_rule": matched, "candidate_rules": matched_rows, "maximum_far": float(far_value), "maximum_far_area_m2": round(capacity, 2), "far_calculation_area_m2": round(calculation_area, 2), "source": source}
    premium = calculate_premium_far_opportunity(profile, result, site_area_m2, road_width_m)
    if premium:
        result["premium_far"] = premium
    return result



def calculate_premium_far_opportunity(profile: dict, far_result: dict, site_area_m2: float, road_width_m: float) -> dict | None:
    """Return a separate premium-FAR scenario ceiling when a profile has a configured rule.

    This is deliberately excluded from the base FAR benchmark; fees, site eligibility,
    precise Table 27 bands and premium/TDR mix are not automated in this MVP.
    """
    rule = (profile or {}).get("premium_far_rule") or {}
    if not rule.get("enabled_for_scenario_only") or far_result.get("maximum_far") is None:
        return None
    min_road = float(rule.get("minimum_road_width_m", 9.0))
    mix_min_road = float(rule.get("mixed_premium_tdr_min_road_width_m", 12.0))
    base_far = float(far_result["maximum_far"])
    calc_area = float(far_result.get("far_calculation_area_m2", site_area_m2))
    factor = float(rule.get("max_additional_far_factor", 0.6))
    if road_width_m < min_road:
        return {"status":"road_width_below_configured_threshold", "message":f"The configured optional Premium FAR/TDR opportunity starts at {min_road:g} m road width. This site is below that threshold.", "base_far":base_far, "additional_far_factor":factor, "source":source_by_id(profile, rule.get("source_id"))}
    additional_far = base_far * factor
    if road_width_m < mix_min_road:
        return {
            "status":"tdr_only_candidate", "base_far":base_far,
            "maximum_additional_far_factor":factor, "additional_far_candidate":round(additional_far,3),
            "additional_floor_area_candidate_m2":round(calc_area * additional_far,2),
            "potential_total_far_candidate":round(base_far + additional_far,3),
            "potential_total_floor_area_candidate_m2":round(calc_area * (base_far + additional_far),2),
            "message":f"Optional additional FAR up to {factor:.1f}× base FAR may require TDR only at this road width. It is not included in the base benchmark and is not an entitlement; verify the operative notification and eligibility.",
            "conditions":rule.get("conditions",[]), "source":source_by_id(profile, rule.get("source_id"))
        }
    return {
        "status":"premium_far_plus_tdr_candidate", "base_far":base_far,
        "maximum_additional_far_factor":factor, "additional_far_candidate":round(additional_far,3),
        "additional_floor_area_candidate_m2":round(calc_area * additional_far,2),
        "potential_total_far_candidate":round(base_far + additional_far,3),
        "potential_total_floor_area_candidate_m2":round(calc_area * (base_far + additional_far),2),
        "message":f"Optional additional FAR up to {factor:.1f}× base FAR may be available through a Premium FAR/TDR combination under the cited scheme. This is not included in the base benchmark and is not an entitlement; charges, mix and eligibility are not calculated.",
        "conditions":rule.get("conditions",[]), "source":source_by_id(profile, rule.get("source_id"))
    }


def source_by_id(profile: Optional[dict], source_id: Optional[str]) -> Optional[dict]:
    if not profile or not source_id:
        return None
    for source in profile.get("sources", []):
        if source.get("id") == source_id:
            return source
    return None


def _nominal_table8_for_area(profile: dict, site_area_m2: float, frontage_m: Optional[float], depth_m: Optional[float]) -> dict:
    bands = profile.get("setback_table8_area_bands", [])
    matches = [b for b in bands if _matches_band(site_area_m2, {
        "min": b.get("site_area_min", 0), "max": b.get("site_area_max"),
        "min_exclusive": b.get("min_exclusive", False), "max_exclusive": b.get("max_exclusive", False)
    })]
    if len(matches) != 1:
        return {"status":"rule_not_configured_for_area", "message":"No unique Table 8 area band is configured for the entered plot area.", "front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None}
    band = matches[0]
    src = source_by_id(profile, band.get("source_id") or profile.get("setback_table8_source_id") or "udd235_setbacks")
    if band.get("all_round_m") is not None:
        d=float(band["all_round_m"])
        return {"status":"nominal_height_band_requires_authority_check","message":band.get("note","Minimum all-round setback from supplied Table 8."),"front_m":d,"rear_m":d,"left_m":d,"right_m":d,"all_round_m":d,"basis":band.get("note"),"source":src}
    if band.get("front_pct_of_depth") is not None:
        if not frontage_m or not depth_m or frontage_m <= 0 or depth_m <= 0:
            return {"status":"missing_inputs","message":"Frontage and depth are needed for a nominal Table 8 percentage check; imported site geometry is still required for the true boundary offset.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":src}
        return {"status":"nominal_calculation_requires_site_geometry_check","message":band.get("note","Table 8 percentage distances from nominal dimensions."),"front_m":round(depth_m*band['front_pct_of_depth']/100,2),"rear_m":round(depth_m*band['rear_pct_of_depth']/100,2),"left_m":round(frontage_m*band['left_pct_of_width']/100,2),"right_m":round(frontage_m*band['right_pct_of_width']/100,2),"all_round_m":None,"basis":band.get("note"),"source":src}
    if band.get("side_m") is not None and band.get("left_m") is None:
        # The source says 
        # This table band permits the side distance on any one side only; don't pick the side automatically.
        return {"status":"side_selection_required","message":band.get("note","Table 8 requires a setback on any one side in this area band."),"front_m":band.get("front_m"),"rear_m":band.get("rear_m"),"left_m":None,"right_m":None,"side_any_one_m":band.get("side_m"),"all_round_m":None,"basis":band.get("note"),"source":src}
    return {"status":"candidate_match_requires_verification","message":band.get("note","Table 8 nominal distances."),"front_m":band.get("front_m"),"rear_m":band.get("rear_m"),"left_m":band.get("left_m"),"right_m":band.get("right_m"),"all_round_m":None,"basis":band.get("note"),"source":src}


def calculate_setbacks(profile: Optional[dict], site_area_m2: float, frontage_m: Optional[float], depth_m: Optional[float], height_for_setback_m: Optional[float], stilt: bool, zone: str | None = None) -> dict:
    """Select building setbacks from the configured zone-specific rule path."""
    if not profile:
        return {"status":"not_configured","message":"No authority-specific setback rules are configured.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":None}
    if height_for_setback_m is None or float(height_for_setback_m) <= 0:
        return {"status":"missing_inputs","message":"Enter building height for setback-table selection.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":None}
    cat = category_by_label(profile, zone) if zone else None
    if cat and cat.get("setback_method") == "authority_decided":
        return {"status":"authority_decision_required","message":"The selected land-use category does not have a generic setback value in the configured source. Obtain the authority-specific setback requirement.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":source_by_id(profile,cat.get('source_id'))}
    if cat and cat.get("setback_method") == "industrial_table16":
        matches = [b for b in cat.get("industrial_setbacks",[]) if _matches_band(site_area_m2,b)]
        if len(matches) != 1:
            return {"status":"rule_not_configured_for_area","message":"No unique Industrial (General) Table 16 setback band matched the site area.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":source_by_id(profile,cat.get('source_id'))}
        row = matches[0]
        if str(row.get('front','')).startswith('12%'):
            if not frontage_m or not depth_m:
                return {"status":"missing_inputs","message":"Table 16 setback percentages need nominal frontage/depth; use surveyed geometry for the true boundary envelope.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":source_by_id(profile,cat.get('source_id'))}
            values = {'front_m': round(depth_m*.12,2), 'rear_m': round(depth_m*.08,2), 'left_m': round(frontage_m*.08,2), 'right_m': round(frontage_m*.08,2)}
        else:
            fv = float(row['front'].split()[0]); rv = float(row['rear_side'].split()[0])
            values = {'front_m':fv,'rear_m':rv,'left_m':rv,'right_m':rv}
        height_note = "Table 16 special setback selected by plot area. For height above 12 m, confirm its interaction with general Table 9 and any special conditions before relying on it." if height_for_setback_m > 12 else "Table 16 special setback selected by plot area; confirm remaining conditions in the operative rule."
        return {"status":"special_table16_requires_verification","message":height_note,"basis":row,"all_round_m":None,**values,"source":source_by_id(profile,cat.get('source_id'))}

    # Authority profiles may use different cut-off heights for their own setback tables.
    table8_max = float(profile.get("setback_table8_max_height_m", 12.0))
    if height_for_setback_m <= table8_max:
        return _nominal_table8_for_area(profile, site_area_m2, frontage_m, depth_m)

    src = source_by_id(profile, profile.get("setback_height_source_id") or 'udd235_setbacks')
    for band in profile.get('setback_table9_height_bands', []):
        hmin = band['height_min_exclusive']; hmax = band.get('height_max')
        if not (height_for_setback_m > hmin and (hmax is None or height_for_setback_m <= hmax)):
            continue
        if 'stilt' in band and bool(band['stilt']) != bool(stilt):
            continue
        # For plots above 4,000 m², Table 8/9 requires a 5 m minimum all-round setback
        # in the configured amendment for these height bands.
        if site_area_m2 > 4000 and profile.get("force_minimum_all_round_for_area_above_4000", True):
            d = float(band.get('all_round_m', 5.0))
            return {"status":"nominal_height_band_requires_authority_check","message":"Minimum all-round setback for the selected height and plot-area band; confirm current operative row and height definition.","front_m":d,"rear_m":d,"left_m":d,"right_m":d,"all_round_m":d,"basis":band.get('note','Table 9 height band'),"source":src}
        if 'all_round_m' in band:
            d = float(band['all_round_m'])
            return {"status":"nominal_height_band_requires_authority_check","message":band.get('note','All-round setback from supplied Table 9; confirm exact height definition and applicable row.'),"front_m":d,"rear_m":d,"left_m":d,"right_m":d,"all_round_m":d,"basis":band.get('note','Table 9 all-round setback'),"source":src}
        if 'front_min_m' in band:
            t8 = _nominal_table8_for_area(profile, site_area_m2, frontage_m, depth_m)
            if any(t8.get(k) is None for k in ('front_m','rear_m','left_m','right_m')):
                return {"status":"incomplete_table8_values","message":"The stilt-specific Table 9 row needs Table 8 distances, but those could not be uniquely calculated. Confirm with the authority.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":src}
            vals = {'front_m':max(float(band['front_min_m']),float(t8['front_m'])),'rear_m':max(float(band['rear_min_m']),float(t8['rear_m'])),'left_m':max(float(band['side_min_m']),float(t8['left_m'])),'right_m':max(float(band['side_min_m']),float(t8['right_m']))}
            return {"status":"nominal_calculation_requires_height_definition_check","message":band.get('note','Use the greater of Table 9 minimum and Table 8 distance.'),**{k:round(v,2) for k,v in vals.items()},"all_round_m":None,"basis":band.get('note','Table 9 stilt provision compared with Table 8'),"source":src}
    return {"status":"rule_not_configured_for_height","message":"No configured Table 9 height/stilt row matched. Verify the current table and height definition.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":src}


def calculate_basement_setbacks(profile: Optional[dict], zone: str, site_area_m2: float, building_setbacks: dict, basement_levels: int, manual_front_m: float | None = None, manual_nonfront_m: float | None = None) -> dict:
    """Calculate a preliminary basement setback from the supplied amendment or flag uncertainty."""
    if int(basement_levels or 0) <= 0:
        return {"status":"no_basement","message":"No basement selected for this option.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":0,"source":None}
    if manual_front_m is not None and manual_nonfront_m is not None and manual_front_m > 0 and manual_nonfront_m > 0:
        return {"status":"manual_scenario_not_rule_result","message":"Manual basement setbacks are scenario inputs only, not a statement of the required basement setback.","front_m":float(manual_front_m),"rear_m":float(manual_nonfront_m),"left_m":float(manual_nonfront_m),"right_m":float(manual_nonfront_m),"all_round_m":None,"levels":int(basement_levels),"source":None}
    if not profile:
        return {"status":"not_configured","message":"No authority-specific basement setback rule is configured.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":int(basement_levels),"source":None}
    cat = category_by_label(profile, zone)
    if site_area_m2 <= 4000:
        if cat and cat.get('setback_method') != 'table8_9':
            return {"status":"special_zone_needs_confirmation","message":"The configured basement provision refers to building setbacks under Table 8/9. This category uses a special setback path, so SiteIQ has not auto-applied the general basement rule.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":int(basement_levels),"source":source_by_id(profile,'udd235_setbacks')}
        b = profile.get('basement_setback_rule', {}).get('up_to_4000', {})
        if not b:
            return {"status":"rule_not_configured_for_area","message":"No authority-specific basement setback rule is configured for this plot-area band. SiteIQ will not reuse another authority's basement rules.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":int(basement_levels),"source":None}
        if any(building_setbacks.get(k) is None for k in ('front_m','rear_m','left_m','right_m')):
            return {"status":"building_setback_required","message":"Basement setback depends on the option's building setback under Table 8/9. Resolve building setbacks and identify the road-facing edge(s) first.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":int(basement_levels),"source":source_by_id(profile,b.get('source_id'))}
        lim = float(b.get('other_sides_max_m',2.0))
        front = float(building_setbacks['front_m'])
        rear = min(float(building_setbacks['rear_m']),lim)
        left = min(float(building_setbacks['left_m']),lim)
        right = min(float(building_setbacks['right_m']),lim)
        if building_setbacks.get('all_round_m') is not None:
            d = float(building_setbacks['all_round_m'])
            front, rear, left, right = d, min(d,lim), min(d,lim), min(d,lim)
        return {"status":"candidate_match_requires_authority_check","message":b.get('logic',''),"front_m":front,"rear_m":rear,"left_m":left,"right_m":right,"all_round_m":None,"levels":int(basement_levels),"basis":"Road-facing edge retains the building setback; non-road sides may use the lesser of building setback or 2.0 m under the supplied basement amendment.","source":source_by_id(profile,b.get('source_id'))}
    for row in profile.get('basement_setback_rule', {}).get('above_4000', []):
        if _matches_band(site_area_m2, {'min':row['min_area_exclusive'],'max':row.get('max_area'),'min_exclusive':True}):
            d = float(row['setback_m'])
            return {"status":"candidate_match_requires_authority_check","message":"Minimum basement setback selected by the site's area band from the supplied amendment; verify scope and current operative provisions.","front_m":d,"rear_m":d,"left_m":d,"right_m":d,"all_round_m":d,"levels":int(basement_levels),"basis":f"Minimum {d:.2f} m basement setback for this site-area band.","source":source_by_id(profile,row.get('source_id'))}
    return {"status":"rule_not_configured_for_area","message":"No basement setback band is configured for this site area.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"levels":int(basement_levels),"source":None}


def calculate_rectangular_proxy(site: dict, setbacks: dict) -> dict:
    """Compute a simple inner rectangle only when user explicitly requests a proxy.

    This is not a true geometry operation and must never be described as the legal
    buildable polygon, particularly when the uploaded/site boundary is irregular.
    """
    mode = site.get("geometry_mode", "")
    frontage = site.get("frontage_m")
    depth = site.get("depth_m")
    if not mode.startswith("Rectangular proxy"):
        return {"status":"not_requested", "area_m2":None, "width_m":None, "depth_m":None, "message":"No rectangular proxy requested; SiteIQ does not compute the true buildable polygon in this MVP."}
    if frontage is None or depth is None:
        return {"status":"missing_dimensions", "area_m2":None, "width_m":None, "depth_m":None, "message":"Frontage and depth are required to calculate a rectangular proxy."}
    if any(setbacks.get(k) is None for k in ("front_m", "rear_m", "left_m", "right_m")):
        return {"status":"setbacks_unavailable", "area_m2":None, "width_m":None, "depth_m":None, "message":"A rectangular proxy cannot be calculated until all four nominal setback distances are available."}
    inner_width = max(0.0, float(frontage) - float(setbacks["left_m"]) - float(setbacks["right_m"]))
    inner_depth = max(0.0, float(depth) - float(setbacks["front_m"]) - float(setbacks["rear_m"]))
    area = round(inner_width * inner_depth, 2)
    irregular = str(site.get("shape_type", "")).lower().startswith("irregular")
    message = "Rectangular proxy only; not a statutory ground-coverage limit or a true buildable polygon."
    if irregular:
        message += " The site is marked irregular, so this rectangular proxy must not be used for setting out or sanction drawings."
    return {
        "status":"indicative_rectangular_proxy_only",
        "area_m2":area,
        "width_m":round(inner_width,2),
        "depth_m":round(inner_depth,2),
        "message":message,
    }

def build_scenarios(site_area_m2: float, scenarios: List[dict], max_far_benchmark: float | None = None, max_far_capacity_m2: float | None = None, far_calculation_area_m2: float | None = None) -> List[dict]:
    """Calculate gross scenario yields against a rule-derived FAR benchmark only.

    A user-entered legacy assumed_far value is ignored unless the site explicitly sets
    manual_benchmark_far; this prevents an assumed FAR from masquerading as the regulatory
    maximum.
    """
    output: List[dict] = []
    for idx, s in enumerate(scenarios, 1):
        name = s.get("name") or f"Option {idx}"
        footprint = s.get("footprint_m2")
        floors = s.get("floors")
        height = s.get("height_m")
        gross_concept_area = None
        achieved_far = None
        far_capacity = None
        headroom = None
        scenario_far_area = float(far_calculation_area_m2) if far_calculation_area_m2 is not None and float(far_calculation_area_m2) > 0 else float(site_area_m2)
        far_ratio_basis = "net FAR calculation area after configured reservation/deduction" if abs(scenario_far_area - float(site_area_m2)) > 0.01 else "gross site area"
        benchmark = float(max_far_benchmark) if max_far_benchmark is not None and float(max_far_benchmark) > 0 else None
        benchmark_source = "configured rule lookup" if benchmark is not None else "unresolved"
        if benchmark is None and s.get("manual_benchmark_far") is not None and float(s.get("manual_benchmark_far") or 0) > 0:
            benchmark = float(s["manual_benchmark_far"])
            benchmark_source = "user-entered what-if only; not statutory"
        if footprint is not None and floors is not None and float(footprint) > 0 and int(floors) > 0:
            gross_concept_area = round(float(footprint) * int(floors), 2)
            achieved_far = round(gross_concept_area / scenario_far_area, 3) if scenario_far_area > 0 else None
        if benchmark is not None:
            far_capacity = round(float(max_far_capacity_m2), 2) if max_far_capacity_m2 is not None else round(site_area_m2 * benchmark, 2)
            if gross_concept_area is not None:
                headroom = round(far_capacity - gross_concept_area, 2)
        output.append({
            "name": name,
            "height_m": float(height) if height not in (None, "") else None,
            "floors": int(floors) if floors not in (None, "") else None,
            "footprint_m2": round(float(footprint), 2) if footprint not in (None, "") and float(footprint) > 0 else None,
            "benchmark_far": benchmark,
            "benchmark_source": benchmark_source,
            "assumed_far": None,
            "stilt": bool(s.get("stilt", False)),
            "basement_levels": int(s.get("basement_levels", 0) or 0),
            "setback_mode": s.get("setback_mode", "automatic"),
            "manual_all_round_setback_m": s.get("manual_all_round_setback_m"),
            "basement_setback_mode": s.get("basement_setback_mode", "automatic"),
            "manual_basement_front_m": s.get("manual_basement_front_m"),
            "manual_basement_nonfront_m": s.get("manual_basement_nonfront_m"),
            "far_capacity_m2": far_capacity,
            "far_calculation_area_m2": round(scenario_far_area, 2),
            "far_ratio_basis": far_ratio_basis,
            "gross_concept_area_m2": gross_concept_area,
            # Keep legacy key for older templates; reports label the denominator correctly.
            "achieved_gross_far_ratio": achieved_far,
            "achieved_far_ratio": achieved_far,
            "scenario_headroom_m2": headroom,
            "interpretation": "Gross arithmetic proxy for the above-ground concept only. FAR exclusions, basements, floor-by-floor variations and sanction conditions are not modelled.",
        })
    return output


def _manual_all_round_setback(distance: float | None) -> dict:
    if distance is None or float(distance) <= 0:
        return {"status":"manual_setback_missing","message":"Enter a positive manual setback or select the configured rule path.","front_m":None,"rear_m":None,"left_m":None,"right_m":None,"all_round_m":None,"source":None}
    d=float(distance)
    return {"status":"manual_scenario_not_rule_result","message":"A uniform setback entered for option testing only; it is not a confirmed statutory requirement.","front_m":d,"rear_m":d,"left_m":d,"right_m":d,"all_round_m":d,"basis":"Manual uniform what-if scenario","source":None}


def build_report(site: dict, registry: Optional[dict] = None, profile: Optional[dict] = None) -> dict:
    registry = registry or load_authority_registry()
    authority = find_authority(registry, site["authority_key"])
    if profile is None and authority.get("rule_profile"):
        profile = load_rule_profile(authority["rule_profile"])

    site_area = float(site["site_area_m2"])
    road_width = float(site["road_width_m"])
    # The selected regulatory land-use category is distinct from an auto-identified official map zone.
    selected_zone = site.get("land_use_category") or site.get("zone", "Not verified")
    official_zone = site.get("official_zone", site.get("zone", "Not verified"))
    far_result = match_far_rule(profile, selected_zone, site_area, road_width, surrounding_zone=site.get("surrounding_zone"), proposed_use=site.get("proposed_use"))
    max_far_benchmark = far_result.get("maximum_far") if far_result.get("status") == "candidate_match_requires_verification" else None
    max_far_capacity = far_result.get("maximum_far_area_m2") if max_far_benchmark is not None else None
    far_calculation_area = far_result.get("far_calculation_area_m2", site_area) if max_far_benchmark is not None else site_area
    setback_result = calculate_setbacks(
        profile, site_area, site.get("frontage_m"), site.get("depth_m"),
        site.get("height_for_setback_m"), bool(site.get("stilt", False)), zone=selected_zone,
    )
    envelope_result = calculate_rectangular_proxy(site, setback_result)

    scenario_inputs = []
    for raw_scenario in site.get("scenarios", []):
        normalized = dict(raw_scenario)
        normalized.setdefault("stilt", bool(site.get("stilt", False)))
        if normalized.get("setback_mode") == "manual":
            option_setbacks = _manual_all_round_setback(normalized.get("manual_all_round_setback_m"))
        else:
            option_setbacks = calculate_setbacks(
                profile, site_area, site.get("frontage_m"), site.get("depth_m"),
                normalized.get("height_m"), bool(normalized.get("stilt", False)), zone=selected_zone,
            )
        normalized["setback_result"] = option_setbacks
        normalized["setback_status"] = option_setbacks.get("status", "not_configured")
        if option_setbacks.get("all_round_m") is not None:
            d=float(option_setbacks["all_round_m"])
            normalized["setback_summary"] = f"{d:.2f} m all sides"
        elif all(option_setbacks.get(k) is not None for k in ("front_m","rear_m","left_m","right_m")):
            normalized["setback_summary"] = f"Front {option_setbacks['front_m']:.2f} / Rear {option_setbacks['rear_m']:.2f} / Sides {option_setbacks['left_m']:.2f}, {option_setbacks['right_m']:.2f} m"
        else:
            normalized["setback_summary"] = "Not determined"
        basement_levels = int(normalized.get("basement_levels", 0) or 0)
        if normalized.get("basement_setback_mode") == "manual":
            bfront=normalized.get("manual_basement_front_m")
            bother=normalized.get("manual_basement_nonfront_m")
            basement_setbacks = calculate_basement_setbacks(profile, selected_zone, site_area, option_setbacks, basement_levels, bfront, bother)
        else:
            basement_setbacks = calculate_basement_setbacks(profile, selected_zone, site_area, option_setbacks, basement_levels)
        normalized["basement_setback_result"] = basement_setbacks
        normalized["basement_setback_status"] = basement_setbacks.get("status", "not_configured")
        if basement_setbacks.get("status") == "no_basement":
            normalized["basement_setback_summary"] = "No basement"
        elif basement_setbacks.get("all_round_m") is not None:
            normalized["basement_setback_summary"] = f"{float(basement_setbacks['all_round_m']):.2f} m all sides"
        elif all(basement_setbacks.get(k) is not None for k in ("front_m","rear_m","left_m","right_m")):
            normalized["basement_setback_summary"] = f"Front {basement_setbacks['front_m']:.2f} / Rear {basement_setbacks['rear_m']:.2f} / Sides {basement_setbacks['left_m']:.2f}, {basement_setbacks['right_m']:.2f} m"
        else:
            normalized["basement_setback_summary"] = "Not determined"
        scenario_inputs.append(normalized)

    scenarios = build_scenarios(site_area, scenario_inputs, max_far_benchmark=max_far_benchmark, max_far_capacity_m2=max_far_capacity, far_calculation_area_m2=far_calculation_area)
    if max_far_benchmark is not None and far_result.get("rule_source_quality") == "secondary_copy_pending_official_validation":
        for item in scenarios:
            item["benchmark_source"] = "provisional secondary-source rule candidate; official applicability pending"
    for out_scenario, raw in zip(scenarios, scenario_inputs):
        for key in ("setback_result","setback_status","setback_summary","basement_setback_result","basement_setback_status","basement_setback_summary","setback_mode","manual_all_round_setback_m","basement_setback_mode","manual_basement_front_m","manual_basement_nonfront_m"):
            out_scenario[key] = raw.get(key)
        out_scenario["setback_basis"] = (out_scenario.get("setback_result") or {}).get("basis") or (out_scenario.get("setback_result") or {}).get("message") or "No configured setback basis."

    implied_rect_area = None
    dimension_difference_pct = None
    if site.get("frontage_m") and site.get("depth_m"):
        implied_rect_area = float(site["frontage_m"]) * float(site["depth_m"])
        dimension_difference_pct = round(abs(implied_rect_area - site_area) / site_area * 100, 2) if site_area else None

    single_plot = None
    if profile and profile.get("single_plot_chapter_6a"):
        rule = profile["single_plot_chapter_6a"]
        if rule["trigger_min_exclusive_sq_m"] < site_area <= rule["trigger_max_sq_m"]:
            approval_path = (site.get("approval_path") or "").lower()
            explicitly_new_single_plot = "new single-plot approval" in approval_path
            single_plot = {
                "status": "conditional_check" if explicitly_new_single_plot else "applicability_needs_confirmation",
                "park_option_m2": round(site_area * rule["park_reservation_pct"] / 100, 2),
                "guidance_value_charge_pct": rule["alternative_guidance_value_charge_pct"],
                "message": rule["condition"] + (" The user selected a new single-plot Chapter 6-A route; verify the route and exemptions." if explicitly_new_single_plot else " Approval route is not confirmed as a new Chapter 6-A single-plot approval; this percentage is an indicative check only."),
                "source": source_by_id(profile, rule["source_id"]),
            }
        else:
            single_plot = {"status": "not_in_configured_area_band", "message": "This MVP's Chapter 6-A note is configured only for the greater-than-2,000 m² up-to-4,000 m² band."}

    fire_rule = profile.get("fire_noc_trigger") if profile else None
    proposed_heights = [s.get("height_m") for s in site.get("scenarios", []) if s.get("height_m") not in (None, "")]
    maximum_height = max([float(h) for h in proposed_heights], default=site.get("height_for_setback_m"))
    fire_check = {"status": "not_configured", "message": "Authority-specific fire review remains pending."}
    if fire_rule and maximum_height is not None:
        fire_check = {"status": "triggered_by_height_scenario" if float(maximum_height) >= fire_rule["height_min_m_inclusive"] else "below_configured_high_rise_threshold", "threshold_m": fire_rule["height_min_m_inclusive"], "maximum_scenario_height_m": float(maximum_height), "message": fire_rule["condition"], "source": source_by_id(profile, fire_rule["source_id"])}

    checks = [
        {"item":"Planning jurisdiction and boundary", "status":"pending_confirmation", "note":"Map pin does not establish the notified planning boundary or sanctioning authority."},
        {"item":"Official land-use zone / selected rule category", "status":"pending_confirmation", "note":"Confirm the official land-use classification against the relevant notified map. The selected category drives this FAR lookup."},
        {"item":"Maximum FAR lookup", "status":far_result["status"], "note":far_result["message"]},
        {"item":"Survey geometry / boundary", "status":"pending_confirmation", "note":"Irregular site boundaries need an authenticated survey and CAD-reviewed setback envelope."},
        {"item":"Building and basement setbacks", "status":"calculated_candidate" if any(s.get('setback_result',{}).get('front_m') is not None for s in scenarios) else "pending_confirmation", "note":"Compare the selected rule and each option's building and basement setbacks; special geometry and frontage remain to be checked."},
        {"item":"Lake, drain, HT line, road widening and other overlays", "status":"pending_confirmation", "note":"Official overlay checks have not been performed by this offline MVP."},
        {"item":"Parking, accessibility, structure and services", "status":"pending_design", "note":"Requires unit schedule, design strategy and authority/consultant coordination."},
        {"item":"Fire NOC trigger", "status":fire_check.get("status", "not_configured"), "note":fire_check.get("message", "Confirm with the relevant fire authority.")},
    ]
    sources = (profile or {}).get("sources", [])
    report = {
        "application": {"name":"SiteIQ", "version":"0.4.7", "assessment_date":date.today().isoformat(), "profile_status":(profile or {}).get("profile_status", "not configured")},
        "project": site.get("project_name") or "Untitled Site Feasibility",
        "client": site.get("client") or "Not supplied",
        "site": {
            "address": site.get("address") or "Not supplied", "map_url": site.get("map_url") or "", "coordinates": site.get("coordinates") or "",
            "authority": authority["name"], "authority_status": authority.get("status"), "authority_scope_note": authority.get("scope_note"),
            "rule_profile": (profile or {}).get("profile_name", "No rules configured for selected authority"),
            "site_area_m2": site_area, "site_area_source": site.get("site_area_source", "user-entered"), "road_width_m": road_width,
            "frontage_m": site.get("frontage_m"), "depth_m": site.get("depth_m"), "shape_type": site.get("shape_type", "unknown"),
            "geometry_mode": site.get("geometry_mode", "no_envelope"), "proposed_use": site.get("proposed_use", "Not supplied"),
            "zone": selected_zone, "land_use_category": selected_zone, "official_zone": official_zone, "surrounding_zone": site.get("surrounding_zone"),
            "approval_path": site.get("approval_path", "Not confirmed"), "height_for_setback_m": site.get("height_for_setback_m"),
            "stilt": bool(site.get("stilt", False)), "basement": site.get("basement", "Not decided"),
            "implied_rectangular_area_m2": round(implied_rect_area,2) if implied_rect_area is not None else None,
            "dimension_difference_pct": dimension_difference_pct,
        },
        "far": far_result, "maximum_far": max_far_benchmark, "maximum_far_area_m2": round(max_far_capacity,2) if max_far_capacity is not None else None,
        "setbacks": setback_result, "envelope": envelope_result, "single_plot": single_plot, "fire": fire_check,
        "scenarios": scenarios, "checks": checks, "sources": sources, "authority_sources": authority.get("sources", []),
        "land_use_categories": [{"key":c.get("key"),"label":c.get("label"),"table":c.get("table"),"method":c.get("method")} for c in land_use_categories(profile)],
        "limits": [
            "This is an early-stage feasibility aid, not sanction advice or a legal opinion.",
            "Bengaluru RMP 2015 has a partial configured profile. Hoskote, Kanakapura, Nelamangala and Anekal use provisional FAR candidate profiles transcribed from secondary Master Plan 2031 copies; operative notification, amendments, zoning and authority coverage require confirmation. Other authority profiles remain unconfigured.",
            "A rule-based FAR is a candidate from the configured source, not a sanctioned entitlement. Confirm the exact authority, official land-use classification, notification validity and applicable conditions.",
            "SiteIQ can use a validated imported boundary area and calculate preliminary envelopes. Complex concave geometry, frontage-specific interpretations and all statutory overlays still need architect/authority review.",
            "Gross area is footprint times above-ground floor count; FAR exclusions, ancillary areas, floor-by-floor variations, parking, structure and service constraints are not fully modelled.",
        ]
    }
    return report


def report_to_plain_dict(report: dict) -> dict:
    """Kept as a stable seam if future dataclasses/models are added."""
    return report
