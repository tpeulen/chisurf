"""The native Trace Browser, card T5: the host adapter that fulfils the HMM, TW and NDX hand-offs.

``gui/host.py`` (Qt allowed: it only hosts) opens the windows the Qt Trace Browser opened:
``IntensityTrace`` for HMM, the Time Window tool for TW and ChiSurf's ndX window for NDX. The app finds it
through ``make_app()`` only when a Qt application already runs. Everything uses temporary COPIES of
``test/data/tttr/BH/132/BH_SPC132.spc`` (6233 bins of 10 ms for the ALEX setup, see the T3b/T4 tests) and an
offscreen ``QApplication`` (the ``qapp`` fixture). The ndX window and the Time Window tool are real windows here
(they construct headless); ndX settings go to a temporary folder.
"""

import gc
import json
import os
import pathlib
import shutil
import subprocess
import sys
import weakref

import pytest

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t2 import (
    BH132,
    frames,
    pressing,
)
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t3b import settle_all
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t4 import (
    button_states,
    open_folder,
    select,
)

REPO = next(p for p in pathlib.Path(__file__).parents if (p / "pyproject.toml").exists())


# ---- helpers ---------------------------------------------------------------------------------
@pytest.fixture
def work(tmp_path, monkeypatch):
    """``work/data`` with two copies of the real measurement; ndX keeps its settings in the temp folder."""
    if not BH132.exists():
        pytest.skip("sample TTTR data missing")
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndx_settings"))
    data = tmp_path / "work" / "data"
    data.mkdir(parents=True)
    shutil.copy(BH132, data / "m000.spc")
    shutil.copy(BH132, data / "m001.spc")
    return data


@pytest.fixture
def host(qapp):
    """The host module with its window list emptied before and after the test."""
    from chisurf.plugins.tttr.trace_browser.gui import host as module

    def close_all():
        for window in list(module.WINDOWS):
            window.close()
        qapp.processEvents()
        module.WINDOWS.clear()

    close_all()
    yield module
    close_all()


def make_hosted_app(qapp):
    """``make_app()`` with no argument, as the plugin registry calls it, on the Browser page with the ALEX setup."""
    from chisurf.plugins.tttr.trace_browser.gui.app import make_app

    app = make_app()
    app.model.accept_setup(json.loads(json.dumps(ALEX)))
    app.model.precompute_after_scan = False
    return app


def payload(path, window_ms=10.0):
    return {
        "file": str(path),
        "window_ms": window_ms,
        "setup_settings": json.loads(json.dumps(ALEX)),
        "selected_channels": [0, 1],
    }


def close(window, qapp, host):
    window.close()
    deadline = 50
    while window in host.WINDOWS and deadline:
        qapp.processEvents()
        deadline -= 1
    assert window not in host.WINDOWS


# ---- the three windows ---------------------------------------------------------------------------
def test_hmm_opens_an_intensity_trace_window_set_up_as_the_qt_tool_does(qapp, host, work):
    from chisurf.plugins.tttr.intensity_trace import IntensityTrace

    window = host.default_request_handler()("open_intensity_trace", payload(work / "m001.spc", 10.0))
    assert type(window) is IntensityTrace
    assert window.windowTitle() == "Intensity Trace Analysis - m001.spc"
    assert window.file_path_edit.text() == str(work / "m001.spc")
    assert window.window_spin.value() == 10.0
    assert window._detector_settings == ALEX
    assert sorted(window.detector_checkboxes) == ["green", "red", "yellow"]
    # the file was loaded and processed: 10 ms bins of the 62.3 s measurement, the two routing channels
    data = window.current_data
    assert data["window_ms"] == 10.0 and data["padded"].shape[0] > 6000
    assert data["padded"].shape[1] == len(data["channels"]) > 0
    assert window.isVisible() and window in host.WINDOWS


def test_hmm_follows_the_bin_window_of_the_browser(qapp, host, work):
    window = host.default_request_handler()("open_intensity_trace", payload(work / "m000.spc", 1.0))
    assert window.window_spin.value() == 1.0
    assert window.current_data["window_ms"] == 1.0 and window.current_data["padded"].shape[0] > 60000


def test_tw_opens_the_time_window_tool_holding_the_file_and_the_bin_window(qapp, host, work):
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    window = host.default_request_handler()(
        "open_time_window", {"files": [str(work / "m001.spc")], "window_ms": 5.0}
    )
    assert type(window) is TTTRTimeWindowTool
    assert window.windowTitle() == "Time Window BID Generation: m001.spc"
    assert [str(p) for p in window._file_paths] == [str(work / "m001.spc")]
    assert window.time_window_ms == 5.0
    assert window.isVisible() and window in host.WINDOWS


def test_ndx_opens_the_ndx_window_on_the_folder_the_model_wrote(qapp, host, work):
    from chisurf.plugins.ndxplorer.window import NdxWindow
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.accept_setup(json.loads(json.dumps(ALEX)))
    folder = model.prepare_ndx(work / "m000.spc")
    assert folder == work / "m000_TW_10ms" and (folder / "bi4_bur" / "m000.bur").exists()
    request = model.requests[-1]
    assert request["name"] == "open_ndxplorer"
    window = host.default_request_handler()(request["name"], request["payload"])
    assert type(window) is NdxWindow
    assert window.windowTitle()
    assert window.isVisible() and window in host.WINDOWS
    assert window.app is not None and window.host is not None            # the emtk app, hosted


def test_ndx_is_built_on_exactly_the_prepared_folder(qapp, host, work, monkeypatch):
    """The heavy part (the ndX app) is stubbed: only the folder it receives is asserted."""
    from qtpy import QtWidgets

    received = []

    class Stub(QtWidgets.QWidget):
        pass

    import chisurf.plugins.ndxplorer.window as ndx_window

    monkeypatch.setattr(ndx_window, "build_ndxplorer_window", lambda folder, **kw: received.append(folder) or Stub())
    folder = work / "m000_TW_10ms"
    folder.mkdir()
    window = host.default_request_handler()("open_ndxplorer", {"folder": str(folder), "file": "x", "window_ms": 10.0})
    assert received == [folder] and type(window) is Stub and window in host.WINDOWS


# ---- windows are kept alive and forgotten on close ---------------------------------------------------
def test_the_windows_are_kept_alive_and_closing_them_drops_the_reference(qapp, host, work):
    handle = host.default_request_handler()
    window = handle("open_time_window", {"files": [str(work / "m000.spc")], "window_ms": 10.0})
    reference = weakref.ref(window)
    del window
    gc.collect()
    qapp.processEvents()
    assert reference() is not None and reference() in host.WINDOWS      # only the module list holds it
    kept = reference()
    close(kept, qapp, host)
    del kept
    gc.collect()
    assert reference() is None or reference() not in host.WINDOWS


def test_every_request_adds_its_own_window(qapp, host, work):
    handle = host.default_request_handler()
    first = handle("open_time_window", {"files": [str(work / "m000.spc")], "window_ms": 10.0})
    second = handle("open_time_window", {"files": [str(work / "m001.spc")], "window_ms": 20.0})
    assert first is not second and host.WINDOWS == [first, second]
    assert second.time_window_ms == 20.0 and first.time_window_ms == 10.0


# ---- failures raise: the app shows them ------------------------------------------------------------------
def test_requests_that_cannot_be_fulfilled_raise(qapp, host, work):
    handle = host.default_request_handler()
    with pytest.raises(ValueError, match="unknown request"):
        handle("open_something_else", {})
    with pytest.raises(FileNotFoundError, match="gone.spc"):
        handle("open_intensity_trace", payload(work / "gone.spc"))
    with pytest.raises(FileNotFoundError, match="gone.spc"):
        handle("open_time_window", {"files": [str(work / "gone.spc")], "window_ms": 10.0})
    with pytest.raises(FileNotFoundError):
        handle("open_ndxplorer", {"folder": str(work / "nothing_TW_10ms")})
    (work / "notes.txt").write_text("not a measurement")
    with pytest.raises(ValueError, match="not a TTTR file"):
        handle("open_time_window", {"files": [str(work / "notes.txt")], "window_ms": 10.0})
    assert host.WINDOWS == []


def test_a_failing_hand_off_shows_an_error_status_and_the_app_keeps_drawing(qapp, host, work):
    app = make_hosted_app(qapp)
    try:
        open_folder(app, work)
        app.model.set_selection([str(work / "m000.spc")])
        (work / "m000.spc").unlink()                                   # the file vanishes after it was listed
        app.model.open_intensity_trace()
        frames(app, n=3)
        assert "could not open open_intensity_trace" in app.model.error_text
        assert "m000.spc does not exist" in app.model.error_text
        assert host.WINDOWS == []
        frames(app, n=2)
    finally:
        app.close()


# ---- the wiring: make_app() finds the adapter only with a Qt application --------------------------------------
def test_make_app_with_a_qt_application_wires_the_default_handler_and_enables_the_buttons(qapp, host, work):
    app = make_hosted_app(qapp)
    try:
        assert app.on_request is not None and app.model.host_connected is True
        open_folder(app, work)
        select(app, "m001.spc")
        states = button_states(app)
        assert states["HMM"] is False and states["TW"] is False and states["NDX"] is False   # all enabled
    finally:
        app.close()


def test_pressing_hmm_and_tw_in_the_app_opens_the_windows(qapp, host, work, monkeypatch):
    from chisurf.plugins.tttr.intensity_trace import IntensityTrace
    from chisurf.plugins.tttr.tttr_time_windows.gui.tool import TTTRTimeWindowTool

    app = make_hosted_app(qapp)
    try:
        open_folder(app, work)
        select(app, "m001.spc")
        app.model.window_ms = 10.0
        for label in ("HMM", "TW"):
            with pressing(monkeypatch, label):
                frames(app, n=1)
            frames(app, n=2)
        kinds = [type(w) for w in host.WINDOWS]
        assert kinds == [IntensityTrace, TTTRTimeWindowTool]
        assert host.WINDOWS[0].file_path_edit.text() == str(work / "m001.spc")
        assert [str(p) for p in host.WINDOWS[1]._file_paths] == [str(work / "m001.spc")]
        assert app.model.error_text == ""
        assert app.model.status_text.startswith("Sent m001.spc")
    finally:
        app.close()


def test_pressing_ndx_in_the_app_writes_the_burst_table_and_opens_the_ndx_window(qapp, host, work, monkeypatch):
    from chisurf.plugins.ndxplorer.window import NdxWindow

    app = make_hosted_app(qapp)
    try:
        open_folder(app, work)
        select(app, "m000.spc")
        with pressing(monkeypatch, "NDX"):
            frames(app, n=1)
        settle_all(app)
        frames(app, n=3)
        assert (work / "m000_TW_10ms" / "bi4_bur" / "m000.bur").exists()
        assert [type(w) for w in host.WINDOWS] == [NdxWindow]
        assert app.model.error_text == ""
    finally:
        app.close()


def test_an_explicit_on_request_wins_over_the_default_handler(qapp, host, work, monkeypatch):
    from chisurf.plugins.tttr.trace_browser.gui.app import make_app

    received = []
    app = make_app(on_request=lambda name, payload: received.append(name))
    try:
        assert app.on_request is not None and app.on_request.__name__ == "<lambda>"
        app.model.accept_setup(json.loads(json.dumps(ALEX)))
        app.model.precompute_after_scan = False
        open_folder(app, work)
        select(app, "m000.spc")
        with pressing(monkeypatch, "TW"):
            frames(app, n=1)
        frames(app, n=2)
        assert received == ["open_time_window"] and host.WINDOWS == []
    finally:
        app.close()


def test_without_a_qt_application_the_buttons_stay_greyed(qapp, work, monkeypatch):
    """Qt is loaded (the test runs under it) but no QApplication exists: the app is not hosted."""
    from qtpy import QtWidgets

    from chisurf.plugins.tttr.trace_browser.gui import app as app_module

    monkeypatch.setattr(QtWidgets.QApplication, "instance", staticmethod(lambda: None))
    app = app_module.make_app()
    try:
        assert app.on_request is None and app.model.host_connected is False
        app.model.accept_setup(json.loads(json.dumps(ALEX)))
        open_folder(app, work)
        select(app, "m000.spc")
        states = button_states(app)
        assert states["HMM"] is True and states["TW"] is True and states["NDX"] is True
        assert all(app.model.enabled(a) is False for a in ("open_intensity_trace", "open_time_window", "open_ndxplorer"))
    finally:
        app.close()


def test_make_app_stays_qt_free_when_qt_is_blocked_and_without_an_application():
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.tttr.trace_browser.gui.app import make_app
app = make_app()
assert app.on_request is None and app.model.host_connected is False
bad = sorted(m for m in sys.modules if m.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'})
assert not bad, bad
assert 'chisurf.plugins.tttr.trace_browser.gui.host' not in sys.modules
assert not any(m == 'chisurf.gui' or m.startswith('chisurf.gui.') for m in sys.modules)
print('OK')
"""
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)),
        capture_output=True, text=True,
    )
    assert done.returncode == 0 and "OK" in done.stdout, done.stdout + done.stderr


def test_loaded_qt_without_an_application_is_not_hosted_either():
    script = """
import sys
from qtpy import QtWidgets
assert QtWidgets.QApplication.instance() is None
from chisurf.plugins.tttr.trace_browser.gui.app import make_app
app = make_app()
assert app.on_request is None and app.model.host_connected is False
assert 'chisurf.plugins.tttr.trace_browser.gui.host' not in sys.modules
print('OK')
"""
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO,
        env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), QT_QPA_PLATFORM="offscreen"),
        capture_output=True, text=True,
    )
    assert done.returncode == 0 and "OK" in done.stdout, done.stdout + done.stderr


def test_the_qt_free_proof_of_the_port_still_passes():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("trace_browser")
    assert result["ok"], result["output"]


def test_the_host_module_is_imported_lazily_and_the_sources_name_no_qt():
    gui = pathlib.Path(__file__).parents[1] / "gui"
    for name in ("app.py", "model.py"):
        source = (gui / name).read_text()
        for needle in ("qtpy", "PyQt", "PySide", "chisurf.gui"):
            assert needle not in source, (name, needle)
    for name in ("app.py", "model.py", "host_lookup.py"):
        for line in (gui / name).read_text().splitlines():
            if line.startswith(("import ", "from ")):
                assert not line.startswith("from .host import") and "gui.host " not in line, (name, line)
    assert "from .host import" in (gui / "host_lookup.py").read_text()      # inside the function only
    assert "qtpy" in (gui / "host.py").read_text()                         # the adapter is where Qt may live
