"""The emtk shell's post-show startup stages (W9 S5): the update check.

The deleted Qt window ran ``services.d/30_gui_post_show.json`` after it was shown. Its
window-building stages have shell equivalents of their own (history, autosave, plugin menus); the
one that is not about the window -- ``check_updates`` -- is the shell's ``surface="emtk"``,
``phase="post_show"`` set (``35_emtk_post_show.json``). ``warmup_imports`` has no twin: the session's own stages have
imported what a first fit needs before the window opens, and an import on a worker thread racing
the frame loop is how the shell deadlocked (``test/startup/test_startup_import_race.py``). Checked here: the set
is declared and resolvable, the stages honour the shared updater preferences and never import Qt,
and in the shell they run once the session is adopted, show on the status strip and, when a newer
version exists, ask the Qt window's *Update Available* question, whose *Yes* opens *Settings* on
its *Updates* page. The question is answered through :class:`emtk.testing.Driver`, by click.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.testing import Driver

from chisurf.emtk import post_show
from chisurf.emtk.main_app import EmtkShellApp

REPO = Path(__file__).resolve().parents[2]
SERVICES = REPO / "chisurf" / "startup" / "services.d"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
#: The post-show stages and the words they show on the status strip. The labels are the ones
#: the deleted Qt window's ``30_gui_post_show.json`` used, pinned here now that it is gone.
STAGE_LABELS = {"emtk_check_updates": "Checking for updates"}


def _specs(name: str) -> dict[str, dict]:
    data = json.loads((SERVICES / name).read_text("utf-8"))
    return {spec["id"]: spec for spec in data["services"]}


def test_the_post_show_set_is_declared_for_the_emtk_surface():
    from chisurf.startup.services import AppStartupServiceManager

    emtk = _specs("35_emtk_post_show.json")
    for emtk_id, label in STAGE_LABELS.items():
        assert emtk[emtk_id]["label"] == label
        assert emtk[emtk_id]["surface"] == "emtk" and emtk[emtk_id]["phase"] == "post_show"
    ordered = AppStartupServiceManager().ordered_specs(surface="emtk", phase="post_show")
    assert [spec.id for spec in ordered] == ["emtk_check_updates"]
    for spec in ordered:
        module, _, name = spec.entrypoint.partition(":")
        assert callable(getattr(__import__(module, fromlist=[name]), name)), spec.entrypoint


def test_the_stages_import_no_qt(tmp_path):
    """Run the whole set (update check suppressed) in a fresh interpreter: no Qt module appears."""
    code = (
        "import sys\n"
        "from chisurf.core.settings import cs_settings\n"
        "cs_settings.setdefault('plugins', {})['updater'] = {'check_on_startup': False}\n"
        "from chisurf.emtk.post_show import run_post_show\n"
        "seen = []\n"
        "run_post_show(lambda p: seen.append(p['id']))\n"
        "assert seen == ['emtk_check_updates'], seen\n"
        "qt = sorted(m for m in sys.modules if m.split('.')[0] in ('qtpy', 'PyQt5', 'PyQt6', 'PySide6'))\n"
        "print('QT', qt)\n"
    )
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=240
    )
    assert done.returncode == 0, done.stderr[-3000:]
    assert "QT []" in done.stdout, done.stdout


@pytest.mark.parametrize(
    ("settings", "wanted"),
    [
        ({}, True),
        ({"plugins": {"updater": {"check_on_startup": False}}}, False),
        ({"plugins": {"updater": {"ignore_updates_on_startup": True}}}, False),
        ({"plugins": {"updater": {"check_on_startup": True}}}, True),
    ],
)
def test_the_update_check_honours_the_shared_preferences(settings, wanted):
    assert post_show.update_check_wanted(settings) is wanted


def test_the_update_stage_leaves_an_offer_only_for_a_newer_version(monkeypatch):
    from chisurf.plugins.core.updater import updater

    monkeypatch.setattr(post_show, "update_check_wanted", lambda settings=None: True)
    monkeypatch.setattr(
        updater, "build_installed_vs_latest_changelog", lambda latest: ("1.0", "- faster fits")
    )
    for answer, offered in (
        ((False, None, None), False),
        ((False, None, "offline"), False),
        ((True, "9.9", None), True),
    ):
        monkeypatch.setattr(updater, "check_for_updates", lambda answer=answer: answer)
        context = SimpleNamespace(metadata={})
        post_show.stage_check_updates(context)
        assert ("update_offer" in context.metadata) is offered
    assert context.metadata["update_offer"] == {
        "latest": "9.9",
        "installed": "1.0",
        "changes": "- faster fits",
    }
    monkeypatch.setattr(post_show, "update_check_wanted", lambda settings=None: False)
    monkeypatch.setattr(updater, "check_for_updates", lambda: pytest.fail("asked the server"))
    post_show.stage_check_updates(SimpleNamespace(metadata={}))


# -- in the shell ----------------------------------------------------------------------------- #


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    from chisurf.emtk.i18n import install, set_locale

    install("en")
    yield
    set_locale("en")


class _Events:
    def drain(self):
        return None


class _Session:
    events = _Events()


class _SetupStub:
    """Stands in for the Settings hub: records the page it was asked to show."""

    def __init__(self):
        from emtk.app import ImApp

        self.pages: list[str] = []
        self.app = ImApp(lambda: None)

    def select(self, key):
        self.pages.append(key)

    def draw(self, painter, x, y, w, h):
        self.app.draw(painter, x, y, w, h)

    def __getattr__(self, name):
        return getattr(self.app, name)


def _shell(runner, setup=None) -> EmtkShellApp:
    return EmtkShellApp(
        loader=lambda plugin_id: setup if plugin_id == "setup" else None,
        console_history=False,
        console_session_file=False,
        post_show=runner,
    )


def _join(build) -> None:
    """Wait for a :class:`~chisurf.emtk.background_build.BackgroundBuild`'s worker; the frame collects it."""
    thread = build._thread
    if thread is not None:
        thread.join(10)


def _adopt(shell) -> None:
    data = shell.data
    data.session = _Session()
    data._dirty = set()


def test_the_default_shell_runs_no_post_show_stages(isolated):
    shell = EmtkShellApp(loader=lambda p: None, console_history=False, console_session_file=False)
    try:
        assert shell.post_show is None
    finally:
        shell.close()


def test_the_stages_wait_for_the_session_run_once_and_show_on_the_strip(isolated):
    calls: list[int] = []
    release = threading.Event()
    staged = threading.Event()

    def runner(on_stage):
        calls.append(1)
        on_stage({"id": "emtk_check_updates", "label": "Checking for updates", "progress": 50})
        staged.set()
        release.wait(10)
        return {}

    shell = _shell(runner)
    driver = Driver(shell, size=(1440, 900))
    try:
        driver.frame(2)
        assert calls == [], "the stages wait for the session"
        _adopt(shell)
        driver.frame()
        assert staged.wait(10)
        driver.frame(2)
        texts = [c["text"] for c in shell.status_strip.drawn]
        assert "Checking for updates" in texts, shell.status_strip.drawn
        SHOTS.mkdir(parents=True, exist_ok=True)
        driver.screenshot(SHOTS / "emtk_post_show_strip.png")
        release.set()
        _join(shell.post_show.build)
        driver.frame(3)
        assert calls == [1], "once per shell"
        assert "Checking for updates" not in [c["text"] for c in shell.status_strip.drawn]
    finally:
        release.set()
        shell.data.session = None
        shell.close()


def test_a_newer_version_asks_and_yes_opens_settings_on_updates(isolated):
    setup = _SetupStub()
    offer = {"latest": "9.9", "installed": "1.0", "changes": "- faster fits"}
    shell = _shell(lambda on_stage: {"update_offer": offer}, setup=setup)
    driver = Driver(shell, size=(1440, 900))
    try:
        _adopt(shell)
        driver.frame()
        _join(shell.post_show.build)
        driver.frame(3)
        question = shell.project.dialogs.current
        assert question is not None and question.title == "Update Available"
        assert "9.9" in question.message and "- faster fits" in question.message
        assert "Do you want to open the Updater now?" in question.message
        SHOTS.mkdir(parents=True, exist_ok=True)
        driver.screenshot(SHOTS / "emtk_post_show_update_question.png")
        driver.click(question.rects["button.yes"])
        hosted = shell.hosted.get("setup")
        assert hosted is not None, "Yes opens Settings"
        if hosted.build is not None:
            _join(hosted.build)
        driver.frame(3)
        assert "setup" in shell.hosted, "Yes opens Settings"
        assert setup.pages == ["updates"], "on its Updates page"
    finally:
        shell.data.session = None
        shell.close()


def test_no_answer_opens_nothing(isolated):
    from emtk.message_dialog import auto_answer

    shell = _shell(lambda on_stage: {"update_offer": {"latest": "9.9"}})
    driver = Driver(shell, size=(1440, 900))
    try:
        _adopt(shell)
        with auto_answer(confirm=False):
            driver.frame()
            _join(shell.post_show.build)
            driver.frame(3)
        assert "setup" not in shell.hosted
        assert shell.project.dialogs.current is None
    finally:
        shell.data.session = None
        shell.close()
