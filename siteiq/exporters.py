"""Client-friendly PDF and editable PowerPoint report exporters for SiteIQ."""
from __future__ import annotations
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Image
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR

from . import __version__

NAVY = colors.HexColor('#111111')
TEAL = colors.HexColor('#111111')
MINT = colors.HexColor('#F2F2F2')
ORANGE = colors.HexColor('#555555')
PALE = colors.HexColor('#F5F5F5')
GREY = colors.HexColor('#656565')
RED = colors.HexColor('#111111')
WHITE = colors.white


STATUS_LABELS = {"PASS": "Pass", "FAIL": "Fail", "NEEDS_INPUT": "Needs input", "NOT_CONFIGURED": "Not configured", "REFER": "Confirm"}
VERDICT_LABELS = {"BLOCKED": "Blocked", "INCOMPLETE": "Incomplete", "PROVISIONAL": "Provisional", "READY_FOR_REVIEW": "Ready for review"}
CHECK_ORDER = {"FAIL": 0, "NEEDS_INPUT": 1, "REFER": 2, "NOT_CONFIGURED": 3, "PASS": 4}


def _sorted_checks(report: dict) -> list[dict]:
    return sorted(report.get("compliance_checks") or [], key=lambda c: CHECK_ORDER.get(c.get("status"), 9))


def _verdict_line(report: dict) -> str | None:
    verdict = report.get("verdict")
    if not verdict:
        return None
    return f"{VERDICT_LABELS.get(verdict['code'], verdict['code'])}: {verdict['message']}"


def _compliance_story(report: dict, styles) -> list:
    """Full check register: every provision and its outcome, so nothing unassessed reads as a pass."""
    checks = _sorted_checks(report)
    if not checks:
        return []
    rows = [[_p(h, styles["ClientTableHead"]) for h in ("Status", "Check", "Option", "Finding", "Source")]]
    for c in checks:
        src = c.get("source") or {}
        rows.append([
            _p(f"<b>{STATUS_LABELS.get(c['status'], c['status'])}</b>", styles["ClientTableSmall"]),
            _p(_html(c.get("title", "")), styles["ClientTableSmall"]),
            _p(_html(c.get("option") or "All"), styles["ClientTableSmall"]),
            _p(_html(c.get("message", "")), styles["ClientTableSmall"]),
            _p(_html(src.get("notification") or src.get("title") or "—"), styles["ClientTableSmall"]),
        ])
    table = Table(rows, colWidths=[20*mm, 40*mm, 22*mm, 131*mm, 60*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#CCCCCC')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
    ]))
    counts = (report.get("verdict") or {}).get("counts", {})
    summary = " · ".join(f"{counts.get(k, 0)} {STATUS_LABELS[k].lower()}" for k in ("FAIL", "NEEDS_INPUT", "REFER", "NOT_CONFIGURED", "PASS"))
    return [PageBreak(), _p("COMPLIANCE REGISTER", styles["ClientTitle"]), _p(_html(summary), styles["ClientSubtitle"]), table]


def _fmt(value, suffix=""):
    if value is None or value == "":
        return "Not provided"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value}{suffix}"


def _status_text(status):
    return str(status or "pending").replace("_", " ").title()


def _html(value):
    return escape(str(value if value is not None else ""), {'"': '&quot;'})


def _p(text, style):
    return Paragraph(str(text), style)


def _plain_far_summary(report: dict) -> str:
    far = report.get("far", {})
    if far.get("status") in {"no_matching_table_row", "no_matching_far_band", "outside_configured_table_scope"}:
        return (
            "SiteIQ could not identify one unambiguous rule for the inputs. It has not guessed or interpolated a FAR. "
            "Confirm the applicable zone, plot-area band, road-width band and operative notification before fixing the design."
        )
    if far.get("status") == "candidate_match_requires_verification":
        row = far.get("matched_rule") or {}
        profile_quality = far.get("rule_source_quality")
        prefix = "A provisional FAR candidate transcribed from a secondary plan copy is" if profile_quality == "secondary_copy_pending_official_validation" else "The selected configured table gives a maximum FAR candidate of"
        if profile_quality == "secondary_copy_pending_official_validation":
            message = f"{prefix} {row.get('far', 'not stated')}. The current operative version and amendments have not been confirmed."
        else:
            message = f"{prefix} {row.get('far', 'not stated')}."
        details = row.get("details", {})
        basis = row.get("far_calculation_area_m2")
        if basis is not None and row.get("gross_site_area_m2") is not None and abs(float(basis)-float(row["gross_site_area_m2"])) > 0.01:
            message += f" FAR area uses a configured net calculation area of {float(basis):,.0f} m², not the gross plot area."
        return message + " This is a rule-based starting point, not a sanctioned entitlement. Confirm the jurisdiction, official land-use zone, road width and current rule before relying on it."
    if far.get("status") in {"not_configured", "zone_not_supported"}:
        return "This authority/category is not configured sufficiently in SiteIQ to calculate a maximum FAR. No rule from another authority has been substituted."
    return far.get("message", "The applicable floor-area rule still needs to be confirmed.")


def _scenario_target(report: dict):
    """Return only a rule-derived FAR benchmark; never promote legacy assumed FAR to entitlement."""
    site = report.get("site") or {}
    far = report.get("far") or {}
    max_far = report.get("maximum_far")
    if max_far is None:
        max_far = far.get("maximum_far")
    if max_far is not None and float(max_far) > 0 and site.get("site_area_m2"):
        area = report.get("maximum_far_area_m2")
        if area is None:
            area = float(site["site_area_m2"]) * float(max_far)
        return float(area), float(max_far)
    manual = site.get("manual_benchmark_far")
    if manual is not None and float(manual) > 0 and site.get("site_area_m2"):
        return float(site["site_area_m2"]) * float(manual), float(manual)
    return None, None


def _option_setback_plain(opt: dict) -> str:
    sb = opt.get("setback_result") or {}
    all_round = sb.get("all_round_m")
    if all_round is not None:
        return f"{all_round:.2f} m on all sides"
    vals = [sb.get(k) for k in ("front_m", "rear_m", "left_m", "right_m")]
    if all(v is not None for v in vals):
        return f"Front {vals[0]:.2f} m; rear {vals[1]:.2f} m; sides {vals[2]:.2f} / {vals[3]:.2f} m"
    return "Not determined from configured rules"


def _option_setback_basis_plain(opt: dict) -> str:
    sb = opt.get("setback_result") or {}
    if sb.get("all_round_m") is not None:
        return "Height-band rule (preliminary)"
    if all(sb.get(k) is not None for k in ("front_m", "rear_m", "left_m", "right_m")):
        return "Percentage method (nominal distances)"
    return "Rule not configured / inputs incomplete"


def _option_difference_plain(opt: dict, target: float | None) -> str:
    actual = opt.get("gross_concept_area_m2")
    if actual is None or target is None:
        return "Working target not set"
    delta = actual - target
    if abs(delta) < 0.5:
        return "At working target"
    if delta > 0:
        return f"{delta:,.0f} m² above target"
    return f"{abs(delta):,.0f} m² below target"


def _make_styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="ClientTitle", parent=s["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, alignment=TA_LEFT, spaceAfter=3))
    s.add(ParagraphStyle(name="ClientSubtitle", parent=s["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=GREY, spaceAfter=5))
    s.add(ParagraphStyle(name="ClientH2", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=15, textColor=TEAL, spaceBefore=4, spaceAfter=4))
    s.add(ParagraphStyle(name="ClientH3", parent=s["Heading3"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=NAVY, spaceBefore=3, spaceAfter=2))
    s.add(ParagraphStyle(name="ClientBody", parent=s["BodyText"], fontName="Helvetica", fontSize=8.1, leading=10.2, textColor=NAVY, spaceAfter=3))
    s.add(ParagraphStyle(name="ClientSmall", parent=s["BodyText"], fontName="Helvetica", fontSize=7, leading=8.5, textColor=GREY, spaceAfter=2))
    s.add(ParagraphStyle(name="ClientTable", parent=s["BodyText"], fontName="Helvetica", fontSize=7.3, leading=8.8, textColor=NAVY))
    s.add(ParagraphStyle(name="ClientTableSmall", parent=s["BodyText"], fontName="Helvetica", fontSize=6.7, leading=8, textColor=NAVY))
    s.add(ParagraphStyle(name="ClientTableHead", parent=s["BodyText"], fontName="Helvetica-Bold", fontSize=7.1, leading=8.5, textColor=WHITE))
    s.add(ParagraphStyle(name="Callout", parent=s["BodyText"], fontName="Helvetica", fontSize=8.2, leading=10.5, textColor=NAVY, spaceAfter=0))
    s.add(ParagraphStyle(name="CalloutTitle", parent=s["BodyText"], fontName="Helvetica-Bold", fontSize=9.4, leading=11, textColor=NAVY, spaceAfter=3))
    return s


def build_pdf_report(report: dict) -> bytes:
    """Generate a plain-English client report, followed by a technical source appendix."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm,
        topMargin=10*mm, bottomMargin=13*mm,
        title=f"SiteIQ - {report.get('project','Site feasibility')} - Client-friendly feasibility report"
    )
    styles = _make_styles()
    story = []
    site = report["site"]
    scenarios = report.get("scenarios", [])
    target_m2, target_far = _scenario_target(report)
    far = report.get("far", {})

    # PAGE 1: Plain-English outcome, site snapshot and what this means.
    story.append(_p("SITE FEASIBILITY | CLIENT SUMMARY", styles["ClientTitle"]))
    story.append(_p(f"{_html(report.get('project','Untitled site'))}  |  Prepared { _html(report.get('application',{}).get('assessment_date','')) }  |  Early-stage review", styles["ClientSubtitle"]))

    verdict_line = _verdict_line(report)
    if verdict_line:
        verdict_table = Table([[_p(f"<b>{_html(verdict_line)}</b>", styles["Callout"])]], colWidths=[273*mm])
        verdict_table.setStyle(TableStyle([('BOX',(0,0),(-1,-1),1.2,NAVY),('LEFTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story += [verdict_table, Spacer(1, 2*mm)]

    if far.get("status") == "no_matching_table_row":
        banner_title = "Current position: one key rule still needs confirmation"
    elif far.get("status") == "not_configured":
        banner_title = "Current position: this authority's rules are not yet configured"
    elif far.get("status") == "candidate_match_requires_verification" and far.get("rule_source_quality") == "secondary_copy_pending_official_validation":
        banner_title = "Current position: provisional FAR candidate — source checks required"
    elif far.get("status") == "candidate_match_requires_verification":
        banner_title = "Current position: possible rule found, confirmation still needed"
    else:
        banner_title = "Current position: preliminary check only"
    callout = Table([
        [_p(_html(banner_title), styles["CalloutTitle"])],
        [_p(_html(_plain_far_summary(report)), styles["Callout"])],
    ], colWidths=[273*mm])
    callout.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F5F5F5')),
        ('BOX',(0,0),(-1,-1),0.6,colors.HexColor('#BDBDBD')),
        ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
    ]))
    story += [callout, Spacer(1, 3*mm)]

    metrics = [
        [_p("PLOT AREA", styles["ClientTableHead"]), _p("ROAD WIDTH PROVIDED", styles["ClientTableHead"]), _p("PROPOSED PROJECT", styles["ClientTableHead"]), _p("SITE SHAPE", styles["ClientTableHead"])],
        [_p(f"{site['site_area_m2']:,.0f} m²", styles["ClientTable"]), _p(f"{site['road_width_m']:.2f} m", styles["ClientTable"]), _p(_html(site.get('proposed_use','Not supplied')), styles["ClientTable"]), _p(_html(site.get('shape_type','Not known')), styles["ClientTable"])],
    ]
    mt = Table(metrics, colWidths=[47*mm, 53*mm, 83*mm, 90*mm], rowHeights=[8*mm, 10*mm])
    mt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),TEAL),('BACKGROUND',(0,1),(-1,1),MINT),
        ('BOX',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),('INNERGRID',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
    ]))
    story += [mt, Spacer(1, 2*mm)]

    story.append(_p("What this means in everyday language", styles["ClientH2"]))
    if target_m2 is not None:
        if report.get("maximum_far") is not None:
            row = far.get("matched_rule") or {}
            basis_area = row.get("far_calculation_area_m2") or site.get("site_area_m2")
            basis_label = "net FAR calculation area" if abs(float(basis_area) - float(site.get("site_area_m2") or 0)) > 0.01 else "plot area"
            provisional = far.get("rule_source_quality") == "secondary_copy_pending_official_validation"
            rule_note = " This is a provisional candidate transcribed from a secondary plan copy; the current operative rules require confirmation." if provisional else " This is a rule-based candidate, not an approval."
            body = (
                f"The selected rule profile identifies a maximum FAR candidate of <b>{target_far:.2f}</b>, "
                f"which gives a preliminary benchmark of <b>{target_m2:,.0f} m²</b> of floor area using the {basis_label} of <b>{float(basis_area):,.0f} m²</b>. "
                + rule_note + " Confirm the exact jurisdiction, official zone, road width and operative notification before relying on it. "
            )
        else:
            body = (
                f"For comparison only, the user-entered FAR assumption of <b>{target_far:.2f}</b> creates a working target of <b>{target_m2:,.0f} m²</b> "
                "of floor area (plot area × assumed FAR). This is not a confirmed legal allowance. "
            )
        over = [x for x in scenarios if x.get("scenario_headroom_m2") is not None and x["scenario_headroom_m2"] < -0.5]
        if len(over) == len(scenarios) and scenarios:
            closest = min(over, key=lambda x: abs(x["scenario_headroom_m2"]))
            body += (
                f"All {len(over)} concept options currently exceed that working target. {closest.get('name','The closest option')} is the closest, "
                f"at {abs(closest['scenario_headroom_m2']):,.0f} m² above it. The FAR rule must be confirmed before deciding whether to reduce floor area or test a different permitted scenario."
            )
        story.append(_p(body, styles["ClientBody"]))
    else:
        story.append(_p("The current report cannot create a reliable floor-area target yet. First confirm the applicable rule with the planning authority, then compare the design options against that confirmed figure.", styles["ClientBody"]))

    # Simple project facts that don't require interpretation.
    address = site.get("address") or "Not provided"
    if site.get("map_url"):
        address += f" | <link href=\"{_html(site['map_url'])}\" color=\"#585858\">Open map</link>"
    facts = [
        [_p("Site location", styles["ClientTable"]), _p(address, styles["ClientTable"])],
        [_p("Planning zone entered", styles["ClientTable"]), _p(_html(site.get("zone") or "Not verified") + " (must be checked against the official map)", styles["ClientTable"])],
        [_p("Building height options", styles["ClientTable"]), _p(", ".join(f"{s.get('height_m',0):g} m" for s in scenarios if s.get("height_m") is not None) or "Not entered", styles["ClientTable"])],
    ]
    ft = Table(facts, colWidths=[48*mm,225*mm])
    ft.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,-1),PALE),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    story += [Spacer(1, 2*mm), ft, Spacer(1, 2*mm)]

    story.append(_p("Recommended next steps", styles["ClientH2"]))
    steps = [
        "Confirm which planning authority and official land-use zone apply to this exact parcel.",
        "Get the authority to clarify the applicable FAR for the entered plot area and road width.",
        "Use an authenticated site survey to check the irregular boundary, road edge and any overlays before fixing a building footprint.",
    ]
    step_table = Table([[ _p(f"<b>{i+1}.</b>  {_html(item)}", styles["ClientBody"]) ] for i,item in enumerate(steps)], colWidths=[273*mm])
    step_table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),
        ('INNERGRID',(0,0),(-1,-1),0.3,colors.HexColor('#DDDDDD')),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),2),
    ]))
    story.append(step_table)
    story.append(PageBreak())

    # PAGE 2: Option comparison and each option's setback rule, in plain language.
    story.append(_p("COMPARE THE DESIGN OPTIONS", styles["ClientTitle"]))
    story.append(_p("The figures below are based on the footprints, floor counts and FAR scenarios entered by the project team. They are for comparison, not a statement of approved development rights.", styles["ClientSubtitle"]))
    if target_m2 is not None:
        if report.get("maximum_far") is None:
            source_wording = "manual comparison assumption"
        elif far.get("rule_source_quality") == "secondary_copy_pending_official_validation":
            source_wording = "provisional FAR table candidate from secondary source"
        else:
            source_wording = "rule-derived FAR candidate"
        story.append(_p(f"Comparison benchmark: <b>{target_m2:,.0f} m²</b> of floor area (FAR {target_far:.2f}; {source_wording}). Confirm the rule before using this figure as a project limit.", styles["ClientBody"]))

    headers = ["Option", "Height / floors", "Ground footprint", "Approx. floor area*", "Compared with working target", "Preliminary setback distances"]
    rows = [[_p(h, styles["ClientTableHead"]) for h in headers]]
    for opt in scenarios:
        h = opt.get("height_m")
        f = opt.get("floors")
        height_floors = (f"{h:.0f} m / {f} floors" if h is not None and f is not None else f"{_fmt(h,' m')} / {_fmt(f,' floors')}")
        footprint = f"{opt['footprint_m2']:,.0f} m²" if opt.get("footprint_m2") is not None else "Not provided"
        gross = f"{opt['gross_concept_area_m2']:,.0f} m²" if opt.get("gross_concept_area_m2") is not None else "Not calculated"
        setback = _option_setback_plain(opt)
        rows.append([
            _p(_html(opt.get("name","Option")), styles["ClientTable"]),
            _p(_html(height_floors), styles["ClientTable"]),
            _p(footprint, styles["ClientTable"]),
            _p(gross, styles["ClientTable"]),
            _p(_html(_option_difference_plain(opt, target_m2)), styles["ClientTable"]),
            _p(_html(setback), styles["ClientTable"]),
        ])
    tbl = Table(rows, colWidths=[26*mm,34*mm,35*mm,38*mm,54*mm,86*mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
    ]))
    story += [tbl, Spacer(1, 3*mm)]

    story.append(_p("How to read this table", styles["ClientH2"]))
    notes = [
        "<b>Ground footprint</b> is the area covered by the building at ground level.",
        "<b>Approx. floor area</b> is footprint × floor count. It assumes similar floor area on each level; it does not model exclusions, terraces, service areas or changes to individual floors.",
        "<b>FAR ratio basis</b> is shown where the selected source table uses a configured net calculation area after a specified reservation/deduction. The area figure above remains the gross concept estimate (footprint × floors); the FAR ratio denominator follows the configured rule profile and needs confirmation.",
        "<b>Setbacks</b> are open spaces between the building and the plot boundary. The distances shown are rule-profile calculations only. Because this plot is irregular, the actual boundary must be surveyed and the distances applied to its real geometry.",
    ]
    note_data = [[_p("• " + n, styles["ClientBody"])] for n in notes]
    note_tbl = Table(note_data, colWidths=[273*mm])
    note_tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),MINT),('BOX',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),
        ('INNERGRID',(0,0),(-1,-1),0.3,colors.HexColor('#DDDDDD')),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),2),
    ]))
    story += [note_tbl, Spacer(1, 2*mm)]
    # Clear, scenario-specific text for clients.
    story.append(_p("Setback rule basis used for each option", styles["ClientH2"]))
    basis_rows = [[_p("Option",styles["ClientTableHead"]), _p("Basis used in this study",styles["ClientTableHead"]), _p("What still needs checking",styles["ClientTableHead"])]]
    for opt in scenarios:
        sb = opt.get("setback_result") or {}
        basis = _option_setback_basis_plain(opt)
        if sb.get("all_round_m") is not None:
            distances = f"{sb['all_round_m']:.2f} m on all sides"
        elif all(sb.get(k) is not None for k in ("front_m","rear_m","left_m","right_m")):
            distances = f"Front {sb['front_m']:.2f} m; rear {sb['rear_m']:.2f} m; side {sb['left_m']:.2f}/{sb['right_m']:.2f} m"
        else:
            distances = "No result"
        basement = opt.get("basement_setback_result") or {}
        if basement.get("status") == "no_basement":
            basement_text = "Basement: not proposed"
        elif basement.get("all_round_m") is not None:
            basement_text = f"Basement: {basement['all_round_m']:.2f} m all sides"
        elif all(basement.get(k) is not None for k in ("front_m", "rear_m", "left_m", "right_m")):
            basement_text = f"Basement: front {basement['front_m']:.2f}; rear {basement['rear_m']:.2f}; sides {basement['left_m']:.2f}/{basement['right_m']:.2f} m"
        else:
            basement_text = "Basement setback: not determined"
        basis_rows.append([
            _p(_html(opt.get("name","Option")), styles["ClientTable"]),
            _p(f"<b>Building:</b> {_html(basis)}: {_html(distances)}<br/><b>Basement:</b> {_html(basement_text)}", styles["ClientTable"]),
            _p("Confirm height definition, stilt condition, current applicable table, road-facing edge and surveyed boundary.", styles["ClientTable"]),
        ])
    bt = Table(basis_rows, colWidths=[30*mm,125*mm,118*mm], repeatRows=1)
    bt.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),TEAL),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story.append(bt)
    story.append(_p("*Approximate floor area is not the final FAR-counted area. Applicable exclusions and authority-approved calculations may change the result.", styles["ClientSmall"]))
    story.append(PageBreak())

    # Optional boundary geometry page. This is inserted only when a validated boundary was imported.
    boundary = report.get("boundary_analysis")
    if boundary and boundary.get("geometry"):
        try:
            from shapely.geometry import shape as shapely_shape
            from .boundary import boundary_preview_png
            parcel = shapely_shape(boundary["geometry"])
            env_map = {x.get("name", "Option"): x.get("envelope", {}) for x in boundary.get("options", [])}
            png = boundary_preview_png(parcel, env_map, figsize=(6, 8), dpi=160)
            story.append(_p("IMPORTED SITE BOUNDARY & SETBACK ENVELOPES", styles["ClientTitle"]))
            story.append(_p("The drawing shows the imported parcel and the preliminary space remaining after the selected setbacks. It is a geometry aid, not a final building layout.", styles["ClientSubtitle"]))
            image = Image(BytesIO(png), width=105*mm, height=138*mm, kind="proportional")
            geom_rows = [
                [_p("Boundary metric", styles["ClientTableHead"]), _p("Calculated value", styles["ClientTableHead"])],
                [_p("Area from imported outline", styles["ClientTable"]), _p(f"{boundary.get('area_m2',0):,.2f} m²", styles["ClientTable"])],
                [_p("Boundary perimeter", styles["ClientTable"]), _p(f"{boundary.get('perimeter_m',0):,.2f} m", styles["ClientTable"])],
                [_p("Unique vertices", styles["ClientTable"]), _p(str(boundary.get("vertex_count", "-")), styles["ClientTable"])],
                [_p("Area difference vs input", styles["ClientTable"]), _p((f"{boundary.get('area_difference_from_input_pct'):.2f}%" if boundary.get("area_difference_from_input_pct") is not None else "Not compared"), styles["ClientTable"])],
            ]
            gt = Table(geom_rows, colWidths=[77*mm,70*mm], repeatRows=1)
            gt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),TEAL),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
            option_rows = [[_p("Option", styles["ClientTableHead"]), _p("Envelope area", styles["ClientTableHead"]), _p("Status", styles["ClientTableHead"])]]
            for item in boundary.get("options", []):
                env = item.get("envelope", {})
                area_label = f"{env.get('area_m2',0):,.2f} m²" if env.get("area_m2") is not None else "—"
                status_label = "Calculated — preliminary" if env.get("status") == "calculated_preliminary" else _status_text(env.get("status"))
                option_rows.append([_p(_html(item.get("name")), styles["ClientTable"]), _p(area_label, styles["ClientTable"]), _p(status_label, styles["ClientTableSmall"])])
            opt_tbl = Table(option_rows, colWidths=[39*mm,45*mm,63*mm], repeatRows=1)
            opt_tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#DDDDDD')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
            note = _p(_html(boundary.get("limitation", "Validate this geometry against the authenticated survey and current rules.")), styles["ClientSmall"])
            right_content = Table([[gt], [Spacer(1, 3*mm)], [_p("PRELIMINARY ENVELOPE AREAS", styles["ClientH3"])], [opt_tbl], [Spacer(1, 3*mm)], [note]], colWidths=[150*mm])
            right_content.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1)]))
            two_col = Table([[image, right_content]], colWidths=[112*mm, 161*mm])
            two_col.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
            story.append(two_col)
            story.append(PageBreak())
        except Exception:
            story.append(_p("Boundary geometry was imported, but the preview could not be embedded in this export. Inspect the boundary analysis in the SiteIQ application.", styles["ClientBody"]))
            story.append(PageBreak())

    # PAGE 3: Things to resolve, with straightforward language + glossary.
    story.append(_p("WHAT NEEDS TO BE CHECKED NEXT", styles["ClientTitle"]))
    story.append(_p("These are the decisions and documents needed before the options can be treated as reliable design feasibility.", styles["ClientSubtitle"]))
    check_explanations = {
        "Planning jurisdiction and boundary": ("Which authority approves this exact site?", "Confirm the parcel boundary, corporation/planning authority and sanctioning route from official records."),
        "Official land-use zone": ("Is apartment development permitted here, and under which zone?", "Check the official land-use map and property/site identifiers."),
        "Statutory FAR": ("How much floor area can legally be counted on this plot?", "Confirm the selected category, authority and operative clause; the configured table result is a candidate, not an approval."),
        "Survey geometry / boundary": ("Where exactly can the building sit?", "Obtain an authenticated survey for the irregular boundary and verify the stated site area."),
        "Lake, drain, HT line, road widening and other overlays": ("Are there restrictions affecting the buildable area?", "Check the official overlays for water bodies, drains, high-tension lines, flood-prone areas and road widening."),
        "Parking, accessibility, structure and services": ("Can the concept work safely and functionally?", "Check dwelling mix, parking, access, accessible routes, fire strategy, structure and services."),
        "Fire NOC trigger": ("What fire approvals and design provisions are required?", "Confirm the applicable threshold and current procedure with the fire authority and fire consultant."),
    }
    checks = report.get("checks", [])
    c_rows = [[_p("Check", styles["ClientTableHead"]), _p("Why it matters", styles["ClientTableHead"]), _p("Next action", styles["ClientTableHead"]), _p("Status", styles["ClientTableHead"])]]
    for ch in checks:
        why, action = check_explanations.get(ch.get("item"), (ch.get("note", "Confirm before proceeding."), "Review with the project team and relevant authority."))
        status = ch.get("status", "pending")
        if status in ("pending_confirmation", "no_matching_table_row", "applicability_needs_confirmation", "below_configured_high_rise_threshold"):
            status_label = "To confirm"
        elif status == "pending_design":
            status_label = "Design review"
        elif status == "not_configured":
            status_label = "Not configured"
        else:
            status_label = _status_text(status)
        c_rows.append([_p(_html(ch.get("item")), styles["ClientTable"]), _p(_html(why), styles["ClientTable"]), _p(_html(action), styles["ClientTable"]), _p(_html(status_label), styles["ClientTable"])])
    ct = Table(c_rows, colWidths=[49*mm,72*mm,115*mm,37*mm], repeatRows=1)
    ct.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story += [ct, Spacer(1, 4*mm), _p("A few terms in simple language", styles["ClientH2"])]
    glossary = [
        ("FAR", "A ratio used to limit the floor area counted under the regulations compared with the plot area."),
        ("Setback", "The open space required between the building and the plot boundary."),
        ("Footprint", "The area the building covers at ground level."),
        ("Working FAR target", "A comparison assumption only. It is not a confirmed permission until the applicable rule is verified."),
    ]
    gl_data = [[_p(f"<b>{_html(term)}</b>", styles["ClientTable"]), _p(_html(defn), styles["ClientTable"])] for term,defn in glossary]
    gl = Table(gl_data, colWidths=[45*mm,228*mm])
    gl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,-1),MINT),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    story.append(gl)
    site = report["site"]
    if site.get("implied_rectangular_area_m2") is not None and site.get("dimension_difference_pct") is not None:
        story.append(Spacer(1, 3*mm))
        story.append(_p(
            f"<b>Survey note:</b> the entered frontage × depth equals {_fmt(site.get('implied_rectangular_area_m2'),' m²')}, compared with the stated plot area of {_fmt(site.get('site_area_m2'),' m²')}. "
            f"The difference is {_fmt(site.get('dimension_difference_pct'),'%')}. Because the site is irregular, this is only a consistency check; the authenticated survey area and boundary should be used for design.", styles["ClientBody"]))
    story.append(PageBreak())

    # PAGE 4: Traceability appendix for architects and reviewers.
    story.append(_p("TECHNICAL REFERENCES & ASSUMPTIONS", styles["ClientTitle"]))
    story.append(_p("This appendix keeps the calculation trail visible without making the client summary difficult to read.", styles["ClientSubtitle"]))
    story.append(_p("Rule references used by this report", styles["ClientH2"]))
    src_rows = [[_p("Rule / topic", styles["ClientTableHead"]), _p("Document and exact reference", styles["ClientTableHead"]), _p("Status / link", styles["ClientTableHead"])]]
    for src in report.get("sources", []):
        title = _html(src.get("title", ""))
        clause = _html(src.get("clause", ""))
        docref = _html(src.get("document", ""))
        if src.get("document_page"):
            docref += "<br/>" + _html(src.get("document_page"))
        if src.get("notification"):
            docref = _html(src.get("notification")) + "<br/>" + docref
        url = src.get("url") or ""
        link = f"<link href=\"{_html(url)}\" color=\"#585858\">Open source / authority page</link>" if url else "No link configured"
        status = _html(src.get("status", ""))
        src_rows.append([
            _p(title + (f"<br/><font color='#656565'>{clause}</font>" if clause else ""), styles["ClientTableSmall"]),
            _p(docref, styles["ClientTableSmall"]),
            _p((status + "<br/>" if status else "") + link, styles["ClientTableSmall"]),
        ])
    st = Table(src_rows, colWidths=[101*mm,78*mm,94*mm], repeatRows=1)
    st.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),TEAL),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
        ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
    ]))
    story.append(st)
    premium = far.get("premium_far")
    if premium:
        story += [Spacer(1, 3*mm), _p("Optional additional FAR scenario — not included in the base benchmark", styles["ClientH2"])]
        prem_src = premium.get("source") or {}
        prem_text = _html(premium.get("message", "Optional additional FAR scenario; verify current eligibility and charges."))
        prem_text += f"<br/><b>Status:</b> {_html(str(premium.get('status', 'not verified')).replace('_',' '))}"
        if premium.get("potential_total_far_candidate") is not None:
            prem_text += f"<br/><b>Illustrative total FAR ceiling:</b> {float(premium['potential_total_far_candidate']):.2f}"
            prem_text += f"<br/><b>Illustrative total floor area:</b> {float(premium.get('potential_total_floor_area_candidate_m2',0)):,.0f} m²"
        if prem_src.get("url"):
            prem_text += f'<br/><link href="{_html(prem_src.get("url"))}" color="#585858">Open source reference</link>'
        story.append(_p(prem_text, styles["ClientBody"]))
    location_id = report.get("location_identification")
    if location_id:
        story += [Spacer(1, 3*mm), _p("Location auto-identification record", styles["ClientH2"])]
        ident_rows = [[_p("Field", styles["ClientTableHead"]), _p("Result", styles["ClientTableHead"]), _p("Status / provenance", styles["ClientTableHead"])]]
        coords = location_id.get("coordinates", {})
        # Compact status text so the report's closing note stays on the same appendix page.
        def _brief(value, limit=105):
            value = " ".join(str(value or "").split())
            if len(value) <= limit:
                return value
            first_sentence = value.split(".")[0].strip()
            if first_sentence and len(first_sentence) <= limit:
                return first_sentence + "."
            return value[:limit-1].rsplit(" ", 1)[0] + "…"
        ident_rows.append([_p("Coordinates", styles["ClientTableSmall"]), _p(_html(coords.get("text", "Not resolved")), styles["ClientTableSmall"]), _p(_html(str(coords.get("method", "")).replace("_", " ")), styles["ClientTableSmall"])])
        auth = location_id.get("authority", {})
        auth_status = _html(_status_text(auth.get("status", "")))
        auth_reason = _html(_brief(auth.get("reason", "")))
        if auth.get("source_url"):
            auth_reason += f'<br/><link href="{_html(auth.get("source_url"))}" color="#585858">Source</link>'
        ident_rows.append([_p("Authority / rules profile", styles["ClientTableSmall"]), _p(_html(auth.get("label") or auth.get("key") or "Not identified"), styles["ClientTableSmall"]), _p(auth_status + ("<br/>" + auth_reason if auth_reason else ""), styles["ClientTableSmall"])])
        zone = location_id.get("zone", {})
        zone_status = _html(_status_text(zone.get("status", "")))
        zone_reason = _html(_brief(zone.get("reason", "")))
        if zone.get("source_url"):
            zone_reason += f'<br/><link href="{_html(zone.get("source_url"))}" color="#585858">Source</link>'
        ident_rows.append([_p("Land-use zone", styles["ClientTableSmall"]), _p(_html(zone.get("value", "Not verified")), styles["ClientTableSmall"]), _p(zone_status + ("<br/>" + zone_reason if zone_reason else ""), styles["ClientTableSmall"])])
        route = location_id.get("approval_route", {})
        route_status = _html(_status_text(route.get("status", "")))
        route_reason = _html(_brief(route.get("reason", "")))
        ident_rows.append([_p("Approval route", styles["ClientTableSmall"]), _p(_html(route.get("suggested_value", "Not confirmed")), styles["ClientTableSmall"]), _p(route_status + ("<br/>" + route_reason if route_reason else ""), styles["ClientTableSmall"])])
        it = Table(ident_rows, colWidths=[43*mm,60*mm,170*mm], repeatRows=1)
        it.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),NAVY),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
            ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
        ]))
        story.append(it)
        story.append(_p("Indicative only: geocoder results do not establish legal jurisdiction or zoning. A confirmed status requires a current official-source polygon match.", styles["ClientSmall"]))
        public_sources = location_id.get("public_sources") or []
        if public_sources:
            story += [Spacer(1, 2*mm), _p("Official map and planning-source links", styles["ClientH2"])]
            ps_rows = [[_p("Source", styles["ClientTableHead"]), _p("What it can establish", styles["ClientTableHead"]), _p("Link / status", styles["ClientTableHead"])]]
            for source in public_sources[:5]:
                title = _html(source.get("title", "Official source"))
                note = _html(_brief(source.get("note", "Reference page only; confirm applicability."), 150))
                url = source.get("url") or ""
                link = f'<link href="{_html(url)}" color="#585858">Open official page</link>' if url else "No link configured"
                ps_rows.append([
                    _p(title, styles["ClientTableSmall"]),
                    _p(note, styles["ClientTableSmall"]),
                    _p(link + "<br/><font color='#656565'>Reference page; not a verified geometry match</font>", styles["ClientTableSmall"]),
                ])
            pst = Table(ps_rows, colWidths=[62*mm, 155*mm, 54*mm], repeatRows=1)
            pst.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),TEAL),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DDDDDD')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,PALE]),
                ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
            ]))
            story.append(pst)
    story += [Spacer(1, 1*mm)]
    final_box = Table([[_p("<b>Important:</b> This is a preliminary feasibility aid, not a sanction report or confirmation of development rights. Verify operative regulations and authority interpretation before commercial commitments or submission.", styles["Callout"])]], colWidths=[273*mm])
    final_box.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),0.5,colors.HexColor('#DDDDDD')),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
    ]))
    story.append(final_box)

    story += _compliance_story(report, styles)

    def footer(canvas, doc_):
        canvas.saveState()
        w, h = landscape(A4)
        canvas.setStrokeColor(colors.HexColor('#DDDDDD'))
        canvas.line(12*mm, 9.5*mm, w-12*mm, 9.5*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(12*mm, 5.5*mm, f"SITEIQ v{__version__} | Rule status: {report.get('application', {}).get('source_status', 'not recorded')} | Preliminary feasibility; confirm operative rules before sanction use")
        canvas.drawRightString(w-12*mm, 5.5*mm, f"Page {doc_.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _hex(rgb):
    return RGBColor(*rgb)


def _add_text(slide, x, y, w, h, text, size=12, color=(46,46,46), bold=False, font="Aptos", align=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.08); tf.margin_right = Inches(0.08); tf.margin_top = Inches(0.04); tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]
    p.text = str(text)
    p.font.name = font
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = _hex(color)
    if align is not None:
        p.alignment = align
    return box


def _add_rect(slide, x, y, w, h, fill, line=None, radius=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = _hex(fill)
    shape.line.color.rgb = _hex(line or fill)
    shape.shadow.inherit = False
    # Some viewers ignore the empty effect list and read the theme effect from the shape style.
    for effect_ref in shape._element.xpath(".//a:effectRef"):
        effect_ref.set("idx", "0")
    if radius:
        shape.adjustments[0] = 0.04
    return shape


def _set_cell(cell, text, font_size=9, color=(46,46,46), bold=False, fill=None):
    cell.text = str(text)
    cell.margin_left = Inches(0.06); cell.margin_right = Inches(0.06); cell.margin_top = Inches(0.035); cell.margin_bottom = Inches(0.035)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    for p in cell.text_frame.paragraphs:
        p.font.name = "Aptos"
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.color.rgb = _hex(color)
    # Always set a fill: otherwise PowerPoint applies its blue default table banding.
    cell.fill.solid(); cell.fill.fore_color.rgb = _hex(fill or (255, 255, 255))


def build_pptx_report(report: dict) -> bytes:
    """Generate a client-friendly editable slide report using plain language."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    site = report["site"]
    scenarios = report.get("scenarios", [])
    target_m2, target_far = _scenario_target(report)
    dark=(46,46,46); teal=(88,88,88); mint=(238,238,238); orange=(142,142,142); grey=(101,101,101); pale=(245,245,245); white=(255,255,255); red=(99,99,99); line=(221,221,221)
    far = report.get("far", {})

    # Slide 1: executive summary.
    s = prs.slides.add_slide(blank)
    _add_rect(s,0,0,13.333,7.5,dark)
    _add_rect(s,0,0,0.16,7.5,orange)
    _add_text(s,0.65,0.55,11.8,0.35,"SITEIQ  /  SITE FEASIBILITY",13,(203,203,203),True)
    _add_text(s,0.65,1.05,11.8,0.65,report.get("project","Site feasibility"),29,white,True)
    _add_text(s,0.65,1.75,11.8,0.36,"A plain-English early feasibility review  |  " + report.get("application",{}).get("assessment_date",""),11,(212,212,212))
    cards=[(0.65,"PLOT AREA",f"{site['site_area_m2']:,.0f} m²"),(3.65,"ROAD WIDTH",f"{site['road_width_m']:.2f} m"),(6.65,"PROJECT",site.get("proposed_use","Not supplied")),(9.65,"SITE SHAPE",site.get("shape_type","Unknown"))]
    for x,label,value in cards:
        _add_rect(s,x,2.5,2.72,1.12,(64,64,64),line=(87,87,87),radius=True)
        _add_text(s,x+0.12,2.62,2.48,0.22,label,8.5,(200,200,200),True)
        _add_text(s,x+0.12,2.94,2.48,0.52,value,13.5,white,True)
    if far.get("status") != "candidate_match_requires_verification":
        status = "FAR RULE NEEDS CONFIRMATION"
    elif far.get("rule_source_quality") == "secondary_copy_pending_official_validation":
        status = "PROVISIONAL TABLE CANDIDATE — VERIFY SOURCE"
    else:
        status = "FAR CANDIDATE FOUND — VERIFY BEFORE DESIGN FREEZE"
    _add_rect(s,0.65,4.0,12.0,0.55,(245,245,245),line=(189,189,189),radius=True)
    _add_text(s,0.85,4.12,11.6,0.25,status,11,(79,79,79),True)
    if target_m2 is not None:
        overs = [o for o in scenarios if o.get("scenario_headroom_m2") is not None and o["scenario_headroom_m2"] < 0]
        if report.get("maximum_far") is None:
            benchmark_label = "manual comparison assumption"
        elif far.get("rule_source_quality") == "secondary_copy_pending_official_validation":
            benchmark_label = "provisional table candidate (secondary source)"
        else:
            benchmark_label = "configured rule candidate"
        far_area = far.get("far_calculation_area_m2")
        gross_site_area = site.get("site_area_m2")
        if far_area is not None and gross_site_area is not None and abs(float(far_area)-float(gross_site_area)) > 0.01:
            basis_note = f" The calculation uses a net FAR area of {float(far_area):,.0f} m² after the configured deduction, rather than the gross site area."
        else:
            basis_note = ""
        summary = f"FAR {target_far:.2f} gives a comparison benchmark of {target_m2:,.0f} m² ({benchmark_label}).{basis_note} {len(overs)} entered option(s) exceed that figure. Verify statutory entitlement before choosing a design."
    else:
        summary = "The current rule profile cannot establish a reliable maximum FAR. Confirm the applicable authority, official zone and current table before choosing a design option."
    _add_text(s,0.78,4.9,11.75,0.92,summary,16,white,False)
    _add_text(s,0.7,6.25,11.8,0.55,"Purpose: support an early design discussion. This report is not a sanction, legal opinion or confirmation of development rights.",10,(218,218,218))

    # Slide 2: findings explained.
    s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,pale)
    _add_text(s,0.45,0.35,12.3,0.45,"01  /  WHAT WE KNOW SO FAR",18,dark,True)
    _add_rect(s,0.45,1.05,6.0,5.95,white,line=line,radius=True)
    _add_text(s,0.72,1.3,5.4,0.35,"SITE SNAPSHOT",11,teal,True)
    facts=[
        ("Location",site.get("address","Not supplied")),
        ("Authority profile",site.get("authority","Not confirmed")),
        ("Rule category",site.get("land_use_category",site.get("zone","Not selected"))),
        ("Official map zone",site.get("official_zone","Not verified")+" (verify on official map)"),
        ("Approx. dimensions",f"{_fmt(site.get('frontage_m'),' m')} × {_fmt(site.get('depth_m'),' m')}"),
        ("Plot shape",site.get("shape_type","Unknown")),
        ("Basement",site.get("basement","Undecided")),
    ]
    y=1.85
    for label,value in facts:
        _add_text(s,0.72,y,1.62,0.27,label,8.5,grey,True)
        _add_text(s,2.32,y,3.8,0.42,str(value),9,dark)
        y+=0.72
    _add_rect(s,6.75,1.05,6.1,5.95,mint,line=line,radius=True)
    _add_text(s,7.0,1.3,5.55,0.35,"WHY THE FAR IS NOT CONFIRMED",11,teal,True)
    _add_text(s,7.0,1.83,5.55,1.12,_plain_far_summary(report),11,dark)
    _add_text(s,7.0,3.15,5.55,0.30,"WHAT DOES FAR MEAN?",10,teal,True)
    _add_text(s,7.0,3.48,5.55,0.8,"FAR is the rule that limits the amount of floor area counted for a building relative to the plot area.",10,dark)
    if target_m2 is not None:
        _add_rect(s,7.0,4.6,5.55,1.23,white,line=line,radius=True)
        _add_text(s,7.22,4.74,5.1,0.25,"WORKING COMPARISON ONLY",8,grey,True)
        _add_text(s,7.22,5.08,5.1,0.47,f"{target_m2:,.0f} m² total floor area",17,dark,True)
        _add_text(s,7.0,6.05,5.55,0.55,"The assumed FAR is for option-testing; it is not the confirmed statutory limit.",9,grey)

    # Slide 3: options in accessible terminology.
    s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,white)
    _add_text(s,0.45,0.35,12.3,0.45,"02  /  COMPARE THE OPTIONS",18,dark,True)
    _add_text(s,0.45,0.84,12.2,0.36,"Approximate floor area assumes the entered footprint is repeated on each floor.",9,grey)
    headers=["Option","Height / floors","Footprint","Approx. total floor area","Above working target","Setback distances"]
    rows=[headers]
    for opt in scenarios:
        height=opt.get("height_m"); floors=opt.get("floors")
        hf=f"{height:.0f} m / {floors} floors" if height is not None and floors is not None else f"{_fmt(height,' m')} / {_fmt(floors)} floors"
        fp=f"{opt['footprint_m2']:,.0f} m²" if opt.get("footprint_m2") is not None else "Not provided"
        gross=f"{opt['gross_concept_area_m2']:,.0f} m²" if opt.get("gross_concept_area_m2") is not None else "Not calculated"
        rows.append([opt.get("name","Option"),hf,fp,gross,_option_difference_plain(opt,target_m2),_option_setback_plain(opt)])
    if len(rows)==1: rows.append(["No options entered","-","-","-","-","-"])
    table=s.shapes.add_table(len(rows),6, Inches(0.45), Inches(1.42), Inches(12.42), Inches(2.65)).table
    widths=[1.2,1.45,1.42,1.72,2.05,4.58]
    for j,w in enumerate(widths): table.columns[j].width=Inches(w)
    for i,row in enumerate(rows):
        for j,val in enumerate(row): _set_cell(table.cell(i,j),val,8 if i else 7.5,white if i==0 else dark,i==0,teal if i==0 else (mint if i%2 else white))
    _add_rect(s,0.45,4.48,12.42,1.95,pale,line=line,radius=True)
    _add_text(s,0.72,4.7,11.8,0.28,"HOW TO READ THIS",10,teal,True)
    notes="Footprint = area covered by the building at ground level. Approx. total floor area = footprint × floor count. Setbacks are the clear spaces between the building and plot boundary. The values are preliminary rule-profile results; an irregular plot needs a survey-based boundary check."
    _add_text(s,0.72,5.08,11.75,1.03,notes,10,dark)
    _add_text(s,0.55,6.82,12.15,0.25,"Important: floor-area exclusions and floor-by-floor changes have not been modelled; confirm the applicable FAR before treating any option as compliant.",8.3,grey)

    # Optional boundary geometry slide, only when a validated boundary was imported.
    boundary = report.get("boundary_analysis")
    if boundary and boundary.get("geometry"):
        try:
            from shapely.geometry import shape as shapely_shape
            from .boundary import boundary_preview_png
            parcel = shapely_shape(boundary["geometry"])
            env_map = {x.get("name", "Option"): x.get("envelope", {}) for x in boundary.get("options", [])}
            png_bytes = boundary_preview_png(parcel, env_map, figsize=(10, 6.5), dpi=180)
            s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,white)
            _add_text(s,0.45,0.35,12.3,0.45,"03  /  SITE BOUNDARY & SETBACK ENVELOPES",17,dark,True)
            _add_text(s,0.45,0.84,12.2,0.32,"Imported geometry is scaled and checked; the inner lines are preliminary setback envelopes.",9,grey)
            s.shapes.add_picture(BytesIO(png_bytes), Inches(0.45), Inches(1.35), height=Inches(5.35))
            _add_rect(s,4.75,1.32,8.12,5.55,mint,line=line,radius=True)
            _add_text(s,5.03,1.58,7.5,0.32,"BOUNDARY CHECK",11,teal,True)
            metrics = [
                ("Imported file", boundary.get("source_file", "Not supplied")),
                ("Calculated area", f"{boundary.get('area_m2',0):,.2f} m²"),
                ("Perimeter", f"{boundary.get('perimeter_m',0):,.2f} m"),
                ("Vertices", str(boundary.get("vertex_count", "-"))),
                ("Difference from area input", f"{boundary.get('area_difference_from_input_pct'):.2f}%" if boundary.get("area_difference_from_input_pct") is not None else "Not compared"),
            ]
            y=2.05
            for label,value in metrics:
                _add_text(s,5.03,y,2.55,0.26,label,8.4,grey,True)
                _add_text(s,7.55,y,5.0,0.44,str(value),9.4,dark,True)
                y+=0.66
            _add_text(s,5.03,5.45,7.5,0.25,"IMPORTANT",9,orange,True)
            _add_text(s,5.03,5.78,7.45,0.83,"Check the outline against the authenticated survey. Variable setbacks near complex concave corners are an approximation and require CAD review. A setback envelope is not the final building footprint.",8.8,dark)
            _add_text(s,0.55,7.08,12.15,0.18,f"SITEIQ v{__version__} | Boundary geometry is preliminary; confirm dimensions, source units and operative regulations",7.1,grey)
        except Exception:
            pass

    # Slide 4: actions and simple glossary.
    s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,pale)
    _add_text(s,0.45,0.35,12.3,0.45,("04  /  WHAT NEEDS TO HAPPEN NEXT" if report.get("boundary_analysis") else "03  /  WHAT NEEDS TO HAPPEN NEXT"),18,dark,True)
    _add_rect(s,0.45,1.05,7.15,5.95,white,line=line,radius=True)
    _add_text(s,0.72,1.3,6.6,0.35,"BEFORE THE CONCEPT IS FROZEN",11,teal,True)
    next_steps=[
        "Confirm which planning authority and land-use zone apply to this exact parcel.",
        "Ask the authority to clarify the applicable FAR for the plot area and road width.",
        "Use an authenticated survey to reconcile site area, boundary and road edge.",
        "Check lake/drain, HT-line, flood-prone and road-widening overlays.",
        "Confirm parking, accessibility, structure, services and fire requirements against the chosen design.",
    ]
    y=1.85
    for i,item in enumerate(next_steps,1):
        _add_rect(s,0.75,y,0.38,0.38,teal,radius=True)
        _add_text(s,0.79,y+0.045,0.3,0.24,str(i),9,white,True,align=PP_ALIGN.CENTER)
        _add_text(s,1.25,y-0.02,5.98,0.57,item,9.5,dark)
        y+=0.94
    _add_rect(s,7.9,1.05,4.95,5.95,mint,line=line,radius=True)
    _add_text(s,8.18,1.3,4.42,0.35,"QUICK GLOSSARY",11,teal,True)
    glossary=[
        ("FAR","A ratio that limits the floor area counted by the rules."),
        ("Setback","Open space required between building and plot boundary."),
        ("Footprint","Area covered by the building at ground level."),
        ("Working target","A comparison assumption, not a permission."),
    ]
    y=1.92
    for term,desc in glossary:
        _add_text(s,8.18,y,4.25,0.28,term,9.5,dark,True)
        _add_text(s,8.18,y+0.31,4.25,0.62,desc,8.8,dark)
        y+=1.06

    # Slide 5: technical appendix/source record.
    s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,white)
    _add_text(s,0.45,0.35,12.3,0.45,"TECHNICAL APPENDIX  /  SOURCES & ASSUMPTIONS",17,dark,True)
    _add_text(s,0.45,0.84,12.2,0.35,"Use the cited clause and source document to trace each rule. Current applicability must be confirmed for the exact site.",9,grey)
    srcs=report.get("sources",[])
    headers=["Rule / document","Clause / page","Source status"]
    rows=[headers]
    for src in srcs[:4]:
        title=src.get("title","")
        if src.get("notification"):
            title=f"{src.get('notification')}\n{title}"
        ref=(src.get("clause","") + ("\n"+src.get("document_page","") if src.get("document_page") else ""))
        status=src.get("status","")
        rows.append([title,ref,status])
    if len(rows)==1: rows.append(["No configured rule sources","-","Check selected authority profile"])
    table=s.shapes.add_table(len(rows),3, Inches(0.45), Inches(1.35), Inches(12.42), Inches(3.55)).table
    widths=[4.65,3.55,4.22]
    for j,w in enumerate(widths): table.columns[j].width=Inches(w)
    for i,row in enumerate(rows):
        for j,val in enumerate(row): _set_cell(table.cell(i,j),val,8.2 if i else 8,white if i==0 else dark,i==0,teal if i==0 else (mint if i%2 else white))
    # Hyperlinks in source titles where URLs exist.
    for i,src in enumerate(srcs[:4],1):
        if src.get("url"):
            cell=table.cell(i,0)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.hyperlink.address=src["url"]
    _add_rect(s,0.45,5.2,12.42,1.55,pale,line=line,radius=True)
    _add_text(s,0.72,5.4,11.8,0.28,"ASSUMPTIONS & LIMITS",10,teal,True)
    limit_lines=[
        (f"Rule lookup candidate FAR {report.get('maximum_far'):.2f}; derived benchmark {report.get('maximum_far_area_m2'):,.0f} m². Confirm zone and operative clause." if report.get("maximum_far") is not None else "No maximum FAR benchmark is established for these inputs; no FAR entitlement has been assumed."),
        "Option footprints and floor counts are feasibility inputs. Gross area does not model all statutory FAR exclusions or design constraints.",
        "Authority and zone matching require current official GeoJSON layers; geocoder-only results are provisional. Road width and all site overlays are not automatically certified.",
    ]
    location_id = report.get("location_identification")
    if location_id:
        auth_id = location_id.get("authority", {})
        zone_id = location_id.get("zone", {})
        route_id = location_id.get("approval_route", {})
        limit_lines.append(f"Location lookup: {location_id.get('coordinates', {}).get('text', 'not resolved')}; authority {auth_id.get('status', 'unknown')}; zone {zone_id.get('status', 'unknown')}; route {route_id.get('status', 'unknown')}.")
    _add_text(s,0.72,5.78,11.8,0.83,"\n".join("• "+x for x in limit_lines),8.6,dark)
    _add_text(s,0.55,7.08,12.15,0.18,f"SITEIQ v{__version__} | Preliminary feasibility only | Verify operative Gazette and authority interpretation before sanction use",7.1,grey)

    premium = far.get("premium_far")
    if premium:
        s=prs.slides.add_slide(blank); _add_rect(s,0,0,13.333,7.5,pale)
        _add_text(s,0.45,0.35,12.3,0.45,"OPTIONAL ADDITIONAL FAR SCENARIO",18,dark,True)
        _add_text(s,0.45,0.88,12.0,0.5,"Shown separately from the base FAR benchmark. This is an opportunity to investigate, not a development entitlement.",10,grey)
        _add_rect(s,0.55,1.55,12.2,1.05,mint,line=line,radius=True)
        _add_text(s,0.82,1.73,11.7,0.72,premium.get("message","Optional additional FAR scenario; source and eligibility must be verified."),12,dark)
        total_far=premium.get("potential_total_far_candidate")
        total_area=premium.get("potential_total_floor_area_candidate_m2")
        additional=premium.get("additional_far_candidate")
        metrics=[("STATUS",str(premium.get("status","unverified")).replace("_"," ").upper()),("BASE FAR",f"{premium.get('base_far',0):.2f}" if premium.get('base_far') is not None else "Not established"),("ADDITIONAL FAR SCENARIO",f"Up to {additional:.2f}" if additional is not None else "Not established"),("ILLUSTRATIVE TOTAL FAR",f"{total_far:.2f}" if total_far is not None else "Not calculated"),("ILLUSTRATIVE TOTAL FLOOR AREA",f"{total_area:,.0f} m²" if total_area is not None else "Not calculated")]
        x0=0.55; gap0=0.16; w0=(12.2-gap0*4)/5
        for i,(label,value) in enumerate(metrics):
            x=x0+i*(w0+gap0); _add_rect(s,x,3.0,w0,1.25,white,line=line,radius=True)
            _add_text(s,x+0.12,3.14,w0-0.24,0.38,label,7.7,teal,True)
            _add_text(s,x+0.12,3.62,w0-0.24,0.48,value,10.3,dark,True)
        src=premium.get("source") or {}
        src_note = str(src.get("title", "Source not configured")) + (" | " + str(src.get("url")) if src.get("url") else "")
        _add_text(s,0.68,4.68,11.9,0.4,"SOURCE / VERIFICATION",9,teal,True)
        _add_text(s,0.68,5.05,11.9,0.68,src_note,8.8,dark)
        _add_text(s,0.65,6.18,12.0,0.65,"Premium charges, TDR combination, site eligibility, exact operative Table 27 and any cap/exception are not calculated in this MVP. Confirm the final Gazette text and authority's interpretation.",9,grey)
        _add_text(s,0.55,7.08,12.15,0.18,f"SITEIQ v{__version__} | Optional FAR scenario excluded from base benchmark",7.1,grey)

    checks = _sorted_checks(report)
    if checks:
        open_items = [c for c in checks if c["status"] != "PASS"]
        s = prs.slides.add_slide(blank)
        _add_text(s,0.45,0.35,12.3,0.45,"COMPLIANCE REGISTER",18,dark,True)
        _add_text(s,0.45,0.84,12.2,0.36,_verdict_line(report) or "",10,grey)
        shown = open_items[:14]
        rows = [["STATUS","CHECK","OPTION","FINDING"]] + [[STATUS_LABELS.get(c["status"],c["status"]),c.get("title",""),c.get("option") or "All",str(c.get("message",""))[:150]] for c in shown]
        table = s.shapes.add_table(len(rows),4,Inches(0.45),Inches(1.3),Inches(12.42),Inches(5.3)).table
        for col,width in enumerate((1.25,2.5,1.2,7.47)):
            table.columns[col].width = Inches(width)
        for r,row in enumerate(rows):
            for col,value in enumerate(row):
                _set_cell(table.cell(r,col),value,8,(255,255,255) if r==0 else dark,r==0,dark if r==0 else None)
        if len(open_items) > len(shown):
            _add_text(s,0.45,6.95,12.2,0.3,f"{len(open_items)-len(shown)} more open items are listed in the PDF report and assessment JSON.",9,grey)
    out=BytesIO(); prs.save(out); return out.getvalue()

# ---------------------------------------------------------------------------
# One-page A3 comparison board. Kept as a separate export from the detailed
# client report so teams can share a concise, drawing-led option comparison.
# ---------------------------------------------------------------------------
def _basement_setback_plain(opt: dict) -> str:
    if int(opt.get("basement_levels", 0) or 0) <= 0:
        return "No basement selected"
    sb = opt.get("basement_setback_result") or {}
    all_round = sb.get("all_round_m")
    if all_round is not None:
        return f"{float(all_round):.2f} m all sides"
    vals = [sb.get(k) for k in ("front_m", "rear_m", "left_m", "right_m")]
    if all(v is not None for v in vals):
        return f"F {vals[0]:.2f} · R {vals[1]:.2f} · sides {vals[2]:.2f}/{vals[3]:.2f} m"
    return "Not determined / confirm rule"


def _option_delta(opt: dict, target_m2: float | None) -> tuple[str, float | None]:
    area = opt.get("gross_concept_area_m2")
    if area is None or target_m2 is None:
        return "Benchmark not established", None
    delta = float(area) - float(target_m2)
    if abs(delta) < 0.5:
        return "At benchmark", 0.0
    if delta > 0:
        return f"{delta:,.0f} m² above benchmark", delta
    return f"{abs(delta):,.0f} m² below benchmark", delta


def _geojson_polygon_lists(geom: dict | None) -> list[list[tuple[float, float]]]:
    """Return exterior coordinate lists for Polygon/MultiPolygon GeoJSON mappings."""
    if not geom or not isinstance(geom, dict):
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    out: list[list[tuple[float, float]]] = []
    try:
        if gtype == "Polygon":
            if coords and coords[0]:
                out.append([(float(x), float(y)) for x, y, *_ in coords[0]])
        elif gtype == "MultiPolygon":
            for poly in coords:
                if poly and poly[0]:
                    out.append([(float(x), float(y)) for x, y, *_ in poly[0]])
    except (TypeError, ValueError):
        return []
    return out


def _draw_geo_preview_pdf(c, x, y, w, h, boundary_geom: dict | None, envelope_geom: dict | None = None):
    """Small-to-medium vector preview in PDF coordinates; y is the lower edge."""
    parcel = _geojson_polygon_lists(boundary_geom)
    envs = _geojson_polygon_lists(envelope_geom)
    if not parcel:
        c.setStrokeColor(colors.HexColor('#C2C2C2'))
        c.setDash(3, 2)
        c.roundRect(x + 7, y + 7, w - 14, h - 14, 5, stroke=1, fill=0)
        c.setDash()
        c.setFillColor(GREY)
        c.setFont("Helvetica-Oblique", 7.2)
        c.drawCentredString(x + w / 2, y + h / 2, "Survey boundary not imported")
        return
    all_pts = [pt for poly in parcel + envs for pt in poly]
    minx = min(p[0] for p in all_pts); maxx = max(p[0] for p in all_pts)
    miny = min(p[1] for p in all_pts); maxy = max(p[1] for p in all_pts)
    dx = max(maxx - minx, 1e-6); dy = max(maxy - miny, 1e-6)
    scale = min((w - 18) / dx, (h - 14) / dy)
    ox = x + (w - dx * scale) / 2 - minx * scale
    oy = y + (h - dy * scale) / 2 - miny * scale
    for poly in parcel:
        path = c.beginPath()
        for i, (px, py) in enumerate(poly):
            (path.moveTo if i == 0 else path.lineTo)(ox + px * scale, oy + py * scale)
        path.close()
        c.setFillColor(colors.HexColor('#EEEEEE'))
        c.setStrokeColor(colors.HexColor('#2E2E2E'))
        c.setLineWidth(1.25)
        c.drawPath(path, stroke=1, fill=1)
    for poly in envs:
        path = c.beginPath()
        for i, (px, py) in enumerate(poly):
            (path.moveTo if i == 0 else path.lineTo)(ox + px * scale, oy + py * scale)
        path.close()
        c.setFillColor(colors.Color(0.1, 0.1, 0.1, alpha=0.12))
        c.setStrokeColor(TEAL)
        c.setLineWidth(1.5)
        c.drawPath(path, stroke=1, fill=1)


def build_a3_comparison_board_pdf(report: dict) -> bytes:
    """Generate an A3 landscape one-page comparison board with option-specific
    building and basement setbacks and an explicit maximum-FAR benchmark."""
    buf = BytesIO()
    page_w, page_h = landscape(A3)
    c = pdfcanvas.Canvas(buf, pagesize=(page_w, page_h), pageCompression=1)
    site = report.get("site", {})
    options = report.get("scenarios", [])[:4]
    target_m2, target_far = _scenario_target(report)
    far = report.get("far", {})
    boundary = report.get("boundary_analysis") or {}
    boundary_geom = boundary.get("geometry")
    margin = 9 * mm
    gap = 4 * mm
    dark = colors.HexColor('#2E2E2E')
    teal = colors.HexColor('#585858')
    mint = colors.HexColor('#EEEEEE')
    pale = colors.HexColor('#F5F5F5')
    line = colors.HexColor('#DDDDDD')
    orange = colors.HexColor('#8E8E8E')
    grey = colors.HexColor('#656565')
    red = colors.HexColor('#636363')
    white = colors.white

    c.setFillColor(colors.HexColor('#FBFBFB')); c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    c.setFillColor(dark); c.rect(0, page_h - 4 * mm, page_w, 4 * mm, stroke=0, fill=1)
    c.setFillColor(teal); c.setFont("Helvetica-Bold", 8.5); c.drawString(margin, page_h - 13 * mm, "SITEIQ  /  RESIDENTIAL FEASIBILITY")
    c.setFillColor(dark); c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, page_h - 24 * mm, str(report.get("project", "Site feasibility"))[:70])
    c.setFillColor(grey); c.setFont("Helvetica", 8.5)
    c.drawString(margin, page_h - 30 * mm, (_verdict_line(report) or "BUILDING ENVELOPE + FAR COMPARISON  ·  PRELIMINARY DESIGN STUDY — NOT SANCTION")[:150])
    c.setFillColor(dark); c.roundRect(page_w - margin - 55*mm, page_h - 28*mm, 55*mm, 12*mm, 4, stroke=0, fill=1)
    c.setFillColor(white); c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(page_w - margin - 27.5*mm, page_h - 21.5*mm, f"ASSESSMENT  {report.get('application', {}).get('assessment_date', '')}")

    # Summary strip: max FAR only if it comes from a configured rule lookup.
    strip_y = page_h - 47 * mm
    far_label = "PROVISIONAL FAR*" if far.get("rule_source_quality") == "secondary_copy_pending_official_validation" else "MAX FAR CANDIDATE"
    labels = [
        ("SITE AREA", f"{site.get('site_area_m2', 0):,.0f} m²"),
        ("ROAD WIDTH", f"{site.get('road_width_m', 0):.2f} m"),
        ("LAND-USE CATEGORY", str(site.get("land_use_category", site.get("zone", "Not selected"))),),
        (far_label, f"{target_far:.2f}" if target_far is not None else "Needs confirmation"),
        ("FAR AREA BENCHMARK", f"{target_m2:,.0f} m²" if target_m2 is not None else "Not established"),
    ]
    strip_w = page_w - margin * 2
    cell_w = strip_w / len(labels)
    c.setFillColor(mint); c.roundRect(margin, strip_y, strip_w, 14*mm, 4, stroke=0, fill=1)
    for i, (label, value) in enumerate(labels):
        x = margin + i * cell_w
        if i: c.setStrokeColor(line); c.setLineWidth(0.5); c.line(x, strip_y + 2*mm, x, strip_y + 12*mm)
        c.setFillColor(grey); c.setFont("Helvetica-Bold", 6.7); c.drawString(x + 3*mm, strip_y + 9.2*mm, label)
        c.setFillColor(dark); c.setFont("Helvetica-Bold", 11 if i in (2,2,2) else 9)
        c.drawString(x + 3*mm, strip_y + 3.6*mm, value[:32])

    # Option cards.
    card_top = strip_y - 5*mm
    card_h = 151*mm
    card_y = card_top - card_h
    n = max(1, len(options))
    card_w = (strip_w - gap * (n - 1)) / n
    color_cycle = [teal, colors.HexColor('#737373'), orange, colors.HexColor('#7B7B7B')]
    for i, opt in enumerate(options):
        x = margin + i * (card_w + gap)
        accent = color_cycle[i % len(color_cycle)]
        c.setFillColor(white); c.setStrokeColor(line); c.setLineWidth(0.7)
        c.roundRect(x, card_y, card_w, card_h, 5, stroke=1, fill=1)
        c.setFillColor(accent); c.roundRect(x, card_y + card_h - 11*mm, card_w, 11*mm, 5, stroke=0, fill=1)
        # Square off the lower edge of the header band.
        c.rect(x, card_y + card_h - 11*mm, card_w, 4*mm, stroke=0, fill=1)
        c.setFillColor(white); c.setFont("Helvetica-Bold", 10.2)
        c.drawString(x + 3*mm, card_y + card_h - 6.8*mm, str(opt.get("name", f"Option {i+1}"))[:32])
        c.setFillColor(grey); c.setFont("Helvetica", 7.2)
        h = opt.get("height_m"); floors = opt.get("floors")
        c.drawString(x + 3*mm, card_y + card_h - 16*mm, f"HEIGHT  {h:g} m" if h is not None else "HEIGHT  Not set")
        c.drawRightString(x + card_w - 3*mm, card_y + card_h - 16*mm, f"{floors} floors" if floors is not None else "Floors not set")
        # Option-specific parcel/envelope preview.
        preview_h = 66*mm
        preview_y = card_y + card_h - 85*mm
        env_geom = (opt.get("boundary_envelope") or {}).get("geometry")
        _draw_geo_preview_pdf(c, x + 3*mm, preview_y, card_w - 6*mm, preview_h, boundary_geom, env_geom)
        # Divider then clear, client-readable metrics.
        y = preview_y - 4*mm
        c.setStrokeColor(line); c.line(x + 3*mm, y + 1.2*mm, x + card_w - 3*mm, y + 1.2*mm)
        y -= 4.4*mm
        lines = [
            ("BUILDING SETBACK", _option_setback_plain(opt)),
            ("BASEMENT", (f"{int(opt.get('basement_levels', 0))} level(s) · {_basement_setback_plain(opt)}" if int(opt.get("basement_levels", 0) or 0) > 0 else "Not included")),
            ("GROUND FOOTPRINT", f"{opt['footprint_m2']:,.0f} m²" if opt.get("footprint_m2") is not None else "Not calculated"),
            ("APPROX. FLOOR AREA", f"{opt['gross_concept_area_m2']:,.0f} m²" if opt.get("gross_concept_area_m2") is not None else "Not calculated"),
            ("ACHIEVED FAR" + (" · NET BASIS" if opt.get("far_ratio_basis", "gross site area") != "gross site area" else ""), f"{opt['achieved_far_ratio']:.2f}" if opt.get("achieved_far_ratio") is not None else "Not calculated"),
        ]
        line_h = 7.1*mm if n <= 3 else 6.5*mm
        for label, value in lines:
            c.setFillColor(grey); c.setFont("Helvetica-Bold", 6.1 if n >= 4 else 6.5)
            c.drawString(x + 3*mm, y, label)
            c.setFillColor(dark); c.setFont("Helvetica-Bold", 7.3 if n >= 4 else 8)
            # Wrap longer setback summaries within card width.
            maxv = card_w - 6*mm
            if stringWidth(value, "Helvetica-Bold", 7.3 if n >= 4 else 8) > maxv:
                c.setFont("Helvetica", 6.2 if n >= 4 else 6.7)
                first = value[:int(maxv/(3.6 if n >= 4 else 4.0))]
                c.drawString(x + 3*mm, y - 2.7*mm, first)
                y -= line_h + 2.4*mm
            else:
                c.drawString(x + 3*mm, y - 2.7*mm, value)
                y -= line_h
        delta_text, delta = _option_delta(opt, target_m2)
        badge_y = card_y + 3*mm
        c.setFillColor((mint if delta is None or delta <= 0 else colors.HexColor('#EEEEEE')))
        c.roundRect(x + 3*mm, badge_y, card_w - 6*mm, 8*mm, 3, stroke=0, fill=1)
        c.setFillColor((teal if delta is None or delta <= 0 else red)); c.setFont("Helvetica-Bold", 7.1)
        c.drawCentredString(x + card_w/2, badge_y + 2.8*mm, delta_text[:50])

    # Lower band: area bars and readable findings.
    low_y = 18*mm
    low_h = card_y - low_y - 7*mm
    chart_x = margin; chart_w = strip_w * 0.57
    panel_x = chart_x + chart_w + 5*mm; panel_w = strip_w - chart_w - 5*mm
    c.setFillColor(white); c.setStrokeColor(line); c.roundRect(chart_x, low_y, chart_w, low_h, 4, stroke=1, fill=1)
    c.setFillColor(dark); c.setFont("Helvetica-Bold", 10); c.drawString(chart_x + 4*mm, low_y + low_h - 7*mm, "FLOOR-AREA COMPARISON")
    c.setFillColor(grey); c.setFont("Helvetica", 6.8); c.drawString(chart_x + 4*mm, low_y + low_h - 12*mm, "Concept estimate compared with the maximum FAR-area benchmark")
    chart_rows = []
    if target_m2 is not None:
        chart_rows.append(("FAR benchmark", target_m2, teal))
    for i, opt in enumerate(options):
        if opt.get("gross_concept_area_m2") is not None:
            delta = float(opt["gross_concept_area_m2"]) - target_m2 if target_m2 is not None else 0
            chart_rows.append((str(opt.get("name", f"Option {i+1}")), float(opt["gross_concept_area_m2"]), orange if delta > 0.5 else color_cycle[i % len(color_cycle)]))
    if not chart_rows:
        chart_rows.append(("No calculated floor area", 0, grey))
    maxbar = max([v for _, v, _ in chart_rows] + [1])
    bar_x = chart_x + 35*mm; bar_w = chart_w - 56*mm
    rows_top = low_y + low_h - 20*mm
    row_space = min(11*mm, (low_h - 24*mm) / max(len(chart_rows), 1))
    for idx, (label, value, col) in enumerate(chart_rows):
        yy = rows_top - idx * row_space
        c.setFillColor(dark); c.setFont("Helvetica", 7.2); c.drawString(chart_x + 4*mm, yy + 1.2*mm, label[:21])
        c.setFillColor(pale); c.roundRect(bar_x, yy, bar_w, 3.5*mm, 1.5*mm, stroke=0, fill=1)
        c.setFillColor(col); c.roundRect(bar_x, yy, max(0.8*mm, bar_w * value / maxbar), 3.5*mm, 1.5*mm, stroke=0, fill=1)
        c.setFillColor(dark); c.setFont("Helvetica-Bold", 7); c.drawRightString(chart_x + chart_w - 4*mm, yy + 1.2*mm, f"{value:,.0f} m²")

    c.setFillColor(dark); c.roundRect(panel_x, low_y, panel_w, low_h, 4, stroke=0, fill=1)
    c.setFillColor(colors.HexColor('#D0D0D0')); c.setFont("Helvetica-Bold", 10); c.drawString(panel_x + 4*mm, low_y + low_h - 7*mm, "WHAT THE OPTIONS TELL US")
    findings = []
    if target_m2 is not None and options:
        above = [o for o in options if o.get("gross_concept_area_m2") is not None and float(o["gross_concept_area_m2"]) > target_m2 + 0.5]
        within = [o for o in options if o.get("gross_concept_area_m2") is not None and float(o["gross_concept_area_m2"]) <= target_m2 + 0.5]
        if above:
            closest = min(above, key=lambda o: float(o["gross_concept_area_m2"]) - target_m2)
            findings.append(f"{len(above)} option(s) exceed the benchmark; {closest.get('name')} is closest to it.")
        if within:
            best = max(within, key=lambda o: float(o["gross_concept_area_m2"]))
            findings.append(f"{best.get('name')} is within the arithmetic benchmark before exclusions and detailed design checks.")
        highest = max([o for o in options if o.get("gross_concept_area_m2") is not None], key=lambda o: o["gross_concept_area_m2"], default=None)
        if highest:
            basis_note = "FAR on net calculation area" if highest.get("far_ratio_basis", "gross site area") != "gross site area" else "FAR on gross site area"
            findings.append(f"Highest calculated floor area: {highest.get('name')} — {highest['gross_concept_area_m2']:,.0f} m² ({basis_note}: {highest.get('achieved_far_ratio', 0):.2f}).")
    else:
        findings.append("A maximum FAR benchmark is not available from the selected rule profile. Resolve the rule before choosing a preferred option.")
    findings.append("Basement area is shown separately; it is not included in the above-ground gross FAR proxy.")
    findings.append("Verify zone, road width, plot boundary, exclusions, fire, parking and applicable official setbacks before design freeze.")
    y = low_y + low_h - 15*mm
    for f in findings[:4]:
        y = _draw_pdf_wrapped(c, f, panel_x + 4*mm, y, panel_w - 8*mm, 7.3, white, max_lines=2)
        y -= 2*mm

    c.setFillColor(grey); c.setFont("Helvetica", 6.5)
    footer = "*Provisional FAR transcribed from a secondary plan copy; confirm current official rules." if far.get("rule_source_quality") == "secondary_copy_pending_official_validation" else "Verify current authority, zone and operative rules before sanction use."
    c.drawString(margin, 7*mm, f"SITEIQ v{__version__} · {report.get('application', {}).get('assessment_date', '')} · Preliminary study — not sanction · {footer}")
    c.drawRightString(page_w - margin, 7*mm, "Rule-derived benchmark remains subject to jurisdiction and operative-source verification")
    c.showPage(); c.save()
    return buf.getvalue()


def _draw_pdf_wrapped(c, text, x, y, max_width, font_size=8, color=NAVY, max_lines=3):
    """Draw wrapped text starting at y (top baseline) and return next y below text."""
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and stringWidth(trial, "Helvetica", font_size) > max_width:
            lines.append(current); current = word
        else:
            current = trial
    if current:
        lines.append(current)
    lines = lines[:max_lines]
    c.setFillColor(color); c.setFont("Helvetica", font_size)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * (font_size + 2), line)
    return y - len(lines) * (font_size + 2)


def _pptx_polyline(slide, geom, x, y, w, h, color, width_pt=1.4, fill_color=None, reference_bounds=None):
    """Draw a GeoJSON polygon as editable PowerPoint connector lines."""
    from pptx.enum.shapes import MSO_CONNECTOR
    polygons = _geojson_polygon_lists(geom)
    if not polygons:
        return
    pts = [pt for poly in polygons for pt in poly]
    if reference_bounds is None:
        minx=min(p[0] for p in pts); maxx=max(p[0] for p in pts)
        miny=min(p[1] for p in pts); maxy=max(p[1] for p in pts)
    else:
        minx, miny, maxx, maxy = reference_bounds
    dx=max(maxx-minx,1e-6); dy=max(maxy-miny,1e-6)
    scale=min((w-0.12)/dx,(h-0.12)/dy)
    ox=x+(w-dx*scale)/2-minx*scale
    oy=y+(h-dy*scale)/2-miny*scale
    for poly in polygons:
        transformed=[(ox+px*scale, oy+(maxy-py)*scale) for px,py in poly]
        for a,b in zip(transformed, transformed[1:]+transformed[:1]):
            line=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(a[0]), Inches(a[1]), Inches(b[0]), Inches(b[1]))
            line.line.color.rgb = _hex(color)
            line.line.width = Pt(width_pt)


def build_a3_comparison_board_pptx(report: dict) -> bytes:
    """Generate a single editable A3 landscape PPTX comparison board."""
    prs = Presentation()
    prs.slide_width = Inches(16.54)
    prs.slide_height = Inches(11.69)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    site = report.get("site", {})
    options = report.get("scenarios", [])[:4]
    target_m2, target_far = _scenario_target(report)
    boundary = report.get("boundary_analysis") or {}
    boundary_geom = boundary.get("geometry")
    dark=(46,46,46); teal=(88,88,88); mint=(238,238,238); pale=(245,245,245); grey=(101,101,101); white=(255,255,255); orange=(142,142,142); red=(99,99,99); line=(221,221,221)
    _add_rect(slide,0,0,16.54,11.69,(251,251,251))
    _add_rect(slide,0,0,16.54,0.12,dark)
    _add_text(slide,0.4,0.22,10.5,0.25,"SITEIQ  /  RESIDENTIAL FEASIBILITY",9,teal,True)
    _add_text(slide,0.4,0.48,11.6,0.52,report.get("project","Site feasibility"),25,dark,True)
    _add_text(slide,0.4,1.03,13.0,0.24,(_verdict_line(report) or "BUILDING ENVELOPE + FAR COMPARISON  ·  PRELIMINARY DESIGN STUDY — NOT SANCTION")[:150],9,grey)
    _add_rect(slide,12.6,0.38,3.5,0.55,dark,radius=True)
    _add_text(slide,12.75,0.52,3.2,0.22,f"ASSESSMENT  {report.get('application',{}).get('assessment_date','')}",8,white,True,align=PP_ALIGN.CENTER)

    far_label = "PROVISIONAL FAR*" if report.get("far", {}).get("rule_source_quality") == "secondary_copy_pending_official_validation" else "MAX FAR CANDIDATE"
    metrics=[
        ("SITE AREA", f"{site.get('site_area_m2',0):,.0f} m²"),
        ("ROAD WIDTH", f"{site.get('road_width_m',0):.2f} m"),
        ("LAND-USE CATEGORY", str(site.get("land_use_category",site.get("zone","Not selected")))),
        (far_label, f"{target_far:.2f}" if target_far is not None else "Needs confirmation"),
        ("FAR AREA BENCHMARK", f"{target_m2:,.0f} m²" if target_m2 is not None else "Not established"),
    ]
    met_x, met_y, met_w, met_h = 0.4, 1.36, 15.74, 0.62
    _add_rect(slide,met_x,met_y,met_w,met_h,mint,radius=True)
    colw=met_w/len(metrics)
    for i,(label,value) in enumerate(metrics):
        x=met_x+i*colw
        if i: slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(met_y+0.08), Inches(x), Inches(met_y+met_h-0.08)).line.color.rgb=_hex(line)
        _add_text(slide,x+0.10,met_y+0.08,colw-0.2,0.16,label,7.2,grey,True)
        _add_text(slide,x+0.10,met_y+0.29,colw-0.2,0.24,value[:29],10.2,dark,True)

    card_x0=0.4; card_y=2.16; card_h=6.53; gap=0.14
    n=max(1,len(options)); card_w=(15.74-gap*(n-1))/n
    accents=[teal,(115,115,115),(142,142,142),(123,123,123)]
    for i,opt in enumerate(options):
        x=card_x0+i*(card_w+gap); accent=accents[i%len(accents)]
        _add_rect(slide,x,card_y,card_w,card_h,white,line=line,radius=True)
        _add_rect(slide,x,card_y,card_w,0.48,accent,radius=True)
        _add_rect(slide,x,card_y+0.32,card_w,0.16,accent)
        _add_text(slide,x+0.14,card_y+0.11,card_w-0.28,0.24,opt.get("name",f"Option {i+1}"),11,white,True)
        ht=opt.get("height_m"); floors=opt.get("floors")
        _add_text(slide,x+0.14,card_y+0.59,card_w-0.28,0.22,f"HEIGHT  {ht:g} m" if ht is not None else "HEIGHT  Not set",8.5,grey,True)
        _add_text(slide,x+0.14,card_y+0.83,card_w-0.28,0.22,f"{floors} above-ground floors" if floors is not None else "Floors not set",8.5,dark)
        diagram_x=x+0.13; diagram_y=card_y+1.18; diagram_w=card_w-0.26; diagram_h=2.6
        if boundary_geom:
            boundary_polys = _geojson_polygon_lists(boundary_geom)
            boundary_pts = [pt for poly in boundary_polys for pt in poly]
            ref_bounds = (min(p[0] for p in boundary_pts), min(p[1] for p in boundary_pts), max(p[0] for p in boundary_pts), max(p[1] for p in boundary_pts)) if boundary_pts else None
            _pptx_polyline(slide,boundary_geom,diagram_x,diagram_y,diagram_w,diagram_h,dark,1.2,reference_bounds=ref_bounds)
            env=(opt.get("boundary_envelope") or {}).get("geometry")
            if env: _pptx_polyline(slide,env,diagram_x,diagram_y,diagram_w,diagram_h,accent,1.7,reference_bounds=ref_bounds)
        else:
            _add_rect(slide,diagram_x+0.20,diagram_y+0.18,diagram_w-0.40,diagram_h-0.36,pale,line=line,radius=True)
            _add_text(slide,diagram_x+0.28,diagram_y+0.58,diagram_w-0.56,0.36,"Boundary drawing not imported",8,grey,False,align=PP_ALIGN.CENTER)
        _add_rect(slide,x+0.12,card_y+3.87,card_w-0.24,0.04,line)
        details=[
            ("BUILDING SETBACK",_option_setback_plain(opt)),
            ("BASEMENT",(f"{int(opt.get('basement_levels',0))} level(s) · {_basement_setback_plain(opt)}" if int(opt.get("basement_levels",0) or 0)>0 else "Not included")),
            ("GROUND FOOTPRINT",f"{opt['footprint_m2']:,.0f} m²" if opt.get("footprint_m2") is not None else "Not calculated"),
            ("APPROX. FLOOR AREA",f"{opt['gross_concept_area_m2']:,.0f} m²" if opt.get("gross_concept_area_m2") is not None else "Not calculated"),
            ("ACHIEVED FAR" + (" · NET BASIS" if opt.get("far_ratio_basis", "gross site area") != "gross site area" else ""),f"{opt['achieved_far_ratio']:.2f}" if opt.get("achieved_far_ratio") is not None else "Not calculated"),
        ]
        yy=card_y+4.06
        for label,value in details:
            _add_text(slide,x+0.14,yy,card_w-0.28,0.16,label,7.1,grey,True)
            _add_text(slide,x+0.14,yy+0.15,card_w-0.28,0.22,value,8.2,dark,True)
            yy+=0.39
        delta_text, delta=_option_delta(opt,target_m2)
        fill=mint if delta is None or delta<=0 else (238,238,238)
        textcolor=teal if delta is None or delta<=0 else red
        _add_rect(slide,x+0.12,card_y+card_h-0.49,card_w-0.24,0.34,fill,radius=True)
        _add_text(slide,x+0.18,card_y+card_h-0.42,card_w-0.36,0.2,delta_text,8,textcolor,True,align=PP_ALIGN.CENTER)

    # Floor area bar comparison.
    band_y=8.84; band_h=2.25
    chart_w=9.0; panel_x=9.65; panel_w=6.49
    _add_rect(slide,0.4,band_y,chart_w,band_h,white,line=line,radius=True)
    _add_text(slide,0.65,band_y+0.18,8.5,0.25,"FLOOR-AREA COMPARISON",11,dark,True)
    _add_text(slide,0.65,band_y+0.47,8.5,0.2,"Approximate floor area compared with the maximum FAR-area benchmark",8,grey)
    chart_rows=[]
    if target_m2 is not None: chart_rows.append(("FAR benchmark",target_m2,teal))
    for i,opt in enumerate(options):
        if opt.get("gross_concept_area_m2") is not None:
            val=float(opt["gross_concept_area_m2"]); over=target_m2 is not None and val>target_m2+0.5
            chart_rows.append((opt.get("name",f"Option {i+1}"),val,orange if over else accents[i%len(accents)]))
    maxval=max([r[1] for r in chart_rows]+[1])
    chart_top=band_y+0.8; row_step=0.27; bar_start=2.3; bar_max=5.1
    for i,(label,val,col) in enumerate(chart_rows[:5]):
        yy=chart_top+i*row_step
        _add_text(slide,0.65,yy,1.5,0.23,label,7.8,dark)
        _add_rect(slide,bar_start,yy+0.01,bar_max,0.14,pale,radius=True)
        _add_rect(slide,bar_start,yy+0.01,max(0.04,bar_max*val/maxval),0.14,col,radius=True)
        _add_text(slide,7.55,yy-0.01,1.45,0.22,f"{val:,.0f} m²",8,dark,True,align=PP_ALIGN.RIGHT)

    _add_rect(slide,panel_x,band_y,panel_w,band_h,dark,radius=True)
    _add_text(slide,panel_x+0.25,band_y+0.2,panel_w-0.5,0.25,"WHAT THE OPTIONS TELL US",10,(208,208,208),True)
    findings=[]
    if target_m2 is not None and options:
        over=[o for o in options if o.get("gross_concept_area_m2") is not None and o["gross_concept_area_m2"]>target_m2+0.5]
        within=[o for o in options if o.get("gross_concept_area_m2") is not None and o["gross_concept_area_m2"]<=target_m2+0.5]
        if over:
            closest=min(over,key=lambda o:o["gross_concept_area_m2"]-target_m2)
            findings.append(f"{len(over)} option(s) exceed the benchmark; {closest.get('name')} is closest.")
        if within:
            best=max(within,key=lambda o:o["gross_concept_area_m2"])
            findings.append(f"{best.get('name')} is within the arithmetic benchmark before FAR exclusions and design checks.")
        highest=max([o for o in options if o.get("gross_concept_area_m2") is not None],key=lambda o:o["gross_concept_area_m2"],default=None)
        if highest:
            basis_note = "FAR on net area" if highest.get("far_ratio_basis", "gross site area") != "gross site area" else "FAR on gross site area"
            findings.append(f"Highest gross floor-area proxy: {highest.get('name')} — {highest['gross_concept_area_m2']:,.0f} m² ({basis_note}: {highest.get('achieved_far_ratio',0):.2f}).")
    else:
        findings.append("Maximum FAR benchmark not established. Confirm the rule before selecting a preferred option.")
    findings += ["Basements and upper-floor variations require separate design checks.","Confirm jurisdiction, zone, survey boundary, fire, parking and current operative rules before design freeze."]
    yy=band_y+0.52
    for f in findings[:4]:
        _add_text(slide,panel_x+0.25,yy,panel_w-0.5,0.38,"• "+f,7.8,white)
        yy+=0.40
    board_footer = "*FAR transcribed from a secondary plan copy; confirm current official rules." if report.get("far", {}).get("rule_source_quality") == "secondary_copy_pending_official_validation" else "Preliminary study — verify official zone and operative rules before sanction."
    _add_text(slide,0.4,11.2,15.1,0.18,f"SITEIQ v{__version__} · {report.get('application',{}).get('assessment_date','')} · {board_footer}",7,grey)

    out=BytesIO(); prs.save(out); return out.getvalue()
