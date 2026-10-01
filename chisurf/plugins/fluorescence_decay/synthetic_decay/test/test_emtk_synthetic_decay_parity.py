"""The native synthetic decay generator against the Qt tool and the canonical generator.

Hermetic: settings in a temporary folder, IRF and spectrum files written into ``tmp_path``, the fit
group goes to a stub sink (no session, no datasets registered). Numbers are checked against
``core.algorithms`` (the canonical generator), against analytic expressions, and against the Qt tool.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import (
    compute_aniso_decay,
    compute_decay,
    compute_rt,
)
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import SyntheticDecayApp, make_app
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.model import SyntheticDecayModel

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SIZE = (1200, 900)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


@pytest.fixture
def app():
    a = SyntheticDecayApp(fit_sink=lambda group, polarized: None)
    yield a
    a.close() if hasattr(a, "close") else None


def draw(app, size=SIZE, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE):
    x, y, w, h = rect
    app.press(x + w / 2, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def press_action(app, name):
    draw(app)
    rect = app.item_rects.get(name) or app.form.rects[name]
    click(app, rect)


def cell(app, source, row, key, text):
    """Type *text* into a table cell the way the control does on a double click and Enter."""
    control = app.form.tables[source].control
    control.begin_edit(row, key)
    control.editor.set_text(text)
    control.commit_edit()


# ── 1. numbers equal the canonical generator, analytic values and the Qt tool ──


def test_vm_decay_equals_the_canonical_generator_and_the_analytic_shape(app):
    m = app.model
    m.spectrum_rows = [{"amp": 1.0, "tau": 2.0}]
    m.generate()
    ref = compute_decay(n_bins=256, bin_width=0.032, lifetimes=[2.0], amplitudes=[1.0])
    np.testing.assert_allclose(m._y, ref["y"])
    np.testing.assert_allclose(m._x, ref["x"])
    y = np.asarray(m._y)
    assert y.sum() == pytest.approx(1.0)  # normalized when noise is off
    assert np.allclose(y[1:] / y[:-1], np.exp(-0.032 / 2.0))  # a single exponential is log-linear
    assert [s["name"] for s in m.decay_series()] == ["decay"]
    r = compute_rt(n_bins=256, bin_width=0.032, rotation_rows=m.rotation_rows)["r"]
    np.testing.assert_allclose(m._r, r)
    assert m._r[0] == pytest.approx(0.2) and m._r[-1] == pytest.approx(0.2 * np.exp(-255 * 0.032 / 1.0))
    assert m.status_text() == "Generated 256 bins (1 components)."


def test_vv_vh_pair_equals_the_canonical_generator_and_the_g_ratio(app):
    m = app.model
    m.set_polarization("vv/vh")
    m.g_factor, m.l1, m.l2 = 1.3, 0.02, 0.05
    m.generate()
    ref = compute_aniso_decay(
        n_bins=256, bin_width=0.032, lifetimes=[1.2, 4.0], amplitudes=[1.0, 1.0],
        rotation_rows=m.rotation_rows, g_factor=1.3, l1=0.02, l2=0.05,
    )
    np.testing.assert_allclose(m._vv, ref["vv"])
    np.testing.assert_allclose(m._vh, ref["vh"])
    np.testing.assert_allclose(m._r, ref["r"])
    assert [s["name"] for s in m.decay_series()] == ["VV", "VH"]
    assert m.status_text() == "Generated VV/VH pair, 256 bins (2 lifetimes, 1 rotations, g=1.3, l1=0.02, l2=0.05)."
    # no anisotropy, no mixing: VH is VV divided by g (the detection sensitivity ratio)
    m.rotation_rows, m.l1, m.l2 = [{"b": 0.0, "rho": 1.0}], 0.0, 0.0
    m.generate()
    np.testing.assert_allclose(np.asarray(m._vh), np.asarray(m._vv) / 1.3)


def test_noise_is_reproducible_by_seed_and_spends_the_photon_budget(app):
    m = app.model
    m.shot_noise, m.photon_count, m.seed = True, 200000.0, 7
    m.generate()
    first = list(m._y)
    assert abs(sum(first) - 200000.0) < 5 * np.sqrt(200000.0)  # Poisson counts around the budget
    assert np.all(np.equal(first, np.round(first)))  # integer counts
    m.generate()
    assert m._y == first  # same seed, same realisation
    m.seed = 8
    m.generate()
    assert m._y != first
    ref = compute_decay(n_bins=256, bin_width=0.032, lifetimes=[1.2, 4.0], amplitudes=[1.0, 1.0],
                        normalize=False, photon_count=200000.0, seed=8)
    np.testing.assert_allclose(m._y, ref["y"])


def test_an_irf_file_smears_the_prompt_and_a_missing_one_is_an_error(app, tmp_path):
    m = app.model
    t = np.arange(256) * 0.032
    irf = tmp_path / "irf.txt"
    np.savetxt(irf, np.exp(-0.5 * ((t - 1.0) / 0.1) ** 2))
    m.irf_path = str(irf)
    m.generate()
    assert int(np.argmax(m._y)) > 25  # the peak moved to the IRF, not bin 0
    ref = compute_decay(n_bins=256, bin_width=0.032, lifetimes=[1.2, 4.0], amplitudes=[1.0, 1.0], irf=str(irf))
    np.testing.assert_allclose(m._y, ref["y"])
    m.irf_path = str(tmp_path / "missing.txt")
    m.generate()
    assert m.status_text() == f"Error: IRF file does not exist: {tmp_path / 'missing.txt'}"
    assert m.decay_series() == [] and m.aniso_series() == []  # no stale curve survives an error


def test_the_native_app_and_the_qt_tool_generate_the_same_numbers(qapp, app):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool

    tool = SyntheticDecayTool()
    try:
        for model in (tool.model, app.model):
            model.update_spectrum(0, "tau", 0.5)
            model.add_row()
            model.update_spectrum(2, "amp", 0.25)
            model.update_spectrum(2, "tau", 9.0)
            model.shot_noise, model.photon_count, model.seed = True, 200000.0, 7
            model.set_polarization("vv/vh")
            model.g_factor, model.l1, model.l2 = 1.3, 0.02, 0.05
            model.generate()
        assert tool.model._vv == app.model._vv and tool.model._vh == app.model._vh
        assert tool.model._r == app.model._r
        assert tool.model.status_text() == app.model.status_text()
        assert tool.model.aniso_metadata() == app.model.aniso_metadata()
        # and the table the Qt window shows holds the rows the native table shows
        from qtpy import QtWidgets

        qapp.processEvents()
        table = next(t for t in tool.form.findChildren(QtWidgets.QTableWidget) if t.rowCount() == 3)
        qt_cells = [[float(table.item(r, c).text()) for c in range(2)] for r in range(3)]
        assert qt_cells == [[row["amp"], row["tau"]] for row in app.model.spectrum_rows]
    finally:
        tool.deleteLater()


# ── 2. every action and its error path, by the buttons ──────────────────


def test_generate_button_generates_and_the_status_says_so(app):
    press_action(app, "generate")
    assert len(app.model._y) == 256 and app.model.status_text() == "Generated 256 bins (2 components)."
    assert any("Generated 256 bins" in s for s in draw(app).strings)


def test_a_cell_edit_reaches_the_model_and_the_generated_decay(app):
    """The table section's edit is wired to the model (the Qt spec's update_call is not read natively)."""
    draw(app)
    cell(app, "spectrum_records", 0, "tau", "2.5")
    cell(app, "spectrum_records", 1, "amp", "3")
    assert app.model.spectrum_rows == [{"amp": 1.0, "tau": 2.5}, {"amp": 3.0, "tau": 4.0}]
    cell(app, "rotation_records", 0, "rho", "2")
    assert app.model.rotation_rows == [{"b": 0.2, "rho": 2.0}]
    cell(app, "spectrum_records", 0, "tau", "oops")  # a typo leaves the cell as it was
    assert app.model.spectrum_rows[0]["tau"] == 2.5
    app.model.generate()
    ref = compute_decay(n_bins=256, bin_width=0.032, lifetimes=[2.5, 4.0], amplitudes=[1.0, 3.0])
    np.testing.assert_allclose(app.model._y, ref["y"])
    assert all(type(v) is float for row in app.model.spectrum_rows for v in row.values())


def test_add_and_remove_buttons_edit_both_tables(app):
    draw(app)
    click(app, app.form.rects["add_row"])
    assert len(app.model.spectrum_rows) == 3 and app.model.spectrum_rows[-1] == {"amp": 1.0, "tau": 2.0}
    app.model.selected_row = 2
    click(app, app.form.rects["remove_row"])
    assert len(app.model.spectrum_rows) == 2
    app.model.spectrum_rows = app.model.spectrum_rows[:1]
    app.model.selected_row = 0
    click(app, app.form.rects["remove_row"])
    assert len(app.model.spectrum_rows) == 1  # the last component is never removed
    click(app, app.form.rects["add_rotation_row"])
    assert app.model.rotation_rows[-1] == {"b": 0.1, "rho": 2.0}
    app.model.selected_rotation_row = 1
    click(app, app.form.rects["remove_rotation_row"])
    assert len(app.model.rotation_rows) == 1


def test_the_table_shows_rows_added_and_loaded_without_a_rebuild(app, tmp_path):
    draw(app)
    app.model.add_row()
    draw(app)
    assert app.form.tables["spectrum_records"].control.row_count() == 3
    spectrum = tmp_path / "spectrum.csv"
    np.savetxt(spectrum, [[0.3, 1.2], [0.7, 4.0]], delimiter=",")
    app.model.load_spectrum(str(spectrum))
    draw(app)
    assert app.form.tables["spectrum_records"].control.row_count() == 2
    assert app.model.status_text() == "Loaded 2 components from spectrum.csv."


def test_load_and_save_dialogs_do_the_work(app, tmp_path, monkeypatch):
    from emtk.file_dialog import FileDialog

    draw(app)
    spectrum = tmp_path / "spectrum.csv"
    np.savetxt(spectrum, [[0.3, 1.2], [0.7, 4.0]], delimiter=",")
    click(app, app.form.rects["load_spectrum"])
    assert app.dialog is not None and app.dialog_action == "load_spectrum"
    monkeypatch.setattr(FileDialog, "draw", lambda self: [str(spectrum)])
    draw(app, frames=1)
    assert app.dialog is None and [r["amp"] for r in app.model.spectrum_rows] == [0.3, 0.7]
    app.model.generate()
    out = tmp_path / "decay.csv"
    monkeypatch.undo()
    press_action(app, "save")
    assert app.dialog is not None and app.dialog_action == "save"
    monkeypatch.setattr(FileDialog, "draw", lambda self: False)
    draw(app, frames=1)
    assert app.dialog is None and not out.exists()  # cancel writes nothing
    monkeypatch.setattr(FileDialog, "draw", lambda self: [str(out)])
    press_action(app, "save")
    assert np.loadtxt(out).shape == (256, 2) and app.model.status_text() == "Saved 256 bins to decay.csv."


def test_save_formats_and_the_vv_vh_file_round_trip(app, tmp_path):
    from chisurf.core.fio.vv_vh import read_vv_vh

    m = app.model
    m.generate()
    npy, js = tmp_path / "d.npy", tmp_path / "d.json"
    m.save(str(npy))
    m.save(str(js))
    np.testing.assert_allclose(np.load(npy), m._y)
    assert json.loads(js.read_text())["y"] == m._y
    m.set_polarization("vv/vh")
    m.g_factor = 1.5
    m.generate()
    pair = tmp_path / "pair.dat"
    m.save(str(pair))
    channels, meta = read_vv_vh(pair, split=True, return_metadata=True)
    np.testing.assert_allclose(channels["VV"], m._vv)
    assert meta["g_factor"] == pytest.approx(1.5) and meta["dt"] == pytest.approx(0.032)
    assert m.status_text() == "Saved VV/VH pair (256 bins) to pair.dat."


def test_save_and_fit_group_before_generate_say_so_like_the_qt_tool(qapp, app, tmp_path):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool

    tool = SyntheticDecayTool()
    try:
        tool.model.save(str(tmp_path / "x.csv"))
        qt_save = tool.model.status_text()
        tool.model.send_to_fit()
        qt_fit = tool.model.status_text()
    finally:
        tool.deleteLater()
    app.model.save(str(tmp_path / "x.csv"))
    assert app.model.status_text() == qt_save == "Nothing to save — press Generate first."
    assert not (tmp_path / "x.csv").exists()
    app.model.send_to_fit()
    assert app.model.status_text() == qt_fit == "Nothing to send — press Generate first."


def test_load_spectrum_errors_equal_the_qt_tool(qapp, app, tmp_path):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool

    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\nx,y\n")
    negative = tmp_path / "negative.csv"
    np.savetxt(negative, [[1.0, -2.0]], delimiter=",")
    tool = SyntheticDecayTool()
    try:
        for path in (bad, negative):
            tool.model.load_spectrum(str(path))
            app.model.load_spectrum(str(path))
            assert app.model.status_text() == tool.model.status_text()
            assert app.model.spectrum_rows == tool.model.spectrum_rows == [{"amp": 1.0, "tau": 1.2}, {"amp": 1.0, "tau": 4.0}]
        assert app.model.status_text().startswith("Invalid lifetime spectrum")
    finally:
        tool.deleteLater()


def test_fit_group_button_sends_the_generated_group_to_the_sink(tmp_path):
    sent = []
    app = SyntheticDecayApp(fit_sink=lambda group, polarized: sent.append((len(group), polarized, dict(group.meta_data))))
    app.model.set_polarization("vv/vh")
    app.model.g_factor, app.model.l1, app.model.l2 = 1.5, 0.03, 0.07
    app.model.generate()
    press_action(app, "send_to_fit")
    assert [(n, p) for n, p, _ in sent] == [(2, True)]
    assert sent[0][2]["g_factor"] == 1.5 and sent[0][2]["source"] == "synthetic_decay"
    assert app.model.status_text() == "Added synthetic dataset and fit group (2 curves)."


def test_a_failing_fit_sink_is_reported_not_raised():
    def boom(group, polarized):
        raise RuntimeError("no session")

    app = SyntheticDecayApp(fit_sink=boom)
    app.model.generate()
    press_action(app, "send_to_fit")
    assert app.model.status_text() == "Fit group failed: no session"


def test_browse_irf_sets_the_path_and_a_cancel_changes_nothing(app, tmp_path, monkeypatch):
    from emtk.file_dialog import FileDialog

    irf = tmp_path / "irf.txt"
    np.savetxt(irf, np.ones(256))
    monkeypatch.setattr(FileDialog, "draw", lambda self: False)
    press_action(app, "irf_path")
    draw(app, frames=1)
    assert app.dialog is None and app.model.irf_path == ""
    monkeypatch.setattr(FileDialog, "draw", lambda self: [str(irf)])
    press_action(app, "irf_path")
    draw(app, frames=1)
    assert app.model.irf_path == str(irf)


def test_the_mode_choice_shows_the_corrections_and_both_plots_draw(app):
    draw(app)
    assert "g_factor" not in app.form.rects
    app.model.set_polarization("vv/vh")
    app.model.generate()
    painter = draw(app)
    assert "g_factor" in app.form.rects
    strings = " ".join(painter.strings)
    assert "VV" in strings and "VH" in strings and "Micro-time (ns)" in strings


# ── 3. drawing, no invented data, labels ────────────────────────────────


def test_the_empty_state_draws_no_curve_and_says_what_to_do(app):
    painter = draw(app)
    assert app.model.decay_series() == [] and app.model.aniso_series() == []
    assert any("Edit the lifetime spectrum and press Generate." in s for s in painter.strings)


@pytest.mark.parametrize("size", [(1200, 900), (1200, 800), (800, 600), (500, 500)])
def test_draws_empty_and_populated(size):
    app = SyntheticDecayApp(fit_sink=lambda g, p: None)
    assert len(draw(app, size).texts) > 10
    app.model.set_polarization("vv/vh")
    app.model.shot_noise = True
    app.model.generate()
    assert any("Generated VV/VH pair" in s for s in draw(app, size).strings)


def test_no_emoji_in_the_native_labels(app):
    strings = draw(app).strings
    assert all(ord(ch) < 0x2190 or ch in "τΔρΣ" for text in strings for ch in text), [
        t for t in strings if any(ord(ch) >= 0x2190 and ch not in "τΔρΣ" for ch in t)
    ]
    labels = {text for text in strings}
    assert {"Add", "Remove", "Load", "Generate", "Save", "Fit group"} <= labels
    assert {"Browse IRF", "Help", "Guide"} <= labels


# ── 4. tooltips, spec, guide, help ──────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    model = SyntheticDecayModel()
    app = SyntheticDecayApp()
    for section in _walk(app.spec["sections"]):
        for key in ("attr", "call", "source", "options_source", "edited_call", "selected_attr"):
            if section.get(key):
                assert hasattr(model, section[key]), (key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
    tables = [s for s in _walk(app.spec["sections"]) if s.get("type") == "table"]
    assert [t["source"] for t in tables] == ["spectrum_records", "rotation_records"]
    assert all(t["edited_call"] == "edit_cell" for t in tables)


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("synthetic_decay"))
    assert inventory["controls_without_tooltip"] == []
    app.model.set_polarization("vv/vh")
    app.model.generate()
    populated = emtk_inventory(app)
    assert populated["controls_without_tooltip"] == []
    labels = {row["label"] for row in populated["interactive"]}
    assert {"Generate", "Save", "Fit group", "Browse IRF", "Help", "Guide", "Add", "Remove", "Load"} <= labels
    spec = json.loads((GUI / "synthetic_decay.view.json").read_text())
    for section in _walk(spec["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "plot", "table", "info"):
            assert section.get("description"), section.get("attr") or section.get("title") or section
        for column in section.get("columns", []):
            assert column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_guide_steps_point_at_controls_the_app_draws(app):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app.model.set_polarization("vv/vh")
    draw(app)
    steps = json.loads((GUI / "guide_emtk.json").read_text())["steps"]
    assert len(steps) == 7
    for step in steps:
        target = step.get("target") or {}
        if not target:
            continue  # the opening step is an introduction
        name = EmTkGuidedTour._target_key(target)
        assert app.target_rect(name), f"{step['title']}: nothing drawn for {name!r}"
    assert [s["title"] for s in steps if s.get("await")] == ["Generate, then vary one thing at a time"]
    assert not any(re.search(r"[\U0001F300-\U0001FAFF]", s["await"]["hint"]) for s in steps if s.get("await"))


def test_the_tour_waits_for_the_generate_press(app):
    app.tour.start(6)
    assert app.tour.awaiting
    press_action(app, "generate")
    assert not app.tour.awaiting
    assert draw(app).strings


def test_the_qt_tool_keeps_its_own_help_and_guide():
    guide = json.loads((GUI / "guide.json").read_text())
    assert "🧪" in guide["steps"][-1]["await"]["hint"]
    assert "**" in (GUI / "help.md").read_text()


def test_help_exists_its_links_are_live_and_it_draws(app):
    text = (GUI / "help_emtk.md").read_text()
    assert "**" not in text and "`" not in text  # the native help window shows Markdown marks raw
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)\)", text)
    assert len(links) == 5 and all((repo / link).is_file() for link in links)
    app.help_window.show()
    assert draw(app).strings


# ── 5. persistence, no Qt ───────────────────────────────────────────────


def test_settings_round_trip_and_invalid_values_are_ignored(app, tmp_path):
    m = app.model
    m.update_spectrum(0, "tau", 0.7)
    m.add_row()
    m.n_bins, m.bin_width, m.start_bin, m.irf_path = 128, 0.05, 3, str(tmp_path / "irf.txt")
    m.shot_noise, m.photon_count, m.seed = True, 5e4, 11
    m.set_polarization("vv/vh")
    m.g_factor, m.l1, m.l2 = 1.2, 0.01, 0.02
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["spectrum_rows"][0] == {"amp": 1.0, "tau": 0.7} and saved["polarization"] == "vv/vh"
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved
    other.restore_settings({"n_bins": "lots", "bin_width": float("nan"), "seed": -5, "g_factor": 1e9,
                            "polarization": "diagonal", "spectrum_rows": [{"amp": 1.0}], "shot_noise": "yes"})
    assert other.model.n_bins == 128 and other.model.bin_width == 0.05  # unusable values change nothing
    assert other.model.seed == 0 and other.model.g_factor == 100.0  # out-of-range values are clamped
    assert other.model.polarization == "vv/vh" and len(other.model.spectrum_rows) == 3
    assert other.model.shot_noise is True
    assert draw(other).strings


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("synthetic_decay")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app:make_app"
    assert isinstance(make_app(), SyntheticDecayApp)
