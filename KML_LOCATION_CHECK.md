# SiteIQ KML location check — Test 02

Date checked: 16 October 2026

## What the uploaded KML contains
- Site polygon centroid: **13.0733543 N, 77.7823976 E** (WGS84).
- SiteIQ projected polygon area: **20,684.15 m²**.
- SiteIQ perimeter: **673.59 m**.
- Polygon geometry parsed as valid.

## Why the screenshot showed Greater Bengaluru
The screenshot's active coordinates were **13.0424360 N, 77.4656840 E**, from the address `Madhavara, Lakshmipura, Bangalore North`. That point is approximately **34.5 km** from the uploaded Test 02 KML centroid. SiteIQ v0.4.3 ran location identification from that active coordinate before the imported boundary was used, so the displayed Greater Bengaluru candidate was for a different point—not a spatial match to the Test 02 polygon.

## Updated behavior in v0.4.4 and v0.4.6
After a valid georeferenced KML polygon is applied, SiteIQ uses its WGS84 centroid to rerun location identification. If the previous coordinate is more than 1 km away, the app shows a mismatch warning. Hoskote/Hosakote is checked before broad Bengaluru/Bangalore locality labels. In v0.4.6, provisional source-transcribed rule profiles are also available for Hoskote, Kanakapura, Nelamangala, and Anekal. Applying the boundary is required; merely attaching this KML to the chat does not update a local SiteIQ instance.

## Regulatory status
The point is consistent with the Hoskote locality; **Hoskote Planning Authority remains a provisional candidate, not a verified boundary match**, unless an official authority polygon is installed and matches it. SiteIQ still has no active Hoskote FAR rules profile, and will not borrow Bengaluru RMP values. The 24 March 2026 UDD 559 BMR 2025(E) uniform zonal regulations document located during review is explicitly a draft; the document says commencement would be on final notification by each individual authority. Verify any subsequent final notification before relying on its rules.

## Important area note
If an earlier screen showing **64,960.91 m²** was meant to refer to the same Test 02 KML, it does not match this file's computed area of **20,684.15 m²**. Confirm that the active boundary candidate and report are generated from the same source file.


## v0.4.7 — Google Maps link is now the primary manual input
When no selected/applied KML boundary is active, a supplied Google Maps link is resolved before typed coordinates or address geocoding. If both a map link and coordinate text are present, SiteIQ compares them and warns when the inputs are more than 1 km apart. If the map link fails to resolve, it clears the previous identification result and does not use the possibly stale coordinate field.
