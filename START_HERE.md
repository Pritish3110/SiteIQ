# SiteIQ v0.4.7 — Start here

## 1. Run the app on Windows
1. Extract the full ZIP to a local folder.
2. Install Python 3.10 or newer and enable **Add Python to PATH**.
3. Double-click `run_siteiq.bat`.
4. The launcher creates a virtual environment, installs `requirements.txt`, and starts the Streamlit app in your browser. Internet is required for first-time package installation and geocoding.

## 2. Recommended workflow
1. Enter the project/site details and paste a Google Maps link, address or coordinates.
2. Enter the address/map link if available. If you already have a KML/KMZ, upload it in Step 2 first; do not rely on the first address-only result for the parcel's authority.
3. After upload, a KML with exactly one feature is used automatically for the location lookup. If the file contains multiple features, select the correct one in Step 2 and click **Use selected KML location for authority lookup**. This refreshes the point-based authority/context lookup even if the path is open. It does not change the site area.
4. Validate the boundary and click **Apply boundary and derived area**. The applied boundary becomes the location source of truth for subsequent lookups, and its calculated area is used when selected. If the address point is far away, SiteIQ warns you.
5. Select the applicable rules profile and a regulatory land-use category. The official map zone and selected regulation category are separate fields; do not use a guessed zone.
6. Enter the legally recognised abutting road width. SiteIQ matches an exact configured table path; it does not interpolate a missing row.
7. Review the FAR candidate, source quality, area calculation basis and all conditions. For provisional profiles, obtain the official rules before using the result for design freeze.
8. Compare option-specific heights, floors, building setbacks, stilt condition, basement levels/setbacks and footprints.
9. Export the detailed PDF, editable PowerPoint, A3 board, JSON assessment and DXF envelopes as needed.


## KML location-vs-area reminder
- The **Use selected KML location for authority lookup** button uses the selected KML feature's geographic anchor to update the location query. This may work for an open LineString because it is only a search point.
- This location-only action does **not** validate or apply the legal parcel area. For area/FAR/setback calculations, use **Apply boundary and derived area** after selecting/confirming a valid parcel geometry.
- If a newly uploaded KML is not applied, SiteIQ displays a warning that the location or area may still refer to an older input. Do not export a final report until the active boundary and location source refer to the same site.

## 3. Rule profile coverage in this release
- **Bengaluru / Greater Bengaluru RMP 2015:** partial profile based on selected provisions from supplied regulations/amendments.
- **Hoskote, Kanakapura, Nelamangala:** provisional FAR/setback candidates transcribed from secondary copies of respective Master Plan 2031 zoning regulations. Their latest operative version and amendments have not been independently confirmed with the authorities.
- **Anekal:** selected general FAR/setback candidates; the group-housing FAR path is deliberately unresolved due to conflicting secondary copies.
- **Other Karnataka authorities:** registry entries only until their applicable approved Master Plan/zoning regulations and amendments are source-reviewed and tested.

The UDD 559 BMR 2025(E) uniform-zoning document dated 24 March 2026 is draft-only in SiteIQ. It must not be used as operative law unless final notification and authority-specific commencement are verified.

## 4. What provisional FAR means
A result from a provisional profile means the table was transcribed from a secondary copy of a Master Plan/zonal regulation. The profile can calculate a useful **candidate** to help with early feasibility, but the result is not a legal entitlement. Confirm:
- exact planning authority and notified boundary;
- official land-use zone and permissible use;
- current approved plan and all amendments;
- official road right-of-way/width;
- FAR table conditions, net/gross calculation basis and exclusions;
- development-plan/group-housing thresholds and reservation requirements;
- other site-specific constraints and NOCs.

## 5. Geometry input notes
- **DXF:** closed LWPOLYLINE/POLYLINE; verify `$INSUNITS` and calibrate with a known survey dimension where needed. Export native DWG to DXF.
- **KML/KMZ:** Polygon outer rings and perimeter LineStrings. KML coordinates are geographic; confirm that the selected polygon is the actual parcel.
- **Vector PDF:** only simple vector paths can be extracted, and scale calibration is needed.
- **Scanned PDF:** automatic raster tracing is not included in this release; trace/vectorise in CAD first.

## 6. Tests
Run from the project folder:
```bash
python -m pytest -q
```

## 7. Source files and rule library
- `rules/authority_registry.json`: authority coverage/status and source links.
- `rules/*lpa2031_candidate.json`: provisional LPA rule profiles and source clauses.
- `rules/authority_coverage_matrix.csv`: review queue and next actions.
- `SOURCES.md`: provenance notes and limitations.
- `KARNATAKA_RULES_EXPANSION_PLAN.md`: work queue for adding and validating authority profiles.


## Location lookup order in v0.4.7
1. Selected/applied georeferenced KML boundary (the boundary takes precedence).
2. Google Maps link, if supplied.
3. Manually entered coordinates, only when no map link is supplied.
4. Address geocoding, only when neither map link nor coordinates are supplied.

If the supplied Google Maps link cannot be resolved, clear or replace it deliberately; SiteIQ will not silently fall back to old coordinates. When both a map link and coordinates are supplied, it shows their distance if they differ by more than 1 km.
