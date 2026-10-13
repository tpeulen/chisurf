"""The emtk shell's status strip (W9 S5) against the Qt main window's status bar.

The before-half is ``shell_s5_status_qt_inventory.json`` (``capture_shell_s5_status_qt_before.py``):
the controls the Qt status bar shows in five states (idle, a log message, a startup stage, an
operation with a known size and ✕, a busy operation). Each state is driven here through the
shell's own sources -- a log record, the session's startup stage callback, the progress-host
contract, a call on the data docks' worker -- and the strip's drawn controls are compared
control by control; ✕ is pressed the way a user presses it, through :class:`emtk.testing.Driver`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.main_app import EmtkShellApp

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
BEFORE = json.loads(
    Path(__file__).with_name("shell_s5_status_qt_inventory.json").read_text("utf-8")
)
#: The capture's texts (``capture_shell_s5_status_qt_before.py``).
MESSAGE = "The IRF file has no header; the bin width is guessed."
STAGE = {"id": "emtk_experiments", "label": "Loading plugins", "progress": 28}
TASK = ("Fitting fit 1…", 100, 40)
BUSY = "Reading the fits…"

#: Qt status-bar controls the strip does not have yet (ledger items); this only shrinks.
KNOWN_GAPS: dict[str, str] = {}
#: ``(state, kind, text)`` the strip shows differently on purpose, and how.
DELIBERATE = {
    ("startup", "message", "Loading plugins"): (
        "the stage is the operation's text beside its bar; the Qt bar's showMessage hides its own "
        "startup progress bar, so Qt shows the stage as a bare message"
    ),
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Recent projects in ``tmp_path``; English."""
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    from chisurf.emtk.i18n import install, set_locale

    install("en")
    yield
    set_locale("en")


def _shell(session_factory=None) -> EmtkShellApp:
    return EmtkShellApp(
        loader=lambda plugin_id: None,
        session_factory=session_factory,
        console_history=False,
        console_session_file=False,
    )


@pytest.fixture
def shell(isolated):
    app = _shell()
    yield app
    app.close()


def _key(control: dict) -> tuple:
    return (control["kind"], control["text"], control.get("value"), control.get("maximum"))


def _assert_parity(state: str, strip) -> None:
    drawn = [_key(c) for c in strip.drawn]
    missing = []
    for control in BEFORE["states"][state]:
        if (state, control["kind"], control["text"]) in DELIBERATE:
            assert any(control["text"] in c[1] for c in drawn), (state, control, drawn)
            continue
        if _key(control) not in drawn:
            missing.append(control)
    missing = [c for c in missing if c["text"] not in KNOWN_GAPS]
    assert not missing, f"{state}: Qt shows {missing}; the strip drew {drawn}"
    # Every control the strip reports was drawn where a user can see it.
    kinds = {c["kind"] for c in strip.drawn}
    rects = strip.item_rects
    assert "status.message" in rects
    if "progress" in kinds:
        assert {"status.task", "status.bar"} <= set(rects), rects
    if "button" in kinds:
        assert "status.cancel" in rects


def _along_the_bottom(shell, driver) -> None:
    x, y, w, h = shell.item_rects["status.message"]
    assert y > driver.size[1] - 30, "the strip is the window's bottom line"


def test_idle_shows_ready(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame(2)
    _assert_parity("idle", shell.status_strip)
    _along_the_bottom(shell, driver)
    driver.screenshot(SHOTS / "emtk_status_idle.png")


def test_a_warning_logged_anywhere_is_the_message(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame()
    logging.getLogger("chisurf.capture").warning(MESSAGE)
    driver.frame(2)
    _assert_parity("message", shell.status_strip)
    driver.screenshot(SHOTS / "emtk_status_message.png")


def test_an_operation_shows_text_bar_and_cancel_and_the_cancel_reaches_the_work(shell):
    driver = Driver(shell, size=(1440, 900))
    driver.frame()
    cancelled: list[bool] = []
    task = shell.begin_task(TASK[0], TASK[1], cancel=lambda: cancelled.append(True))
    task.setValue(TASK[2])
    driver.frame(2)
    _assert_parity("task", shell.status_strip)
    driver.screenshot(SHOTS / "emtk_status_task.png")
    driver.click("status.cancel")
    assert cancelled == [True] and task.wasCanceled()
    task.close()
    driver.frame()
    assert shell.status_strip.task is None
    assert "status.bar" not in shell.status_strip.item_rects


def test_a_call_on_the_data_worker_is_a_busy_operation(shell):
    from chisurf.emtk.fit_docks import _Job

    driver = Driver(shell, size=(1440, 900))
    driver.frame()
    shell.data.job = _Job(BUSY)
    driver.frame(2)
    _assert_parity("busy", shell.status_strip)
    assert shell.animating(), "a busy bar slides, so frames keep coming"
    driver.screenshot(SHOTS / "emtk_status_busy.png")
    shell.data.job = None
    driver.frame()
    assert shell.status_strip.task is None


def test_the_sessions_startup_stage_is_on_the_strip(isolated):
    release = threading.Event()
    reached = threading.Event()

    def factory(wake=None, on_stage=None):
        on_stage(dict(STAGE))
        reached.set()
        release.wait(30)
        raise RuntimeError("no session in this test")

    shell = _shell(factory)
    try:
        assert reached.wait(10)
        driver = Driver(shell, size=(1440, 900))
        driver.frame(2)
        _assert_parity("startup", shell.status_strip)
        task = shell.status_strip.task
        assert task is not None and task.value() == STAGE["progress"]
        driver.screenshot(SHOTS / "emtk_status_startup.png")
    finally:
        release.set()
        shell.close()


def test_a_sampling_job_shows_its_percentage_and_cancel_asks_the_server(shell):
    asked: list[str] = []

    class Api:
        def cancel_sampling(self, job_id):
            asked.append(job_id)
            return {"ok": True}

    class Events:
        def drain(self):
            return None

    class Session:
        api = Api()
        events = Events()

    driver = Driver(shell, size=(1440, 900))
    driver.frame()
    data = shell.data
    data.session = Session()
    data.sampling_job = "job-1"
    data.sampling_progress = 55
    data._sampling_polled = float("inf")  # no poll of the fake server
    data._dirty = set()
    try:
        driver.frame(2)
        controls = shell.status_strip.drawn
        assert ("progress", "", 55, 100) in [_key(c) for c in controls], controls
        driver.click("status.cancel")
        assert asked == ["job-1"]
    finally:
        data.sampling_job = ""
        data.session = None
