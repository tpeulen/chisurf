"""The in-tree HTTP client, exercised against a real local server.

``chisurf.core.http`` replaced a third-party client that nothing declared, so
these tests pin the behaviour the call sites rely on: JSON round trips, query
parameters, an error status arriving as a *response* rather than an exception,
and a transport failure arriving as one.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading

import pytest

from chisurf.core import http as client


class _Handler(http.server.BaseHTTPRequestHandler):
    """Echo requests back as JSON so the test can assert what was sent."""

    def log_message(self, *args):
        """Silence the default stderr logging."""

    def _reply(self, status: int, payload: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("retry-after", "7")  # lower case on purpose
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        """Echo the path, or fail on ``/bad``, or return bytes on ``/blob``."""
        if self.path.startswith("/bad"):
            self._reply(404, b'{"error": "nope"}', "application/json")
        elif self.path.startswith("/blob"):
            self._reply(200, bytes(range(8)), "application/octet-stream")
        else:
            body = json.dumps(
                {"path": self.path, "agent": self.headers.get("User-Agent")}
            ).encode()
            self._reply(200, body, "application/json; charset=utf-8")

    def do_POST(self):
        """Echo the JSON body and the headers that carried it."""
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(
            {
                "echo": payload,
                "content_type": self.headers.get("Content-Type"),
                "authorization": self.headers.get("Authorization"),
            }
        ).encode()
        self._reply(200, body, "application/json")


@pytest.fixture(scope="module")
def server_url():
    """Serve :class:`_Handler` on a free port for the duration of the module."""
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_get_returns_parsed_json_and_sends_a_user_agent(server_url):
    response = client.get(server_url + "/models", timeout=10)
    assert response.status_code == 200
    assert response.ok
    assert response.json() == {"path": "/models", "agent": client.USER_AGENT}


def test_query_parameters_are_encoded(server_url):
    response = client.get(server_url + "/models", params={"a": 1, "b": "c d"}, timeout=10)
    assert response.json()["path"] == "/models?a=1&b=c+d"


def test_post_sends_json_with_headers(server_url):
    response = client.post(
        server_url + "/chat",
        headers={"Authorization": "Bearer secret"},
        json={"model": "m", "messages": []},
        timeout=10,
    )
    body = response.json()
    assert body["echo"] == {"model": "m", "messages": []}
    assert body["content_type"] == "application/json"
    assert body["authorization"] == "Bearer secret"


def test_error_status_is_a_response_not_an_exception(server_url):
    response = client.get(server_url + "/bad", timeout=10)
    assert response.status_code == 404
    assert not response.ok
    assert response.json() == {"error": "nope"}
    with pytest.raises(client.HTTPStatusError):
        response.raise_for_status()


def test_raise_for_status_returns_the_response_when_fine(server_url):
    response = client.get(server_url + "/models", timeout=10)
    assert response.raise_for_status() is response


def test_headers_are_case_insensitive(server_url):
    response = client.get(server_url + "/models", timeout=10)
    assert response.headers.get("Retry-After") == "7"
    assert response.headers["RETRY-AFTER"] == "7"
    assert "retry-after" in response.headers
    assert response.headers.get("nothing-here") is None


def test_binary_body_is_returned_as_bytes(server_url):
    response = client.get(server_url + "/blob", timeout=10)
    assert response.content == bytes(range(8))


def test_transport_failure_raises_request_error():
    with pytest.raises(client.RequestError):
        client.get("http://127.0.0.1:1/never", timeout=5)


def test_json_and_data_together_are_rejected(server_url):
    with pytest.raises(ValueError):
        client.post(server_url + "/chat", json={"a": 1}, data=b"raw", timeout=10)
