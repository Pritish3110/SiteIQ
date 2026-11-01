# SiteIQ v0.4.7 — Multi-authority rule-driven feasibility

SiteIQ is a local browser-based tool for early-stage architectural site feasibility. This release expands the configured rules catalogue beyond Bengaluru RMP 2015 to include **provisional source-transcribed FAR candidates** for Hoskote, Kanakapura, Nelamangala and Anekal LPA Master Plan 2031 profiles. These are not verified consolidated operative codes; the app labels them accordingly and requires official validation before design freeze or sanction use. A separate 22 May 2026 final amendment (UDD 17 TTP 2025(E)) is recorded for its stated non-BMR / non-Mangaluru scope and selected special-use provisions, but it is not treated as a universal residential FAR code.

## Current capabilities
- Resolve locations from a selected/applied KML boundary first, then a supplied Google Maps link, then manually entered coordinates, then address geocoding. If a supplied Google Maps link cannot be resolved, SiteIQ fails closed instead of silently using a potentially stale coordinate. Map-link/typed-coordinate mismatches are shown.
- Apply imported georeferenced KML/KMZ site boundaries as the preferred location reference; warn if the old address coordinates are far away.
- Import closed DXF polylines, simple vector PDF geometry and KML/KMZ paths; validate units/scale and geometry; calculate area/perimeter; identify frontage edges; generate preliminary setback envelopes and export DXF.
- Select authority-specific regulatory land-use categories from the configured profile.
- Lookup FAR from configured rule methods without interpolation across missing bands; conditional group-housing rules can apply to configured LPA profiles where the site/use conditions match.
- Calculate a net FAR calculation area when a configured table specifies a reservation/deduction, and label achieved FAR ratios by their denominator basis.
- Compare multiple height/floor/setback/stilt/basement options against a rule-derived candidate FAR benchmark.
- Display optional Premium FAR/TDR scenarios separately from base FAR. Charges, exact current Table 27 eligibility and premium/TDR mix are not calculated.
- Export detailed PDF, editable PowerPoint, A3 comparison board PDF/PPTX, assessment JSON and boundary/envelope DXF.
- Show a Karnataka authority coverage registry and CSV source-review queue.

## Run locally
See `START_HERE.md`. On Windows, extract the ZIP and run `run_siteiq.bat`. The first run creates a virtual environment, installs dependencies and launches Streamlit locally. Internet access is needed for initial package installation and location geocoding.

## Run tests
From the extracted project folder:
```bash
python -m pytest -q
```

## Rule status and scope
| Profile | Current state in v0.4.7 | Can return a FAR candidate? |
|---|---|---:|
| Bengaluru / Greater Bengaluru RMP 2015 | Partial configured provisions from user-supplied RMP/amendments | Yes, selected categories only |
| Hoskote LPA Master Plan 2031 | Provisional transcription from secondary copies; official current version/amendments pending | Yes, for configured category/table paths, with warnings |
| Kanakapura LPA Master Plan 2031 | Provisional transcription from secondary copies; official current version/amendments pending | Yes, for configured category/table paths, with warnings |
| Nelamangala LPA Master Plan 2031 | Provisional transcription from secondary copies; official current version/amendments pending | Yes, for configured category/table paths, with warnings |
| Anekal LPA Master Plan 2031 | Provisional general table; group-housing path unresolved due source-copy conflicts | Some configured general categories only |
| BDA LPA, Mysuru, Hubballi-Dharwad and other listed authorities | Registry/source queue only; no verified full rule profile | No |

A FAR returned from a provisional profile is a **candidate from a secondary source**, not a statutory entitlement. Confirm exact planning jurisdiction, official zone, current Gazette/approved plan, amendments and notified road width before relying on it. No authority inherits Bengaluru FAR by default.

## Important source-status rules
- The 24 March 2026 UDD 559 BMR 2025(E) Uniform Zonal Regulations proposal is recorded as **draft-only** and is not applied to calculations unless a final notification and commencement for the specific authority are verified.
- The provisional LPA profiles use secondary copies of Master Plan 2031 zoning regulations to reduce initial manual work and surface candidate rules. The source provenance/status is recorded in each profile, and the UI/report display warning text.
- Land-use zone is not considered verified unless an appropriate official zoning polygon layer or equivalent authoritative result is available.
- Authority boundary, ward/corporation boundaries and planning-area boundaries are distinct. Administrative KMLs from OpenCity are useful clues but do not establish legal planning jurisdiction or FAR zoning on their own.

## Version notes
- **v0.4.7:** provisional FAR profiles for four BMRDA-area LPAs; conditional group-housing logic, net FAR calculation basis, source-quality warnings and optional Premium FAR/TDR scenario; per-option set-back and basement logic retained.
- v0.4.4: KML boundary location precedence and public-source lookup.
- v0.4.1: location auto-identification Streamlit state fix.
- v0.4.0: rule-driven FAR and option comparison workflow.
- v0.3.x: boundary import, geometry checks, setback-envelope preview and CAD export.
