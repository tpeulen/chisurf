"""Regression tests for ChiSurf's dual-mode MMFDB client boundary."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest
import yaml


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_client_config_defaults_to_embedded_admin() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    config = client_config({})

    assert config == {
        "mode": "embedded",
        "username": "admin",
        "host": "127.0.0.1",
        "cmd_port": 8765,
        "pub_port": 8766,
        "base_url": "http://127.0.0.1:8080",
        "allow_insecure_http": False,
        "timeout_ms": 5000,
    }


def test_client_config_reads_explicit_remote_yaml_block() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import (
        client_config,
        credential_endpoint,
    )

    config = client_config(
        {
            "client": {
                "mode": "remote",
                "base_url": "https://mmfdb.example.test/root/",
                "username": "scientist",
                "timeout_ms": 9000,
            }
        }
    )

    assert config["mode"] == "remote"
    assert config["base_url"] == "https://mmfdb.example.test/root"
    assert config["username"] == "scientist"
    assert config["timeout_ms"] == 9000
    assert credential_endpoint(config) == ("mmfdb.example.test", 443)


def test_client_config_reuses_deployment_yaml_with_nested_override(tmp_path) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    deployment = tmp_path / "mmfdb.yaml"
    deployment.write_text(
        """
version: 1
mode: standalone
database:
  path: ./mmfdb.db
client:
  mode: remote
  base_url: http://mmfdb.internal:8080
  username: deployment-user
  allow_insecure_http: true
""",
        encoding="utf-8",
    )

    config = client_config(
        {
            "config_file": str(deployment),
            "default_user_id": "legacy-user",
            "client": {"username": "chisurf-user"},
        }
    )

    assert config["mode"] == "remote"
    assert config["base_url"] == "http://mmfdb.internal:8080"
    assert config["username"] == "chisurf-user"
    assert config["allow_insecure_http"] is True


def test_shipped_settings_allow_config_file_to_select_remote_mode(tmp_path) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    settings_path = (
        Path(__file__).resolve().parents[2]
        / "chisurf"
        / "core"
        / "settings"
        / "settings_chisurf.yaml"
    )
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))["mmfdb"]
    deployment = tmp_path / "mmfdb.yaml"
    deployment.write_text(
        "version: 1\nclient:\n  mode: remote\n"
        "  base_url: http://standalone:8080\n  username: admin\n"
        "  allow_insecure_http: true\n",
        encoding="utf-8",
    )
    settings["config_file"] = str(deployment)

    config = client_config(settings)

    assert config["mode"] == "remote"
    assert config["base_url"] == "http://standalone:8080"


def test_client_config_rejects_persisted_password() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    with pytest.raises(ValueError, match="password"):
        client_config({"client": {"mode": "remote", "password": "admin"}})


@pytest.mark.parametrize(
    "base_url",
    [
        "http://mmfdb.example.test:8080",
        "https://user:secret@mmfdb.example.test",
        "https://mmfdb.example.test?token=secret",
        "https://mmfdb.example.test#fragment",
    ],
)
def test_client_config_rejects_unsafe_remote_urls(base_url: str) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    with pytest.raises(ValueError):
        client_config({"client": {"mode": "remote", "base_url": base_url}})


def test_client_config_allows_explicit_insecure_remote_url() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import client_config

    config = client_config(
        {
            "client": {
                "mode": "remote",
                "base_url": "http://mmfdb.example.test:8080",
                "allow_insecure_http": True,
            }
        }
    )

    assert config["allow_insecure_http"] is True


def test_direct_remote_client_rejects_unsafe_url() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    with pytest.raises(ValueError, match="HTTPS"):
        MMFDBClient(mode="remote", base_url="http://mmfdb.example.test:8080")


def test_direct_remote_client_allows_explicit_insecure_url() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    client = MMFDBClient(
        mode="remote",
        base_url="http://mmfdb.example.test:8080",
        allow_insecure_http=True,
    )

    assert client.base_url == "http://mmfdb.example.test:8080"


def test_remote_client_posts_jsonrpc_and_uses_bearer_token(monkeypatch) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return _Response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"ok": True, "samples": [{"sample_id": "s1"}]},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = MMFDBClient(
        mode="remote",
        base_url="https://mmfdb.example.test/",
        timeout_ms=2500,
    )
    client.token = "secret-token"

    assert client.list_samples() == [{"sample_id": "s1"}]

    request, timeout = requests[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://mmfdb.example.test/rpc"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["Content-type"] == "application/json"
    assert payload == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "mmfdb.samples.list",
        "params": {},
    }
    assert timeout == 2.5


def test_explicit_embedded_mode_keeps_inprocess_test_transport() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    class Transport:
        def call(self, method, params):
            return {"result": {"ok": True, "method": method, "params": params}}

    transport = Transport()
    client = MMFDBClient(client=transport, mode="embedded")

    assert client.call("meta.ping") == {
        "ok": True,
        "method": "meta.ping",
        "params": {},
    }
    assert client.mode == "embedded"


def test_logout_sends_current_token_before_clearing_it() -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    calls = []

    class Transport:
        def call(self, method, params):
            calls.append((method, params))
            return {"result": {"ok": True}}

    client = MMFDBClient(client=Transport(), mode="embedded")
    client.token = "active-session-token"

    assert client.logout() == {"ok": True}
    assert calls == [
        (
            "mmfdb.security.auth.logout",
            {"auth": {"token": "active-session-token"}},
        )
    ]
    assert client.token is None


def test_remote_jsonrpc_error_is_not_treated_as_success(monkeypatch) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32001, "message": "Authentication required"},
            }
        ),
    )

    with pytest.raises(RuntimeError, match="Authentication required"):
        MMFDBClient(mode="remote").list_samples()


def test_remote_object_methods_use_binary_transport_without_json_base64(tmp_path) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    payload = (b"binary-object\x00" * 10_000) + b"tail"
    source = tmp_path / "trace.ptu"
    source.write_bytes(payload)

    class Transport:
        def __init__(self):
            self.upload = None

        def upload_object(self, stream, *, length, filename, mime_type, metadata, token):
            self.upload = {
                "chunks": iter(lambda: stream.read(65536), b""),
                "length": length,
                "filename": filename,
                "mime_type": mime_type,
                "metadata": metadata,
                "token": token,
            }
            self.upload["data"] = b"".join(self.upload.pop("chunks"))
            return {"ok": True, "object": {"object_uuid": "obj-1"}}

        def download_object(self, object_uuid, *, token):
            assert object_uuid == "obj-1"
            assert token == "session-token"
            return payload

    transport = Transport()
    client = MMFDBClient(client=transport, mode="remote")
    client.token = "session-token"

    uploaded = client.put_object(
        path=str(source), mime_type="application/octet-stream", metadata={"run": 7}
    )
    assert uploaded["object"]["object_uuid"] == "obj-1"
    assert transport.upload == {
        "length": len(payload),
        "filename": "trace.ptu",
        "mime_type": "application/octet-stream",
        "metadata": {"run": 7},
        "token": "session-token",
        "data": payload,
    }
    downloaded = client.get_object("obj-1")
    assert base64.b64decode(downloaded["data"]) == payload


def test_remote_object_transfer_refuses_to_send_before_login(tmp_path) -> None:
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

    source = tmp_path / "private.bin"
    source.write_bytes(b"must-not-be-sent")

    class Transport:
        def upload_object(self, *_args, **_kwargs):
            raise AssertionError("transport must not be opened without a token")

        def download_object(self, *_args, **_kwargs):
            raise AssertionError("transport must not be opened without a token")

    client = MMFDBClient(client=Transport(), mode="remote")

    with pytest.raises(RuntimeError, match="Login required"):
        client.put_object(path=str(source))
    with pytest.raises(RuntimeError, match="Login required"):
        client.get_object("object-id")


def test_http_binary_transport_sends_bounded_chunks_and_bearer(monkeypatch):
    from chisurf.plugins.core.mmfdb_admin.gui.client import _HttpJsonRpcClient

    payload = b"x" * 200_000
    connections = []

    class Response:
        status = 201
        reason = "Created"

        def read(self, _size=-1):
            return b'{"ok":true,"object":{"object_uuid":"obj-2"}}'

    class Connection:
        def __init__(self, host, port=None, timeout=None):
            self.host, self.port, self.timeout = host, port, timeout
            self.headers = {}
            self.sent = []
            connections.append(self)

        def putrequest(self, method, path):
            self.method, self.path = method, path

        def putheader(self, key, value):
            self.headers[key] = str(value)

        def endheaders(self):
            pass

        def send(self, data):
            self.sent.append(bytes(data))

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("http.client.HTTPSConnection", Connection)
    client = _HttpJsonRpcClient("https://mmfdb.example.test/api", 2500)

    result = client.upload_object(
        io.BytesIO(payload),
        length=len(payload),
        filename="trace file.ptu",
        mime_type="application/octet-stream",
        metadata={"run": 8},
        token="secret",
    )

    connection = connections[0]
    assert result["object"]["object_uuid"] == "obj-2"
    assert connection.method == "POST"
    assert connection.path == "/api/objects"
    assert connection.headers["Authorization"] == "Bearer secret"
    assert connection.headers["Content-Length"] == str(len(payload))
    assert connection.headers["X-MMFDB-Filename"] == "trace%20file.ptu"
    assert b"".join(connection.sent) == payload
    assert len(connection.sent) > 1


def test_http_binary_download_reads_bounded_chunks_and_bearer(monkeypatch):
    from chisurf.plugins.core.mmfdb_admin.gui.client import _HttpJsonRpcClient

    payload = b"download" * 30_000
    connections = []

    class Response:
        status = 200
        reason = "OK"

        def __init__(self):
            self.stream = io.BytesIO(payload)
            self.read_sizes = []

        def getheader(self, name):
            return str(len(payload)) if name == "Content-Length" else None

        def read(self, size=-1):
            self.read_sizes.append(size)
            return self.stream.read(size)

    class Connection:
        def __init__(self, *_args, **_kwargs):
            self.headers = {}
            self.response = Response()
            connections.append(self)

        def putrequest(self, method, path):
            self.method, self.path = method, path

        def putheader(self, key, value):
            self.headers[key] = str(value)

        def endheaders(self):
            pass

        def getresponse(self):
            return self.response

        def close(self):
            pass

    monkeypatch.setattr("http.client.HTTPConnection", Connection)
    client = _HttpJsonRpcClient(
        "http://mmfdb.example.test/root",
        1000,
        allow_insecure_http=True,
    )

    result = client.download_object("object id", token="secret")

    connection = connections[0]
    assert result == payload
    assert connection.method == "GET"
    assert connection.path == "/root/objects/object%20id"
    assert connection.headers["Authorization"] == "Bearer secret"
    assert len(connection.response.read_sizes) > 1
    assert max(connection.response.read_sizes) <= 64 * 1024
