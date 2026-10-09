"""The native κ² calculator against the Qt tool it replaces, every control and action driven through the UI.

Hermetic: settings in a temporary folder, the CSV goes to ``tmp_path``, no network. The Qt tool is the
committed AutoForm ``Kappa2Dist`` (its source is kept in ``okf/plugins/emtk-ports/kappa2_dist/pre-upgrade/
qt_original_tool.py.txt``), built offscreen. The results are Monte-Carlo (numpy's global generator), so both
sides are seeded identically before every computation; the numbers must then agree exactly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.calculator.kappa2_dist.gui.app import INPUT_FIELDS, Kappa2App, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BASELINE = REPO / "okf/plugins/emtk-ports/kappa2_dist/pre-upgrade/qt_original_tool.py.txt"
SIZE = (1200, 800)
SMALL = (800, 600)
RESULTS = ("k2_mean", "k2_sd", "Rapp_mean", "RappSD", "delta_deg")


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture
def app():
    np.random.seed(7)
    return make_app()


def draw(app, size=SIZE, frames=2):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def settle(app, size=SIZE, timeout=60.0):
    """Draw until the background computation (and a queued second one) is in."""
    end = time.monotonic() + timeout
    draw(app, size, frames=1)
    while (app.tool.busy or app.tool.dirty) and time.monotonic() < end:
        time.sleep(0.005)
        draw(app, size, frames=1)
    assert not app.tool.busy
    return draw(app, size, frames=1)


def click(app, rect, size=SIZE, fx=0.5):
    x, y, w, h = rect
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def type_into(app, name, text, size=SIZE, seed=7):
    """Click the field, type, press Enter (the computation is seeded just before it starts)."""
    draw(app, size)
    click(app, app.item_rects[name], size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    app.key(0x41, "a", 0x04000000)
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    np.random.seed(seed)
    app.key(keys.KEY_RETURN, "\r")
    settle(app, size)


def pick_model(app, label, size=SIZE, seed=7):
    """Open the model combo and click the entry."""
    draw(app, size)
    click(app, app.item_rects["model_type"], size)
    painter = draw(app, size, frames=1)
    entry = [t for t in painter.texts if t[5] == label][-1]
    x, y, w, h = entry[:4]
    np.random.seed(seed)
    app.press(x + w / 2, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    settle(app, size)


def model_state(model):
    return {k: getattr(model, k) for k in (*INPUT_FIELDS, *RESULTS)}


# -- the Qt tool, built from the committed source ---------------------------------------------- #


@pytest.fixture
def qt_tool():
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    source = BASELINE.read_text(encoding="utf-8").replace(
        "pathlib.Path(__file__).parent\n", f"pathlib.Path({str(PLUGIN / 'gui')!r})\n"
    )
    path = Path(tempfile.mkdtemp()) / "qt_tool.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "chisurf.plugins.calculator.kappa2_dist.gui.qt_original", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    np.random.seed(7)
    tool = module.Kappa2Dist()
    tool._qapp, tool._module = qapp, module
    from chisurf.gui.autoform.sections.builtin import ToggleWidget, ValueWidget

    tool._editors = {
        vw._section.attr: vw.editor
        for vw in tool._form.findChildren(ValueWidget)
        if getattr(vw, "_section", None)
    }
    tool._toggles = {tw._section.attr: tw.checkbox for tw in tool._form.findChildren(ToggleWidget)}
    by_text = {b.text(): b for b in tool._form.findChildren(QtWidgets.QRadioButton)}
    tool._radios = {
        "cone": by_text["WIC (Cone)"],
        "diffusion": by_text["DWT (Diffusion)"],
        "isotropic": by_text["Isotropic"],
    }
    yield tool
    tool.close()


def qt_edit(tool, attr, value, seed=7):
    if attr == "model_type":
        tool._radios[value].click()
    elif attr == "rAD_known":
        tool._toggles[attr].setChecked(bool(value))
    else:
        tool._editors[attr].setValue(value)
        tool._editors[attr].editingFinished.emit()
    np.random.seed(seed)
    tool._compute_timer.stop()
    tool._do_compute()
    tool._qapp.processEvents()


# ── 1. every scenario equals the Qt tool, edited through the real fields ------------------------- #

EDITS = [
    ("model_type", "isotropic"),
    ("model_type", "diffusion"),
    ("fret_efficiency", 0.4),
    ("model_type", "cone"),
    ("r_Dinf", 0.15),
    ("n_bins", 60),
    ("step", 3.0),
    ("rAD_known", True),
    ("kappa2_true", 1.0),
    ("r_0", 0.3),
    ("r_Ainf", 0.2),
    ("r_ADinf", 0.01),
    ("r_ADinf", 0.4),
    ("rAD_known", False),
]


def apply_native(app, attr, value):
    if attr == "model_type":
        pick_model(
            app,
            {"cone": "WIC (Cone)", "diffusion": "DWT (Diffusion)", "isotropic": "Isotropic"}[value],
        )
    elif attr == "rAD_known":
        draw(app)
        np.random.seed(7)
        click(app, app.item_rects["rAD_known"])
        settle(app)
    else:
        text = str(int(value)) if attr == "n_bins" else repr(float(value))
        type_into(app, attr, text)


def assert_same(native, qt, what):
    for key in native:
        if isinstance(native[key], (str, bool)):
            assert native[key] == qt[key], (what, key)
        else:
            assert native[key] == pytest.approx(qt[key], rel=1e-9, abs=1e-12, nan_ok=True), (
                what,
                key,
                native[key],
                qt[key],
            )


def test_defaults_and_every_edit_equal_the_qt_tool(app, qt_tool):
    assert_same(model_state(app.tool._model), model_state(qt_tool._model), "construction")
    for attr, value in EDITS:
        qt_edit(qt_tool, attr, value)
        apply_native(app, attr, value)
        assert_same(
            model_state(app.tool._model), model_state(qt_tool._model), f"after {attr}={value}"
        )
    np.testing.assert_allclose(app.tool._model._k2hist, qt_tool._model._k2hist, equal_nan=True)
    np.testing.assert_allclose(app.tool._model._k2scale, qt_tool._model._k2scale)


def test_the_numbers_the_qt_window_showed_are_pinned(app):
    """Seed 7 values read off the Qt window (okf/plugins/emtk-ports/kappa2_dist/qt_values.json)."""
    m = app.tool._model
    assert (m.k2_mean, m.k2_sd) == pytest.approx((0.66644, 0.21922), abs=5e-6)
    assert (m.Rapp_mean, m.RappSD, m.delta_deg) == pytest.approx(
        (0.99288, 0.05216, 57.65812), abs=5e-6
    )
    pick_model(app, "Isotropic")
    assert (m.k2_mean, m.k2_sd, m.RappSD) == pytest.approx((0.66884, 0.71818, 0.23542), abs=5e-6)
    pick_model(app, "DWT (Diffusion)")
    type_into(app, "fret_efficiency", "0.4")
    assert (m.k2_mean, m.k2_sd, m.Rapp_mean) == pytest.approx((0.71815, 0.24988, 1.00486), abs=5e-6)


def test_the_statistics_are_the_analytic_ones(app):
    """Physics: isotropic frozen dipoles have <k2> = 2/3 and SD = 0.72; SD2 and SA2 follow r_inf / r0."""
    pick_model(app, "Isotropic")
    m = app.tool._model
    assert m.k2_mean == pytest.approx(2.0 / 3.0, abs=0.02)
    assert m.k2_sd == pytest.approx(0.7071, abs=0.05)
    assert m.SD2 == pytest.approx(-np.sqrt(0.05 / 0.38)) and m.SA2 == pytest.approx(
        np.sqrt(0.1 / 0.38)
    )


# ── 2. actions, errors ---------------------------------------------------------------------------- #


def test_the_table_shows_every_result_and_the_order_parameters(app):
    rows = {r["quantity"]: r["value"] for r in app.kappa2_gui.result_rows()}
    m = app.tool._model
    assert rows["Mean κ²"] == f"{m.k2_mean:.4f}" and rows["SD R_app/R_DA"] == f"{m.RappSD:.4f}"
    assert rows["δ (deg)"] == f"{m.delta_deg:.2f}"
    strings = draw(app).strings
    assert {
        "Mean κ²",
        "SD κ²",
        "Mean R_app/R_DA",
        "SD R_app/R_DA",
        "δ (deg)",
        rows["Mean κ²"],
    } <= set(strings)


def test_the_compute_button_recomputes_with_the_same_inputs(app):
    m = app.tool._model
    first = m.k2_mean
    draw(app)
    np.random.seed(11)
    click(app, app.item_rects["compute"])
    settle(app)
    assert m.k2_mean != first and m.k2_mean == pytest.approx(
        0.667, abs=0.02
    )  # another seed, the same distribution


def test_typed_garbage_is_ignored_clamped_and_arrows_step(app):
    m = app.tool._model
    type_into(app, "r_Dinf", "abc")
    assert m.r_Dinf == 0.05
    type_into(app, "r_Dinf", "9")
    assert m.r_Dinf == 0.4  # the Qt maximum
    type_into(app, "n_bins", "3")
    assert m.n_bins == 5
    type_into(app, "fret_efficiency", "7")
    assert m.fret_efficiency == 0.999
    draw(app)
    x, y, w, h = app.item_rects["kappa2_true.stepper"]
    before = m.kappa2_true
    np.random.seed(7)
    app.press(x + w / 2, y + h * 0.25)
    draw(app, frames=1)
    app.release()
    settle(app)
    assert m.kappa2_true == pytest.approx(before + 0.01)  # the Qt spin box's step


def test_an_edit_while_computing_is_not_lost(app):
    m = app.tool._model
    draw(app)
    app.kappa2_gui.on_compute()
    assert app.tool.busy
    m.kappa2_true = 1.5
    app.kappa2_gui.on_edit()
    settle(app)
    assert m.kappa2_true == 1.5 and app.tool.dirty is False


def test_a_failing_backend_is_reported_and_the_plot_says_so(app, monkeypatch):
    from chisurf.plugins.calculator.kappa2_dist.backend import services

    monkeypatch.setattr(
        services,
        "compute_kappa2_dist",
        lambda **p: (_ for _ in ()).throw(ValueError("grid is empty")),
    )
    app.tool._model.model_type = "cone"
    app.kappa2_gui.on_compute()
    settle(app)
    assert app.tool.status == "The calculation failed: grid is empty"
    assert "The calculation failed: grid is empty" in draw(app).strings or any(
        "grid is empty" in s for s in draw(app).strings
    )
    assert app.tool._model._k2hist is None and not app.kappa2_gui.has_results()
    monkeypatch.undo()
    app.kappa2_gui.on_compute()
    settle(app)
    assert app.tool.status == "" and app.kappa2_gui.has_results()


def test_inputs_without_a_finite_result_are_reported(app):
    """The Qt tool showed 1e+308-like garbage for these; the native window says what happened."""
    app.tool._model.rAD_known = True
    app.tool._model.r_ADinf = 0.4
    np.random.seed(7)
    app.kappa2_gui.on_compute()
    settle(app)
    assert np.isnan(app.tool._model.k2_mean)
    assert "no finite result" in app.tool.status
    assert any("no finite result" in s for s in draw(app).strings)
    type_into(app, "r_ADinf", "0.005")
    assert app.tool.status == ""


# ── 3. Save ------------------------------------------------------------------------------------------- #


def run_save(app, target, size=SIZE):
    """Press Save, then drive the file dialog to the target file."""
    draw(app, size)
    click(app, app.item_rects["save"], size)
    assert app.write_csv  # the export helper installed its request
    return draw(app, size)


def test_save_writes_the_csv_the_qt_tool_wrote_and_says_so(app, qt_tool, tmp_path):
    np.random.seed(7)
    app.tool._model.compute(
        __import__("types").SimpleNamespace(
            compute=__import__(
                "chisurf.plugins.calculator.kappa2_dist.backend.services", fromlist=["x"]
            )._kappa2_compute_handler
        )
    )
    target = tmp_path / "k2.csv"
    app.write_csv(target)
    assert app.tool.status == f"Saved to k2.csv ({tmp_path})"
    qt_target = tmp_path / "qt.csv"
    qt_tool._module.QtWidgets.QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(qt_target), "")
    )
    shown = {}
    qt_tool._module.dialogs.information = lambda parent, title, text: shown.update(
        info=(title, text)
    )
    np.random.seed(7)
    qt_tool._do_compute()
    qt_tool._on_save()
    assert shown["info"][0] == "Save Successful"
    assert (
        target.read_text() == qt_target.read_text()
    )  # header, bins and probabilities, byte for byte


def test_save_opens_the_file_dialog_writes_nothing_until_it_returns_and_cancel_closes_it(
    app, tmp_path
):
    painter = run_save(app, tmp_path)
    assert {"Cancel", "kappa2.csv"} <= set(
        painter.strings
    )  # the dialog is open, suggesting the file name
    assert not list(tmp_path.glob("*.csv"))
    from emtk import file_dialog as export

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(export.FileDialog, "draw", lambda self: False)  # Cancel
        assert "Cancel" not in draw(app).strings
    assert not list(tmp_path.glob("*.csv")) and app.tool.status == ""


def test_save_through_the_dialog_adds_the_extension_and_reports_it(app, tmp_path, monkeypatch):
    from emtk import file_dialog as export

    run_save(app, tmp_path)
    monkeypatch.setattr(export.FileDialog, "draw", lambda self: [str(tmp_path / "distribution")])
    draw(app)
    written = tmp_path / "distribution.csv"
    assert written.is_file() and written.read_text().startswith(
        "# Kappa2 Distribution\n# Model: cone"
    )
    assert app.tool.status == f"Saved to distribution.csv ({tmp_path})"
    shown = " ".join(draw(app).strings)
    assert "Saved to distribution.csv" in shown


def test_save_to_an_unwritable_place_keeps_the_dialog_with_the_error(app, tmp_path, monkeypatch):
    from emtk import file_dialog as export

    run_save(app, tmp_path)
    monkeypatch.setattr(
        export.FileDialog, "draw", lambda self: [str(tmp_path / "missing_folder" / "k2.csv")]
    )
    strings = draw(app).strings
    assert any("Could not save" in s or "missing_folder" in s for s in strings)
    monkeypatch.setattr(export.FileDialog, "draw", lambda self: False)
    draw(app)  # Cancel dismisses it: the error box is not stuck
    assert not any("missing_folder" in s for s in draw(app).strings)


def test_save_is_disabled_until_a_distribution_exists_like_the_qt_button(app):
    assert app.kappa2_gui.has_results()
    app.tool._model._k2hist = None
    assert not app.kappa2_gui.has_results()
    app.tool._model._k2hist = np.zeros(5)
    assert not app.kappa2_gui.has_results()  # no weight: the Qt button was disabled for this too
    draw(app)
    click(app, app.item_rects["save"])  # a disabled button does nothing
    assert "Cancel" not in draw(app).strings


def test_exporting_nothing_is_an_error_not_a_file(app, tmp_path):
    app.tool._model._k2scale = None
    with pytest.raises(ValueError, match="Compute a distribution"):
        app.write_csv(tmp_path / "nothing.csv")
    assert not (tmp_path / "nothing.csv").exists()


# ── 4. drawing, spec, tooltips -------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_draws_form_plot_and_statistics(app, size):
    strings = settle(app, size).strings
    for label in (
        "Compute",
        "Save",
        "Guide",
        "Help",
        "Model",
        "r₀ (fund.)",
        "r_D∞",
        "r_A∞",
        "r_AD∞",
        "true κ²",
        "FRET E",
        "Step (°)",
        "Bins",
        "r_AD known (use δ)",
        "Mean κ²",
        "SD κ²",
        "Quantity",
        "Value",
    ):
        assert label in strings, (size, label)
    assert any(s.startswith("true κ² = ") for s in strings)


def test_every_editable_field_has_arrows_and_the_qt_range_and_step(app):
    spec = json.loads((PLUGIN / "k2dist.view.json").read_text(encoding="utf-8"))
    qt = {
        s["attr"]: s
        for p in spec["sections"]
        for s in p.get("sections", [])
        if s.get("type") == "value" and not s.get("read_only")
    }
    native = {
        s["attr"]: s
        for p in app.kappa2_gui.input_spec["sections"]
        for s in p.get("sections", [])
        if s.get("type") == "value"
    }
    assert (
        set(native)
        == set(qt)
        == {
            "r_0",
            "r_Dinf",
            "r_Ainf",
            "r_ADinf",
            "kappa2_true",
            "fret_efficiency",
            "step",
            "n_bins",
        }
    )
    for attr, section in native.items():
        assert section["style"] == "spin"
        assert (section["minimum"], section["maximum"], section.get("step")) == (
            qt[attr]["minimum"],
            qt[attr]["maximum"],
            qt[attr].get("step"),
        ), attr


def test_no_emoji_and_the_model_choice_lists_the_qt_labels(app):
    strings = draw(app).strings
    assert all(ord(ch) < 0x2190 or ch in "κ²₀∞δ°ₐ₂" for text in strings for ch in text), strings
    draw(app)
    click(app, app.item_rects["model_type"])
    assert {"WIC (Cone)", "DWT (Diffusion)", "Isotropic"} <= set(draw(app, frames=1).strings)


def test_the_assumed_kappa2_follows_the_constructor_argument():
    assert make_app(kappa2=1.0).tool._model.kappa2_true == 1.0
    assert make_app().tool._model.kappa2_true == 0.667


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("kappa2_dist"))["controls_without_tooltip"] == []
    settle(app)
    inventory = emtk_inventory(app)
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {"Compute", "Save", "Guide", "Help", "r_0", "n_bins", "r_AD known (use δ)"} <= labels
    spec = json.loads((PLUGIN / "k2dist.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle") and not s.get("read_only"):
                assert s.get("description"), s.get("attr")
            walk(s.get("sections", []))

    walk(spec["sections"])
    for column in __import__(
        "chisurf.plugins.calculator.kappa2_dist.gui.app", fromlist=["x"]
    ).RESULTS_TABLE["sections"][0]["options"]["columns"]:
        assert column.get("description")


# ── 5. guide and help -------------------------------------------------------------------------------------- #


def test_guide_targets_are_drawn_and_the_tour_waits_for_the_user(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    settle(app)
    steps = json.loads((PLUGIN / "gui/guide.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        target = step.get("target") or {}
        if target:
            name = EmTkGuidedTour._target_key(target)
            assert app.item_rects.get(name), f"{step['title']}: nothing drawn for {name!r}"
    assert [s["title"] for s in steps if s.get("await")] == [
        "Start with the worst case",
        "Compute, and read the mean",
        "Now use your own dyes",
        "The inputs are anisotropy fits, not guesses",
    ]
    assert (
        "Press <b>Help</b>" in steps[-1]["text"] and "<b>?</b>" not in steps[-1]["text"]
    )  # the Qt '?' is Help here
    app.kappa2_gui.tour.start(1)
    draw(app)
    assert app.kappa2_gui.tour.awaiting
    pick_model(app, "Isotropic")
    assert not app.kappa2_gui.tour.awaiting
    app.kappa2_gui.tour.next()
    draw(app)
    assert app.kappa2_gui.tour.awaiting  # Compute is next
    click(app, app.item_rects["compute"])
    assert not app.kappa2_gui.tour.awaiting


def test_guide_and_help_buttons_open_the_tour_and_the_help(app):
    draw(app)
    click(app, app.item_rects["guide"])
    assert app.kappa2_gui.tour.active
    app.kappa2_gui.tour.stop()
    draw(app)
    click(app, app.item_rects["help"])
    assert app.kappa2_gui.help_window.open and draw(app).strings


def test_help_links_are_live_and_the_text_is_plain():
    text = (PLUGIN / "gui/help.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert links and all((REPO / link).is_file() for link in links), links


# ── 6. persistence, manifest, no Qt, host -------------------------------------------------------------------- #


def test_settings_round_trip_and_invalid_values_are_ignored(app):
    pick_model(app, "DWT (Diffusion)")
    type_into(app, "r_Dinf", "0.2")
    type_into(app, "n_bins", "80")
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["model_type"] == "diffusion" and saved["r_Dinf"] == 0.2 and saved["n_bins"] == 80
    assert set(saved) == set(INPUT_FIELDS)
    other = make_app()
    other.restore_settings(saved)
    settle(other)
    assert other.export_settings() == saved
    assert other.tool._model.k2_mean != 0.0 and other.tool._model.model_type == "diffusion"
    other.restore_settings(
        {
            "model_type": "bogus",
            "r_0": float("nan"),
            "r_Dinf": 9,
            "n_bins": "x",
            "rAD_known": "yes",
            "step": 1e9,
            "fret_efficiency": -4,
        }
    )
    settle(other)
    assert (
        other.tool._model.model_type == "diffusion" and other.tool._model.r_0 == 0.38
    )  # unusable: unchanged
    assert (
        other.tool._model.r_Dinf == 0.4 and other.tool._model.step == 10.0
    )  # out of range: clamped
    assert other.tool._model.fret_efficiency == 0.001 and other.tool._model.rAD_known is False
    other.restore_settings("garbage")
    assert draw(other).strings


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("kappa2_dist")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["entrypoints"]["emtk"] == "chisurf.plugins.calculator.kappa2_dist.gui.app:make_app"
    )
    assert isinstance(make_app(), Kappa2App)


def test_the_idle_window_does_not_ask_for_frames_and_a_nan_result_does_not_recompute_forever(app):
    settle(app)
    assert app.continuous is False
    app.tool._model.rAD_known, app.tool._model.r_ADinf = True, 0.4
    app.kappa2_gui.on_compute()
    settle(app)
    assert np.isnan(app.tool._model.k2_mean)
    for _ in range(5):  # NaN != NaN: watching every float re-ran the computation on every frame
        draw(app, frames=1)
        time.sleep(0.01)
    assert app.tool.busy is False and app.tool.dirty is False
