"""Actual separate-process owner policy and one-use ZMQ project transactions."""

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import chisurf as cs
from chisurf.core.api import ChiSurfAPI
from chisurf.core.api._client import ChisurfClient, RemoteError
from chisurf.core.project import capture_session
from chisurf.core.project.lifecycle import ProjectDocument
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.transition import _authorization_scope
from chisurf.server.session import SessionState
from test.server.helpers import find_free_port


def test_separate_process_gui_operation_requires_preapproved_owner_scope(monkeypatch, tmp_path):
    """Real RPC may consume bootstrap-approved authority, never a client assertion."""
    incoming = capture_session([], [], name="owner-approved resource-only operation")
    incoming.resources = ResourceContext({"attachments/owned.pdb": b"owned exact bytes"})
    approved = _authorization_scope(incoming, None)
    command_port, publication_port = find_free_port(), find_free_port()
    ready = tmp_path / "ready"
    script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[5])
from chisurf.server.app import ChiSurfServer
from chisurf.core.project.transition import _authorization_scope
sys.path.insert(0, sys.argv[5])
from test.project.test_server_project_snapshot import _state_with_real_fit
state = _state_with_real_fit()
state._project_gui_required = True
# The actual application bootstrap preapproves one exact operation. Network
# callers cannot configure this policy or mint authority for another snapshot.
state._project_transition_policy = lambda project, path: _authorization_scope(project, path) == sys.argv[4]
server = ChiSurfServer(cmd_port=int(sys.argv[1]), pub_port=int(sys.argv[2]), state=state)
Path(sys.argv[3]).write_text('ready')
server.serve_forever()
"""
    env = os.environ.copy()
    env["CHISURF_SETTINGS_DIR"] = str(tmp_path / "settings")
    env["MMFDB_SETTINGS_DIR"] = str(tmp_path / "mmfdb")
    client = None
    with (tmp_path / "server.log").open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(command_port),
                str(publication_port),
                str(ready),
                approved,
                str(Path(__file__).resolve().parents[2]),
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert ready.exists(), (tmp_path / "server.log").read_text()
            client = ChisurfClient(cmd_port=command_port, pub_port=publication_port)
            client.connect()
            original = client.call("project.capture")
            with pytest.raises(RemoteError, match="Service error"):
                client.call(
                    "project.transition.begin",
                    {
                        "project": capture_session([], [], name="unapproved").to_dict(),
                    },
                )
            assert (
                client.call("project.capture")["project"]["datasets"]
                == original["project"]["datasets"]
            )
            calls = []
            document = ProjectDocument(name="original")
            gui = SimpleNamespace(
                _guard_project_transition=lambda: calls.append("guard") or True,
                _get_project_document=lambda: document,
            )
            monkeypatch.setattr(cs, "cs", gui)
            state = SessionState()
            state._project_gui = gui
            api = ChiSurfAPI(mode="server", client=client, state=state)
            api.install_proxies()
            result = api.restore_project_payload(incoming)
            assert result["ok"] is True, result
            assert calls == ["guard"]
            captured = api.capture_project()
            assert captured.resources.entries == incoming.resources.entries
            assert captured.resources.sources == incoming.resources.sources
            assert captured.fits == []
            assert captured.datasets == {}
            assert document.name == incoming.name
            with pytest.raises(RemoteError, match="owning GUI"):
                client.call(
                    "project.restore_payload",
                    {
                        "project": incoming.to_dict(),
                        "resources": incoming.resources.to_transport_dict(),
                    },
                )
            assert api.capture_project().resources.entries == incoming.resources.entries
            # Exact project policy also protects public/direct registered paths.
            rejected = api.restore_project_payload(
                capture_session([], [], name="another operation")
            )
            assert rejected == {"ok": False, "cancelled": True}
            assert api.capture_project().resources.entries == incoming.resources.entries
        finally:
            if client is not None:
                client.close()
            process.terminate()
            process.wait(timeout=10)
