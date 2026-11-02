> **Historical document.** This is the original handover brief for v0.4.7. The file layout, stack and defect list below are out of date. For the current state see `README.md`, `CHANGELOG.md` and `SOURCES.md`.

# SiteIQ — Project Master Brief for Engineering Agent

**Document purpose:** This is the handover brief for an engineering agent taking the existing SiteIQ prototype and turning it into a maintainable, complete application. Read this document together with the existing SiteIQ ZIP/source code before making changes.

**Prepared:** 1 November 2026  
**Current codebase baseline supplied in this handover:** `SiteIQ_v047_GoogleMapsPriorityFix.zip` / SiteIQ v0.4.7  
**GitHub target:** `https://github.com/Pritish3110/SiteIQ.git`  
**Product type:** Browser-based internal architectural site-feasibility application, initially focused on Karnataka, India.

> **Important:** SiteIQ is a preliminary feasibility and design-option tool. It is not a statutory sanction system, legal opinion, or substitute for the applicable notified regulations and authority confirmation. A result must never be presented as a confirmed entitlement when its jurisdiction, zone, source status or rule applicability is uncertain.

---

# 1. Project overview

## 1.1 What is SiteIQ?

SiteIQ is a browser-based tool intended to automate the early-stage regulatory and architectural feasibility process that architects currently perform manually for development sites.

The user provides a location, a site boundary and a small number of project inputs. SiteIQ should then:

1. Identify the likely planning authority and the relevant regulatory jurisdiction from the site location.
2. Derive the site area and geometry from an uploaded site boundary wherever possible.
3. Let the user select the intended regulatory land-use category from the categories configured for that authority.
4. Use the abutting road width and plot-area conditions to find the applicable maximum FAR from the correct authority-specific regulation.
5. Use that rule-derived FAR as the benchmark for multiple design scenarios.
6. Compare different building heights, floor counts, building setbacks, stilt conditions, basements and basement setbacks.
7. Calculate the preliminary buildable envelope and the FAR yield for each option.
8. Produce a clear comparative feasibility study, with diagrams and traceable source references, in PDF and editable PowerPoint formats.

The core objective is to **minimise repeated manual searching through regulations and speed up architectural feasibility studies**, while retaining transparent calculations and source traceability.

SiteIQ should serve two audiences:

- **Architects/design team:** need detailed rule lookup, dimensions, calculations, drawings, option controls and source clauses.
- **Client/developer:** needs a concise, plain-language explanation of what can be explored, how the options compare, what is uncertain, and what decisions are required next.

## 1.2 Product principles

1. **Accuracy before automation coverage.** Never invent or extrapolate a regulatory value to fill a missing rule.
2. **Authority-specific rules.** Do not apply Bengaluru RMP 2015 rules to Hoskote, Kanakapura, Mysuru or any other authority unless that exact authority's applicable instrument says so.
3. **One source of truth for the site location.** The active boundary/map point used for jurisdiction identification must be visible and consistent with the boundary used for area and envelope calculations.
4. **Traceability.** Every rule-derived result must show the regulation, notification, date, clause/table, page, source document and source status.
5. **Explainable calculations.** Show the input values, selected bands, calculation method, exclusions, formula and result.
6. **Explicit uncertainty.** Mark information as verified, provisional, calculated, assumed, unresolved or pending authority confirmation.
7. **No silent fallback.** If a map link fails or a rule does not match, do not reuse stale coordinates, an earlier authority result or another authority's FAR.
8. **Geometry-aware feasibility.** Use the actual irregular boundary, not a rectangular approximation, whenever a valid survey/polyline is available.
9. **Client-friendly reporting.** Lead with the conclusion and options; place detailed regulatory extracts and technical calculations in the supporting sections/appendix.
10. **Versioned rules.** Regulations change. Preserve the history and effective dates of rule sets rather than silently overwriting older rules.

---

# 2. Intended user workflow

The workflow below is the product's principal functional requirement. Keep the order and user experience aligned with this process.

## Stage 1 — Identify the site and planning jurisdiction

**User inputs:**
- Project name and optional client/project code.
- Site address/locality.
- Google Maps link (optional but preferred when available).
- Coordinates (optional; latitude, longitude).
- Site boundary file (KML/KMZ, DXF or supported PDF geometry).

**System actions:**
- Resolve the best available site location.
- Identify the likely planning authority using official planning-area boundary data where available.
- Distinguish a planning authority/local planning area from a municipal corporation, ward, revenue district, taluk or administrative zone. These are not interchangeable.
- Identify an official land-use zone only if the correct current official zoning layer/map has been matched to the parcel. The selected regulatory category used for the FAR table is a separate field.
- Suggest an approval route only where the chosen authority's rules contain a configured route and the inputs meet its criteria.

**Required location-source precedence:**
1. Applied/selected georeferenced site boundary (KML/KMZ) when the user has explicitly selected/applied it.
2. Resolved Google Maps link, when supplied.
3. Manually entered coordinates, when no usable higher-priority source is supplied.
4. Address geocoding, only when there is no usable map link or coordinate pair.

The UI must display **which source was used** and the coordinates used for the jurisdiction lookup. If two sources disagree materially (initial default 1 km warning threshold; make configurable), display the distance and ask the user to resolve the mismatch. Do not quietly pick whichever value is easiest to process.

**Critical known defect to investigate:** the user tested a short Google Maps link (`https://maps.app.goo.gl/VGjypsrJo2TogXrF6`) while the address and manually displayed coordinates still represented Tumakuru (`13.3297678, 77.1121664`). SiteIQ continued to show “Other Karnataka planning authority” instead of resolving the intended map location. The v0.4.7 code contains short-link expansion via `requests`, but the real-world short-link workflow has not been reliably demonstrated. Treat this as an open P0/P1 issue, reproduce it using the actual link, inspect redirects/HTML/metadata, and fix it with explicit success/failure states. Do not claim this is fixed merely because the code attempts `requests.get()`.

## Stage 2 — Import and validate the plot boundary

Plot area should be derived from the actual site polyline where the user chooses to use the imported boundary.

Supported input in the current prototype:
- **DXF:** closed `LWPOLYLINE` / `POLYLINE` entities. Read `$INSUNITS` where available. If units are missing or ambiguous, require calibration from a known dimension. Native DWG is not read directly; user must export/save as DXF.
- **KML/KMZ:** Polygon outer rings and LineStrings. KML coordinates are geographic longitude/latitude. Open LineStrings can provide a location lookup anchor but cannot be treated as an area boundary until the user confirms the closing edge.
- **PDF:** simple vector line paths, rectangles and quadrilaterals only, within the current supported extractor. Scale calibration is mandatory. Scanned/raster PDFs and fragmented linework are not automatically traced in the prototype.

**Boundary validation must include:**
- Geometry type and number of candidate features.
- Selected candidate identifier and source filename.
- CRS/coordinate system and units.
- Closure status.
- Unique vertex count.
- Self-intersection and validity checks.
- Computed area and perimeter.
- Bounding box and, where applicable, area difference from the user's stated area.
- Warnings if the uploaded file contains multiple candidate polygons or an open path.
- Explicit confirmation before joining an open perimeter's last point to its first point.

Never silently repair a self-intersecting legal boundary and use the repaired geometry as if it were the survey. A repaired copy may be offered as a diagnostic, but preserve the original and require review/confirmation.

For KML/KMZ, use a suitable projected metric CRS (the prototype currently chooses a local UTM EPSG based on the feature location) for area, distance and setback geometry. Preserve the original WGS84 coordinates and document the projection used.

## Stage 3 — Select regulatory land-use category

Once the likely authority/profile is selected, populate the regulatory category dropdown from that authority's rule profile.

Examples of categories that have appeared in the Bengaluru RMP profile include:
- Residential (Main)
- Residential (Mixed)
- Commercial (Central)
- Commercial (Business)
- Mutation Corridors
- Industrial (General)
- Industrial (Hi-Tech)
- Public and Semi-public
- Traffic and Transportation
- Other categories explicitly listed by each authority's rules.

Do not hardcode one statewide list. Each authority profile must define its own categories, aliases, permissible uses and applicable tables.

Keep these two concepts separate in UI and reports:
- **Official land-use zone:** identified from the approved land-use map or authoritative confirmation.
- **Regulatory category selected for calculation:** the table/category the user selects within the chosen rule profile.

If the official zone is unverified, clearly show that the user must confirm that the selected regulatory category matches the notified land-use designation.

## Stage 4 — Enter official abutting road width

The user enters the legally recognised abutting road width in metres. The software uses this to select the applicable road-width band and any minimum-road-width eligibility condition.

The tool should distinguish:
- measured/observed road width;
- road width shown on a survey/approved plan;
- notified/right-of-way width used by the regulation;
- road widening or master-plan road reservations.

Do not assume the visually measured road width is the legally applicable width. Record its source/status and warn when it is not verified.

## Stage 5 — Identify maximum FAR benchmark

This is one of SiteIQ's most important features.

The rule engine should select the correct maximum FAR using the exact structure of the selected authority/category table. The current core engine supports rule methods such as:
- `area_cap_and_road_width`: select one plot-area cap and one road-width FAR band, then apply the exact configured interpretation (currently the lower of the two values in the Bengaluru implementation).
- `road_width`: select the single exact road-width band.
- `plot_area`: select the single exact plot-area band and any minimum road width condition.
- `fixed`: apply an expressly configured fixed FAR where the rule says so.
- Conditional rule paths, e.g. a group-housing/residential development-plan table when plot area and proposed use satisfy the configured conditions.

**Rules engine requirements:**
- Implement exact band matching with inclusive/exclusive lower and upper bounds.
- Do not interpolate, extrapolate, choose the nearest band or fill missing table rows.
- If zero or multiple bands match, return a clear unresolved status and show why.
- Apply minimum plot area, maximum plot area, minimum frontage, road width, surrounding-zone, occupancy/use and development-route conditions as recorded in the source.
- Calculate the FAR calculation area using the table's stated gross/net basis and configured deductions/reservations. Clearly show gross site area, excluded area and net FAR calculation area.
- Keep base FAR separate from optional Premium FAR/TDR scenarios. Premium FAR/TDR must never silently inflate the base statutory benchmark.
- Every positive FAR result is a rule-derived candidate with source metadata and status, not an approval or entitlement.

**Expected output:**
- Maximum FAR candidate (e.g. 2.50).
- Area calculation basis (gross or net, and why).
- Maximum FAR floor-area benchmark (FAR × applicable calculation area).
- Exact selected table row(s), plot-area band and road-width band.
- Limiting factor, conditions, exceptions and source citation.
- Rule status: verified operative / partial / provisional secondary source / draft-only / unresolved.

## Stage 6 — Compare multiple design options

After a base FAR benchmark is established, allow the architect to prepare multiple options. Each option must be independently configurable.

Required option inputs:
- Option name.
- Building height (metres).
- Number of above-ground floors.
- Stilt present/not present and stilt height where relevant.
- Building setbacks: percentage-based/front-rear-side values or all-round fixed setback, as allowed by the applicable rule.
- Front, rear, left and right edges/segments for irregular plots.
- Basement levels.
- Basement front and non-front setbacks or the applicable profile rule.
- User-entered footprint, or computed envelope area when geometry/rule method supports it.
- Optional notes/alternative design assumptions.

For each option SiteIQ should calculate/display:
- Rule-derived building setback summary and its rule source/status.
- Preliminary buildable polygon/envelope and its area.
- Basement envelope and area, separately from building envelope.
- Footprint area used.
- Above-ground gross concept area (normally footprint × above-ground floor count, unless a more detailed floor schedule is supplied).
- Achieved gross FAR ratio and the denominator used.
- FAR-area benchmark.
- Remaining area or excess area compared with the benchmark.
- Warnings if entered footprint exceeds the calculated envelope.
- Any height/fire/access/parking triggers that can be derived from configured rules.

**Geometry requirements for irregular plots:**
- Let the architect select/label front and rear boundary edges; do not infer the legal frontage from geometry orientation alone.
- Map setback values to individual boundary segments, not just a single uniform inward buffer, when the applicable rule distinguishes front/rear/sides.
- Handle concave polygons, narrow necks, disconnected envelopes and corners carefully. Use robust geometric construction/offset methods and explicit validity checks.
- If an inward offset creates multiple parts or collapses a narrow section, report that outcome; do not fabricate a single rectangle.
- Clearly distinguish a statutory setback envelope from a user-created footprint and from a final architectural design.
- The current Shapely-based prototype is a preliminary geometry engine. Its methods need independent tests and CAD review for complex irregular plots before being treated as production-grade.

## Stage 7 — Produce comparative feasibility output

Use the user's manual Nandi Housing feasibility board as the visual/content reference. The board includes a reference layout (Umiya Prism) and three options:

| Option | Height | Floors | Setback assumption | Footprint | Gross floor-area estimate | Achieved gross FAR |
|---|---:|---:|---|---:|---:|---:|
| Option 01 | 12 m | 4 | Percentage basis | 1,483 m² | 5,932 m² | 2.69 |
| Option 02 | 15 m | 5 | 5 m all around | 1,271 m² | 6,355 m² | 2.88 |
| Option 03 | 18 m | 6 | 6 m all around | 1,106 m² | 6,636 m² | 3.01 |

These values are retained from the manual study as illustrative comparison inputs. The source study used a site area of approximately 2,200 m², road width over 18 m, and a working FAR assumption of 2.50 / approximately 5,500 m² benchmark. The 2.50 FAR was explicitly a working assumption, not a confirmed statutory entitlement. The sample illustrates the desired report style and comparison logic; it must not be taken as a verified legal determination.

Output formats required:
1. Detailed, client-friendly PDF report with technical appendix.
2. Editable PowerPoint report.
3. Single-page A3 landscape comparison-board PDF.
4. Editable A3 landscape comparison-board PowerPoint.
5. Structured JSON assessment.
6. Boundary/building-envelope/basement-envelope DXF export where valid geometry exists.

---

# 3. Design/report output criteria

These are the criteria SiteIQ should consider when calculating and presenting a feasibility result. Every criterion should be explicitly marked as configured, calculated, user supplied, assumed, unresolved or outside the current MVP.

## 3.1 Site identity and jurisdiction
- Project name/client code.
- Site address/locality and map link.
- Latitude/longitude and the source used to obtain them.
- Active boundary filename and selected feature.
- Planning authority and notified planning-area status.
- Municipal corporation/ward/admin zone as separate context fields.
- Official land-use zone and verification status.
- Rule profile/version and source review date.
- Approval route/development pathway (single plot, development plan, group housing, etc.) only if rules and inputs support it.

## 3.2 Site geometry
- Stated plot area vs area computed from the polyline.
- Difference and tolerance warning.
- Perimeter and vertex count.
- Frontage/depth only where meaningful and confirmed.
- Irregular/concave/convex status.
- Front/rear/side boundary assignment.
- Boundary validity, closure, self-intersection and CRS/units.
- Road edge and access point.
- Any known road widening/reservation, drain, lake, HT line, flood-prone or other overlay.

## 3.3 Planning and development controls
- Regulatory land-use category.
- Proposed use/occupancy.
- Plot-area FAR band.
- Road-width FAR band.
- Maximum FAR candidate and the exact logic used to select it.
- Base FAR floor-area capacity.
- Ground coverage rule, if configured and applicable.
- Applicable plot-size/development-plan thresholds.
- Park, open-space, civic-amenity, surface-parking or other reservation deductions, if applicable.
- Gross vs net FAR calculation basis.
- Ancillary uses, additional FAR, TDR and Premium FAR only where expressly configured, with separate status.
- Any exemptions/grandfathering or prior-sanction considerations requiring confirmation.

## 3.4 Building envelope and height
- Height of building and how stilt is treated in the height definition.
- Number of floors and floor-to-floor assumptions where supplied.
- Table 8/percentage-based setbacks or Table 9/height-based setbacks, as applicable in the selected profile.
- Front/rear/left/right distances or all-round setback.
- Option-specific setbacks (never show only one generic setback for all options).
- Irregular-boundary offset geometry.
- Buildable envelope area and geometry status.
- Building separation distances if more than one building is proposed and rule data are available.
- Stilt parking requirements, stilt height and use conditions.

## 3.5 Basement and parking
- Number of basement levels per option.
- Basement setbacks, separately from building setbacks.
- Basement envelope area.
- Basement/flood/water-table/low-lying restrictions where a verified overlay/rule exists.
- Ramp count/width/gradient/turning only when the authority's current rules are configured.
- Parking requirement by occupancy/unit or floor-area schedule.
- Conventional vs mechanised parking scenario and its conditions.
- Surface parking, visitor parking and two-wheeler parking where applicable.
- Parking result should remain unresolved if the dwelling-unit mix/area inputs are not supplied.

## 3.6 Fire, life safety, accessibility and services
- Fire NOC/high-rise trigger based on configured current rule.
- Fire-tender access, gate/access-road width, turning and hardstanding where rules are available.
- Exit numbers/widths/travel distances/staircases and fire lift where relevant and configured.
- Accessibility: accessible route, entrance, ramp, lift, parking, toilets and common areas against the applicable current standards.
- Structural, geotechnical, electrical transformer, water, sewerage, stormwater/rainwater, STP and other service requirements where relevant.
- NOCs/clearances: fire, airport, lake/drain, HT line, pollution/environment, water/sewerage, electricity, traffic/road and other agencies as applicable.
- Do not invent dimensions or triggers when the applicable current standard is absent from the rule library.

## 3.7 Comparative design option metrics
For each option show:
- Height.
- Floors.
- Stilt condition.
- Building setback summary.
- Basement levels and setback summary.
- Footprint/envelope area.
- Gross concept floor area.
- Achieved gross FAR ratio and denominator.
- Base FAR benchmark and available/remaining or excess area.
- Any additional/Premium FAR/TDR scenario separately.
- Parking and fire/access constraints where calculable.
- Short plain-language interpretation (e.g. “Option exceeds the base FAR benchmark by 350 m²; review footprint or floor count”).

## 3.8 Presentation and visual design
- Professional architectural layout; restrained palette; clear typography and hierarchy.
- A3 landscape comparison board should be based on the Nandi Housing board: site boundary + option diagrams in comparable panels, metrics, FAR comparison graphic, key observations and verification notes.
- Use diagrams/plans/sections, not only text tables, for setbacks, envelopes, height and basement conditions.
- Distinguish actual site boundary, road/frontage, statutory setback line, preliminary buildable envelope, basement envelope and proposed footprint with a clear legend.
- Include north arrow and scale bar only when direction/scale is known.
- Show units everywhere; use consistent m, m², FAR and dates.
- Client report: plain-English executive summary first, client-facing terms and “what this means” callouts; technical calculations, rules and sources in later pages/appendix.
- Architect report: exact table rows, formulas, exclusions, edge labels, source citations and assumptions.
- Use consistent status labels: **Verified**, **Calculated**, **Provisional**, **Assumed**, **Pending confirmation**, **Not configured**, **Draft only**.
- Include report version, assessment date, software version and rule-profile version.
- PDF should be printable; provide A4 detailed report and A3 comparison board. Greyscale legibility should be considered.

---

# 4. Regulation library and legal/source governance

## 4.1 Current baseline coverage in v0.4.7

The supplied v0.4.7 package contains 25 authority/area registry entries. Current rule-profile states are:

### Partial or provisional profiles able to return selected FAR candidates
- Bengaluru / Greater Bengaluru RMP 2015 — partial selected rules profile based on user-supplied RMP and amendments.
- Hoskote LPA Master Plan 2031 — provisional FAR/setback candidate transcribed from secondary copies; official current version/amendments not independently confirmed.
- Kanakapura LPA Master Plan 2031 — provisional FAR/setback candidate from secondary copies; current operative version/amendments not independently confirmed. There is a known coordinate-range mismatch to investigate for the Attihalli test point.
- Nelamangala LPA Master Plan 2031 — provisional FAR/setback candidate from secondary copies; official current version/amendments not independently confirmed.
- Anekal LPA Master Plan 2031 — provisional selected general tables; group-housing path deliberately unresolved due conflicting source copies.

### Registry-only, draft-only or not configured in v0.4.7
- Bangalore Development Authority Local Planning Area (BDA LPA).
- Bengaluru Metropolitan Region Development Authority (BMRDA) regional context (not by itself the local building-control rule set).
- Mysuru Development Authority.
- Hubballi-Dharwad Urban Development Authority.
- Other Karnataka planning authority (manual verification).
- Bengaluru International Airport Area Planning Authority (BIAAPA).
- Channapatna Planning Authority.
- Doddaballapura Planning Authority.
- Magadi Planning Authority.
- Satellite Town Ring Road Planning Authority (STRRPA).
- Ramanagara Urban Development Authority (RUDA).
- Greater Bengaluru Development Authority designation appearing in the 2026 draft reference.
- Mangaluru, Belagavi, Kalaburagi, Davanagere, Tumakuru, Shivamogga, Ballari and Udupi planning areas (discovery queue; legal names/boundaries must be checked).

The in-app `rules/authority_coverage_matrix.csv` and `rules/authority_registry.json` are the current machine-readable coverage register. Keep them aligned.

## 4.2 Regulatory documents already considered in project discussions

The user supplied the following documents for the Bengaluru architect's regulatory handbook and the subsequent SiteIQ rule profile:
- `BBMP 2015.pdf` — Revised Master Plan 2015 zoning regulations, including land-use categories and FAR/coverage tables.
- `Amendment 01.pdf` through `Amendment 10.pdf` — user-supplied amendment set; each document must be read and indexed by notification/date/clauses before coding.
- `Karnataka Fire protection.pdf` — fire/life-safety reference document.
- The SiteIQ project also researched the Karnataka Fire Force (Amendment) Act, 2023 and later Karnataka notifications discussed below.

Important specific source references in current code/docs:
- Bengaluru RMP 2015 Residential (Main), Chapter 4, Regulation 4.1.2, Table 10 — base FAR table reference in the supplied `BBMP 2015.pdf` (PDF page 28 / printed page 27).
- Bengaluru RMP setbacks, Chapter 3, Regulation 3.1, Tables 8 and 9 — supplied `Amendment 01.pdf`, Notification UDD 235 MNJ 2025(E), dated 5 January 2026.
- Single Plot Approval / Chapter 6-A and basement provisions — supplied `Amendment 05.pdf`, Notification UDD 272 MNJ 2025(E), dated 16 July 2025.
- Fire high-rise definition/NOC threshold — user-supplied `Amendment 03.pdf`, Karnataka Fire Force (Amendment) Act, 2023; the code's note refers to 21 m or above. Current administrative process and all other applicable fire provisions still need confirmation.
- Premium FAR/TDR amendments and later updates were discussed in the handbook work. Keep Premium FAR/TDR distinct from base FAR and re-verify the currently operative notification and Table 27 before relying on figures.

Further research leads already recorded by the project:
- **UDD 559 BMR 2025(E), 24 March 2026:** draft Uniform Zonal Regulations proposal for multiple LPAs within BMRDA. The available draft says it commences only after final notification by the relevant authority. It is **draft only** in SiteIQ and must not be used as operative rules without proof of final notification and authority-specific commencement.
- **UDD 17 TTP 2025(E), 22 May 2026:** final amendment stated to apply to approved Master Plans outside the Bengaluru Metropolitan Region (including GBA/BDA/BMR authorities) and outside Mangaluru LPA. It standardises some land-use categories and contains selected special-use provisions (including industrial/commercial-in-industrial-area/flatted factory/related provisions). It does **not** create one universal residential FAR table for all Karnataka authorities.
- Kanakapura LPA Master Plan 2031 material has been found in secondary copies. Its current approved/operative version, notification/effective date, amendments and exact boundary still require confirmation.
- Hoskote, Kanakapura, Nelamangala and Anekal profiles in v0.4.7 are provisional source transcriptions, not independently verified consolidated operative codes.

## 4.3 Rules library requirements

Every authority needs a structured, versioned profile. At a minimum, encode:
- Authority key and legal name.
- Notified planning-area boundary/source/version/effective date.
- Approved Master Plan/zoning regulation name and notification/approval details.
- Source status and source quality.
- Applicable land-use categories and proposed uses.
- FAR methods and exact tables/bands.
- Plot-area and road-width conditions, inclusivity/exclusivity, frontage/access thresholds.
- Conditional routes: group housing, single plot, development plan, layout, industrial/other pathways.
- Gross/net FAR area basis and all exclusions/reservations.
- Ground coverage, height and setback tables.
- Stilt treatment, basement setbacks/limits, parking, ramps and mechanical parking.
- Premium FAR/TDR rules separately from base FAR.
- Fire, accessibility, environmental/buffer and other approval triggers where source-supported.
- Source metadata for each rule: unique source ID, title, notification number, publication date, effective date, clause, table, PDF page, official/secondary URL, status, notes, superseded-by relationship and reviewer.
- Explicit `effective_from` and `effective_to` where determinable.

Suggested source-status lifecycle:
- `draft_only`
- `secondary_source_candidate`
- `official_source_found_pending_review`
- `partially_verified`
- `verified_operative`
- `superseded`
- `withdrawn_or_stayed`
- `not_configured`
- `jurisdiction_unverified`
- `zone_unverified`

Only a profile promoted to the approved status defined by the product governance process should be treated as a verified operative rule profile. Provisional profiles may be used for preliminary candidates only if the UI/report conspicuously marks the status and the product owner accepts that mode. Draft rules must never be active.

## 4.4 Spatial layers already supplied by the user

The user uploaded five OpenCity KML files:
- `53329777-285d-43d6-b2cf-dd54900d4dc6.kml` — GBA boundary polygon.
- `790f6df1-45dc-4096-b4ed-53a4c3743d58.kml` — corporation boundaries.
- `e7ad0eac-7fa9-435f-822d-752be486e726.kml` — administrative zones.
- `632f5209-dfe1-4e0e-9fa9-d11c21028e55.kml` — corporation-grouped areas.
- `gba-369-wards-december-2025.kml` — 369-ward map.

Assessment made during the project:
- The GBA wards layer contains 369 ward polygons with administrative attributes (corporation, ward name/number and administrative zone). Eight geometries were reported with self-intersections and must be validated/repaired only on a working copy.
- The corporation KML contains five corporation areas; some polygons have validity issues.
- The administrative zone KML contains labels such as `Zone1` and `Zone2`. These are administrative zone labels, **not** RMP regulatory land-use categories such as Residential (Main), Commercial or Industrial.
- These datasets cover Greater Bengaluru administrative geography; they do not establish all Karnataka planning authority boundaries or land-use zones.
- Corporation, ward, administrative-zone, planning-authority and regulatory land-use boundaries are distinct data layers. Do not map one to another without authoritative evidence.

These files can support administrative/context lookups for sites in their coverage. Do not use them alone to calculate FAR or establish the legal planning authority for sites outside the covered geography.

---

# 5. Existing technical stack (actual v0.4.7 codebase)

The agent must inspect and preserve/upgrade this existing stack unless a documented technical reason justifies a change. Do not claim that a technology is already implemented if it is only proposed.

## 5.1 Runtime and application
- **Python 3.10+** — application/runtime.
- **Streamlit (`streamlit>=1.37,<2`)** — local browser-based user interface; no separate React/Vue frontend in the current prototype.
- **Pandas (`pandas>=2.0,<3`)** — comparison tables and tabular data handling.

## 5.2 Geometry, CAD and GIS
- **Shapely (`shapely>=2.0,<3`)** — polygon construction, validity checks, point-in-polygon spatial checks, setback envelope calculations and geometry operations.
- **ezdxf (`ezdxf>=1.3,<2`)** — DXF polyline import and DXF boundary/envelope export.
- **PyMuPDF / fitz (`PyMuPDF>=1.24,<2`)** — extract supported vector paths from PDF drawings.
- **pyproj (`pyproj>=3.6,<4`)** — convert geographic coordinates (WGS84/EPSG:4326) to local projected metric CRS (currently UTM-based) for area/distance calculations.
- Python standard library `xml.etree.ElementTree` and `zipfile` — KML and KMZ parsing.
- **matplotlib (`matplotlib>=3.8,<4`)** — boundary/envelope preview diagrams.

## 5.3 Reports and exports
- **ReportLab (`reportlab>=4.0,<5`)** — PDF report and A3 comparison board generation.
- **python-pptx (`python-pptx>=0.6.23,<2`)** — editable PowerPoint report and A3 board generation.
- JSON — structured assessment export and JSON-based rule profiles.
- CSV — authority coverage matrix export.
- DXF — selected site boundary and building/basement envelope layers.

## 5.4 Network/location
- **Requests (`requests>=2.31,<3`)** — user-triggered Google Maps short-link expansion and public geocoding/source requests.
- **OpenStreetMap Nominatim** — address/reverse geocoding in current location module. The prototype caches results locally for 24 hours and throttles Nominatim requests. Respect the provider's published usage policy, required User-Agent and request limits. Treat geocoding as indicative location only, not property-boundary or statutory jurisdiction evidence.
- Official authority/Gazette/map websites are exposed as reference links. The prototype does not yet have universal authoritative point-query APIs for every authority.

## 5.5 Testing and launch
- **pytest (`pytest>=8,<10`)** — automated test suite.
- `run_siteiq.bat` — Windows local setup/launch script.
- `run_siteiq.sh` — macOS/Linux shell launch script.
- `requirements.txt` — current dependency constraints.

## 5.6 Current persistence and deployment state
- Rule profiles and registry are local JSON files.
- Authority coverage is a local CSV.
- Geocoding cache is local JSON under `data/geocode_cache/`.
- Spatial lookup layers are expected under `data/spatial/` (authority and land-use GeoJSON).
- No production SQL database, cloud deployment, authentication/role management, multi-user concurrency, API backend or audit service is implemented in the current prototype.
- The app is designed to run locally in a browser through Streamlit. A production multi-user deployment needs a separate architecture decision.

---

# 6. Current codebase structure (v0.4.7 ZIP)

The current ZIP expands to a folder named `SiteIQ_MVP_v0.4.7_GoogleMapsPriorityFix/`.

```text
SiteIQ_MVP_v0.4.7_GoogleMapsPriorityFix/
├── app.py
├── requirements.txt
├── run_siteiq.bat
├── run_siteiq.sh
├── README.md
├── START_HERE.md
├── RELEASE_NOTES.md
├── CHANGELOG.md
├── IMPLEMENTATION_PLAN.md
├── KARNATAKA_RULES_EXPANSION_PLAN.md
├── KML_LOCATION_CHECK.md
├── SOURCES.md
│
├── siteiq/
│   ├── __init__.py
│   ├── boundary.py
│   ├── engine.py
│   ├── exporters.py
│   ├── location.py
│   ├── location_ui.py
│   └── public_sources.py
│
├── rules/
│   ├── authority_registry.json
│   ├── authority_coverage_matrix.csv
│   ├── bengaluru_rmp2015_partial.json
│   ├── hoskote_lpa2031_candidate.json
│   ├── kanakapura_lpa2031_candidate.json
│   ├── nelamangala_lpa2031_candidate.json
│   ├── anekal_lpa2031_candidate.json
│   ├── NEW_AUTHORITY_RULE_PROFILE_TEMPLATE.json
│   └── candidate_profiles/
│       ├── bmrda_uniform_zoning_udd559_draft_2026.json
│       └── kanakapura_mp2031_review_candidate.json
│
├── data/
│   └── spatial/
│       └── README.md
│   # Runtime folders may also include geocode_cache/, uploads and optional GIS layers.
│
├── sample_data/
│   ├── illustrative_irregular_site.dxf
│   └── nandi_housing_test_case.json
│
├── sample_outputs/
│   ├── SiteIQ_Nandi_Assessment_v0.4.7.json
│   ├── SiteIQ_Nandi_Detailed_Report_v0.4.7.pdf
│   ├── SiteIQ_Nandi_Detailed_Report_v0.4.7.pptx
│   ├── SiteIQ_Nandi_Comparison_Board_A3_v0.4.7.pdf
│   ├── SiteIQ_Nandi_Comparison_Board_A3_v0.4.7.pptx
│   ├── SiteIQ_Hoskote_Profile_Check_v0.4.7.json
│   ├── SiteIQ_Hoskote_Profile_Check_v0.4.7_Summary.json
│   ├── SiteIQ_Hoskote_Profile_Check_v0.4.7.txt
│   └── SiteIQ_Boundary_Demo_Preview.png
│
├── tests/
│   ├── test_app_location_callback_wiring.py
│   ├── test_authority_coverage_registry.py
│   ├── test_boundary.py
│   ├── test_engine.py
│   ├── test_exporters.py
│   ├── test_location.py
│   ├── test_location_ui.py
│   └── test_multi_authority_profiles.py
│
├── create_boundary_demo.py
├── create_location_demo.py
└── create_sample_outputs.py
```

**Do not commit** Python virtual environments, `.pytest_cache`, `__pycache__`, temporary uploads, private/client site data, geocoding caches or local secrets. Add/update `.gitignore` before the first Git commit.

---

# 7. Existing module responsibilities

The current codebase is small and concentrated. The agent should understand these modules before refactoring.

| File | Current responsibility |
|---|---|
| `app.py` | Streamlit page, user inputs, stage order, callbacks, boundary import UI, rules/profile selection, scenarios, report invocation and downloads. |
| `siteiq/engine.py` | JSON rule loading, authority/profile selection, land-use categories, FAR matching, conditional paths, coverage, setback tables, basement setbacks, scenario calculations and report assembly. Core engine intentionally has no Streamlit dependency. |
| `siteiq/boundary.py` | DXF/KML/KMZ/vector-PDF import, candidate extraction, units/scale, geometry validation, edge lengths, setback envelope geometry, previews and DXF export. |
| `siteiq/location.py` | Coordinate parsing, Google Maps URL extraction/short-link expansion, Nominatim geocoding/reverse geocoding, local GeoJSON layer lookup, locality-based provisional authority suggestions and approval-route suggestions. |
| `siteiq/location_ui.py` | Streamlit-independent helper for applying location identification results to session state; must be called through safe callbacks. |
| `siteiq/public_sources.py` | Returns authority/locality-specific official source links for user review. It is a source-discovery helper, not a verified rule engine. |
| `siteiq/exporters.py` | Client-friendly detailed PDF, editable PPTX, A3 comparison PDF and editable A3 PPTX. |
| `rules/authority_registry.json` | Authority names/keys, current rule-profile links and profile status. |
| `rules/*.json` | Structured regulation profiles and source metadata. |
| `rules/authority_coverage_matrix.csv` | Authority source-review and implementation queue. |
| `tests/` | Regression tests for engine, geometry, location, UI callback wiring, rule registry and exporters. |

Keep the core calculation modules independent from Streamlit so they can be unit-tested and eventually called through an API.

---

# 8. Data model and rule-engine design expectations

The current profiles are JSON. Retain the readable, reviewable structure, but formalise and validate it as the library grows.

## 8.1 Recommended core entities

- **Authority:** legal authority key/name, jurisdiction type, notified boundary source/version, official website, parent/regional authority if applicable.
- **RuleProfile:** authority key, profile name/version, status, effective dates, source-quality level and category catalog.
- **RuleSource:** source ID, document title, notification/Government Order number, issue/publication date, effective date, URL, PDF/file name, page, clause/table, official/secondary classification, legal status and review notes.
- **LandUseCategory:** key/label, official aliases, permissible uses, FAR table reference, coverage table reference and relevant conditions.
- **FARRule:** method, plot-area bands, road-width bands, FAR values, inclusivity/exclusivity, min/max plot area, minimum road width, conditional paths, calculation-area basis, deductions/exemptions and source IDs.
- **SetbackRule:** height bands, plot-size bands, method (percentage/all-round/fixed/other), front/rear/side rules, stilt treatment, edge conditions and source IDs.
- **BasementRule:** area/height/number-of-basement conditions, building-setback relationship, independent minimum setbacks, flood/waterbody exclusions and source IDs.
- **SiteAssessment:** project input, selected location source, active boundary, jurisdiction/zone status, selected category, road width, approval route, rule version and assessment timestamp.
- **ScenarioOption:** height, floor count, stilt condition, footprint, front/rear/side/all-round setbacks, basement levels/setbacks, calculated envelopes and FAR comparison.
- **AssessmentResult:** raw inputs, rule matches, calculations, assumptions, warnings, citations, output paths and software/rule version.

## 8.2 FAR calculation trace

A user should be able to inspect:
- Which profile/category/table was selected.
- Why a conditional table was or was not selected (e.g. site area threshold and proposed-use text).
- Which plot-area band matched.
- Which road-width band matched.
- How multiple FAR constraints were combined (e.g. lower of two configured values where the source/table interpretation requires it).
- Whether the table uses gross site area or net area after reservations/exclusions.
- How FAR capacity was calculated.
- Which exact source clause/table/page supports each step.

## 8.3 Do not over-generalise regulatory tables

Do not assume every authority uses the same table structure. Build a small, explicit set of supported rule methods; add new methods only with examples and tests. If an authority uses a different structure, represent it specifically. Never map a table into a generic `FAR = f(road_width)` formula unless the source actually defines that relationship.

---

# 9. Current known limitations and open defects

The agent must read this section before changing code. These are known product risks and should be converted into tracked issues/tests.

## P0 — Google Maps short-link resolution and stale coordinate behaviour

The user has repeatedly supplied `maps.app.goo.gl` links, but the application screenshots continued to display an old/manual coordinate/address pair and a wrong/unspecific authority result. This remained a reported issue after releases that claimed to prioritise map links.

Current v0.4.7 code has `coordinates_from_map_url()` in `siteiq/location.py`, which:
- extracts common direct coordinate URL patterns (`!3d...!4d...`, `@lat,lon`, `q/query/ll/center` etc.);
- attempts to expand approved Google Maps/Google Earth hosts using `requests.get(..., allow_redirects=True)`;
- parses the final URL and limited response text.

This is not sufficient proof that all real `maps.app.goo.gl` links resolve. Reproduce the actual user link and implement a reliable, tested resolution strategy. Consider:
- redirects/host allowlists and multi-hop redirect handling;
- Google Maps destination HTML/metadata formats;
- explicit user-visible “map link resolved to X,Y” preview;
- failure handling that clears prior location/authority/zone/approval-route results;
- no stale address/coordinate fallback after an explicitly supplied map link fails;
- security limits (HTTPS, strict host allowlist, timeout, response-size limit, no arbitrary URL fetch / SSRF);
- no scraping that violates service terms; provide a clean manual coordinate fallback if Google does not expose a usable point.

**Known real test case from screenshots:**
- Address displayed: `Tumakuru, Tumkur taluk, Tumakuru, Karnataka, 572101, India`.
- Coordinates displayed: `13.3297678, 77.1121664`.
- Google short link shown: `https://maps.app.goo.gl/VGjypsrJo2TogXrF6`.
- The user expected a different target/site location and reported that SiteIQ still returned an unhelpful authority candidate. The link was not successfully proven to resolve to the intended target in the prior work.

The product must show exactly which source was used and the resolved destination before jurisdiction lookup.

## P0 — KML source/lookup/area synchronization

The user experienced address coordinates overriding the imported KML. Later changes allowed KML location handoff, but it must be regression-tested thoroughly.

The correct behaviour is:
- A selected KML feature can provide a location lookup anchor, including an open LineString if it is suitable only as a locator.
- An applied, valid parcel polygon is the source of truth for both jurisdiction spatial checks and parcel area.
- A location-only LineString must not silently become the area/FAR/setback boundary.
- When a new KML is uploaded, the UI must show “new boundary uploaded, not yet applied” until the user applies it.
- When there are multiple candidate geometries, the user must select the correct parcel feature.
- Clear stale location/authority/zone/route results when the active source changes or the resolution fails.
- Store the boundary file fingerprint, selected candidate ID, source filename, coordinate anchor, applied geometry and derived area in the assessment so the report can prove which geometry was used.

## P1 — Planning authority identification is still provisional without official planning-boundary layers

- Reverse geocoding/locality text can suggest a likely authority, but it cannot establish legal inclusion in a notified planning boundary.
- GBA ward/corporation KMLs are administrative context, not automatically planning authority boundaries.
- GBA/BDA/BMRDA/local planning area boundaries must be sourced and represented separately.
- A parcel near a boundary may overlap two authorities or be partially inside/outside. Do not use centroid-only checks as the only jurisdiction decision; implement whole-polygon intersection/coverage diagnostics and flag overlaps.
- For concave polygons the centroid can fall outside the parcel. Prefer a representative interior point for point-based lookups, while retaining centroid metadata.

## P1 — Karnataka rules coverage incomplete

Current v0.4.7 has selected/partial or provisional profiles only. It is not a complete Karnataka rule library. Provisional FAR candidates from secondary copies must not be represented as verified entitlements. See Section 4 and the existing coverage CSV.

## P1 — Irregular geometry / variable edge setbacks

- The engine can import and validate geometry and create preliminary setback envelopes.
- Complex concave geometries, different front/rear/side offsets, multiple road edges, corner plots, road-facing side edges and special edge rules need more independent validation.
- The front/rear/side designation must be explicit and tied to actual selected boundary edges.
- Test inward offsets that split, collapse or create invalid polygons.
- Basement envelopes must be calculated independently when the regulation differs from the above-ground building setback.

## P2 — Incomplete full-code coverage

The MVP does not comprehensively calculate every applicable planning, building, fire, parking, accessibility, environmental, service or NOC provision. Any missing provision must be shown as “not configured / requires review,” not silently ignored.

## P2 — Production readiness

The current prototype is local Streamlit with JSON/CSV storage. It has no production authentication, role-based permissions, database migrations, project sharing/version history, hosted service, centralized audit logs or admin rule-approval workflow. Do not market it as a multi-user production platform until these are implemented and tested.

---

# 10. Agent instructions: how to take over and iterate through the codebase

The agent must not rewrite the entire application blindly. Follow this order.

## Phase 0 — Inspect and baseline

1. Extract `SiteIQ_v047_GoogleMapsPriorityFix.zip` into a clean working folder.
2. Read this master brief, then read the existing `README.md`, `START_HERE.md`, `RELEASE_NOTES.md`, `CHANGELOG.md`, `SOURCES.md`, `KARNATAKA_RULES_EXPANSION_PLAN.md` and `KML_LOCATION_CHECK.md`.
3. Inspect the complete tree and all source modules listed in Section 7.
4. Create a baseline branch before changes.
5. Set up Python 3.10+ virtual environment and install `requirements.txt`.
6. Run the existing tests from the project root:

   ```bash
   python -m pytest -q
   ```

   Baseline verification performed while preparing this brief: **75 tests passed** in the v0.4.7 archive. Re-run locally and record the actual result in the engineering log.

7. Launch the actual Streamlit interface using `run_siteiq.bat` (Windows) or `run_siteiq.sh` (macOS/Linux). Test all key workflows in a browser. Do not assume unit tests prove the Streamlit UI works.
8. Generate the sample Nandi reports and inspect the PDF/PPTX/A3 board visually.
9. Record bugs before modifying code.

## Phase 1 — Fix location and source-of-truth behaviour first

1. Reproduce the known Google Maps short-link failure and build deterministic tests for full URLs, short URLs, direct coordinates, unsupported URLs, redirect failure, timeout and stale field mismatch.
2. Add a clear location-source preview and explicit resolved coordinates before authority lookup.
3. Ensure applied KML boundary takes precedence over any old map/address/coordinate fields.
4. Ensure map-link failure does not preserve a previous jurisdiction candidate.
5. Synchronize location lookup point, active boundary, area source and report metadata.
6. Add full-polygon authority boundary checks and overlap diagnostics; don't rely only on point centroid.
7. Test with `Test 02.kml`, `Test 03.kml`, the five OpenCity KML layers, and synthetic edge cases.

## Phase 2 — Make geometry dependable

1. Review `siteiq/boundary.py` and the current `calculate_setback_envelope()` algorithm.
2. Add a robust geometry test suite for convex, concave, narrow, self-intersecting, multi-part, corner and multi-road plots.
3. Implement edge-level setback assignment for front/rear/side/all-road-facing boundaries.
4. Implement option-specific building and basement setback calculations from the correct rule tables.
5. Display edge IDs and setback values in the diagram and CAD export.
6. Do not auto-fix source geometry without explicit confirmation and a saved original.
7. Keep calculation CRS and transformations recorded in output.

## Phase 3 — Build a verified Karnataka rules library

For each authority, perform this source workflow:
1. Verify legal authority identity and current notified planning-area boundary.
2. Obtain the currently approved Master Plan, Zonal Regulations/Building Bye-laws, official land-use map and every Gazette/Government Order amendment.
3. Confirm document legal status: draft/final, effective date, supersession, withdrawal/stay, authority-specific commencement.
4. Build a source index by category/table/clause/page.
5. Transcribe each rule into JSON without rounding away thresholds or changing inclusivity.
6. Have a second reviewer compare every row against the original document page/image.
7. Add exact rule tests for lower/upper band boundaries, gaps, overlaps, exceptions, and conditional routes.
8. Build at least one manually verified worked example for the authority.
9. Only then change the registry status to the level required for the profile to calculate.
10. Update the CSV, source notes, changelog and tests together.

Suggested sequencing:
- Hoskote — highest immediate priority because the user has tested Hoskote sites and expects a useful FAR result.
- Kanakapura — needed for the Attihalli test case; first resolve the location/boundary discrepancy.
- Nelamangala and Anekal — verify candidate profiles and resolve table/source conflicts.
- BIAAPA, Channapatna, Doddaballapura, Magadi, STRRPA and Ramanagara — verify individual operative plans; do not assume the March 2026 draft uniform rules are in force.
- BDA, Mysuru, Hubballi-Dharwad, Mangaluru, Belagavi, Kalaburagi, Davanagere, Tumakuru, Shivamogga, Ballari, Udupi and other authorities — research and configure individually.

## Phase 4 — Complete the feasibility calculation/report logic

1. Ensure the maximum FAR candidate is derived from the exact selected profile/category and all relevant conditions.
2. Show all FAR lookup bands and the limiting rule.
3. Keep base FAR, Premium FAR, TDR and assumed scenario FAR separate.
4. Make the FAR calculation denominator explicit (gross vs net calculation area).
5. For every option calculate the applicable building setbacks and basement setbacks separately.
6. Compare each option's footprint, gross floor area, achieved FAR, FAR capacity and excess/remaining area using clearly stated denominators.
7. Add parking, fire, accessibility and approval checks only where backed by configured sources and data. Clearly flag not-configured checks.

## Phase 5 — Improve reports and UI

1. Keep the workflow in the agreed order (location/jurisdiction → boundary/area → land-use category → road width → maximum FAR → options → comparative report).
2. Use client-friendly plain English on the first pages and retain technical sources/clauses in an appendix.
3. Make the A3 board resemble the user's Nandi Housing study: option panels, plan/envelope diagrams, key metrics, FAR comparison and “what this means” summary.
4. Include source status and software/rule version on every report.
5. Ensure PDF and PPTX figures/tables match the JSON calculation result.
6. Perform print checks (A3 landscape and A4 detailed report; greyscale legibility).

## Phase 6 — Production hardening

Recommended additions (do not introduce without a clear design decision):
- Typed data models and validation (e.g. Pydantic) for site assessments, geometry, profiles and source metadata.
- Separate API/service layer if the app becomes multi-user or integrates with CAD/GIS clients.
- Database (PostgreSQL/PostGIS) for projects, rule profiles, boundary features, audit history and multi-user access; current JSON/CSV is acceptable for prototype only.
- Authentication and role-based access: architect, reviewer, rules administrator.
- Rule profile approval workflow (draft → peer review → active → superseded).
- GIS import/admin console so normal architects never need to convert or upload GeoJSON.
- Background job only if file processing becomes heavy; keep the MVP simple until measured need exists.
- Structured logging, error reporting, backups and audit records.
- CI workflow (GitHub Actions) that installs dependencies and runs tests on each push/PR.
- Dependency pinning/lockfile and security review.

---

# 11. Required tests and acceptance criteria

A release is not ready merely because the Python files compile. The following criteria are required.

## 11.1 Location/jurisdiction
- A direct coordinate URL resolves to the exact coordinate.
- A supported full Google Maps URL resolves to the pin coordinate, not map viewport center where a pin coordinate exists.
- A supported `maps.app.goo.gl` short URL expands or returns an explicit failure; it never silently uses old coordinates.
- A failed lookup clears stale jurisdiction, zone and approval-route results.
- A newly applied KML boundary updates the lookup point and active boundary consistently.
- A multi-feature KML requires candidate selection.
- A mismatch between address, map link, manual coordinate and KML is visible and quantified.
- Authority identification distinguishes corporation/ward from planning authority.
- A polygon crossing or touching two planning areas is flagged for review.
- A zone is only marked verified when matched to an authoritative, current land-use source.

## 11.2 Boundary/geometry
- DXF closed polylines with known units produce expected metric area/perimeter.
- Unknown units require calibration.
- KML Polygon and closed LineString areas calculate correctly after projection.
- Open LineString can locate only; area calculation requires explicit close confirmation.
- PDF vector geometry requires scale calibration.
- Scanned PDF produces an honest unsupported/trace-first message.
- Self-intersection, duplicate points, zero area and invalid geometry are flagged.
- Irregular plot setbacks generate correct, valid, inspectable geometry.
- Front/rear/side edge choices are reflected in the right setback distances.
- Basement setbacks are independent where the rule says they differ.
- DXF export contains clear layers and units.

## 11.3 Regulatory rules
- Test every exact band boundary (`>`, `>=`, `<`, `<=`).
- Test no-match and multiple-match cases.
- Test minimum/maximum plot area and road width conditions.
- Test category/use conditional paths (including group housing where configured).
- Test gross/net area deductions and calculation bases.
- Draft-only profiles cannot return active statutory FAR.
- No authority falls back to Bengaluru FAR.
- Rule sources are included in result JSON and reports.
- Rule status and effective date are visible.

## 11.4 Scenario comparison
- Each option can select its own height, floor count, stilt condition, building setbacks, basement level and basement setbacks.
- Option 01/02/03 can have distinct setback rules and envelopes.
- FAR capacity uses the selected rule-derived benchmark, not a manual FAR unless explicitly shown as a what-if scenario.
- Gross floor area/achieved FAR uses a clear stated formula and denominator.
- Exceeding/remaining figures are signed and plain-language explained.

## 11.5 Export quality
- PDF and PPTX use the same calculation/result JSON.
- The A3 board includes all option summaries and readable geometry diagrams.
- No clipped text, overlapping tables, missing labels or empty diagrams.
- Sources, notes and rule status are legible.
- PDF and PPTX render correctly in independent viewers.

## 11.6 Release gate
- `python -m pytest -q` passes.
- Interactive Streamlit smoke test completed.
- At least one boundary import path tested with a real project file.
- At least one verified authority profile benchmarked against a manually checked calculation.
- Detailed PDF, editable PPTX and A3 board rendered and visually reviewed.
- CHANGELOG, README, source register and rule version updated.

---

# 12. UI/UX structure expected

The normal architect should not have to convert GIS files or understand GeoJSON.

Suggested primary workflow screens/sections:

1. **Project and site identification** — project name, map/address/coordinates, location lookup and result/source preview.
2. **Boundary import and validation** — upload file, choose boundary candidate, review geometry, confirm scale/closure, apply boundary and area.
3. **Regulatory land-use and road width** — choose category from active authority profile, proposed use, road width and approval route (suggested only until confirmed).
4. **Maximum FAR lookup** — show candidate FAR, matched bands, benchmark area, rule/source status and reasons.
5. **Design options** — add/remove options; height/floors/stilt/building setbacks/basement/footprint.
6. **Boundary/envelope preview** — site boundary, road edges, front/rear labels, option building envelope and basement envelope.
7. **Comparative analysis** — table/chart and a concise recommendation/constraints summary.
8. **Export** — detailed PDF, editable PowerPoint, A3 board, JSON and DXF.

Administrator-only pages (not normal architect flow):
- Manage authority boundary and land-use layers.
- Manage source documents and citations.
- Review/update rules profiles.
- Review authority coverage matrix.
- Approve/activate/supersede rule profiles.

---

# 13. GitHub repository and version control instructions

The agent must push the complete project to the newly created repository:

`https://github.com/Pritish3110/SiteIQ.git`

## 13.1 Repository setup

1. Create/confirm the GitHub repository `Pritish3110/SiteIQ` as an **empty repository** (do not initialise it with a separate README, licence or `.gitignore`, because the source ZIP already has a README and project files).
2. Extract the full v0.4.7 source ZIP into the repository working directory.
3. Review the existing `README.md`; do not append a duplicate title if the file already exists.
4. Create `.gitignore` before staging files.
5. Run tests and ensure there are no local caches, virtual environments, client-private drawings, API credentials or temporary outputs unintentionally staged.

## 13.2 Initial Git commands

The user requested the following initialisation sequence. The `echo` line is only appropriate for a blank folder without an existing README; this project already includes `README.md`, so do **not** append a second title unnecessarily.

```bash
# Only if README.md does not already exist:
echo "# SiteIQ" >> README.md

git init
git add .
git commit -m "Initial SiteIQ codebase import"
git branch -M main
git remote add origin https://github.com/Pritish3110/SiteIQ.git
git push -u origin main
```

The originally suggested `git add README.md` stages only the README. Use `git add .` (after checking `.gitignore` and reviewing `git status`) to stage the complete project.

If the remote already contains commits, do not force-push. Inspect the remote history, then merge/rebase or clone the remote and copy the project into it safely.

## 13.3 Minimum `.gitignore`

Include at least:

```gitignore
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.streamlit/secrets.toml
.env
.env.*
!.env.example
.DS_Store
Thumbs.db
*.log
# Runtime geocoding cache and private uploads
siteiq/data/geocode_cache/
data/geocode_cache/
uploads/
tmp/
temp/
# Local virtual environments / generated transient files
```

Do not ignore curated sample data, reviewed sample outputs or public/appropriately licensed regulation files intended to be versioned. Keep private client drawings/site data out of the public repository unless the owner explicitly authorises it.

## 13.4 Git workflow after initial push

- `main` should contain stable releases.
- Use feature branches such as `feature/google-maps-resolver`, `feature/karnataka-rules-hoskote`, `feature/irregular-edge-setbacks`.
- Commit small, reviewable changes with meaningful messages.
- Run tests before every push.
- Use Pull Requests for rule-profile changes and geometry/location changes.
- Require a second human review for regulatory transcriptions before activating a profile.
- Tag releases (e.g. `v0.4.8`, `v0.5.0`) and maintain `CHANGELOG.md`.
- Never force-push `main` to resolve a normal merge conflict.

---

# 14. Suggested roadmap

## P0 — Stabilise current workflow
- Fix and prove Google Maps short-link resolution.
- Make location source and selected coordinates visible before running jurisdiction lookup.
- Ensure KML boundary, location and area state cannot drift apart.
- Stop stale authority/zone/route results from surviving failed lookups.
- Test `Test 02.kml` and `Test 03.kml` and explain location differences to the user.

## P1 — Geometry reliability
- Implement and validate segment-specific irregular setbacks.
- Add full polygon vs authority-boundary intersection diagnostics.
- Improve CAD/PDF candidate handling and boundary selection.
- Add geometry QA visualisation and robust DXF output.

## P2 — Verified authority coverage
- Obtain current official Hoskote rules/boundary/zoning and validate the candidate profile.
- Resolve Kanakapura boundary/source mismatch and validate its operative rules.
- Validate Nelamangala and Anekal rules.
- Add remaining BMRDA-area authorities one at a time.
- Add BDA/Mysuru/Hubballi-Dharwad/Mangaluru/Tumakuru/etc. from their current operative rules.
- Do not activate draft UDD 559 uniform rules without final notification and authority-specific commencement evidence.

## P3 — Improved calculations and reports
- Complete parking, basement, fire, accessibility and services rule modules.
- Add more complete floor-area exclusions and schedule-based floor-area calculations.
- Improve client/architect report modes and A3 board diagrams.
- Add a rule/source update review dashboard.

## P4 — Production platform
- Database and multi-user project store.
- Authentication/roles.
- Admin rule approval/version workflow.
- Auditable assessments and report snapshots.
- Automated source review reminders and regression suite.
- Hosted deployment only after privacy/security, user access and support decisions are made.

---

# 15. Immediate instructions to the engineering agent

Start by doing the following, in order:

1. Extract and inspect `SiteIQ_v047_GoogleMapsPriorityFix.zip`.
2. Read all included docs and every module listed in Section 7.
3. Create/prepare the GitHub repo and push the unmodified baseline before major refactoring (after `.gitignore` and secret review).
4. Run the 75-test baseline and launch the app locally.
5. Reproduce the user's latest Google Maps short-link failure. Do not assume the current implementation works just because the README says the priority is correct.
6. Fix source-of-truth logic and add end-to-end location tests.
7. Use Test 02 and Test 03 KML files as regression fixtures. Their coordinate extents differ materially:
   - `Test 02.kml` vertices are around latitude 13.0719–13.0744, longitude 77.7819–77.7830 (Hoskote vicinity).
   - `Test 03.kml` vertices are around latitude 13.3289–13.3306, longitude 77.1113–77.1131 (Tumakuru vicinity). Do not treat Test 03 as a Hoskote site unless the user supplies a different file.
8. Add a repeatable source acquisition/review workflow for Hoskote and other Karnataka authorities. Keep draft, provisional and verified rules distinct.
9. Improve irregular-site segment-specific setback calculations and basement envelope calculations.
10. Preserve all current outputs and make sure PDF, PPTX, A3 board, JSON and DXF exports use the same assessment object.
11. Add UI smoke tests and visually review reports before tagging a release.

## Final product success definition

A normal architect should be able to:

1. Paste a Google Maps link or upload a survey/KML/DXF boundary.
2. See the precise location source and a plausible/verified authority result, with mismatch warnings if sources disagree.
3. Get the actual site area from the boundary.
4. Select the land-use category and enter the official road width.
5. See the maximum FAR candidate only when a unique, source-backed rule matches.
6. Compare building heights, setbacks and basement options on the actual irregular site.
7. See the FAR yield/headroom for each option against the rule-derived benchmark.
8. Export a polished, plain-English client report and an editable A3 comparison board, with a technical source appendix.

A regulatorily uncertain site should still generate a useful report—but the report must say exactly what is unknown and what must be confirmed. **SiteIQ must never manufacture certainty.**

---

# Appendix A — Project reference files discussed in the conversation

The following files were provided or generated during the project discussion and may be needed for the full engineering handover. They are not all bundled inside the v0.4.7 ZIP; locate/copy them into a well-organised `docs/reference/` or `data/reference/` directory only after checking source provenance and permission to version them.

## Regulations/handbook materials
- `BBMP 2015.pdf`
- `Amendment 01.pdf` through `Amendment 10.pdf`
- `Karnataka Fire protection.pdf`
- `Bengaluru_Architect_Regulatory_Handbook_v1.2_Oct2026.pptx`
- `Bengaluru_Architect_Regulatory_Handbook_v1.2_Oct2026.pdf`
- `Bengaluru_Architect_Regulatory_Handbook_v1.2_A4_Greyscale_Print.pdf`
- `Bengaluru_Architect_Regulatory_Handbook_Brief_Notes.docx`

## Site/geometry test materials
- `Nandi Housing_Feasibility Model.pdf`
- `Nandi_Housing_Feasibility_Board_Editable_R01.pdf`
- `Nandi_Housing_Feasibility_Board_Editable.pptx`
- `Test 02.kml`
- `Test 03.kml`
- Five OpenCity KML files listed in Section 4.4.
- `SiteIQ_Illustrative_Irregular_Site.dxf`

## Sample outputs and prototypes
- Earlier SiteIQ ZIPs: v0.1 through v0.4.6 (historical only; the v0.4.7 ZIP is the current baseline for this handover).
- Nandi sample PDF/PPTX/A3 comparison board.
- Boundary engine demo PDF/PPTX/DXF preview.

Keep historic ZIPs for reference if needed, but do not combine multiple version folders into the active codebase. The current v0.4.7 package is the source-of-truth baseline unless a newer source bundle is explicitly supplied.

---

**End of handover brief.**
