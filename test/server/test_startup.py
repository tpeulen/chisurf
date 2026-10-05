from __future__ import annotations

import select
import subprocess
import sys
import time
from unittest.mock import patch

from chisurf.server.startup import (
    rpc_config_from_settings,
    rpc_is_available,
    terminate_and_collect_stderr,
)


def test_terminate_and_collect_stderr_does_not_block_live_process():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; sys.stderr.write('server failed' + chr(10)); "
            "sys.stderr.flush(); print('ready', flush=True); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        # Observe readiness instead of racing interpreter startup under load.
        ready, _, _ = select.select([proc.stdout], [], [], 5.0)
        assert ready and proc.stdout.readline().strip() == b"ready"
        assert proc.poll() is None
        stderr = terminate_and_collect_stderr(proc, timeout=1.0)
        assert "server failed" in stderr
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5.0)


def test_terminate_and_collect_stderr_is_bounded():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('x' * 100)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    proc.wait(timeout=5.0)
    stderr = terminate_and_collect_stderr(proc, limit=10, timeout=1.0)

    assert stderr == "x" * 10


def test_rpc_config_from_settings_returns_defaults():
    config = rpc_config_from_settings("agent")
    assert config["chisurf"]["host"] == "127.0.0.1"
    assert config["chisurf"]["cmd_port"] == 8765
    assert config["chisurf"]["pub_port"] == 8766
    assert config["editor"]["cmd_port"] == 8775


def test_rpc_config_from_settings_mmfdb_namespace():
    config = rpc_config_from_settings("mmfdb")
    assert config["chisurf"]["host"] == "127.0.0.1"


def test_rpc_is_available_returns_false_for_unreachable():
    available = rpc_is_available("127.0.0.1", 1, timeout_ms=100)
    assert available is False


def test_session_state_from_live_chisurf_returns_none_when_chisurf_unavailable():
    import sys

    orig = sys.modules.get("chisurf")
    if "chisurf" in sys.modules:
        del sys.modules["chisurf"]
    try:
        # Clear cached imports
        for mod in list(sys.modules.keys()):
            if mod.startswith("chisurf.server.startup"):
                del sys.modules[mod]
        from chisurf.server.startup import session_state_from_live_chisurf

        result = session_state_from_live_chisurf()
        assert result is None
    finally:
        if orig is not None:
            sys.modules["chisurf"] = orig


def test_session_state_from_live_chisurf_with_mock():
    from unittest.mock import MagicMock

    import chisurf.server.startup as startup_mod

    mock_cs = MagicMock()
    mock_cs.fits = ["fit1"]
    mock_cs.imported_datasets = ["ds1"]

    with patch.dict("sys.modules", {"chisurf": mock_cs}):
        with patch.object(startup_mod, "sync_current_fit_uid_from_live_chisurf") as mock_sync:
            state = startup_mod.session_state_from_live_chisurf()
            assert state is not None
            assert state.fits == ["fit1"]
            assert state.datasets == ["ds1"]
            mock_sync.assert_called_once_with(state)


def test_sync_current_fit_uid_from_chisurf_current_fit():
    from unittest.mock import MagicMock

    import chisurf.server.startup as startup_mod
    from chisurf.server.session import SessionState

    mock_fit = MagicMock()
    mock_fit.unique_identifier = "fit-gui-1"
    mock_cs = MagicMock()
    mock_cs.current_fit = mock_fit
    mock_cs.fits = [mock_fit]

    state = SessionState(current_fit_uid=None)
    with patch.dict("sys.modules", {"chisurf": mock_cs}):
        startup_mod.sync_current_fit_uid_from_live_chisurf(state)
    assert state.current_fit_uid == "fit-gui-1"


def test_ensure_embedded_chisurf_rpc_server_returns_false_for_unreachable():
    from chisurf.server.startup import ensure_embedded_chisurf_rpc_server

    for port in (18765, 18766):
        available = ensure_embedded_chisurf_rpc_server(
            "127.0.0.1",
            port,
            port + 1,
            timeout_s=0.5,
            state=None,
        )
        assert available is False


def test_ensure_embedded_chisurf_rpc_server_returns_true_when_available():
    import json
    import socket
    import threading

    import zmq

    from chisurf.server.startup import ensure_embedded_chisurf_rpc_server

    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    cmd = _find_free_port()
    pub = _find_free_port()
    ctx = zmq.Context()
    ready = threading.Event()
    stop = threading.Event()

    def _serve():
        # A ZMQ socket must be created, used and closed on its owning thread.
        rep = ctx.socket(zmq.REP)
        try:
            rep.bind(f"tcp://127.0.0.1:{cmd}")
            ready.set()
            while not stop.is_set():
                if not rep.poll(50, zmq.POLLIN):
                    continue
                msg = rep.recv_string()
                parsed = json.loads(msg)
                reply = {"jsonrpc": "2.0", "result": {"ok": True}, "id": parsed.get("id", 1)}
                rep.send_string(json.dumps(reply))
        finally:
            rep.close(linger=0)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    try:
        assert ready.wait(5.0)
        available = ensure_embedded_chisurf_rpc_server(
            "127.0.0.1",
            cmd,
            pub,
            timeout_s=2.0,
            state=None,
        )
        assert available is True
    finally:
        stop.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
        ctx.term()


def test_sync_current_fit_uid_from_list_selected():
    from unittest.mock import MagicMock, PropertyMock

    import chisurf.server.startup as startup_mod
    from chisurf.server.session import SessionState

    mock_fit = MagicMock()
    mock_fit.unique_identifier = "fit-selected-1"
    mock_cs = MagicMock(spec_set=["current_fit", "cs", "current_fit_idx", "fits"])
    type(mock_cs).current_fit = PropertyMock(return_value=None)
    mock_cs.current_fit_idx = -1
    type(mock_cs).cs = PropertyMock(return_value=None)
    mock_cs.fits = MagicMock()
    mock_cs.fits.selected = mock_fit

    state = SessionState(current_fit_uid=None)
    with patch.dict("sys.modules", {"chisurf": mock_cs}):
        startup_mod.sync_current_fit_uid_from_live_chisurf(state)
    assert state.current_fit_uid == "fit-selected-1"
