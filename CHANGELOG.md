# Changelog

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
