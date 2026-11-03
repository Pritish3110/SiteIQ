"""Compliance checks: one explicit outcome for every regulation SiteIQ knows about.

A provision that could not be evaluated is reported as NEEDS_INPUT, NOT_CONFIGURED or
REFER. It never counts as a pass, so a missing rule lowers confidence rather than vanishing.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .engine import load_statewide_rules, match_far_rule, rule_status_problem, source_by_id

PASS = "PASS"
FAIL = "FAIL"
NEEDS_INPUT = "NEEDS_INPUT"
NOT_CONFIGURED = "NOT_CONFIGURED"
REFER = "REFER"

AREA_TOLERANCE_PCT = 0.5
ROAD_TOLERANCE_M = 0.25
AREA_MISMATCH_PCT = 2.0
MIN_STOREY_HEIGHT_M = 2.4  # Screening check on entered numbers, not a statutory minimum.
MAX_STOREY_HEIGHT_M = 8.0

OVERLAYS = {
    "lake": "Lake or tank",
    "drain": "Drain or rajakaluve",
    "ht_line": "High-tension power line",
    "airport": "Airport height zone",
    "heritage": "Protected monument",
    "railway": "Railway land",
    "defence": "Defence establishment",
    "highway": "National or state highway",
    "flood_prone": "Flood-prone or low-lying land",
    "road_widening": "Road widening or master-plan road",
}
OVERLAY_AGENCY = {
    "ht_line": "Take the clearance from KPTCL or the electricity supplier. SiteIQ does not configure clearance distances.",
    "airport": "Check the AAI colour-coded zoning map and obtain a height NOC where it applies.",
    "heritage": "Check the distance from the monument with ASI or the State Archaeology Department.",
    "railway": "Check the railway boundary and obtain an NOC from the zonal railway where it applies.",
    "defence": "Check restrictions with the local military estates officer.",
    "highway": "Check building lines and access permission with NHAI or the state PWD.",
    "road_widening": "Confirm the widening line with the planning authority. The surrendered land may change the FAR area and TDR entitlement.",
}


def _check(check_id: str, group: str, title: str, status: str, message: str, source: Optional[dict] = None, option: str | None = None, value: Any = None) -> dict:
    return {"id": check_id, "group": group, "title": title, "status": status, "message": message, "source": source, "option": option, "value": value}


def _bmr_scope(authority: Optional[dict]) -> bool:
    if not authority:
        return False
    return authority.get("key") in {"bengaluru_rmp2015", "bda_lpa"} or "BMRDA" in str(authority.get("coverage_group", ""))


def _threshold_sensitivity(profile: dict, site: dict, far: dict, area: float, road: float) -> list[dict]:
    """Re-run the lookup just either side of the measured values and report any change."""
    base_far = far.get("maximum_far")
    area_delta = area * AREA_TOLERANCE_PCT / 100
    cases = [("area", area - area_delta, road), ("area", area + area_delta, road), ("road", area, road - ROAD_TOLERANCE_M), ("road", area, road + ROAD_TOLERANCE_M)]
    changes = []
    for kind, a, r in cases:
        if a <= 0 or r <= 0:
            continue
        other = match_far_rule(profile, site.get("land_use_category"), a, r, surrounding_zone=site.get("surrounding_zone"), proposed_use=site.get("proposed_use"), statutory_deduction_pct=site.get("statutory_deduction_pct"))
        if other.get("maximum_far") != base_far or other.get("selected_path") != far.get("selected_path"):
            changes.append({"kind": kind, "area_m2": round(a, 2), "road_width_m": round(r, 2), "maximum_far": other.get("maximum_far"), "status": other.get("status")})
    return changes


def jurisdiction_checks(site: dict, authority: dict, location: Optional[dict], parcel: Optional[dict]) -> list[dict]:
    out = []
    auth = (location or {}).get("authority") or {}
    suggested = (location or {}).get("suggested_authority_key")
    selected = site.get("authority_key")
    if site.get("authority_confirmed"):
        out.append(_check("jurisdiction.confirmed", "Jurisdiction", "Planning authority", PASS, "You confirmed this authority against official records."))
    elif auth.get("status") == "matched_polygon_layer" and suggested == selected:
        out.append(_check("jurisdiction.confirmed", "Jurisdiction", "Planning authority", REFER, "The location matched an installed boundary layer. Confirm the layer's date and source, then mark the authority as confirmed."))
    else:
        out.append(_check("jurisdiction.confirmed", "Jurisdiction", "Planning authority", NEEDS_INPUT, "No official boundary evidence supports this authority. Check the notified planning area, then mark it as confirmed."))
    if location and suggested and suggested != selected:
        out.append(_check("jurisdiction.mismatch", "Jurisdiction", "Selected vs detected authority", REFER, f"The location suggests '{suggested}', but the assessment uses '{selected}'. Resolve this before relying on the result."))
    comparison = (location or {}).get("input_coordinate_comparison") or {}
    if comparison.get("mismatch"):
        out.append(_check("location.mismatch", "Jurisdiction", "Location sources disagree", REFER, f"The map pin is {comparison.get('distance_km', 0):.1f} km from the typed coordinates."))
    precision = ((location or {}).get("map_link_resolution") or {}).get("precision")
    if precision == "viewport":
        out.append(_check("location.precision", "Jurisdiction", "Map link has no pin", REFER, "The map link only gives the centre of the view. Confirm that it marks this site."))
    if not location and not parcel:
        out.append(_check("location.resolved", "Jurisdiction", "Site location", NEEDS_INPUT, "The location was not identified. Run the location lookup or import a georeferenced boundary."))
    if parcel:
        status = parcel.get("status")
        if status == "fully_within":
            near = parcel.get("near_boundaries") or []
            if near:
                out.append(_check("jurisdiction.parcel", "Jurisdiction", "Whole-parcel coverage", REFER, f"The parcel is inside one authority but within {parcel.get('near_threshold_m', 500):g} m of a boundary. Confirm against the notified limits."))
            else:
                out.append(_check("jurisdiction.parcel", "Jurisdiction", "Whole-parcel coverage", PASS, parcel.get("message", "")))
        elif status in {"straddles_authorities", "partial_coverage", "no_coverage"}:
            out.append(_check("jurisdiction.parcel", "Jurisdiction", "Whole-parcel coverage", FAIL if status == "straddles_authorities" else REFER, parcel.get("message", ""), value=parcel.get("authorities")))
        else:
            out.append(_check("jurisdiction.parcel", "Jurisdiction", "Whole-parcel coverage", NOT_CONFIGURED, parcel.get("message", "No official planning-boundary layer is installed.")))
    return out


def rule_checks(site: dict, profile: Optional[dict], far: dict, area: float, road: float) -> list[dict]:
    out = []
    if not profile:
        out.append(_check("rule.profile", "Rules", "Rule profile", NOT_CONFIGURED, "No rules are configured for this authority. SiteIQ did not borrow another authority's rules."))
        return out
    problem = rule_status_problem(profile)
    status = profile.get("source_status")
    if problem:
        out.append(_check("rule.profile", "Rules", "Rule profile", FAIL, problem))
    elif status == "verified_operative":
        out.append(_check("rule.profile", "Rules", "Rule profile", PASS, "This profile has been reviewed against the operative documents."))
    else:
        label = {"secondary_source_candidate": "transcribed from secondary copies", "official_source_found_pending_review": "compared with the published source documents, but not independently reviewed", "partially_verified": "only partly verified"}.get(status, str(status))
        out.append(_check("rule.profile", "Rules", "Rule profile", REFER, f"This profile is {label}. Do not freeze a design on it. {profile.get('profile_name', '')}".strip()))
    if site.get("zone_confirmed"):
        out.append(_check("rule.zone", "Rules", "Land-use zone", PASS, "You confirmed the category against the notified land-use map."))
    else:
        out.append(_check("rule.zone", "Rules", "Land-use zone", NEEDS_INPUT, "Check the category against the official land-use map, then mark it as confirmed."))
    if far.get("maximum_far") is not None:
        out.append(_check("rule.far", "Rules", "FAR table match", PASS if status == "verified_operative" else REFER, far.get("message", ""), far.get("source"), value=far.get("maximum_far")))
        for change in _threshold_sensitivity(profile, site, far, area, road):
            what = f"plot area of {change['area_m2']:,.2f} m²" if change["kind"] == "area" else f"road width of {change['road_width_m']:g} m"
            result = f"FAR {change['maximum_far']:.2f}" if change.get("maximum_far") is not None else "no FAR"
            out.append(_check(f"rule.sensitivity.{change['kind']}", "Rules", "Close to a rule threshold", REFER, f"A {what} gives {result}, against {far['maximum_far']:.2f} now. Confirm the exact legal figure before relying on this.", value=change))
    else:
        code = FAIL if far.get("status") in {"minimum_road_width_not_met", "outside_configured_table_scope", "rule_status_blocked"} else NEEDS_INPUT if far.get("status") in {"surrounding_zone_required", "invalid_input"} else REFER
        out.append(_check("rule.far", "Rules", "FAR table match", code, far.get("message", "No FAR was found."), far.get("source")))
    return out


def site_checks(site: dict, far: dict, boundary: Optional[dict]) -> list[dict]:
    out = []
    area = float(site.get("site_area_m2") or 0)
    stated = site.get("area_stated_m2")
    if boundary and stated:
        diff = abs(float(boundary["area_m2"]) - float(stated)) / float(stated) * 100
        status = PASS if diff <= AREA_MISMATCH_PCT else REFER
        out.append(_check("site.area_match", "Site", "Drawn vs title area", status, f"The boundary gives {boundary['area_m2']:,.2f} m² and the stated area is {float(stated):,.2f} m², a {diff:.2f}% difference.", value=round(diff, 2)))
    elif boundary:
        out.append(_check("site.area_match", "Site", "Drawn vs title area", NEEDS_INPUT, "Enter the area from the title or survey so it can be compared with the drawn boundary."))
    else:
        out.append(_check("site.boundary", "Site", "Surveyed boundary", NEEDS_INPUT, "No boundary is applied, so the area is as typed and no envelope can be drawn."))
    source = site.get("road_width_source") or "unknown"
    if source == "notified":
        out.append(_check("site.road", "Site", "Road width source", PASS, "The road width is the notified width."))
    elif source in {"survey", "measured"}:
        out.append(_check("site.road", "Site", "Road width source", REFER, f"The road width is {source}. FAR tables use the legal width, which may differ."))
    else:
        out.append(_check("site.road", "Site", "Road width source", NEEDS_INPUT, "Record where the road width came from: notified, surveyed or measured."))
    edges = site.get("road_edges") or []
    widths = sorted({float(e["width_m"]) for e in edges if e.get("width_m")})
    if len(widths) > 1:
        out.append(_check("site.multi_road", "Site", "Roads of different widths", REFER, f"This plot has roads from {widths[0]:g} m to {widths[-1]:g} m. The assessment uses {float(site.get('road_width_m') or 0):g} m; confirm which road governs FAR and access."))
    if boundary:
        fronts = boundary.get("front_edges") or []
        if not fronts:
            out.append(_check("site.frontage", "Site", "Road-facing edges", NEEDS_INPUT, "Tag the road-facing edges so setbacks can be applied to the right sides."))
        elif len(fronts) > 1:
            out.append(_check("site.frontage", "Site", "Corner or multi-road plot", REFER, f"{len(fronts)} edges are tagged as road-facing. Each gets the front setback; confirm how the authority treats this plot."))
        else:
            out.append(_check("site.frontage", "Site", "Road-facing edges", PASS, "One road-facing edge is tagged."))
        if boundary.get("hole_count"):
            out.append(_check("site.holes", "Site", "Excluded land inside plot", REFER, f"{boundary['hole_count']} inner area(s) are excluded from the plot area. Confirm they are outside the title."))
    land = site.get("land_status") or "unknown"
    if land == "converted":
        out.append(_check("site.conversion", "Site", "Land conversion", PASS, "You recorded the land as converted for non-agricultural use."))
    elif land == "not_converted":
        out.append(_check("site.conversion", "Site", "Land conversion", FAIL, "The land is recorded as not converted. Conversion is needed before building approval."))
    else:
        out.append(_check("site.conversion", "Site", "Land conversion", NEEDS_INPUT, "Record whether the land has been converted for non-agricultural use."))
    prior = site.get("prior_sanction") or "unknown"
    if prior == "none":
        out.append(_check("site.prior_sanction", "Site", "Earlier sanctions", PASS, "You recorded no earlier sanction or layout on this land."))
    elif prior == "exists":
        out.append(_check("site.prior_sanction", "Site", "Earlier sanctions", REFER, "An earlier sanction or layout exists. Its conditions and grandfathering may override this assessment."))
    else:
        out.append(_check("site.prior_sanction", "Site", "Earlier sanctions", NEEDS_INPUT, "Record whether an earlier sanction or layout exists on this land."))
    details = (far.get("matched_rule") or {}).get("details") or {}
    source_kind = details.get("deduction_source")
    if source_kind == "user_assumption":
        out.append(_check("far.deduction", "FAR", "Reservation assumption", REFER, f"The {details.get('deduction_pct', 0):g}% reduction is your assumption, not a configured rule. Replace it with the figure in the operative plan."))
    elif source_kind == "configured_rule":
        out.append(_check("far.deduction", "FAR", "Net FAR area", REFER, details.get("area_basis_note") or "A configured reservation reduces the FAR area.", far.get("source")))
    elif far.get("maximum_far") is not None and area > 4000:
        out.append(_check("far.deduction", "FAR", "Gross or net FAR area", REFER, f"FAR uses the gross area of {area:,.0f} m². Plots this size may need reservations that reduce it. Confirm the approval route before relying on the capacity."))
    return out


def overlay_checks(site: dict, authority: Optional[dict], profile: Optional[dict] = None) -> list[dict]:
    statewide = load_statewide_rules()
    declared = site.get("overlays") or {}
    out = []
    for key, label in OVERLAYS.items():
        item = declared.get(key) or {}
        state = item.get("status") or "unknown"
        cid = f"overlay.{key}"
        if state == "unknown":
            out.append(_check(cid, "Overlays", label, NEEDS_INPUT, f"Check the official maps and record whether this affects the site. SiteIQ has no official layer for it."))
            continue
        if state == "absent":
            out.append(_check(cid, "Overlays", label, PASS, "You recorded that this does not affect the site."))
            continue
        extra = item.get("extra_setback_m")
        edge_note = f" A {float(extra):g} m no-build depth is applied along edge {int(item['edge']) + 1}." if extra and item.get("edge") is not None else " Tag the affected edge and depth so it is removed from the envelope."
        if key == "airport":
            if not item.get("max_height_m"):
                out.append(_check(cid, "Overlays", label, NEEDS_INPUT, "Enter the maximum height permitted here, from the AAI colour-coded zoning map or the height NOC. Each option is then checked against it."))
            else:
                out.append(_check(cid, "Overlays", label, REFER, f"Maximum height of {float(item['max_height_m']):g} m above ground, as you entered it. Confirm the reference level the NOC uses.", value=float(item["max_height_m"])))
            continue
        if key == "heritage":
            rule = statewide["heritage"]
            distance = item.get("distance_m")
            if distance is None:
                out.append(_check(cid, "Overlays", label, NEEDS_INPUT, "Enter the distance from the protected monument's boundary.", rule["source"]))
            elif float(distance) < rule["prohibited_m"]:
                out.append(_check(cid, "Overlays", label, FAIL, f"{float(distance):g} m is inside the {rule['prohibited_m']:g} m prohibited area, where new construction is not allowed. {rule['note']}", rule["source"], value=float(distance)))
            elif float(distance) < rule["prohibited_m"] + rule["regulated_m"]:
                out.append(_check(cid, "Overlays", label, REFER, f"{float(distance):g} m is inside the regulated area, so construction needs permission from the competent authority. {rule['note']}", rule["source"], value=float(distance)))
            else:
                out.append(_check(cid, "Overlays", label, PASS, f"{float(distance):g} m is beyond the prohibited and regulated areas. {rule['note']}", rule["source"], value=float(distance)))
            continue
        if key == "flood_prone" and item.get("flood_level_m") is not None:
            out.append(_check(cid, "Overlays", label, REFER, f"Flood level {float(item['flood_level_m']):g} m above ground, as you entered it. Keep the plinth and openings above it. Basements are not permitted in notified flood-prone or low-lying areas under the 2026 Bengaluru amendment.", value=float(item["flood_level_m"])))
            continue
        if key in {"railway", "defence", "lake"} and item.get("distance_m") is not None:
            if key == "lake":
                agency = statewide["lake_buffer"]["message"] if _bmr_scope(authority) else "Confirm the lake buffer that applies in this planning area."
            else:
                agency = OVERLAY_AGENCY[key]
            out.append(_check(cid, "Overlays", label, REFER, f"{float(item['distance_m']):g} m away, as you entered it. {agency}" + edge_note, value=float(item["distance_m"])))
            continue
        if key == "drain":
            rule = statewide["drain_buffers"]
            if not _bmr_scope(authority):
                out.append(_check(cid, "Overlays", label, NOT_CONFIGURED, "Drain buffers are configured only for Bengaluru and BMR planning areas. Confirm the local rule." + edge_note))
                continue
            required = rule["buffers_m"].get(item.get("drain_class") or "")
            if required is None:
                out.append(_check(cid, "Overlays", label, NEEDS_INPUT, "Choose the drain class from the revenue records: primary, secondary or tertiary.", rule["source"]))
                continue
            short = extra is not None and float(extra) < required
            message = f"A {item['drain_class']} drain needs at least {required:g} m on either side from its edge as per revenue records."
            if extra is None or item.get("edge") is None:
                out.append(_check(cid, "Overlays", label, NEEDS_INPUT, message + " Tag the affected edge and depth so it is removed from the envelope.", rule["source"], value=required))
            else:
                out.append(_check(cid, "Overlays", label, FAIL if short else REFER, message + (f" Only {float(extra):g} m was entered." if short else edge_note), rule["source"], value=required))
        elif key == "ht_line" and (profile or {}).get("electrical_clearance"):
            rule = profile["electrical_clearance"]
            src = source_by_id(profile, rule.get("source_id"))
            line = rule["lines"].get(item.get("line_kv") or "")
            if line is None:
                out.append(_check(cid, "Overlays", label, NEEDS_INPUT, "Choose the line voltage. The clearance depends on it.", src))
            else:
                horizontal, corridor = line
                message = f"{rule['note']} For this line: {horizontal:g} m horizontal distance from its edge, and a {corridor:g} m corridor overall. Confirm with KPTCL or the electricity supplier."
                short = extra is not None and float(extra) < horizontal
                out.append(_check(cid, "Overlays", label, FAIL if short else NEEDS_INPUT if extra is None or item.get("edge") is None else REFER, message + (f" Only {float(extra):g} m was entered." if short else edge_note), src, value=horizontal))
        elif key == "lake":
            rule = statewide["lake_buffer"]
            out.append(_check(cid, "Overlays", label, REFER, (rule["message"] if _bmr_scope(authority) else "Confirm the lake buffer that applies in this planning area.") + edge_note, rule["source"] if _bmr_scope(authority) else None))
        elif key == "flood_prone":
            out.append(_check(cid, "Overlays", label, REFER, "Basements are not permitted in notified flood-prone or low-lying areas under the 2026 Bengaluru amendment. Confirm the local rule and the flood level." + edge_note))
        else:
            out.append(_check(cid, "Overlays", label, REFER, OVERLAY_AGENCY[key] + edge_note))
    return out


def _parking_cars(profile: dict, site: dict, floor_area: float) -> tuple[Optional[int], str, str]:
    """Return (cars, status, message) under the configured parking table."""
    rule = (profile or {}).get("parking_rule")
    if not rule:
        return None, NOT_CONFIGURED, "No parking table is configured for this authority."
    use = site.get("proposed_use") or ""
    per = rule.get("floor_area_per_car_m2", {}).get(use)
    def by_standard(amount: float, standard: float) -> int:
        whole = math.floor(amount / standard)
        return whole + (1 if amount - whole * standard > standard / 2 else 0)
    if per:
        cars = by_standard(floor_area, float(per))
        return cars, REFER, f"About {cars} car spaces at 1 per {per} m² of {floor_area:,.0f} m². Floor area for parking is not the same as FAR area, so check the schedule."
    multi = rule.get("multi_dwelling") or {}
    if use in multi.get("uses", []):
        units, avg = site.get("dwelling_units"), site.get("average_unit_area_m2")
        if not units or not avg:
            return None, NEEDS_INPUT, "Enter the number of dwelling units and their average floor area to calculate parking."
        if float(avg) <= float(multi["small_unit_max_m2"]):
            base = math.ceil(int(units) / int(multi["small_units_per_car"]))
        elif multi.get("unit_area_per_car_m2") is None:
            base = int(units)
        else:
            base = int(units) * max(1, by_standard(float(avg), float(multi["unit_area_per_car_m2"])))
        visitors = math.ceil(base * float(multi["visitor_pct"]) / 100)
        return base + visitors, REFER, f"About {base + visitors} car spaces: {base} for {int(units)} units" + (f" plus {visitors} for visitors." if visitors else ".")
    return None, NOT_CONFIGURED, f"The parking table is not mapped for '{use}'. Work it out from the table by use."


def option_checks(site: dict, profile: Optional[dict], far: dict, scenario: dict, boundary: Optional[dict]) -> list[dict]:
    statewide = load_statewide_rules()
    name = scenario.get("name") or "Option"
    out: list[dict] = []
    area = float(site.get("site_area_m2") or 0)
    road = float(site.get("road_width_m") or 0)
    height = scenario.get("height_m")
    floors = scenario.get("floors")
    footprint = scenario.get("footprint_m2")
    gross = scenario.get("gross_concept_area_m2")
    category = site.get("land_use_category")
    def add(cid, title, status, message, source=None, value=None):
        out.append(_check(f"{cid}", "Options", title, status, message, source, name, value))

    def add_site(cid, title, status, message, source=None, value=None):
        out.append(_check(cid, "Site", title, status, message, source, None, value))

    if not height or not floors:
        add("option.inputs", "Height and floors", NEEDS_INPUT, "Enter a height and floor count.")
    else:
        storey = float(height) / int(floors)
        stilt_height = float(scenario.get("stilt_height_m") or 0) if scenario.get("stilt") else 0.0
        occupied = (float(height) - stilt_height) / int(floors)
        if occupied < MIN_STOREY_HEIGHT_M or storey > MAX_STOREY_HEIGHT_M:
            add("option.inputs", "Height and floors", FAIL, f"{int(floors)} floors in {float(height):g} m gives {occupied:.2f} m per floor. Check the entries.", value=round(occupied, 2))
        else:
            add("option.inputs", "Height and floors", PASS, f"{occupied:.2f} m per floor is plausible.", value=round(occupied, 2))

    headroom = scenario.get("scenario_headroom_m2")
    if headroom is None:
        add("option.far", "FAR capacity", NEEDS_INPUT if gross is None else NOT_CONFIGURED, "Enter or derive a footprint to compare it with FAR capacity." if gross is None else "No FAR benchmark was found to compare against.")
    elif headroom < -0.5 and scenario.get("footprint_source") not in {None, "user-entered design footprint"}:
        # The floor plate was derived, not designed, so this states a limit rather than failing a design.
        fit = float(scenario.get("far_capacity_m2") or 0) / int(floors) if floors else 0
        add("option.far", "FAR capacity", REFER, f"Filling the whole {scenario['footprint_source']} on every floor would exceed FAR capacity by {abs(headroom):,.0f} m². At {int(floors)} floors, about {fit:,.0f} m² per floor fits. Enter a footprint to test a design.", value=headroom)
    elif headroom < -0.5:
        add("option.far", "FAR capacity", FAIL, f"This option exceeds the FAR capacity by {abs(headroom):,.0f} m². Premium FAR and TDR are not counted.", value=headroom)
    else:
        add("option.far", "FAR capacity", PASS, f"{headroom:,.0f} m² of FAR capacity remains.", value=headroom)

    coverage = far.get("coverage") or {}
    coverage_pct = coverage.get("coverage_pct")
    if coverage.get("status") == "chapter4_coverage_not_considered_for_area_up_to_4000":
        add("option.coverage", "Ground coverage", PASS, "The configured amendment does not apply a coverage limit at this plot size.", coverage.get("source"))
    elif coverage_pct is None:
        add("option.coverage", "Ground coverage", NOT_CONFIGURED, coverage.get("message", "No coverage limit is configured for this category."), coverage.get("source"))
    elif footprint is None:
        add("option.coverage", "Ground coverage", NEEDS_INPUT, f"Coverage is limited to {coverage_pct:g}%. A footprint is needed to test it.", coverage.get("source"))
    else:
        achieved = float(footprint) / area * 100 if area else 0
        allowed = area * float(coverage_pct) / 100
        status = FAIL if float(footprint) > allowed + 0.5 else PASS
        add("option.coverage", "Ground coverage", status, f"{achieved:.1f}% of the plot against a {coverage_pct:g}% limit ({allowed:,.0f} m²).", coverage.get("source"), round(achieved, 2))

    setback = scenario.get("setback_result") or {}
    resolved = setback.get("all_round_m") is not None or all(setback.get(k) is not None for k in ("front_m", "rear_m", "left_m", "right_m"))
    if scenario.get("setback_status") == "manual_scenario_not_rule_result":
        add("option.setback", "Building setbacks", REFER, "These are your what-if setbacks, not the rule result.")
    elif resolved:
        add("option.setback", "Building setbacks", REFER, f"{scenario.get('setback_summary')}. {setback.get('message', '')}".strip(), setback.get("source"))
    else:
        add("option.setback", "Building setbacks", NEEDS_INPUT if setback.get("status") in {"missing_inputs", "side_selection_required"} else NOT_CONFIGURED, setback.get("message", "Setbacks were not determined."), setback.get("source"))

    stilt_rule = (profile or {}).get("stilt_definition")
    if scenario.get("stilt"):
        if not scenario.get("stilt_height_m"):
            add("option.stilt", "Stilt height", NEEDS_INPUT, "Enter the stilt height. It can change which setback table applies and whether the floor counts.")
        elif stilt_rule and float(scenario["stilt_height_m"]) >= float(stilt_rule["max_clear_height_m_exclusive"]):
            add("option.stilt", "Stilt height", REFER, f"{float(scenario['stilt_height_m']):g} m is not below the {stilt_rule['max_clear_height_m_exclusive']:g} m in the base definition. Confirm against later notifications whether it still counts as a stilt.", source_by_id(profile, stilt_rule.get("source_id")))

    limits_tested = False
    for limit in (profile or {}).get("height_limits", []):
        if limit.get("categories") and category not in limit["categories"]:
            continue
        if limit.get("road_width_max_exclusive_m") is not None and not road < float(limit["road_width_max_exclusive_m"]):
            continue
        if limit.get("site_area_max_m2") is not None and not area <= float(limit["site_area_max_m2"]):
            continue
        limits_tested = True
        if not height:
            continue
        measured = float(height)
        if not limit.get("includes_stilt") and scenario.get("stilt"):
            measured -= float(scenario.get("stilt_height_m") or 0)
        src = source_by_id(profile, limit.get("source_id"))
        add(f"option.height.{limit['id']}", "Height limit", FAIL if measured > float(limit["max_height_m"]) else PASS, f"{limit['note']} This option is {measured:g} m.", src)
    if not limits_tested and height and not (profile or {}).get("height_limits"):
        add("option.height", "Height limit", NOT_CONFIGURED, "No height limits are configured for this authority. Check the airport zone and road-width limits.")

    apartment = (profile or {}).get("apartment_rules")
    is_apartment = "apartment" in str(site.get("proposed_use", "")).casefold()
    if is_apartment and apartment and category in apartment.get("categories", []):
        src = source_by_id(profile, apartment.get("source_id"))
        ring = site.get("rmp_ring")
        if "bands" not in apartment:
            if road <= float(apartment["road_width_min_exclusive_m"]):
                add_site("site.apartment", "Apartment eligibility", FAIL, f"{apartment['note']} The road is {road:g} m.", src)
            elif area <= float(apartment.get("municipal_plot_min_exclusive_m2", apartment["plot_min_exclusive_m2"])):
                add_site("site.apartment", "Apartment eligibility", FAIL, f"{apartment['note']} The plot is {area:,.0f} m².", src)
            elif area <= float(apartment["plot_min_exclusive_m2"]):
                add_site("site.apartment", "Apartment eligibility", REFER, f"{apartment['note']} At {area:,.0f} m² this depends on whether the plot is within CMC limits.", src)
            else:
                add_site("site.apartment", "Apartment eligibility", PASS, f"Plot and road meet the rule. {apartment['note']}", src)
        elif road < float(apartment["minimum_road_width_m"]):
            add_site("site.apartment", "Apartment eligibility", FAIL, f"Apartments need a road of at least {apartment['minimum_road_width_m']:g} m.", src)
        elif ring not in {"I", "II", "III"}:
            add_site("site.apartment", "Apartment eligibility", NEEDS_INPUT, "Select the RMP ring. Apartment rules differ between Rings I, II and III.", src)
        else:
            match = None
            for band in apartment["bands"]:
                if ring not in band["rings"]:
                    continue
                if "min_exclusive" in band and not area > band["min_exclusive"]:
                    continue
                if "min_inclusive" in band and not area >= band["min_inclusive"]:
                    continue
                if "max_exclusive" in band and not area < band["max_exclusive"]:
                    continue
                if "max_inclusive" in band and not area <= band["max_inclusive"]:
                    continue
                match = band
                break
            if match is None:
                add_site("site.apartment", "Apartment eligibility", FAIL, f"Apartments are not listed for a {area:,.0f} m² plot in Ring {ring}.", src)
            elif match.get("max_units") and not site.get("dwelling_units"):
                add_site("site.apartment", "Apartment eligibility", NEEDS_INPUT, f"Up to {match['max_units']} units are allowed here. Enter the unit count.", src)
            elif match.get("max_units") and int(site["dwelling_units"]) > int(match["max_units"]):
                add_site("site.apartment", "Apartment eligibility", FAIL, f"{int(site['dwelling_units'])} units exceed the limit of {match['max_units']} at this plot size in Ring {ring}.", src)
            else:
                add_site("site.apartment", "Apartment eligibility", PASS, f"Apartments are listed for this plot size in Ring {ring}.", src)

    envelope = scenario.get("boundary_envelope") or {}
    if boundary:
        env_area = envelope.get("area_m2")
        if envelope.get("status") == "no_remaining_envelope":
            add("option.envelope", "Buildable envelope", FAIL, envelope.get("message", "Setbacks leave no buildable area."))
        elif env_area is None:
            add("option.envelope", "Buildable envelope", NEEDS_INPUT, envelope.get("message", "The envelope could not be calculated."))
        elif scenario.get("footprint_exceeds_envelope"):
            add("option.envelope", "Buildable envelope", FAIL, f"The footprint of {footprint:,.0f} m² is larger than the {env_area:,.0f} m² envelope.", value=env_area)
        elif envelope.get("is_split") or envelope.get("has_narrow_neck"):
            add("option.envelope", "Buildable envelope", REFER, " ".join(envelope.get("warnings", [])), value=env_area)
        else:
            add("option.envelope", "Buildable envelope", PASS, f"A {env_area:,.0f} m² envelope remains after setbacks.", value=env_area)

    levels = int(scenario.get("basement_levels") or 0)
    if levels:
        limits = (profile or {}).get("basement_limits")
        src = source_by_id(profile, (limits or {}).get("source_id"))
        if limits and levels > int(limits["max_levels"]):
            add("option.basement", "Basement", FAIL, f"{levels} levels exceed the {limits['max_levels']} permitted for car parking.", src)
        elif limits and area < float(limits["no_parking_below_site_area_m2"]):
            add("option.basement", "Basement", FAIL, f"Basement car parking is not permitted on sites below {limits['no_parking_below_site_area_m2']:g} m².", src)
        elif ((site.get("overlays") or {}).get("flood_prone") or {}).get("status") == "present":
            add("option.basement", "Basement", FAIL if limits else REFER, "This site is recorded as flood-prone or low-lying, where basements may not be permitted.", src)
        elif (scenario.get("basement_setback_result") or {}).get("front_m") is None and (scenario.get("basement_setback_result") or {}).get("all_round_m") is None:
            add("option.basement", "Basement", NOT_CONFIGURED, (scenario.get("basement_setback_result") or {}).get("message", "Basement setbacks were not determined."))
        else:
            add("option.basement", "Basement", REFER, f"Setbacks: {scenario.get('basement_setback_summary')}. Confirm the road-side setback: the 2026 amendment says the lesser of the building setback and 2.0 m, while SiteIQ keeps the larger building setback on road edges.", src)

    if gross:
        cars, status, message = _parking_cars(profile or {}, site, float(gross))
        add("option.parking", "Parking", status, message, source_by_id(profile, ((profile or {}).get("parking_rule") or {}).get("source_id")), cars)
        ramp = (profile or {}).get("ramp_rule")
        if cars is not None and ramp and levels:
            band = next(b for b in ramp["bands"] if b["max_cars"] is None or cars <= b["max_cars"])
            add("option.ramps", "Basement ramps", REFER, f"For about {cars} cars: {band['text']}, unless car lifts are used under Regulation 3.9(x).", source_by_id(profile, ramp.get("source_id")))

    if height:
        rule = statewide["fire_high_rise"]
        h = float(height)
        if h >= rule["noc_height_m"]:
            add("option.fire", "Fire NOC", REFER, rule["message_noc"], rule["source"])
        elif h >= rule["nbc_high_rise_height_m"]:
            add("option.fire", "Fire NOC", REFER, rule["message_band"], rule["source"])
        else:
            add("option.fire", "Fire NOC", PASS, rule["message_below"], rule["source"])

    if gross:
        rule = statewide["environmental_clearance"]
        basement_area = levels * float((scenario.get("basement_boundary_envelope") or {}).get("area_m2") or footprint or 0)
        built_up = float(gross) + basement_area
        if built_up > rule["built_up_area_m2_min_exclusive"]:
            add("option.eia", "Environmental clearance", REFER, f"About {built_up:,.0f} m² built up. {rule['message']}", rule["source"], round(built_up))
        else:
            add("option.eia", "Environmental clearance", PASS, f"About {built_up:,.0f} m² built up, below the {rule['built_up_area_m2_min_exclusive']:,.0f} m² trigger.", rule["source"], round(built_up))
    return out


def calculation_checks(report: dict) -> list[dict]:
    """Checks on what the geometry and floor areas reveal about the calculation itself."""
    out = []
    boundary = report.get("boundary_analysis") or {}
    span = boundary.get("dimension_range")
    percentage = any((s.get("setback_result") or {}).get("status") == "nominal_calculation_requires_site_geometry_check" and (s.get("setback_result") or {}).get("all_round_m") is None for s in report.get("scenarios", []))
    if span and percentage and (span["depth_max_m"] > span["depth_min_m"] * 1.05 or span["width_max_m"] > span["width_min_m"] * 1.05):
        out.append(_check("site.dimensions", "Site", "Depth and width vary", REFER, f"Depth runs from {span['depth_min_m']:g} to {span['depth_max_m']:g} m and width from {span['width_min_m']:g} to {span['width_max_m']:g} m. Percentage setbacks here use the overall dimensions, which is the cautious reading. Confirm how the authority measures an irregular plot.", value=span))
    widening = report.get("road_widening")
    if widening:
        capacity = widening.get("capacity_if_land_excluded_m2")
        extra = f" If the authority does not count that land, capacity falls from {float(report.get('maximum_far_area_m2') or 0):,.0f} to {capacity:,.0f} m²." if capacity is not None else ""
        out.append(_check("far.road_widening", "FAR", "Road widening", REFER, f"Widening takes about {widening['area_taken_m2']:,.0f} m² along edge {widening['edge'] + 1}.{extra} Any TDR for the surrendered land is not calculated.", value=widening))
    for s in report.get("scenarios", []):
        if s.get("gross_concept_area_m2") is None:
            continue
        name = s.get("name")
        refused = float(s.get("far_exclusion_refused_m2") or 0)
        if refused > 0:
            out.append(_check("option.far_exclusions", "Options", "FAR exclusions", REFER, f"{refused:,.0f} m² you entered was not deducted, because this authority's plan does not list it as excluded from FAR.", option=name, value=refused))
        elif s.get("far_exclusions_entered"):
            out.append(_check("option.far_exclusions", "Options", "FAR exclusions", REFER, f"{float(s.get('far_excluded_m2') or 0):,.0f} m² is excluded from FAR, as you entered it. Confirm it against the design.", option=name, value=s.get("far_excluded_m2")))
        else:
            out.append(_check("option.far_exclusions", "Options", "FAR exclusions", REFER, "No exclusions were entered, so all floor area counts towards FAR. Enter parking and core areas where the rule allows them.", option=name))
    return out


def project_checks(site: dict, profile: Optional[dict] = None, scenarios: Optional[list[dict]] = None) -> list[dict]:
    rule = load_statewide_rules()["rera"]
    area = float(site.get("site_area_m2") or 0)
    units = site.get("dwelling_units")
    out = []
    if area > rule["land_area_m2"] or (units and int(units) > rule["apartments"]):
        out.append(_check("project.rera", "Approvals", "RERA registration", REFER, rule["message"], rule["source"]))
    elif units:
        out.append(_check("project.rera", "Approvals", "RERA registration", REFER, "This project may be below the limits. " + rule["message"], rule["source"]))
    else:
        out.append(_check("project.rera", "Approvals", "RERA registration", NEEDS_INPUT, "Enter the dwelling unit count, if any, to test the RERA limits.", rule["source"]))
    access = (profile or {}).get("accessibility_rule")
    gross = max([float(s.get("gross_concept_area_m2") or 0) for s in (scenarios or [])], default=0)
    if access and site.get("proposed_use") in access["uses"] and gross >= float(access["covered_area_min_m2"]):
        out.append(_check("project.accessibility", "Approvals", "Accessibility", REFER, f"{access['note']} SiteIQ does not check the design details.", source_by_id(profile, access.get("source_id"))))
    else:
        out.append(_check("project.accessibility", "Approvals", "Accessibility", NOT_CONFIGURED, "Detailed accessibility standards are not configured. Check the applicable building bye-laws and NBC 2016."))
    services = (profile or {}).get("services_rule")
    if services and area >= float(services["rainwater_min_plot_m2"]):
        out.append(_check("project.services", "Approvals", "Rainwater and solar", REFER, f"{services['note']} Water, sewerage, STP and transformer rules are not configured.", source_by_id(profile, services.get("source_id"))))
    else:
        out.append(_check("project.services", "Approvals", "Services and utilities", NOT_CONFIGURED, "Water, sewerage, STP, rainwater harvesting and transformer rules are not configured for this case. Confirm them with the local agencies."))
    typology = (profile or {}).get("housing_typology_rule")
    if typology and site.get("proposed_use") == "Individual house / villa":
        out.append(_check("project.typology", "Approvals", "Semi-detached or row housing", REFER, f"If these are attached houses: {typology['note']}", source_by_id(profile, typology.get("source_id"))))
    separation = (profile or {}).get("building_separation")
    tallest = max([float(s.get("height_m") or 0) for s in (scenarios or [])], default=0)
    if separation and tallest:
        out.append(_check("project.separation", "Approvals", "Multiple blocks", REFER, f"{separation['note']} At {tallest:g} m that is {tallest / 2:g} m. Each option is assessed as a single block, so check this if you plan several.", source_by_id(profile, separation.get("source_id")), value=tallest / 2))
    else:
        out.append(_check("project.separation", "Approvals", "Multiple blocks", NOT_CONFIGURED, "Building separation is not configured for this authority. Each option is assessed as a single block."))
    return out


VERDICTS = {
    "BLOCKED": "At least one check fails. This scheme cannot proceed as entered.",
    "INCOMPLETE": "Information is missing, so these figures may change. Complete the open items.",
    "PROVISIONAL": "No check fails, but some could not be confirmed. Not for design freeze or sanction.",
    "READY_FOR_REVIEW": "Every check passes on a verified rule profile. A registered architect must still review it.",
}


def group_checks(checks: list[dict]) -> list[dict]:
    """Merge checks that say the same thing for several options into one entry naming them all."""
    grouped: dict[tuple, dict] = {}
    for check in checks:
        key = (check["id"], check["status"], check["message"], check["group"])
        if key not in grouped:
            grouped[key] = {**check, "options": [check["option"]] if check.get("option") else []}
        elif check.get("option") and check["option"] not in grouped[key]["options"]:
            grouped[key]["options"].append(check["option"])
    out = []
    for check in grouped.values():
        names = check["options"]
        check["option"] = None if not names else ", ".join(names)
        out.append(check)
    return out


def summarise(checks: list[dict]) -> dict:
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (PASS, FAIL, NEEDS_INPUT, NOT_CONFIGURED, REFER)}
    if counts[FAIL]:
        verdict = "BLOCKED"
    elif counts[NEEDS_INPUT]:
        verdict = "INCOMPLETE"
    elif counts[NOT_CONFIGURED] or counts[REFER]:
        verdict = "PROVISIONAL"
    else:
        verdict = "READY_FOR_REVIEW"
    return {"code": verdict, "message": VERDICTS[verdict], "counts": counts, "total": len(checks)}
