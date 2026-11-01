"""Location resolution and spatial auto-identification for SiteIQ.

Address geocoding is a convenience only. Official jurisdiction and land-use outputs
are selected only when matching GeoJSON polygon layers are installed locally.
Geocoder-only matches are explicitly marked provisional.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import requests
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
SPATIAL_DIR = ROOT / "data" / "spatial"
CACHE_DIR = ROOT / "data" / "geocode_cache"
AUTHORITY_LAYER = SPATIAL_DIR / "authority_boundaries.geojson"
ZONE_LAYER = SPATIAL_DIR / "land_use_zones.geojson"
USER_AGENT = "SiteIQ/0.4.7 (local architectural feasibility tool; user-triggered location lookup)"
_LAST_NOMINATIM_REQUEST = 0.0


def parse_coordinate_text(value: str | None) -> Optional[tuple[float, float]]:
    """Parse user coordinates as latitude, longitude."""
    if not value:
        return None
    m = re.search(r"(-?\d{1,2}(?:\.\d+)?)\s*[,;/ ]\s*(-?\d{1,3}(?:\.\d+)?)", value.strip())
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _coords_from_text(text: str) -> Optional[tuple[float, float]]:
    text = unquote(text or "")
    # Prefer the explicit place/pin coordinates (!3d/!4d) over @viewport-centre
    # coordinates when both are present in a Google Maps URL.
    patterns = [
        r"!3d\s*(-?\d{1,2}(?:\.\d+)?)!4d\s*(-?\d{1,3}(?:\.\d+)?)",
        r"@\s*(-?\d{1,2}(?:\.\d+)?),\s*(-?\d{1,3}(?:\.\d+)?)",
        r"(?:[?&](?:q|query|ll|center|destination|origin)=)(-?\d{1,2}(?:\.\d+)?)[,%20+ ]+(-?\d{1,3}(?:\.\d+)?)",
        r"(?:/search/)(-?\d{1,2}(?:\.\d+)?)[,%20+ ]+(-?\d{1,3}(?:\.\d+)?)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    return None


def coordinates_from_map_url(map_url: str | None, resolve_short_link: bool = True) -> dict:
    """Extract coordinates from common Google Maps URLs; expand short links on demand."""
    result = {"coordinates": None, "resolved_url": map_url or "", "method": None, "warning": None}
    if not map_url:
        return result
    direct = _coords_from_text(map_url)
    if direct:
        result.update(coordinates=direct, method="coordinates_embedded_in_map_url")
        return result
    if not resolve_short_link:
        result["warning"] = "No coordinates were visible in the supplied map URL."
        return result
    try:
        # Expand only expected map-provider hosts; do not let this local UI fetch arbitrary URLs.
        parsed = urlparse(map_url)
        host = (parsed.hostname or "").casefold()
        allowed_host = host in {"maps.app.goo.gl", "goo.gl", "google.com", "www.google.com", "maps.google.com", "maps.google.co.in", "earth.google.com"} or host.endswith(".google.com") or host.endswith(".google.co.in")
        if parsed.scheme != "https" or not allowed_host:
            result["warning"] = "Only HTTPS Google Maps / Google Earth links can be expanded. Paste coordinates or use a searchable address instead."
            return result
        # Only called after the user clicks Identify; no background scraping/polling.
        response = requests.get(map_url, allow_redirects=True, timeout=12, headers={"User-Agent": USER_AGENT})
        final_url = response.url or map_url
        result["resolved_url"] = final_url
        coords = _coords_from_text(final_url)
        if coords is None:
            coords = _coords_from_text(response.text[:2_000_000])
        if coords:
            result.update(coordinates=coords, method="expanded_map_link")
            return result
        result["warning"] = "The map link opened, but its destination coordinates could not be extracted. Paste latitude, longitude or provide a searchable address."
    except Exception as exc:
        result["warning"] = f"Could not resolve the map short link ({type(exc).__name__}). Paste latitude, longitude or provide a searchable address."
    return result


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")


def _cached_request(kind: str, query: str, endpoint: str, params: dict) -> dict:
    global _LAST_NOMINATIM_REQUEST
    cache = _cache_path(kind + "|" + query.casefold())
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - float(saved.get("cached_at", 0)) < 86400:
                return saved["result"]
        except Exception:
            pass
    # Respect the public Nominatim service's one-request-per-second usage limit.
    wait = 1.1 - (time.monotonic() - _LAST_NOMINATIM_REQUEST)
    if wait > 0:
        time.sleep(wait)
    response = requests.get(endpoint, params=params, timeout=10, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    _LAST_NOMINATIM_REQUEST = time.monotonic()
    response.raise_for_status()
    result = response.json()
    cache.write_text(json.dumps({"cached_at": time.time(), "result": result}, ensure_ascii=False), encoding="utf-8")
    return result


def geocode_address(address: str) -> dict:
    """Resolve an address via one manual Nominatim lookup, cached locally for 24h."""
    if not address or not address.strip():
        raise ValueError("Enter a site address/locality, a map link with coordinates, or latitude/longitude.")
    query = address.strip()
    try:
        rows = _cached_request("geocode", query, "https://nominatim.openstreetmap.org/search", {
            "q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1,
            "countrycodes": "in",
        })
    except Exception as exc:
        raise RuntimeError(f"Address lookup failed: {type(exc).__name__}. Try a direct Google Maps link or enter latitude, longitude.") from exc
    if not rows:
        raise RuntimeError("No address match was found. Try a more complete address or enter latitude, longitude.")
    row = rows[0]
    return {
        "lat": float(row["lat"]), "lon": float(row["lon"]),
        "display_name": row.get("display_name", query),
        "address": row.get("address", {}),
        "source": "OpenStreetMap Nominatim geocoding (indicative location; not a property-boundary source)",
    }


def reverse_geocode(lat: float, lon: float) -> dict:
    query = f"{lat:.7f},{lon:.7f}"
    try:
        result = _cached_request("reverse", query, "https://nominatim.openstreetmap.org/reverse", {
            "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 16, "addressdetails": 1,
        })
        return {
            "display_name": result.get("display_name", ""),
            "address": result.get("address", {}),
            "source": "OpenStreetMap Nominatim reverse geocoding (indicative location only)",
        }
    except Exception as exc:
        return {"display_name": "", "address": {}, "source": None, "warning": f"Reverse geocoding unavailable ({type(exc).__name__})."}


def _load_geojson(path: Path) -> dict:
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") == "Feature":
        data = {"type": "FeatureCollection", "features": [data]}
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError(f"{path.name} must be a GeoJSON FeatureCollection (WGS84 / EPSG:4326).")
    return data


def _point_matches(layer_path: Path, lat: float, lon: float, kind: str) -> dict:
    if not layer_path.exists():
        return {"status": "layer_not_installed", "match": None, "matches": [], "layer": str(layer_path.name)}
    try:
        fc = _load_geojson(layer_path)
    except Exception as exc:
        return {"status": "layer_error", "match": None, "matches": [], "layer": layer_path.name, "message": str(exc)}
    point = Point(lon, lat)
    matches = []
    for feature in fc.get("features", []):
        if not feature or not feature.get("geometry"):
            continue
        props = feature.get("properties") or {}
        if props.get("active") is False or str(props.get("active", "")).lower() in ("false", "0", "no"):
            continue
        try:
            geom = shape(feature["geometry"])
            if geom.is_empty or not geom.is_valid or not geom.covers(point):
                continue
        except Exception:
            continue
        if kind == "authority":
            value = props.get("authority_key") or props.get("siteiq_authority_key") or props.get("rule_profile_key")
            label = props.get("authority_name") or props.get("name") or value
        else:
            value = props.get("zone_name") or props.get("land_use") or props.get("zone") or props.get("category")
            label = value
        if not value:
            continue
        # More specific polygons win where official layers include nested areas.
        matches.append({
            "value": str(value), "label": str(label or value),
            "area_degrees2": float(geom.area), "source_title": props.get("source_title", "Uploaded spatial layer"),
            "source_url": props.get("source_url", ""), "source_date": props.get("source_date", ""),
            "confidence": "spatial_polygon_match",
        })
    if not matches:
        return {"status": "no_polygon_match", "match": None, "matches": [], "layer": layer_path.name,
                "message": "The point did not fall inside a configured feature in this layer."}
    matches.sort(key=lambda x: x["area_degrees2"])
    best_area = matches[0]["area_degrees2"]
    equally_specific = [x for x in matches if abs(x["area_degrees2"] - best_area) < max(1e-12, best_area * 0.001)]
    unique_values = {x["value"] for x in equally_specific}
    if len(unique_values) > 1:
        return {"status": "ambiguous_polygon_match", "match": None, "matches": equally_specific, "layer": layer_path.name,
                "message": "More than one equally specific polygon matches this point. A human must resolve the overlap/boundary."}
    return {"status": "matched_polygon_layer", "match": matches[0], "matches": matches, "layer": layer_path.name}


def identify_spatial_context(lat: float, lon: float, authority_layer: Path = AUTHORITY_LAYER, zone_layer: Path = ZONE_LAYER) -> dict:
    """Match point to user-installed, official-source WGS84 GeoJSON layers."""
    return {
        "authority": _point_matches(authority_layer, lat, lon, "authority"),
        "zone": _point_matches(zone_layer, lat, lon, "zone"),
    }


def _locality_candidate(reverse: dict) -> dict:
    """Return a low-confidence candidate from geocoder administrative labels only.

    This is intentionally a candidate, never a legally verified jurisdiction match.
    More specific local planning authority names are checked before city-level labels.
    """
    addr = reverse.get("address") or {}
    tokens = [str(addr.get(k, "")) for k in (
        "city", "town", "municipality", "county", "state_district",
        "suburb", "village", "hamlet", "township", "state"
    )]
    text = " ".join(tokens).casefold()
    # Check local planning areas before broad Bengaluru/Bangalore district labels.
    if "kanakapura" in text:
        return {"key": "kanakapura_planning_authority", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The geocoder labels this location with Kanakapura. Kanakapura Planning Authority is a candidate to investigate, but a locality/taluk label does not prove that the parcel lies within its notified planning boundary."}
    if "nelamangala" in text:
        return {"key": "nelamangala_planning_authority", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The geocoder labels this location with Nelamangala. Nelamangala Planning Authority is a candidate to investigate; confirm the notified boundary and current operative rules."}
    if "anekal" in text:
        return {"key": "anekal_planning_authority", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The geocoder labels this location with Anekal. Anekal Planning Authority is a candidate to investigate; confirm the notified boundary and current operative rules."}
    # Check outer local planning areas before broad Bengaluru/Bangalore district labels.
    # This remains a geocoder candidate unless an official authority polygon matches.
    if "hoskote" in text or "hosakote" in text:
        return {"key": "hoskote_planning_authority", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The geocoder labels this point with Hoskote/Hosakote. Hoskote Planning Authority is a candidate to investigate; a locality label or KML centroid does not prove the parcel is inside its notified planning boundary."}
    if any(x in text for x in ("bengaluru", "bangalore")):
        return {"key": "bengaluru_rmp2015", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The mapped locality is labelled Bengaluru/Bangalore, but this does not prove the parcel's current Greater Bengaluru, BDA or BMRDA planning boundary. SiteIQ will show official map sources to check."}
    if any(x in text for x in ("mysuru", "mysore")):
        return {"key": "mysuru_development_authority", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The mapped locality is labelled Mysuru/Mysore. Confirm the notified planning area and operative local authority."}
    if any(x in text for x in ("hubballi", "hubli", "dharwad")):
        return {"key": "hubballi_dharwad_udau", "status": "provisional_geocoder_candidate", "confidence": "low",
                "reason": "The mapped locality is labelled Hubballi/Dharwad. Confirm the notified planning area and operative local authority."}
    if "karnataka" in text:
        return {"key": "other_karnataka", "status": "state_only_candidate", "confidence": "low",
                "reason": "The location appears to be in Karnataka, but an exact planning authority cannot be inferred from locality text alone."}
    return {"key": None, "status": "not_identified", "confidence": "none",
            "reason": "The public geocoder did not return enough administrative labels to suggest a planning authority."}


def infer_approval_route(site_area_m2: float, proposed_use: str, authority_key: str | None, current_choice: str | None, road_width_m: float | None = None) -> dict:
    """Suggest an approval-route starting point only for configured Bengaluru RMP context."""
    cur = (current_choice or "").lower()
    if current_choice and "not sure" not in cur and "needs confirmation" not in cur:
        return {"suggested_value": current_choice, "status": "user_selected", "reason": "Existing selection retained; location lookup will not overwrite the user's declared approval route."}
    configured_lpa_candidates = {
        "hoskote_planning_authority", "kanakapura_planning_authority",
        "nelamangala_planning_authority", "anekal_planning_authority"
    }
    if authority_key not in ({"bengaluru_rmp2015"} | configured_lpa_candidates):
        return {"suggested_value": "Not sure / needs confirmation", "status": "not_configured_for_authority",
                "reason": "Approval route is not auto-suggested because the authority-specific rule profile is not configured."}
    if site_area_m2 <= 0:
        return {"suggested_value": "Not sure / needs confirmation", "status": "missing_site_area", "reason": "Enter the plot area to suggest an approval route."}
    use_folded = (proposed_use or "").casefold()
    non_residential = any(token in use_folded for token in ("commercial", "office", "mixed use", "institutional", "other"))
    road_note = f" Reported road width is {road_width_m:.2f} m; use-specific minimum road-width conditions still need checking." if road_width_m and road_width_m > 0 else " Road width is not available for the use-specific route check."
    if authority_key in configured_lpa_candidates:
        authority_label = {
            "hoskote_planning_authority": "Hoskote",
            "kanakapura_planning_authority": "Kanakapura",
            "nelamangala_planning_authority": "Nelamangala",
            "anekal_planning_authority": "Anekal",
        }[authority_key]
        if site_area_m2 >= 10000 and any(token in use_folded for token in ("apartment", "apartments", "group housing", "multi dwelling", "multi-dwelling")):
            route = "Group housing / residential development-plan candidate"
            reason = f"For an apartment site of {site_area_m2:,.0f} m², the available {authority_label} LPA Master Plan 2031 source copies describe a group-housing pathway at 1 hectare or above. This is a provisional pathway suggestion: confirm the operative plan, required reservations, minimum approach road and exact development-plan route with the authority." + road_note
        elif site_area_m2 >= 10000 and non_residential and authority_key == "hoskote_planning_authority":
            route = "Non-residential development-plan candidate"
            reason = "The available Hoskote LPA 2031 source copy has a non-residential development-plan table for sites above 1 hectare (excluding industrial uses). Verify the exact approval pathway and current official text." + road_note
        elif site_area_m2 >= 10000:
            route = "Development plan / local LPA route — confirm"
            reason = f"The plot exceeds 1 hectare. A development-plan route may apply under {authority_label} LPA source material; SiteIQ has not verified the operative local approval pathway." + road_note
        else:
            route = "Local building / plot approval route — confirm"
            reason = f"The plot is below 1 hectare. Confirm whether the current {authority_label} LPA rules require building-plan, single-plot, layout or another approval pathway; this is not configured as a definitive route." + road_note
        return {"suggested_value": route, "status": "provisional_route_candidate", "reason": reason}
    if site_area_m2 <= 10000:
        reason = f"For a {site_area_m2:,.0f} m² plot, Chapter 6-A may be the starting route under the configured Bengaluru RMP profile, assuming a new eligible single-plot application. Verify plot identity, prior sanctions, applicability and current validity."
        if non_residential:
            reason += " For non-residential/mixed or other use, Table 7 minimum plot-area and abutting-road conditions are not configured in this MVP; this route is not an eligibility determination."
            reason += road_note
        return {"suggested_value": "New single-plot approval under Chapter 6-A", "status": "provisional_candidate",
                "reason": reason}
    return {"suggested_value": "Development plan / layout", "status": "provisional_candidate",
            "reason": f"The {site_area_m2:,.0f} m² area is above the configured 10,000 m² single-plot route. A development-plan route may be relevant under the configured Bengaluru profile; confirm the exact approval pathway and use-specific requirements." + road_note}


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine distance between (latitude, longitude) coordinate pairs."""
    from math import asin, cos, radians, sin, sqrt
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1.0, h)))


def auto_identify_site(address: str = "", map_url: str = "", coordinates_text: str = "", site_area_m2: float = 0,
                       proposed_use: str = "", road_width_m: float | None = None,
                       current_authority_key: str | None = None,
                       current_zone: str | None = None, current_approval_path: str | None = None,
                       authority_layer: Path = AUTHORITY_LAYER, zone_layer: Path = ZONE_LAYER) -> dict:
    """Resolve coordinates and suggest fields; a supplied map link is the primary source.

    Priority: (1) selected/applied KML is handled by location_ui and passed as coordinates
    with its map URL suppressed, (2) an explicit Google Maps link, (3) typed coordinates,
    (4) address geocoding. If a map link is supplied but cannot be resolved, fail closed
    rather than silently using stale coordinates from another site.
    """
    entered_coords = parse_coordinate_text(coordinates_text)
    map_lookup = {"coordinates": None, "resolved_url": map_url or "", "method": None, "warning": None}
    geocoded = None
    input_coordinate_comparison = None

    if map_url and map_url.strip():
        map_lookup = coordinates_from_map_url(map_url.strip(), resolve_short_link=True)
        coords = map_lookup.get("coordinates")
        method = map_lookup.get("method")
        if coords is None:
            detail = map_lookup.get("warning") or "The Google Maps link did not return extractable coordinates."
            raise RuntimeError(
                f"Google Maps link could not be resolved: {detail} "
                "SiteIQ did not use the existing coordinate field or address because they may refer to a different property. "
                "Paste a full Google Maps URL containing a pin/coordinate, or clear the map-link field to deliberately use the typed coordinates/address."
            )
        if entered_coords:
            distance = _distance_km(entered_coords, (float(coords[0]), float(coords[1])))
            input_coordinate_comparison = {
                "entered_coordinates": [float(entered_coords[0]), float(entered_coords[1])],
                "map_link_coordinates": [float(coords[0]), float(coords[1])],
                "distance_km": distance,
                "mismatch": distance > 1.0,
                "threshold_km": 1.0,
            }
        location_source = "Google Maps link"
    elif entered_coords:
        coords = entered_coords
        method = "user_entered_coordinates"
        location_source = "Manually entered coordinates"
    elif address.strip():
        geocoded = geocode_address(address)
        coords = (geocoded["lat"], geocoded["lon"])
        method = "address_geocoding"
        location_source = "Address geocoding (indicative)"
    else:
        raise RuntimeError("Provide a Google Maps link, coordinate pair, or searchable address.")

    if coords is None:
        raise RuntimeError("Site location could not be resolved. Provide a Google Maps link, coordinate pair, or searchable address.")
    lat, lon = float(coords[0]), float(coords[1])
    # Reuse forward-geocoder address metadata to avoid a second Nominatim call in
    # the same lookup. If coordinates came from a map or user, request reverse geocoding once.
    if geocoded:
        reverse = {"display_name": geocoded.get("display_name", ""), "address": geocoded.get("address", {}), "source": geocoded.get("source")}
    else:
        reverse = reverse_geocode(lat, lon)
    spatial = identify_spatial_context(lat, lon, authority_layer=authority_layer, zone_layer=zone_layer)

    authority_result = spatial["authority"]
    if authority_result.get("status") == "matched_polygon_layer":
        raw_key = authority_result["match"]["value"]
        # layer value can be an authority registry key or an authority label
        authority_key = raw_key if raw_key in {
            "bengaluru_rmp2015", "bda_lpa", "bmrda", "kanakapura_planning_authority", "hoskote_planning_authority", "anekal_planning_authority", "nelamangala_planning_authority", "mysuru_development_authority", "hubballi_dharwad_udau", "other_karnataka"
        } else None
        if authority_key:
            authority_candidate = {"key": authority_key, "label": authority_result["match"].get("label") or authority_key, "status": "matched_polygon_layer", "confidence": "medium_high",
                                  "reason": "Point matched the installed authority boundary layer. Validate layer date and the distinction between municipal corporation and planning authority.",
                                  "source_title": authority_result["match"].get("source_title"), "source_url": authority_result["match"].get("source_url"),
                                  "source_date": authority_result["match"].get("source_date")}
        else:
            authority_candidate = {"key": None, "status": "matched_polygon_but_unmapped", "confidence": "unknown",
                                  "reason": f"Layer matched '{raw_key}', but it is not mapped to a configured SiteIQ rules profile. Add a mapping in the authority registry."}
    else:
        authority_candidate = _locality_candidate(reverse)
        authority_candidate["source_title"] = reverse.get("source")
        authority_candidate["source_url"] = "https://www.openstreetmap.org/"
        authority_candidate["source_date"] = "Lookup time"

    selected_authority = authority_candidate.get("key")
    zone_result = spatial["zone"]
    zone_candidate = {"value": "Not verified", "status": zone_result.get("status", "not_identified"), "reason": "The public location lookup could not verify the parcel's official land-use zone. SiteIQ has listed the relevant official map sources below; it will not infer a zone from the address alone."}
    if zone_result.get("status") == "matched_polygon_layer":
        raw_zone = zone_result["match"]["value"]
        normal = re.sub(r"\s+", " ", raw_zone.strip().casefold().replace("_", " ").replace("-", " "))
        zone_aliases = {
            "residential main": "Residential (Main)", "residential (main)": "Residential (Main)",
            "residential mixed": "Residential (Mixed)", "residential (mixed)": "Residential (Mixed)",
            "commercial": "Commercial", "industrial": "Industrial",
            "public / semi public": "Public / Semi-public", "public and semi public": "Public / Semi-public",
            "other / unknown": "Other / unknown",
        }
        zone_value = zone_aliases.get(normal, "Other / unknown")
        known_zones = ["Residential (Main)", "Residential (Mixed)", "Commercial", "Industrial", "Public / Semi-public", "Other / unknown"]
        zone_candidate = {"value": zone_value, "raw_value": raw_zone, "status": "matched_polygon_layer", "reason": "Point matched the installed land-use polygon layer. Confirm source date, layer applicability and any plan amendments.",
                         "source_title": zone_result["match"].get("source_title"), "source_url": zone_result["match"].get("source_url"), "source_date": zone_result["match"].get("source_date")}

    # Do not infer an approval route from the UI's default/previously selected profile when
    # the current location itself has not produced an authority candidate.
    route_result = infer_approval_route(float(site_area_m2 or 0), proposed_use or "", selected_authority, current_approval_path, road_width_m=road_width_m)
    # Official public source links are selected automatically from the geocoder context.
    # These are source-navigation aids; they do not turn a locality match into a legal boundary match.
    try:
        from .public_sources import official_sources_for_context
        public_sources = official_sources_for_context(
            authority_key=selected_authority,
            locality_text=(reverse.get("display_name", "") + " " + " ".join(str(v) for v in (reverse.get("address") or {}).values())),
        )
    except Exception:
        public_sources = []

    # Do not erase a prior user-selected authority unless an exact polygon match or a clearly supported locality candidate exists.
    return {
        "coordinates": {"latitude": lat, "longitude": lon, "text": f"{lat:.7f}, {lon:.7f}", "method": method},
        "map_url": map_lookup.get("resolved_url") or map_url or "",
        "location_source": location_source,
        "input_coordinate_comparison": input_coordinate_comparison,
        "map_link_resolution": {"method": map_lookup.get("method"), "warning": map_lookup.get("warning"), "resolved_url": map_lookup.get("resolved_url") or map_url or ""},
        "geocoded_address": geocoded.get("display_name") if geocoded else reverse.get("display_name", ""),
        "reverse_geocode": reverse,
        "authority": authority_candidate,
        "suggested_authority_key": selected_authority,
        "zone": zone_candidate,
        "approval_route": route_result,
        "spatial_layer_status": {"authority": authority_result.get("status"), "zone": zone_result.get("status")},
        "public_sources": public_sources,
        "public_lookup_mode": "automatic_reference_lookup_no_user_GIS_upload",
        "privacy_note": "If address search was needed, the address was sent to OpenStreetMap Nominatim for a one-off lookup and cached locally for 24 hours. Map link expansion may contact the map provider. No location data is sent to a SiteIQ server by this local app.",
        "overall_status": "location_resolved" if (authority_candidate.get("key") or zone_candidate.get("status") == "matched_polygon_layer") else "location_resolved_context_unconfirmed",
    }


def save_geojson_layer(filename: str, data: bytes) -> dict:
    """Validate and save a WGS84 GeoJSON FeatureCollection in the local app folder."""
    if filename not in {"authority_boundaries.geojson", "land_use_zones.geojson"}:
        raise ValueError("Unsupported spatial layer filename.")
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError("The file is not valid UTF-8 GeoJSON.") from exc
    if obj.get("type") == "Feature":
        obj = {"type": "FeatureCollection", "features": [obj]}
    if obj.get("type") != "FeatureCollection" or not isinstance(obj.get("features"), list):
        raise ValueError("Use a GeoJSON FeatureCollection. Convert shapefile or geodatabase layers to WGS84 / EPSG:4326 GeoJSON (e.g. in QGIS).")
    if len(obj["features"]) == 0:
        raise ValueError("The GeoJSON contains no features.")
    valid_features = 0
    for feature in obj["features"]:
        if not feature or not feature.get("geometry"):
            continue
        try:
            geom = shape(feature["geometry"])
            if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty or not geom.is_valid:
                continue
            valid_features += 1
        except Exception:
            continue
    if valid_features == 0:
        raise ValueError("No valid Polygon or MultiPolygon features were found.")
    SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    dest = SPATIAL_DIR / filename
    dest.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return {"path": str(dest), "feature_count": len(obj["features"]), "valid_polygon_count": valid_features}
