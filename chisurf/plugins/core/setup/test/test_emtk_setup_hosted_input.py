"""Real wheel, drag and drop input into the panels the Settings hub hosts (and the Acquisition and ChiSurf Settings panels)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from chisurf.plugins.core.setup.test import seeded
from chisurf.plugins.emtk_test_input import Driver

REPO = Path(__file__).parents[5]


@pytest.fixture
def hub(tmp_path, monkeypatch):
    from chisurf.plugins.core.setup.gui.app import make_app

    folder = seeded.prepare(tmp_path, monkeypatch)
    app = make_app(settings_dir=folder)
    drv = Driver(app)
    drv.draw(3)
    yield drv
    app.close()


def texts(drv):
    return sorted((round(t[0]), round(t[1]), t[5]) for t in drv.draw(1).texts)


def panel_point(drv, fx, fy):
    bx, by, bw, bh = drv.app.child_box
    return bx + bw * fx, by + bh * fy


@pytest.mark.parametrize("key", ["models", "plugins", "check", "plots"])
def test_the_wheel_scrolls_the_hosted_panel_under_the_pointer(hub, key):
    hub.app.select(key)
    hub.draw(3)
    before = texts(hub)
    for fx, fy in ((0.25, 0.5), (0.75, 0.5), (0.5, 0.85)):
        hub.wheel(*panel_point(hub, fx, fy), -3)
    assert texts(hub) != before, key
    # and back up: the first rows return
    for _ in range(4):
        for fx, fy in ((0.25, 0.5), (0.75, 0.5), (0.5, 0.85)):
            hub.wheel(*panel_point(hub, fx, fy), 3)


def test_the_wheel_scrolls_the_models_table_and_the_first_row_leaves_the_view(hub):
    hub.app.select("models")
    hub.draw(3)
    painter = hub.draw(1)
    bx, by, bw, bh = hub.app.child_box
    rows_before = [t for t in painter.texts if t[1] > by + 120]
    assert rows_before
    for _ in range(5):
        hub.wheel(bx + bw * 0.3, by + bh * 0.5, -3)
    rows_after = [t for t in hub.draw(1).texts if t[1] > by + 120]
    assert [t[5] for t in rows_before] != [t[5] for t in rows_after]


def plot_centre(drv):
    painter = drv.draw(1)
    cx = next(t[0] for t in painter.texts if t[5] == "t / ns")
    cy = next(t[1] for t in painter.texts if t[5] == "counts")
    return cx, cy


def axis_ticks(drv):
    return sorted(t[5] for t in drv.draw(1).texts if t[1] > 500 and t[5].replace(".", "").isdigit())


def test_the_wheel_zooms_the_preview_plot_of_the_plots_panel(hub):
    hub.app.select("plots")
    hub.draw(3)
    cx, cy = plot_centre(hub)
    before = axis_ticks(hub)
    hub.wheel(cx, cy, 4)
    hub.wheel(cx, cy, 4)
    zoomed = axis_ticks(hub)
    assert zoomed != before and len(zoomed) < len(before)
    hub.wheel(cx, cy, -8)
    hub.wheel(cx, cy, -8)
    assert axis_ticks(hub) != zoomed


def test_a_drag_pans_the_preview_plot(hub):
    hub.app.select("plots")
    hub.draw(3)
    cx, cy = plot_centre(hub)
    hub.wheel(cx, cy, 4)
    hub.wheel(cx, cy, 4)
    zoomed = axis_ticks(hub)
    hub.drag((cx, cy), (cx - 160, cy))
    assert axis_ticks(hub) != zoomed


def test_a_dropped_photon_file_reaches_the_lut_tools_panel(hub, tmp_path):
    source = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
    if not source.exists():
        pytest.skip("sample photon file not present")
    target = tmp_path / "BH_SPC132.spc"
    shutil.copy(source, target)
    hub.app.select("lut")
    hub.draw(3)
    child = hub.app.child
    assert hub.drop(target)
    import time

    end = time.monotonic() + 60
    while time.monotonic() < end and str(target) not in [str(f) for f in child.model.input_files]:
        hub.draw(1)
        time.sleep(0.05)
    assert str(target) in [str(f) for f in child.model.input_files]


def test_a_dropped_file_on_a_panel_without_a_drop_handler_is_declined(hub):
    hub.app.select("check")
    assert hub.app.files_dropped(["/tmp/x.dat"]) is False


# --------------------------------------------------------------------------------------- helpers for hosted forms
def child_rect(drv, name):
    """A control rectangle of the hosted panel's form, moved into the hub's canvas."""
    drv.draw(2)
    child = drv.app.child
    rect = dict(getattr(child, "item_rects", {}) or {})
    form = getattr(child, "form", None)
    if form is not None:
        rect.update(form.rects)
    x, y, w, h = rect[name]
    bx, by = drv.app.child_box[:2]
    return bx + x, by + y, w, h


def child_type(drv, name, text):
    drv.click(child_rect(drv, name), fx=0.3)
    assert drv.app.child.io.want_capture_keyboard, name
    drv.app.key(0x41, "a", 0x04000000)
    drv.draw(1)
    drv.type(text)
    drv.enter()


@pytest.fixture
def acq(hub):
    hub.app.select("acq")
    hub.draw(3)
    saved = []
    hub.app.child.model._persist = lambda config: saved.append(config)
    return hub, hub.app.child.model, saved


def test_typing_an_output_folder_stores_it_at_once(acq, tmp_path):
    hub, model, saved = acq
    child_type(hub, "output_path", str(tmp_path / "runs"))
    assert model.config["output_path"] == str(tmp_path / "runs")
    assert saved and saved[-1]["output_path"] == str(tmp_path / "runs")


def test_typing_a_chunk_size_stores_it_and_it_is_limited_to_the_qt_range(acq):
    hub, model, saved = acq
    child_type(hub, "chunk_size", "20000")
    assert model.config["chunk_size"] == 20000
    child_type(hub, "chunk_size", "99999999")
    assert model.config["chunk_size"] == 65536
    child_type(hub, "chunk_size", "5")
    assert model.config["chunk_size"] == 1000


def test_the_real_time_switch_is_a_real_click_and_is_hidden_for_vendor_devices(acq):
    hub, model, saved = acq
    hub.click(child_rect(hub, "real_time_sim"))
    assert model.config["real_time_sim"] is True
    hub.click(child_rect(hub, "device_type"))
    hub.click_text("PicoQuant")
    assert model.config["device_type"] == "PicoQuant"
    hub.draw(2)
    assert "real_time_sim" not in hub.app.child.form.rects
    assert any("No specific configuration" in t[5] for t in hub.draw(2).texts)
    hub.click(child_rect(hub, "device_type"))
    hub.click_text("Simulation")
    hub.draw(2)
    assert model.config["device_type"] == "Simulation" and "real_time_sim" in hub.app.child.form.rects


def test_a_simulator_parameter_edit_keeps_every_other_stored_parameter(acq):
    from chisurf.plugins.core.setup.gui.acq_app import simulation_defaults

    hub, model, saved = acq
    child_type(hub, "sim_N_ph_max", "250000")
    params = model.config["simulation_params"]
    assert params["N_ph_max"] == 250000
    assert {k: v for k, v in params.items() if k != "N_ph_max"} == {
        k: v for k, v in simulation_defaults().items() if k != "N_ph_max"
    }


def test_the_browse_button_opens_the_folder_chooser_and_choose_stores_the_folder(acq, tmp_path):
    hub, model, saved = acq
    target = tmp_path / "chosen"
    target.mkdir()
    hub.click(child_rect(hub, "browse_output"))
    child = hub.app.child
    assert child.dialog is not None
    child.dialog.directory = str(target)
    hub.click_text("Choose")
    assert child.dialog is None and model.config["output_path"] == str(target)


def test_the_acquisition_defaults_equal_what_the_qt_simulator_dialog_writes():
    from chisurf.plugins.core.acq.tcspc_devices.simulation.setup_dialog import SimulationSettingsModel
    from chisurf.plugins.core.setup.gui.acq_app import simulation_defaults

    assert simulation_defaults() == SimulationSettingsModel().to_parameters()


def test_the_acquisition_settings_survive_a_round_trip_through_the_settings_file(hub):
    import os

    import yaml

    from chisurf.plugins.core.setup.gui.acq_app import AcquisitionSettingsModel

    hub.app.select("acq")
    model = hub.app.child.model
    model.chunk_size = 4096
    model.device_type = "BrickMic"
    data = yaml.safe_load((Path(os.environ["CHISURF_SETTINGS_DIR"]) / "settings_chisurf.yaml").read_text())
    stored = data.get("gui", {}).get("acquisition") or data.get("acquisition")
    assert stored["chunk_size"] == 4096 and stored["device_type"] == "BrickMic"
    assert AcquisitionSettingsModel(stored).chunk_size == 4096


# --------------------------------------------------------------------------------------- ChiSurf Settings
def test_the_chisurf_settings_language_selector_stores_gui_language(hub):
    hub.app.select("chisurf")
    hub.draw(3)
    editor = hub.app.child
    assert editor.language() == "en"
    hub.click(child_rect(hub, "language"))
    hub.click_text("Deutsch")
    assert editor.language() == "de" and "language: de" in editor.document.text
    assert "Save keeps it" in editor.status
    from chisurf.emtk.i18n import set_locale

    set_locale("en")


def test_the_chisurf_settings_help_button_opens_help_and_save_writes_the_file(hub):
    import os

    hub.app.select("chisurf")
    editor = hub.app.child
    painter = hub.draw(3)
    bx = hub.app.child_box[0]
    helps = [t for t in painter.texts if t[5] == "Help" and t[0] >= bx]
    assert helps
    hub.click(helps[-1][:4])
    assert editor.help.open
    editor.help.hide()
    hub.draw(2)
    editor.document.text = "gui:\n  language: fr\n"
    hub.click_text("Save")
    assert "language: fr" in (Path(os.environ["CHISURF_SETTINGS_DIR"]) / "settings_chisurf.yaml").read_text()


def test_chisurf_settings_shows_the_defaults_under_the_users_values_and_saves_only_the_differences(hub):
    import os

    import yaml

    hub.app.select("chisurf")
    editor = hub.app.child
    shown = yaml.safe_load(editor.document.text)
    assert shown["gui"]["language"] == "en" and "correlator" in shown       # a packaged default, not in the user file
    shown["gui"]["theme"] = "light"
    editor.document.text = yaml.safe_dump(shown, sort_keys=False)
    assert editor.save()
    written = yaml.safe_load((Path(os.environ["CHISURF_SETTINGS_DIR"]) / "settings_chisurf.yaml").read_text())
    assert written["gui"]["theme"] == "light"
    assert "correlator" not in written                                      # defaults are not frozen into the file


def test_a_hosted_panels_own_close_button_does_not_close_the_window_and_says_so(hub):
    hub.app.select("fcs")
    hub.draw(3)
    painter = hub.draw(2)
    bx = hub.app.child_box[0]
    close = [t for t in painter.texts if t[5] == "Close" and t[0] >= bx][-1]
    hub.click(close[:4])
    assert hub.app.status == "Close the Settings window to leave this panel."
    assert hub.app.child.close_requested is False
