"""Assessment service: the one place that turns inputs into a complete result.

Every interface (API, Streamlit, exports) calls this, so they cannot disagree on a figure.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from shapely.affinity import rotate
from shapely.geometry import Polygon

from .boundary import DEFAULT_MIN_CLEAR_WIDTH_M, calculate_setback_envelope
from .checks import jurisdiction_checks, option_checks, overlay_checks, project_checks, rule_checks, site_checks, summarise
from .engine import build_report, find_authority, load_authority_registry, load_rule_profile
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


def _overlay_edge_extras(site: dict) -> dict[int, float]:
    """Combine declared no-build depths per edge; the deepest constraint on an edge governs."""
    extras: dict[int, float] = {}
    for item in (site.get("overlays") or {}).values():
        if (item or {}).get("status") == "present" and item.get("edge") is not None and item.get("extra_setback_m"):
            edge = int(item["edge"])
            extras[edge] = max(extras.get(edge, 0.0), float(item["extra_setback_m"]))
    return extras


def attach_boundary_analysis(report: dict, boundary: dict, site: dict, far_area: float, coverage_pct: Optional[float]) -> None:
    """Add envelopes, then derive any missing footprint without exceeding envelope or coverage."""
    parcel = parcel_from_boundary(boundary)
    front_edges = boundary.get("front_edges", [])
    rear_edges = boundary.get("rear_edges", [])
    extras = _overlay_edge_extras(site)
    area = float(site["site_area_m2"])
    options = []
    for opt in report.get("scenarios", []):
        env = calculate_setback_envelope(parcel, opt.get("setback_result", {}), front_edges, rear_edges, extras)
        opt["boundary_envelope"] = env
        if int(opt.get("basement_levels", 0) or 0) > 0:
            basement = calculate_setback_envelope(parcel, opt.get("basement_setback_result", {}), front_edges, rear_edges, extras)
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
                ratio = round(opt["gross_concept_area_m2"] / far_area, 3) if far_area > 0 else None
                opt["achieved_gross_far_ratio"] = ratio
                opt["achieved_far_ratio"] = ratio
                cap = opt.get("far_capacity_m2")
                opt["scenario_headroom_m2"] = round(cap - opt["gross_concept_area_m2"], 2) if cap is not None else None
        elif opt.get("footprint_m2") is not None and env_area is not None:
            opt["footprint_source"] = "user-entered design footprint"
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
        "front_edges": front_edges, "rear_edges": rear_edges, "edge_no_build_m": {str(k): v for k, v in extras.items()},
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
    report["site"].update({k: site.get(k) for k in ("road_width_source", "authority_confirmed", "zone_confirmed", "rmp_ring", "dwelling_units", "average_unit_area_m2", "land_status", "prior_sanction", "area_stated_m2", "dimensions_source", "statutory_deduction_pct")})
    if boundary:
        attach_boundary_analysis(report, boundary, site, far_area, coverage_pct)

    checks = jurisdiction_checks(site, authority, location, parcel_diagnostics)
    checks += rule_checks(site, profile, far, float(site["site_area_m2"]), float(site["road_width_m"]))
    checks += site_checks(site, far, report.get("boundary_analysis"))
    checks += overlay_checks(site, authority)
    for scenario in report.get("scenarios", []):
        checks += option_checks(site, profile, far, scenario, report.get("boundary_analysis"))
    checks += project_checks(site)
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
