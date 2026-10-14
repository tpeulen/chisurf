"""``region-mle serve`` puts the plugin's RPC services behind a ZMQ server.

The command used to call ``ServiceDispatcher.serve``, which does not exist, so
it failed every time it was run.
"""

from __future__ import annotations

from typing import Any

from click.testing import CliRunner


def test_serve_hands_every_request_to_the_dispatcher(monkeypatch) -> None:
    """The ZMQ server gets the requested ports and a handler that reaches the services."""
    from chisurf.plugins.microscopy.region_mle.cli.main import cli
    from chisurf.server.transport import zmq as transport

    seen: dict[str, Any] = {}

    class _Server:
        def __init__(self, handler, cmd_port, pub_port, host) -> None:
            seen.update(handler=handler, cmd_port=cmd_port, pub_port=pub_port, host=host)

        def serve_forever(self) -> None:
            seen["served"] = True

    monkeypatch.setattr(transport, "ZmqServer", _Server)
    result = CliRunner().invoke(cli, ["serve", "--host", "127.0.0.1", "--port", "6123"])

    assert result.exit_code == 0, result.output
    assert seen["served"] is True
    assert (seen["cmd_port"], seen["pub_port"], seen["host"]) == (6123, 6124, "127.0.0.1")
    reply = seen["handler"]("region_mle.no_such_method", None)
    assert reply.get("ok") is False  # answered by the dispatcher, not raised
