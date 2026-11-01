import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import mapping, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from siteiq import location


def test_parse_coordinate_text_lat_lon():
    assert location.parse_coordinate_text("12.871003, 77.569919") == (12.871003, 77.569919)
    assert location.parse_coordinate_text("lat 12.871003 lon 77.569919") is None
    assert location.parse_coordinate_text("95, 181") is None


def test_extract_coordinates_from_google_maps_at_url():
    result = location.coordinates_from_map_url("https://www.google.com/maps/@12.871003,77.569919,16z", resolve_short_link=False)
    assert result["coordinates"] == (12.871003, 77.569919)
    assert result["method"] == "coordinates_embedded_in_map_url"


def test_extract_coordinates_from_google_maps_place_data():
    result = location.coordinates_from_map_url("https://www.google.com/maps/place/foo/data=!3d12.871003!4d77.569919", resolve_short_link=False)
    assert result["coordinates"] == (12.871003, 77.569919)


def test_infer_route_for_bengaluru_profile_is_provisional():
    result = location.infer_approval_route(2200, "Residential apartments", "bengaluru_rmp2015", "Not sure / needs confirmation")
    assert result["suggested_value"] == "New single-plot approval under Chapter 6-A"
    assert result["status"] == "provisional_candidate"
    assert "Verify plot identity" in result["reason"]


def test_infer_route_does_not_guess_for_unconfigured_authority():
    result = location.infer_approval_route(2200, "Residential apartments", "mysuru_development_authority", "Not sure / needs confirmation")
    assert result["suggested_value"] == "Not sure / needs confirmation"
    assert result["status"] == "not_configured_for_authority"


def test_spatial_layer_identifies_zone_and_authority(tmp_path):
    # The point is (77.57, 12.87), GeoJSON geometry coordinates are [lon, lat].
    authority_path = tmp_path / "authority_boundaries.geojson"
    zone_path = tmp_path / "land_use_zones.geojson"
    feature = {
        "type": "Feature",
        "properties": {"authority_key": "bengaluru_rmp2015", "authority_name": "Test Bengaluru Profile", "source_title": "Test official map", "source_url": "https://example.invalid", "source_date": "2026-01-01"},
        "geometry": mapping(box(77.56, 12.86, 77.58, 12.88)),
    }
    authority_path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    zfeature = {
        "type": "Feature",
        "properties": {"zone_name": "Residential (Main)", "source_title": "Test land use", "source_url": "https://example.invalid/zone", "source_date": "2026-01-01"},
        "geometry": mapping(box(77.565, 12.865, 77.575, 12.875)),
    }
    zone_path.write_text(json.dumps({"type": "FeatureCollection", "features": [zfeature]}), encoding="utf-8")
    result = location.identify_spatial_context(12.871, 77.569, authority_path, zone_path)
    assert result["authority"]["status"] == "matched_polygon_layer"
    assert result["authority"]["match"]["value"] == "bengaluru_rmp2015"
    assert result["zone"]["status"] == "matched_polygon_layer"
    assert result["zone"]["match"]["value"] == "Residential (Main)"


def test_spatial_overlap_with_equally_specific_different_zones_is_flagged(tmp_path):
    zone_path = tmp_path / "land_use_zones.geojson"
    features = []
    for zone_name in ["Commercial", "Industrial"]:
        features.append({
            "type": "Feature",
            "properties": {"zone_name": zone_name},
            "geometry": mapping(box(77.56, 12.86, 77.58, 12.88)),
        })
    zone_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    result = location._point_matches(zone_path, 12.871, 77.569, "zone")
    assert result["status"] == "ambiguous_polygon_match"
    assert result["match"] is None


def test_save_geojson_layer_requires_valid_polygon(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "SPATIAL_DIR", tmp_path)
    payload = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"zone_name": "Residential (Main)"},
        "geometry": mapping(box(77.56, 12.86, 77.58, 12.88)),
    }]}
    result = location.save_geojson_layer("land_use_zones.geojson", json.dumps(payload).encode())
    assert result["valid_polygon_count"] == 1
    assert (tmp_path / "land_use_zones.geojson").exists()


def test_save_geojson_layer_rejects_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "SPATIAL_DIR", tmp_path)
    with pytest.raises(ValueError):
        location.save_geojson_layer("land_use_zones.geojson", b'{"type":"FeatureCollection","features":[]}')


def test_auto_identification_uses_official_layer_matches_and_marks_provenance(tmp_path, monkeypatch):
    authority_path = tmp_path / "authority_boundaries.geojson"
    zone_path = tmp_path / "land_use_zones.geojson"
    authority_feature = {
        "type": "Feature",
        "properties": {"authority_key": "bengaluru_rmp2015", "authority_name": "Configured Bengaluru profile", "source_title": "Official boundary", "source_url": "https://example.invalid/authority", "source_date": "2026-10-01"},
        "geometry": mapping(box(77.56, 12.86, 77.58, 12.88)),
    }
    zone_feature = {
        "type": "Feature",
        "properties": {"zone_name": "Residential Main", "source_title": "Official land use", "source_url": "https://example.invalid/land-use", "source_date": "2026-10-01"},
        "geometry": mapping(box(77.565, 12.865, 77.575, 12.875)),
    }
    authority_path.write_text(json.dumps({"type": "FeatureCollection", "features": [authority_feature]}), encoding="utf-8")
    zone_path.write_text(json.dumps({"type": "FeatureCollection", "features": [zone_feature]}), encoding="utf-8")
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {"display_name": "Test address, Bengaluru", "address": {"city": "Bengaluru", "state": "Karnataka"}, "source": "mock reverse geocode"})
    result = location.auto_identify_site(
        coordinates_text="12.871, 77.569", site_area_m2=2200,
        proposed_use="Residential apartments", current_approval_path="Not sure / needs confirmation",
        authority_layer=authority_path, zone_layer=zone_path,
    )
    assert result["authority"]["status"] == "matched_polygon_layer"
    assert result["suggested_authority_key"] == "bengaluru_rmp2015"
    assert result["zone"]["value"] == "Residential (Main)"
    assert result["zone"]["status"] == "matched_polygon_layer"
    assert result["approval_route"]["status"] == "provisional_candidate"


def test_auto_identification_does_not_guess_zone_from_city_label(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {"display_name": "Bengaluru, Karnataka", "address": {"city": "Bengaluru", "state": "Karnataka"}, "source": "mock reverse geocode"})
    empty_authority = tmp_path / "no_authority.geojson"
    empty_zone = tmp_path / "no_zone.geojson"
    result = location.auto_identify_site(
        coordinates_text="12.871, 77.569", site_area_m2=2200,
        proposed_use="Residential apartments", current_approval_path="Not sure / needs confirmation",
        authority_layer=empty_authority, zone_layer=empty_zone,
    )
    assert result["authority"]["status"] == "provisional_geocoder_candidate"
    assert result["suggested_authority_key"] == "bengaluru_rmp2015"
    assert result["zone"]["value"] == "Not verified"
    assert result["zone"]["status"] == "layer_not_installed"
    assert result["approval_route"]["status"] == "provisional_candidate"


def test_kanakapura_locality_is_provisional_candidate_not_verified_boundary():
    result = location._locality_candidate({
        "display_name": "Attihalli, Kanakapura Taluk, Bengaluru South, Karnataka, India",
        "address": {"village": "Attihalli", "county": "Kanakapura Taluk", "state": "Karnataka"},
    })
    assert result["key"] == "kanakapura_planning_authority"
    assert result["status"] == "provisional_geocoder_candidate"
    assert "does not prove" in result["reason"].lower()


def test_auto_identify_attihalli_returns_relevant_official_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {
        "display_name": "Attihalli, Kanakapura Taluk, Bengaluru South, Karnataka, India",
        "address": {"village": "Attihalli", "county": "Kanakapura Taluk", "state": "Karnataka"},
        "source": "mock reverse geocode",
    })
    result = location.auto_identify_site(
        coordinates_text="12.511506, 77.323792", site_area_m2=2200,
        proposed_use="Residential apartments", current_approval_path="Not sure / needs confirmation",
        authority_layer=tmp_path / "no_authority.geojson", zone_layer=tmp_path / "no_zone.geojson",
    )
    assert result["suggested_authority_key"] == "kanakapura_planning_authority"
    assert result["authority"]["status"] == "provisional_geocoder_candidate"
    sources = result["public_sources"]
    assert any("Kanakapura" in source["title"] for source in sources)
    assert all(source["queryable_geometry"] is False for source in sources)
    assert result["zone"]["value"] == "Not verified"


def test_hoskote_locality_candidate_precedes_bengaluru_district_label():
    result = location._locality_candidate({
        "display_name": "Near Hoskote, Bengaluru Rural, Karnataka, India",
        "address": {"town": "Hoskote", "county": "Bengaluru Rural", "state": "Karnataka"},
    })
    assert result["key"] == "hoskote_planning_authority"
    assert result["status"] == "provisional_geocoder_candidate"
    assert "does not prove" in result["reason"].lower()


def test_hoskote_auto_identification_surfaces_hoskote_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {
        "display_name": "Near Hoskote, Bengaluru Rural, Karnataka, India",
        "address": {"town": "Hoskote", "county": "Bengaluru Rural", "state": "Karnataka"},
        "source": "mock reverse geocode",
    })
    result = location.auto_identify_site(
        coordinates_text="13.0733543, 77.7823976", site_area_m2=20654,
        proposed_use="Residential apartments", current_approval_path="Not sure / needs confirmation",
        authority_layer=tmp_path / "no_authority.geojson", zone_layer=tmp_path / "no_zone.geojson",
    )
    assert result["suggested_authority_key"] == "hoskote_planning_authority"
    assert result["authority"]["status"] == "provisional_geocoder_candidate"
    assert any("Hoskote" in source["title"] for source in result["public_sources"])
    assert result["zone"]["value"] == "Not verified"
    assert result["approval_route"]["status"] == "provisional_route_candidate"
    assert "group-housing" in result["approval_route"]["reason"].lower() or "group housing" in result["approval_route"]["reason"].lower()


def test_hoskote_authority_key_is_supported_for_installed_official_polygon(tmp_path, monkeypatch):
    authority_path = tmp_path / "authority_boundaries.geojson"
    zone_path = tmp_path / "land_use_zones.geojson"
    authority_feature = {
        "type": "Feature",
        "properties": {"authority_key": "hoskote_planning_authority", "authority_name": "Hoskote Planning Authority", "source_title": "Verified authority boundary", "source_url": "https://example.invalid/hpa", "source_date": "2026-10-01"},
        "geometry": mapping(box(77.78, 13.07, 77.79, 13.08)),
    }
    authority_path.write_text(json.dumps({"type": "FeatureCollection", "features": [authority_feature]}), encoding="utf-8")
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {"display_name": "Hoskote, Karnataka", "address": {"town": "Hoskote"}, "source": "mock"})
    result = location.auto_identify_site(
        coordinates_text="13.0733543, 77.7823976", site_area_m2=20654,
        proposed_use="Residential apartments", current_approval_path="Not sure / needs confirmation",
        authority_layer=authority_path, zone_layer=zone_path,
    )
    assert result["authority"]["status"] == "matched_polygon_layer"
    assert result["suggested_authority_key"] == "hoskote_planning_authority"


def test_map_link_takes_precedence_over_stale_typed_coordinates(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "coordinates_from_map_url", lambda url, resolve_short_link=True: {
        "coordinates": (13.0733543, 77.7823976),
        "resolved_url": "https://www.google.com/maps/place/example/@13.0733543,77.7823976,17z/data=!3d13.0733543!4d77.7823976",
        "method": "expanded_map_link",
        "warning": None,
    })
    monkeypatch.setattr(location, "reverse_geocode", lambda lat, lon: {
        "display_name": "Hoskote, Karnataka, India",
        "address": {"town": "Hoskote", "state": "Karnataka"},
        "source": "mock reverse geocode",
    })
    result = location.auto_identify_site(
        address="Vijaynagar Main Road, Tumakuru, Karnataka",
        map_url="https://maps.app.goo.gl/example-hoskote",
        coordinates_text="13.3297678, 77.1121664",
        site_area_m2=20000,
        proposed_use="Residential apartments",
        road_width_m=36,
        current_approval_path="Not sure / needs confirmation",
        authority_layer=tmp_path / "no_authority.geojson",
        zone_layer=tmp_path / "no_zone.geojson",
    )
    assert result["coordinates"]["latitude"] == pytest.approx(13.0733543)
    assert result["coordinates"]["longitude"] == pytest.approx(77.7823976)
    assert result["location_source"] == "Google Maps link"
    assert result["input_coordinate_comparison"]["mismatch"] is True
    assert result["input_coordinate_comparison"]["distance_km"] > 30
    assert result["suggested_authority_key"] == "hoskote_planning_authority"


def test_unresolvable_map_link_fails_closed_instead_of_using_stale_coordinates(monkeypatch, tmp_path):
    monkeypatch.setattr(location, "coordinates_from_map_url", lambda url, resolve_short_link=True: {
        "coordinates": None, "resolved_url": url, "method": None,
        "warning": "Test short-link resolution failure",
    })
    with pytest.raises(RuntimeError, match="did not use the existing coordinate field"):
        location.auto_identify_site(
            address="Tumakuru, Karnataka",
            map_url="https://maps.app.goo.gl/unresolvable",
            coordinates_text="13.3297678, 77.1121664",
            site_area_m2=20000,
            proposed_use="Residential apartments",
            current_approval_path="Not sure / needs confirmation",
            authority_layer=tmp_path / "no_authority.geojson",
            zone_layer=tmp_path / "no_zone.geojson",
        )


def test_google_maps_pin_coordinates_precede_viewport_center():
    result = location.coordinates_from_map_url(
        "https://www.google.com/maps/place/example/@13.000000,77.000000,16z/data=!3d13.0733543!4d77.7823976",
        resolve_short_link=False,
    )
    assert result["coordinates"] == (13.0733543, 77.7823976)
