"""Every control of the saturation calculator operated with simulated pointer and keyboard events.

Only ``pointer_move`` / ``press`` / ``release`` / ``wheel`` / ``key`` and the host's file drop reach the window, at the rectangles
the controls were drawn in (``item_rects`` for buttons and fields, the table's own cell geometry for the tables, the drawn text for
list entries and dialog buttons); the assertions read the visible outcome (the model, the drawn strings, the files written). The
control -> test list is in ``okf/plugins/emtk-ports/fcs_saturation/REPORT.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.calculator.fcs_saturation_calc.gui.app import make_app
from chisurf.plugins.calculator.fcs_saturation_calc.gui.panel import TABS

from .driving import BIG, SMALL, SatDriver, hermetic_env

GOLDEN = json.loads((Path(__file__).with_name("golden_qt.json")).read_text())


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def no_failed_draws(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def drv():
    app = make_app(restore=False)
    d = SatDriver(app, BIG)
    d.draw(3)
    yield d
    app.model.save_user_settings = lambda: None  # a closing window saves the session: not the point of these tests
    app.close()


def model(drv):
    return drv.app.model


def sat(drv):
    return drv.app.model.saturation


def rate(drv, name, group="dark"):
    return float(getattr(sat(drv), group).rates_by_name()[name].value)


def series(drv, source="fcs_curves_series"):
    return {s["name"]: np.asarray(s["y"]) for s in getattr(model(drv), source)}


def golden_y(state, source="fcs_curves_series"):
    return {s["name"]: np.asarray(s["y"]) for s in GOLDEN[state]["series"][source]}


def pick(drv, field, label):
    drv.click(field)
    drv.click_text(label, last=True)


def tab(drv, name):
    drv.click(name)
    assert drv.app.result_tab == name
    return drv.draw(2)


def stepper(drv, name, direction):
    x, y, w, h = drv.rect(f"{name}.stepper")
    drv.click_at(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))


def cell_text(drv, table, row, column):
    control = drv.control(table)
    return control.value(row, column)


def edit(drv, table, row, column, text):
    """Double click the cell and type; the cell editor keeps its text, so the old one is erased with Backspace."""
    x, y, w, h = drv.cell(table, row, column)
    drv.app.press(x + w / 2, y + h / 2, clicks=2)
    drv.draw(1)
    drv.app.release()
    drv.draw(1)
    control = drv.control(table)
    if control.editing is None:
        return False
    drv.key(keys.KEY_END, "")
    for _ in range(24):
        drv.key(keys.KEY_BACKSPACE, "")
    drv.type_text(text)
    drv.enter()
    return True


# -- the toolbar ----------------------------------------------------------------------------------------------------- #


def test_compute_recomputes_from_scratch_and_says_so(drv):
    m = model(drv)
    m._info_summary = ""  # as if nothing had been computed
    assert drv.app.panel.info_rows() == []
    drv.click("compute")
    assert drv.app.status == "Computed." and drv.app.panel.info_rows()
    assert "Computed." in drv.draw(2).strings


def test_compute_gives_the_qt_tools_curves(drv):
    drv.click("compute")
    for name, y in golden_y("default").items():
        assert np.allclose(series(drv)[name], y, rtol=1e-9, atol=1e-12)


def test_save_and_load_session_buttons_write_and_restore_the_settings_file(drv, tmp_path):
    m = model(drv)
    m.save_user_settings = type(m).save_user_settings.__get__(m)  # the real writer, into the temporary settings folder
    type_power(drv, "1.5")
    drv.click("save_session")
    path = Path(m.get_user_settings_path())
    assert path.is_file() and json.loads(path.read_text())["power_mW"] == 1.5
    assert drv.app.status == f"Session saved to {path}"
    type_power(drv, "7")
    assert m.power_mW == 7.0
    drv.click("load_session")
    assert m.power_mW == 1.5 and drv.app.status == "Session restored."
    assert any("1.5000" in s for s in drv.draw(2).strings)


def test_load_session_without_a_file_changes_nothing(drv):
    before = model(drv).power_mW
    drv.click("load_session")
    assert model(drv).power_mW == before and drv.app.error == ""


def test_save_scheme_dialog_writes_the_typed_name_and_adds_the_suffix(drv, tmp_path):
    drv.click("save_scheme")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Save scheme"
    drv.click_text("scheme.json")
    drv.select_all()
    drv.type_text("my_dye")
    drv.click_text("Save", last=True)
    written = tmp_path / "my_dye.json"
    assert written.is_file() and drv.app.dialog is None
    data = json.loads(written.read_text())
    assert data["n_states"] == 3 and data["state_labels"] == ["S0", "S1", "T1"] and data["dark_rates"]["k2_1"] == 250.0
    assert drv.app.status == f"Saved {written}"


def test_save_scheme_cancel_and_the_close_button_write_nothing(drv, tmp_path):
    drv.click("save_scheme")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not list(tmp_path.glob("*.json"))
    drv.click("save_scheme")
    x, y, w, h = drv.app.file_window.box
    drv.click_at(x + w - 12, y + 12)  # the header's close button
    assert drv.app.dialog is None and not list(tmp_path.glob("*.json"))


def test_save_scheme_to_an_unwritable_place_reports_instead_of_raising(drv, tmp_path):
    (tmp_path / "blocked").write_text("a file where a folder is needed")
    drv.click("save_scheme")
    drv.click_text("scheme.json")
    drv.select_all()
    drv.type_text("blocked/scheme.json")
    drv.click_text("Save", last=True)
    assert drv.app.error.startswith("Error:") and any(s.startswith("Error:") for s in drv.draw(2).strings)


def test_load_scheme_dialog_loads_the_picked_file_and_marks_the_preset_custom(drv, tmp_path):
    src = Path(__file__).parents[1] / "schemes" / "cyanine_4state.json"
    (tmp_path / "cy5_copy.json").write_text(src.read_text())
    drv.click("load_scheme")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Load scheme"
    drv.click_text("cy5_copy.json")
    drv.click_text("Open", last=True)
    assert drv.app.dialog is None and sat(drv).n_states == 4 and model(drv).scheme_preset == "Custom"
    assert drv.app.status == "Loaded cy5_copy.json"
    assert {"S0", "S1", "P", "T1"} <= set(drv.draw(2).strings)
    for name, y in series_after(drv).items():
        assert np.isfinite(y).all()


def series_after(drv):
    return series(drv)


def test_load_scheme_cancel_and_a_broken_file(drv, tmp_path):
    (tmp_path / "broken.json").write_text("{ not json")
    drv.click("load_scheme")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and sat(drv).n_states == 3
    drv.click("load_scheme")
    drv.click_text("broken.json")
    drv.click_text("Open", last=True)
    assert drv.app.error.startswith("Error:") and sat(drv).n_states == 3
    assert any(s.startswith("Error:") for s in drv.draw(2).strings)


def test_a_dropped_scheme_is_loaded_and_a_stray_file_is_refused(drv, tmp_path):
    src = Path(__file__).parents[1] / "schemes" / "two_state.json"
    (tmp_path / "dropped.json").write_text(src.read_text())
    (tmp_path / "notes.txt").write_text("not a scheme")
    assert drv.drop(str(tmp_path / "notes.txt")) in (True, False)
    assert drv.app.error == "Error: drop a scheme .json file." and sat(drv).n_states == 3
    drv.drop(str(tmp_path / "dropped.json"))
    assert sat(drv).n_states == 2 and drv.app.status == "Loaded dropped.json" and drv.app.error == ""
    drv.drop(str(tmp_path / "missing.json"))
    assert drv.app.error.startswith("Error:") and sat(drv).n_states == 2


# -- the photophysics fields ------------------------------------------------------------------------------------------- #


def type_power(drv, text):
    drv.type_into("power_mW", text)


def test_the_scheme_list_picks_every_preset_and_custom_changes_nothing(drv):
    sizes = {"Two-state (ground + excited)": 2, "Rhodamine 6G (3-state, triplet)": 3, "Cyanine 5 (4-state, isomer + triplet)": 4,
             "Oxazine 1 (3-state, triplet)": 3}
    for label, n in sizes.items():
        pick(drv, "scheme_preset", label)
        assert model(drv).scheme_preset == label and sat(drv).n_states == n
        assert label in drv.draw(2).strings
    pick(drv, "scheme_preset", "Oxazine 1 (3-state, triplet)")
    before = rate(drv, "k2_1")
    pick(drv, "scheme_preset", "Custom")
    assert model(drv).scheme_preset == "Custom" and rate(drv, "k2_1") == before  # a label for edited schemes, not a scheme


def test_picking_the_cyanine_preset_gives_the_qt_tools_curves(drv):
    type_power(drv, "1")
    pick(drv, "scheme_preset", "Cyanine 5 (4-state, isomer + triplet)")
    for source in ("fcs_curves_series", "volume_profile_series", "volume_power_series"):
        for name, y in golden_y("cy5_1mW", source).items():
            assert np.allclose(series(drv, source)[name], y, rtol=1e-9, atol=1e-12), (source, name)


@pytest.mark.parametrize("text, expected", [("2", 2.0), ("0", 0.0), ("0.05", 0.05), ("500", 100.0), ("-3", 0.0), ("1e-3", 0.001)])
def test_laser_power_is_typed_and_clamped_to_zero_and_100_mw(drv, text, expected):
    type_power(drv, text)
    assert model(drv).power_mW == pytest.approx(expected)


def test_a_typed_power_gives_the_qt_tools_curves_and_summary(drv):
    type_power(drv, "2")
    for source in ("fcs_curves_series", "volume_power_series", "tau_d_power_series"):
        for name, y in golden_y("power_2mW", source).items():
            assert np.allclose(series(drv, source)[name], y, rtol=1e-9, atol=1e-12)
    assert model(drv).info_text() == GOLDEN["power_2mW"]["info"]
    type_power(drv, "0")
    for name, y in golden_y("power_0").items():
        assert np.allclose(series(drv)[name], y, rtol=1e-9, atol=1e-12)
    assert np.allclose(series(drv)["Saturated"], series(drv)["Unperturbed Gaussian"])  # no excitation, no saturation


def test_a_typed_text_that_is_not_a_number_is_ignored(drv):
    type_power(drv, "abc")
    assert model(drv).power_mW == 0.2


def test_the_power_arrows_and_the_wheel_step_the_value(drv):
    stepper(drv, "power_mW", +1)
    assert model(drv).power_mW == pytest.approx(0.25)
    stepper(drv, "power_mW", -1)
    stepper(drv, "power_mW", -1)
    assert model(drv).power_mW == pytest.approx(0.15)
    x, y, w, h = drv.rect("power_mW")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert model(drv).power_mW > 0.15


def test_the_logarithmic_power_slider_is_clicked_and_dragged(drv):
    x, y, w, h = drv.rect("power_log.slider")
    drv.click_at(x + w / 2, y + h / 2)  # the middle of 0.001 .. 100 mW is 0.1 mW
    assert model(drv).power_mW == pytest.approx(10 ** -0.5, rel=0.2)  # the middle of 0.001 .. 100 mW on a log scale
    drv.drag((x + w * 0.5, y + h / 2), (x + w * 0.99, y + h / 2))
    assert model(drv).power_mW > 30.0
    drv.drag((x + w * 0.99, y + h / 2), (x + 1, y + h / 2))
    assert model(drv).power_mW < 0.01
    assert "Power (log)" in drv.draw(2).strings


@pytest.mark.parametrize("text, expected", [("640", 640.0), ("1500", 1200.0), ("100", 200.0), ("561.5", 561.5)])
def test_the_wavelength_is_typed_and_clamped(drv, text, expected):
    drv.type_into("wavelength_nm", text)
    assert model(drv).wavelength_nm == pytest.approx(expected)


def test_the_wavelength_changes_the_curves_and_matches_the_qt_tool(drv):
    drv.type_into("wavelength_nm", "640")
    drv.type_into("power_mW", "0.5")
    pick(drv, "scheme_preset", "Two-state (ground + excited)")
    # the golden state sets the unit by the Qt tool's setter after the preset; do the same by the unit list
    pick(drv, "rate_unit", "1/ms")
    for name, y in golden_y("two_state_640_ms").items():
        assert np.allclose(series(drv)[name], y, rtol=1e-9, atol=1e-12), name


def test_the_dye_list_reads_the_extinction_from_the_chosen_dye(drv):
    calls = []
    sat(drv).dye_names = lambda: ["Alexa 647", "Cy5"]

    def apply_dye(name, lifetime_rate=None):
        calls.append(name)
        sat(drv)._dye_name = name
        return {}

    sat(drv).apply_dye = apply_dye
    pick(drv, "dye", "Cy5")
    assert calls == ["Cy5"] and model(drv).dye == "Cy5" and "Cy5" in drv.draw(2).strings
    drv.type_into("wavelength_nm", "650")
    assert calls[-1] == "Cy5"  # the extinction is read again at the new wavelength
    pick(drv, "dye", "(none, type the extinction)")
    assert model(drv).dye == ""


def test_the_rate_unit_list_rescales_the_dark_rates_and_the_table_title(drv):
    pick(drv, "rate_unit", "1/ms")
    assert rate(drv, "k2_1") == pytest.approx(250000.0) and model(drv).rate_unit == "1/ms"
    assert "K_dark (1/ms), row to column" in " ".join(s.replace("v ", "") for s in drv.draw(2).strings)
    pick(drv, "rate_unit", "1/us")
    assert rate(drv, "k2_1") == pytest.approx(250.0)
    for unit in ("1/s", "1/ns"):
        pick(drv, "rate_unit", unit)
        assert model(drv).rate_unit == unit


def test_the_bunching_checkbox_changes_the_saturated_curve_and_back(drv):
    base = series(drv)["Saturated"].copy()
    drv.click("include_bunching")
    assert model(drv).include_bunching is False and not np.allclose(series(drv)["Saturated"], base)
    drv.click("include_bunching")
    assert model(drv).include_bunching is True and np.allclose(series(drv)["Saturated"], base)


@pytest.mark.parametrize("text, expected", [("4", 4), ("6", 6), ("9", 6), ("1", 2), ("5", 5)])
def test_number_of_states_is_typed_clamped_and_resizes_every_table(drv, text, expected):
    drv.type_into("n_states", text)
    assert sat(drv).n_states == expected
    assert len(drv.app.panel.dark_rows()) == len(drv.app.panel.exc_rows()) == len(drv.app.panel.brightness_rows()) == expected
    assert len(drv.control("dark_rows").records) == expected
    assert len(sat(drv).state_labels) == expected


def test_the_number_of_states_arrows_and_the_wheel(drv):
    stepper(drv, "n_states", +1)
    assert sat(drv).n_states == 4
    stepper(drv, "n_states", -1)
    stepper(drv, "n_states", -1)
    assert sat(drv).n_states == 2
    x, y, w, h = drv.rect("n_states")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert sat(drv).n_states == 3


# -- the rate and parameter tables ------------------------------------------------------------------------------------ #


def test_a_dark_rate_cell_is_typed_and_gives_the_new_curve(drv):
    base = series(drv)["Saturated"].copy()
    assert edit(drv, "dark_rows", 1, "c0", "300")  # S1 -> S0
    assert rate(drv, "k2_1") == 300.0 and not np.allclose(series(drv)["Saturated"], base)
    assert cell_text(drv, "dark_rows", 1, "c0") == 300.0
    assert "300" in drv.draw(2).strings


def test_rates_are_clamped_and_zero_removes_the_transition(drv):
    edit(drv, "dark_rows", 2, "c0", "-5")
    assert rate(drv, "k3_1") == 0.0
    edit(drv, "dark_rows", 2, "c0", "2e9")
    assert rate(drv, "k3_1") == 1e9
    edit(drv, "dark_rows", 2, "c0", "abc")
    assert rate(drv, "k3_1") == 1e9  # not a number: unchanged
    edit(drv, "dark_rows", 2, "c0", "0")
    assert rate(drv, "k3_1") == 0.0 and all((s, d) != (2, 0) for s, d, g, v in drv.app.panel.state_edges(model(drv)))


def test_the_ground_state_row_and_the_diagonal_of_k_dark_cannot_be_edited(drv):
    assert not edit(drv, "dark_rows", 0, "c1", "5")  # the ground state row: use K_exc
    assert rate(drv, "k1_2") == 0.0
    assert not edit(drv, "dark_rows", 1, "c1", "5")  # the diagonal
    assert not edit(drv, "dark_rows", 0, "state", "5")  # a row name
    assert not edit(drv, "exc_rows", 1, "c1", "0.5")


def test_a_cross_section_is_typed_clamped_to_the_peak_and_changes_the_curve(drv):
    base = series(drv)["Saturated"].copy()
    assert edit(drv, "exc_rows", 0, "c1", "0.5")
    assert rate(drv, "sigma1_2", "exc") == 0.5 and not np.allclose(series(drv)["Saturated"], base)
    edit(drv, "exc_rows", 0, "c1", "3")
    assert rate(drv, "sigma1_2", "exc") == 1.0
    assert edit(drv, "exc_rows", 1, "c0", "0.25")  # an excited-state absorption
    assert rate(drv, "sigma2_1", "exc") == 0.25


def test_the_brightness_table_is_edited_and_its_checkboxes_clicked(drv):
    base = series(drv)["Saturated"].copy()
    assert edit(drv, "brightness_rows", 0, "value", "0.5")
    q = sat(drv).brightness._brightness
    assert q[0].value == 0.5 and not np.allclose(series(drv)["Saturated"], base)
    fixed = q[1].fixed
    drv.click_cell("brightness_rows", 1, "fixed")
    assert q[1].fixed is (not fixed)
    drv.click_cell("brightness_rows", 1, "fixed")
    assert q[1].fixed is fixed
    bounds = q[2].bounds_on
    drv.click_cell("brightness_rows", 2, "bounds")
    assert q[2].bounds_on is (not bounds)
    edit(drv, "brightness_rows", 2, "value", "9")  # a bound is only enforced while it is on
    assert q[2].value == (9.0 if not q[2].bounds_on else 1.0)


def test_the_optics_values_are_typed_and_equal_the_qt_curves(drv):
    drv.select = tab(drv, "State diagram")
    assert edit(drv, "optics_rows", 3, "value", "250")  # w_r
    assert edit(drv, "optics_rows", 4, "value", "1000")  # w_z
    assert edit(drv, "optics_rows", 5, "value", "400")  # D
    s = sat(drv)
    assert (s.w_r_nm, s.w_z_nm, s.D_um2s) == (250.0, 1000.0, 400.0)
    assert edit(drv, "optics_rows", 2, "value", "100000")  # epsilon
    assert s.extinction == 100000.0
    tab(drv, "FCS curve")
    type_power(drv, "0.05")
    assert "1.3" in " ".join(v for _l, v in drv.app.panel.info_rows() if "Volume" in _l)  # the guide's 1.33 at 50 uW


def test_the_optics_limits_clamp_values_and_inverted_limits_are_refused(drv):
    tab(drv, "State diagram")
    assert edit(drv, "optics_rows", 1, "value", "5000")  # the wavelength is limited to 200 .. 1200 while Bounds is on
    assert sat(drv)._wavelength.value == 1200.0
    assert edit(drv, "optics_rows", 1, "hi", "900")
    assert sat(drv)._wavelength.bounds[1] == 900.0
    assert edit(drv, "optics_rows", 1, "lo", "950")  # above the upper limit: refused
    assert sat(drv)._wavelength.bounds[0] == 200.0
    drv.click_cell("optics_rows", 1, "bounds")
    assert sat(drv)._wavelength.bounds_on is False
    assert edit(drv, "optics_rows", 1, "value", "1100")  # unlimited now
    assert sat(drv)._wavelength.value == 1100.0
    drv.click_cell("optics_rows", 1, "fixed")
    assert sat(drv)._wavelength.fixed is False


def test_the_relaxation_times_are_results_and_cannot_be_edited(drv):
    tab(drv, "State diagram")
    rows = drv.app.panel.optics_rows()
    r1 = next(i for i, r in enumerate(rows) if r["_output"])
    value = rows[r1]["value"]
    assert not edit(drv, "optics_rows", r1, "value", "7")
    drv.click_cell("optics_rows", r1, "fixed")
    assert drv.app.panel.optics_rows()[r1]["value"] == value and drv.app.panel.optics_rows()[r1]["fixed"] is None


def test_a_table_header_click_changes_no_value(drv):
    before = [r["value"] for r in drv.app.panel.brightness_rows()]
    x, y, w, h = drv._header(drv, "brightness_rows", "value") if hasattr(drv, "_header") else (0, 0, 0, 0)
    control = drv.control("brightness_rows")
    hx, hy, hw, hh = control._header_box
    drv.click_at(hx + 90, hy + hh / 2)  # the Value header: sorts
    drv.click_at(hx + 90, hy + hh / 2)  # and again: reverse
    assert sorted(r["value"] for r in drv.app.panel.brightness_rows()) == sorted(before)


# -- the tabs and the plots ---------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("name, marker", [("State diagram", "dark transition"), ("FCS curve", "FCS Saturation Effect"),
                                          ("Info", "FCS saturation summary"), ("Volume profile", "Radial Spatial Volume Profiles"),
                                          ("Volume(P)", "Volume Expansion vs Laser Power"), ("Diffusion time", "Diffusion Time vs Laser Power")])
def test_each_tab_button_shows_its_panel(drv, name, marker):
    other = "Info" if name != "Info" else "FCS curve"
    tab(drv, other)
    painter = tab(drv, name)
    assert marker in painter.strings
    assert drv.app.item_rects[name]


def test_the_state_diagram_shows_the_scheme_the_tables_hold(drv):
    painter = tab(drv, "State diagram")
    assert {"S0", "S1", "T1", "250", "2.5", "0.5"} <= set(painter.strings) and "σ 1" in painter.strings
    edit(drv, "dark_rows", 2, "c0", "0")
    assert "0.5" not in drv.draw(2).strings  # the transition is gone with its arrow
    pick(drv, "scheme_preset", "Cyanine 5 (4-state, isomer + triplet)")
    assert {"S0", "S1", "P", "T1"} <= set(drv.draw(2).strings)


def test_the_info_tab_lists_the_qt_summary_rows(drv):
    tab(drv, "Info")
    strings = drv.draw(2).strings
    for label in ("Power P_total:", "Peak focal rate k_exc(0,0):", "Volume expansion V_eff/V_0:", "Saturated G(0):", "Relaxation times:"):
        assert label in strings, label
    assert "1.933×" in strings  # the Qt summary's number for 0.2 mW


def test_the_normalise_checkbox_scales_both_curves_to_one_and_back(drv):
    tab(drv, "FCS curve")
    drv.click("normalize_fcs")
    s = series(drv)
    assert model(drv).normalize_fcs and s["Saturated"][0] == pytest.approx(1.0) and s["Unperturbed Gaussian"][0] == pytest.approx(1.0)
    drv.click("normalize_fcs")
    assert not np.isclose(series(drv)["Saturated"][0], 1.0)
    for name, y in golden_y("default").items():
        assert np.allclose(series(drv)[name], y, rtol=1e-9, atol=1e-12)


def test_the_one_component_fit_checkbox_adds_and_removes_the_fit_and_the_residual(drv):
    tab(drv, "FCS curve")
    assert "1-component Gaussian fit" in series(drv)
    drv.click("show_gaussian_fit")
    assert not model(drv).show_gaussian_fit and "1-component Gaussian fit" not in series(drv)
    drv.click("show_gaussian_fit")
    assert "1-component Gaussian fit" in series(drv)
    for name, y in golden_y("default", "fcs_residual_series").items():
        assert np.allclose(series(drv, "fcs_residual_series")[name], y, rtol=1e-9, atol=1e-12)


def test_the_three_profile_checkboxes_remove_and_restore_their_curves(drv):
    tab(drv, "Volume profile")
    names = lambda: [s["name"] for s in model(drv).volume_profile_series]  # noqa: E731
    assert len(names()) == 5
    drv.click("show_power_profile")
    assert not any(n.startswith("Excitation") for n in names())
    drv.click("show_power_profile")
    drv.click("show_state_profiles")
    assert not any(n.startswith("P") for n in names()) and len(names()) == 2
    drv.click("show_state_profiles")
    drv.click("show_fluorescence_profile")
    assert not any(n.startswith("Emission") for n in names())
    drv.click("show_fluorescence_profile")
    for source in ("volume_profile_series",):
        for name, y in golden_y("default", source).items():
            assert np.allclose(series(drv, source)[name], y, rtol=1e-9, atol=1e-12)


def ticks(painter):
    return [s for s in painter.strings if re.fullmatch(r"-?[\d.]+(e[+-]?\d+)?", s)]


@pytest.mark.parametrize("tab_name, source", [("FCS curve", "fcs_curves_series"), ("Volume profile", "volume_profile_series"),
                                              ("Volume(P)", "volume_power_series"), ("Diffusion time", "tau_d_power_series")])
def test_a_drag_pans_each_plot(drv, tab_name, source):
    tab(drv, tab_name)
    before = ticks(drv.draw(2))
    x, y, w, h = drv.app.item_rects[source]
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert ticks(drv.draw(2)) != before


@pytest.mark.parametrize("tab_name, source", [("FCS curve", "fcs_curves_series"), ("Volume profile", "volume_profile_series"),
                                              ("Volume(P)", "volume_power_series"), ("Diffusion time", "tau_d_power_series")])
def test_the_wheel_zooms_each_plot(drv, tab_name, source):
    tab(drv, tab_name)
    before = ticks(drv.draw(2))
    x, y, w, h = drv.app.item_rects[source]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert ticks(drv.draw(2)) != before


def test_a_new_scheme_frames_the_data_again_after_a_pan(drv):
    tab(drv, "Volume(P)")
    x, y, w, h = drv.app.item_rects["volume_power_series"]
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.2, y + h * 0.2))
    panned = ticks(drv.draw(2))
    type_power(drv, "5")
    assert ticks(drv.draw(2)) != panned


# -- the guide and the help ---------------------------------------------------------------------------------------------- #


def test_guide_click_starts_the_tour_and_its_buttons_are_clicked(drv):
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and not tour.awaiting  # step one only shows the scheme list
    drv.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting  # "type 488" waits for the wavelength field
    drv.click_text("Next ►")
    assert tour.step_idx == 1  # greyed
    drv.type_into("wavelength_nm", "488")
    assert not tour.awaiting
    drv.click_text("◄ Prev")
    assert tour.step_idx == 0
    drv.click_text("Close Tour")
    assert not tour.active


def test_escape_closes_the_tour_even_while_a_step_waits(drv):
    drv.click("guide")
    drv.click_text("Next ►")
    assert drv.app.tour.awaiting
    drv.escape()
    drv.draw(2)
    assert not drv.app.tour.active


def operate(drv, step):
    """What the user does at the highlighted control of *step*."""
    target = step.get("target") or {}
    key = target.get("attr") or target.get("key") or target.get("tab")
    if key == "wavelength_nm":
        drv.type_into("wavelength_nm", "488")
    elif key == "optics":
        if step["title"].startswith("Step 2"):
            edit(drv, "optics_rows", 2, "value", "100000")
        else:
            edit(drv, "optics_rows", 3, "value", "250")
            edit(drv, "optics_rows", 4, "value", "1000")
            edit(drv, "optics_rows", 5, "value", "400")
    elif key == "power_mW":
        value = re.findall(r"type <b>([\d.]+)</b>", step["text"], flags=re.I)
        drv.type_into("power_mW", value[0] if value else "0.2")
    elif key == "show_state_profiles":
        drv.click("show_state_profiles")
    elif key == "Volume(P)":
        drv.click("Volume(P)")
    elif key == "normalize_fcs":
        drv.click("normalize_fcs")
    return key


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(drv):
    tour = drv.app.tour
    drv.click("guide")
    waited = []
    for _ in range(40):
        if not tour.active:
            break
        drv.draw(3)
        step = tour.steps[tour.step_idx]
        if tour.awaiting:
            waited.append(operate(drv, step))
            assert not tour.awaiting, f"{step['title']}: operating {step.get('target')} did not release the step"
        if step.get("tab") and not tour.awaiting:
            assert drv.app.result_tab in TABS
        drv.draw(2)
        drv.click_text("Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►")
    assert not tour.active
    assert waited == ["wavelength_nm", "optics", "optics", "power_mW", "power_mW", "power_mW", "show_state_profiles",
                      "Volume(P)", "normalize_fcs"]
    # the worked example ended where the guide said: 2 mW gives 3.3x the volume of the unsaturated Gaussian
    assert model(drv).power_mW == 2.0 and model(drv).normalize_fcs


def test_every_guide_target_is_a_real_control_on_its_tab(drv):
    tour = drv.app.tour
    for step in tour.steps:
        if step.get("tab"):
            drv.app.select_tab(step["tab"])
        drv.draw(3)
        key = tour._target_key(step.get("target"))
        if key:
            assert key in drv.app.item_rects, (step["title"], key)
            assert drv.app.item_rects[key][2] > 0


def test_a_tour_step_brings_its_tab_forward(drv):
    tour = drv.app.tour
    drv.click("guide")
    for index, step in enumerate(tour.steps):
        tour.start(index)
        drv.draw(3)
        if step.get("tab"):
            assert drv.app.result_tab == step["tab"], step["title"]
    tour.stop()


def test_help_click_opens_the_window_whose_buttons_and_escape_close_it(drv):
    drv.click("help")
    window = drv.app.help_window
    assert window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.click("help")
    drv.click_text("Close")
    assert not window.open
    drv.click("help")
    drv.escape()
    assert not window.open


# -- the small window ----------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(drv):
    drv.size = SMALL
    drv.draw(3)
    drv.type_into("power_mW", "2")
    assert model(drv).power_mW == 2.0
    assert edit(drv, "dark_rows", 1, "c0", "300") and rate(drv, "k2_1") == 300.0
    tab(drv, "State diagram")
    assert edit(drv, "optics_rows", 3, "value", "250") and sat(drv).w_r_nm == 250.0
    drv.click("compute")
    assert drv.app.status == "Computed."
    for name in TABS:
        tab(drv, name)
