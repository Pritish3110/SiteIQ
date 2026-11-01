"""Refresh the bundled location auto-identification demo reports.

The location_identification metadata in the JSON is illustrative, not a live lookup.
"""
import json
from pathlib import Path
from siteiq.exporters import build_pdf_report, build_pptx_report

ROOT = Path(__file__).resolve().parent
out = ROOT / "sample_outputs"
report = json.loads((out / "SiteIQ_Location_AutoID_Demo_Assessment.json").read_text(encoding="utf-8"))
(out / "SiteIQ_Location_AutoID_Demo_Report.pdf").write_bytes(build_pdf_report(report))
(out / "SiteIQ_Location_AutoID_Demo_Report.pptx").write_bytes(build_pptx_report(report))
print("Refreshed Auto-ID demo. Location metadata is illustrative, not a live lookup.")
