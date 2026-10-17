"""Startup diagnostics retain failures without importing a fallback GUI.

``python -m chisurf`` opens the emtk shell (behind its splash window) through a crash-log
wrapper: a failed start is logged with its traceback, re-raised as the original object (the
terminal shows it), and leaves a closed ``crash_*.log`` in the settings folder.
"""

from __future__ import annotations

import builtins
import faulthandler
import logging
import os
import pathlib
import sys
import types
from unittest.mock import Mock

import pytest

import chisurf.__main__ as chisurf_main


class _HardExit(BaseException):
    """Stand in for successful process termination without exiting pytest."""


@pytest.fixture()
def startup(monkeypatch, tmp_path):
    """Isolate application startup, crash logs and process termination."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path / "unused-home")
    shell = types.ModuleType("chisurf.emtk.main_app")
    shell.main = Mock(return_value=7)
    monkeypatch.setitem(sys.modules, "chisurf.emtk.main_app", shell)
    monkeypatch.setattr(sys, "argv", ["chisurf"])
    opened = []
    path_open = pathlib.Path.open

    def track_open(path, *args, **kwargs):
        """Record crash-file resources while retaining normal file behavior."""
        stream = path_open(path, *args, **kwargs)
        if path.name.startswith("crash_"):
            opened.append((path, stream))
        return stream

    monkeypatch.setattr(pathlib.Path, "open", track_open)
    enable = Mock()

    def disable_before_close():
        """Require the crash-file descriptor to remain valid during disable."""
        assert opened and all(not stream.closed for _, stream in opened)

    disable = Mock(side_effect=disable_before_close)
    hard_exit = Mock(side_effect=_HardExit)
    monkeypatch.setattr(faulthandler, "enable", enable)
    monkeypatch.setattr(faulthandler, "disable", disable)
    monkeypatch.setattr(os, "_exit", hard_exit)
    yield types.SimpleNamespace(
        shell=shell,
        # What opens the window: the emtk shell's main.
        launch=shell.main,
        opened=opened,
        enable=enable,
        disable=disable,
        hard_exit=hard_exit,
        directory=tmp_path,
    )
    for _, stream in opened:
        stream.close()


def _assert_logged_reraised_and_closed(startup, caplog, failure, captured, *, disabled):
    """The failure is the one raised, logged with its traceback, and the crash file is closed."""
    assert captured.value is failure
    records = [record for record in caplog.records if record.exc_info]
    assert any(record.exc_info[1] is failure for record in records)
    assert "Traceback (most recent call last)" in caplog.text
    assert str(failure) in caplog.text
    assert len(startup.opened) == 1
    path, stream = startup.opened[0]
    assert path.parent == startup.directory
    assert stream.closed
    assert startup.disable.call_count == disabled
    startup.hard_exit.assert_not_called()


@pytest.mark.parametrize("phase", ["faulthandler", "launch"])
def test_startup_failure_retains_exception_and_closes_crash_file(startup, caplog, phase):
    """Every startup phase logs and re-raises the original exception object.

    ``launch`` is the emtk shell's ``main`` (the splash, the shell and its event loop).
    """
    failure = RuntimeError(f"startup failed in {phase}")
    {"faulthandler": startup.enable, "launch": startup.launch}[phase].side_effect = failure

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError) as captured:
        chisurf_main.main()

    _assert_logged_reraised_and_closed(
        startup, caplog, failure, captured, disabled=phase != "faulthandler"
    )


def test_success_exits_with_the_window_code_and_releases_crash_file(startup):
    """A closed window ends the process with its exit code."""
    with pytest.raises(SystemExit) as exited:
        chisurf_main.main()
    assert exited.value.code == 7
    startup.hard_exit.assert_not_called()
    startup.shell.main.assert_called_once_with([])

    startup.disable.assert_called_once_with()
    assert startup.opened[0][0].parent == startup.directory
    assert startup.opened[0][1].closed
    startup.enable.assert_called_once_with(file=startup.opened[0][1], all_threads=True)


def test_entrypoint_import_has_no_qt_dependency_or_error_dialog(monkeypatch):
    """Importing the entrypoint itself cannot construct a fallback Qt surface."""
    original_import = builtins.__import__
    attempted = []

    def track_import(name, *args, **kwargs):
        """Reject and record Qt imports made by the entrypoint."""
        if name.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}:
            attempted.append(name)
            raise ImportError("Qt must remain lazy")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", track_import)
    namespace = {"__name__": "chisurf_startup_probe", "__file__": chisurf_main.__file__}
    source = pathlib.Path(chisurf_main.__file__).read_text()
    exec(compile(source, chisurf_main.__file__, "exec"), namespace)
    assert attempted == []
    assert "SimpleErrorDialog" not in namespace


def test_startup_failure_does_not_clear_user_settings(startup):
    """A failure leaves every existing settings file intact."""
    marker = startup.directory / "settings_chisurf.yaml"
    marker.write_text("user_settings: keep\n")
    failure = RuntimeError("preserve settings")
    startup.launch.side_effect = failure

    with pytest.raises(RuntimeError) as captured:
        chisurf_main.main()

    assert captured.value is failure
    assert marker.read_text() == "user_settings: keep\n"


def test_crash_handler_cleanup_cannot_replace_the_startup_failure(startup, caplog):
    """A cleanup error is logged separately and retains the original failure."""
    failure = RuntimeError("original startup failure")
    startup.launch.side_effect = failure
    startup.disable.side_effect = OSError("crash cleanup failed")

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError) as captured:
        chisurf_main.main()

    assert captured.value is failure
    assert "crash cleanup failed" in caplog.text
    assert "original startup failure" in caplog.text
    assert startup.opened[0][1].closed
    startup.hard_exit.assert_not_called()
