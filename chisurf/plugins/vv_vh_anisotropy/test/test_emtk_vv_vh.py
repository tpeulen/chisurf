"""The VV/VH anisotropy app: r(t), r-infinity, the saved files, the batch, the window.

The input is generated (:func:`make`) with a planted residual anisotropy, and r(t) is checked against the
documented formula recomputed here from the input file: after background subtraction, an optional VV/VH swap
and a linearly interpolated shift of VH, ``r = (VV - g VH) / ((1 - 3 l2) VV + (2 - 3 l1) g VH)``;
r-infinity is the mean of the finite r(t) over the region ``[lo, hi)`` of channels.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.vv_vh_anisotropy.gui import app as app_module
from chisurf.plugins.vv_vh_anisotropy.gui.app import create_app
from chisurf.plugins.vv_vh_anisotropy.gui.model import AnisotropyModel

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
GUI = HERE.parent / "gui"


def make(path, seed=1, n=256, tau=40.0, rho=18.0, r0=0.36, rinf=0.05, g=1.0, bg_vv=12.0, bg_vh=9.0):
    """A VV/VH decay pair with Poisson noise, VV then VH in one column; r(t) decays from r0 to ``rinf``."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    i = 60000.0 * np.exp(-t / tau)
    r = rinf + (r0 - rinf) * np.exp(-t / rho)
    vv = rng.poisson(i * (1 + 2 * r) / 3.0 + bg_vv).astype(float)
    vh = rng.poisson(g * i * (1 - r) / 3.0 + bg_vh).astype(float)
    np.savetxt(path, np.r_[vv, vh], fmt="%d")
    return Path(path)


@pytest.fixture
def files(tmp_path):
    return make(tmp_path / "a.dat", seed=1), make(tmp_path / "b.dat", seed=2, rinf=0.08)


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


@pytest.fixture
def app():
    app = create_app()
    yield app
    app.close()


# r(t) recomputed from the input file -----------------------------------------------------------

SETTINGS = [
    dict(g=1.0, bg=(0.0, 0.0), apply_bg=False, shift=0.0, flip=False),
    dict(g=1.05, bg=(12.0, 9.0), apply_bg=True, shift=1.5, flip=False),
    dict(g=0.9, bg=(12.0, 9.0), apply_bg=True, shift=-2.25, flip=True),
]


def _set_model(model, s):
    model.g_factor, (model.bg_vv, model.bg_vh) = s["g"], s["bg"]
    model.apply_bg, model.shift, model.flip = s["apply_bg"], s["shift"], s["flip"]
    model.compute()


def expected_r(path, s):
    """r(t) of the file at *path* under the settings *s*, from the documented formula (l1 = l2 = 0)."""
    raw = np.loadtxt(path)
    vv, vh = raw[: raw.size // 2], raw[raw.size // 2 :]
    if s["flip"]:
        vv, vh = vh, vv
    if s["apply_bg"]:
        vv, vh = vv - s["bg"][0], vh - s["bg"][1]
    t = np.arange(vh.size, dtype=float)
    query = t - s["shift"]
    inside = (query >= 0) & (query <= t[-1])
    shifted = np.full(vh.size, np.nan)
    shifted[inside] = np.interp(query[inside], t, vh)
    g = s["g"]
    with np.errstate(divide="ignore", invalid="ignore"):
        return (vv - g * shifted) / (vv + 2.0 * g * shifted)


def mean_over(r, lo, hi):
    part = r[int(lo) : int(hi)]
    return float(np.mean(part[np.isfinite(part)]))


# 1. r(t), r-infinity and the saved files follow the formula, for every setting
@pytest.mark.parametrize(
    "index", range(len(SETTINGS)), ids=["plain", "bg+shift", "flip+negative-shift"]
)
def test_trace_rinf_and_files_follow_the_formula(files, tmp_path, index):
    settings = SETTINGS[index]
    a, _ = files
    model = AnisotropyModel()
    model.load(a)
    _set_model(model, settings)
    assert model.region_bounds == [179.0, 230.0]  # 70 % and 90 % of the 256 channels
    expected = expected_r(a, settings)
    np.testing.assert_allclose(model.r_t, expected, rtol=1e-12, equal_nan=True)
    assert model.r_infty == pytest.approx(mean_over(expected, 179, 230), rel=1e-12)
    assert model.r_infty_text == f"{model.r_infty:.5f}"
    if index == 0:  # no correction needed: the planted residual anisotropy comes back
        assert model.r_infty == pytest.approx(0.05, abs=0.01)
    out = tmp_path / "emtk" / "r.txt"
    out.parent.mkdir()
    model.save(out)
    trace = np.loadtxt(out.parent / "r_anisotropy.txt", skiprows=1)
    assert (out.parent / "r_anisotropy.txt").read_text().splitlines()[0] == "channel\tr(t)\tr(t)-r_inf"
    np.testing.assert_array_equal(trace[:, 0], np.arange(256.0))
    np.testing.assert_allclose(trace[:, 1], model.r_t, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(trace[:, 2], model.r_t - model.r_infty, rtol=1e-9, atol=1e-12, equal_nan=True)
    (row,) = csv.DictReader((out.parent / "r_rinf.csv").open())
    assert row["filename"] == "a.dat" and float(row["r_inf"]) == model.r_infty
    assert [float(row[k]) for k in ("region_min", "region_max", "bg_vv", "bg_vh", "g_factor")] == [
        179.0,
        230.0,
        *settings["bg"],
        settings["g"],
    ]


# 2. _shifted.dat reads back as the background-corrected VV and the shifted VH
def test_shifted_decays_are_written_and_read_back(files, tmp_path):
    a, _ = files
    model = AnisotropyModel()
    model.load(a)
    model.bg_vv, model.bg_vh, model.shift = 12.0, 9.0, 1.5
    model.compute()
    decay, _, _ = model.save(tmp_path / "out.txt")
    from chisurf.core.fio import read_vv_vh

    data = read_vv_vh(str(decay), split=True)
    vv, vh = (data["VV"], data["VH"]) if isinstance(data, dict) else data
    cvv, cvh = model.corrected_channels()
    shifted = np.nan_to_num(AnisotropyModel.shifted(cvh, 1.5), nan=0.0)
    np.testing.assert_allclose(vv, np.where(cvv > 0, cvv, 0.0), rtol=1e-9)
    np.testing.assert_allclose(vh, np.where(shifted > 0, shifted, 0.0), rtol=1e-6, atol=1e-6)
    assert len(vv) == len(vh) == 256


# 3. the batch rows: r-infinity of each file over the snapshot's region, clamped to the last channel
@pytest.mark.parametrize(
    "index", range(len(SETTINGS)), ids=["plain", "bg+shift", "flip+negative-shift"]
)
def test_batch_rows_follow_the_formula(files, index):
    settings = SETTINGS[index]
    snap_in = {
        "apply_bg": settings["apply_bg"],
        "bg_vv": settings["bg"][0],
        "bg_vh": settings["bg"][1],
        "g": settings["g"],
        "shift": settings["shift"],
        "flip": settings["flip"],
        "region_min": 150.0,
        "region_max": 400.0,
    }  # past the last channel: clamped
    model = AnisotropyModel()
    model.batch_snapshot = dict(snap_in)
    model.batch_files = [str(p) for p in files]
    rows = model.run_batch()
    assert [row[0] for row in rows] == ["a.dat", "b.dat"]
    for row, path in zip(rows, files):
        assert row[1] == pytest.approx(mean_over(expected_r(path, settings), 150, 255), rel=1e-12)
        assert list(row[2:7]) == [150.0, 255.0, *settings["bg"], settings["g"]]
        assert row[7] == ""
    if index == 0:  # the planted residual anisotropies
        assert (rows[0][1], rows[1][1]) == (pytest.approx(0.05, abs=0.01), pytest.approx(0.08, abs=0.01))


# 4. the batch uses the settings the window was opened with, not later edits
def test_batch_uses_the_snapshot_taken_when_the_window_opens(files):
    a, b = files
    model = AnisotropyModel()
    model.load(a)
    model.g_factor = 1.05
    model.compute()
    model.open_batch()
    model.g_factor = 3.0  # edited after the window opened
    model.compute()
    model.batch_files = [str(a)]
    (row,) = model.run_batch()
    assert row[6] == 1.05
    reference = AnisotropyModel()
    reference.load(a)
    reference.g_factor = 1.05
    reference.compute()
    assert row[1] == pytest.approx(reference.r_infty)
    assert model.loaded_file == str(a) and model.g_factor == 3.0  # the main state is untouched


# 5. load: errors keep the loaded data and say why
def test_load_errors_are_reported_and_keep_the_data(app, files, tmp_path):
    a, _ = files
    assert app.load_file(a)
    before = app.model.r_t.copy()
    empty = tmp_path / "words.dat"
    empty.write_text("not numbers\n")
    odd = tmp_path / "odd.dat"
    odd.write_text("1\n2\n3\n")
    for bad in (empty, odd, tmp_path / "missing.dat"):
        assert app.load_file(bad) is False
        assert app.model.message.startswith(f"Could not load {bad.name}"), app.model.message
        assert app.model.loaded_file == str(a)
        np.testing.assert_array_equal(app.model.r_t, before)
    assert any("Could not load missing.dat" in s for s in _draw(app).strings)  # on the status line


# 6. Save: refused until data is loaded; the three files; an unwritable target is an error line
def test_save_outputs_and_its_error_path(app, files, tmp_path):
    a, _ = files
    assert not app.model.enabled("request_save")
    app.model.request_save()  # e.g. a stale request
    _draw(app)
    assert app.dialog is None and app.model.message == "Pick a VV/VH file before saving outputs."
    app.load_file(a)
    assert app.model.enabled("request_save")
    out = tmp_path / "res.txt"
    app.model.request_save()
    _draw(app)
    assert app.dialog is not None and app.dialog_request == "save"
    app.dialog.draw = lambda: [str(out)]
    _draw(app, times=1)
    assert app.dialog is None
    names = sorted(p.name for p in tmp_path.glob("res_*"))
    assert names == ["res_anisotropy.txt", "res_rinf.csv", "res_shifted.dat"]
    assert "Saved res_shifted.dat" in app.model.message
    row = next(csv.DictReader((tmp_path / "res_rinf.csv").open()))
    assert row["filename"] == "a.dat" and float(row["r_inf"]) == pytest.approx(app.model.r_infty)
    # the target's folder is a file: the failure is the status line, and the data is still there
    app.model.request_save()
    _draw(app)
    app.dialog.draw = lambda: [str(a / "x.txt")]
    _draw(app, times=1)
    assert app.dialog is None and app.model.message.startswith(
        ("NotADirectoryError", "FileExistsError", "OSError")
    )
    assert app.model.has_data
    # The message names the target path, so it wraps onto several drawn lines when the
    # path is long; the status shows it when a drawn line starts with its error prefix.
    prefix = app.model.message.split(":", 1)[0]
    assert any(s.startswith(prefix) for s in _draw(app).strings)


def test_cancelling_a_dialog_changes_nothing(app, files, tmp_path):
    a, _ = files
    app.model.load(a)
    app.model.request_save()
    _draw(app)
    assert app.dialog is not None
    app.dialog.draw = lambda: False
    _draw(app, times=1)
    assert app.dialog is None and app.model.loaded_file == str(a)
    assert not list(tmp_path.glob("*_rinf.csv"))


# 7. Load what the workspace hands over
def test_load_what_the_workspace_hands_over(app, files):
    from chisurf.plugins.vv_vh_anisotropy.gui.app import receive_file

    a, _ = files
    receive_file(app, {"file": [str(a)]})
    assert app.model.loaded_file == str(a) and app.model.message == "Loaded a.dat: 256 channels"
    painter = _draw(app)
    assert any("a.dat" in s for s in painter.strings) and "0.01..." not in painter.strings


# 8. the fields: ranges, five decimals of g, and the region bounds that the plot's lines also move
def test_fields_clamp_and_the_region_is_ordered_for_the_average(app, files):
    a, _ = files
    app.load_file(a)
    model = app.model
    spec = json.loads((GUI / "vv_vh_emtk.view.json").read_text(encoding="utf-8"))
    fields = {}

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                fields[s["attr"]] = s
            walk(s.get("sections", []))

    walk(spec["sections"])
    assert (
        fields["g_factor"]["minimum"],
        fields["g_factor"]["maximum"],
        fields["g_factor"]["decimals"],
    ) == (0.0, 10.0, 5)
    assert (fields["shift"]["minimum"], fields["shift"]["maximum"]) == (-150.0, 150.0)
    assert (
        fields["bg_vv"]["decimals"],
        fields["bg_vh"]["decimals"],
        fields["shift"]["decimals"],
    ) == (3, 3, 3)
    assert fields["apply_bg"]["type"] == "toggle" and model.apply_bg is True and model.flip is False
    model.region_start, model.region_end = 100.0, 140.0
    model.compute()
    forward = model.r_infty
    model.region_start, model.region_end = 140.0, 100.0  # lines dragged past each other
    model.compute()
    assert model.r_infty == pytest.approx(forward) and (model.region_min, model.region_max) == (
        100.0,
        140.0,
    )
    model.recompute(1.0)
    assert model.r_infty_text == f"{forward:.5f}"
    model.vv_raw = model.vh_raw = None
    model.r_t, model.r_infty = None, float("nan")
    assert model.r_infty_text == "N/A"


# 9. no drop hook: the workspace hands files over; a folder or files join the batch queue
def test_handed_over_files_are_loaded_or_queued(app, files, tmp_path):
    from chisurf.plugins.vv_vh_anisotropy.gui.app import receive_batch, receive_file

    a, b = files
    for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
        assert not callable(getattr(app, name, None)), name
    receive_file(app, {"file": [str(a)]})
    assert app.model.loaded_file == str(a) and app.model.batch_files == []
    receive_file(app, {"file": []})
    assert app.model.loaded_file == str(a)
    receive_file(app, {"file": [str(tmp_path / "missing.dat")]})
    assert app.model.loaded_file == str(a)
    folder = tmp_path / "set"
    (folder / "sub").mkdir(parents=True)
    make(folder / "c.dat", seed=3)
    make(folder / "sub" / "d.txt", seed=4)
    (folder / "notes.md").write_text("x")
    receive_batch(app, {"files": [str(folder)]})
    assert sorted(Path(p).name for p in app.model.batch_files) == ["c.dat", "d.txt"]
    receive_batch(app, {"files": [str(folder / "notes.md")]})
    assert app.model.message.startswith("Nothing to queue")
    receive_batch(app, {"files": [str(folder / "c.dat")]})
    assert app.model.message.startswith("Nothing to queue")  # already queued


# 10. the batch window: queue, select, remove, clear, run, save, every error path
def test_batch_queue_remove_clear_run_and_save(app, files, tmp_path):
    a, b = files
    model = app.model
    assert not any(
        model.enabled(x)
        for x in ("run_batch", "clear_batch", "remove_selected", "request_save_batch")
    )
    model.run_batch()
    assert model.message == "No files to process." and model.batch_results == []
    with pytest.raises(ValueError, match="Run batch before saving CSV"):
        model.save_batch(tmp_path / "x.csv")
    app.model.open_batch()
    assert model.add_batch_paths([str(a), str(b), str(a)]) == 2  # the duplicate is not queued twice
    model.select_batch_file({"path": str(a)})
    assert model.enabled("remove_selected")
    model.remove_selected()
    assert model.batch_files == [str(b)] and not model.enabled("remove_selected")
    model.add_batch_paths([str(a)])
    rows = model.run_batch()
    assert [r[0] for r in rows] == ["b.dat", "a.dat"] and model.message == "Processed 2 file(s)."
    model.select_batch_file({"path": str(b)})
    model.remove_selected()
    model.select_batch_file({"path": str(a)})
    model.remove_selected()  # the queue is empty: results go too
    assert model.batch_results == [] and model.batch_files == []
    model.add_batch_paths([str(a), str(b)])
    model.run_batch()
    out = tmp_path / "batch.csv"
    model.save_batch(out)
    lines = out.read_text().splitlines()
    assert (
        lines[0] == "filename,r_inf,region_min,region_max,bg_vv,bg_vh,g_factor,error"
        and len(lines) == 3
    )
    model.clear_batch()
    assert model.batch_files == [] and model.batch_results == [] and not model.enabled("run_batch")


def test_a_bad_file_in_the_batch_is_a_row_with_its_error(app, files, tmp_path):
    a, _ = files
    bad = tmp_path / "bad.dat"
    bad.write_text("not numbers\n")
    model = app.model
    model.add_batch_paths([str(a), str(bad), str(tmp_path / "gone.dat")])
    assert model.batch_files == [str(a), str(bad)]  # gone.dat is not a file: not queued
    model.batch_files.append(str(tmp_path / "gone.dat"))
    rows = model.run_batch()
    assert np.isfinite(rows[0][1]) and rows[0][-1] == ""
    assert np.isnan(rows[1][1]) and "two bins" in rows[1][-1]
    assert np.isnan(rows[2][1]) and rows[2][-1]
    assert model.message == "Processed 3 file(s), 2 failed."
    model.save_batch(tmp_path / "b.csv")
    assert "two bins" in (tmp_path / "b.csv").read_text()


def test_batch_files_come_from_the_workspace_and_save_csv_through_the_dialog(app, files, tmp_path):
    from chisurf.plugins.vv_vh_anisotropy.gui.app import receive_batch

    a, b = files
    model = app.model
    model.open_batch()
    receive_batch(app, {"files": [str(a), str(b)]})
    assert model.batch_files == [str(a), str(b)]
    model.run_batch()
    model.request_save_batch()
    _draw(app)
    app.dialog.draw = lambda: [str(tmp_path / "t.csv")]
    _draw(app, times=1)
    assert (tmp_path / "t.csv").exists() and model.message == "Saved t.csv"


# 11. persistence
def test_settings_round_trip(app, files, tmp_path):
    a, b = files
    m = app.model
    m.load(a)
    m.g_factor, m.bg_vv, m.shift, m.flip = 1.07, 5.0, 2.0, True
    m.region_bounds = [20.0, 60.0]
    m.batch_files = [str(b)]
    m.compute()
    saved = json.loads(json.dumps(app.export_settings()))
    other = create_app()
    try:
        other.restore_settings(saved)
        o = other.model
        assert (o.g_factor, o.bg_vv, o.shift, o.flip, o.region_bounds) == (
            1.07,
            5.0,
            2.0,
            True,
            [20.0, 60.0],
        )
        assert o.loaded_file == str(a) and o.batch_files == [str(b)]
        assert o.r_infty == pytest.approx(m.r_infty)
        other.restore_settings({"loaded_file": str(tmp_path / "gone.dat"), "g_factor": 2.0})
        assert o.g_factor == 2.0  # a missing file does not stop the rest
    finally:
        other.close()


# 12/13. draws, empty and populated, with the batch window and a dialog, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(app, files, size):
    a, b = files
    painter = _draw(app, size)
    assert "Pick a VV/VH file" in painter.strings or any(
        "Pick a VV/VH file" in s for s in painter.strings
    )
    app.model.load(a)
    app.model.add_batch_paths([str(a), str(b)])
    painter = _draw(app, size)
    assert "Save outputs…" in painter.strings and any("a.dat" in s for s in painter.strings)
    app.model.open_batch()
    rows = app.model.run_batch()
    painter = _draw(app, size)
    assert "Run Batch" in painter.strings and "r_inf" in painter.strings
    assert (
        f"{rows[0][1]:.5f}" in painter.strings and f"{rows[1][1]:.5f}" in painter.strings
    )  # the table cells, five decimals
    app.model.request_save_batch()
    _draw(app, size)
    assert app.dialog is not None
    _draw(app, size)


def test_labels_have_no_pictograms(app, files):
    import re

    app.model.load(files[0])
    app.model.open_batch()
    painter = _draw(app)
    from chisurf.plugins.emtk_layout import ACTIONS, action_caption

    shared = {action_caption(key) for key in ACTIONS}  # the shared vocabulary draws its own icons
    assert [
        s
        for s in painter.strings
        if s not in shared and re.search("[\U0001f000-\U0001ffff☀-➿⛔️]", s)
    ] == []


# 14. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("vv_vh_anisotropy")
    assert result["ok"], result["output"]


# 15. tooltips: the recorded controls and every spec section, button and table column
def test_every_control_has_a_tooltip(files):
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("vv_vh_anisotropy")
    app.model.load(files[0])
    app.model.open_batch()
    assert emtk_inventory(app)["controls_without_tooltip"] == []
    spec = json.loads((GUI / "vv_vh_emtk.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            assert s.get("description"), s.get("attr") or s.get("title") or s.get("key") or s
            for c in (s.get("options") or {}).get("columns", []):
                assert c.get("tooltip"), c
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


# 16. every attr, call and action of the spec is on the model
def test_the_spec_names_exist_on_the_model():
    model = AnisotropyModel()
    spec = json.loads((GUI / "vv_vh_emtk.view.json").read_text(encoding="utf-8"))
    missing = []

    def has(name):
        return hasattr(type(model), name) or hasattr(model, name)

    def walk(sections):
        for s in sections:
            for key in ("attr", "call", "source"):
                if s.get(key) and not has(s[key]):
                    missing.append((key, s[key]))
            opts = s.get("options") or {}
            for key in ("source", "selected_call", "delete_call"):
                if opts.get(key) and not has(opts[key]):
                    missing.append((key, opts[key]))
            for b in s.get("buttons", []):
                if not has(b["action"]):
                    missing.append(("action", b["action"]))
            walk(s.get("sections", []))

    walk(spec["sections"])
    assert missing == []


# 17. help, guide: the tour waits for the controls it names
def test_guide_waits_for_the_user_and_points_at_drawn_controls(app, files):
    tour = app.tour
    assert (
        tour.wait_for_controls and len(tour.steps) >= 3 and any(s.get("await") for s in tour.steps)
    )
    assert (GUI / "help.md").stat().st_size > 400
    app.model.load(files[0])
    _draw(app)
    for step in tour.steps:
        key = tour._target_key(step["target"])
        assert key in app.item_rects or key in app.form.rects, step["title"]
    tour.start(0)
    assert not tour.awaiting  # what a measurement file holds: read, not pressed
    tour.start(1)
    assert tour.awaiting and tour.steps[1]["target"] == {"name": "load_example"}
    tour.notify_used("request_save")  # another control: still waiting
    assert tour.awaiting
    app.form.on_used("load_example")  # what the form reports on a press of Load example
    assert not tour.awaiting
    tour.next()
    app.model.g_factor = 1.2
    app.form.on_used("g_factor")
    assert not tour.awaiting
    app.help_window.show()
    _draw(app)
    assert app.help_window.open
