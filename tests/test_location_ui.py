from siteiq.location_ui import apply_location_identification


def _fake_identify(**kwargs):
    _fake_identify.kwargs = kwargs
    return {
        "coordinates": {"text": "12.8710030, 77.5699190"},
        "geocoded_address": "Test locality, Bengaluru, Karnataka",
        "authority": {"status": "provisional_geocoder_candidate"},
        "suggested_authority_key": "bengaluru_rmp2015",
        "zone": {"status": "layer_not_installed", "value": "Not verified"},
        "approval_route": {
            "suggested_value": "New single-plot approval under Chapter 6-A",
            "status": "provisional_candidate",
        },
    }


def test_location_callback_state_uses_actual_area_widget_and_prefills_fields():
    state = {
        "siteiq_address": "",
        "siteiq_map_url": "https://maps.app.goo.gl/example",
        "siteiq_coordinates": "12.871003, 77.569919",
        "siteiq_site_area": 2200,
        "siteiq_road_width": 18.5,
        "siteiq_proposed_use": "Residential apartments",
        "siteiq_authority_key": "other_karnataka",
        "siteiq_official_zone": "Not verified",
        "siteiq_approval_path": "Not sure / needs confirmation",
        "siteiq_report": {"old": "report"},
    }

    result = apply_location_identification(state, {"bengaluru_rmp2015", "other_karnataka"}, _fake_identify)

    assert _fake_identify.kwargs["site_area_m2"] == 2200.0
    assert _fake_identify.kwargs["road_width_m"] == 18.5
    assert state["siteiq_coordinates"] == "12.8710030, 77.5699190"
    assert state["siteiq_address"] == "Test locality, Bengaluru, Karnataka"
    assert state["siteiq_authority_key"] == "bengaluru_rmp2015"
    assert state["siteiq_approval_path"] == "New single-plot approval under Chapter 6-A"
    assert "siteiq_report" not in state
    assert state["siteiq_location_error"] == ""
    assert result["suggested_authority_key"] == "bengaluru_rmp2015"


def test_boundary_area_is_used_when_boundary_area_mode_is_active():
    state = {
        "siteiq_address": "Bengaluru",
        "siteiq_coordinates": "12.871,77.569",
        "siteiq_site_area": 2200,
        "siteiq_road_width": 18.5,
        "siteiq_boundary": {"area_m2": 2234.25, "use_computed_area": True},
    }
    apply_location_identification(state, set(), _fake_identify)
    assert _fake_identify.kwargs["site_area_m2"] == 2234.25


def test_manual_area_is_used_when_boundary_not_selected_for_far():
    state = {
        "siteiq_site_area": 2222,
        "siteiq_road_width": 18.5,
        "siteiq_boundary": {"area_m2": 2234.25, "use_computed_area": False},
    }
    apply_location_identification(state, set(), _fake_identify)
    assert _fake_identify.kwargs["site_area_m2"] == 2222.0


def test_applied_kml_location_overrides_stale_address_coordinates_and_map_link():
    state = {
        "siteiq_address": "Vijaynagar Main Road, Tumakuru, Karnataka",
        "siteiq_map_url": "https://maps.app.goo.gl/old-location",
        "siteiq_coordinates": "13.3297678, 77.1121664",
        "siteiq_site_area": 1,
        "siteiq_road_width": 36,
        "siteiq_proposed_use": "Residential apartments",
        "siteiq_boundary": {
            "source_type": "kml",
            "source_file": "Hoskote_site.kml",
            "source_fingerprint": "abc123",
            "source_location_point_wgs84": [77.7823976, 13.0733543],
            "area_m2": 20654,
            "use_computed_area": True,
        },
    }
    apply_location_identification(state, {"hoskote_planning_authority", "other_karnataka"}, _fake_identify)
    assert _fake_identify.kwargs["coordinates_text"] == "13.0733543, 77.7823976"
    assert _fake_identify.kwargs["map_url"] == ""
    assert _fake_identify.kwargs["site_area_m2"] == 20654.0
    assert state["siteiq_location_coordinate_source"] == "Applied KML boundary location point"


def test_selected_kml_location_override_precedes_old_active_boundary():
    state = {
        "siteiq_address": "Tumakuru",
        "siteiq_coordinates": "13.3297678, 77.1121664",
        "siteiq_site_area": 2000,
        "siteiq_road_width": 18,
        "siteiq_boundary": {
            "source_type": "kml", "source_file": "old.kml",
            "source_fingerprint": "oldhash", "source_location_point_wgs84": [77.11, 13.33],
            "area_m2": 2000, "use_computed_area": True,
        },
        "siteiq_kml_lookup_override": {
            "point_wgs84": [77.7823976, 13.0733543], "source_file": "new_hoskote.kml",
            "source_fingerprint": "newhash",
        },
    }
    apply_location_identification(state, {"hoskote_planning_authority", "other_karnataka"}, _fake_identify)
    assert _fake_identify.kwargs["coordinates_text"] == "13.0733543, 77.7823976"
    assert _fake_identify.kwargs["site_area_m2"] == 2000.0
    assert state["siteiq_location_coordinate_source"] == "Selected KML boundary lookup point"


def test_failed_location_identification_clears_stale_detection_and_report():
    def _raise_lookup(**kwargs):
        raise RuntimeError("Map link failed; stale coordinates were not used")

    state = {
        "siteiq_address": "Tumakuru",
        "siteiq_map_url": "https://maps.app.goo.gl/unresolvable",
        "siteiq_coordinates": "13.3297678, 77.1121664",
        "siteiq_site_area": 20000,
        "siteiq_road_width": 36,
        "siteiq_location_detection": {"suggested_authority_key": "bengaluru_rmp2015"},
        "siteiq_report": {"old": "report"},
    }
    try:
        apply_location_identification(state, set(), _raise_lookup)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected lookup error")
    assert "siteiq_location_detection" not in state
    assert "siteiq_report" not in state
