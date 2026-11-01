# SiteIQ implementation plan

## Delivered through v0.4.7
1. Ordered workflow: identify jurisdiction → import/calculate site boundary area → choose land-use category from the configured profile → enter road width → identify maximum FAR candidate → compare height/setback/basement options.
2. Category-specific FAR methods with traceable source data. For Table 10-type profiles, compare road-width FAR and plot-area FAR cap and use the lower applicable figure where supported by the source provisions; gaps are flagged.
3. Separate building and basement setback calculation for each height/stilt/basement option.
4. Detailed client PDF / PowerPoint and one-page A3 comparison board PDF / editable PPTX.
5. Regression tests for FAR calculation and non-matching bands, set-back/basement scenarios, boundary functions, report exports and automatic public-source selection.
6. Removed GIS upload from the normal workflow; added context-sensitive official source links and a Kanakapura candidate profile. Exact legal boundary/zone remains pending when public sources do not expose a verified point-query layer.

## Next recommended phase
- Expand from selected Bengaluru rules to a source-reviewed rule profile for each planning authority. Include final Gazette version, clause, effective date, bands, exclusions and independent review.
- Negotiate/identify public services with suitable reuse terms for official authority and land-use polygons; integrate queryable map APIs where available. Do not download or reuse source datasets with incompatible terms.
- Improve edge classification and geometry engine for complex concave parcels and side-specific setbacks; regression-test envelopes against CAD examples.
- Add parking-count calculations from unit schedules and relevant authority-specific tables.
- Add dimensioned option summaries, optional basement plate/levels and explicit inclusion/exclusion accounting for statutory FAR.
- Test Streamlit end-to-end on Windows and add a small suite of real but anonymised survey examples before production use.

## Non-goals until verified
- No general legal interpretation by LLM alone.
- No defaulting to Bengaluru rules when another authority is selected.
- No guessing an FAR when category, band or source is ambiguous.
- No treating geometry envelopes as sanctioned building footprints.


## v0.4.1 maintenance update
Location-identification prefills now execute in a Streamlit button callback. The area passed to route suggestions uses the actual site-area widget key or active boundary-derived area.


## v0.4.4 — Karnataka source coverage work queue
- Added the March 2026 draft UDD 559 BMR 2025(E) reference as a draft-only research source for BMRDA local planning areas; it is not used in calculations.
- Added registry entries and next actions for BMRDA local planning authorities and an initial statewide discovery queue. This is not a complete inventory.
- Added a Kanakapura Master Plan 2031 review candidate with no active FAR tables. The coordinates used in the recent Attihalli test appear outside the longitude range quoted by a secondary plan copy, so the authority suggestion must be verified against an official boundary before rules are applied.
- Added a coverage matrix CSV and UI expander for tracking profile readiness.
- Next: secure and verify official current plans/notifications, encode one authority profile at a time, and require regression-tested activation.


## v0.4.7 — First rule profiles beyond Bengaluru RMP
Delivered: provisional Hoskote, Kanakapura, Nelamangala and Anekal LPA Master Plan 2031 candidate profiles; selected FAR/setback tables; conditional group-housing routes; source-quality warnings; net FAR denominator tracking; separate optional Premium FAR/TDR scenario; refreshed report provenance.

## Next implementation phases
1. **Authority validation:** obtain authority-issued current plan/regulations and all amendments for the four new LPAs. Verify legal commencement and exact table wording before upgrading candidate profiles.
2. **Official jurisdiction/zone data:** install versioned authoritative planning-area and land-use polygon layers or use supported official point-query services. Avoid substituting corporation/ward maps for planning-area/land-use boundaries.
3. **Broaden profiles:** complete BMRDA-area authorities one by one, beginning with those that have clear final rules and official source documents; add Mysuru, Hubballi-Dharwad and other statewide authorities only after source review.
4. **Model more conditions:** group housing/development plan thresholds, net site-area deductions/reservations, parking, height definitions, fire triggers, basements, and occupancy/category exceptions.
5. **Regression validation:** build reviewed benchmark sites for every rule profile and compare outputs against an independent manual calculation before enabling that profile as verified.
6. **Data governance:** store source URL, title, Gazette date, commencement, amendment chain, page/table, reviewer, last review date and profile status for every rule path.
