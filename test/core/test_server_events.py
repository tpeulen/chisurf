"""The Qt-free subscriber hears the server's PUB events and dispatches them on the caller's thread."""

from __future__ import annotations

import socket
import sys
import threading
import time

import pytest

from chisurf.core.server_events import ServerEventSubscriber


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def server():
    """A real ChiSurf server on private ports, serving on its own thread."""
    from chisurf.server.app import ChiSurfServer
    from chisurf.server.session import SessionState
    from chisurf.server.transport.zmq import ZmqClient

    cmd, pub = _free_port(), _free_port()
    srv = ChiSurfServer(cmd_port=cmd, pub_port=pub, state=SessionState())
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    client = ZmqClient(cmd_port=cmd, pub_port=pub, timeout_ms=2000)
    client.connect()
    end = time.monotonic() + 30
    while "result" not in client.call("meta.ping", {}):
        assert time.monotonic() < end, "the server did not answer"
    client.close()
    yield srv
    srv.stop()
    thread.join(5)


def _publish_until(srv, subscriber, topic, payload, timeout=10.0):
    """Publish until the subscriber has queued something (ZMQ drops what a SUB joins too late for)."""
    end = time.monotonic() + timeout
    while subscriber.pending == 0:
        assert time.monotonic() < end, f"{topic} never reached the subscriber"
        srv.event_bus.publish(topic, payload)
        time.sleep(0.05)


def test_a_published_fit_updated_reaches_the_subscriber(server):
    woken = threading.Event()
    seen: list[dict] = []
    owner = threading.get_ident()
    threads: list[int] = []

    def on_fit(payload):
        seen.append(payload)
        threads.append(threading.get_ident())

    subscriber = ServerEventSubscriber(server.pub_port, wake=woken.set).start()
    subscriber.subscribe("fit.", on_fit)
    subscriber.subscribe(
        "dataset.", lambda payload: pytest.fail("a fit event is not a dataset one")
    )
    try:
        _publish_until(server, subscriber, "fit.updated", {"fit_uid": "abc", "fit_name": "demo"})
        assert woken.wait(2), "the worker did not wake its owner"
        assert seen == [], "nothing is dispatched before the owner drains"
        assert subscriber.drain() >= 1
        assert seen[0]["topic"] == "fit.updated" and seen[0]["fit_uid"] == "abc"
        assert set(threads) == {owner}, "callbacks run on the draining thread"
        assert subscriber.pending == 0
    finally:
        subscriber.stop()
    assert not subscriber.running


def test_drain_limit_keeps_the_rest_queued(server):
    subscriber = ServerEventSubscriber(server.pub_port).start()
    got: list[str] = []
    subscriber.subscribe("", lambda payload: got.append(payload["topic"]))
    try:
        _publish_until(server, subscriber, "session.cleared", {})
        for _ in range(3):
            server.event_bus.publish("dataset.added", {"dataset_index": 0})
        end = time.monotonic() + 5
        while subscriber.pending < 3 and time.monotonic() < end:
            time.sleep(0.02)
        before = subscriber.pending
        assert subscriber.drain(limit=1) == 1
        assert subscriber.pending == before - 1
        subscriber.drain()
        assert "dataset.added" in got
    finally:
        subscriber.stop()


def test_the_subscriber_module_does_not_import_qt():
    import subprocess

    code = (
        "import sys, chisurf.core.server_events as m; "
        "bad = [k for k in sys.modules if k.split('.')[0] in ('PyQt5', 'PyQt6', 'PySide2', "
        "'PySide6', 'qtpy')]; print(bad); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr
