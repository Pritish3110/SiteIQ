"""Sweep every authority, category and awkward input through the full pipeline and all exports."""
import pytest
from shapely.geometry import Polygon

from siteiq.engine import land_use_categories, load_authority_registry, load_rule_profile
from siteiq.exporters import build_a3_comparison_board_pdf, build_a3_comparison_board_pptx, build_pdf_report, build_pptx_report
from siteiq.service import assess

REGISTRY = load_authority_registry()
AREAS = [50.0, 240.0, 2000.0, 4000.0, 15000.0, 60000.0]
ROADS = [3.0, 9.0, 12.0, 18.0, 45.0]
USES = ["Residential apartments", "Commercial / office", "Industrial / warehouse", "Mixed use"]
HOSTILE = '<b>A & B</b> "quoted" <script>x</script> ✓ कन्नಡ'


def boundary_for(points, front=(0,), rear=()):
    poly = Polygon(points)
    return {"source_file": "x", "source_type": "dxf", "points_m": [list(p) for p in points], "holes_m": [], "area_m2": poly.area, "perimeter_m": poly.length, "vertex_count": len(points), "is_convex": poly.equals(poly.convex_hull), "use_computed_area": True, "front_edges": list(front), "rear_edges": list(rear)}


def scenarios():
    return [
        {"name": "Low", "height_m": 9.0, "floors": 3, "footprint_m2": 100.0, "basement_levels": 1},
        {"name": "Stilt", "height_m": 13.5, "floors": 4, "stilt": True, "stilt_height_m": 2.4, "basement_levels": 2},
        {"name": "Tower", "height_m": 60.0, "floors": 20},
        {"name": "Blank"},
    ]


CASES = []
for authority in REGISTRY["authorities"]:
    profile = load_rule_profile(authority["rule_profile"]) if authority.get("rule_profile") else None
    for category in [c["label"] for c in land_use_categories(profile)] or ["Not configured"]:
        CASES.append((authority["key"], category))


@pytest.mark.parametrize("key,category", CASES)
def test_every_category_at_every_size_never_crashes_and_never_invents_a_verdict(key, category):
    for area in AREAS:
        for road in ROADS:
            for use in USES[:2]:
                report = assess({"project_name": "x", "authority_key": key, "land_use_category": category, "proposed_use": use, "site_area_m2": area, "road_width_m": road, "scenarios": scenarios()})
                assert report["verdict"]["code"] in {"BLOCKED", "INCOMPLETE"}
                far = report["far"]
                if far.get("maximum_far") is not None:
                    assert far["maximum_far"] > 0
                    assert far["source"] is not None, "a FAR must carry its source"
                    assert far["maximum_far_area_m2"] <= area * far["maximum_far"] + 0.01
                if not load_rule_profile(next(a for a in REGISTRY["authorities"] if a["key"] == key).get("rule_profile") or ""):
                    assert far.get("maximum_far") is None


SHAPES = {
    "triangle": ([(0, 0), (60, 0), (30, 50)], (0,), ()),
    "narrow_strip": ([(0, 0), (200, 0), (200, 6), (0, 6)], (0,), (2,)),
    "panhandle": ([(0, 0), (4, 0), (4, 30), (40, 30), (40, 70), (-36, 70), (-36, 30), (0, 30)], (0,), (5,)),
    "clockwise": ([(0, 0), (0, 40), (50, 40), (50, 0)], (1,), (3,)),
    "no_front": ([(0, 0), (40, 0), (40, 40), (0, 40)], (), ()),
    "many_vertices": ([(50 + 40 * __import__("math").cos(i / 200 * 6.283), 50 + 40 * __import__("math").sin(i / 200 * 6.283)) for i in range(200)], (0, 1, 2), ()),
}


@pytest.mark.parametrize("name", SHAPES)
def test_awkward_shapes_and_hostile_text_export_everywhere(name):
    points, front, rear = SHAPES[name]
    report = assess({"project_name": HOSTILE, "client": HOSTILE, "address": HOSTILE, "map_url": "https://maps.google.com/?q=1&x=<y>", "authority_key": "bengaluru_rmp2015", "land_use_category": "Residential (Main)", "proposed_use": "Residential apartments", "site_area_m2": 1.0, "road_width_m": 12.0, "boundary": boundary_for(points, front, rear), "overlays": {"drain": {"status": "present", "edge": 0, "extra_setback_m": 5.0, "drain_class": "tertiary"}}, "scenarios": [dict(s, name=HOSTILE if i == 0 else s["name"]) for i, s in enumerate(scenarios())]})
    assert build_pdf_report(report).startswith(b"%PDF")
    assert build_a3_comparison_board_pdf(report).startswith(b"%PDF")
    assert build_pptx_report(report).startswith(b"PK")
    assert build_a3_comparison_board_pptx(report).startswith(b"PK")


@pytest.mark.parametrize("key,category,area,road", [("mysuru_development_authority", "Not configured", 2000.0, 18.0), ("bengaluru_rmp2015", "Park and Open Space (P)", 2000.0, 18.0), ("bengaluru_rmp2015", "Residential (Main)", 30000.0, 18.0), ("hoskote_planning_authority", "Residential", 12000.0, 9.0)])
def test_unresolved_far_still_exports_honestly(key, category, area, road):
    import fitz
    report = assess({"project_name": "x", "authority_key": key, "land_use_category": category, "proposed_use": "Residential apartments", "site_area_m2": area, "road_width_m": road, "scenarios": scenarios()})
    assert report["maximum_far"] is None
    text = " ".join(p.get_text() for p in fitz.open(stream=build_pdf_report(report), filetype="pdf"))
    assert "COMPLIANCE REGISTER" in text
    assert build_pptx_report(report) and build_a3_comparison_board_pptx(report) and build_a3_comparison_board_pdf(report)
