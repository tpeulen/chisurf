"""The native micro-time shifter at parity with the Qt MicrotimeShifterTool.

The Qt tool runs in a subprocess (this process stays Qt-free) on a demo file whose two
detectors are offset by a known 400 bins: its auto-align shifts, preview and saved file
are compared with the emtk app's, and both against references computed here from the
photons themselves (the rising edge from a numpy histogram, the saved micro-times as
``(input + shift) % N`` per photon).
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

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
# Before the plugin import, which puts modules/ndxplorer (and its own `test` package) on sys.path.
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402

from emtk.testing import PixelPainter, RecordingPainter  # noqa: E402

from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app  # noqa: E402
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import N_MT, RISE, TARGET, build  # noqa: E402
# isort: on

SPEC = json.loads((HERE.parent / "gui" / "shifter.view.json").read_text())


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build(tmp_path_factory.mktemp("mts") / "demo")


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=60.0, size=(1200, 800), painter=RecordingPainter):
    end = time.monotonic() + timeout
    _draw(app, size, n=1, painter=painter)
    while app.job.running:
        assert time.monotonic() < end, "the job did not finish"
        time.sleep(0.02)
        _draw(app, size, n=1, painter=painter)
    _draw(app, size, n=1, painter=painter)


def _loaded(path):
    app = create_app()
    app.load_files([path])
    _settle(app)
    assert app.n_mt == N_MT
    return app


def _photons(path):
    import tttrlib

    data = tttrlib.TTTR(str(path))
    return (
        np.asarray(data.macro_times),
        np.asarray(data.micro_times, dtype=np.int64),
        np.asarray(data.routing_channels, dtype=np.int64),
    )


def _fields(sections):
    for section in sections:
        if section.get("attr"):
            yield section
        yield from _fields(section.get("sections", []))


_QT = r"""
import json, sys
from pathlib import Path
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.gui import dialogs
from chisurf.plugins.tttr.tttr_microtime_shifter.gui.tool import MicrotimeShifterTool
source, target = sys.argv[1:3]
told = []
dialogs.information = lambda parent, title, text, *a, **k: told.append([title, text])
dialogs.error = lambda parent, title, text, *a, **k: told.append([title, text])
w = MicrotimeShifterTool()
w._db = lambda: None                                   # no database: the file branch of Save
w._file_model.files = [source]
w._on_file_path(source)
level, pos = w._trigger_level, w._trigger_pos
w.auto_align()
preview = w._client.histogram(w._file_paths, global_shift=w._global_shift, channel_shifts=w._channel_shifts)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, ""))
w._open_save_dialog()
print("FACTS" + json.dumps({"shifts": {str(k): v for k, v in w._channel_shifts.items()}, "level": level, "pos": pos,
                            "preview": preview["histograms"], "told": told}))
"""


@pytest.fixture(scope="module")
def qt(demo, tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "qt_shifted.spc"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, str(demo), str(target)],
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
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS") :])
    facts["target"] = target
    return facts


# 1. the Qt tool's defaults, shifts and preview; the shifts put each rising edge on the target
def test_auto_align_gives_the_qt_shifts_and_lands_each_edge_on_the_target(qt, demo):
    _, micro, routing = _photons(demo)
    app = _loaded(demo)
    try:
        assert (
            (app.trigger_level, app.trigger_position) == (qt["level"], qt["pos"]) == (124, TARGET)
        )
        app.auto_align()
        assert {str(k): v for k, v in app.channel_shifts.items()} == qt["shifts"]
        for channel, rise in RISE.items():  # the edge, found here from the photons
            counts = np.bincount(micro[routing == channel], minlength=N_MT)
            peak = int(np.argmax(counts))
            edge = int(np.where(counts[: peak + 1] >= app.trigger_level)[0][0])
            assert abs(edge - rise) <= 3
            assert app.channel_shifts[channel] == (TARGET - edge) % N_MT
        for (
            channel,
            counts,
        ) in app.histograms().items():  # the emtk preview is the Qt (backend) preview
            assert counts.tolist() == qt["preview"][str(channel)]
            edge = int(np.where(counts[: int(np.argmax(counts)) + 1] >= app.trigger_level)[0][0])
            assert edge == TARGET
    finally:
        app.close()


def test_a_saved_file_holds_every_photon_shifted_as_the_qt_tool_writes_it(qt, demo, tmp_path):
    macro, micro, routing = _photons(demo)
    app = _loaded(demo)
    try:
        app.auto_align()
        app.save_dialog()
        assert app.dialog.mode == "save" and app.dialog.filename == "offset_shifted.spc"
        target = tmp_path / "emtk_shifted.spc"
        app.dialog.draw = lambda: [str(target)]
        _settle(app)
        assert app.message == "Saved 1/1 shifted file(s)."
        ours, theirs = _photons(target), _photons(qt["target"])
        shift = np.vectorize(app.channel_shifts.get)(routing)
        expected = (micro + shift) % N_MT
        assert np.array_equal(ours[1], expected) and np.array_equal(ours[0], macro)
        assert np.array_equal(ours[2], routing)
        for a, b in zip(ours, theirs):
            assert np.array_equal(a, b)
        assert qt["told"] and qt["told"][-1][0] == "Saved"
    finally:
        app.close()


# 2. actions and errors
def test_actions_say_what_is_missing(demo, tmp_path):
    app = create_app()
    try:
        assert (
            not app.enabled("save_dialog")
            and not app.enabled("auto_align")
            and not app.enabled("register")
        )
        assert app.apply() is False and app.message == "Load TTTR files first."
        app.add_paths([str(tmp_path / "notes.txt")])
        assert app.message == "Choose supported TTTR or PTO photon files."
        app.load_files([demo])
        _settle(app)
        assert app.save_batch() is False and app.message == "Choose an output folder first."
        assert app.register() is False and app.message == "Choose an MMFDB sample first."
        app.output_folder = str(tmp_path / "batch")
        app.save_batch()
        _settle(app)
        assert [p.name for p in (tmp_path / "batch").iterdir()] == ["offset_shifted.spc"]
        assert app.message == "Saved 1/1 shifted file(s)."
    finally:
        app.close()


def test_files_with_different_bin_counts_are_refused(demo, tmp_path):
    other = tmp_path / "coarse.spc"
    other.write_bytes(Path(demo).read_bytes())
    app = create_app()
    try:
        original = app._client.load_metadata  # the second file reports 256 bins
        app._client.load_metadata = lambda path: (
            {**original(path), "n_mt": 256} if Path(path) == other.resolve() else original(path)
        )
        app.load_files([demo, other])
        _settle(app)
        assert app.message == "Queued files must have the same positive number of micro-time bins."
        assert app.message in " ".join(_draw(app).strings)
    finally:
        app.close()


def test_frames_are_requested_while_loading(demo, monkeypatch):
    import threading

    app = create_app()
    gate = threading.Event()
    original = app._client.load_metadata
    app._client.load_metadata = lambda path: (gate.wait(10), original(path))[1]
    try:
        app.load_files([demo])
        _draw(app, n=1)
        assert app.job.running and app.animating()
        assert not app.enabled("save_dialog")
        gate.set()
        _settle(app)
        assert not app.animating() and app.n_mt == N_MT
    finally:
        gate.set()
        app.close()


def test_remove_takes_the_selected_file_off_the_queue(demo, tmp_path):
    second = tmp_path / "second.spc"
    second.write_bytes(Path(demo).read_bytes())
    app = create_app()
    try:
        app.load_files([demo, second], current=second)
        _settle(app)
        app.remove_selected()
        _settle(app)
        assert [p.name for p in app.files] == ["offset.spc"]
        assert Path(second).exists()  # off the queue, not off the disk
    finally:
        app.close()


def test_a_dropped_folder_queues_its_photon_files(demo):
    app = create_app()
    try:
        app.on_paths_dropped([str(Path(demo).parent)])
        _settle(app)
        assert [p.name for p in app.files] == ["offset.spc"]
    finally:
        app.close()


# 3. one spec: every field drawn, its description the tooltip; an edit re-aligns
def test_every_spec_field_is_drawn_with_its_description(demo, monkeypatch):
    from emtk import im, im_widgets

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    app = _loaded(demo)
    try:
        for panel in SPEC["sections"]:
            app.form.folds[panel["title"]] = True
        _draw(app)
        fields = list(_fields(SPEC["sections"]))
        assert {f["attr"] for f in fields} <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        buttons = [
            b for s in SPEC["sections"] for sub in s["sections"] for b in sub.get("buttons", [])
        ]
        assert all(b["description"] in tips for b in buttons)
    finally:
        app.close()


def test_editing_the_target_bin_realigns(demo):
    from emtk.view_form import _commit

    app = _loaded(demo)
    try:
        field = next(f for f in _fields(SPEC["sections"]) if f["attr"] == "trigger_position")
        _commit(app, field, 1000, app.form)
        for channel, counts in app.histograms().items():
            assert (
                int(np.where(counts[: int(np.argmax(counts)) + 1] >= app.trigger_level)[0][0])
                == 1000
            )
        assert app.bounds("trigger_position") == (0, N_MT - 1)
    finally:
        app.close()


def test_the_channel_rows_reset(demo):
    app = _loaded(demo)
    try:
        app.auto_align()
        _draw(app)
        assert {"reset_0", "reset_8", "channel_shifts"} <= set(app.item_rects)
        app.reset_shift(8)
        assert app.channel_shifts[8] == 0 and app.channel_shifts[0] == 3904
    finally:
        app.close()


# guide: targets drawn, folded panels unfold, the action steps wait for presses
def test_the_guide_points_at_real_controls_and_waits(demo):
    app = _loaded(demo)
    size = (1200, 800)
    try:
        _draw(app, size, painter=PixelPainter)
        steps = app.tour.steps
        for index, step in enumerate(steps):
            key = app.tour._target_key(step.get("target"))
            if not key:
                continue
            app.tour.start(index)
            _draw(app, size, n=1)
            assert key in app.item_rects or key in app.form.rects, key

        def press(key):
            x, y, w, h = app.item_rects.get(key) or app.form.rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        for key in ("add_files", "auto_align", "save_dialog"):
            index = next(
                i for i, s in enumerate(steps) if app.tour._target_key(s.get("target")) == key
            )
            app.tour.start(index)
            assert app.tour.awaiting
            assert steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)
            _draw(app, size, n=1, painter=PixelPainter)
            press(key)
            assert not app.tour.awaiting, key
            app.dialog = None
        assert app.channel_shifts == {0: 3904, 8: 3504}  # the Auto align press aligned
    finally:
        app.tour.active = False
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(demo, size, monkeypatch):
    from emtk import im

    app = create_app()
    try:
        strings = _draw(app, size).strings
        assert {"📖  Guide", "❓  Help", "➕  Files…", "Alignment", "Shifts", "Save"} <= set(
            strings
        )
        assert "No file loaded." in strings
        app.load_files([demo])
        _settle(app, size=size)
        app.auto_align()
        clipped = []
        original = im.button

        def button(label, size_arg=(0.0, 0.0), *a, **k):
            pressed = original(label, size_arg, *a, **k)
            x, y, w, h = im.get_item_rect()
            if x + w > size[0] + 0.5:
                clipped.append(label)
            return pressed

        monkeypatch.setattr(im, "button", button)
        strings = " ".join(_draw(app, size).strings)
        assert "Channel 0" in strings and "Channel 8" in strings and "Routing 8" in strings
        assert not clipped, clipped  # every button inside the window
        fx, fy, fw, fh = app.item_rects["files"]  # and the file buttons inside their dock
        for key in ("add_files", "add_folder", "add_database", "remove", "clear"):
            x, y, w, h = app.item_rects[key]
            assert x + w <= fx + fw + 16.5, key
    finally:
        app.close()


def test_settings_round_trip(demo):
    app = _loaded(demo)
    app.auto_align()
    app.output_folder = "/tmp/out"
    state = json.loads(json.dumps(app.export_settings()))
    app.close()
    other = create_app()
    try:
        other.restore_settings(state)
        _settle(other)
        assert other.channel_shifts == {0: 3904, 8: 3504} and other.output_folder == "/tmp/out"
        assert [str(p) for p in other.files] == state["files"]
    finally:
        other.close()


def test_help_opens_with_its_page():
    app = create_app()
    try:
        app.help.show()
        assert app.help.open and "rising edge" in " ".join(_draw(app).strings)
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("microtime_shifter")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("microtime_shifter")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
