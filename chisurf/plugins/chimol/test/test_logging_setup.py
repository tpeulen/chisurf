"""chimol's logging: one file in every mode, a console when standalone.

Two contracts are pinned here, because both have been quietly wrong before:

* **embedded, chimol does not double-print.** Inside a host that already
  configured the root logger (ChiSurf), chimol's records must reach the
  host's sinks through propagation -- and chimol itself must add no console
  handler, or every record appears twice on screen;
* **standalone, the log exists.** No host configures anything, so chimol
  owns the console and writes its rotating file itself.

Plus the ``log`` command: the session's tail shown in the info panel -- the
same overlay ``help`` and ``keys`` use -- read from an in-memory ring, so it
works identically where no file can exist (the browser).
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from chimol.logging_setup import (
    LOGGER,
    configure_logging,
    console_handler,
    log_path,
    recent_lines,
)


@pytest.fixture(autouse=True)
def _restore_root():
    """Every test on a clean slate, and the loggers back as it found them.

    chimol's handlers are module state (that is what makes ``configure_logging``
    idempotent in a process) -- and the plugin's import configures logging
    before any test runs, so "as found" would restore another run's handlers.
    This suite *is* about those handlers: start from none, and put back
    whatever was there only to be polite.
    """
    root = logging.getLogger()
    before_root_handlers = list(root.handlers)
    before_root_level = root.level
    before_chimol_handlers = list(LOGGER.handlers)
    LOGGER.handlers.clear()
    import chimol.logging_setup as _setup

    _setup._FILE_HANDLER = None
    _setup._CONSOLE_HANDLER = None
    yield
    root.handlers[:] = before_root_handlers
    root.setLevel(before_root_level)
    LOGGER.handlers[:] = before_chimol_handlers
    _setup._FILE_HANDLER = None
    _setup._CONSOLE_HANDLER = None


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Never write into a developer's real settings directory."""
    monkeypatch.setenv("CHIMOL_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.delenv("CHIMOL_LOG_FILE", raising=False)
    monkeypatch.delenv("CHIMOL_LOG_DISABLE", raising=False)
    monkeypatch.delenv("CHIMOL_LOG_LEVEL", raising=False)


def test_a_bare_root_gets_a_console_handler(tmp_path):
    # Under pytest the root logger is never bare (the logging plugin hangs a
    # capture handler on it), so the standalone case is staged rather than
    # hoped for -- and the fixture puts the handlers back.
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        configure_logging(log_file=False)
        assert console_handler() is not None
    finally:
        root.handlers[:] = saved


def test_a_configured_root_gets_no_console_handler():
    """The embedded case: the host owns the console; chimol propagates."""
    # The host's handler is added to a *bare* root for the same reason as
    # above: under pytest the capture handler would already decide the
    # question, and the point here is what an embedded host looks like.
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    host_sink = logging.StreamHandler()
    root.addHandler(host_sink)
    try:
        configure_logging(log_file=False)
        assert console_handler() is None
        # ... and a record still reaches the host's sink through propagation.
        reached = []
        host_sink.emit = lambda record: reached.append(record.getMessage())
        LOGGER.warning("through the host")
        assert reached == ["through the host"]
    finally:
        root.removeHandler(host_sink)
        root.handlers[:] = saved


def test_the_log_file_lands_in_the_settings_directory(tmp_path):
    configure_logging()
    expected = tmp_path / "settings" / "logs" / "chimol.log"
    assert log_path() == expected
    assert expected.is_file()


def test_chimol_log_file_overrides_the_location(monkeypatch, tmp_path):
    monkeypatch.setenv("CHIMOL_LOG_FILE", str(tmp_path / "elsewhere.log"))
    configure_logging()
    assert log_path() == tmp_path / "elsewhere.log"


def test_configuring_twice_does_not_double_the_handlers(tmp_path):
    configure_logging()
    files = [h for h in LOGGER.handlers if type(h).__name__ == "RotatingFileHandler"]
    configure_logging()
    files_after = [h for h in LOGGER.handlers if type(h).__name__ == "RotatingFileHandler"]
    assert len(files_after) == len(files) == 1


def test_the_ring_holds_the_tail_for_the_log_command():
    configure_logging(log_file=False)
    for index in range(12):
        LOGGER.info("event %02d", index)
    tail = recent_lines(3)
    assert len(tail) == 3
    assert "event 09" in tail[0] and "event 11" in tail[-1]
    assert all("INFO" in line for line in tail)


def test_records_reach_the_file_and_the_ring(tmp_path):
    configure_logging()
    LOGGER.warning("the pinned phrase")
    assert "the pinned phrase" in (tmp_path / "settings" / "logs" / "chimol.log").read_text()
    assert any("the pinned phrase" in line for line in recent_lines())


def test_log_disable_keeps_the_ring_but_drops_the_file(monkeypatch):
    """The browser case: no filesystem worth writing, ``log`` still works."""
    monkeypatch.setenv("CHIMOL_LOG_DISABLE", "1")
    configure_logging()
    assert log_path() is not None  # where it *would* be stays answerable
    files = [h for h in LOGGER.handlers if type(h).__name__ == "RotatingFileHandler"]
    assert files == []
    LOGGER.info("buffered anyway")
    assert any("buffered anyway" in line for line in recent_lines())
