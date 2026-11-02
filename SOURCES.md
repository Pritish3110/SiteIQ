# SiteIQ v0.4.7 — Source provenance and public-map lookup notes

## Bengaluru / Greater Bengaluru partial profile

1. **Base RMP 2015 Table 10 - Residential (Main)**
   - User-provided document: `BBMP 2015.pdf`, PDF page 28 / printed page 27.
   - Clause: Chapter 4, Regulation 4.1.2, Table 10.
   - Official starting point: [BDA Master Plan](https://eng.bdabangalore.org/masterplan.html).
   - Encoding policy: the configured category lookup calculates the plot-area FAR cap and road-width FAR candidate independently, then uses the lower applicable value under the configured reading of Regulation 3.4(iii)-(iv). It does not interpolate across missing bands. The result is a candidate and needs current jurisdiction/zone/rule verification.

2. **Setback Tables 8 and 9**
   - User-provided document: `Amendment 01.pdf`, PDF pages 2-3, headed Government of Karnataka, Notification No. UDD 235 MNJ 2025(E), dated 05.01.2026.
   - Clauses: Chapter 3, Regulation 3.1 and Tables 8 / 9.
   - Official portal entry point: [Greater Bengaluru Authority](https://gba.karnataka.gov.in/).
   - Encoding policy: selected values are implemented; exact applicability and current supersession still require professional review.

3. **Single Plot Approval / Chapter 6-A**
   - User-provided document: `Amendment 05.pdf`, PDF pages 2-5, Notification No. UDD 272 MNJ 2025(E), dated 16.07.2025.
   - Clauses: updated definitions, Regulation 3.9 basement setback and Chapter 6-A.
   - Official starting point: [BDA Acts, Rules and Amendments](https://eng.bdabangalore.org/acts-rules-amendments.html).
   - Encoding policy: only the 2,000-4,000 m2 potential park/payment band is flagged. The software does not assume the approval route or compute guidance value charges.

4. **Fire high-rise threshold**
   - User-provided document: `Amendment 03.pdf`, PDF pages 1-3, Karnataka Fire Force (Amendment) Act, 2023, Karnataka Act No. 24 of 2023.
   - Clause: Section 13 amendment; high-rise defined as 21 m or above irrespective of occupancy.
   - Official law repository entry point: [India Code](https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_587_000010_196442_1551090039403&filename=42_of_1964_%28e%29.pdf&type=actfile).
   - Encoding policy: height threshold flag only; not a complete fire-safety code engine.

## Authorities in registry only (no automated rules)

- BDA Local Planning Area
- BMRDA regional planning area
- Mysuru Development Authority
- Hubballi-Dharwad Urban Development Authority
- Planning Authority Kanakapura (candidate; no configured FAR/setback profile)
- Other Karnataka planning authorities

Each requires exact boundary/jurisdiction validation and separate verification of the current, final master plan and amendments before any rules are encoded. This explicit lack of configuration is a feature, not a missing calculation: it prevents accidental reuse of another authority's standards.


## Geometry engine references
- DXF import: `ezdxf` reads selected closed polyline entities; `$INSUNITS` is used when present.
- GIS coordinates: KML/KMZ longitude/latitude are projected with `pyproj` to a local UTM coordinate system so distances/areas can be computed in metres.
- Geometry validation and offsets: Shapely/GEOS polygons; uniform setbacks use inward buffer. Unequal setbacks use edge-strips and are marked approximate near complex concave corners.
- PDF vector paths: PyMuPDF drawing paths. The importer does not trace scanned/raster imagery and requires user scale calibration.
These are implementation mechanics, not official regulatory sources. The geometry should be checked against an authenticated survey and applicable authority regulations.


## Location and automatic public-source lookup (v0.4.4)
- **Coordinate parsing:** coordinates embedded in common Google Maps URL formats; redirect expansion for short links on an explicit user action.
- **Address geocoding:** OpenStreetMap Nominatim (`https://nominatim.openstreetmap.org/`) for a single, user-triggered location lookup. Results are cached locally for 24 hours. A geocoder is not a cadastral or regulatory source.
- **Automatic official-source navigation:** location labels are used to surface relevant official pages, including the [GBA GIS Viewer](https://bbmp.gov.in/gisviewer/), [GBA portal](https://gba.karnataka.gov.in/), [BDA Master Plan portal](https://eng.bdabangalore.org/masterplan.html), and the [official Kanakapura Planning Authority directory](https://bengalurusouth.nic.in/en/divisions/planning-authority/).
- **Authority candidate matching:** Bengaluru, Mysuru and Hubballi-Dharwad labels produce provisional candidates. Kanakapura labels now suggest Planning Authority Kanakapura as a candidate, not a verified boundary match. A taluk/city label cannot prove a parcel's planning jurisdiction.
- **Exact polygon lookup:** only performed when a valid, provenance-bearing authority or land-use polygon layer has already been installed by an administrator. Most authority pages are interactive viewers or static PDF map catalogues, not verified public point-query APIs. SiteIQ does not pretend a link is a polygon match.
- **No automatic KGIS data ingestion:** the official [K-GIS/KSRSAC downloads page](https://kgis.ksrsac.in/kgis/downloads.aspx) states that its spatial data are representational, not for legal use, and includes commercial-use restrictions. This release does not download, bundle or process those layers for SiteIQ results. Obtain explicit permission or use a source with suitable terms before any commercial integration.
- The normal architect workflow no longer asks for GIS uploads. Optional local layer maintenance is retained under a sidebar Administrator tools expander, but remains a specialist/administrative function.


## v0.4.0 FAR benchmark workflow
- **Input order:** identify jurisdiction, import/validate boundary area, select the regulatory land-use category from the configured profile, enter the road width, run the maximum-FAR lookup, then compare design options.
- **Area + road rules:** for `area_cap_and_road_width`, area and road rows are matched separately and the lower value is used only when each produces exactly one configured band. The returned `candidate_match_requires_verification` status is intentionally not labelled an approved entitlement.
- **Other rule methods:** `road_width`, `plot_area`, `fixed`, `inherit_surrounding_zone`, and `special_no_generic_far` are declared per category in `rules/bengaluru_rmp2015_partial.json`.
- **No implicit jurisdiction fallback:** authority profiles without configured rules return `not_configured` rather than borrowing Bengaluru values.
- **Option comparison:** every option receives its own building setbacks, stilt interpretation, basement levels/setbacks and achieved gross floor-area proxy. Option floor area is footprint × above-ground floor count; statutory exclusions are not modelled.


## New Karnataka coverage research leads (2026-10-16)
- Karnataka Town and Country Planning Act, 1961, India Code: https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_402_00001_11_1552283484255&filename=11_of_1963.pdf&type=actfile — official legal framework.
- UDD 559 BMR 2025(E), dated 2026-03-24, Draft Uniform Zonal Regulations for BMRDA LPA master plans: https://policyindex.ai/in/gazette/zonal-regulations-for-master-plans-of-different-lpas-within-bmrda-and-it-is-required-to-regulate-the-lpas-within-bmrda-with-uniform-zonal-regulations-to-avoid-confusions-while-hr5z5g — secondary Gazette viewer; draft-only, not enabled in calculations.
- Kanakapura LPA Master Plan 2031 Final Report/Zoning Regulations: https://www.scribd.com/document/403292547/Kanakapura-LPA-Final-Report-pdf — secondary copy; operative status and amendments not verified.
- Kanakapura LPA Master Plan 2031 zoning regulations copy hosted by NGT: https://www.greentribunal.gov.in/sites/default/files/news_updates/3_15.pdf — supporting copy, not treated as an authoritative consolidated current version.
- Planning Authority Kanakapura official district directory: https://bengalurusouth.nic.in/en/whoswho/nagaratna/ — contact/authority reference only.
- The coordinate 12.511506, 77.323792 used in a recent test appears west of the longitude range stated in the secondary Kanakapura LPA Master Plan copy (77°31′E–77°41′E); verify against the current official polygon before assigning jurisdiction.


## v0.4.7 multi-authority candidate profiles

The following rule profiles were added for early feasibility candidate lookup. They are transcriptions from secondary copies of LPA Master Plan 2031 zoning regulations and are **not** verified consolidated current legal codes. The profile files preserve source URLs, table/clause names, page references where available, and a persistent `secondary_copy_pending_official_validation` quality flag.

- **Hoskote LPA Master Plan 2031** — Table 4 (general FAR by road width), Table 3 (>10 m height setbacks), Table 5 (group housing), plus conditional group-housing reservation/area-basis notes. Secondary copy: https://www.scribd.com/document/680458988/Zonal-Regulations-of-Hoskote-Local-Planning-Area
- **Kanakapura LPA Master Plan 2031** — Table 4, Table 3, Table 6 group housing and reservation/area-basis notes. Secondary copy: https://www.scribd.com/document/403292547/Kanakapura-LPA-Final-Report-pdf. A copy hosted by the National Green Tribunal is retained as supporting reference, not proof of current operative law: https://www.greentribunal.gov.in/sites/default/files/news_updates/3_15.pdf
- **Nelamangala LPA Master Plan 2031** — general FAR, >10 m height setbacks, group-housing and selected industrial table candidates. The profile stores source pointers and conditions.
  - Additional official-domain source lead: [Nelamangala Planning Authority-hosted PDF referencing the Approved Master Plan 2031](https://npa.karnataka.gov.in/uploads/media_to_upload1753705289.pdf). It is a useful authority-issued starting point, but it has not been verified as a complete current zoning/FAR tables document and does not validate the secondary-source transcriptions used in this MVP.
- **Anekal LPA Master Plan 2031** — general FAR and height setback candidate table. The group-housing FAR path remains disabled because the available secondary copies conflict. Candidate PDF reference: https://www.scribd.com/document/525485934/Anekal-LPA-Master-Plan-2031-Vol-III-Zoning-Regulations
- **Uniform Zonal Regulations draft for LPAs within BMRDA**, Notification UDD 559 BMR 2025(E), dated 24 March 2026 — draft only; it is not used for FAR calculations in this release. Final notification and authority-specific commencement must be established before activation. Secondary mirror: https://policyindex.ai/in/gazette/zonal-regulations-for-master-plans-of-different-lpas-within-bmrda-and-it-is-required-to-regulate-the-lpas-within-bmrda-with-uniform-zonal-regulations-to-avoid-confusions-while-hr5z5g
- **Premium FAR/TDR optional scenario** — current notifications and Karnataka High Court judgment are recorded in relevant LPA profiles. This scenario is only a ceiling candidate and does not calculate charges, exact Table 27 mix or authority eligibility: https://indiankanoon.org/doc/91467302/

### Source-quality controls
- These profiles must remain visibly provisional until matched to authority-issued current approvals/Gazette notifications and amendments.
- Do not convert the March 2026 draft uniform rules into operative calculations without final notification and commencement confirmation for the exact authority.
- The automatic authority label is still a candidate unless an authoritative current planning boundary or formal parcel confirmation is available.
- The official land-use category must come from the notified map or equivalent authoritative determination. The user-selected regulatory category used in the rule lookup is distinct from a map-verified land-use zone.

## Additional statewide rules research lead — UDD 17 TTP 2025(E), 22 May 2026
- Gazette text mirror: https://policyindex.ai/in/gazette/amendment-to-zonal-regulations-of-all-approved-master-plans-of-the-local-planning-areas-except-the-master-plans-within-bengaluru-metropolitan-region-including-gba-bda-and-all-13e7fq
- The notification is published as a final amendment effective on Gazette publication for approved Master Plans in local planning areas **excluding** the Bengaluru Metropolitan Region (including GBA, BDA and all planning authorities within BMR) and the Mangaluru Local Planning Area.
- It standardises land-use-zone classifications and includes selected rules/tables for Industrial (General) and Commercial buildings in industrial areas, flatted factories, industry-linked affordable housing, buffers and associated matters. The table text does **not** establish a single universal residential FAR table for all non-BMR Karnataka authorities.
- SiteIQ records this as a cross-authority source lead. No generic statewide residential FAR has been inferred from it. A parcel still needs the correct authority/approved Master Plan and land-use category; only exact tables that match the notification and applicable use/pathway should be encoded.
- Source basis: notification No. UDD 17 TTP 2025(E), dated 22.05.2026; the available web copy displays the Gazette transcript but its PDF endpoint did not resolve in the targeted retrieval, so obtain the Gazette PDF directly for rule-by-rule encoding.


## Sources read directly on 2 November 2026
Only the items below were read from the document itself for this release. Everything else in this file remains as previously recorded.

| Document | Used for | Checked |
|---|---|---|
| [RMP 2015 Vol. III, Zoning of Land Use and Regulations](https://data.opencity.in/dataset/bengaluru-masterplan-zoning-regulations-2015) | Tables 10 and 12 to 19, Table 23 parking, stilt and drain definitions, Regulation 3.9, Chapter 7 | FAR tables match the profile. Public copy hosted by OpenCity |
| [UDD 235 MNJ 2025(E), 5 January 2026](https://data.opencity.in/dataset/greater-bengaluru-amendment-regulations-2025) | Tables 8 and 16, Table 9 notes, basement and ramp rules, Table 10 notes (b) and (c) | Scanned pages 2 to 6 read by eye. Pages 1 and 7 not reviewed |
| [UDD 468 MNJ 2025(E), 15 October 2025](https://data.opencity.in/dataset/bengaluru-notification-of-drains-buffer-area-specifications-2025) | Drain buffers 15/10/5 m from the edge; lake buffer deferred to the KTCDA Act | Gazette copy read in full. Later orders or litigation not checked |
| [Karnataka Fire Force ordinance 2023](https://prsindia.org/files/bills_acts/bills_states/karnataka/2023/Ord01of2023Karnataka.pdf) | 21 m high-rise and NOC trigger | From search summary of the text |
| [NBC 2016 Part 4](https://nmcnagpur.gov.in/assets/300/2025/03/mediafiles/NBC2016-Part-IV.pdf) | Clause 2.38, high-rise from 15 m | Read directly; licensed BIS text, so not stored in this repo |

**Planning authority plans, read from each authority's website:** [Hoskote](https://hoskote.tpa.gov.in/sites/hoskote.tpa.gov.in/files/HOSKOTE_ZR%20REPORT_-2031_finalsigned.pdf), [Kanakapura](https://kanakapura.tpa.gov.in/sites/kanakapura.tpa.gov.in/files/Zoning%20Regulations-Final.pdf), [Nelamangala](https://nelamangala.tpa.gov.in/sites/nelamangala.tpa.gov.in/files/1%20NPA_ZONING_REGULATION_2031.pdf) and [Anekal](https://anekal.tpa.gov.in/sites/anekal.tpa.gov.in/files/Zonal%20Regulations.pdf). Tables 2, 3, 4 and the group-housing table were compared with the profiles. This corrected the Hoskote industrial table, resolved the Anekal group-housing table, and added low-rise setbacks and apartment rules. Later amendments were not checked.

**Open conflicts:** Hoskote's site hosts two copies. The signed final allows group housing from a 9 m road at FAR 1.5, and the other requires 12 m; SiteIQ keeps 12 m. The Anekal text does not say FAR uses net area, so SiteIQ uses gross area and flags it.

**Also encoded from these plans:** IT/BT and industrial tables with their setbacks, Hoskote Table 6B, basement limits and setbacks, parking, electric line clearances, building separation and the accessibility trigger. Parking and clearance figures are as printed and need confirming with the agency.

**Lake and drain distances:** these plans print 30 m or 10 m from lakes and 9 m or 3 m from drains. UDD 468 applies "irrespective of anything contained in the zonal regulations" in BMR planning areas, so SiteIQ follows UDD 468.

**Added as a FAR or a check:** flatted factories, Hoskote integrated township (Table 7), the rainwater trigger and the attached-housing limits.

**Not encoded:** solar and rainwater sizing, attached-housing layout checks, township eligibility, and detailed accessibility design. No official planning-boundary or land-use GIS layer was found. The BDA site refused connections.

**Taken from secondary sources only:** the EIA 20,000 m² trigger and the RERA 500 m² and 8-unit limits. Both checks say so and ask you to confirm.
