from __future__ import annotations

import concurrent.futures

from chisurf.server.protocol import (
    PROTOCOL_VERSION,
    METHOD_CATALOGUE,
    METHOD_PARAM_SCHEMAS,
    METHOD_SCHEMAS,
    NAMESPACE_DESCRIPTIONS,
    load_method_specs,
    encode_request,
    decode_request,
    encode_response,
    decode_response,
    encode_error,
    is_valid_request,
    is_valid_response,
    _next_id,
)


class TestProtocol:
    """JSON-RPC protocol helpers."""

    def test_encode_request_minimal(self):
        msg = encode_request(method="ping")
        assert isinstance(msg, dict)
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "ping"
        assert "params" not in msg
        assert "id" in msg

    def test_encode_request_with_params(self):
        msg = encode_request(method="fit.run", params={"fit_index": 0})
        assert msg["method"] == "fit.run"
        assert msg["params"] == {"fit_index": 0}

    def test_encode_request_with_id(self):
        msg = encode_request(method="test", request_id=42)
        assert msg["id"] == 42

    def test_decode_request(self):
        raw = {"jsonrpc": "2.0", "method": "fit.run", "params": {"i": 0}, "id": 1}
        method, params, req_id = decode_request(raw)
        assert method == "fit.run"
        assert params == {"i": 0}
        assert req_id == 1

    def test_decode_request_no_params(self):
        raw = {"jsonrpc": "2.0", "method": "ping", "id": 1}
        method, params, req_id = decode_request(raw)
        assert method == "ping"
        assert params == {}
        assert req_id == 1

    def test_decode_request_missing_method(self):
        raw = {"jsonrpc": "2.0", "id": 1}
        result = decode_request(raw)
        assert result is None

    def test_encode_response(self):
        msg = encode_response(result={"ok": True}, request_id=1)
        assert msg["jsonrpc"] == "2.0"
        assert msg["result"] == {"ok": True}
        assert msg["id"] == 1
        assert "error" not in msg

    def test_encode_response_no_id(self):
        msg = encode_response(result=None)
        assert msg["id"] is None

    def test_decode_response(self):
        raw = {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
        result, error, req_id = decode_response(raw)
        assert result == {"ok": True}
        assert error is None
        assert req_id == 1

    def test_decode_response_with_error(self):
        raw = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": 1}
        result, error, req_id = decode_response(raw)
        assert result is None
        assert error["code"] == -32601
        assert error["message"] == "Method not found"

    def test_encode_error(self):
        msg = encode_error(code=-32601, message="Method not found", request_id=1)
        assert msg["jsonrpc"] == "2.0"
        assert msg["error"]["code"] == -32601
        assert msg["error"]["message"] == "Method not found"
        assert msg["id"] == 1

    def test_encode_error_with_data(self):
        msg = encode_error(code=-32603, message="Internal error", data={"detail": "x"}, request_id=5)
        assert msg["error"]["data"] == {"detail": "x"}

    def test_is_valid_request_good(self):
        assert is_valid_request({"jsonrpc": "2.0", "method": "ping", "id": 1})

    def test_is_valid_request_bad(self):
        assert not is_valid_request({"method": "ping"})
        assert not is_valid_request({"jsonrpc": "2.0", "id": 1})
        assert not is_valid_request({})
        assert not is_valid_request(None)
        assert not is_valid_request("not a dict")

    def test_is_valid_response_good(self):
        assert is_valid_response({"jsonrpc": "2.0", "result": {}, "id": 1})
        assert is_valid_response({"jsonrpc": "2.0", "error": {"code": 0, "message": ""}, "id": 1})

    def test_is_valid_response_bad(self):
        assert not is_valid_response({})
        assert not is_valid_response({"jsonrpc": "2.0", "id": 1})
        assert not is_valid_response(None)

    def test_round_trip_request(self):
        req = encode_request(method="dataset.add", params={"filename": "test.ptu"})
        method, params, req_id = decode_request(req)
        assert method == "dataset.add"
        assert params == {"filename": "test.ptu"}
        assert req_id == req["id"]

    def test_round_trip_response(self):
        resp = encode_response(result={"ok": True}, request_id=7)
        result, error, req_id = decode_response(resp)
        assert result == {"ok": True}
        assert error is None
        assert req_id == 7


class TestProtocolConstants:

    def test_protocol_version_is_string(self):
        assert isinstance(PROTOCOL_VERSION, str)
        assert len(PROTOCOL_VERSION) > 0

    def test_method_catalogue_covers_exactly_the_registered_methods(self):
        """The advertised catalogue is the registry — no missing, no phantom methods."""
        registered = {spec["rpc"] for spec in load_method_specs()}
        catalogued = {m for ns in METHOD_CATALOGUE.values() for m in ns["methods"]}
        assert catalogued == registered

    def test_method_catalogue_has_all_namespaces(self):
        expected = {
            "meta", "dataset", "fit", "parameter", "project", "session", "model",
            "graph", "log", "editor", "detector_setups", "flr", "plot", "pda",
            # A gated burst population, handed to another analysis.
            "tcspc", "pch", "bursts",
        }
        assert set(METHOD_CATALOGUE.keys()) == expected

    def test_every_namespace_carries_a_written_description(self):
        """A new namespace must be given prose, not the generated placeholder."""
        for namespace, info in METHOD_CATALOGUE.items():
            assert namespace in NAMESPACE_DESCRIPTIONS
            assert info["description"] == NAMESPACE_DESCRIPTIONS[namespace]

    def test_method_catalogue_methods_are_strings(self):
        for ns, info in METHOD_CATALOGUE.items():
            assert "description" in info
            assert "methods" in info
            for m in info["methods"]:
                assert isinstance(m, str)
                # ``list_methods`` is the one deliberately un-namespaced survivor.
                assert m.startswith(ns + ".") or m == "list_methods"

    def test_method_schemas_only_describe_registered_methods(self):
        registered = {spec["rpc"] for spec in load_method_specs()}
        assert set(METHOD_SCHEMAS.keys()) <= registered

    def test_method_schema_events_come_from_the_registry(self):
        """Schema event topics are derived, so they cannot drift from the registry."""
        declared = {spec["rpc"]: list(spec.get("events", [])) for spec in load_method_specs()}
        for method, schema in METHOD_SCHEMAS.items():
            assert schema["events"] == declared[method]

    def test_param_schemas_do_not_hand_repeat_events(self):
        for method, schema in METHOD_PARAM_SCHEMAS.items():
            assert "events" not in schema, f"{method} re-declares events by hand"

    def test_method_schema_shape(self):
        for method, schema in METHOD_SCHEMAS.items():
            assert isinstance(method, str)
            assert isinstance(schema["required_params"], list)
            assert isinstance(schema["optional_params"], list)
            assert isinstance(schema["result"], str)
            assert isinstance(schema["events"], list)


class TestNextId:

    def test_next_id_increments(self):
        a = _next_id()
        b = _next_id()
        c = _next_id()
        assert a < b < c

    def test_next_id_thread_safe(self):
        results = set()
        def collect():
            results.add(_next_id())
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(collect) for _ in range(50)]
            concurrent.futures.wait(futures)
        assert len(results) == 50
