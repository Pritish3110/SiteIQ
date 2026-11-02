# SiteIQ v0.6.0: early-stage site feasibility for Karnataka

SiteIQ takes a site location and survey boundary, finds the planning rule, draws the buildable envelope for each design option, and reports what it could not confirm. It is a preliminary aid, not sanction advice. To run it, see `START_HERE.md`.

## What it does
- **Location:** resolves a boundary, Google Maps link, coordinates or address, in that order, and fails closed if a lookup fails.
- **Boundary:** imports DXF, KML/KMZ and vector PDF, validates them, and applies a separate setback to each edge, including on concave plots.
- **Rules:** finds FAR from authority-specific tables without interpolating or borrowing. Premium FAR and TDR stay separate.
- **Compliance register:** gives every provision one outcome: Pass, Fail, Needs input, Confirm or Not configured. Anything unevaluated never counts as a pass.
- **Exports:** PDF report, A3 board, editable PowerPoint, layered DXF and JSON, all recalculated from the current inputs.

## How it fits together
```
frontend/ (React) -> siteiq/api.py (FastAPI) -> siteiq/service.py -> engine, boundary, location, checks, exporters
app.py (Streamlit, older interface) ----------^
rules/*.json holds authority profiles; rules/statewide_rules.json holds statewide provisions
```

## Rule status and scope
| Profile | Current state | Can return a FAR candidate? |
|---|---|---:|
| Bengaluru / Greater Bengaluru RMP 2015 | Partial configured provisions from user-supplied RMP/amendments | Yes, selected categories only |
| Hoskote LPA Master Plan 2031 | Compared with the plan on the authority's website; review and later amendments pending | Yes, for configured categories, with warnings |
| Kanakapura LPA Master Plan 2031 | Compared with the plan on the authority's website; review and later amendments pending | Yes, for configured categories, with warnings |
| Nelamangala LPA Master Plan 2031 | Compared with the plan on the authority's website; review and later amendments pending | Yes, for configured categories, with warnings |
| Anekal LPA Master Plan 2031 | Compared with the plan on the authority's website; review and later amendments pending | Yes, for configured categories, with warnings |
| BDA LPA, Mysuru, Hubballi-Dharwad and other listed authorities | Registry/source queue only; no verified full rule profile | No |

A FAR returned from a provisional profile is a **candidate**, not a statutory entitlement. Confirm exact planning jurisdiction, official zone, current Gazette/approved plan, amendments and notified road width before relying on it. No authority inherits Bengaluru FAR by default.

## Important source-status rules
- The 24 March 2026 UDD 559 BMR 2025(E) Uniform Zonal Regulations proposal is recorded as **draft-only** and is not applied to calculations unless a final notification and commencement for the specific authority are verified.
- The LPA profiles were compared with the Master Plan 2031 text on each authority's website. Later amendments have not been checked, so results stay provisional.
- Land-use zone is not considered verified unless an appropriate official zoning polygon layer or equivalent authoritative result is available.
- Authority boundary, ward/corporation boundaries and planning-area boundaries are distinct. Administrative KMLs from OpenCity are useful clues but do not establish legal planning jurisdiction or FAR zoning on their own.

## Version notes
- **v0.6.0:** new interface, compliance register and reliability fixes; see `CHANGELOG.md`.
- **v0.4.7:** provisional FAR profiles for four BMRDA-area LPAs; conditional group-housing logic, net FAR calculation basis, source-quality warnings and optional Premium FAR/TDR scenario; per-option set-back and basement logic retained.
- v0.4.4: KML boundary location precedence and public-source lookup.
- v0.4.1: location auto-identification Streamlit state fix.
- v0.4.0: rule-driven FAR and option comparison workflow.
- v0.3.x: boundary import, geometry checks, setback-envelope preview and CAD export.
