"""Which site inputs matter for a given authority, category, use and road.

The interface hides the rest, and the assessment ignores them, so a value left over from
an earlier choice can never change a result.
"""
from __future__ import annotations

from typing import Optional

HOUSING_FOR_SALE = {"Residential apartments"}
UNITS_FOR_SALE = {"Residential apartments", "Mixed use", "Commercial / office"}


def relevant_inputs(profile: Optional[dict], category: Optional[str], use: Optional[str], road_width_m: Optional[float]) -> dict:
    """Return each optional input with whether it is used, a label and the reason."""
    profile = profile or {}
    out: dict[str, dict] = {}
    if use in UNITS_FOR_SALE:
        label = "Dwelling units" if use in HOUSING_FOR_SALE else "Units for sale"
        uses = ["RERA registration"] + (["apartment rules", "parking"] if use in HOUSING_FOR_SALE else [])
        out["dwelling_units"] = {"relevant": True, "label": label, "reason": "Used for " + ", ".join(uses) + "."}
    else:
        out["dwelling_units"] = {"relevant": False, "label": "Dwelling units", "reason": f"Not used for {use or 'this use'}."}
    multi = (profile.get("parking_rule") or {}).get("multi_dwelling") or {}
    used = use in multi.get("uses", [])
    out["average_unit_area_m2"] = {"relevant": used, "label": "Average unit area",
                                   "reason": "Used for the parking table." if used else "Only used for apartment parking where a parking table is configured."}
    rings = profile.get("apartment_rules") or {}
    ring_used = bool(rings.get("bands")) and category in rings.get("categories", []) and use in HOUSING_FOR_SALE
    out["rmp_ring"] = {"relevant": ring_used, "label": "RMP ring",
                       "reason": "Apartment rules differ by ring." if ring_used else "Only used for apartments under the Bengaluru ring rules."}
    premium = profile.get("premium_far_rule") or {}
    threshold = float(premium.get("mixed_premium_tdr_min_road_width_m") or 0)
    has_rule = bool(premium.get("premium_only_factor"))
    premium_used = has_rule and (not road_width_m or road_width_m >= threshold)
    if premium_used:
        reason = "Used only to estimate a Premium FAR charge."
    elif has_rule:
        reason = f"Premium FAR alone needs a road of at least {threshold:g} m."
    else:
        reason = "No Premium FAR charge rule is configured for this authority."
    out["guidance_value_per_m2"] = {"relevant": premium_used, "label": "Guidance value", "reason": reason}
    return out


def drop_irrelevant(site: dict, profile: Optional[dict]) -> dict:
    """Remove optional inputs that do not apply, so they cannot influence any check."""
    relevance = relevant_inputs(profile, site.get("land_use_category"), site.get("proposed_use"), site.get("road_width_m"))
    return {k: (None if k in relevance and not relevance[k]["relevant"] else v) for k, v in site.items()}
