"""Assessment service: the one place that turns inputs into a complete result.

Every interface (API, Streamlit, exports) calls this, so they cannot disagree on a figure.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon

from .boundary import DEFAULT_MIN_CLEAR_WIDTH_M, calculate_setback_envelope
from .checks import calculation_checks, group_checks, jurisdiction_checks, option_checks, overlay_checks, project_checks, rule_checks, site_checks, summarise
from .engine import build_report, far_counted_area, find_authority, load_authority_registry, load_rule_profile, load_statewide_rules
from .inputs import drop_irrelevant
from .location import parcel_jurisdiction_diagnostics


def input_fingerprint(payload: dict) -> str:
    """Stable hash of the inputs: results and exports carry it so stale output can be detected."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def parcel_from_boundary(boundary: dict) -> Polygon:
    return Polygon(boundary["points_m"], boundary.get("holes_m") or [])


def nominal_dimensions(poly: Polygon, front_edges: list[int]) -> tuple[Optional[float], Optional[float]]:
    """Width and depth measured along and across the first road-facing edge."""
    if not front_edges:
        return None, None
    coords = list(poly.exterior.coords)[:-1]
    index = int(front_edges[0])
    if not 0 <= index < len(coords):
        return None, None
    a, b = coords[index], coords[(index + 1) % len(coords)]
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    minx, miny, maxx, maxy = rotate(poly, -angle, origin=a).bounds
    return round(maxx - minx, 3), round(maxy - miny, 3)


def dimension_range(poly: Polygon, front_edges: list[int], stations: int = 41) -> Optional[dict]:
    """Measure plot depth and width at stations across the plot, relative to the first road edge."""
    if not front_edges:
        return None
    coords = list(poly.exterior.coords)[:-1]
    index = int(front_edges[0])
    if not 0 <= index < len(coords):
        return None
    a, b = coords[index], coords[(index + 1) % len(coords)]
    turned = rotate(poly, -math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), origin=a)
    minx, miny, maxx, maxy = turned.bounds
    def spans(make_line, low, high):
        values = []
        for i in range(1, stations):
            at = low + (high - low) * i / stations
            hit = turned.intersection(make_line(at))
            if not hit.is_empty and hit.length > 0:
                values.append(hit.length)
        return values
    depths = spans(lambda x: LineString([(x, miny - 1), (x, maxy + 1)]), minx, maxx)
    widths = spans(lambda y: LineString([(minx - 1, y), (maxx + 1, y)]), miny, maxy)
    if not depths or not widths:
        return None
    return {"depth_min_m": round(min(depths), 2), "depth_max_m": round(max(depths), 2), "width_min_m": round(min(widths), 2), "width_max_m": round(max(widths), 2)}


def road_widening_effect(boundary: dict, site: dict, far: dict) -> Optional[dict]:
    """Land a declared widening takes, and the FAR capacity if the authority does not count that land."""
    item = (site.get("overlays") or {}).get("road_widening") or {}
    if item.get("status") != "present" or item.get("edge") is None or not item.get("extra_setback_m"):
        return None
    parcel = parcel_from_boundary(boundary)
    coords = list(parcel.exterior.coords)[:-1]
    edge, depth = int(item["edge"]), float(item["extra_setback_m"])
    if not 0 <= edge < len(coords):
        return None
    remaining = calculate_setback_envelope(parcel, {"all_round_m": 0.0}, edge_extra_m={edge: depth})
    taken = round(parcel.area - float(remaining.get("area_m2") or 0), 2)
    result = {"edge": edge, "depth_m": depth, "area_taken_m2": taken}
    if far.get("maximum_far") is not None:
        far_area = float(far.get("far_calculation_area_m2") or 0)
        result["capacity_if_land_excluded_m2"] = round(max(far_area - taken, 0) * float(far["maximum_far"]), 2)
    return result


def premium_charge_estimate(far: dict, guidance_value: Optional[float]) -> Optional[dict]:
    """Rough Premium FAR charge from the gazetted formula, for the Premium-only allowance."""
    premium = far.get("premium_far") or {}
    additional = premium.get("premium_only_additional_area_m2")
    if not additional or not guidance_value or not far.get("maximum_far"):
        return None
    rule = load_statewide_rules()["premium_far_charge"]
    notional_site = float(additional) / float(far["maximum_far"])
    by_site = notional_site * float(guidance_value) * rule["pct_of_guidance_on_notional_site"] / 100
    floor = float(additional) * float(guidance_value) * rule["minimum_pct_of_guidance_per_m2_built"] / 100
    return {"guidance_value_per_m2": float(guidance_value), "additional_area_m2": float(additional), "notional_site_area_m2": round(notional_site, 2), "estimated_charge_inr": round(max(by_site, floor)), "note": rule["note"], "source": rule["source"]}


def height_caps(profile: Optional[dict], site: dict, scenario: dict) -> list[dict]:
    """Every height limit that applies to this site, from the rules and from declared constraints."""
    caps = []
    area = float(site.get("site_area_m2") or 0)
    road = float(site.get("road_width_m") or 0)
    for limit in (profile or {}).get("height_limits", []):
        if limit.get("categories") and site.get("land_use_category") not in limit["categories"]:
            continue
        if limit.get("road_width_max_exclusive_m") is not None and not road < float(limit["road_width_max_exclusive_m"]):
            continue
        if limit.get("site_area_max_m2") is not None and not area <= float(limit["site_area_max_m2"]):
            continue
        height = float(limit["max_height_m"])
        if not limit.get("includes_stilt") and scenario.get("stilt"):
            height += float(scenario.get("stilt_height_m") or 0)
        caps.append({"height_m": height, "reason": limit["note"]})
    airport = (site.get("overlays") or {}).get("airport") or {}
    if airport.get("status") == "present" and airport.get("max_height_m"):
        caps.append({"height_m": float(airport["max_height_m"]), "reason": "Airport height zone, as entered from the AAI NOC or colour-coded map."})
    return caps


def height_for_setback(profile: Optional[dict], site: dict, scenario: dict) -> Optional[dict]:
    """The tallest building a what-if all-round setback allows under the height table, within every cap."""
    distance = scenario.get("manual_all_round_setback_m")
    if not distance or not profile:
        return None
    distance = float(distance)
    minimum = profile.get("minimum_all_round_setback") or {}
    area = float(site.get("site_area_m2") or 0)
    if minimum:
        forced = float(minimum["setback_m"]) if area >= float(minimum["site_area_min_m2"]) else 0.0
    else:
        forced = 5.0 if area > 4000 and profile.get("force_minimum_all_round_for_area_above_4000", True) else 0.0
    if distance < forced:
        return {"max_height_m": None, "message": f"At least {forced:g} m all round is needed on a plot this size, so {distance:g} m is too small at any height."}
    stilt = bool(scenario.get("stilt"))
    bands = [b for b in sorted(profile.get("setback_table9_height_bands", []), key=lambda b: b["height_min_exclusive"])
             if b.get("all_round_m") is not None and ("stilt" not in b or bool(b["stilt"]) == stilt)]
    top = None
    for band in bands:
        # Bands are in height order: stop at the first one this setback is too small for.
        if float(band["all_round_m"]) > distance:
            break
        top = band
    table8_max = float(profile.get("setback_table8_max_height_m", 12.0))
    if top is None:
        base_height, basis = table8_max, f"Below the height table's first row, so up to {table8_max:g} m, where the low-rise table must also be met."
    else:
        if top.get("height_max") is None:
            base_height, basis = None, "The height table sets no upper limit at this setback."
        else:
            base_height = float(top["height_max"])
            basis = f"The height table allows up to {base_height:g} m with {distance:g} m all round."
    caps = [c for c in height_caps(profile, site, scenario) if base_height is None or c["height_m"] < base_height]
    if caps:
        cap = min(caps, key=lambda c: c["height_m"])
        return {"max_height_m": cap["height_m"], "message": f"{basis} A lower limit applies: {cap['reason']}"}
    return {"max_height_m": base_height, "message": basis + " Basement setbacks do not change this."}


def height_cap_checks(site: dict, scenario: dict) -> list[dict]:
    """Check each option's height against a declared airport limit."""
    from .checks import FAIL, PASS, _check
    airport = (site.get("overlays") or {}).get("airport") or {}
    height = scenario.get("height_m")
    if airport.get("status") != "present" or not airport.get("max_height_m") or not height:
        return []
    limit = float(airport["max_height_m"])
    status = FAIL if float(height) > limit else PASS
    return [_check("option.airport_height", "Options", "Airport height", status, f"{float(height):g} m against the {limit:g} m permitted in the airport height zone.", option=scenario.get("name"), value=limit)]


def _overlay_edge_extras(site: dict) -> dict[int, float]:
    """Combine declared no-build depths per edge; the deepest constraint on an edge governs."""
    extras: dict[int, float] = {}
    for item in (site.get("overlays") or {}).values():
        if (item or {}).get("status") == "present" and item.get("edge") is not None and item.get("extra_setback_m"):
            edge = int(item["edge"])
            extras[edge] = max(extras.get(edge, 0.0), float(item["extra_setback_m"]))
    return extras


def attach_boundary_analysis(report: dict, boundary: dict, site: dict, far_area: float, coverage_pct: Optional[float], far_exclusions: Optional[dict] = None) -> None:
    """Add envelopes, then derive any missing footprint without exceeding envelope or coverage."""
    parcel = parcel_from_boundary(boundary)
    front_edges = boundary.get("front_edges", [])
    rear_edges = boundary.get("rear_edges", [])
    left_edges = boundary.get("left_edges", [])
    right_edges = boundary.get("right_edges", [])
    extras = _overlay_edge_extras(site)
    area = float(site["site_area_m2"])
    options = []
    for opt in report.get("scenarios", []):
        env = calculate_setback_envelope(parcel, opt.get("setback_result", {}), front_edges, rear_edges, extras, left_edges=left_edges, right_edges=right_edges)
        opt["boundary_envelope"] = env
        if int(opt.get("basement_levels", 0) or 0) > 0:
            basement = calculate_setback_envelope(parcel, opt.get("basement_setback_result", {}), front_edges, rear_edges, extras, left_edges=left_edges, right_edges=right_edges)
        else:
            basement = {"status": "no_basement", "message": "No basement selected for this option.", "area_m2": None, "geometry": None}
        opt["basement_boundary_envelope"] = basement
        env_area = env.get("area_m2")
        if opt.get("footprint_m2") is None and env_area:
            limit = area * coverage_pct / 100 if coverage_pct is not None else None
            footprint = min(float(env_area), limit) if limit is not None else float(env_area)
            opt["footprint_m2"] = round(footprint, 2)
            opt["footprint_source"] = "coverage limit" if limit is not None and limit < float(env_area) else "preliminary setback envelope area"
            floors = opt.get("floors")
            if floors:
                opt["gross_concept_area_m2"] = round(opt["footprint_m2"] * int(floors), 2)
                counted = far_counted_area(opt["gross_concept_area_m2"], floors, opt.get("core_excluded_per_floor_m2"), opt.get("parking_excluded_m2"), far_exclusions)
                opt.update(counted)
                ratio = round(counted["far_counted_area_m2"] / far_area, 3) if far_area > 0 else None
                opt["achieved_gross_far_ratio"] = ratio
                opt["achieved_far_ratio"] = ratio
                cap = opt.get("far_capacity_m2")
                opt["scenario_headroom_m2"] = round(cap - counted["far_counted_area_m2"], 2) if cap is not None else None
        elif opt.get("footprint_m2") is not None and env_area is not None:
            opt["footprint_source"] = "floor schedule" if opt.get("floor_schedule") else "user-entered design footprint"
            opt["footprint_exceeds_envelope"] = float(opt["footprint_m2"]) > float(env_area) + 0.5
            if opt["footprint_exceeds_envelope"]:
                opt["envelope_warning"] = "Entered footprint is larger than the calculated preliminary setback envelope. Reduce footprint or inspect geometry."
        options.append({"name": opt.get("name"), "envelope": env, "basement_envelope": basement})
    report["boundary_analysis"] = {
        "source_file": boundary.get("source_file"), "source_type": boundary.get("source_type"),
        "source_units": boundary.get("source_units"), "scale_to_m": boundary.get("scale_to_m"),
        "source_fingerprint": boundary.get("source_fingerprint"), "candidate_id": boundary.get("candidate_id"),
        "area_m2": boundary.get("area_m2"), "perimeter_m": boundary.get("perimeter_m"),
        "vertex_count": boundary.get("vertex_count"), "is_convex": boundary.get("is_convex"), "hole_count": len(boundary.get("holes_m") or []),
        "validation_status": boundary.get("validation_status"), "validation_notes": boundary.get("validation_notes", []),
        "use_computed_area": boundary.get("use_computed_area", True),
        "front_edges": front_edges, "rear_edges": rear_edges, "left_edges": left_edges, "right_edges": right_edges, "dimension_range": dimension_range(parcel, front_edges), "edge_no_build_m": {str(k): v for k, v in extras.items()},
        "min_clear_width_m": DEFAULT_MIN_CLEAR_WIDTH_M,
        "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in parcel.exterior.coords]] + [[list(p) for p in r.coords] for r in parcel.interiors]},
        "options": options,
    }


def assess(payload: dict, registry: Optional[dict] = None) -> dict:
    """Run a full assessment. ``payload`` holds the site fields plus ``boundary`` and ``location``."""
    site = {k: v for k, v in payload.items() if k not in {"boundary", "location"}}
    boundary = payload.get("boundary") or None
    location = payload.get("location") or None
    registry = registry or load_authority_registry()
    authority = find_authority(registry, site["authority_key"])
    profile = load_rule_profile(authority["rule_profile"]) if authority.get("rule_profile") else None
    site = drop_irrelevant(site, profile)

    parcel_diagnostics = None
    if boundary:
        poly = parcel_from_boundary(boundary)
        if boundary.get("use_computed_area", True):
            site["site_area_m2"] = float(boundary["area_m2"])
            site["site_area_source"] = "imported polyline area"
        width, depth = nominal_dimensions(poly, boundary.get("front_edges") or [])
        if width and not site.get("frontage_m"):
            site["frontage_m"] = width
            site["depth_m"] = depth
            site["dimensions_source"] = "measured along and across the first road-facing edge"
        site["shape_type"] = "Irregular / non-rectangular" if len(boundary.get("points_m", [])) != 4 or not boundary.get("is_convex", False) else "Four-sided"
        site["geometry_mode"] = "Use imported polygon"
        if boundary.get("source_points_wgs84"):
            parcel_diagnostics = parcel_jurisdiction_diagnostics(boundary["source_points_wgs84"], boundary.get("source_holes_wgs84"))

    report = build_report(site, registry=registry, profile=profile)
    far = report.get("far", {})
    far_area = float(far.get("far_calculation_area_m2") or site["site_area_m2"])
    coverage_pct = (far.get("coverage") or {}).get("coverage_pct")
    report["location_identification"] = location
    report["parcel_jurisdiction"] = parcel_diagnostics
    report["site"].update({k: site.get(k) for k in ("road_width_source", "authority_confirmed", "zone_confirmed", "rmp_ring", "dwelling_units", "average_unit_area_m2", "land_status", "prior_sanction", "area_stated_m2", "dimensions_source", "statutory_deduction_pct", "guidance_value_per_m2")})
    if boundary:
        attach_boundary_analysis(report, boundary, site, far_area, coverage_pct, (profile or {}).get("far_exclusions"))
        report["road_widening"] = road_widening_effect(boundary, site, far)
    charge = premium_charge_estimate(far, site.get("guidance_value_per_m2"))
    if charge:
        far["premium_far"]["charge_estimate"] = charge

    checks = jurisdiction_checks(site, authority, location, parcel_diagnostics)
    checks += rule_checks(site, profile, far, float(site["site_area_m2"]), float(site["road_width_m"]))
    checks += site_checks(site, far, report.get("boundary_analysis"))
    checks += overlay_checks(site, authority, profile)
    for scenario in report.get("scenarios", []):
        checks += option_checks(site, profile, far, scenario, report.get("boundary_analysis"))
    checks += calculation_checks(report)
    checks += project_checks(site, profile, report.get("scenarios", []))
    for scenario in report.get("scenarios", []):
        scenario["height_for_setback"] = height_for_setback(profile, site, scenario)
        checks += height_cap_checks(site, scenario)
    checks = group_checks(checks)
    report["compliance_checks"] = checks
    report["verdict"] = summarise(checks)
    report["input_fingerprint"] = input_fingerprint(payload)
    return report


def far_preview(authority_key: str, category: Optional[str], site_area_m2: float, road_width_m: float, surrounding_zone: Optional[str] = None, proposed_use: Optional[str] = None, statutory_deduction_pct: Optional[float] = None, registry: Optional[dict] = None) -> dict:
    from .engine import match_far_rule
    registry = registry or load_authority_registry()
    authority = find_authority(registry, authority_key)
    profile = load_rule_profile(authority["rule_profile"]) if authority.get("rule_profile") else None
    if not profile:
        return {"status": "not_configured", "message": "No rules are configured for this planning authority. SiteIQ will not use another authority's FAR.", "maximum_far": None}
    if not category:
        return {"status": "category_required", "message": "Select the land-use category to run the FAR lookup.", "maximum_far": None}
    return match_far_rule(profile, category, site_area_m2, road_width_m, surrounding_zone=surrounding_zone, proposed_use=proposed_use, statutory_deduction_pct=statutory_deduction_pct)
