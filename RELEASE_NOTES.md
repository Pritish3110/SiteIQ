# SiteIQ v0.4.7 — Google Maps Link Priority Fix

## Main fix
- A supplied Google Maps link is now the primary location input unless a selected/applied KML boundary is active.
- When both a map link and typed coordinates are present, SiteIQ resolves the map link first and computes the distance from the typed coordinates. A mismatch above 1 km is shown clearly.
- If a supplied map link cannot be resolved, SiteIQ stops and reports the error instead of silently falling back to stale coordinates or the address.
- Explicit Google Maps place/pin coordinates (`!3d...!4d...`) are prioritised over `@lat,lon` viewport-centre coordinates when both appear in a URL.
- Failed location lookups clear the previous identification result and report so a stale authority is not left visible.
- The UI now names the source that drove the lookup.

## Retained capabilities
- KML/KMZ boundary coordinate overrides take precedence over address, typed coordinates and map links when a boundary is selected/applied.
- Multi-authority rule profiles for Bengaluru (partial), Hoskote, Kanakapura, Nelamangala and Anekal remain subject to their existing source-status warnings.
- Geometry/boundary tools, FAR lookup, option comparison, basement handling and PDF/PowerPoint/A3 exports remain in place.

## Validation
- Automated tests include a map-link-vs-stale-coordinate regression case and a fail-closed case when the map URL cannot be resolved.
- A real short-link resolution still requires the user's local machine to reach Google Maps over the internet. If resolution fails, SiteIQ intentionally will not use conflicting old coordinates.

## Important limitation
A resolved map point or geocoder locality is not proof of notified planning jurisdiction or statutory land-use zone. Official planning-boundary and zoning data still need to be verified before relying on FAR or sanction-related results.
