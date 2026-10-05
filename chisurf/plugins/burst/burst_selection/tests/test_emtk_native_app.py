"""The native Burst Selection app (cards BS1 to BS6): real input on copies of the in-repository BH SPC-132 files.

Files arrive by a host drop, the search runs by a click on Run, numbers on screen are the model's (which
``test_emtk_native_model.py`` compares with the Qt tool). Nothing is plotted without photons.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import implot

from chisurf.plugins.emtk_test_input import SMALL, Driver

DATA = Path(__file__).parent / "data" / "bh_spc132_sm_dna"
GUI = Path(__file__).parents[1] / "gui"
SETUP = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": []},
        "red": {"chs": [8, 9], "micro_time_ranges": []},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}
WINDOWS = (
    "Inter-photon time",
    "Micro-time decay",
    "Burst duration",
    "Scatter",
    "Bursts",
    "Summary",
)


class PlotSpy:
    """Records every ``implot.plot_*`` call that was given data."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str]] = []
        for name in [n for n in dir(implot) if n.startswith("plot_") and "pixels" not in n]:
            monkeypatch.setattr(implot, name, self._wrap(name, getattr(implot, name)))

    def _wrap(self, name, original):
        def spy(*args, **kwargs):
            self.calls.append((name, args[0] if args and isinstance(args[0], str) else ""))
            return original(*args, **kwargs)

        return spy


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    for name in ("m000.spc", "m001.spc"):
        shutil.copy(DATA / name, data / name)
    from chisurf.plugins.burst.burst_selection.gui.model import save_setup

    save_setup("probe", SETUP)
    return [data / "m000.spc", data / "m001.spc"]


@pytest.fixture
def app(files):
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    window = create_app(restore=False)
    window.apply_setup(SETUP, "probe")
    yield window
    window.close()


def wait(drv, timeout=300.0):
    end = time.monotonic() + timeout
    drv.draw(1)
    while drv.app.job.busy and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    assert not drv.app.job.busy, "the run did not finish"
    drv.draw(2)


def texts(painter) -> str:
    return " ".join(t[5] for t in painter.texts)


def test_empty_app_draws_no_data_and_says_so(monkeypatch, files):
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    window = create_app(restore=False)
    try:
        spy = PlotSpy(monkeypatch)
        shown = ""
        for size in ((1200, 800), SMALL):
            drv = Driver(window, size)
            shown += texts(drv.draw())
            for title in WINDOWS:
                drv.click_text(title)
                shown += texts(drv.draw())
        assert spy.calls == []
        assert "No count-rate trace" in shown
        assert "No burst table yet" in shown
        assert "No search yet" in shown
    finally:
        window.close()


def test_drop_run_and_draw_the_models_numbers(monkeypatch, app, files):
    drv = Driver(app, (1200, 800))
    assert drv.drop(*files)
    assert [p.name for p in app.model.files] == ["m000.spc", "m001.spc"]
    drv.draw(2)
    drv.click_name("toolAction_run")
    wait(drv)
    assert app.model.n_bursts == 198, app.model.status_text
    assert "198 bursts" in texts(drv.draw())
    assert [r["bursts"] for r in app.model.file_rows()] == ["71", "127"]
    # the diagnostics are recomputed after the run, and the trace drawn is the model's
    app._diag_due = 0.0
    drv.draw(2)
    assert app.model.diagnostic is not None
    spy = PlotSpy(monkeypatch)
    drv.draw(1)
    assert ("plot_line", "Selected photons") in spy.calls
    # unchanged request: kept; Restart searches again
    drv.click_name("toolAction_run")
    drv.draw(1)
    assert "Unchanged" in app.model.status_text
    drv.click_name("toolAction_restart")
    wait(drv)
    assert app.model.n_bursts == 198


def test_typed_settings_reach_the_model(app):
    drv = Driver(app, (1200, 800))
    drv.click_text("Filter settings")
    drv.draw(2)
    drv.type_into_name("min_photons", "61")
    drv.draw(1)
    assert app.model.min_photons == 61
    drv.type_into_name("m", "12")
    drv.draw(1)
    assert app.model.parameters["m"] == 12
    assert app.model.analysis_settings().photon_filter.tttrlib_search.parameters["m"] == 12


def test_algorithm_switch_regenerates_the_parameter_form(app):
    drv = Driver(app, (1200, 800))
    drv.click_text("Filter settings")
    drv.draw(2)
    assert "T" in app.form.rects
    app.model.algorithm_choice = "maxtree"
    drv.draw(2)
    assert "delta" in app.form.rects and "max_variation" in app.form.rects


def test_metadata_dialog_and_flrcif_export(app, files, tmp_path):
    drv = Driver(app, (1200, 800))
    drv.click_name("metadata")
    drv.draw(2)
    assert app.panel_dialog == "metadata"
    drv.type_into_name("metadata_value", "7.4")
    drv.click_name("add_metadata")
    drv.draw(1)
    assert app.model.metadata[app.model.metadata_key] == "7.4"
    app.model.add_paths(files[:1])
    app.model.load_diagnostics()
    out = app.model.export_flr_cif(tmp_path / "x.cif")
    assert f"_{app.model.metadata_key} 7.4" in out.read_text()


def test_every_control_has_a_tooltip(app, files):
    import sys

    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import emtk_inventory

    app.model.add_paths(files)
    app.model.load_diagnostics()
    missing = set()
    for key in ("files", "settings", "detectors", "summary", "histogram", "scatter", "table"):
        app.docks.focus(key)
        missing |= set(emtk_inventory(app)["controls_without_tooltip"])
    assert sorted(missing) == []


def test_guide_steps_point_at_real_controls(app, files):
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    app.model.add_paths(files)
    app.model.load_diagnostics()
    drv = Driver(app, (1200, 800))
    for step in steps:
        key = app.tour._target_key(step.get("target"))
        if not key:
            continue
        if step["target"].get("tab"):
            app.docks.focus(step["target"]["tab"])
        drv.draw(2)
        assert app.item_rects.get(key) or app.form.rects.get(key), key


def test_native_app_is_qt_free():
    import sys

    sys.modules.pop("test", None)
    from test.gui.emtk_port_parity import qt_free

    result = qt_free(
        "burst_selection", "chisurf.plugins.burst.burst_selection.gui.native:create_app"
    )
    assert result["ok"], result["output"]


def test_settings_survive_a_restart(files):
    from chisurf.plugins.burst.burst_selection.gui.native import create_app

    window = create_app(restore=False)
    window.model.hist_bins = 23
    window.model.dt_max = 0.2
    window.close()  # remembers
    again = create_app()
    try:
        assert again.model.hist_bins == 23 and again.model.dt_max == 0.2
        assert np.isclose(
            again.model.analysis_settings().photon_filter.delta_macro_time_filter.dT_max, 0.2
        )
    finally:
        again.close()
