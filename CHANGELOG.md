# Changelog

## v0.7.0 — 2026-11-03
**Changed results.** Bengaluru now shows Premium FAR scenarios, and side edges tagged left or right use their own setback.

**Calculations.** FAR exclusions apply only where the plan lists them. Floor schedules replace footprint × floors. Depth and width variation on irregular plots is reported. Road widening reports the land taken and the capacity if it isn't counted. Premium FAR shows the Premium-only allowance and an estimated charge.

**Daily use.** Projects save to `.siteiq` files and appear in a recent list. Revisions record inputs and results, and compare against the current study. DXF import opens blocks and joins loose lines and arcs; PDF import joins loose lines. Client and architect reports are separate. A3 boards label road edges and show a scale. Narrow screens keep a status bar. Map layer installation moved under administrator tools.

**Tidying.** `python -m siteiq.rule_admin` validates profiles and records sign-off. Runtime and development dependencies are split, with a tested lockfile. Removed `create_location_demo.py`, whose input file no longer exists.

## v0.6.0 — 2026-11-02
**New interface.** React and FastAPI replace Streamlit as the main interface. Results update live, and exports recalculate from the current inputs. The Streamlit app remains as `app.py` and shares the same service.

**Changed results.** Figures from earlier versions may differ:
- No default authority, area, road width or category. A new study shows no FAR.
- Draft, superseded, withdrawn, expired or unrecorded profiles cannot calculate.
- Fire checks apply statewide and no longer state 6 m, 9 m or 12 m access dimensions, which had no source.
- KML areas use a local projection (was UTM, up to 0.165% off) and exclude inner rings.
- Per-edge setbacks stay on their own edge, so concave plots keep area wrongly removed before.
- Auto-footprints respect the ground-coverage limit. Far ratios use one denominator.
- Plots up to 250 m² with height up to 15 m use Table 8, and Table 8 height excludes the stilt when its height is entered.

- Planning authority rules were compared with each authority's published plan: Hoskote's industrial table was corrected, Anekal group housing now has a FAR, and low-rise setbacks and apartment rules were added.
- RMP Tables 20 and 21 now give a FAR for development plans.

**Added.** A compliance register with a verdict, where anything unevaluated never counts as a pass. Checks from source documents: road-width height limit, apartment rules by ring, basement limits, Table 23 parking, ramps, drain buffers (UDD 468), plus EIA and RERA triggers. Warnings near rule thresholds. No-build depths along named edges. Whole-parcel authority overlap checks. Stricter locality matching, coordinate validation and map-link fetching.

## v0.4.7 — 2026-10-16
- Fix KML location handoff and prevent stale address coordinates from overriding an applied boundary.
- Add location-only KML lookup for open perimeter paths; keep area validation separate.
- Warn when a newly uploaded KML is not the same as the active boundary.
- Added regression tests for Hoskote-vs-Tumakuru stale-coordinate scenario.

## Earlier versions
See `KARNATAKA_RULES_EXPANSION_PLAN.md` and `SOURCES.md` for prior rule-library and authority-profile changes.


## v0.4.7 — 2026-10-16
- Prioritised supplied Google Maps links over stale coordinate text.
- Added distance comparison and visible mismatch warning for map-link vs typed coordinates.
- Failed link resolution now fails closed and clears stale results instead of silently using another location.
- Preferred explicit Google Maps place-pin coordinates over viewport centre.
- Added regression coverage for the reported Tumakuru-vs-Hoskote location handoff.
