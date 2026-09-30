"""The native pch port: model, spec, drawing, workflow, no Qt."""

import json
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
REPO = HERE.parents[3]
GUI = HERE.parent / "gui"

#: Small BH photon stream (183 657 photons); channels 0 and 8 are the green detectors.
DATA = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="PCH test data missing")


def make_model():
    from chisurf.plugins.pch.gui.model import PchModel

    model = PchModel()
    model.channels = "0,8"
    model.bin_time_us = 50.0
    return model


def pump(app, seconds=60.0):
    """Draw frames until the app's background job has finished."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
        if not app.job.busy:
            return
        time.sleep(0.02)
    raise AssertionError("the job did not finish")


# 1. the model does the science without any GUI
def test_model_produces_the_reference_result():
    # Reference numbers: the legacy Qt tool (PCHApp) on the same file with
    # channels 0,8, bin time 50 us, starting values eps=2 and N=3 per species,
    # region 0-24; taken from its fit results and status line on 2026-09-30.
    model = make_model()
    assert model.load_path(str(DATA))
    model.compute_now()
    result = model.result
    assert result.total_bins == 1246577
    assert len(result.k_vals) == 25
    assert result.hist_counts[:4] == [1137996, 95757, 7695, 2064]
    assert (model.fit_low, model.fit_high) == (0.0, 24.0)

    model.fit_now()
    fit = model.fit_result
    assert fit.epsilons[0] == pytest.approx(0.3320787632444934, rel=1e-5)
    assert fit.avg_Ns[0] == pytest.approx(1.8326288170909257, rel=1e-5)
    assert fit.dof == 23
    assert model.species[0]["epsilon"] == pytest.approx(0.3320787632444934, rel=1e-5)

    model.set_n_components(2)
    model.species[0].update(epsilon=2.0, n_mean=3.0)
    model.fit_now()
    fit = model.fit_result
    assert fit.epsilons == pytest.approx([8.28225986388613, 0.058043027099024654], rel=1e-4)
    assert fit.avg_Ns == pytest.approx([0.021963498790065913, 8.750137325612235], rel=1e-4)
    assert fit.chi2 == pytest.approx(1018.399056377842, rel=1e-4)
    assert fit.dof == 21
    assert "Comp2: ε=0.0580  ⟨N⟩=8.7501  x=99.7%" in model.results_text
    assert "χ² = 1018.40   red. χ² = 48.495   dof = 21" in model.results_text


def test_model_matches_the_qt_tool(qapp):
    """The same file through the legacy Qt tool gives the numbers the model gives."""
    from chisurf.plugins.pch.gui.tool import PCHApp

    class Task:
        def set_text(self, *args):
            pass

    widget = PCHApp()
    try:
        widget._load_path(str(DATA))
        qt_result = widget._compute(
            Task(), filename=str(DATA), channels=[0, 8], bin_time_us=50.0,
            micro_time_min=0, micro_time_max=65535,
        )
        widget._computed(qt_result)
        widget._on_fit()
        model = make_model()
        model.load_path(str(DATA))
        model.compute_now()
        model.fit_now()
        assert model.result.hist_counts == qt_result.hist_counts
        assert model.fit_result.epsilons == pytest.approx(widget._fit_result.epsilons)
        assert model.fit_result.avg_Ns == pytest.approx(widget._fit_result.avg_Ns)
        assert model.results_text == widget.results_edit.toPlainText()
    finally:
        widget.close()


# 2. the model's actions
def test_actions_change_state_and_report_errors(tmp_path):
    model = make_model()
    assert not model.enabled("compute") and not model.enabled("fit") and not model.enabled("save")
    assert model.enabled("load")

    model.compute()
    assert model.status_line() == "Load a TTTR file first."
    model.fit()
    assert model.status_line() == "Compute the histogram first."
    model.save()
    assert model.status_line() == "Compute the histogram first."
    assert model.dialog == ""

    model.load()
    assert model.dialog == "open"

    # a bad file: readable error, nothing half-loaded
    assert not model.load_path(str(tmp_path / "missing.ptu"))
    assert model.status_line().startswith("Cannot load the file")
    assert model.filename == "" and model.result is None

    # a good file arms Compute
    assert model.load_path(str(DATA))
    assert model.enabled("compute") and not model.enabled("fit")
    assert model.status_line().startswith("Loaded: ") and "183,657 photons" in model.status_line()

    # a bad channel list is an error, not an exception
    model.channels = "0,x"
    model.compute()
    assert "channel list" in model.status_line()
    assert model.result is None
    model.channels = "0,8"
    model.compute()
    assert model.result is not None and model.error_text == ""
    assert model.enabled("fit") and model.enabled("save")
    assert model.status_line() == "Computed PCH: 1,246,577 bins, 25 k-values"

    # components: resize keeps the values typed so far
    model.species[0].update(epsilon=5.0, n_mean=0.5)
    model.set_n_components(3)
    assert [r["component"] for r in model.species] == [1, 2, 3]
    assert model.species[0]["epsilon"] == 5.0 and model.species[0]["n_mean"] == 0.5
    assert model.species[2]["epsilon"] == 2.0 and model.species[2]["n_mean"] == 3.0
    model.set_n_components(1)
    assert len(model.species) == 1
    # a typed cell is clamped like the Qt spin box
    model.edit_species(model.species[0], "epsilon", -4.0)
    assert model.species[0]["epsilon"] == 0.0

    # save: three files, and a bad target is an error, not an exception
    model.fit()
    base = str(tmp_path / "out")
    assert model.save_to(base)
    assert model.status_line() == f"Saved {base}.npz / .csv / .txt"
    saved = np.load(f"{base}.npz")
    assert list(saved["k_vals"]) == list(range(25))
    assert (tmp_path / "out.csv").read_text().splitlines()[0] == "k,P_exp,P_fit"
    assert (tmp_path / "out.txt").read_text() == model.results_text
    assert not model.save_to(str(tmp_path / "no_such_dir" / "out"))
    assert model.status_line().startswith("Saving failed")

    # drops: a photon file loads, anything else is reported
    fresh = make_model()
    assert not fresh.on_paths_dropped([tmp_path / "notes.txt"])
    assert fresh.status_line().startswith("Drop a photon-stream file")
    assert fresh.on_paths_dropped([tmp_path / "notes.txt", DATA])
    assert fresh.filename == str(DATA) and fresh.error_text == ""

    # moving the fit range recomputes the chi2 of an existing fit
    model.set_n_components(1)
    model.fit_now()
    before = model.results_text
    model.set_region(0, 12)
    assert "Region: 0–12" in model.results_text and model.results_text != before


# 3. spec and model agree
def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.pch.gui.model import PchModel

    spec = json.loads((GUI / "pch.view.json").read_text(encoding="utf-8"))
    model = PchModel()

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                assert hasattr(model, s["attr"]), s["attr"]
            for key in ("call", "source", "edited_call"):
                if s.get(key):
                    assert hasattr(model, s[key]), s[key]
            for b in s.get("buttons", []):
                assert callable(getattr(model, b["action"])), b["action"]
            for column in s.get("columns", []):
                assert column["key"] in model.species[0], column["key"]
            walk(s.get("sections", []))

    walk(spec["sections"])


# 4. the app draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_empty_and_populated(size):
    from chisurf.plugins.pch.gui.app import make_app

    app = make_app()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    empty = " ".join(painter.strings)
    assert "Load TTTR" in empty and "Ready. Load a TTTR file to begin." in empty
    assert "Comp1" not in empty

    model = app.model
    model.runner = None
    model.channels, model.bin_time_us = "0,8", 50.0
    model.load_path(str(DATA))
    model.compute_now()
    model.fit_now()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    text = "\n".join(painter.strings)
    assert any("Comp1: ε=0.3321" in s for s in painter.strings), text
    assert "Fit complete" in text and "1e-06" in text  # log axis of the histogram


# 5. the workflow through the UI path
def test_main_action_end_to_end(tmp_path):
    from chisurf.plugins.pch.gui.app import make_app
    from emtk.file_dialog import FileDialog

    app = make_app()
    model = app.model
    assert model.runner is not None  # work goes through the app's job, not the draw thread

    # Load TTTR opens the dialog
    model.load()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert isinstance(app.dialog, FileDialog) and app.dialog_kind == "open"
    app.dialog = None

    # a dropped file loads in the job
    app.on_paths_dropped([str(DATA)])
    pump(app)
    assert model.filename == str(DATA) and model.enabled("compute")

    model.channels, model.bin_time_us = "0,8", 50.0
    model.compute()
    pump(app)
    assert model.result.total_bins == 1246577
    assert model.trace_x.size and model.trace_x.size < 5000  # decimated for display

    model.set_n_components(2)
    model.species[0].update(epsilon=2.0, n_mean=3.0)
    model.fit()
    pump(app)
    assert model.fit_result.chi2 == pytest.approx(1018.399056377842, rel=1e-4)
    assert [round(r["epsilon"], 4) for r in model.species] == [8.2823, 0.0580]

    # Save Results opens the save dialog; choosing a name writes the files
    model.save()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert app.dialog is not None and app.dialog_kind == "save"
    app.dialog = None
    assert model.save_to(str(tmp_path / "run"))
    assert (tmp_path / "run.npz").exists()


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("pch")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("pch"))
    assert inv["controls_without_tooltip"] == []
    labelled = {row["label"] for row in inv["interactive"]}
    assert labelled == {"Help", "Guide", "Load TTTR", "Compute PCH", "Fit Model", "Save Results"}

    # the recorder only sees labelled controls; the spec's fields and table columns
    # (drawn with an empty label) must say what they are through their description
    spec = json.loads((GUI / "pch.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle", "table"):
                assert s.get("description") or s.get("columns"), s
            for column in s.get("columns", []):
                assert column.get("description"), column
            for button in s.get("buttons", []):
                assert button.get("description"), button
            walk(s.get("sections", []))

    walk(spec["sections"])


# 8. persistence round trip
def test_settings_round_trip():
    from chisurf.plugins.pch.gui.app import make_app

    app = make_app()
    model = app.model
    model.folder, model.channels, model.bin_time_us = "/data/run1", "1", 25.0
    model.micro_time_min, model.micro_time_max = 100, 4000
    model.set_n_components(2)
    model.species[1].update(epsilon=7.5, n_mean=0.25)
    state = json.loads(json.dumps(app.export_settings()))  # must survive a settings file

    other = make_app()
    other.restore_settings(state)
    assert other.export_settings() == state
    assert other.model.folder == "/data/run1" and other.model.channels == "1"
    assert other.model.bin_time_us == 25.0 and other.model.n_components == 2
    assert other.model.species[1]["epsilon"] == 7.5

    other.restore_settings({"bin_time_us": "not a number", "n_components": "x", "epsilons": [None]})
    assert other.model.bin_time_us == 25.0 and other.model.n_components == 2


# guide: every step points at a control that is on screen, and awaits are released by the app
def test_guide_targets_are_drawn_and_awaits_release():
    from chisurf.plugins.pch.gui.app import make_app

    app = make_app()
    model = app.model
    model.channels, model.bin_time_us = "0,8", 50.0
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    steps = app.tour.steps
    assert len(steps) >= 8 and sum(1 for s in steps if s.get("await")) == 3
    keys = [app.tour._target_key(s.get("target")) for s in steps]
    missing = [k for k in keys if k and not app.tour.get_target_rect(k)]
    assert missing == [], missing

    app.tour.start(1)
    assert app.tour.awaiting
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert app.tour.awaiting  # opening the dialog is not the outcome
    app.on_paths_dropped([str(DATA)])
    pump(app)
    assert not app.tour.awaiting

    app.tour.start(4)
    assert app.tour.awaiting
    model.compute()
    pump(app)
    assert not app.tour.awaiting
    assert not [k for k in keys if k and not app.tour.get_target_rect(k)]

    app.tour.start(7)
    assert app.tour.awaiting
    model.fit()
    pump(app)
    assert not app.tour.awaiting
