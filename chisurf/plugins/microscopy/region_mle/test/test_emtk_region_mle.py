"""The native region_mle port: model, spec, drawing, workflow, no Qt."""

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"

#: Lifetimes (ns) the Fit23 MLE returns for the four objects of the plugin's own demo
#: (truth 1.0, 3.6, 2.2, 0.6 ns; the long ones come back low because a 3.6 ns decay is not
#: finished in the 8.2 ns excitation period). Taken from the legacy tool's
#: RegionMleViewModel.run() on the same demo, pasted with a tolerance.
REFERENCE_TAU = [1.00002, 3.30177, 2.08438, 0.60221]
REFERENCE_PHOTONS = [60294, 59958, 129646, 140486]


# ── the demo, made once, read through a shim ───────────────────────────
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The simulated demo scan and its IRF, written to a private settings folder."""
    import chisurf.core.settings as settings_mod

    root = tmp_path_factory.mktemp("region_mle_demo")
    saved = getattr(settings_mod, "chisurf_settings_path", None)
    settings_mod.chisurf_settings_path = str(root)
    try:
        from chisurf.plugins.microscopy.region_mle.gui.model import RegionMleModel

        model = RegionMleModel()
        model.load_demo()
        yield root / "demo"
    finally:
        settings_mod.chisurf_settings_path = saved


@pytest.fixture
def workdir(demo, tmp_path, monkeypatch):
    """A temp copy of the demo (a run writes beside its input) and the CLSM shim.

    The plugin's core reads an image with ``tttrlib.CLSMImage`` directly, which cannot
    rebuild the simulated scan (it needs the simulator's scanner layout from the sidecar
    json); the spot finder's loader can. The shim gives ``CLSMImage`` the same reading
    so the real ``run`` path can be driven. It stands in for a backend fix that is
    outside this port (see the port report, "Blocked").
    """
    import tttrlib

    for path in demo.glob("spot_demo_mixture*"):
        shutil.copy(path, tmp_path)
    layout = json.loads((tmp_path / "spot_demo_mixture.json").read_text())["scan_layout"]
    original = tttrlib.CLSMImage

    def shim(tttr, *args, channels=None, fill=True, **kwargs):
        from chisurf.core.fluorescence.imaging.simulate import clsm_from_scan

        monkeypatch.setattr(tttrlib, "CLSMImage", original)
        try:
            return clsm_from_scan(tttr, int(layout["n_pixel_per_line"]), channels=channels)
        finally:
            monkeypatch.setattr(tttrlib, "CLSMImage", shim)

    monkeypatch.setattr(tttrlib, "CLSMImage", shim)
    return tmp_path


def loaded_model(workdir):
    """A model pointing at the copied demo, settings as ``load_demo`` left them."""
    from chisurf.plugins.microscopy.region_mle.gui.model import RegionMleModel

    model = RegionMleModel()
    sample = str(workdir / "spot_demo_mixture.ptu")
    model.files = [sample]
    model.irf_files = [str(workdir / "spot_demo_mixture_irf.ptu")]
    model.settings.detector_chs = [0, 1]
    model.settings.micro_time_range = (0, 128)
    model.settings.regions = sample
    model.settings.region_set = "spots"
    model.settings.min_photons = 100
    model.settings.fix_r0 = model.settings.fix_rho = True
    return model


def pump(app, seconds=120.0, size=(1200, 800)):
    """Draw frames until the app's background job has finished."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, *size)
        if not app.job.busy:
            app.draw(RecordingPainter(), 0, 0, *size)
            return
        time.sleep(0.02)
    raise AssertionError("the job did not finish")


def taus(model):
    from chisurf.core.datastore import numeric_column

    return [float(t) for t in numeric_column(model.results[0].dataframe, "tau")]


# 1. the model does the science without any GUI
def test_model_produces_the_reference_result(workdir):
    model = loaded_model(workdir)
    model.run()
    assert model.results and model.results[0].n_molecules == 4
    np.testing.assert_allclose(taus(model), REFERENCE_TAU, rtol=2e-3)
    from chisurf.core.datastore import numeric_column

    photons = numeric_column(model.results[0].dataframe, "n_photons_total")
    assert [int(p) for p in photons] == REFERENCE_PHOTONS
    # the run wrote beside the (copied) input, as the Qt tool does
    assert (workdir / "joint_output.tsv").exists()
    assert (workdir / "spot_demo_mixture_analysis" / "molecule_data.tsv").exists()
    assert "median" in model.info_html()


def test_model_matches_the_legacy_view_model(workdir):
    """The native model is the view-model plus window state: same numbers."""
    from chisurf.plugins.microscopy.region_mle.gui.view_model import RegionMleViewModel

    native = loaded_model(workdir)
    native.run()
    legacy = RegionMleViewModel()
    legacy.files, legacy.irf_files = list(native.files), list(native.irf_files)
    legacy.settings = native.settings.__class__(
        **{k: getattr(native.settings, k) for k in ("detector_chs", "micro_time_range")}
    )
    legacy.settings.regions = native.settings.regions
    legacy.settings.region_set = "spots"
    legacy.settings.min_photons = 100
    legacy.settings.fix_r0 = legacy.settings.fix_rho = True
    legacy.run()
    np.testing.assert_allclose(taus(native), taus(legacy))


# 2. the model's actions
def test_actions_change_state_and_report_errors(workdir, tmp_path):
    from chisurf.plugins.microscopy.region_mle.gui.model import RegionMleModel

    model = RegionMleModel()
    # nothing selected: the action buttons are greyed, and the methods say why
    assert not model.enabled("request_run")
    assert not model.enabled("request_preview")
    assert not model.enabled("request_export")
    model.run()
    assert model.status_text == "No imaging files selected."
    model.files = ["x.ptu"]
    model.run()
    assert model.status_text == "No IRF file selected."
    model.status_text = ""
    model.preview_regions()  # a file that cannot be read is reported, not raised
    assert model.status_text and model.status_text != "No imaging files selected."
    assert model.export_results(str(tmp_path / "none.tsv")) == ""
    assert model.status_text == "No regions to export."
    model.load_analysis(str(tmp_path / "missing.tsv"))
    assert model.status_text.startswith("Not found")
    # requests only ask the window
    model.request_open_results()
    assert model.dialog == "open_results"
    # file lists: duplicates are skipped, the IRF list keeps one file
    assert model.add_paths("sel_files", ["a.ptu", "b.ptu", "a.ptu"]) == 2
    assert model.sel_files == ["x.ptu", "a.ptu", "b.ptu"]
    assert model.add_paths("sel_irf_files", ["i1.ptu", "i2.ptu"]) == 1
    assert model.sel_irf_files == ["i1.ptu"]
    # busy greys everything
    model.busy = True
    assert not model.enabled("request_demo") and not model.enabled("tau")
    # the real workflow: after a run the export action is usable and writes a table
    model = loaded_model(workdir)
    assert model.enabled("request_run") and model.enabled("request_preview")
    model.run()
    assert model.enabled("request_export")
    out = tmp_path / "regions.tsv"
    assert model.export_results(str(out)) == str(out)
    assert len(out.read_text().splitlines()) == 5  # header + 4 regions
    assert "Exported 4 region(s)" in model.status_text


# 3. spec and model agree
def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.microscopy.region_mle.gui.model import RegionMleModel

    spec = json.loads((GUI / "region_mle_emtk.view.json").read_text())
    model = RegionMleModel()

    def walk(sections):
        for s in sections:
            for key in ("attr", "target", "source"):
                if s.get(key):
                    assert hasattr(model, s[key]), s[key]
            if s.get("call"):
                assert callable(getattr(model, s["call"])), s["call"]
            for b in s.get("buttons", []):
                assert callable(getattr(model, b["action"])), b["action"]
            options = s.get("options") or {}
            for key in ("entries_source", "entry_attr", "info_source", "markers_source"):
                if options.get(key):
                    assert hasattr(model, options[key]), options[key]
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_custom_sections_are_all_drawn_by_the_app():
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    spec = json.loads((GUI / "region_mle_emtk.view.json").read_text())
    keys = set()

    def walk(sections):
        for s in sections:
            if s.get("type") == "custom":
                keys.add(s["key"])
            walk(s.get("sections", []))

    walk(spec["sections"])
    assert keys == {"path_list", "region_list", "image_browser", "decay_panel"}
    assert keys <= set(make_app().form.custom)


# 4. the app draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_empty_and_populated(workdir, size):
    from chisurf.plugins.microscopy.region_mle.gui.app import RegionMleApp, make_app

    app = make_app()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert any("CLSM imaging files" in s for s in painter.strings)
    app = RegionMleApp(model=loaded_model(workdir))
    app.model.request_run()
    pump(app, size=size)
    seen = {}
    for window in ("analysis", "regions", "decay"):
        app.docks.focus(window)
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, *size)
        seen[window] = " ".join(painter.strings)
    assert "4 region(s) in 1 file(s)" in seen["analysis"]
    assert "spot_demo_mixture.ptu" in seen["analysis"]
    assert "Region 1" in seen["regions"] and "Colormap" in seen["regions"]
    assert "micro-time channel" in seen["decay"] and "Residuals" in seen["decay"]


# 5. the workflow through the UI path
def test_main_action_end_to_end(workdir, tmp_path):
    from chisurf.plugins.microscopy.region_mle.gui.app import RegionMleApp, make_app

    app = RegionMleApp(model=loaded_model(workdir))
    # Preview first: measured, not fitted
    app.model.request_preview()
    assert app.job.busy
    assert not app.model.enabled("request_run")  # greyed while it runs
    pump(app)
    assert app.model.results[0].n_molecules == 4
    assert all(not np.isfinite(t) for t in taus(app.model))
    assert "Preview: 4 region(s)" in app.model.status_text
    # Run: the button's action, through the job
    app.model.request_run()
    pump(app)
    np.testing.assert_allclose(taus(app.model), REFERENCE_TAU, rtol=2e-3)
    assert not app.model.error_text
    # what the windows derived from the result
    view = app._view_of_results()
    assert [e["badge"] for e in view["entries"]][0] == "τ=1.00 ns"
    assert len(list(view["found"])) == 4 and len(view["labels"]) == 4
    assert view["curves"] is not None and len(view["curves"].channels) == 256
    # select another region: the derived data follows
    app.model.current_molecule = 2
    assert app._view_of_results()["info"].startswith("Region 3")
    # Export through the file dialog path, then reopen the saved analysis
    out = tmp_path / "table.csv"
    app._dialog_done("export", [str(out)])
    assert len(out.read_text().splitlines()) == 5
    saved = workdir / "spot_demo_mixture_analysis" / "molecule_data.tsv"
    app._dialog_done("open_results", [str(saved)])
    assert app.model.status_text.startswith("Loaded 4 region(s)")
    assert app.model.results[0].n_molecules == 4
    assert app.model.folder == str(saved.parent)


def test_the_analysis_region_is_dragged_on_the_image(workdir, monkeypatch):
    """Dragging the region on the canvas writes the region the analysis reads."""
    from emtk import implot

    from chisurf.core.roi import RectangleROI
    from chisurf.plugins.microscopy.region_mle.gui.app import RegionMleApp

    app = RegionMleApp(model=loaded_model(workdir))
    app.model.run()
    app.model.regions.add(RectangleROI(2.0, 2.0, 20.0, 20.0, name="box"))
    app.model.apply_regions()
    assert app.model.settings.roi is not None

    class Dragged:
        modified = True
        clicked = held = hovered = False
        x_min, y_min, x_max, y_max = 5.0, 6.0, 30.0, 31.0

    monkeypatch.setattr(implot, "drag_rect", lambda *args, **kwargs: Dragged())
    app.docks.focus("regions")
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    roi = app.model.regions.get("box").roi
    assert (roi.x0, roi.y0, roi.x1, roi.y1) == (5.0, 6.0, 30.0, 31.0)
    mask = app.model.settings.analysis_roi()
    assert mask is not None and (mask.x0, mask.x1) == (5.0, 30.0)


def test_dropped_files_join_the_imaging_list(workdir):
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    app = make_app()
    assert app.files_dropped([str(workdir / "spot_demo_mixture.ptu")]) is True
    assert app.model.files == [str(workdir / "spot_demo_mixture.ptu")]
    app.on_paths_dropped([str(workdir / "spot_demo_mixture.ptu")])
    assert len(app.model.files) == 1  # a duplicate is skipped


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("region_mle")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("region_mle"))
    assert inv["controls_without_tooltip"] == []
    spec = json.loads((GUI / "region_mle_emtk.view.json").read_text())

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle", "table", "data_table", "custom"):
                assert s.get("description"), s.get("attr") or s.get("title") or s
            for c in s.get("columns", []):
                assert c.get("description"), c
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


# 8. persistence round trip
def test_settings_round_trip(workdir):
    from chisurf.core.roi import RectangleROI
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    app = make_app()
    model = app.model
    model.tau, model.fix_tau, model.min_photons = 3.25, True, 77
    model.detector_chs_text = "0 1 2 3"
    model.mtr_start, model.mtr_stop = 4, 99
    model.region_set = "cells"
    model.sel_files = ["/data/a.ptu", "/data/b.ptu"]
    model.sel_irf_files = ["/data/irf.ptu"]
    model.regions.add(RectangleROI(1.0, 2.0, 30.0, 40.0, name="cell"))
    model.folder = "/data"
    app.canvas.colormap = "viridis"
    state = json.loads(json.dumps(app.export_settings()))  # plain JSON
    other = make_app()
    other.restore_settings(state)
    assert other.model.tau == 3.25 and other.model.fix_tau and other.model.min_photons == 77
    assert other.model.settings.detector_chs == [0, 1, 2, 3]
    assert other.model.settings.micro_time_range == (4, 99)
    assert other.model.region_set == "cells"
    assert other.model.files == ["/data/a.ptu", "/data/b.ptu"]
    assert other.model.irf_files == ["/data/irf.ptu"]
    assert other.model.folder == "/data" and other.canvas.colormap == "viridis"
    assert other.model.regions.get("cell") is not None
    assert other.model.settings.roi is not None  # the restored region reached the analysis
    # unusable entries are ignored, not raised
    other.restore_settings({"tau": "not a number", "regions": {"bad": 1}, "colormap": "nope"})
    assert other.model.tau == 3.25 and other.canvas.colormap == "viridis"


# guide and help
def test_guide_targets_are_reachable_and_tour_waits_for_outcomes(workdir):
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    app = make_app()
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    tour = app.tour
    keys = [tour._target_key(s.get("target")) for s in steps if s.get("target")]
    missing = [k for k in keys if k and not (app.item_rects.get(k) or app.form.rects.get(k))]
    # "Decay" is drawn only while its tab is in front; the tour brings it forward
    assert missing == ["Decay"]
    tour.start(steps.index(next(s for s in steps if tour._target_key(s.get("target")) == "Decay")))
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert app.item_rects.get("Decay")
    # the demo step waits for the demo being loaded, not for the button press
    tour.start(1)
    assert tour.awaiting
    app.form.on_used("request_demo")
    assert tour.awaiting
    app._job_method = "load_demo"
    app._job_finished()
    assert not tour.awaiting
    # the step texts name controls of this app (no emoji labels, no Qt toolbar)
    text = json.dumps(steps, ensure_ascii=False)
    assert "🧪" not in text and "👁" not in text and "▶" not in text


def test_the_analysis_region_editor_opens_when_its_header_is_clicked():
    """The editor sits in a collapsible header that starts closed; a click must open it for good.

    (emtk once read the header's flags word as a bool and forced it closed every frame.)
    """
    from emtk.testing import RecordingPainter

    from ..gui.app import make_app

    app = make_app()

    def frame():
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
        return painter

    for _ in range(3):
        painter = frame()
    assert "Add rectangle" not in painter.strings
    header = next(t for t in painter.texts if "Analysis regions" in str(t[5]))
    io = app.io
    io.mouse_pos = (header[0] + 20, header[1] + 5)
    io.mouse_clicked[0] = io.mouse_down[0] = True
    frame()
    io.mouse_clicked[0] = io.mouse_down[0] = False
    io.mouse_released[0] = True
    frame()
    io.mouse_released[0] = False
    for _ in range(3):
        painter = frame()
    assert {"Add rectangle", "Add ellipse", "Add polygon"} <= set(painter.strings)
