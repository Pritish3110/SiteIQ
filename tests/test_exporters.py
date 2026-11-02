import json
from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pptx import Presentation
from siteiq.engine import load_authority_registry, build_report
from siteiq.exporters import build_pdf_report, build_pptx_report

ROOT = Path(__file__).resolve().parents[1]


def sample_report():
    site = json.loads((ROOT / "sample_data" / "nandi_housing_test_case.json").read_text(encoding="utf-8"))
    site.pop("sample_notes", None)
    return build_report(site, registry=load_authority_registry())


def test_client_pdf_is_generated():
    pdf = build_pdf_report(sample_report())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 8000


def test_client_pptx_has_five_client_facing_slides():
    pptx = build_pptx_report(sample_report())
    prs = Presentation(BytesIO(pptx))
    assert len(prs.slides) == 6  # Five client slides, plus the separate Premium FAR slide.
    texts = []
    for shape in prs.slides[2].shapes:
        if getattr(shape, "has_text_frame", False):
            texts.append(shape.text)
        if getattr(shape, "has_table", False):
            texts.extend(cell.text for row in shape.table.rows for cell in row.cells)
    slide_text = "\n".join(texts)
    assert "COMPARE THE OPTIONS" in slide_text
    assert "5.00 m on all sides" in slide_text
    assert "6.00 m on all sides" in slide_text


def test_report_exporters_include_boundary_page_and_slide():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from shapely.geometry import Polygon, mapping
    from siteiq.engine import load_authority_registry, build_report
    from siteiq.exporters import build_pdf_report, build_pptx_report
    site = {
        "project_name":"Boundary test", "address":"Test site", "authority_key":"bengaluru_rmp2015",
        "site_area_m2":2200, "road_width_m":18.5, "frontage_m":33, "depth_m":68,
        "zone":"Residential (Main)", "proposed_use":"Residential apartments", "shape_type":"Irregular / non-rectangular",
        "height_for_setback_m":12, "stilt":False,
        "scenarios":[
            {"name":"Option 01", "height_m":12, "floors":4, "footprint_m2":1000, "assumed_far":2.5, "stilt":False},
            {"name":"Option 02", "height_m":15, "floors":5, "footprint_m2":900, "assumed_far":2.5, "stilt":False},
        ]
    }
    report = build_report(site, registry=load_authority_registry())
    parcel = Polygon([(0,0),(31,0),(35,25),(30,67),(3,65),(-2,38)])
    opts = []
    for opt in report["scenarios"]:
        env = __import__("siteiq.boundary", fromlist=["calculate_setback_envelope"]).calculate_setback_envelope(parcel, opt["setback_result"], [0], [3])
        opt["boundary_envelope"] = env
        opts.append({"name":opt["name"], "envelope":env})
    report["boundary_analysis"] = {
        "source_file":"test.dxf", "source_type":"dxf", "area_m2":parcel.area,
        "perimeter_m":parcel.length, "vertex_count":6, "area_difference_from_input_pct":0.84,
        "geometry":mapping(parcel), "options":opts,
        "limitation":"Test boundary only; survey verification is required."
    }
    pdf = build_pdf_report(report)
    pptx = build_pptx_report(report)
    assert pdf[:4] == b"%PDF"
    assert len(pptx) > 10000
    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert any("IMPORTED SITE BOUNDARY" in page.get_text() for page in doc)
    doc.close()


def test_exporters_include_auto_identification_provenance():
    import fitz
    report = sample_report()
    report["location_identification"] = {
        "coordinates": {"text": "12.8710000, 77.5690000", "method": "user_entered_coordinates"},
        "authority": {"key": "bengaluru_rmp2015", "label": "Bengaluru partial RMP profile", "status": "provisional_geocoder_candidate", "reason": "Locality-based candidate only."},
        "zone": {"value": "Not verified", "status": "layer_not_installed", "reason": "Official land-use polygon layer not installed."},
        "approval_route": {"suggested_value": "New single-plot approval under Chapter 6-A", "status": "provisional_candidate", "reason": "Confirm plot identity and applicability."},
    }
    pdf = build_pdf_report(report)
    doc = fitz.open(stream=pdf, filetype="pdf")
    all_text = "\n".join(page.get_text() for page in doc)
    assert "Location auto-identification record" in all_text
    assert "Official land-use polygon layer not installed" in all_text
    assert len(doc) == 6, "Auto-ID appendix should not orphan the closing note onto a mostly blank page."
    assert "not a sanction report" in all_text.lower()
    doc.close()
    prs = Presentation(BytesIO(build_pptx_report(report)))
    ppt_text = "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False))
    assert "Location lookup" in ppt_text
    assert "12.8710000, 77.5690000" in ppt_text


def test_a3_comparison_board_pdf_and_pptx_export_option_setbacks_and_basements():
    import fitz
    from siteiq.exporters import build_a3_comparison_board_pdf, build_a3_comparison_board_pptx
    report = sample_report()
    pdf = build_a3_comparison_board_pdf(report)
    doc = fitz.open(stream=pdf, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    assert abs(page.rect.width - 1190.55) < 2
    text = page.get_text()
    assert "FLOOR-AREA COMPARISON" in text
    assert "BUILDING SETBACK" in text
    assert "BASEMENT" in text
    assert "5.00 m on all sides" in text
    assert "6.00 m on all sides" in text
    assert "5,500 m²" in text
    doc.close()
    pptx = build_a3_comparison_board_pptx(report)
    prs = Presentation(BytesIO(pptx))
    assert len(prs.slides) == 1
    assert abs(prs.slide_width / 914400 - 16.54) < 0.01
    texts=[]
    for shape in prs.slides[0].shapes:
        if getattr(shape, "has_text_frame", False): texts.append(shape.text)
        if getattr(shape, "has_table", False):
            texts.extend(cell.text for row in shape.table.rows for cell in row.cells)
    all_text="\n".join(texts)
    assert "FLOOR-AREA COMPARISON" in all_text
    assert "BASEMENT" in all_text
    assert "5.00 m on all sides" in all_text
    assert "6.00 m on all sides" in all_text


def test_provisional_far_source_warning_and_net_basis_are_exported():
    import fitz
    registry = load_authority_registry()
    site = {
        "authority_key": "hoskote_planning_authority", "project_name": "Hoskote profile output test",
        "site_area_m2": 20684.0, "road_width_m": 36, "frontage_m": 120, "depth_m": 171,
        "zone": "Not verified", "land_use_category": "Residential", "proposed_use": "Residential apartments",
        "shape_type": "Irregular / non-rectangular", "height_for_setback_m": 15,
        "scenarios": [{"name":"Option 01","height_m":15,"floors":5,"footprint_m2":10000,"stilt":False,"basement_levels":0}],
    }
    report = build_report(site, registry=registry)
    pdf = build_pdf_report(report)
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    assert "provisional far candidate" in text.lower()
    assert "net far calculation area" in text.lower()
    doc.close()
    prs = Presentation(BytesIO(build_pptx_report(report)))
    ppt_text = "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False))
    assert "PROVISIONAL TABLE CANDIDATE" in ppt_text
    assert "net FAR area" in ppt_text
    assert "OPTIONAL ADDITIONAL FAR SCENARIO" in ppt_text
