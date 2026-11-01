# SiteIQ location layers (v0.3.1)

SiteIQ can select an authority/rules profile and official land-use zone automatically only when a point matches an installed polygon layer. A city name or geocoder result is not an authoritative boundary.

## Coordinate system

Store layers as GeoJSON FeatureCollections in WGS84 longitude/latitude (EPSG:4326). In QGIS, load the authoritative boundary, set/export the output CRS to EPSG:4326 and export as GeoJSON. Keep the publisher, notification/version, effective date and source URL in feature properties.

## authority_boundaries.geojson schema

Each polygon feature must have `properties.authority_key` equal to one of the keys in `rules/authority_registry.json` (this maps a polygon to a configured SiteIQ rules profile), plus `authority_name`, `source_title`, `source_url`, and `source_date`. Optional `active: false` disables a feature. If the current local corporation and planning authority are different, do not use a corporation boundary as a rules-profile boundary unless the mapping has been verified by a planner.

## land_use_zones.geojson schema

Each polygon feature must have `properties.zone_name` or `properties.land_use`. For the current Bengaluru partial profile, recommended labels are exactly one of: `Residential (Main)`, `Residential (Mixed)`, `Commercial`, `Industrial`, `Public / Semi-public`, `Other / unknown`. Include `source_title`, `source_url`, `source_date` and, ideally, `effective_date`.

## Important

- Do not upload traced or approximate polygons as if they were official/legal boundaries.
- The official GBA GIS Viewer / city corporation boundary maps and BDA master plan portal are starting points; confirm that a layer is final, applicable and current.
- If multiple equally specific polygons match one point, SiteIQ reports an ambiguity instead of selecting arbitrarily.
- Location lookups are user-triggered only. Address lookups send the entered address to OpenStreetMap Nominatim, and short-link resolution contacts the map provider. Results are cached locally for 24 hours.
