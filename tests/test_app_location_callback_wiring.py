from pathlib import Path


def test_location_identification_uses_on_click_callback_to_prefill_widget_keys():
    app_text = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert 'on_click=_identify_site_callback' in app_text
    assert 'if identify_clicked:' not in app_text
    assert 'apply_location_identification(st.session_state, set(authority_labels))' in app_text
    assert 'authority_labels.get(auth.get("key"), auth.get("key"))' in app_text


def test_kml_location_only_action_is_available_and_unapplied_file_is_flagged():
    app_text = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "Use selected KML location for authority lookup" in app_text
    assert "uploaded/selected but has not been applied as the active boundary" in app_text
    assert "source_location_point_wgs84" in app_text


def test_single_kml_feature_auto_queues_location_lookup():
    app_text = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "len(candidates) == 1" in app_text
    assert "siteiq_kml_location_auto_prefill_fingerprint" in app_text
    assert "Selected KML boundary lookup point" in app_text
