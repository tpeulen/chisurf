"""The native Trace Browser, card T5: its HMM, TW and NDX hand-offs, fulfilled by the emtk shell.

A press on *HMM*, *TW* or *NDX* records a request; ``gui/handoffs.py`` turns it into a plugin
hand-off (:mod:`chisurf.core.plugin.handoff`) to the tool that declares the payload in its
manifest's ``accepts``: Intensity Trace (``tttr_trace``), TTTR Time Window (``tttr_files``) and ndX
(``open_path``). The shell (``python -m chisurf``) opens that tool as a dock and hands it the
payload once it is built. The Qt adapter that did this for the ``--qt`` window (``gui/host.py``)
is retired; its tests are ported here to the real shell, driven with :class:`emtk.testing.Driver`
-- real clicks on the browser's buttons inside its dock.

Everything uses temporary COPIES of ``test/data/tttr/BH/132/BH_SPC132.spc`` (6233 bins of 10 ms
for the ALEX setup, see the T3b/T4 tests). One shell serves the module (it is slow to build); each
test closes the tools it opened. Screenshots of the three hand-offs go to
``$CHISURF_NATIVE_SCREENSHOTS/trace_browser_handoff`` (default: the test's temporary folder).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest
from emtk.testing import Driver

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t2 import (
    BH132,
    frames,
    pressing,
    table,
)

REPO = next(p for p in pathlib.Path(__file__).parents if (p / "pyproject.toml").exists())
SIZE = (1600, 1000)
HANDOFFS = ("open_intensity_trace", "open_time_window", "open_ndxplorer")


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


@pytest.fixture(scope="module")
def module_shell(tmp_path_factory):
    """The real shell, every shipped plugin in its menus, no session; settings in a scratch folder."""
    patch = pytest.MonkeyPatch()
    patch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path_factory.mktemp("shell_settings")))
    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp()
    driver = Driver(shell, SIZE)
    driver.frame(2)
    yield shell, driver
    shell.close()
    patch.undo()


@pytest.fixture
def shell(module_shell):
    """The module's shell, with every tool a test opened closed afterwards."""
    shell, driver = module_shell
    yield shell, driver
    for plugin_id in list(shell.hosted):
        shell.close_plugin(plugin_id)
    driver.frame(1)


def until(driver, condition, timeout=120.0):
    """Draw frames until *condition()* holds."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)
        driver.frame(1)
    driver.frame(2)


def unwrap(app):
    """The plugin's own app behind the shell's child wrapper."""
    return getattr(app, "_control", app)


def idle(browser):
    return not (
        browser.job.busy or browser._queue or browser.load_job.busy or browser.pre_job.busy
    )


def open_browser(shell, driver, folder):
    """Open the Trace Browser in the shell, accept the ALEX setup and open *folder*."""
    hosted = shell.open_plugin("trace_browser")
    until(driver, lambda: hosted.app is not None and hosted.build is None)
    browser = unwrap(hosted.app)
    browser.model.accept_setup(json.loads(json.dumps(ALEX)))
    browser.model.precompute_after_scan = False
    browser.model.request("open_folder", folder)
    until(driver, lambda: idle(browser) and browser.model.rows)
    return hosted, browser


def select(browser, driver, name):
    """Select row *name* the way a click on it does (the table's own selection path)."""
    control = table(browser)
    path = str(browser.model.current_folder / name)
    position = next(
        i for i, index in enumerate(control.order()) if control.key_of(index) == path
    )
    control._select_position(position)
    driver.frame(3)


def click(shell, driver, hosted, browser, key):
    """Bring the browser's dock to the front and click its button *key* (a real pointer press)."""
    shell.docks.focus(hosted.key)
    driver.frame(3)
    x0, y0 = hosted.box[:2]
    x, y, w, h = browser.form.rects[key]
    driver.click((x0 + x, y0 + y, w, h))
    driver.frame(2)


def delivered(shell, plugin_id):
    """The hosted tool once its app has taken a hand-off (or failed to), else ``None``."""
    hosted = shell.hosted.get(plugin_id)
    if hosted is None or hosted.build is not None:
        return None
    if hosted.extra.get("handoffs") or hosted.extra.get("handoff_error"):
        return hosted
    return None


def shots(tmp_path):
    root = os.environ.get("CHISURF_NATIVE_SCREENSHOTS")
    folder = (pathlib.Path(root) if root else tmp_path) / "trace_browser_handoff"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---- the three hand-offs, end to end in the shell -------------------------------------------------
def test_hmm_tw_and_ndx_open_their_docks_with_the_payload_applied(shell, work, tmp_path):
    from chisurf.emtk.main_app import TOOL_REGION
    from chisurf.plugins.tttr.intensity_trace.gui.app import IntensityTraceApp
    from chisurf.plugins.tttr.trace_browser.gui import handoffs

    shell, driver = shell
    out = shots(tmp_path)
    hosted, browser = open_browser(shell, driver, work)
    assert browser.on_request is handoffs.handle and browser.model.host_connected is True
    select(browser, driver, "m001.spc")
    assert all(browser.model.enabled(name) for name in HANDOFFS)
    driver.screenshot(out / "0_browser.png")

    # HMM: Intensity Trace reads and bins the file with the browser's bin window and setup
    click(shell, driver, hosted, browser, "open_intensity_trace")
    until(driver, lambda: delivered(shell, "intensity_trace"))
    trace = shell.hosted["intensity_trace"]
    assert trace.extra["handoffs"] == ["tttr_trace"]
    app = unwrap(trace.app)
    app.wait()
    driver.frame(3)
    assert type(app) is IntensityTraceApp
    assert app.model.path == str(work / "m001.spc")
    assert app.model.window_ms == 10.0
    assert app.model.setup == ALEX
    assert sorted(app.model.choices()) == ["green", "red", "yellow"]
    assert app.model.counts.shape[0] > 6000 and app.model.counts.shape[1] == len(app.model.labels)
    window = shell.docks.window(trace.key)
    assert window is not None and window.workspace is False  # a tool is a dock, never a fit window
    # Docked right of the workspace, or floating at its declared size when that dock is
    # narrower than the tool (the shell's wide-tool rule): never in the workspace.
    assert shell.docks.region_of(trace.key) in (TOOL_REGION, None)
    assert browser.model.status_text.startswith("Sent m001.spc") and browser.model.error_text == ""
    driver.screenshot(out / "1_hmm_intensity_trace.png")

    # TW: the Time Window tool queues the file, takes the bin window and previews the file
    click(shell, driver, hosted, browser, "open_time_window")
    until(driver, lambda: delivered(shell, "tttr_time_windows"))
    tw = shell.hosted["tttr_time_windows"]
    assert tw.extra["handoffs"] == ["tttr_files"]
    tool = unwrap(tw.app).tool
    assert [str(p) for p in tool._file_paths] == [str(work / "m001.spc")]
    assert tool.time_window_ms == 10.0
    assert unwrap(tw.app).time_window_gui.preview_index == 0
    driver.frame(5)
    driver.screenshot(out / "2_tw_time_windows.png")

    # NDX: the browser writes the burst table beside the data, ndX opens that folder
    click(shell, driver, hosted, browser, "open_ndxplorer")
    until(driver, lambda: delivered(shell, "ndxplorer"), timeout=240.0)
    ndx = shell.hosted["ndxplorer"]
    assert ndx.extra["handoffs"] == ["open_path"], ndx.extra
    folder = work / "m001_TW_10ms"
    assert (folder / "bi4_bur" / "m001.bur").exists()
    ndx_app = unwrap(ndx.app)
    assert pathlib.Path(str(ndx_app.model.path)) == folder
    assert ndx_app.model.source is not None and len(ndx_app.model.source) > 6000
    driver.frame(5)
    driver.screenshot(out / "3_ndx.png")
    assert browser.model.error_text == ""
    assert [r["name"] for r in browser.model.requests] == list(HANDOFFS)


def test_hmm_follows_the_bin_window_of_the_browser(shell, work):
    shell, driver = shell
    hosted, browser = open_browser(shell, driver, work)
    select(browser, driver, "m000.spc")
    browser.model.window_ms = 1.0
    click(shell, driver, hosted, browser, "open_intensity_trace")
    until(driver, lambda: delivered(shell, "intensity_trace"))
    app = unwrap(shell.hosted["intensity_trace"].app)
    app.wait()
    assert app.model.window_ms == 1.0 and app.model.path == str(work / "m000.spc")
    assert app.model.counts.shape[0] > 60000


def test_a_second_hand_off_reuses_the_open_dock_and_previews_the_new_file(shell, work):
    """Deliberate difference to the Qt adapter, which opened a new window per press: a tool is one dock."""
    shell, driver = shell
    hosted, browser = open_browser(shell, driver, work)
    select(browser, driver, "m000.spc")
    click(shell, driver, hosted, browser, "open_time_window")
    until(driver, lambda: delivered(shell, "tttr_time_windows"))
    tw = shell.hosted["tttr_time_windows"]
    select(browser, driver, "m001.spc")
    browser.model.window_ms = 20.0
    click(shell, driver, hosted, browser, "open_time_window")
    until(driver, lambda: len(tw.extra.get("handoffs", [])) == 2)
    assert shell.hosted["tttr_time_windows"] is tw
    tool = unwrap(tw.app).tool
    assert [p.name for p in tool._file_paths] == ["m000.spc", "m001.spc"]
    assert tool.time_window_ms == 20.0 and unwrap(tw.app).time_window_gui.preview_index == 1


# ---- failures are said ------------------------------------------------------------------------------
def test_requests_that_cannot_be_fulfilled_raise_or_are_said(shell, work):
    from chisurf.plugins.tttr.trace_browser.gui.handoffs import handle

    shell, driver = shell
    with pytest.raises(ValueError, match="unknown request"):
        handle("open_something_else", {})
    with pytest.raises(FileNotFoundError, match="gone.spc"):
        handle("open_intensity_trace", {"file": str(work / "gone.spc"), "window_ms": 10.0})
    with pytest.raises(FileNotFoundError, match="gone.spc"):
        handle("open_time_window", {"files": [str(work / "gone.spc")], "window_ms": 10.0})
    with pytest.raises(FileNotFoundError):
        handle("open_ndxplorer", {"folder": str(work / "nothing_TW_10ms"), "file": "x"})
    assert shell.hosted == {}  # nothing opened for a request refused up front
    # a file that exists but is no measurement: the tool opens and says why it cannot take it
    (work / "notes.txt").write_text("not a measurement")
    handle("open_time_window", {"files": [str(work / "notes.txt")], "window_ms": 10.0})
    until(driver, lambda: delivered(shell, "tttr_time_windows"))
    error = shell.hosted["tttr_time_windows"].extra["handoff_error"]
    assert "not a TTTR file" in error and "not a TTTR file" in shell.status


def test_a_failing_hand_off_shows_an_error_status_and_the_app_keeps_drawing(shell, work):
    shell, driver = shell
    hosted, browser = open_browser(shell, driver, work)
    select(browser, driver, "m000.spc")
    (work / "m000.spc").unlink()  # the file vanishes after it was listed
    click(shell, driver, hosted, browser, "open_intensity_trace")
    driver.frame(3)
    assert "could not open open_intensity_trace" in browser.model.error_text
    assert "m000.spc does not exist" in browser.model.error_text
    assert "intensity_trace" not in shell.hosted
    driver.frame(2)


# ---- the wiring --------------------------------------------------------------------------------------
def test_an_explicit_on_request_wins_over_the_shell(shell, work, monkeypatch):
    from chisurf.plugins.tttr.trace_browser.gui.app import make_app
    from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t4 import (
        open_folder,
    )
    from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t4 import (
        select as select_standalone,
    )

    shell, _driver = shell
    received = []
    app = make_app(on_request=lambda name, payload: received.append(name))
    try:
        assert app.on_request.__name__ == "<lambda>"
        app.model.accept_setup(json.loads(json.dumps(ALEX)))
        app.model.precompute_after_scan = False
        open_folder(app, work)
        select_standalone(app, "m000.spc")
        with pressing(monkeypatch, "TW"):
            frames(app, n=1)
        frames(app, n=2)
        assert received == ["open_time_window"] and shell.hosted == {}
    finally:
        app.close()


def test_without_a_shell_the_buttons_stay_greyed(work, monkeypatch):
    """No host is installed (the app runs on its own): nothing hands off, the three buttons are greyed."""
    from chisurf.core.plugin import handoff
    from chisurf.plugins.tttr.trace_browser.gui.app import make_app
    from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t4 import (
        button_states,
        open_folder,
    )
    from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t4 import (
        select as select_standalone,
    )

    monkeypatch.setattr(handoff, "_HOST", None)
    app = make_app()
    try:
        assert app.on_request is None and app.model.host_connected is False
        app.model.accept_setup(json.loads(json.dumps(ALEX)))
        open_folder(app, work)
        select_standalone(app, "m000.spc")
        states = button_states(app)
        assert states["HMM"] is True and states["TW"] is True and states["NDX"] is True
        assert not any(app.model.enabled(name) for name in HANDOFFS)
    finally:
        app.close()


def test_make_app_stays_qt_free_when_qt_is_blocked_and_without_a_shell():
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
assert not any(m == 'chisurf.gui' or m.startswith('chisurf.gui.') for m in sys.modules)
print('OK')
"""
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0 and "OK" in done.stdout, done.stdout + done.stderr


def test_the_qt_free_proof_of_the_port_still_passes():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("trace_browser")
    assert result["ok"], result["output"]


def test_the_qt_adapter_is_retired_and_the_sources_name_no_qt():
    gui = pathlib.Path(__file__).parents[1] / "gui"
    assert not (gui / "host.py").exists() and not (gui / "host_lookup.py").exists()
    for name in ("app.py", "model.py", "handoffs.py"):
        source = (gui / name).read_text()
        for needle in ("qtpy", "PyQt", "PySide", "chisurf.gui", "QApplication"):
            assert needle not in source, (name, needle)
