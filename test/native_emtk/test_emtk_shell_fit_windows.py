"""A new fit opens as a window inside the Workspace, by every path that makes one.

Owner, 2026-10-14: "new fit windows should open as windows in workspace" -- as the Qt window's MDI
opened a subwindow: floating inside the workspace at the next cascade place, focused, never a tab
covering the others (unless the user keeps the fits tabbed) and never a dock elsewhere. Every path
that makes a fit reaches the shell as ``fit.created`` and :meth:`DataDocks.open_window`; each is
driven here: + Analysis, the API (a macro, the console, an RPC client, a model search), and a
reopened project.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY, READ_KEY
from chisurf.emtk.main_app import EmtkShellApp

REPO = Path(__file__).resolve().parents[2]
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    return tmp_path


@pytest.fixture
def shell(isolated):
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    app = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                       console_session_file=False)
    app.data.adopt(session)
    yield app
    app.close()
    session.close()


def _idle(shell) -> bool:
    project = shell.project
    return not shell.data.busy and not shell.data._dirty and not project.busy


def _settle(driver, predicate, what, timeout=120.0):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}: {shell_status(driver)}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def shell_status(driver):
    return driver.app.data.status


def _load(driver, shell):
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    data.read.experiment = "FCS"
    data.read.experiment_changed("FCS")
    data.read.setup = "Seidel Kristine"
    data.read.path = str(KRISTINE)
    count = len(data.datasets.datasets)
    driver.click("read.load")
    _settle(driver, lambda: _idle(shell) and len(data.datasets.datasets) > count, "the file")


def _add_fit(driver, shell):
    data = shell.data
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    data.datasets.select_dataset(data.datasets.datasets[-1])
    data.datasets.model = MODEL
    count = len(data.datasets.fits)
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and len(data.windows) > count, "the fit window")
    return data.datasets.fits[-1]["uid"]


def _assert_in_workspace(shell, uids):
    docks = getattr(shell, "workspace_docks", shell.docks)
    bounds = docks.floating_bounds()
    frames = []
    for uid in uids:
        key = shell.data.windows[uid].key
        win = docks.window(key)
        assert win is not None and win.workspace, "a fit window is a document of the workspace"
        assert docks.region_of(key) is None, "it floats in the workspace (not a tab, not a dock)"
        x, y, w, h = win.frame
        bx, by, bw, bh = bounds
        assert x >= bx - 0.5 and y >= by - 0.5 and x + w <= bx + bw + 0.5 and y + h <= by + bh + 0.5
        assert w < bw and h < bh, "not maximized over the others"
        frames.append((x, y))
    assert len(set(frames)) == len(frames), "each new window at its own cascade place"
    assert docks.z[-1] == shell.data.windows[uids[-1]].key, "the newest is in front"
    assert docks.focused == shell.data.windows[uids[-1]].key


def test_add_analysis_opens_each_fit_as_a_cascaded_window_in_the_workspace(shell):
    driver = Driver(shell, (1440, 900))
    driver.frame(2)
    _load(driver, shell)
    uids = [_add_fit(driver, shell) for _ in range(3)]
    driver.frame(4)
    _assert_in_workspace(shell, uids)
    xs = [shell.docks.window(shell.data.windows[u].key).frame[0] for u in uids]
    assert xs == sorted(xs), "a title bar below and right of the last"
    driver.screenshot(SHOTS / "emtk_shell_three_fit_windows.png")


def test_a_fit_made_through_the_api_opens_a_workspace_window(shell):
    """The macro / console / RPC / model-search path: ``fit.create`` on the server."""
    driver = Driver(shell, (1440, 900))
    driver.frame(2)
    _load(driver, shell)
    api = shell.data.session.api
    uid = api.add_fit([len(shell.data.datasets.datasets) - 1], model_name=MODEL)["uid"]
    _settle(driver, lambda: _idle(shell) and uid in shell.data.windows, "the window")
    driver.frame(3)
    _assert_in_workspace(shell, [uid])


def test_the_fits_of_a_reopened_project_open_as_workspace_windows(shell, isolated):
    driver = Driver(shell, (1440, 900))
    driver.frame(2)
    _load(driver, shell)
    _add_fit(driver, shell)
    _add_fit(driver, shell)
    project, data = shell.project, shell.data
    target = isolated / "two_fits.cs.pto"
    project.save_as()
    driver.frame(2)
    project.choose_file(target)
    _settle(driver, lambda: _idle(shell) and project.document.path is not None, "the save")
    project.close_project()
    _settle(driver, lambda: _idle(shell) and not data.datasets.fits, "the empty session")
    project.open_recent(str(target))
    _settle(driver, lambda: _idle(shell) and len(data.windows) == 2, "the reopened fits")
    driver.frame(3)
    _assert_in_workspace(shell, [r["uid"] for r in data.datasets.fits])


def test_with_the_fits_tabbed_a_new_fit_is_a_tab_too(shell):
    """*Tabbed* is the workspace's maximized mode: while every fit is a tab, a new one joins them."""
    driver = Driver(shell, (1440, 900))
    driver.frame(2)
    _load(driver, shell)
    first = _add_fit(driver, shell)
    shell.docks.tab_workspace()
    driver.frame(2)
    second = _add_fit(driver, shell)
    for uid in (first, second):
        assert shell.docks.region_of(shell.data.windows[uid].key) == "center"
