"""Older Streamlit interface. The React app in frontend/ is the main one, and both share siteiq/service.py.

Remove this file, requirements-dev.txt's Streamlit and pandas entries, and its tests once architect testing of the React app is complete.
"""
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
from siteiq.service import assess, input_fingerprint

st.set_page_config(
    page_title="SiteIQ | Architectural Feasibility Suite",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #111111;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2.5rem;
    max-width: 1440px;
}

/* Minimalist tab styling */
button[data-baseweb="tab"] {
    font-size: 0.90rem !important;
    font-weight: 500 !important;
    color: #666666 !important;
    padding: 10px 18px !important;
    border-bottom: 2px solid transparent !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #111111 !important;
    font-weight: 700 !important;
    border-bottom: 2px solid #111111 !important;
    background: transparent !important;
}

/* Minimalist monochrome metric cards */
[data-testid="stMetric"] {
    background: #FAFAFA;
    border: 1px solid #E5E7EB;
    padding: 14px 18px;
    border-radius: 6px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}

[data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6B7280 !important;
    font-weight: 600;
}

[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #111111 !important;
}

/* Architectural typography */
.siteiq-mono {
    font-family: 'JetBrains Mono', monospace;
}

.badge-verified {
    display: inline-block;
    background: #111111;
    color: #FFFFFF;
    font-size: 0.70rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.badge-provisional {
    display: inline-block;
    background: #F3F4F6;
    color: #374151;
    border: 1px solid #D1D5DB;
    font-size: 0.70rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.badge-alert {
    display: inline-block;
    background: #FEF2F2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 4px;
}

.header-strip {
    border-bottom: 1px solid #E5E7EB;
    padding-bottom: 12px;
    margin-bottom: 20px;
}

.section-label {
    font-size: 0.76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #4B5563;
    margin-bottom: 4px;
}

.section-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #111111;
    margin-bottom: 4px;
}

.section-caption {
    font-size: 0.88rem;
    color: #6B7280;
    margin-bottom: 16px;
}

/* Table and dataframe borders */
[data-testid="stDataFrame"] {
    border: 1px solid #E5E7EB;
    border-radius: 6px;
}

/* Button overrides */
div.stButton > button {
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.88rem;
    transition: all 0.15s ease-in-out;
}
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
    st.session_state["siteiq_num_options"] = min(4, max(2, len(sample.get("scenarios", []))))
    st.session_state["siteiq_sample_loaded"] = True
    st.session_state.pop("siteiq_report", None)


def _val(key, default=None):
    return st.session_state.get(f"siteiq_{key}", default)


def _candidate_status(profile, category, area, road, surrounding_zone=None, proposed_use=None, statutory_deduction_pct=None):
    if not profile:
        return {"status": "not_configured", "message": "No current rules profile is configured for this planning authority. SiteIQ will not use another authority's FAR."}
    if not category or category == "Select a land-use category":
        return {"status": "category_required", "message": "Select the official land-use category to run the FAR lookup."}
    if area <= 0 or road <= 0:
        return {"status": "inputs_required", "message": "Enter a positive plot area and road width to run the FAR lookup."}
    return match_far_rule(profile, category, area, road, surrounding_zone=surrounding_zone, proposed_use=proposed_use, statutory_deduction_pct=statutory_deduction_pct)


def candidate_holes_m(candidate: dict, factor: float) -> list:
    return [[[float(p[0]) * factor, float(p[1]) * factor] for p in ring] for ring in (candidate.get("holes") or [])]


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
# before widgets are instantiated and rerun jurisdiction/source identification from the KML.
_pending_boundary_location = st.session_state.pop("siteiq_pending_boundary_location", None)
if _pending_boundary_location:
    old_text = str(st.session_state.get("siteiq_coordinates", "") or "")
    st.session_state["siteiq_coordinates_before_kml"] = old_text
    lon = float(_pending_boundary_location["lon"])
    lat = float(_pending_boundary_location["lat"])
    st.session_state["siteiq_coordinates"] = f"{lat:.7f}, {lon:.7f}"
    st.session_state["siteiq_location_coordinate_source"] = str(_pending_boundary_location.get("source_label") or "Applied KML boundary location point")
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
            dlat = radians(lat - old_lat); dlon = radians(lon - old_lon)
            a = sin(dlat / 2)**2 + cos(radians(old_lat)) * cos(radians(lat)) * sin(dlon / 2)**2
            distance_km = 6371.0088 * 2 * asin(sqrt(min(1.0, a)))
        except Exception:
            distance_km = None
    st.session_state["siteiq_kml_previous_coordinate_distance_km"] = distance_km
    st.session_state.pop("siteiq_location_detection", None)
    _identify_site_callback()


# -----------------------------------------------------------------------------
# TOP HEADER RIBBON
# -----------------------------------------------------------------------------
header_left, header_right = st.columns([2.5, 1.5])
with header_left:
    st.markdown('<div class="section-label">SiteIQ Feasibility Suite</div>', unsafe_allow_html=True)
    st.markdown('<h1 style="font-size: 1.85rem; font-weight: 800; margin: 0; padding: 0; letter-spacing: -0.02em;">ARCHITECTURAL FEASIBILITY & STATUTORY CONTROLS</h1>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 0.85rem; color: #6B7280; margin-top: 4px;">Rule-driven zoning analysis, envelope modeling, and comparative floor-area yield evaluation.</div>', unsafe_allow_html=True)

with header_right:
    active_boundary_summary = st.session_state.get("siteiq_boundary")
    current_auth_key = _val("authority_key", "other_karnataka")
    auth_label = authority_labels.get(current_auth_key, current_auth_key)
    st.markdown(f"""
    <div style="text-align: right; font-size: 0.82rem; color: #4B5563; padding-top: 8px;">
        <div><strong>Active Profile:</strong> {auth_label[:35]}...</div>
        <div><strong>Geometry:</strong> {'Survey Polyline (' + str(round(active_boundary_summary['area_m2'])) + ' m²)' if active_boundary_summary else 'No boundary applied'}</div>
        <div><span class="badge-provisional">Legacy interface · preliminary feasibility only</span></div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="header-strip"></div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS & DIAGNOSTICS
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Quick Setup & Benchmarks")
    if st.button("Load Nandi Housing Benchmark", use_container_width=True, type="secondary"):
        _load_nandi_sample()
        st.rerun()
    if st.button("Reset Assessment State", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("siteiq_"):
                st.session_state.pop(k, None)
        st.rerun()

    st.markdown("---")
    st.markdown("### Planning Authority Matrix")
    configured_profiles = [a for a in authorities if a.get("rule_profile") and load_rule_profile(a.get("rule_profile"))]
    st.markdown(f"**Profiles Active:** {len(configured_profiles)} | **Indexed:** {len(authorities)}")
    st.caption("Active profiles include Bengaluru RMP 2015, and provisional candidates for Hoskote, Kanakapura, Nelamangala and Anekal. Zero silent fallback to other cities.")

    with st.expander("Inspect Authority Coverage Matrix", expanded=False):
        coverage_rows = []
        for a in authorities:
            coverage_rows.append({
                "Authority": a.get("name", a.get("key", "")),
                "Status": a.get("status", "not reviewed"),
                "Rules Enabled": "Yes" if a.get("rule_profile") and load_rule_profile(a.get("rule_profile")) else "No",
            })
        st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)
        coverage_csv = (ROOT / "rules" / "authority_coverage_matrix.csv")
        if coverage_csv.exists():
            st.download_button("Export Matrix (CSV)", data=coverage_csv.read_bytes(), file_name="SiteIQ_Authority_Coverage.csv", mime="text/csv", use_container_width=True)

    with st.expander("GIS Layer Maintenance (Admin)", expanded=False):
        st.caption("Optional local boundary GeoJSON layers for verified point-in-polygon containment checks.")
        authority_geojson = st.file_uploader("Authority GeoJSON", type=["geojson", "json"], key="siteiq_admin_auth_upload")
        zone_geojson = st.file_uploader("Zoning GeoJSON", type=["geojson", "json"], key="siteiq_admin_zone_upload")
        if st.button("Install Local Layers"):
            res = []
            if authority_geojson:
                x = save_geojson_layer("authority_boundaries.geojson", authority_geojson.getvalue())
                res.append(f"Authority layer: {x['valid_polygon_count']} polygons")
            if zone_geojson:
                x = save_geojson_layer("land_use_zones.geojson", zone_geojson.getvalue())
                res.append(f"Zoning layer: {x['valid_polygon_count']} polygons")
            if res:
                st.success(" · ".join(res))

# -----------------------------------------------------------------------------
# MAIN TABBED WORKSPACE (6 STEPPED WORKSPACES)
# -----------------------------------------------------------------------------
tab_loc, tab_bound, tab_zone, tab_far, tab_scen, tab_dossier = st.tabs([
    "1 · Site & Location",
    "2 · Boundary Studio",
    "3 · Zoning & Road",
    "4 · Maximum FAR Engine",
    "5 · Design Scenarios",
    "6 · Feasibility Dossier",
])

# -----------------------------------------------------------------------------
# TAB 1: SITE & LOCATION INTELLIGENCE
# -----------------------------------------------------------------------------
with tab_loc:
    st.markdown('<div class="section-label">Workspace 01</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Site Identity & Location Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Resolve site coordinates, verify planning authority jurisdiction, and link official master plans.</div>', unsafe_allow_html=True)

    l_col, r_col = st.columns([1.1, 1.1], gap="large")
    with l_col:
        st.markdown("**Project Information**")
        project_name = st.text_input("Project Name", value=_val("project_name", "Untitled site"), key="siteiq_project_name")
        client_name = st.text_input("Client / Reference Code (optional)", value=_val("client", ""), key="siteiq_client")

        st.markdown("**Location Inputs**")
        st.caption("Precedence: Applied KML boundary > Google Maps link > Manual coordinates > Address geocoding.")
        map_url = st.text_input("Google Maps Link (recommended)", value=_val("map_url", ""), key="siteiq_map_url", help="Supports short links (maps.app.goo.gl) and full URLs.")
        coordinates = st.text_input("Coordinates (Latitude, Longitude)", value=_val("coordinates", ""), key="siteiq_coordinates")
        address = st.text_input("Site Address / Locality Context", value=_val("address", ""), key="siteiq_address")

        st.button(
            "Identify Location & Authority",
            type="primary",
            key="siteiq_identify",
            on_click=_identify_site_callback,
            use_container_width=True,
        )
        if st.session_state.get("siteiq_location_error"):
            st.error(f"Resolution Notice: {st.session_state['siteiq_location_error']}")

    with r_col:
        st.markdown("**Location & Authority Candidate**")
        detection = st.session_state.get("siteiq_location_detection")
        if detection:
            auth = detection.get("authority", {})
            zres = detection.get("zone", {})
            rres = detection.get("approval_route", {})
            coords_info = detection.get("coordinates", {})
            coord_source = str(st.session_state.get("siteiq_location_coordinate_source", "") or detection.get("location_source", ""))

            with st.container(border=True):
                auth_display_name = auth.get("label") or authority_labels.get(auth.get("key"), auth.get("key")) or "Not identified"
                st.markdown(f"**Planning Authority:** `{auth_display_name}`")
                st.caption(auth.get("reason", ""))

                if auth.get("status") == "matched_polygon_layer":
                    st.markdown('<span class="badge-provisional">Installed Layer Match · confirm layer date and source</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="badge-provisional">Provisional Locality Match</span>', unsafe_allow_html=True)

                st.markdown("---")
                st.markdown(f"**Coordinates Used:** `{coords_info.get('text', 'Not resolved')}`")
                st.markdown(f"**Source:** `{coord_source}`")

                comparison = detection.get("input_coordinate_comparison") or {}
                if comparison.get("mismatch"):
                    st.markdown(f'<div class="badge-alert">⚠️ Coordinate Mismatch: Map pin is {comparison.get("distance_km", 0):.1f} km from entered coordinate text. Map link prioritized.</div>', unsafe_allow_html=True)

                st.markdown(f"**Official Land-Use Map Status:** `{zres.get('value', 'Not verified')}`")
                st.caption(zres.get("reason", ""))

                st.markdown(f"**Approval Route Suggestion:** `{rres.get('suggested_value', 'Needs confirmation')}`")

            public_sources = detection.get("public_sources") or []
            if public_sources:
                with st.expander("Curated Official Maps & Regulatory Links", expanded=False):
                    for src in public_sources:
                        st.markdown(f"**[{src.get('title', 'Official source')}]({src.get('url', '#')})**")
                        st.caption(src.get("note", ""))
        else:
            st.info("Paste a Google Maps link or enter site coordinates, then click **Identify Location & Authority** to resolve the planning jurisdiction.")

# -----------------------------------------------------------------------------
# TAB 2: BOUNDARY & GEOMETRY STUDIO
# -----------------------------------------------------------------------------
with tab_bound:
    st.markdown('<div class="section-label">Workspace 02</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Boundary & Geometry Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Import surveyed polylines, calibrate scale, tag road-facing frontage edges, and validate plot geometry.</div>', unsafe_allow_html=True)

    b_col1, b_col2 = st.columns([1.1, 1.1], gap="large")
    with b_col1:
        st.markdown("**Upload Boundary File**")
        uploaded = st.file_uploader("CAD DXF, Google Earth KML/KMZ, or vector PDF", type=["dxf", "pdf", "kml", "kmz"], key="siteiq_boundary_file")
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

        # Single KML auto-location prefill logic (preserved for tests)
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

        # Unapplied KML warning (preserved for test assertion)
        _current_upload = st.session_state.get("siteiq_boundary_file")
        _active_boundary_for_warning = st.session_state.get("siteiq_boundary") or {}
        try:
            _upload_name = str(getattr(_current_upload, "name", "") or "")
            _upload_bytes = _current_upload.getvalue() if _current_upload is not None and hasattr(_current_upload, "getvalue") else b""
            _upload_fingerprint = hashlib.sha256(_upload_bytes).hexdigest() if _upload_bytes else None
        except Exception:
            _upload_name, _upload_fingerprint = "", None
        _active_fingerprint = _active_boundary_for_warning.get("source_fingerprint")
        if _upload_name.lower().endswith((".kml", ".kmz")) and _upload_fingerprint and _upload_fingerprint != _active_fingerprint:
            st.warning(f"KML file '{_upload_name}' is uploaded/selected but has not been applied as the active boundary. In Step 2, select the correct KML feature and use 'Use selected KML location for authority lookup' or apply the boundary before relying on the authority result.")

        if candidates:
            ids = [c["candidate_id"] for c in candidates]
            candidate_id = st.selectbox(
                "Detected Boundary Feature", ids,
                format_func=lambda cid: next((f"{c['label']} · {len(c['points'])} vertices · {'closed' if c['closed'] else 'open path'}" for c in candidates if c['candidate_id'] == cid), cid),
                key="siteiq_selected_candidate"
            )
            candidate = next(c for c in candidates if c["candidate_id"] == candidate_id)
            source_type = candidate.get("source_type")
            factor = candidate.get("scale_to_m")

            if source_type == "kml":
                if candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84"):
                    st.button(
                        "Use selected KML location for authority lookup",
                        key="siteiq_use_kml_location",
                        on_click=_use_selected_kml_location_callback,
                    )
            elif factor is not None:
                scale_choice = st.radio("Scale method", ["Use drawing-unit metadata", "Calibrate against a known edge"], horizontal=True, key="siteiq_scale_method_known")
                if scale_choice.startswith("Calibrate"):
                    factor = None
            else:
                scale_choice = st.radio("Scale method", ["Choose CAD units", "Calibrate against a known edge"], horizontal=True, key="siteiq_scale_method_unknown")
                if source_type == "dxf" and scale_choice == "Choose CAD units":
                    unit = st.selectbox("CAD drawing units", ["Metres", "Millimetres", "Centimetres", "Feet", "Inches"], key="siteiq_cad_units")
                    factor = {"Metres": 1.0, "Millimetres": 0.001, "Centimetres": 0.01, "Feet": 0.3048, "Inches": 0.0254}[unit]
                else:
                    factor = None

            edge_lengths_raw = candidate_edge_lengths(candidate.get("points", []))
            if factor is None and source_type in ("pdf", "dxf"):
                edge_opts = {f"Edge {e['edge_index']+1} · {e['length']:.3f} units": e['edge_index'] for e in edge_lengths_raw}
                chosen_edge_label = st.selectbox("Known edge to calibrate", list(edge_opts), key="siteiq_calibration_edge")
                known_m = st.number_input("Actual surveyed length (m)", min_value=0.01, value=float(_val("known_edge_m", 10.0)), step=0.5, key="siteiq_known_edge_m")
                raw_len = next(e["length"] for e in edge_lengths_raw if e["edge_index"] == edge_opts[chosen_edge_label])
                factor = known_m / raw_len if raw_len > 0 else None

            close_open = False
            if not candidate.get("closed", False):
                close_open = st.checkbox("Confirm last-to-first segment is a legal boundary edge", value=False, key="siteiq_close_open_boundary")

            poly = None
            validation = {"status": "scale_required", "message": "A reliable drawing scale is required."}
            if factor:
                poly, validation = polygon_from_candidate(candidate, scale_to_m=factor, close_open=close_open)

            if poly is not None:
                st.success(f"Geometry Validated: {validation['area_m2']:,.2f} m² · Perimeter {validation['perimeter_m']:,.2f} m")
                edge_rows = candidate_edge_lengths(list(poly.exterior.coords)[:-1])
                edge_labels = {f"Edge {e['edge_index']+1} ({e['length']:.2f} m)": e['edge_index'] for e in edge_rows}
                front_default = st.session_state.get("siteiq_front_edges", [])
                front_labels_default = [label for label, ix in edge_labels.items() if ix in front_default]
                front_labels = st.multiselect("Road-Facing Frontage Edge(s)", list(edge_labels), default=front_labels_default, key="siteiq_front_edge_labels")
                excluded = [label for label, ix in edge_labels.items() if label in front_labels]
                rear_default = st.session_state.get("siteiq_rear_edges", [])
                rear_labels_default = [label for label, ix in edge_labels.items() if ix in rear_default and label not in excluded]
                rear_labels = st.multiselect("Rear Boundary Edge(s)", [x for x in edge_labels if x not in excluded], default=rear_labels_default, key="siteiq_rear_edge_labels")

                use_poly_area = st.checkbox("Use the polyline-calculated area for FAR calculations", value=True, key="siteiq_use_poly_area")

                if st.button("Apply boundary and derived area", type="primary", key="siteiq_apply_boundary", use_container_width=True):
                    metric_points = [(float(x) * float(factor), float(y) * float(factor)) for x, y in candidate["points"]]
                    st.session_state.pop("siteiq_kml_lookup_override", None)
                    st.session_state["siteiq_boundary"] = {
                        "source_file": uploaded.name, "source_type": source_type,
                        "source_units": candidate.get("source_units"), "scale_to_m": float(factor),
                        "points_m": metric_points, "area_m2": float(validation["area_m2"]),
                        "perimeter_m": float(validation["perimeter_m"]), "vertex_count": int(validation["vertex_count"]),
                        "is_convex": bool(validation["is_convex"]), "validation_status": validation["status"],
                        "validation_notes": validation.get("notes", []), "use_computed_area": bool(use_poly_area),
                        "front_edges": [edge_labels[x] for x in front_labels],
                        "rear_edges": [edge_labels[x] for x in rear_labels],
                        "edge_lengths_m": [e["length"] for e in edge_rows],
                        "source_points_wgs84": candidate.get("source_points_wgs84"),
                        "source_centroid_wgs84": candidate.get("source_centroid_wgs84"),
                        "source_location_point_wgs84": candidate.get("source_location_point_wgs84") or candidate.get("source_centroid_wgs84"),
                        "source_location_method": candidate.get("source_location_method", "KML location point" if source_type == "kml" else None),
                        "source_fingerprint": fingerprint,
                        "holes_m": candidate_holes_m(candidate, float(factor)),
                        "source_holes_wgs84": candidate.get("source_holes_wgs84"),
                    }
                    st.session_state["siteiq_front_edges"] = [edge_labels[x] for x in front_labels]
                    st.session_state["siteiq_rear_edges"] = [edge_labels[x] for x in rear_labels]
                    st.session_state.pop("siteiq_report", None)
                    st.rerun()

    with b_col2:
        active_boundary = st.session_state.get("siteiq_boundary")
        if active_boundary:
            st.markdown("**Active Applied Boundary**")
            m1, m2 = st.columns(2)
            m1.metric("Calculated Area", f"{active_boundary['area_m2']:,.2f} m²")
            m2.metric("Perimeter", f"{active_boundary['perimeter_m']:,.2f} m")
            m3, m4 = st.columns(2)
            m3.metric("Vertices", str(active_boundary['vertex_count']))
            m4.metric("Road Frontage Edges", str(len(active_boundary.get('front_edges', []))))

            # Diagram preview
            parcel = Polygon(active_boundary["points_m"])
            fig = make_boundary_edge_preview(parcel)
            st.pyplot(fig, clear_figure=True)

            if st.button("Remove Active Boundary", key="siteiq_remove_boundary"):
                st.session_state.pop("siteiq_boundary", None)
                st.session_state.pop("siteiq_report", None)
                st.rerun()
        else:
            st.info("Upload a DXF or KML file on the left to extract the boundary polygon.")

# -----------------------------------------------------------------------------
# TAB 3: ZONING & ROAD CONTEXT
# -----------------------------------------------------------------------------
with tab_zone:
    st.markdown('<div class="section-label">Workspace 03</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Zoning & Abutting Road Context</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Specify the regulatory planning authority, land-use category, abutting road width, and statutory deductions.</div>', unsafe_allow_html=True)

    current_authority_default = _val("authority_key", None)
    if current_authority_default not in authority_labels:
        current_authority_default = (detection or {}).get("suggested_authority_key") or "other_karnataka"
    if current_authority_default not in authority_labels:
        current_authority_default = "other_karnataka"

    z_col1, z_col2 = st.columns([1.1, 1.1], gap="large")
    with z_col1:
        st.markdown("**Planning Jurisdiction**")
        authority_key = st.selectbox(
            "Planning Authority / Rules Profile",
            options=[a["key"] for a in authorities],
            format_func=lambda k: authority_labels[k],
            index=[a["key"] for a in authorities].index(current_authority_default),
            key="siteiq_authority_key",
        )
        authority, profile = _profile_for(authority_key)
        if profile:
            st.caption(f"Profile: {profile.get('profile_name')} · Status: {profile.get('profile_status')}")
        else:
            st.warning("No operative rules profile configured for this authority yet.")

        st.markdown("**Land-Use Category**")
        official_zone = (detection or {}).get("zone", {}).get("value", _val("official_zone", "Not verified"))
        st.markdown(f"Official Map Zone: `{official_zone}`")

        if profile:
            category_items = land_use_categories(profile)
            category_labels = [c.get("label", c.get("key")) for c in category_items]
            previous_category = _val("land_use_category", "")
            category_default = previous_category if previous_category in category_labels else "Select a land-use category"
            category_options = ["Select a land-use category"] + category_labels
            category_index = category_options.index(category_default) if category_default in category_options else 0
            land_use_category = st.selectbox("Regulatory Land-Use Category", category_options, index=category_index, key="siteiq_land_use_category")
        else:
            land_use_category = "Select a land-use category"
            st.selectbox("Regulatory Land-Use Category", ["No categories configured"], disabled=True, key="siteiq_cat_disabled")

        use_options = ["Residential apartments", "Individual house / villa", "Commercial / office", "Mixed use", "Institutional / other", "Industrial / warehouse", "Public / semi-public use", "Parking structure"]
        use_default = _val("proposed_use", "Residential apartments")
        proposed_use = st.selectbox("Proposed Building Use", use_options, index=use_options.index(use_default) if use_default in use_options else 0, key="siteiq_proposed_use")

    with z_col2:
        st.markdown("**Site Area & Road Width Parameters**")
        active_boundary = st.session_state.get("siteiq_boundary")
        if active_boundary and active_boundary.get("use_computed_area", True):
            site_area_m2 = float(active_boundary["area_m2"])
            st.metric("Plot Area (from polyline)", f"{site_area_m2:,.2f} m²")
            site_area_source = "imported polyline area"
        else:
            site_area_m2 = st.number_input("Verified Plot Area (m²)", min_value=0.0, value=float(_val("site_area_m2", 0.0) or 0.0), step=50.0, key="siteiq_site_area")
            site_area_source = "user-entered survey/title area"

        road_width_m = st.number_input("Abutting Legal Road Width (m)", min_value=0.0, value=float(_val("road_width_m", 0.0) or 0.0), step=0.5, key="siteiq_road_width", help="Notified ROW / road width shown on master plan.")

        statutory_deduction_pct = st.number_input(
            "Reservation assumption % (what-if, not a rule)",
            min_value=0.0, max_value=50.0,
            value=float(_val("statutory_deduction_pct", 0.0) or 0.0),
            step=1.0,
            key="siteiq_statutory_deduction_pct",
            help="Only an assumption. Configured rules apply their own deduction automatically. Enter the figure from the operative plan if you want to test one."
        )

        approval_path_options = [
            "Not sure / needs confirmation",
            "New single-plot approval under Chapter 6-A",
            "Existing sanctioned plan / modification",
            "Development plan / layout",
            "Group housing / residential development-plan candidate",
            "Non-residential development-plan candidate",
            "Other",
        ]
        approval_default = _val("approval_path", (detection or {}).get("approval_route", {}).get("suggested_value", approval_path_options[0]))
        approval_path = st.selectbox("Approval Route Pathway", approval_path_options, index=approval_path_options.index(approval_default) if approval_default in approval_path_options else 0, key="siteiq_approval_path")

# -----------------------------------------------------------------------------
# TAB 4: MAXIMUM FAR ENGINE
# -----------------------------------------------------------------------------
with tab_far:
    st.markdown('<div class="section-label">Workspace 04</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Maximum FAR & Statutory Controls Engine</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Transparent audit trace of matched bands, limiting factors, statutory net area deductions, and rule sources.</div>', unsafe_allow_html=True)

    surrounding_zone = None
    if land_use_category == "Commercial Axes (inherits surrounding zone)" and profile:
        main_categories = [c["label"] for c in land_use_categories(profile) if c.get("method") in {"area_cap_and_road_width", "road_width", "plot_area", "fixed"}]
        surrounding_zone = st.selectbox("Official Surrounding Zone", ["Select surrounding zone"] + main_categories, key="siteiq_surrounding_zone")
        if surrounding_zone == "Select surrounding zone": surrounding_zone = None

    far_preview = _candidate_status(
        profile, land_use_category, site_area_m2, road_width_m,
        surrounding_zone=surrounding_zone, proposed_use=proposed_use,
        statutory_deduction_pct=statutory_deduction_pct
    )

    if far_preview.get("status") == "candidate_match_requires_verification":
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Maximum Base FAR", f"{far_preview['maximum_far']:.2f}")
        f2.metric("Net Calculation Area", f"{far_preview.get('far_calculation_area_m2', site_area_m2):,.0f} m²")
        f3.metric("FAR Area Capacity", f"{far_preview['maximum_far_area_m2']:,.0f} m²")
        detail = (far_preview.get("matched_rule") or {}).get("details", {})
        f4.metric("Limiting Factor", str(detail.get("limiting_factor", "table rule")).title())

        with st.container(border=True):
            st.markdown("**Rule Verification Trace**")
            st.write(far_preview.get("message", ""))
            if detail.get("far_calculation_area_m2") is not None:
                st.caption(f"Gross Site Area: {detail.get('gross_site_area_m2', site_area_m2):,.2f} m² · Statutory Deduction: {detail.get('deduction_pct', 0):g}% · Net Calculation Area: {detail.get('far_calculation_area_m2'):,.2f} m²")
            if far_preview.get("source"):
                src = far_preview["source"]
                st.caption(f"Legal Source: {src.get('title','')} · {src.get('clause','')} · Page {src.get('document_page','')} · Notification {src.get('notification','')}")
                if src.get("url"):
                    st.markdown(f"[Open Official Gazette / Source Document]({src['url']})")

        premium = far_preview.get("premium_far")
        if premium:
            with st.expander("Optional Premium FAR / TDR Upside Scenario (Quarantined from Base FAR)", expanded=False):
                st.caption(premium.get("message", ""))
                if premium.get("additional_far_candidate") is not None:
                    p1, p2, p3 = st.columns(3)
                    p1.metric("Additional FAR Ceiling", f"+{premium['additional_far_candidate']:.2f}")
                    p2.metric("Additional Floor Area", f"+{premium['additional_floor_area_candidate_m2']:,.0f} m²")
                    p3.metric("Potential Total FAR", f"{premium['potential_total_far_candidate']:.2f}")
    else:
        st.info(far_preview.get("message", "Configure site area and road width in Tab 3 to view the FAR rule match."))

# -----------------------------------------------------------------------------
# TAB 5: DESIGN SCENARIOS STUDIO
# -----------------------------------------------------------------------------
with tab_scen:
    st.markdown('<div class="section-label">Workspace 05</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Design Scenarios Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Configure multiple building height, floor count, setback, and basement scenarios.</div>', unsafe_allow_html=True)

    num_options = st.number_input("Number of options to compare", min_value=2, max_value=4, value=int(_val("num_options", 3) or 3), step=1, key="siteiq_num_options")
    scenarios = []
    defaults = _val("scenarios", [
        {"name": "Option 01", "height_m": 12, "floors": 4, "footprint_m2": 0, "stilt": False, "basement_levels": 1},
        {"name": "Option 02", "height_m": 15, "floors": 5, "footprint_m2": 0, "stilt": False, "basement_levels": 1},
        {"name": "Option 03", "height_m": 18, "floors": 6, "footprint_m2": 0, "stilt": False, "basement_levels": 2},
    ])

    for i in range(int(num_options)):
        d = defaults[i] if i < len(defaults) else {"name": f"Option {i+1}", "height_m": 12 + i * 3, "floors": 4 + i, "footprint_m2": 0, "stilt": False, "basement_levels": 0}
        with st.container(border=True):
            st.markdown(f"**Scenario Option {i+1}**")
            a, b, c, dcol = st.columns([1.5, 1, 1, 1.4])
            with a:
                opt_name = st.text_input("Option Name", value=st.session_state.get(f"siteiq_opt{i}_name", d.get("name", f"Option {i+1}")), key=f"siteiq_opt{i}_name")
            with b:
                opt_height = st.number_input("Total Height (m)", min_value=0.0, value=float(st.session_state.get(f"siteiq_opt{i}_height", d.get("height_m", 0.0)) or 0), step=1.0, key=f"siteiq_opt{i}_height")
            with c:
                opt_floors = st.number_input("Above-Ground Floors", min_value=0, max_value=100, value=int(st.session_state.get(f"siteiq_opt{i}_floors", d.get("floors", 0)) or 0), step=1, key=f"siteiq_opt{i}_floors")
            with dcol:
                opt_footprint = st.number_input("Footprint m² (0 = auto-envelope)", min_value=0.0, value=float(st.session_state.get(f"siteiq_opt{i}_footprint", d.get("footprint_m2", 0.0)) or 0), step=10.0, key=f"siteiq_opt{i}_footprint")

            e, f, g, h = st.columns([1, 1.6, 1, 1.6])
            with e:
                opt_stilt = st.checkbox("Stilt floor", value=bool(st.session_state.get(f"siteiq_opt{i}_stilt", d.get("stilt", False))), key=f"siteiq_opt{i}_stilt")
            with f:
                sb_options = ["Automatic rule lookup", "Manual all-round setback scenario"]
                sb_default = st.session_state.get(f"siteiq_opt{i}_setback_mode", d.get("setback_mode", "automatic"))
                sb_value = "Manual all-round setback scenario" if sb_default == "manual" else "Automatic rule lookup"
                sb_choice = st.selectbox("Setback Mode", sb_options, index=sb_options.index(sb_value), key=f"siteiq_opt{i}_setback_choice")
                sb_mode = "manual" if sb_choice.startswith("Manual") else "automatic"
            with g:
                manual_sb = st.number_input("Manual Setback (m)", min_value=0.0, value=float(st.session_state.get(f"siteiq_opt{i}_manual_sb", d.get("manual_all_round_setback_m", 0.0)) or 0), step=0.5, key=f"siteiq_opt{i}_manual_sb", disabled=sb_mode != "manual")
            with h:
                basement_levels = st.number_input("Basement Levels", min_value=0, max_value=5, value=int(st.session_state.get(f"siteiq_opt{i}_basements", d.get("basement_levels", 0)) or 0), step=1, key=f"siteiq_opt{i}_basements")

            j, k = st.columns([1.3, 1.3])
            with j:
                basement_choice = st.selectbox("Basement Setback Mode", ["Automatic rule lookup", "Manual scenario assumptions"], index=0 if st.session_state.get(f"siteiq_opt{i}_basement_mode", d.get("basement_setback_mode", "automatic")) != "manual" else 1, key=f"siteiq_opt{i}_basement_choice", disabled=basement_levels == 0)
                basement_mode = "manual" if basement_choice.startswith("Manual") else "automatic"
            with k:
                bf, bn = st.columns(2)
                with bf:
                    manual_bf = st.number_input("Basement Front (m)", min_value=0.0, value=float(st.session_state.get(f"siteiq_opt{i}_manual_bf", d.get("manual_basement_front_m", 0.0)) or 0), step=0.5, key=f"siteiq_opt{i}_manual_bf", disabled=basement_levels == 0 or basement_mode != "manual")
                with bn:
                    manual_bn = st.number_input("Basement Sides (m)", min_value=0.0, value=float(st.session_state.get(f"siteiq_opt{i}_manual_bn", d.get("manual_basement_nonfront_m", 0.0)) or 0), step=0.5, key=f"siteiq_opt{i}_manual_bn", disabled=basement_levels == 0 or basement_mode != "manual")

            scenarios.append({
                "name": opt_name or f"Option {i+1}", "height_m": opt_height or None, "floors": int(opt_floors) if opt_floors else None,
                "footprint_m2": float(opt_footprint) if opt_footprint > 0 else None, "stilt": bool(opt_stilt),
                "setback_mode": sb_mode, "manual_all_round_setback_m": float(manual_sb) if sb_mode == "manual" and manual_sb > 0 else None,
                "basement_levels": int(basement_levels), "basement_setback_mode": basement_mode,
                "manual_basement_front_m": float(manual_bf) if basement_mode == "manual" and manual_bf > 0 else None,
                "manual_basement_nonfront_m": float(manual_bn) if basement_mode == "manual" and manual_bn > 0 else None,
            })

    # High-rise check indicator
    any_high_rise = any((s.get("height_m") or 0) >= 21.0 for s in scenarios)
    if any_high_rise:
        st.markdown('<div class="badge-alert">HIGH-RISE (21 m or above): Fire NOC required under the Karnataka Fire Force Act. Take fire access dimensions from NBC 2016 Part 4 and the fire department.</div>', unsafe_allow_html=True)

    st.markdown("---")
    site_payload = {
        "project_name": project_name.strip() or "Untitled site feasibility", "client": client_name.strip(),
        "address": address.strip(), "map_url": map_url.strip(), "coordinates": coordinates.strip(),
        "authority_key": authority_key, "zone": land_use_category, "land_use_category": land_use_category,
        "official_zone": str(_val("official_zone", official_zone or "Not verified")), "surrounding_zone": surrounding_zone,
        "proposed_use": proposed_use, "site_area_m2": float(site_area_m2), "site_area_source": site_area_source,
        "road_width_m": float(road_width_m), "statutory_deduction_pct": float(statutory_deduction_pct) if statutory_deduction_pct > 0 else None,
        "height_for_setback_m": scenarios[0].get("height_m") if scenarios else None,
        "stilt": bool(scenarios[0].get("stilt", False)) if scenarios else False,
        "basement": "Option-specific" if any(x.get("basement_levels", 0) > 0 for x in scenarios) else "No basement selected",
        "approval_path": approval_path, "scenarios": scenarios,
        "boundary": active_boundary, "location": detection,
    }
    current_fingerprint = input_fingerprint(site_payload)
    run_assessment = st.button("Run regulatory and option feasibility", type="primary", use_container_width=True)
    if run_assessment:
        if site_area_m2 <= 0:
            st.error("A valid plot area is required. Import a boundary or enter a verified survey area.")
        elif road_width_m <= 0:
            st.error("Enter the abutting road width.")
        elif profile and (not land_use_category or land_use_category == "Select a land-use category"):
            st.error("Select the official regulatory land-use category.")
        else:
            st.session_state["siteiq_report"] = assess(site_payload, registry=registry)
            st.success("Feasibility assessment calculated. Switch to Tab 6 to inspect results and export reports.")

# -----------------------------------------------------------------------------
# TAB 6: COMPARATIVE FEASIBILITY & DOSSIER
# -----------------------------------------------------------------------------
with tab_dossier:
    st.markdown('<div class="section-label">Workspace 06</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Feasibility Dossier & Executive Outputs</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">Comparative option metrics, 2D envelope diagrams, statutory audit traces, and exportable client deliverables.</div>', unsafe_allow_html=True)

    report = st.session_state.get("siteiq_report")
    if report and report.get("input_fingerprint") != current_fingerprint:
        # Inputs changed since this assessment ran, so its figures and exports are no longer valid.
        st.session_state.pop("siteiq_report", None)
        report = None
        st.warning("Inputs changed, so the previous assessment was cleared. Run it again in Tab 5.")
    if report:
        verdict = report.get("verdict", {})
        st.markdown(f"**Status: {verdict.get('code', '').replace('_', ' ').title()}.** {verdict.get('message', '')}")
        with st.expander("Compliance register", expanded=False):
            st.dataframe(pd.DataFrame([{"Status": c["status"], "Check": c["title"], "Option": c.get("option") or "All", "Finding": c["message"]} for c in report.get("compliance_checks", [])]), use_container_width=True, hide_index=True)
        site = report["site"]
        far = report.get("far", {})

        # Top Metric Ribbon
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Site Area Used", f"{site['site_area_m2']:,.0f} m²")
        r2.metric("Abutting Road", f"{site['road_width_m']:.2f} m")
        r3.metric("Max Base FAR", f"{far['maximum_far']:.2f}" if far.get("maximum_far") is not None else "Unresolved")
        r4.metric("Benchmark Capacity", f"{far['maximum_far_area_m2']:,.0f} m²" if far.get("maximum_far_area_m2") is not None else "Unresolved")

        st.markdown(f"**Regulatory Land-Use:** `{site.get('land_use_category', 'Not selected')}` | **Authority:** `{site.get('authority', 'Not selected')}`")

        st.markdown("### Comparative Yield Matrix")
        rows = []
        for opt in report.get("scenarios", []):
            rows.append({
                "Option": opt.get("name"),
                "Height (m)": f"{opt.get('height_m')} m" if opt.get("height_m") is not None else "Not set",
                "Floors": opt.get("floors"),
                "Building Setbacks": opt.get("setback_summary", "Not determined"),
                "Basement Setbacks": opt.get("basement_setback_summary", "No basement"),
                "Footprint (m²)": opt.get("footprint_m2"),
                "Gross Concept Area (m²)": opt.get("gross_concept_area_m2"),
                "Achieved Gross FAR": opt.get("achieved_gross_far_ratio"),
                "Headroom vs Benchmark (m²)": opt.get("scenario_headroom_m2"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        for opt in report.get("scenarios", []):
            if opt.get("footprint_exceeds_envelope"):
                st.error(f"{opt['name']}: {opt.get('envelope_warning')}")

        # 2D Geometry Envelope View
        boundary = report.get("boundary_analysis")
        if boundary:
            st.markdown("### 2D Spatial Envelope Preview")
            b_left, b_right = st.columns([1.2, 0.8])
            with b_left:
                parcel = Polygon(boundary["geometry"]["coordinates"][0])
                env_map = {x["name"]: x["envelope"] for x in boundary.get("options", []) if x.get("envelope")}
                fig = make_boundary_preview(parcel, env_map)
                st.pyplot(fig, clear_figure=True)
            with b_right:
                env_rows = []
                for item in boundary.get("options", []):
                    benv = item.get("envelope", {})
                    env_rows.append({
                        "Option": item["name"],
                        "Envelope Area (m²)": f"{benv.get('area_m2', 0):,.1f}",
                        "Components": benv.get("component_count", 1),
                    })
                st.dataframe(pd.DataFrame(env_rows), use_container_width=True, hide_index=True)

                layers = {}
                for item in boundary.get("options", []):
                    layers[item["name"]] = item.get("envelope", {})
                    if item.get("basement_envelope", {}).get("geometry"):
                        layers[item["name"] + " basement"] = item["basement_envelope"]
                st.download_button(
                    "Download CAD DXF Envelopes",
                    data=export_boundary_dxf(parcel, layers),
                    file_name="SiteIQ_Boundary_Options.dxf",
                    mime="application/dxf",
                    use_container_width=True,
                )

        with st.expander("Statutory Citations & Verification Checklist", expanded=False):
            for src in report.get("sources", []):
                st.markdown(f"**{src.get('title','Rule Source')}**")
                st.caption(f"Notification: {src.get('notification','N/A')} · Date: {src.get('date','N/A')} · Clause: {src.get('clause','N/A')} · Status: {src.get('status','N/A')}")
                if src.get("url"):
                    st.markdown(f"[Source Document]({src['url']})")

        st.markdown("### Executive Deliverable Suite")
        pdf = build_pdf_report(report)
        pptx = build_pptx_report(report)
        board_pdf = build_a3_comparison_board_pdf(report)
        board_pptx = build_a3_comparison_board_pptx(report)

        e1, e2 = st.columns(2)
        with e1:
            st.download_button("📄 Client-Friendly PDF Feasibility Report", data=pdf, file_name="SiteIQ_Feasibility_Report.pdf", mime="application/pdf", use_container_width=True)
            st.download_button("📐 A3 Landscape Comparison Board (PDF)", data=board_pdf, file_name="SiteIQ_Feasibility_Board_A3.pdf", mime="application/pdf", use_container_width=True)
        with e2:
            st.download_button("📊 Editable PowerPoint Report (PPTX)", data=pptx, file_name="SiteIQ_Feasibility_Report.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)
            st.download_button("🖥️ Editable A3 Comparison Board (PPTX)", data=board_pptx, file_name="SiteIQ_Feasibility_Board_A3.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)

        st.download_button("💾 Complete Audit Assessment JSON", data=json.dumps(report, indent=2, ensure_ascii=False), file_name="SiteIQ_Assessment.json", mime="application/json", use_container_width=True)
    else:
        st.info("No feasibility assessment calculated yet. Configure your project parameters in Tabs 1–5 and click **Run regulatory and option feasibility** in Tab 5.")

st.markdown("---")
st.markdown('<div style="text-align: center; font-size: 0.80rem; color: #9CA3AF;">SiteIQ legacy interface | Preliminary feasibility only, not sanction advice</div>', unsafe_allow_html=True)
