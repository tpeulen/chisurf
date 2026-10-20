"""A call that finishes after its client closed fails quietly, not as an error log."""

from __future__ import annotations

import logging
import threading

import pytest

from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient


class _SlowTransport:
    """Answers a call with a timeout error, but only once the test lets it."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.closed = False

    def call(self, method, params):
        self.release.wait(5.0)
        return {"ok": False, "error": "timeout: no response within 5000ms"}

    def close(self):
        self.closed = True


def test_a_failure_after_close_is_not_logged_as_an_error(caplog):
    transport = _SlowTransport()
    client = MMFDBClient(client=transport)
    errors = []

    def work():
        try:
            client.list_users()
        except RuntimeError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=work)
    with caplog.at_level(logging.WARNING):
        worker.start()
        client.close()
        transport.release.set()
        worker.join(5.0)
    assert transport.closed
    assert errors == ["timeout: no response within 5000ms"]  # the caller still learns it failed
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_a_failure_while_open_is_still_logged(caplog):
    transport = _SlowTransport()
    transport.release.set()
    client = MMFDBClient(client=transport)
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        client.list_users()
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
