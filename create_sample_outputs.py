"""Generate sample reports and a rule-profile smoke-test record."""
import json
from pathlib import Path
from siteiq import __version__
from siteiq.engine import build_report, load_authority_registry
from siteiq.exporters import (
    build_pdf_report, build_pptx_report,
    build_a3_comparison_board_pdf, build_a3_comparison_board_pptx,
)
from siteiq.public_sources import official_sources_for_context

ROOT = Path(__file__).resolve().parent
out = ROOT / "sample_outputs"
out.mkdir(exist_ok=True)
registry = load_authority_registry()

# Nandi case: values from the user's manual feasibility study. It remains illustrative.
site = json.loads((ROOT / "sample_data" / "nandi_housing_test_case.json").read_text(encoding="utf-8"))
site.pop("sample_notes", None)
report = build_report(site, registry=registry)
report["location_identification"] = {
    "coordinates": {"latitude": 12.871003, "longitude": 77.569919, "text": "12.8710030, 77.5699190", "method": "illustrative_sample_only"},
    "geocoded_address": "Southern Bengaluru (illustrative sample location)",
    "authority": {"key": "bengaluru_rmp2015", "label": "Bengaluru / Greater Bengaluru RMP 2015 profile", "status": "provisional_geocoder_candidate", "confidence": "low", "reason": "Illustrative location candidate only; current planning boundary is not established.", "source_url": "https://www.openstreetmap.org/"},
    "zone": {"value": "Not verified", "status": "layer_not_installed", "reason": "No official land-use polygon match is claimed in this sample."},
    "approval_route": {"suggested_value": "Not sure / needs confirmation", "status": "suggestion_only", "reason": "Confirm official jurisdiction, land-use zone and the applicable approval path."},
    "public_sources": official_sources_for_context("bengaluru_rmp2015", "Southern Bengaluru"),
    "sample_note": "Illustrative location metadata, not a live jurisdiction lookup.",
}
(out / "SiteIQ_Nandi_Detailed_Report_v0.6.0.pdf").write_bytes(build_pdf_report(report))
(out / "SiteIQ_Nandi_Detailed_Report_v0.6.0.pptx").write_bytes(build_pptx_report(report))
(out / "SiteIQ_Nandi_Comparison_Board_A3_v0.6.0.pdf").write_bytes(build_a3_comparison_board_pdf(report))
(out / "SiteIQ_Nandi_Comparison_Board_A3_v0.6.0.pptx").write_bytes(build_a3_comparison_board_pptx(report))
(out / "SiteIQ_Nandi_Assessment_v0.6.0.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

# Hoskote rule-profile smoke test: uses KML-derived area from the supplied Test 02 sample
# and a 36 m road width solely to test the rule engine's conditional group-housing path.
hoskote_site = {
    "project_name": "Hoskote LPA FAR Profile Check — illustrative, not a design",
    "client": "Internal rule-profile test",
    "address": "Hoskote vicinity, Karnataka (sample KML centroid; exact jurisdiction not verified)",
    "map_url": "",
    "coordinates": "13.0733543, 77.7823976",
    "authority_key": "hoskote_planning_authority",
    "zone": "Not verified",
    "official_zone": "Not verified",
    "land_use_category": "Residential",
    "proposed_use": "Residential apartments",
    "site_area_m2": 20684.15,
    "site_area_source": "sample KML boundary area; illustrative profile test",
    "road_width_m": 36.0,
    "frontage_m": None,
    "depth_m": None,
    "shape_type": "Irregular / non-rectangular",
    "geometry_mode": "KML centroid/location sample; no design envelope in this rule-only test",
    "height_for_setback_m": 15,
    "stilt": False,
    "basement": "Not decided",
    "approval_path": "Group housing / residential development-plan candidate",
    "scenarios": [],
}
hoskote_report = build_report(hoskote_site, registry=registry)
hoskote_report["location_identification"] = {
    "coordinates": {"latitude": 13.0733543, "longitude": 77.7823976, "text": "13.0733543, 77.7823976", "method": "sample_kml_centroid"},
    "geocoded_address": "Hoskote vicinity (sample-derived context only)",
    "authority": {"key": "hoskote_planning_authority", "label": "Hoskote Planning Authority", "status": "provisional_candidate", "confidence": "low", "reason": "This sample tests the provisional Hoskote rules profile; it does not verify the site's notified planning boundary."},
    "zone": {"value": "Not verified", "status": "not_verified", "reason": "No authoritative land-use polygon is matched by this smoke-test record."},
    "approval_route": {"suggested_value": "Group housing / residential development-plan candidate", "status": "provisional_suggestion", "reason": "The area/use conditions lead to the configured group-housing path in the secondary-source profile; confirm applicable approval route."},
    "public_sources": [],
    "sample_note": "Rule-profile smoke test only. Road width of 36 m is an explicit illustrative input, not verified for the user's actual Hoskote parcel.",
}
(out / "SiteIQ_Hoskote_Profile_Check_v0.6.0.json").write_text(json.dumps(hoskote_report, indent=2, ensure_ascii=False), encoding="utf-8")
summary = {
    "release": __version__,
    "sample_type": "rule-profile smoke test only — not a client report or design proposal",
    "authority_profile": hoskote_report["site"]["rule_profile"],
    "source_quality": hoskote_report["far"].get("rule_source_quality"),
    "selected_path": (hoskote_report["far"].get("matched_rule") or {}).get("conditional_path_id"),
    "far_status": hoskote_report["far"]["status"],
    "candidate_far": hoskote_report["maximum_far"],
    "gross_site_area_m2": hoskote_report["site"]["site_area_m2"],
    "far_calculation_area_m2": hoskote_report["far"].get("far_calculation_area_m2"),
    "candidate_far_capacity_m2": hoskote_report["maximum_far_area_m2"],
    "key_warning": "Secondary-source candidate only; official land-use zone, notified jurisdiction, current operative rules and road width must be verified.",
}
(out / "SiteIQ_Hoskote_Profile_Check_v0.6.0_Summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
(out / "SiteIQ_Hoskote_Profile_Check_v0.6.0.txt").write_text(
    "SITEIQ v0.6.0 — Hoskote profile smoke test\n\n"
    "This is an internal rule-engine test, not a design feasibility report.\n"
    f"Configured FAR status: {summary['far_status']}\n"
    f"Provisional FAR candidate: {summary['candidate_far']}\n"
    f"Gross site area in test: {summary['gross_site_area_m2']:,.2f} m²\n"
    f"FAR calculation area after configured 5% deduction: {summary['far_calculation_area_m2']:,.2f} m²\n"
    f"Candidate FAR area capacity: {summary['candidate_far_capacity_m2']:,.2f} m²\n\n"
    + summary["key_warning"] + "\n",
    encoding="utf-8",
)
print("Generated v0.6.0 Nandi PDF/PPTX/A3/JSON outputs and Hoskote profile smoke-test JSON/TXT.")
