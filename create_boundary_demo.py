"""Generate a boundary-engine demonstration using synthetic geometry (not a real parcel)."""
from __future__ import annotations
import json
from pathlib import Path
from shapely.geometry import Polygon, mapping
from siteiq.engine import build_report, load_authority_registry
from siteiq.exporters import build_pdf_report, build_pptx_report
from siteiq.boundary import calculate_setback_envelope, boundary_preview_png

ROOT = Path(__file__).resolve().parent
site = json.loads((ROOT / "sample_data" / "nandi_housing_test_case.json").read_text(encoding="utf-8"))
site.pop("sample_notes", None)
site["project_name"] = "Boundary Engine Demo — Synthetic Parcel"
site["address"] = "Synthetic example geometry — not a real surveyed parcel"
site["map_url"] = ""
site["coordinates"] = ""
site["shape_type"] = "Irregular / non-rectangular"
report = build_report(site, registry=load_authority_registry())
# Synthetic six-vertex parcel in local metre coordinates. Not based on the Nandi site survey.
parcel = Polygon([(0,0),(31,0),(35,25),(30,67),(3,65),(-2,38)])
front_edges = [0]  # only for demonstration; a real project user must identify legal road-facing edges
rear_edges = [3]
options = []
envelopes = {}
for opt in report.get("scenarios", []):
    env = calculate_setback_envelope(parcel, opt.get("setback_result", {}), front_edges, rear_edges)
    opt["boundary_envelope"] = env
    options.append({"name":opt.get("name", "Option"), "envelope":env})
    envelopes[opt.get("name", "Option")] = env
boundary = {
    "source_file":"illustrative_irregular_site.dxf",
    "source_type":"dxf",
    "source_units":"metres (synthetic sample)",
    "scale_to_m":1.0,
    "area_m2":float(parcel.area),
    "perimeter_m":float(parcel.length),
    "vertex_count":len(list(parcel.exterior.coords))-1,
    "is_convex":bool(parcel.equals(parcel.convex_hull)),
    "validation_status":"valid",
    "validation_notes":["Synthetic geometry only. It is not a legal parcel boundary and must not be used for design or sanction."],
    "use_computed_area":False,
    "area_difference_from_input_pct":round(abs(parcel.area-site["site_area_m2"])/site["site_area_m2"]*100,2),
    "front_edges":front_edges,
    "rear_edges":rear_edges,
    "geometry":mapping(parcel),
    "options":options,
    "limitation":"DEMO ONLY: a synthetic six-vertex boundary was used to demonstrate importing, scale checks and option envelopes. This is not the actual Nandi Housing boundary. Variable setbacks are approximate near complex concave corners and require CAD review."
}
report["boundary_analysis"] = boundary
out = ROOT / "sample_outputs"
(out / "SiteIQ_Boundary_Demo_Report.pdf").write_bytes(build_pdf_report(report))
(out / "SiteIQ_Boundary_Demo_Report.pptx").write_bytes(build_pptx_report(report))
(out / "SiteIQ_Boundary_Demo_Assessment.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
(out / "SiteIQ_Boundary_Demo_Preview.png").write_bytes(boundary_preview_png(parcel, envelopes))
print("Wrote synthetic boundary demo outputs. Do not use the synthetic parcel for any real project.")
