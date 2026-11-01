"""Streamlit-independent state helper for location identification.

This module is intentionally testable without importing Streamlit. In the UI,
call ``apply_location_identification`` from a widget callback (which runs before
widgets are instantiated on the subsequent Streamlit rerun).
"""
from __future__ import annotations
from typing import Any, Callable, MutableMapping, Collection

from .location import auto_identify_site


def apply_location_identification(
    state: MutableMapping[str, Any],
    allowed_authority_keys: Collection[str],
    identify_fn: Callable[..., dict] = auto_identify_site,
) -> dict:
    """Resolve the location and update UI state atomically.

    The caller must invoke this from a Streamlit ``on_click`` callback, not
    inline after rendering widgets that use the same session-state keys.
    """
    state["siteiq_location_error"] = ""
    # Clear prior results first so a failed new lookup cannot leave a stale authority result visible.
    state.pop("siteiq_location_detection", None)
    state.pop("siteiq_report", None)

    active_boundary = state.get("siteiq_boundary") or {}
    # A selected KML lookup point may be used before applying its geometry, but the UI
    # must warn that area calculations still use the active boundary until Apply is clicked.
    kml_override = state.get("siteiq_kml_lookup_override") or {}
    boundary_point = kml_override.get("point_wgs84")
    boundary_point_source = kml_override.get("source_file") or "selected KML"
    if not boundary_point and active_boundary.get("source_type") == "kml":
        boundary_point = active_boundary.get("source_location_point_wgs84") or active_boundary.get("source_centroid_wgs84")
        boundary_point_source = active_boundary.get("source_file") or "active KML boundary"
    lookup_coords_text = str(state.get("siteiq_coordinates", "") or "")
    lookup_map_url = str(state.get("siteiq_map_url", "") or "")
    if boundary_point and len(boundary_point) >= 2:
        # KML coordinates are [longitude, latitude]; UI input is latitude, longitude.
        lookup_coords_text = f"{float(boundary_point[1]):.7f}, {float(boundary_point[0]):.7f}"
        lookup_map_url = ""  # prevent an unrelated/stale map link overriding the imported boundary
        state["siteiq_coordinates"] = lookup_coords_text
        if kml_override.get("point_wgs84"):
            state["siteiq_location_coordinate_source"] = "Selected KML boundary lookup point"
        else:
            state["siteiq_location_coordinate_source"] = "Applied KML boundary location point"
    if active_boundary and active_boundary.get("use_computed_area", True):
        try:
            site_area = float(active_boundary.get("area_m2", 0) or 0)
        except (TypeError, ValueError):
            site_area = 0.0
    else:
        # The actual input widget key is siteiq_site_area (not siteiq_site_area_m2).
        try:
            site_area = float(state.get("siteiq_site_area", 0) or 0)
        except (TypeError, ValueError):
            site_area = 0.0

    try:
        road_width = float(state.get("siteiq_road_width", 0) or 0)
    except (TypeError, ValueError):
        road_width = 0.0

    detection = identify_fn(
        address=str(state.get("siteiq_address", "") or ""),
        map_url=lookup_map_url,
        coordinates_text=lookup_coords_text,
        site_area_m2=site_area,
        proposed_use=str(state.get("siteiq_proposed_use", "Residential apartments") or "Residential apartments"),
        road_width_m=road_width,
        current_authority_key=state.get("siteiq_authority_key", "other_karnataka"),
        current_zone=state.get("siteiq_official_zone", "Not verified"),
        current_approval_path=state.get("siteiq_approval_path", "Not sure / needs confirmation"),
    )

    state["siteiq_location_detection"] = detection
    coords_text = (detection.get("coordinates") or {}).get("text")
    if coords_text:
        # Safe because Streamlit executes this helper inside the button callback,
        # before the coordinates widget is instantiated for this rerun.
        state["siteiq_coordinates"] = coords_text
    if not boundary_point:
        detected_source = detection.get("location_source")
        if detected_source:
            state["siteiq_location_coordinate_source"] = detected_source
    state["siteiq_input_coordinate_comparison"] = detection.get("input_coordinate_comparison")

    geocoded_address = detection.get("geocoded_address")
    if geocoded_address and not str(state.get("siteiq_address", "") or "").strip():
        state["siteiq_address"] = geocoded_address

    suggested_authority = detection.get("suggested_authority_key")
    if suggested_authority in allowed_authority_keys:
        state["siteiq_authority_key"] = suggested_authority

    zone_result = detection.get("zone") or {}
    if zone_result.get("status") == "matched_polygon_layer":
        state["siteiq_official_zone"] = zone_result.get("value", "Not verified")

    route_result = detection.get("approval_route") or {}
    suggested_route = route_result.get("suggested_value")
    if suggested_route:
        state["siteiq_approval_path"] = suggested_route

    state.pop("siteiq_report", None)
    return detection
