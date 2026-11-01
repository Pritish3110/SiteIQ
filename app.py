from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from shapely.geometry import Polygon, shape as shapely_shape

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from siteiq.engine import (
    load_authority_registry, find_authority, load_rule_profile,
    land_use_categories, category_by_label, match_far_rule,
    calculate_setbacks, calculate_basement_setbacks, build_report,
)
from siteiq.exporters import (
    build_pdf_report, build_pptx_report,
    build_a3_comparison_board_pdf, build_a3_comparison_board_pptx,
)
from siteiq.boundary import (
    parse_uploaded_boundary, polygon_from_candidate, candidate_edge_lengths,
    calculate_setback_envelope, make_boundary_preview, make_boundary_edge_preview,
    export_boundary_dxf, UNIT_TO_M,
)
from siteiq.location import (
    save_geojson_layer, AUTHORITY_LAYER, ZONE_LAYER,
)
from siteiq.location_ui import apply_location_identification

st.set_page_config(page_title="SiteIQ | Rule-driven feasibility", page_icon="📐", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1500px;}
[data-testid="stMetric"] {background:#f3f6f4; border:1px solid #dce5e0; padding:12px; border-radius:12px;}
div.stButton>button,div.stDownloadButton>button {border-radius:8px;font-weight:600;}
.small-note {font-size:.86rem;color:#5d686a;}
</style>
""", unsafe_allow_html=True)

registry = load_authority_registry()
authorities = registry.get("authorities", [])
authority_labels = {a["key"]: a["name"] for a in authorities}

def _profile_for(key: str | None):
    try:
        authority = find_authority(registry, key or "other_karnataka")
    except KeyError:
        authority = find_authority(registry, "other_karnataka")
    return authority, load_rule_profile(authority.get("rule_profile")) if authority.get("rule_profile") else None


def _load_nandi_sample():
    sample = json.loads((ROOT / "sample_data" / "nandi_housing_test_case.json").read_text(encoding="utf-8"))
    sample.pop("sample_notes", None)
    for k, v in sample.items():
        st.session_state[f"siteiq_{k}"] = v
    # Maintain easy-to-review sample options in the new workflow.
    st.session_state["siteiq_num_options"] = min(4, max(2, len(sample.get("scenarios", []))))
    st.session_state["siteiq_sample_loaded"] = True
    st.session_state.pop("siteiq_report", None)


def _val(key, default=None):
    return st.session_state.get(f"siteiq_{key}", default)


def _candidate_status(profile, category, area, road, surrounding_zone=None, proposed_use=None):
    if not profile:
        return {"status":"not_configured", "message":"No current rules profile is configured for this planning authority. SiteIQ will not use another authority's FAR."}
    if not category or category == "Select a land-use category":
        return {"status":"category_required", "message":"Select the official land-use category to run the FAR lookup."}
    if area <= 0 or road <= 0:
        return {"status":"inputs_required", "message":"Enter a positive plot area and road width to run the FAR lookup."}
    return match_far_rule(profile, category, area, road, surrounding_zone=surrounding_zone, proposed_use=proposed_use)


def _reset_assessment():
    st.session_state.pop("siteiq_report", None)


def _identify_site_callback():
    """Run before the next widget render so prefill writes are Streamlit-safe."""
    try:
        apply_location_identification(st.session_state, set(authority_labels))
    except Exception as exc:
        st.session_state["siteiq_location_error"] = f"{type(exc).__name__}: {exc}"


def _use_selected_kml_location_callback():
    """Use the currently selected KML feature as a location search point, even before area application."""
    candidates = st.session_state.get("siteiq_boundary_candidates", []) or []
    candidate_id = str(st.session_state.get("siteiq_selected_candidate", ""))
    candidate = next((c for c in candidates if str(c.get("candidate_id")) == candidate_id), None)
    if candidate is None and len(candidates) == 1:
        candidate = candidates[0]
    if not candidate or candidate.get("source_type") != "kml":
        st.session_state["siteiq_location_error"] = "Select a KML/KMZ candidate first."
        return
    point = candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84")
    if not point or len(point) < 2:
        st.session_state["siteiq_location_error"] = "This KML feature has no usable location point. Try a valid polygon or closed perimeter path."
        return
    uploaded = st.session_state.get("siteiq_boundary_file")
    filename = getattr(uploaded, "name", "selected KML") or "selected KML"
    fingerprint = st.session_state.get("siteiq_boundary_fingerprint")
    st.session_state["siteiq_kml_lookup_override"] = {
        "point_wgs84": [float(point[0]), float(point[1])],
        "source_file": filename,
        "source_fingerprint": fingerprint,
        "candidate_id": str(candidate.get("candidate_id")),
        "location_method": candidate.get("source_location_method", "KML location point"),
    }
    st.session_state["siteiq_pending_boundary_location"] = {
        "lon": float(point[0]), "lat": float(point[1]),
        "source_label": "Selected KML boundary lookup point",
    }
    st.session_state.pop("siteiq_location_error", None)


# When a selected/applied KML feature supplies a geographic location point, consume the handoff
# before widgets are instantiated and rerun jurisdiction/source identification from the KML,
# rather than a stale or unrelated address-geocoded point.
_pending_boundary_location = st.session_state.pop("siteiq_pending_boundary_location", None)
if _pending_boundary_location:
    old_text = str(st.session_state.get("siteiq_coordinates", "") or "")
    st.session_state["siteiq_coordinates_before_kml"] = old_text
    lon = float(_pending_boundary_location["lon"])
    lat = float(_pending_boundary_location["lat"])
    st.session_state["siteiq_coordinates"] = f"{lat:.7f}, {lon:.7f}"
    st.session_state["siteiq_location_coordinate_source"] = str(_pending_boundary_location.get("source_label") or "Applied KML boundary location point")
    # Keep the raw centroid as metadata and compute how far it differs from the prior point.
    previous = None
    try:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*[,;/ ]\s*(-?\d+(?:\.\d+)?)", old_text)
        if m:
            previous = (float(m.group(1)), float(m.group(2)))
    except Exception:
        previous = None
    distance_km = None
    if previous:
        try:
            from math import radians, sin, cos, asin, sqrt
            old_lat, old_lon = previous
            dlat = radians(lat-old_lat); dlon = radians(lon-old_lon)
            a = sin(dlat/2)**2 + cos(radians(old_lat))*cos(radians(lat))*sin(dlon/2)**2
            distance_km = 6371.0088 * 2 * asin(sqrt(min(1.0, a)))
        except Exception:
            distance_km = None
    st.session_state["siteiq_kml_previous_coordinate_distance_km"] = distance_km
    st.session_state.pop("siteiq_location_detection", None)
    _identify_site_callback()


st.title("SiteIQ")
st.subheader("Rule-driven architectural feasibility | v0.4.7")
st.caption("Workflow: identify jurisdiction → derive plot area from boundary → select regulated land-use category → enter road width → identify FAR benchmark → compare height, setbacks and basements.")

with st.sidebar:
    st.markdown("### Test / reset")
    if st.button("Load Nandi Housing example", use_container_width=True):
        _load_nandi_sample()
        st.rerun()
    if st.button("Clear assessment results", use_container_width=True):
        st.session_state.pop("siteiq_report", None)
        st.session_state.pop("siteiq_boundary", None)
        st.session_state.pop("siteiq_location_detection", None)
        st.session_state.pop("siteiq_boundary_candidates", None)
        st.session_state.pop("siteiq_boundary_file_fingerprint", None)
        st.session_state.pop("siteiq_kml_lookup_override", None)
        st.session_state.pop("siteiq_kml_location_auto_prefill_fingerprint", None)
        st.session_state.pop("siteiq_location_coordinate_source", None)
        st.session_state.pop("siteiq_coordinates_before_kml", None)
        st.session_state.pop("siteiq_kml_previous_coordinate_distance_km", None)
        st.rerun()
    st.markdown("---")
    st.markdown("### Rule coverage")
    configured_profiles = [a for a in authorities if a.get("rule_profile") and load_rule_profile(a.get("rule_profile"))]
    draft_only_count = sum(1 for a in authorities if "draft" in str(a.get("status", "")).lower())
    provisional_count = sum(1 for a in configured_profiles if a.get("rule_source_status") == "secondary_copy_pending_official_validation")
    st.write(f"**Profiles available:** {len(configured_profiles)} ({provisional_count} provisional LPA profiles; Bengaluru profile remains partial).")
    st.write(f"**Authorities indexed for review:** {len(authorities)} · **Draft/pending items:** {draft_only_count}.")
    st.caption("Some LPA profiles can now return preliminary FAR candidates from secondary Master Plan copies. They are explicitly provisional and must be reconciled with the operative authority-issued regulations before reliance. A profile suggestion is not proof of jurisdiction.")
    st.markdown("[GBA GIS viewer](https://bbmp.gov.in/gisviewer/) · [BDA master plan](https://eng.bdabangalore.org/masterplan.html)")
    with st.expander("Karnataka authority coverage register", expanded=False):
        st.caption("This is a coverage work queue, not proof that listed rule profiles are configured. The UDD 559 BMR 2025(E) item is a draft source lead and is not enabled for calculations.")
        coverage_rows = []
        for a in authorities:
            coverage_rows.append({
                "Authority": a.get("name", a.get("key", "")),
                "Group": a.get("coverage_group", ""),
                "Status": a.get("status", "not reviewed"),
                "FAR enabled": "Yes (check profile status)" if a.get("rule_profile") and load_rule_profile(a.get("rule_profile")) else "No",
                "Next action": a.get("next_action", a.get("scope_note", "")),
            })
        st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)
        coverage_csv = (ROOT / "rules" / "authority_coverage_matrix.csv")
        if coverage_csv.exists():
            st.download_button("Download coverage matrix (CSV)", data=coverage_csv.read_bytes(), file_name="SiteIQ_Karnataka_Authority_Coverage.csv", mime="text/csv", use_container_width=True)
        st.markdown("[Karnataka Town and Country Planning Act](https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_402_00001_11_1552283484255&filename=11_of_1963.pdf&type=actfile) · [Draft UDD 559 BMR 2025(E) source](https://policyindex.ai/in/gazette/zonal-regulations-for-master-plans-of-different-lpas-within-bmrda-and-it-is-required-to-regulate-the-lpas-within-bmrda-with-uniform-zonal-regulations-to-avoid-confusions-while-hr5z5g)")
    st.markdown("---")
    with st.expander("Administrator tools (optional)", expanded=False):
        st.caption("Ordinary project work does not require GIS uploads. These controls are retained only for an administrator maintaining a verified local boundary/zoning dataset.")
        show_admin_layers = st.checkbox("Enable local GeoJSON layer maintenance", value=False, key="siteiq_show_admin_layers")
        if show_admin_layers:
            with st.form("siteiq_spatial_layers_form_admin", clear_on_submit=False):
                authority_geojson = st.file_uploader("Authority boundary GeoJSON", type=["geojson", "json"], key="siteiq_authority_layer_upload")
                zone_geojson = st.file_uploader("Land-use zone GeoJSON", type=["geojson", "json"], key="siteiq_zone_layer_upload")
                save_layers = st.form_submit_button("Install / update local layers")
            if save_layers:
                try:
                    results = []
                    if authority_geojson is not None:
                        x = save_geojson_layer("authority_boundaries.geojson", authority_geojson.getvalue())
                        results.append(f"Authority layer: {x['valid_polygon_count']} valid polygons")
                    if zone_geojson is not None:
                        x = save_geojson_layer("land_use_zones.geojson", zone_geojson.getvalue())
                        results.append(f"Land-use layer: {x['valid_polygon_count']} valid polygons")
                    if results:
                        st.success(" · ".join(results))
                        st.info("Run location identification again to use the newly installed layers.")
                    else:
                        st.warning("Choose at least one GeoJSON file.")
                except Exception as exc:
                    st.error(f"Layer install failed: {exc}")
            st.caption(f"Local layer status — authority: {'installed' if AUTHORITY_LAYER.exists() else 'not installed'}; zoning: {'installed' if ZONE_LAYER.exists() else 'not installed'}.")

# -----------------------------------------------------------------------------
# STEP 1 — location and jurisdiction. Location result is not inferred from text alone.
# -----------------------------------------------------------------------------
st.markdown("## 1 · Identify the jurisdiction")
st.caption("Location priority: selected/applied KML boundary → supplied Google Maps link → manually entered coordinates → address geocoding. A supplied map link takes priority over stale coordinate text; if the link cannot be resolved, SiteIQ stops instead of silently using another point.")
left, right = st.columns(2)
with left:
    project_name = st.text_input("Project name", value=_val("project_name", "Untitled site"), key="siteiq_project_name")
    client_name = st.text_input("Client / project code (optional)", value=_val("client", ""), key="siteiq_client")
    address = st.text_input("Site address / locality", value=_val("address", ""), key="siteiq_address")
    map_url = st.text_input("Google Maps link (optional)", value=_val("map_url", ""), key="siteiq_map_url")
    coordinates = st.text_input("Coordinates (optional; latitude, longitude)", value=_val("coordinates", ""), key="siteiq_coordinates")
with right:
    st.markdown("**Automatic location & official-source lookup**")
    st.write("SiteIQ looks up the location, checks any verified local map layers already available, and finds the relevant official authority/map pages. Where a public planning map has no verified point-query service, the zone is left unconfirmed instead of guessed.")
    st.button(
        "Identify site and find official sources",
        type="primary",
        key="siteiq_identify",
        on_click=_identify_site_callback,
    )
    if st.session_state.get("siteiq_location_error"):
        st.error(f"Location could not be resolved: {st.session_state['siteiq_location_error']}")

# Avoid silently showing a location result for a stale address when a new KML is waiting to be applied.
_current_upload = st.session_state.get("siteiq_boundary_file")
_active_boundary_for_warning = st.session_state.get("siteiq_boundary") or {}
try:
    _upload_name = str(getattr(_current_upload, "name", "") or "")
    _upload_bytes = _current_upload.getvalue() if _current_upload is not None and hasattr(_current_upload, "getvalue") else b""
    _upload_fingerprint = hashlib.sha256(_upload_bytes).hexdigest() if _upload_bytes else None
except Exception:
    _upload_name, _upload_fingerprint = "", None
_active_fingerprint = _active_boundary_for_warning.get("source_fingerprint")
_kml_override = st.session_state.get("siteiq_kml_lookup_override") or {}
_override_fp = _kml_override.get("source_fingerprint")
if _upload_name.lower().endswith((".kml", ".kmz")) and _upload_fingerprint and _upload_fingerprint != _active_fingerprint:
    if _override_fp == _upload_fingerprint:
        active_name = _active_boundary_for_warning.get("source_file") or "no active boundary"
        st.warning(f"Location lookup is using the selected KML '{_upload_name}', but the area/envelope still uses {active_name}. Apply the selected KML boundary below before generating the feasibility report, so location and geometry refer to the same parcel.")
    else:
        st.warning(f"KML file '{_upload_name}' is uploaded/selected but has not been applied as the active boundary. The coordinates currently shown may still describe the address above. In Step 2, select the correct KML feature and use 'Use selected KML location for authority lookup' or apply the boundary before relying on the authority result.")

detection = st.session_state.get("siteiq_location_detection")
if detection:
    auth = detection.get("authority", {})
    zres = detection.get("zone", {})
    rres = detection.get("approval_route", {})
    c1, c2, c3 = st.columns(3)
    if auth.get("status") == "matched_polygon_layer":
        c1.success("Authority matched to installed boundary layer")
    else:
        c1.warning("Authority is a provisional candidate")
    c1.write(auth.get("label") or authority_labels.get(auth.get("key"), auth.get("key")) or "Not identified")
    c1.caption(auth.get("reason", ""))
    if auth.get("source_url"):
        link_label = "Official boundary source" if auth.get("status") == "matched_polygon_layer" else "Geocoder source (indicative only)"
        c1.markdown(f"[{link_label}]({auth['source_url']})")
    if zres.get("status") == "matched_polygon_layer":
        c2.success("Land-use zone matched to installed layer")
    else:
        c2.warning("Official zone not verified")
    c2.write(zres.get("value", "Not verified"))
    c2.caption(zres.get("reason", ""))
    if zres.get("source_url"):
        c2.markdown(f"[Zone source]({zres['source_url']})")
    c3.info("Approval route: suggestion only")
    c3.write(rres.get("suggested_value", "Needs confirmation"))
    c3.caption(rres.get("reason", ""))
    st.caption(detection.get("privacy_note", ""))
    coordinate_source = str(st.session_state.get("siteiq_location_coordinate_source", "") or detection.get("location_source", ""))
    resolved_coords_text = (detection.get("coordinates") or {}).get("text", "")
    if coordinate_source == "Google Maps link":
        st.info(f"Location used for authority lookup: Google Maps link coordinates ({resolved_coords_text}). The typed address is context only; the resolved map-link point drove this lookup.")
        comparison = detection.get("input_coordinate_comparison") or {}
        if comparison.get("mismatch"):
            st.warning(f"Location mismatch detected: the typed coordinates were about {comparison.get('distance_km', 0):.1f} km from the supplied Google Maps link. SiteIQ used the map-link coordinates and did not use the old coordinate value. Confirm that the map pin marks the intended parcel.")
        resolved_url = (detection.get("map_link_resolution") or {}).get("resolved_url", "")
        if resolved_url and resolved_url != (detection.get("map_url") or ""):
            st.caption(f"Resolved map URL: {resolved_url}")
    if coordinate_source.startswith(("Applied KML boundary", "Selected KML boundary")):
        kml_coords = (detection.get("coordinates") or {}).get("text", "")
        reverse_name = detection.get("geocoded_address") or (detection.get("reverse_geocode") or {}).get("display_name", "")
        st.info(f"Location lookup is based on the selected/applied KML location point ({kml_coords}), not the earlier address-derived point. Reverse-geocoded context: {reverse_name or 'not available'}. This is a search point; it does not independently prove the planning boundary.")
        previous_distance = st.session_state.get("siteiq_kml_previous_coordinate_distance_km")
        if previous_distance is not None and previous_distance > 1.0:
            st.warning(f"The previous coordinate was approximately {previous_distance:.1f} km from the imported KML boundary. Your earlier address/map point may describe a different site; verify the address and parcel before proceeding.")
        override = st.session_state.get("siteiq_kml_lookup_override") or {}
        active = st.session_state.get("siteiq_boundary") or {}
        if override and override.get("source_fingerprint") != active.get("source_fingerprint"):
            st.warning("This KML location is being used for authority identification only. The active plot area has not been updated from this file yet. Apply this exact boundary in Step 2 before calculating FAR or setbacks.")
    public_sources = detection.get("public_sources") or []
    if public_sources:
        with st.expander("Suggested official maps and regulations for this location", expanded=True):
            st.caption("These official reference pages were selected from the location context. This is a curated source lookup, not a live zoning-map query; a page link is not the same as a verified GIS polygon match.")
            for source in public_sources:
                st.markdown(f"**[{source.get('title', 'Official source')}]({source.get('url', '#')})**")
                st.caption(source.get("note", ""))
    if auth.get("status") != "matched_polygon_layer":
        st.info("No verified planning-authority boundary matched this point automatically. SiteIQ has removed the need to upload GIS files in the normal workflow, but this location currently yields a provisional candidate from public map/address context. Confirm the parcel against the authority's official map before treating its FAR or approval route as statutory.")
    if zres.get("status") != "matched_polygon_layer":
        st.warning("The official land-use zone is not yet machine-verified. SiteIQ has surfaced the most relevant official map sources above; it will not infer a land-use category from an address alone.")

current_authority_default = _val("authority_key", None)
if current_authority_default not in authority_labels:
    current_authority_default = (detection or {}).get("suggested_authority_key") or "other_karnataka"
st.markdown("### Rules profile selected for this assessment")
authority_key = st.selectbox(
    "Planning authority / rules profile", options=[a["key"] for a in authorities],
    format_func=lambda key: authority_labels[key],
    index=[a["key"] for a in authorities].index(current_authority_default),
    key="siteiq_authority_key",
    help="SiteIQ includes a partial Bengaluru RMP 2015 profile and provisional source-transcribed profiles for Hoskote, Kanakapura, Nelamangala and Anekal. Confirm source status, boundary, zone and current rule before relying on a result."
)
authority, profile = _profile_for(authority_key)
if profile:
    st.caption(f"Loaded: {profile.get('profile_name')} · Status: {profile.get('profile_status')} · Last profile review: {profile.get('last_reviewed','not stated')}")
else:
    st.warning("No operative rule profile is configured for this authority yet. You can continue entering the site, but FAR/setback rules will not be borrowed from Bengaluru.")
    if authority.get("scope_note"):
        st.caption(authority.get("scope_note"))
    if authority.get("next_action"):
        st.info("Next source-verification step: " + str(authority.get("next_action")))

# -----------------------------------------------------------------------------
# STEP 2 — boundary import and plot area derived from geometry.
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 2 · Import the site boundary and calculate its area")
st.caption("Preferred inputs: a closed AutoCAD DXF polyline or a Google Earth KML/KMZ polygon. A vector PDF may work after scale calibration. Native DWG should be saved as DXF. Scanned raster PDFs need tracing/vectorisation first.")
with st.expander("Import / inspect boundary", expanded=not bool(st.session_state.get("siteiq_boundary"))):
    uploaded = st.file_uploader("Site boundary file", type=["dxf", "pdf", "kml", "kmz"], key="siteiq_boundary_file")
    if uploaded is not None:
        raw = uploaded.getvalue()
        fingerprint = hashlib.sha256(raw).hexdigest()
        if fingerprint != st.session_state.get("siteiq_boundary_fingerprint"):
            try:
                candidates, meta = parse_uploaded_boundary(uploaded.name, raw)
                st.session_state["siteiq_boundary_candidates"] = candidates
                st.session_state["siteiq_boundary_meta"] = meta
                st.session_state["siteiq_boundary_fingerprint"] = fingerprint
                st.session_state.pop("siteiq_boundary_parse_error", None)
            except Exception as exc:
                st.session_state["siteiq_boundary_candidates"] = []
                st.session_state["siteiq_boundary_parse_error"] = str(exc)
                st.session_state["siteiq_boundary_fingerprint"] = fingerprint
        if st.session_state.get("siteiq_boundary_parse_error"):
            st.error(st.session_state["siteiq_boundary_parse_error"])
    candidates = st.session_state.get("siteiq_boundary_candidates", [])
    meta = st.session_state.get("siteiq_boundary_meta", {})
    # When a newly uploaded KML contains exactly one feature, immediately use its geographic
    # anchor for location identification. Do not auto-choose if several features require user selection.
    if uploaded is not None and str(getattr(uploaded, "name", "")).lower().endswith((".kml", ".kmz")) and len(candidates) == 1:
        only_candidate = candidates[0]
        upload_fp = st.session_state.get("siteiq_boundary_fingerprint")
        active_now = st.session_state.get("siteiq_boundary") or {}
        active_fp_now = active_now.get("source_fingerprint")
        auto_done_fp = st.session_state.get("siteiq_kml_location_auto_prefill_fingerprint")
        point = only_candidate.get("source_location_point_wgs84") or only_candidate.get("source_centroid_wgs84")
        if point and upload_fp and upload_fp != active_fp_now and upload_fp != auto_done_fp:
            st.session_state["siteiq_kml_lookup_override"] = {
                "point_wgs84": [float(point[0]), float(point[1])],
                "source_file": uploaded.name,
                "source_fingerprint": upload_fp,
                "candidate_id": str(only_candidate.get("candidate_id")),
                "location_method": only_candidate.get("source_location_method", "KML location point"),
            }
            st.session_state["siteiq_pending_boundary_location"] = {
                "lon": float(point[0]), "lat": float(point[1]),
                "source_label": "Selected KML boundary lookup point",
            }
            st.session_state["siteiq_kml_location_auto_prefill_fingerprint"] = upload_fp
            st.rerun()
    for warning in meta.get("warnings", []):
        st.caption("• " + warning)
    if candidates:
        ids = [c["candidate_id"] for c in candidates]
        candidate_id = st.selectbox(
            "Detected boundary candidate", ids,
            format_func=lambda cid: next((f"{c['label']} · {len(c['points'])} vertices · {'closed' if c['closed'] else 'open path'}" for c in candidates if c['candidate_id'] == cid), cid),
            key="siteiq_selected_candidate"
        )
        candidate = next(c for c in candidates if c["candidate_id"] == candidate_id)
        source_type = candidate.get("source_type")
        factor = candidate.get("scale_to_m")
        if source_type == "kml":
            st.info("KML/KMZ coordinates can be used to locate the site before its area is applied. Verify that the selected feature follows the intended parcel boundary.")
            if candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84"):
                st.button(
                    "Use selected KML location for authority lookup",
                    key="siteiq_use_kml_location",
                    help="Uses this feature's geographic anchor to refresh the location lookup. This does not apply its area; use the Apply boundary button below before calculating feasibility.",
                    on_click=_use_selected_kml_location_callback,
                )
                st.caption("Location-only lookup is useful even for an open perimeter path. Plot area and setbacks still require a valid/confirmed boundary below.")
        elif factor is not None:
            st.info(f"Drawing-unit metadata found: {candidate.get('source_units')}; conversion {factor:g} metres per drawing unit. Confirm against a known survey dimension.")
            scale_choice = st.radio("Scale method", ["Use drawing-unit metadata", "Calibrate against a known edge"], horizontal=True, key="siteiq_scale_method_known")
            if scale_choice.startswith("Calibrate"):
                factor = None
        else:
            st.warning("Drawing scale is not known. Confirm CAD units or calibrate using a known boundary dimension.")
            scale_choice = st.radio("Scale method", ["Choose CAD units", "Calibrate against a known edge"], horizontal=True, key="siteiq_scale_method_unknown")
            if source_type == "dxf" and scale_choice == "Choose CAD units":
                unit = st.selectbox("CAD drawing units", ["Metres", "Millimetres", "Centimetres", "Feet", "Inches"], key="siteiq_cad_units")
                factor = {"Metres":1.0, "Millimetres":0.001, "Centimetres":0.01, "Feet":0.3048, "Inches":0.0254}[unit]
            else:
                factor = None
        edge_lengths_raw = candidate_edge_lengths(candidate.get("points", []))
        if factor is None and source_type in ("pdf", "dxf"):
            edge_opts = {f"Edge {e['edge_index']+1} · {e['length']:.3f} drawing units":e['edge_index'] for e in edge_lengths_raw}
            chosen_edge_label = st.selectbox("Known edge to calibrate", list(edge_opts), key="siteiq_calibration_edge")
            known_m = st.number_input("Actual surveyed length of selected edge (m)", min_value=0.01, value=float(_val("known_edge_m", 10.0)), step=0.5, key="siteiq_known_edge_m")
            raw_len = next(e["length"] for e in edge_lengths_raw if e["edge_index"] == edge_opts[chosen_edge_label])
            factor = known_m / raw_len if raw_len > 0 else None
            if factor:
                st.caption(f"Scale factor: {factor:.8f} m per drawing unit. Assumes no non-uniform distortion.")
        close_open = False
        if not candidate.get("closed", False):
            close_open = st.checkbox("Confirm last-to-first segment is a legal boundary edge", value=False, key="siteiq_close_open_boundary")
        poly = None
        validation = {"status":"scale_required", "message":"A reliable drawing scale is required."}
        if factor:
            poly, validation = polygon_from_candidate(candidate, scale_to_m=factor, close_open=close_open)
        if poly is None:
            st.error(validation.get("message", "Boundary could not be validated."))
        else:
            st.success(f"Boundary checked: {validation['area_m2']:,.2f} m² · perimeter {validation['perimeter_m']:,.2f} m · {validation['vertex_count']} vertices.")
            with st.expander("Numbered boundary preview — select road-facing edges", expanded=True):
                fig = make_boundary_edge_preview(poly)
                st.pyplot(fig, clear_figure=True)
                edge_rows = candidate_edge_lengths(list(poly.exterior.coords)[:-1])
                edge_labels = {f"Edge {e['edge_index']+1} · {e['length']:.2f} m":e['edge_index'] for e in edge_rows}
                front_default = st.session_state.get("siteiq_front_edges", [])
                front_labels_default = [label for label, ix in edge_labels.items() if ix in front_default]
                front_labels = st.multiselect("Road-facing/frontage edge(s)", list(edge_labels), default=front_labels_default, key="siteiq_front_edge_labels")
                excluded = [label for label,ix in edge_labels.items() if label in front_labels]
                rear_default = st.session_state.get("siteiq_rear_edges", [])
                rear_labels_default = [label for label, ix in edge_labels.items() if ix in rear_default and label not in excluded]
                rear_labels = st.multiselect("Rear edge(s), if known", [x for x in edge_labels if x not in excluded], default=rear_labels_default, key="siteiq_rear_edge_labels")
                use_poly_area = st.checkbox("Use the polyline-calculated area for FAR calculations", value=True, key="siteiq_use_poly_area")
                st.caption("If this area differs from the title/survey area, resolve the discrepancy before design freeze. SiteIQ does not decide which legal area prevails.")
                if st.button("Apply boundary and derived area", type="primary", key="siteiq_apply_boundary"):
                    metric_points = [(float(x)*float(factor), float(y)*float(factor)) for x,y in candidate["points"]]
                    st.session_state.pop("siteiq_kml_lookup_override", None)
                    st.session_state["siteiq_boundary"] = {
                        "source_file":uploaded.name, "source_type":source_type,
                        "source_units":candidate.get("source_units"), "scale_to_m":float(factor),
                        "points_m":metric_points, "area_m2":float(validation["area_m2"]),
                        "perimeter_m":float(validation["perimeter_m"]), "vertex_count":int(validation["vertex_count"]),
                        "is_convex":bool(validation["is_convex"]), "validation_status":validation["status"],
                        "validation_notes":validation.get("notes", []), "use_computed_area":bool(use_poly_area),
                        "front_edges":[edge_labels[x] for x in front_labels],
                        "rear_edges":[edge_labels[x] for x in rear_labels],
                        "edge_lengths_m":[e["length"] for e in edge_rows],
                        "source_points_wgs84":candidate.get("source_points_wgs84"),
                        "source_centroid_wgs84":candidate.get("source_centroid_wgs84"),
                        "source_location_point_wgs84":candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84"),
                        "source_location_method":candidate.get("source_location_method", "KML location point" if source_type == "kml" else None),
                        "source_fingerprint":fingerprint,
                    }
                    st.session_state["siteiq_front_edges"]=[edge_labels[x] for x in front_labels]
                    st.session_state["siteiq_rear_edges"]=[edge_labels[x] for x in rear_labels]
                    st.session_state.pop("siteiq_report", None)
                    lookup_point = (candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84")) if source_type == "kml" else None
                    if lookup_point:
                        # The source point is only for location lookup. The metric polygon above must independently pass boundary validation for area calculations.
                        st.session_state.pop("siteiq_kml_lookup_override", None)
                        st.session_state["siteiq_pending_boundary_location"] = {
                            "lon": float(lookup_point[0]), "lat": float(lookup_point[1]),
                            "source_label": "Applied KML boundary location point",
                        }
                        st.success("Boundary applied. SiteIQ will now re-run location identification using this KML footprint.")
                        st.rerun()
                    else:
                        st.success("Boundary applied. The plot area below will be derived from this polyline unless you choose to use a verified survey/title area instead. This KML did not contain a usable geographic location point.")
    active_boundary = st.session_state.get("siteiq_boundary")
    if active_boundary:
        st.markdown("**Active boundary**")
        bc1,bc2,bc3,bc4 = st.columns(4)
        bc1.metric("Polyline area", f"{active_boundary['area_m2']:,.2f} m²")
        bc2.metric("Perimeter", f"{active_boundary['perimeter_m']:,.2f} m")
        bc3.metric("Vertices", str(active_boundary['vertex_count']))
        bc4.metric("Front edges selected", str(len(active_boundary.get('front_edges', []))))
        area_mode = st.radio("Area used for the FAR lookup", ["Use imported polyline area", "Use verified survey / title area instead"], index=0 if active_boundary.get("use_computed_area", True) else 1, horizontal=True, key="siteiq_active_area_mode")
        active_boundary["use_computed_area"] = area_mode == "Use imported polyline area"
        if st.button("Remove active boundary", key="siteiq_remove_boundary"):
            st.session_state.pop("siteiq_boundary", None)
            st.session_state.pop("siteiq_kml_lookup_override", None)
            previous = st.session_state.pop("siteiq_coordinates_before_kml", None)
            if previous:
                st.session_state["siteiq_coordinates"] = previous
            st.session_state.pop("siteiq_location_coordinate_source", None)
            st.session_state.pop("siteiq_kml_previous_coordinate_distance_km", None)
            st.session_state.pop("siteiq_location_detection", None)
            st.session_state.pop("siteiq_report", None)
            st.rerun()
    else:
        st.info("No boundary has been applied yet. You can continue with a manually entered area, but a true irregular-site envelope requires an imported boundary.")

# -----------------------------------------------------------------------------
# STEP 3 — land-use rule category, proposed use, site area + road width.
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 3 · Choose land-use category and enter road width")
official_zone = (detection or {}).get("zone", {}).get("value", _val("official_zone", "Not verified"))
zone_status = (detection or {}).get("zone", {}).get("status", "not_verified")
st.markdown(f"**Official land-use map result:** `{official_zone}`  ·  Status: `{zone_status}`")
st.caption("The official map zone and the regulatory land-use category used for the table lookup are shown separately. Choose a category that matches the notified zone and proposed use; an auto-geocoded locality does not verify this classification.")

active_boundary = st.session_state.get("siteiq_boundary")
if active_boundary and active_boundary.get("use_computed_area", True):
    site_area_m2 = float(active_boundary["area_m2"])
    st.metric("Plot area derived from imported polyline", f"{site_area_m2:,.2f} m²")
    site_area_source = "imported polyline area"
else:
    site_area_m2 = st.number_input("Verified plot area (m²)", min_value=0.0, value=float(_val("site_area_m2", 0.0) or 0.0), step=10.0, key="siteiq_site_area")
    site_area_source = "user-entered survey/title area"

c1,c2,c3 = st.columns([1.4,1,1])
with c1:
    if profile:
        category_items = land_use_categories(profile)
        category_labels = [c.get("label", c.get("key")) for c in category_items]
        previous_category = _val("land_use_category", "")
        mapped_zone = official_zone if official_zone in category_labels else ""
        category_default = previous_category if previous_category in category_labels else (mapped_zone if mapped_zone else ("Residential (Main)" if st.session_state.get("siteiq_sample_loaded") and "Residential (Main)" in category_labels else "Select a land-use category"))
        category_options = ["Select a land-use category"] + category_labels
        if st.session_state.get("siteiq_land_use_category") not in category_options:
            # Authority changes can remove categories. Reset before constructing the widget to avoid stale invalid selections.
            st.session_state["siteiq_land_use_category"] = category_default if category_default in category_options else category_options[0]
        category_index = category_options.index(category_default) if category_default in category_options else 0
        land_use_category = st.selectbox("Regulatory land-use category", category_options, index=category_index, key="siteiq_land_use_category", help="Only categories in this selected authority's configured rule catalogue are shown. Unsupported categories will not produce an assumed FAR.")
    else:
        land_use_category = "Select a land-use category"
        st.selectbox("Regulatory land-use category", ["No configured categories for selected authority"], disabled=True, key="siteiq_category_unconfigured")
with c2:
    use_options = ["Residential apartments", "Individual house / villa", "Commercial / office", "Mixed use", "Institutional / other", "Industrial / warehouse", "Public / semi-public use", "Parking structure"]
    use_default = _val("proposed_use", "Residential apartments")
    proposed_use = st.selectbox("Proposed building use", use_options, index=use_options.index(use_default) if use_default in use_options else 0, key="siteiq_proposed_use")
with c3:
    road_width_m = st.number_input("Abutting road width (m)", min_value=0.0, value=float(_val("road_width_m", 0.0) or 0.0), step=0.5, key="siteiq_road_width")

c1,c2,c3 = st.columns(3)
with c1:
    frontage_m = st.number_input("Frontage (m; optional if boundary imported)", min_value=0.0, value=float(_val("frontage_m", 0.0) or 0.0), step=1.0, key="siteiq_frontage")
with c2:
    depth_m = st.number_input("Depth (m; optional if boundary imported)", min_value=0.0, value=float(_val("depth_m", 0.0) or 0.0), step=1.0, key="siteiq_depth")
with c3:
    approval_path_options = [
        "Not sure / needs confirmation",
        "New single-plot approval under Chapter 6-A",
        "Existing sanctioned plan / modification",
        "Development plan / layout",
        "Group housing / residential development-plan candidate",
        "Non-residential development-plan candidate",
        "Development plan / local LPA route — confirm",
        "Local building / plot approval route — confirm",
        "Other",
    ]
    approval_default = _val("approval_path", (detection or {}).get("approval_route", {}).get("suggested_value", approval_path_options[0]))
    approval_path = st.selectbox("Approval route", approval_path_options, index=approval_path_options.index(approval_default) if approval_default in approval_path_options else 0, key="siteiq_approval_path")

surrounding_zone = None
if land_use_category == "Commercial Axes (inherits surrounding zone)" and profile:
    main_categories = [c["label"] for c in land_use_categories(profile) if c.get("method") in {"area_cap_and_road_width", "road_width", "plot_area", "fixed"}]
    surrounding_default = _val("surrounding_zone", "Select surrounding zone")
    sur_opts = ["Select surrounding zone"] + main_categories
    surrounding_zone = st.selectbox("Official surrounding main zone", sur_opts, index=sur_opts.index(surrounding_default) if surrounding_default in sur_opts else 0, key="siteiq_surrounding_zone")
    if surrounding_zone == "Select surrounding zone": surrounding_zone = None

far_preview = _candidate_status(profile, land_use_category, site_area_m2, road_width_m, surrounding_zone, proposed_use=proposed_use)
st.markdown("### 4 · Maximum FAR rule lookup")
if far_preview.get("status") == "candidate_match_requires_verification":
    provisional_profile = far_preview.get("rule_source_quality") == "secondary_copy_pending_official_validation"
    f1,f2,f3=st.columns(3)
    f1.metric("Preliminary FAR candidate" if provisional_profile else "Maximum FAR candidate", f"{far_preview['maximum_far']:.2f}")
    f2.metric("Calculated FAR area capacity", f"{far_preview['maximum_far_area_m2']:,.0f} m²")
    detail = (far_preview.get("matched_rule") or {}).get("details", {})
    f3.metric("Limiting factor", str(detail.get("limiting_factor", "table provision")).replace("_", " ").title())
    if provisional_profile:
        st.warning("PROVISIONAL RULE PROFILE — This candidate is transcribed from a secondary copy of the LPA Master Plan. Confirm the current approved plan, amendments, official zone and notified road width with the authority before relying on it.")
    else:
        st.info("Candidate result — verify applicability and the operative notification before design freeze.")
    st.write(far_preview.get("message", "Candidate found; verify current applicability."))
    if detail.get("far_calculation_area_m2") is not None:
        st.caption(f"FAR calculation basis: {detail['far_calculation_area_m2']:,.2f} m² net of the configured {detail.get('deduction_pct', 0):g}% area deduction. Gross site area: {detail.get('gross_site_area_m2', site_area_m2):,.2f} m². Verify the reservation and net-area basis against the operative regulation.")
    if far_preview.get("selected_path"):
        st.caption(f"Selected conditional table: {far_preview['selected_path']}")
    if far_preview.get("source"):
        src=far_preview["source"]
        st.caption(f"Source: {src.get('title','')} · {src.get('clause','')} · {src.get('document_page','')} · {src.get('status','')}")
        if src.get("url"):
            st.markdown(f"[Open rule source / authority page]({src['url']})")
    coverage=far_preview.get("coverage", {})
    if coverage:
        st.caption("Coverage check: " + coverage.get("message", "No coverage result.") + (f" Listed table value: {coverage['coverage_pct']:.1f}%" if coverage.get("coverage_pct") is not None else ""))
    if far_preview.get("conditions"):
        with st.expander("Conditions attached to this table", expanded=False):
            for condition in far_preview["conditions"]:
                st.write("- " + condition)
    premium = far_preview.get("premium_far")
    if premium:
        with st.expander("Optional Premium FAR / TDR scenario (not included in base FAR)", expanded=False):
            st.warning(premium.get("message", "Optional premium FAR scenario only; verify eligibility and current notification."))
            if premium.get("additional_far_candidate") is not None:
                p1,p2,p3=st.columns(3)
                p1.metric("Additional FAR ceiling candidate", f"{premium['additional_far_candidate']:.2f}")
                p2.metric("Additional floor area scenario", f"{premium['additional_floor_area_candidate_m2']:,.0f} m²")
                p3.metric("Potential total FAR scenario", f"{premium['potential_total_far_candidate']:.2f}")
            if premium.get("source", {}).get("url"):
                st.markdown(f"[Open Premium FAR source / court judgment]({premium['source']['url']})")
elif far_preview.get("status") in {"category_required", "inputs_required"}:
    st.info(far_preview["message"])
else:
    st.warning(far_preview.get("message", "No FAR result is available from the selected profile."))
    if far_preview.get("source"):
        st.caption(f"Source: {far_preview['source'].get('title','')} · {far_preview['source'].get('clause','')}")

# -----------------------------------------------------------------------------
# STEP 5 — options: option-specific building and basement setbacks.
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown("## 5 · Compare height, building setbacks and basements")
st.caption("The FAR benchmark is the rule-derived candidate above. If the profile cannot identify one, SiteIQ will not silently use a manual FAR as the statutory benchmark. Footprint may be entered from design drawings, or set to zero to use the calculated boundary envelope as a maximum geometric proxy when a boundary is imported.")
num_options = st.number_input("Number of options to compare", min_value=2, max_value=4, value=int(_val("num_options", 3) or 3), step=1, key="siteiq_num_options")
scenarios = []
defaults = _val("scenarios", [
    {"name":"Option 01","height_m":12,"floors":4,"footprint_m2":0,"stilt":False,"basement_levels":1},
    {"name":"Option 02","height_m":15,"floors":5,"footprint_m2":0,"stilt":False,"basement_levels":1},
    {"name":"Option 03","height_m":18,"floors":6,"footprint_m2":0,"stilt":False,"basement_levels":2},
])
for i in range(int(num_options)):
    d = defaults[i] if i < len(defaults) else {"name":f"Option {i+1}","height_m":12+i*3,"floors":4+i,"footprint_m2":0,"stilt":False,"basement_levels":0}
    with st.container(border=True):
        st.markdown(f"### Option {i+1}")
        a,b,c,dcol = st.columns([1.5,1,1,1.4])
        with a:
            opt_name=st.text_input("Option name",value=st.session_state.get(f"siteiq_opt{i}_name",d.get("name",f"Option {i+1}")),key=f"siteiq_opt{i}_name")
        with b:
            opt_height=st.number_input("Total height (m)",min_value=0.0,value=float(st.session_state.get(f"siteiq_opt{i}_height",d.get("height_m",0.0)) or 0),step=1.0,key=f"siteiq_opt{i}_height")
        with c:
            opt_floors=st.number_input("Above-ground floors",min_value=0,max_value=100,value=int(st.session_state.get(f"siteiq_opt{i}_floors",d.get("floors",0)) or 0),step=1,key=f"siteiq_opt{i}_floors")
        with dcol:
            opt_footprint=st.number_input("Footprint m² (0 = use envelope)",min_value=0.0,value=float(st.session_state.get(f"siteiq_opt{i}_footprint",d.get("footprint_m2",0.0)) or 0),step=10.0,key=f"siteiq_opt{i}_footprint",help="If zero, an imported boundary envelope is used as a maximum footprint proxy. Without a boundary, area yield cannot be calculated automatically.")
        e,f,g,h = st.columns([1,1.6,1,1.6])
        with e:
            opt_stilt=st.checkbox("Stilt floor",value=bool(st.session_state.get(f"siteiq_opt{i}_stilt",d.get("stilt",False))),key=f"siteiq_opt{i}_stilt")
        with f:
            sb_options=["Automatic rule lookup","Manual all-round setback scenario"]
            sb_default=st.session_state.get(f"siteiq_opt{i}_setback_mode",d.get("setback_mode","automatic"))
            sb_value="Manual all-round setback scenario" if sb_default=="manual" else "Automatic rule lookup"
            sb_choice=st.selectbox("Building setback mode",sb_options,index=sb_options.index(sb_value),key=f"siteiq_opt{i}_setback_choice")
            sb_mode="manual" if sb_choice.startswith("Manual") else "automatic"
        with g:
            manual_sb=st.number_input("Manual setback (m)",min_value=0.0,value=float(st.session_state.get(f"siteiq_opt{i}_manual_sb",d.get("manual_all_round_setback_m",0.0)) or 0),step=0.5,key=f"siteiq_opt{i}_manual_sb",disabled=sb_mode!="manual")
        with h:
            basement_levels=st.number_input("Basement levels",min_value=0,max_value=5,value=int(st.session_state.get(f"siteiq_opt{i}_basements",d.get("basement_levels",0)) or 0),step=1,key=f"siteiq_opt{i}_basements")
        j,k=st.columns([1.3,1.3])
        with j:
            basement_choice=st.selectbox("Basement setback mode",["Automatic rule lookup","Manual scenario assumptions"],index=0 if st.session_state.get(f"siteiq_opt{i}_basement_mode",d.get("basement_setback_mode","automatic"))!="manual" else 1,key=f"siteiq_opt{i}_basement_choice",disabled=basement_levels==0)
            basement_mode="manual" if basement_choice.startswith("Manual") else "automatic"
        with k:
            bf, bn = st.columns(2)
            with bf:
                manual_bf=st.number_input("Basement front m",min_value=0.0,value=float(st.session_state.get(f"siteiq_opt{i}_manual_bf",d.get("manual_basement_front_m",0.0)) or 0),step=0.5,key=f"siteiq_opt{i}_manual_bf",disabled=basement_levels==0 or basement_mode!="manual")
            with bn:
                manual_bn=st.number_input("Basement other sides m",min_value=0.0,value=float(st.session_state.get(f"siteiq_opt{i}_manual_bn",d.get("manual_basement_nonfront_m",0.0)) or 0),step=0.5,key=f"siteiq_opt{i}_manual_bn",disabled=basement_levels==0 or basement_mode!="manual")
        scenarios.append({
            "name":opt_name or f"Option {i+1}","height_m":opt_height or None,"floors":int(opt_floors) if opt_floors else None,
            "footprint_m2":float(opt_footprint) if opt_footprint>0 else None,"stilt":bool(opt_stilt),
            "setback_mode":sb_mode,"manual_all_round_setback_m":float(manual_sb) if sb_mode=="manual" and manual_sb>0 else None,
            "basement_levels":int(basement_levels),"basement_setback_mode":basement_mode,
            "manual_basement_front_m":float(manual_bf) if basement_mode=="manual" and manual_bf>0 else None,
            "manual_basement_nonfront_m":float(manual_bn) if basement_mode=="manual" and manual_bn>0 else None,
        })

# User can manually enter official verified zone separately. It never overrides the category chosen above.
with st.expander("Optional: official zone / jurisdiction notes for the report", expanded=False):
    st.text_input("Official zone as shown on current notified map (if known)", value=str(_val("official_zone", official_zone or "Not verified")), key="siteiq_official_zone")
    st.text_area("Survey / title / authority notes", value=str(_val("authority_notes", "")), key="siteiq_authority_notes", height=80)

st.markdown("---")
run_assessment = st.button("Run regulatory and option feasibility", type="primary", use_container_width=True)
if run_assessment:
    if site_area_m2 <= 0:
        st.error("A valid plot area is required. Import a boundary or enter a verified survey/title area.")
    elif road_width_m <= 0:
        st.error("Enter the abutting road width. SiteIQ uses it to select a configured road-width FAR band where the regulation requires one.")
    elif profile and (not land_use_category or land_use_category == "Select a land-use category"):
        st.error("Select the official regulatory land-use category before running the lookup.")
    else:
        site = {
            "project_name":project_name.strip() or "Untitled site feasibility", "client":client_name.strip(),
            "address":address.strip(), "map_url":map_url.strip(), "coordinates":coordinates.strip(),
            "authority_key":authority_key, "zone":land_use_category, "land_use_category":land_use_category,
            "official_zone":str(_val("official_zone",official_zone or "Not verified")), "surrounding_zone":surrounding_zone,
            "proposed_use":proposed_use, "site_area_m2":float(site_area_m2), "site_area_source":site_area_source,
            "road_width_m":float(road_width_m), "frontage_m":float(frontage_m) if frontage_m>0 else None,
            "depth_m":float(depth_m) if depth_m>0 else None,
            "shape_type":"Irregular / non-rectangular" if active_boundary else str(_val("shape_type","Not determined from imported geometry")),
            "geometry_mode":"Use imported polygon" if active_boundary else "No imported polygon",
            "height_for_setback_m":scenarios[0].get("height_m") if scenarios else None,
            "stilt":bool(scenarios[0].get("stilt",False)) if scenarios else False,
            "basement":"Option-specific" if any(x.get("basement_levels",0)>0 for x in scenarios) else "No basement selected",
            "approval_path":approval_path,"authority_notes":str(_val("authority_notes","")),"scenarios":scenarios,
        }
        report = build_report(site, registry=registry, profile=profile)
        report["location_identification"] = detection
        # Preserve only real validated boundary inputs; build separate building/basement envelopes per option.
        if active_boundary:
            parcel = Polygon(active_boundary["points_m"])
            front_edges = active_boundary.get("front_edges", [])
            rear_edges = active_boundary.get("rear_edges", [])
            option_data=[]
            envelope_map={}
            for opt in report.get("scenarios", []):
                building_env=calculate_setback_envelope(parcel, opt.get("setback_result",{}), front_edges, rear_edges)
                opt["boundary_envelope"] = building_env
                envelope_map[opt.get("name","Option")]=building_env
                bres=opt.get("basement_setback_result",{})
                if int(opt.get("basement_levels",0) or 0)>0:
                    basement_env=calculate_setback_envelope(parcel,bres,front_edges,rear_edges)
                else:
                    basement_env={"status":"no_basement","message":"No basement selected for this option.","area_m2":None,"geometry":None}
                opt["basement_boundary_envelope"] = basement_env
                if basement_env.get("geometry"):
                    envelope_map[opt.get("name","Option")+" basement"] = basement_env
                # If no footprint was supplied, use the envelope area as a conservative geometry-derived proxy.
                if opt.get("footprint_m2") is None and building_env.get("area_m2") is not None:
                    opt["footprint_m2"] = round(float(building_env["area_m2"]),2)
                    opt["footprint_source"] = "preliminary setback envelope area"
                    floors=opt.get("floors")
                    if floors:
                        opt["gross_concept_area_m2"] = round(opt["footprint_m2"]*int(floors),2)
                        opt["achieved_gross_far_ratio"] = round(opt["gross_concept_area_m2"]/site_area_m2,3)
                        cap=opt.get("far_capacity_m2")
                        opt["scenario_headroom_m2"] = round(cap-opt["gross_concept_area_m2"],2) if cap is not None else None
                elif opt.get("footprint_m2") is not None and building_env.get("area_m2") is not None:
                    opt["footprint_source"] = "user-entered design footprint"
                    opt["footprint_exceeds_envelope"] = float(opt["footprint_m2"]) > float(building_env["area_m2"])+0.5
                    if opt["footprint_exceeds_envelope"]:
                        opt["envelope_warning"] = "Entered footprint is larger than the calculated preliminary setback envelope. Reduce/review the footprint or inspect geometry in CAD."
                option_data.append({"name":opt.get("name"),"envelope":building_env,"basement_envelope":basement_env})
            report["boundary_analysis"]={
                "source_file":active_boundary.get("source_file"),"source_type":active_boundary.get("source_type"),
                "source_units":active_boundary.get("source_units"),"scale_to_m":active_boundary.get("scale_to_m"),
                "area_m2":active_boundary.get("area_m2"),"perimeter_m":active_boundary.get("perimeter_m"),
                "vertex_count":active_boundary.get("vertex_count"),"is_convex":active_boundary.get("is_convex"),
                "validation_status":active_boundary.get("validation_status"),"validation_notes":active_boundary.get("validation_notes",[]),
                "use_computed_area":active_boundary.get("use_computed_area",True),
                "area_difference_from_input_pct":None,
                "front_edges":front_edges,"rear_edges":rear_edges,
                "geometry":{"type":"Polygon","coordinates":[[list(pt) for pt in list(parcel.exterior.coords)]]},
                "options":option_data,
                "limitation":"Area and envelope are derived from the imported scaled outline. Verify against the authenticated survey. Complex concave corners, exact legal boundary interpretations, overlaps, overlays and full design/code constraints remain for CAD and authority review."
            }
            st.session_state["siteiq_active_envelope_layers"] = envelope_map
        st.session_state["siteiq_report"] = report
        st.session_state["siteiq_last_site"] = site

# -----------------------------------------------------------------------------
# RESULTS and report outputs
# -----------------------------------------------------------------------------
report = st.session_state.get("siteiq_report")
if report:
    st.markdown("---")
    st.markdown("# Feasibility result")
    site=report["site"]
    far=report.get("far",{})
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Plot area used", f"{site['site_area_m2']:,.0f} m²")
    c2.metric("Road width", f"{site['road_width_m']:.2f} m")
    c3.metric("Max FAR candidate", f"{far['maximum_far']:.2f}" if far.get("maximum_far") is not None else "Needs confirmation")
    c4.metric("FAR-area benchmark", f"{far['maximum_far_area_m2']:,.0f} m²" if far.get("maximum_far_area_m2") is not None else "Not calculated")
    st.write(f"**Regulatory category used:** {site.get('land_use_category',site.get('zone','Not selected'))}  ·  **Official map zone:** {site.get('official_zone','Not verified')}")
    if far.get("status")=="candidate_match_requires_verification":
        st.info(far.get("message","Candidate FAR identified; confirm before sanction use."))
        details=(far.get("matched_rule") or {}).get("details",{})
        if details:
            st.write("**Lookup breakdown:** " + "; ".join(f"{k.replace('_',' ')}: {v}" for k,v in details.items()))
    else:
        st.warning(far.get("message","FAR could not be calculated."))
    if far.get("coverage"):
        cov=far["coverage"]
        st.caption("Ground coverage: " + cov.get("message", "No result") + (f" Table figure: {cov['coverage_pct']}%" if cov.get("coverage_pct") is not None else ""))

    st.markdown("### Option comparison")
    rows=[]
    for opt in report.get("scenarios",[]):
        headroom=opt.get("scenario_headroom_m2")
        rows.append({
            "Option":opt.get("name"),"Height":f"{opt.get('height_m')} m" if opt.get("height_m") is not None else "Not set",
            "Floors":opt.get("floors"),"Building setback":opt.get("setback_summary","Not determined"),
            "Basement levels":opt.get("basement_levels",0),"Basement setback":opt.get("basement_setback_summary","Not determined"),
            "Footprint used (m²)":opt.get("footprint_m2"),"FAR area capacity (m²)":opt.get("far_capacity_m2"),
            "Approx. floor area (m²)":opt.get("gross_concept_area_m2"),"Achieved gross FAR":opt.get("achieved_gross_far_ratio"),
            "Remaining / over benchmark (m²)":headroom,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Positive remaining area means the option is under the calculated FAR-area benchmark; negative means it exceeds it. Gross area is footprint × above-ground floor count. Detailed FAR exclusions and floor-by-floor changes are not modelled.")
    for opt in report.get("scenarios",[]):
        if opt.get("footprint_exceeds_envelope"):
            st.error(f"{opt['name']}: {opt.get('envelope_warning')}")

    boundary=report.get("boundary_analysis")
    if boundary:
        st.markdown("### Site boundary and option envelopes")
        bx1,bx2,bx3=st.columns(3)
        bx1.metric("Imported boundary area",f"{boundary['area_m2']:,.2f} m²")
        bx2.metric("Perimeter",f"{boundary['perimeter_m']:,.2f} m")
        bx3.metric("Boundary vertices",str(boundary['vertex_count']))
        parcel=Polygon(boundary["geometry"]["coordinates"][0])
        env_map={x["name"]:x["envelope"] for x in boundary.get("options",[]) if x.get("envelope")}
        fig=make_boundary_preview(parcel,env_map)
        st.pyplot(fig,clear_figure=True)
        env_rows=[]
        for item in boundary.get("options",[]):
            opt=next((x for x in report.get("scenarios",[]) if x.get("name")==item.get("name")),{})
            benv=item.get("envelope",{}); bas=item.get("basement_envelope",{})
            env_rows.append({"Option":item["name"],"Building envelope (m²)":benv.get("area_m2"),"Building envelope status":benv.get("status"),"Basement envelope (m²)":bas.get("area_m2"),"Basement status":bas.get("status")})
            if benv.get("message"): st.caption(f"{item['name']} building envelope: {benv['message']}")
            if bas.get("message") and int(opt.get("basement_levels",0) or 0)>0: st.caption(f"{item['name']} basement envelope: {bas['message']}")
        st.dataframe(pd.DataFrame(env_rows), use_container_width=True, hide_index=True)
        layers={}
        for item in boundary.get("options",[]):
            layers[item["name"]]=item.get("envelope",{})
            if item.get("basement_envelope",{}).get("geometry"):
                layers[item["name"]+" basement"]=item["basement_envelope"]
        st.download_button("Download boundary + building / basement envelopes as DXF",data=export_boundary_dxf(parcel,layers),file_name="SiteIQ_Boundary_Options.dxf",mime="application/dxf")

    with st.expander("Rule sources and assumptions",expanded=False):
        for src in report.get("sources",[]):
            st.markdown(f"**{src.get('title','Rule source')}**")
            st.caption(" · ".join(str(v) for v in [src.get("notification"),src.get("date"),src.get("document"),src.get("document_page"),src.get("clause"),src.get("status")] if v))
            if src.get("url"): st.markdown(f"[Open source / authority page]({src['url']})")
        for item in report.get("checks",[]):
            st.write(f"- **{item.get('item')}** — {item.get('status')}: {item.get('note')}")

    st.markdown("### Export")
    st.caption("The A3 board is designed to resemble the attached Nandi comparison sheet. The detailed PDF/PowerPoint includes source notes and limitations.")
    pdf=build_pdf_report(report)
    pptx=build_pptx_report(report)
    board_pdf=build_a3_comparison_board_pdf(report)
    board_pptx=build_a3_comparison_board_pptx(report)
    c1,c2,c3,c4=st.columns(4)
    c1.download_button("Client-friendly PDF report",data=pdf,file_name="SiteIQ_Feasibility_Report.pdf",mime="application/pdf",use_container_width=True)
    c2.download_button("Editable PowerPoint report",data=pptx,file_name="SiteIQ_Feasibility_Report.pptx",mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",use_container_width=True)
    c3.download_button("One-page A3 comparison PDF",data=board_pdf,file_name="SiteIQ_Feasibility_Comparison_A3.pdf",mime="application/pdf",use_container_width=True)
    c4.download_button("Editable A3 board PPTX",data=board_pptx,file_name="SiteIQ_Feasibility_Comparison_A3.pptx",mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",use_container_width=True)
    st.download_button("Download assessment JSON",data=json.dumps(report,indent=2,ensure_ascii=False),file_name="SiteIQ_Assessment.json",mime="application/json")
    if report.get("limits"):
        with st.expander("MVP limitations",expanded=False):
            for limit in report["limits"]: st.write("- "+limit)
else:
    st.info("Complete Steps 1–5, confirm the rule-derived FAR result, and click **Run regulatory and option feasibility**. Load the Nandi Housing example from the sidebar to see the workflow filled with sample inputs.")

st.markdown("---")
st.caption("SiteIQ v0.4.7 | Multi-authority provisional rules profiles | GIS uploads are optional admin tools, not part of the normal workflow. Confirm operative Gazette, official zone, survey geometry and authority interpretation before sanction use.")
