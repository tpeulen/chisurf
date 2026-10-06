"""The native FCS curve merger at parity with the Qt WizardFcsMerger page.

Real repeats: BH_SPC132.spc cut into six 10 s chunks and cross-correlated with tttrlib
(``okf/plugins/emtk-ports/fcs_merger/scripts/make_chunks.py``). The Qt page runs in a
subprocess (this process stays Qt-free): it loads the folder, leaves chunk 3 out and
saves. The native app does the same through its controls -- a pointer press on the Use
check box, a double click on a row -- and must show the same rows, target and merge,
and write the same file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.fcs.fcs_merger.gui.app import MergerApp

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO / "okf" / "plugins" / "emtk-ports" / "fcs_merger" / "scripts"))
from make_chunks import build  # noqa: E402

SPEC = json.loads((HERE.parent / "gui" / "fcs_merger_emtk.view.json").read_text(encoding="utf-8"))

_QT = r"""
import json, pathlib, sys
from qtpy import QtCore, QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fcs.fcs_merger.wizard import ChisurfWizard
folder = pathlib.Path(sys.argv[1])
w = ChisurfWizard(); p = w.page(w.pageIds()[0])
p.lineEdit.setText(str(folder))
p.open_correlation_folder(folder)
p.tableWidget.item(2, 0).setCheckState(QtCore.Qt.Unchecked)
t = p.tableWidget
rows = [[t.item(r, c).text().strip() for c in range(1, 5)] for r in range(t.rowCount())]
tips = [t.item(r, 1).toolTip() for r in range(t.rowCount())]
m = p.mean_correlation
p.save_mean_correlation()
print("FACTS" + json.dumps({"rows": rows, "tips": tips, "target": p.lineEdit_2.text(),
      "mean": {k: (list(map(float, m[k])) if k in ("x", "y", "ey") else float(m[k])) for k in ("x", "y", "ey", "duration", "count_rate")},
      "saved": pathlib.Path(p.target_filepath).read_text()}))
"""


@pytest.fixture(scope="module")
def chunks(tmp_path_factory):
    pytest.importorskip("tttrlib")
    return build(tmp_path_factory.mktemp("qt") / "BH_SPC132")


@pytest.fixture(scope="module")
def qt(chunks):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, str(chunks)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt page's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


@pytest.fixture
def folder(tmp_path):
    """A fresh copy per test (saving writes beside the folder)."""
    pytest.importorskip("tttrlib")
    return build(tmp_path / "BH_SPC132")


def _draw(app, size=(1200, 800), n=2):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _wait(app, timeout=60.0):
    end = time.monotonic() + timeout
    while app.job.running and time.monotonic() < end:
        _draw(app, n=1)
        time.sleep(0.01)
    assert not app.job.running
    _draw(app, n=1)


def _press(app, x, y, clicks=1, size=(1200, 800)):
    app.pointer_move(x, y)
    app.press(x, y, clicks=clicks)
    _draw(app, size, n=1)
    app.release()
    _draw(app, size, n=1)


def _click(app, key, size=(1200, 800)):
    _draw(app, size)
    x, y, w, h = app.item_rects[key]
    _press(app, x + w / 2, y + h / 2, size=size)


def _cell(app, row, key):
    """Centre of a drawn table cell (from the control's last draw)."""
    control = app.form.tables["curve_rows"].control
    bx, by, bw, bh = control._body_box
    y = by + (row + 0.5) * control._row_h
    x = next(
        px
        for px in np.arange(bx + 1, bx + bw, 2.0)
        if (column := control.column_at(px)) is not None and column.key == key
    )
    while (column := control.column_at(x + 2)) is not None and column.key == key:
        x += 2  # walk to the column's middle
        if control.column_at(x + 12) is None or control.column_at(x + 12).key != key:
            break
    return x - 4, y


def _loaded(folder, **kwargs):
    app = MergerApp(**kwargs)
    app.files_dropped([str(folder)])
    _wait(app)
    return app


# 1. the Qt page's rows, target, merge and saved file, chunk 3 left out with the pointer
def test_rows_merge_and_file_match_the_qt_page(qt, folder, chunks):
    app = _loaded(folder)
    try:
        rows = [
            [r["file"], f"{r['cr_a']:.2f}", f"{r['cr_b']:.2f}", f"{r['duration']:.2f}"]
            for r in app.model.curve_rows()
        ]
        assert rows == qt["rows"]
        assert [Path(r["path"]).name for r in app.model.curve_rows()] == [
            Path(t).name for t in qt["tips"]
        ]
        assert Path(app.model.output).name == Path(qt["target"]).name == "BH_SPC132.cor"
        assert (
            Path(app.model.output).parent == folder.parent
            and Path(qt["target"]).parent == chunks.parent
        )
        _draw(app)
        x, y = _cell(app, 2, "use")
        _press(app, x, y)  # the Use check box of chunk 3
        assert app.model.use == [True, True, False, True, True, True]
        assert app.model.curve_rows()[2]["muted"]
        mean = app.model.mean_correlation
        for key in ("x", "y", "ey"):
            np.testing.assert_allclose(mean[key], qt["mean"][key], rtol=1e-12)
        assert (
            mean["count_rate"] == pytest.approx(qt["mean"]["count_rate"])
            and mean["count_rate"] > 1.0
        )
        assert mean["duration"] == qt["mean"]["duration"] == 50.0
        _click(app, "request_save")
        _wait(app)
        assert Path(app.model.output).read_text() == qt["saved"]
        assert "Saved the merge of 5 curves" in app.model.status
    finally:
        app.close()


# 2. the table: a double click toggles, Delete removes, the highlighted curve is thicker
def test_double_click_toggles_and_delete_removes(folder):
    app = _loaded(folder)
    try:
        _draw(app)
        x, y = _cell(app, 1, "file")
        _press(app, x, y)
        assert app.model.selected == 1
        _press(app, x, y, clicks=2)
        assert app.model.use[1] is False
        from emtk.keys import KEY_DELETE

        app.key(KEY_DELETE, "")
        _draw(app)
        assert len(app.model.correlations) == 5 and len(app.model.curve_rows()) == 5
        assert app.model.use == [True] * 5
    finally:
        app.close()


def test_curves_carry_the_qt_pens(folder, monkeypatch):
    from chisurf.plugins.fcs.fcs_merger.gui import app as app_module

    app = _loaded(folder)
    try:
        app.use = [i != 2 for i in range(6)]
        app.selected = 1
        styles = []
        monkeypatch.setattr(
            app_module.implot,
            "set_next_line_style",
            lambda colour=None, weight=None, dash=None: styles.append((colour, weight, dash)),
        )
        _draw(app, n=1)
        assert [w for _, w, _ in styles] == [1.0, 3.0, 1.0, 1.0, 1.0, 1.0]  # the highlighted one
        assert (
            styles[2][0] == app_module.UNUSED and styles[2][2] is not None
        )  # unused: grey, dashed
        assert styles[0][0] == app.palette[0] and styles[0][2] is None
    finally:
        app.close()


# 3. no curve ticked: the merge of all, as the Qt page; errors are shown
def test_none_ticked_merges_all_and_errors_show(folder, tmp_path):
    app = _loaded(folder)
    try:
        app.use = [False] * 6
        assert app.model.n_used() == 6
        assert any("averages all of them" in s for s in _draw(app).strings)
        app.load_folder(tmp_path / "empty")
        _wait(app)
        assert (
            "Could not read" in app.model.error and len(app.model.correlations) == 6
        )  # the list stays
        assert any("Could not read" in s for s in _draw(app).strings)
        app.model.output = ""
        assert not app.save() and "target" in app.model.error
    finally:
        app.close()


def test_buttons_follow_the_state(folder):
    app = MergerApp()
    try:
        _click(app, "request_save")
        assert not app.job.running  # nothing loaded: disabled
        assert not app.form_model.enabled("request_save") and not app.form_model.enabled(
            "request_clear"
        )
        _draw(app)
        assert not app.animating()  # at rest: no frames
        app.files_dropped([str(folder)])
        assert app.job.running and not app.form_model.enabled("request_open")
        assert app.form_model.busy and app.animating()
        _wait(app)
        assert not app.animating() and app.form_model.enabled("request_add")
        _click(app, "request_clear")
        assert app.model.correlations == [] and app.model.folder == ""
        app.files_dropped([str(folder / "chnk-0003.cor")])  # a dropped chunk reads its folder
        _wait(app)
        assert len(app.model.correlations) == 6 and app.model.folder == str(folder)
    finally:
        app.close()


# 4. dialogs, typed folder, Add to ChiSurf
def test_open_save_as_and_add(folder, tmp_path):
    added = []
    app = MergerApp(add_dataset=added.append)
    try:
        _click(app, "request_open")
        assert app.dialog is not None and app.dialog_mode == "folder"
        app.path_chosen(str(folder))
        _wait(app)
        assert len(app.model.correlations) == 6
        _click(app, "request_save_as")
        assert app.dialog_mode == "save"
        app.path_chosen(str(tmp_path / "elsewhere.cor"))
        _wait(app)
        assert (tmp_path / "elsewhere.cor").exists() and app.model.output == str(
            tmp_path / "elsewhere.cor"
        )
        _click(app, "request_add")
        _wait(app)
        assert added == [str(tmp_path / "elsewhere.cor")] or added == [tmp_path / "elsewhere.cor"]
        other = MergerApp()
        other.form_model.folder = str(folder)
        other.form_model.folder_entered(str(folder))  # what Enter in the folder field does
        _wait(other)
        assert len(other.model.correlations) == 6
        other.close()
    finally:
        app.close()


# 5. guide: every target drawn; the folder step waits for a folder, the save step for the button
def test_the_guide_points_at_real_controls_and_waits(folder):
    app = MergerApp()
    try:
        _draw(app)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys == {"lineEdit", "tableWidget", "toolButton_3"}
        assert all(app.tour.get_target_rect(k) is not None for k in keys)
        first = next(i for i, s in enumerate(steps) if s.get("await"))
        app.tour.start(first)
        assert app.tour.awaiting
        app.form.used("folder")  # a typed path is not a loaded folder
        assert app.tour.awaiting
        app.files_dropped([str(folder)])
        _wait(app)
        assert not app.tour.awaiting
        last = max(i for i, s in enumerate(steps) if s.get("await"))
        app.tour.start(last)
        _click(app, "request_save")
        assert not app.tour.awaiting
        _wait(app)
    finally:
        app.tour.active = False
        app.close()


def test_help_opens():
    app = MergerApp()
    try:
        _click(app, "request_help")
        assert app.help.open
    finally:
        app.close()


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_inside_the_window(folder, size):
    app = _loaded(folder)
    try:
        strings = _draw(app, size).strings
        for text in (
            "📂 Open folder…",
            "💾 Save",
            "Use",
            "File",
            "CR A",
            "Duration",
            "chnk-0000",
            "FCS",
            "FCS Merged",
        ):
            assert text in strings, text
        x0, y0, w0, h0 = app.item_rects["files"]
        for name in (
            "request_open",
            "request_help",
            "folder",
            "curve_rows",
            "output",
            "request_save",
            "request_add",
        ):
            x, y, w, h = app.item_rects[name]
            assert x >= x0 - 0.5 and x + w <= x0 + w0 + 0.5 and y + h <= y0 + h0 + 0.5, name
    finally:
        app.close()


# 6. no Qt, tooltips (inventory, spec sections, buttons and columns)
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fcs_merger")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("fcs_merger")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(section.get("sections") or [])

    sections = list(walk(SPEC["sections"]))
    assert all(s.get("description") for s in sections)
    assert all(b.get("description") for s in sections for b in s.get("buttons") or [])
    table = next(s for s in sections if s.get("key") == "data_table")
    assert all(c.get("tooltip") for c in table["options"]["columns"])
