"""The legacy Streamlit interface must start empty, never crash on blanks, and never show old results."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run_app():
    return AppTest.from_file(APP, default_timeout=120).run()


def test_opens_without_any_assumed_site():
    app = run_app()
    assert not app.exception
    assert app.selectbox(key="siteiq_authority_key").value == "other_karnataka"
    assert app.number_input(key="siteiq_site_area").value == 0
    assert not any("Production Ready" in m.value for m in app.markdown)
    assert not [m for m in app.metric if m.label == "Maximum Base FAR"]


def test_zero_height_does_not_crash():
    app = run_app()
    app.number_input(key="siteiq_opt0_height").set_value(0.0).run()
    assert not app.exception


def test_changing_an_input_clears_the_result():
    app = run_app()
    app.selectbox(key="siteiq_authority_key").set_value("bengaluru_rmp2015").run()
    app.selectbox(key="siteiq_land_use_category").set_value("Residential (Main)").run()
    app.number_input(key="siteiq_site_area").set_value(2200.0).run()
    app.number_input(key="siteiq_road_width").set_value(18.0).run()
    next(b for b in app.button if "Run regulatory" in b.label).click().run()
    assert not app.exception
    assert app.session_state["siteiq_report"]["maximum_far"] == 2.25
    app.number_input(key="siteiq_road_width").set_value(6.0).run()
    assert "siteiq_report" not in app.session_state
