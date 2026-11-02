# SiteIQ Karnataka Rules Expansion — v0.4.7 multi-authority candidate profiles

## Why this exists

Karnataka does not have one universal FAR/setback table for every location. Under the Karnataka Town and Country Planning Act, the Master Plan and associated zoning regulations define zone-specific development rules for each planning area. SiteIQ therefore needs an authority-specific, versioned rules catalogue rather than a single statewide FAR table.

## What this release does

- Expands the authority registry with the authorities listed in the 24 March 2026 draft Uniform Zonal Regulations for BMRDA LPAs, plus a non-exhaustive statewide discovery queue.
- Adds a downloadable/inspectable coverage matrix in `rules/authority_coverage_matrix.csv`.
- Records the UDD 559 BMR 2025(E) uniform-zoning proposal as **DRAFT ONLY**. The draft states it commences only after a final notification by the individual authority. It is not enabled for FAR calculations.
- Records the Kanakapura LPA Master Plan 2031 source as a candidate for review only; no Kanakapura FAR tables are active.
- Adds a jurisdiction mismatch warning for the Attihalli test coordinates. The secondary copy's reported longitude range does not appear to include the coordinate currently entered in SiteIQ. This is a red flag, not a conclusive jurisdiction finding; authoritative boundary verification is required.

## What must be completed before an authority can return an FAR result

1. **Identity and boundary:** establish the current legal planning authority and the parcel's inclusion in its notified area, using a current boundary and the site survey/parcel identity.
2. **Operative rule set:** collect the approved Master Plan, zoning regulations, building bye-laws where applicable, and every later Gazette/Government Order affecting FAR, setback, coverage, height, basements, parking, approval routes and special controls.
3. **Legal sequence:** record whether each document is final, draft, withdrawn, superseded, effective, stayed or pending commencement. Do not assume publication of a draft means it is in force.
4. **Structured encoding:** for each land-use category, encode all FAR bands with exact inequalities, plot-area and road-width conditions, occupancy/development-plan route, exclusions, caveats, premium FAR/TDR, and source clause/page.
5. **Independent review:** review the transcription and interpretation against original source pages. At least two boundary/band edge cases and one worked example should be tested per table.
6. **Activation gate:** `source_status` in each profile controls this. Draft, superseded, withdrawn and unrecorded statuses cannot calculate. Secondary-source and pending-review profiles can give a provisional FAR, but the study can never reach "Ready for review" until the profile is `verified_operative`.
7. **Update monitoring:** monitor Gazette updates and authority pages; when a later amendment is found, flag the relevant profile for review rather than silently overwriting history.

## Suggested coverage order

### Wave 1 — Bengaluru Metropolitan Region

Begin with the BMRDA-area LPAs named in the UDD 559 BMR 2025(E) draft: Anekal, BIAAPA, Channapatna, Doddaballapura, Hoskote, Kanakapura, Magadi, Nelamangala, STRRPA, the draft's Greater Bengaluru Development Authority designation, and Ramanagara UDA. The draft is a discovery/normalisation aid only until the final notification and individual commencement are verified. Keep the currently operative approved plan as the controlling source in the meantime.

### Wave 2 — other major urban-development/planning areas

Build verified profiles for Mysuru, Mangaluru, Hubballi-Dharwad, Belagavi, Kalaburagi, Davanagere, Tumakuru, Shivamogga, Ballari and other confirmed authorities. This is a seed queue, not a complete statewide list; verify each legal name and boundary against official records before activating it.

### Wave 3 — remaining planning authorities and local areas

Use a complete official authority inventory from the Directorate/Department of Town and Country Planning and Urban Development Department. For areas outside an Urban Development Authority or LPA, determine the applicable local authority, rules and approval route instead of defaulting to the nearest city profile.

## Important Kanakapura site finding

SiteIQ's reverse geocoder labels the test address as Attihalli, Kanakapura Taluk and therefore suggests Kanakapura provisionally. A secondary copy of the Kanakapura LPA Master Plan 2031 describes the LPA between coordinate extents including approximately 77°31′E to 77°41′E. The test point currently entered is longitude 77.323792°E, west of that stated range. This discrepancy must be resolved against a current, official notified boundary; do not activate Kanakapura regulations solely based on the locality text.

## Sources / research leads

- Karnataka Town and Country Planning Act, 1961 (India Code): https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_402_00001_11_1552283484255&filename=11_of_1963.pdf&type=actfile
- Draft UDD 559 BMR 2025(E), 24 March 2026 (secondary Gazette viewer): https://policyindex.ai/in/gazette/zonal-regulations-for-master-plans-of-different-lpas-within-bmrda-and-it-is-required-to-regulate-the-lpas-within-bmrda-with-uniform-zonal-regulations-to-avoid-confusions-while-hr5z5g
- Kanakapura LPA Master Plan 2031 Final Report/Zoning Regulations, secondary copy: https://www.scribd.com/document/403292547/Kanakapura-LPA-Final-Report-pdf
- Kanakapura LPA Master Plan 2031 zoning copy hosted by NGT: https://www.greentribunal.gov.in/sites/default/files/news_updates/3_15.pdf
- Planning Authority Kanakapura district directory: https://bengalurusouth.nic.in/en/whoswho/nagaratna/
- Official BDA Master Plan resources: https://eng.bdabangalore.org/masterplan.html
- Official Greater Bengaluru Authority portal: https://gba.karnataka.gov.in/

**This is a coverage-management artifact, not an operative ruleset. It intentionally contains no new active FAR values.**


## Update: v0.4.7 implemented
Four provisional Master Plan 2031 candidate profiles are now connected to the FAR engine: Hoskote, Kanakapura, Nelamangala and Anekal. Hoskote/Kanakapura/Nelamangala have configured general FAR and conditional group-housing paths; Anekal group-housing is deliberately unresolved pending reconciliation of conflicting source copies. All are visibly marked as secondary-source candidates, not verified operative laws.

Current verification priority:
1. Obtain the current authority-issued approved zoning regulations and amendment notifications for Hoskote.
2. Check final notification status and current FAR/setback tables with Kanakapura, Nelamangala and Anekal authorities.
3. Resolve conflicts in group-housing thresholds and reservation/net-area treatment before promoting any path.
4. Add official planning-area boundary and notified land-use data so SiteIQ can verify jurisdiction and land use spatially.
5. Expand to other LPAs only from their operative rule documents; the March 2026 uniform zoning proposal remains draft-only until final notification/commencement is proved.


## Additional research result: common non-BMR amendment (22 May 2026)
Notification UDD 17 TTP 2025(E) is a final notification for amendments to approved Master Plans in local planning areas outside BMR (including GBA/BDA and all BMR authorities) and outside Mangaluru LPA. The available Gazette transcript standardises land-use categories and includes selected industrial/commercial-in-industrial-area, flatted-factory, affordable-housing and buffer provisions. It is not a universal residential FAR schedule. SiteIQ records the reference in the registry but continues to require each authority's underlying approved plan and operative category/pathway before calculating ordinary residential FAR. The Gazette PDF should be obtained directly for table-by-table verification before coding the special use tables.
