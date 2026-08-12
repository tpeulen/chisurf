"""End-to-end lifecycle and edge-case tests through ZMQ proxy/client.

Uses a single shared server + client (module-scoped) to minimize ZMQ
socket conflicts.  Each test resets server state via the shared client.
"""

import json
import math
import os
import threading
import time
import tempfile

import pytest

from chisurf.core.api._client import ChisurfClient, RemoteError
from chisurf.server.app import ChiSurfServer
from chisurf.core.api._proxies import ProxyFitList, ProxyDatasetList
from test.server.helpers import find_free_port

#: A model the server can actually build. "TCSPC" is the name of the
#: *experiment*, never of a model, so every fit created with it failed with
#: "model 'TCSPC' not found" and the tests that depend on one skipped or failed.
TCSPC_MODEL = "Lifetime"


# ── Shared server + client (module-scoped) ──────────────────────

_SERVER: ChiSurfServer = None
_CLIENT: ChisurfClient = None
_PORTS: tuple = None
_LOCK = threading.Lock()


def _client() -> ChisurfClient:
    """Get the module-scoped shared client (lazy-init)."""
    global _SERVER, _CLIENT, _PORTS
    if _CLIENT is not None:
        return _CLIENT
    with _LOCK:
        if _CLIENT is not None:
            return _CLIENT
        cmd = find_free_port()
        pub = find_free_port()
        _PORTS = (cmd, pub)
        _SERVER = ChiSurfServer(cmd_port=cmd, pub_port=pub)
        t = threading.Thread(target=_SERVER.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        _CLIENT = ChisurfClient(cmd_port=cmd, pub_port=pub)
        _CLIENT.connect()
        return _CLIENT


def _reset():
    """Reset server state (clear datasets + fits)."""
    c = _client()
    try:
        c.fit__clear()
    except Exception:
        pass
    try:
        c.dataset__clear()
    except Exception:
        pass


#: A decay long enough to fit. The two-point curve this used to send made every
#: dataset unusable as soon as a fit was actually *run* over it: the optimiser
#: rejects a window narrower than the number of free parameters with
#: ``Improper input: N=4 must not exceed M=(1,)``.
_N_POINTS = 64
_DEFAULT_X = tuple(float(i) for i in range(_N_POINTS))
_DEFAULT_Y = tuple(1000.0 * math.exp(-i / 8.0) + 5.0 for i in range(_N_POINTS))


def _add_ds(c, name="TestDS", x=_DEFAULT_X, y=_DEFAULT_Y):
    return c.call("dataset.load", {
        "reader_name": f"{name}R", "filename": f"/tmp/{name}.dat",
        "name": name, "curve_data": {"x": list(x), "y": list(y)},
    })


@pytest.fixture(autouse=True)
def reset_state():
    _reset()
    yield


@pytest.fixture
def client():
    return _client()


# ── 1. Full lifecycle through proxy objects ─────────────────────


class TestProxyLifecycle:

    def test_add_dataset_through_proxy(self, client):
        dlist = ProxyDatasetList(client)
        assert len(dlist) == 0
        _add_ds(client, "ProxyDS1")
        dlist._invalidate()
        assert len(dlist) == 1
        assert dlist[0].name == "ProxyDS1"

    def test_add_fit_through_proxy(self, client):
        flist = ProxyFitList(client)
        assert len(flist) == 0
        _add_ds(client, "PFitDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist._invalidate()
        assert len(flist) == 1
        assert flist[0].chi2 is not None

    def test_run_fit_through_proxy(self, client):
        _add_ds(client, "RunProxy")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        result = fit.run()
        assert isinstance(result, dict)

    def test_proxy_pop_through_server(self, client):
        _add_ds(client, "PopDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        assert len(flist) == 1
        popped = flist.pop(0)
        assert popped.uid == ft["uid"]
        flist._invalidate()
        assert len(flist) == 0

    def test_proxy_clear_through_server(self, client):
        _add_ds(client, "ClrDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        flist.clear()
        flist._invalidate()
        assert len(flist) == 0

    def test_proxy_iterate_enumerate(self, client):
        _add_ds(client, "EnumDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        for _idx, fit in enumerate(flist):
            assert fit.uid == ft["uid"]

    def test_proxy_dataset_cache_invalidation(self, client):
        dlist = ProxyDatasetList(client)
        assert len(dlist) == 0
        _add_ds(client, "Cache1", x=(0.0,), y=(1.0,))
        dlist._invalidate()
        assert len(dlist) == 1
        _add_ds(client, "Cache2", x=(0.0,), y=(2.0,))
        dlist._invalidate()
        assert len(dlist) == 2

    def test_proxy_fit_getitem(self, client):
        _add_ds(client, "GetItem")
        ft1 = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        ft2 = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft1.get("ok") or not ft2.get("ok"):
            pytest.skip("fit__create not available")
        flist = ProxyFitList(client)
        assert flist[0].uid == ft1["uid"]
        assert flist[1].uid == ft2["uid"]


# ── 2. Large payload tests ──────────────────────────────────────


class TestLargePayload:

    def test_large_10k(self, client):
        n = 10_000
        r = _add_ds(client, "L10k", range(n), [float(i * i) for i in range(n)])
        assert r.get("ok") is True
        di = r["dataset_index"]
        assert client.dataset__get(dataset_index=di)["length"] == n
        curve = client.dataset__curve_data(dataset_index=di)
        assert len(curve["x"]) == n
        assert curve["x"][-1] == float(n - 1)

    def test_large_100k(self, client):
        n = 100_000
        x = [float(i) for i in range(n)]
        y = [math.sin(i * 0.001) for i in range(n)]
        r = client.call("dataset.load", {
            "reader_name": "L100kR", "filename": "/tmp/l100k.dat",
            "name": "L100k",
            "curve_data": {"x": x, "y": y},
        })
        assert r.get("ok") is True
        curve = client.dataset__curve_data(dataset_index=r["dataset_index"])
        assert len(curve["x"]) == n
        assert abs(curve["y"][50000] - math.sin(50.0)) < 1e-10

    def test_large_with_nan(self, client):
        n = 1000
        x = list(range(n))
        y = [float("nan") if i % 100 == 0 else float(i) for i in range(n)]
        r = _add_ds(client, "NanLg", x, y)
        assert r.get("ok") is True
        curve = client.dataset__curve_data(dataset_index=r["dataset_index"])
        # NaN/Inf values are sanitized to None for JSON safety
        assert curve["y"][0] is None
        assert curve["y"][100] is None
        assert curve["y"][1] == 1.0

    def test_fifty_datasets(self, client):
        for i in range(50):
            _add_ds(client, f"Fifty{i}", (0.0, 1.0), (float(i), float(i + 1)))
        assert len(client.dataset__list()) == 50

    def test_ten_fits(self, client):
        _add_ds(client, "TenFit")
        created = 0
        for _ in range(10):
            ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
            if ft.get("ok"):
                created += 1
        if created == 0:
            pytest.skip("fit__create not available")
        assert len(client.fit__list()) == created


# ── 3. Client resilience ────────────────────────────────────────


class TestClientResilience:

    def test_ping_ok(self, client):
        r = client.meta__ping()
        assert r.get("ok") is True
        assert r.get("status") == "alive"

    def test_timeout_raises_remote_error(self):
        cmd = find_free_port()
        pub = find_free_port()
        c = ChisurfClient(cmd_port=cmd, pub_port=pub, timeout_ms=100)
        c.connect()
        with pytest.raises(RemoteError):
            c.meta__ping()
        c.close()

    def test_second_client(self, client):
        """Multiple clients can connect to the shared server."""
        cmd, pub = _PORTS
        c2 = ChisurfClient(cmd_port=cmd, pub_port=pub)
        c2.connect()
        assert c2.meta__ping().get("ok") is True
        c2.close()

    def test_five_concurrent_clients(self, client):
        cmd, pub = _PORTS
        clients = [ChisurfClient(cmd_port=cmd, pub_port=pub) for _ in range(5)]
        for c in clients:
            c.connect()
            assert c.meta__ping().get("ok") is True
            c.close()

    def test_send_after_close_raises(self, client):
        cmd, pub = _PORTS
        c = ChisurfClient(cmd_port=cmd, pub_port=pub)
        c.connect()
        c.close()
        with pytest.raises(Exception):
            c.meta__ping()

    def test_sequential_reconnect(self, client):
        cmd, pub = _PORTS
        for _ in range(3):
            c = ChisurfClient(cmd_port=cmd, pub_port=pub)
            c.connect()
            assert c.meta__ping().get("ok") is True
            c.close()


# ── 4. Parameter bounds / linkage lifecycle ─────────────────────


class TestParameterLifecycle:

    def _setup(self, client):
        _add_ds(client, "Param")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        info = client.fit__get(fit_index=ft["fit_index"])
        params = info.get("model", {}).get("parameters_all", [])
        if not params:
            pytest.skip("no parameters")
        return ft, params

    def test_set_value(self, client):
        ft, params = self._setup(client)
        p = params[0]["name"]
        assert client.parameter__set_value(p, 42.0, fit_index=ft["fit_index"]).get("ok")
        info = client.fit__get(fit_index=ft["fit_index"])
        for par in info["model"]["parameters_all"]:
            if par["name"] == p:
                assert par["value"] == 42.0
                return
        pytest.fail(f"param {p} not found")

    def test_set_fixed(self, client):
        ft, params = self._setup(client)
        p = params[0]["name"]
        assert client.parameter__set_fixed(p, True, fit_index=ft["fit_index"]).get("ok")
        info = client.fit__get(fit_index=ft["fit_index"])
        for par in info["model"]["parameters_all"]:
            if par["name"] == p:
                assert par["fixed"] is True
                return

    def test_set_bounds(self, client):
        ft, params = self._setup(client)
        p = params[0]["name"]
        # Two RPCs on purpose: `parameter.set_bounds` carries the interval and
        # `parameter.set_bounds_on` decides whether it is enforced. The client
        # rejects unknown keywords, so the `bounds_on=True` this used to pass
        # never reached the server -- it raised TypeError before sending.
        r = client.parameter__set_bounds(p, 0.0, 100.0, fit_index=ft["fit_index"])
        assert r.get("ok") is True
        assert client.parameter__set_bounds_on(p, True, fit_index=ft["fit_index"]).get("ok")
        info = client.fit__get(fit_index=ft["fit_index"])
        for par in info["model"]["parameters_all"]:
            if par["name"] == p:
                assert par["bounds"] == [0.0, 100.0]
                assert par["bounds_on"] is True
                return

    def test_link_then_unlink(self, client):
        ft, params = self._setup(client)
        if len(params) < 2:
            pytest.skip("need 2+ params")
        assert client.parameter__link(params[0]["name"], params[1]["name"], fit_index=ft["fit_index"]).get("ok")
        assert client.parameter__unlink(params[0]["name"], fit_index=ft["fit_index"]).get("ok")

    def test_linked_info(self, client):
        ft, params = self._setup(client)
        if len(params) < 2:
            pytest.skip("need 2+ params")
        client.parameter__link(params[0]["name"], params[1]["name"], fit_index=ft["fit_index"])
        # ``parameter.get`` declares ``result_key: "parameter"``, so the client
        # returns the parameter payload itself -- there is no "ok" envelope to
        # read, and asserting on one only ever saw ``None``.
        pinfo = client.parameter__get(params[0]["name"], fit_index=ft["fit_index"])
        assert pinfo.get("name") == params[0]["name"]
        assert pinfo.get("linked_to") is not None


# ── 5. High-frequency / stress ──────────────────────────────────


class TestHighFrequency:

    def test_rapid_dataset_add(self, client):
        for i in range(50):
            _add_ds(client, f"R{i}", (0.0,), (float(i),))
        assert len(client.dataset__list()) == 50

    def test_rapid_fit_create_remove(self, client):
        _add_ds(client, "RFit")
        indices = []
        for _ in range(20):
            ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
            if ft.get("ok"):
                indices.append(ft["fit_index"])
        if not indices:
            pytest.skip("fit__create not available")
        for idx in reversed(indices):
            assert client.fit__remove(fit_indices=[idx]).get("ok") is True
        assert len(client.fit__list()) == 0

    def test_interleaved_fit_add_remove(self, client):
        _add_ds(client, "Inter")
        indices = []
        for i in range(10):
            ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
            if ft.get("ok"):
                indices.append(ft["fit_index"])
            if i >= 3 and indices:
                client.fit__remove(fit_indices=[indices.pop(0)])
        if not indices:
            pytest.skip("fit__create not available")

    def test_inprocess_bus_1000(self):
        from chisurf.server.eventbus import InProcessEventBus
        bus = InProcessEventBus()
        seen = []
        bus.subscribe("t", lambda e: seen.append(e))
        for i in range(1000):
            bus.publish("t", {"i": i})
        assert len(seen) == 1000
        assert seen[999]["i"] == 999

    def test_inprocess_bus_wildcard_500(self):
        from chisurf.server.eventbus import InProcessEventBus
        bus = InProcessEventBus()
        seen = []
        bus.subscribe("a.*", lambda e: seen.append(e))
        for i in range(500):
            bus.publish(f"a.{i}", {"i": i})
        assert len(seen) == 500


# ── 6. Error boundary ───────────────────────────────────────────


class TestErrorBoundary:
    """A failing call raises, it does not return ``{"ok": False}``.

    Service errors are carried in the JSON-RPC ``error`` member and
    :meth:`ChisurfClient.call` turns them into :class:`RemoteError`; only a
    *transport* failure ever produced the ``ok: False`` dict these tests were
    written against. Asserting ``not result.get("ok")`` therefore never
    described the contract: it passed on any successful call too, because a
    result payload has no ``"ok"`` key either.
    """

    def test_unknown_method(self, client):
        with pytest.raises(RemoteError, match="not found"):
            client.call("does.not.exist")

    def test_none_index(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": None})

    def test_string_index(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": "abc"})

    def test_list_index(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": [1, 2, 3]})

    def test_missing_param(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {})

    def test_out_of_range(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": 99999})

    def test_negative_index(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": -1})

    def test_nan_in_param(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": float("nan")})

    def test_inf_in_param(self, client):
        with pytest.raises(RemoteError):
            client.call("dataset.get", {"dataset_index": float("inf")})

    def test_nested_extra_param(self, client):
        """meta.ping accepts ping calls with extra params stripped."""
        r = client.call("meta.ping", {})
        assert r.get("ok") is True

    def test_binary_data_raises(self, client):
        with pytest.raises(Exception):
            client.call("meta.ping", {"data": b"\xff"})

    def test_double_call(self, client):
        assert client.meta__ping().get("ok") is True
        assert client.meta__ping().get("ok") is True


# ── 7. Session save/load ────────────────────────────────────────


class TestSessionSaveLoad:

    def test_save_empty(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            r = client.project__save(target_path=tmp)
            assert r.get("ok") is True
            pf = os.path.join(tmp, "project.json")
            assert os.path.isfile(pf)
            data = json.load(open(pf))
            assert "project_format_version" in data
            assert data["datasets"] == {}

    def test_save_with_dataset(self, client):
        _add_ds(client, "SaveDS")
        with tempfile.TemporaryDirectory() as tmp:
            r = client.project__save(target_path=tmp)
            assert r.get("ok") is True
            data = json.load(open(os.path.join(tmp, "project.json")))
            assert len(data["datasets"]) > 0

    def test_project_info(self, client):
        info = client.project__info()
        assert "dataset_count" in info
        assert "fit_count" in info

    def test_session_restore(self, client):
        assert client.session__restore().get("ok") is True
        assert client.session__describe().get("fit_count") == 0


# ── 8. Special float serialization ──────────────────────────────


class TestSpecialFloats:

    def test_nan_via_curve_data(self, client):
        r = _add_ds(client, "NaNCD", (float("nan"), 1.0), (2.0, float("nan")))
        assert r.get("ok") is True
        curve = client.dataset__curve_data(dataset_index=r["dataset_index"])
        assert curve.get("ok") is True
        # NaN/Inf values are sanitized to None for JSON safety
        assert curve["x"][0] is None
        assert curve["y"][1] is None
        assert curve["x"][1] == 1.0
        assert curve["y"][0] == 2.0

    def test_inf_via_curve_data(self, client):
        r = _add_ds(client, "InfCD", (float("inf"), 1.0), (2.0, float("-inf")))
        assert r.get("ok") is True
        curve = client.dataset__curve_data(dataset_index=r["dataset_index"])
        # Inf values are sanitized to None for JSON safety
        assert curve["x"][0] is None
        assert curve["y"][1] is None
        assert curve["x"][1] == 1.0
        assert curve["y"][0] == 2.0


# ── 9. ZMQ event patterns ───────────────────────────────────────


class TestZmqEvents:
    """Each test creates its own server+client to avoid ZMQ SUB filter bleed."""

    @pytest.fixture
    def zmq_pair(self):
        cmd = find_free_port()
        pub = find_free_port()
        srv = ChiSurfServer(cmd_port=cmd, pub_port=pub)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        cl = ChisurfClient(cmd_port=cmd, pub_port=pub)
        cl.connect()
        yield cl, srv
        cl.close()
        srv.stop()

    def test_empty_string_receives_all(self, zmq_pair):
        cl, srv = zmq_pair
        received = []
        def h(e):
            received.append(e)
        cl.subscribe(topic="", callback=h)
        time.sleep(0.3)
        cl.call("dataset.load", {
            "reader_name": "AllR", "filename": "/tmp/all.dat",
            "name": "AllDS",
            "curve_data": {"x": [0.0], "y": [1.0]},
        })
        time.sleep(0.5)
        cl.drain()
        assert len(received) > 0, f"got: {received}"

    def test_topic_filter(self, zmq_pair):
        cl, srv = zmq_pair
        received = []
        def h(e):
            received.append(e)
        cl.subscribe(topic="fit.ran", callback=h)
        time.sleep(0.3)
        cl.call("dataset.load", {
            "reader_name": "FiltR", "filename": "/tmp/filt.dat",
            "name": "FiltDS",
            "curve_data": {"x": [0.0], "y": [1.0]},
        })
        time.sleep(0.3)
        cl.drain()
        assert len(received) == 0, f"got: {received}"

    def test_prefix_matches_subtopics(self, zmq_pair):
        cl, srv = zmq_pair
        received = []
        def h(e):
            received.append(e)
        cl.subscribe(topic="dataset.", callback=h)
        time.sleep(0.3)
        cl.call("dataset.load", {
            "reader_name": "PrefR", "filename": "/tmp/pref.dat",
            "name": "PrefDS",
            "curve_data": {"x": [0.0], "y": [1.0]},
        })
        time.sleep(0.5)
        cl.drain()
        assert len(received) > 0, f"got: {received}"


# ── 10. Proxy RPC error handling ────────────────────────────────


class TestProxyRpcErrorHandling:

    def test_proxy_run_returns_error_dict_on_failure(self, client):
        _add_ds(client, "ErrRun")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        fit = flist[0]
        result = fit.run()
        assert isinstance(result, dict)
        # run() with fake data may return ok=False, but shouldn't crash
        assert "ok" in result

    def test_proxy_update_does_not_crash(self, client):
        _add_ds(client, "ErrUpd")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        result = fit.update()
        assert isinstance(result, dict)

    def test_proxy_model_finalize_does_not_crash(self, client):
        _add_ds(client, "ErrFin")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        result = fit.model_finalize()
        assert isinstance(result, dict)

    def test_proxy_save_does_not_crash(self, client):
        _add_ds(client, "ErrSav")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        # ``FitProxy.save`` takes the destination; calling it bare raised
        # TypeError in the *client*, before anything reached the server.
        with tempfile.TemporaryDirectory() as tmp:
            result = fit.save(os.path.join(tmp, "fit.json"))
        assert isinstance(result, dict)

    def test_proxy_set_dataset_does_not_crash(self, client):
        _add_ds(client, "ErrSDS")
        _add_ds(client, "ErrSDS2", x=(3.0,), y=(4.0,))
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        result = fit.set_dataset(dataset_index=1)
        assert isinstance(result, dict)

    def test_proxy_set_result_idx_does_not_crash(self, client):
        _add_ds(client, "ErrSRI")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        # A fit with no stored results has nothing to restore, and says so.
        with pytest.raises(RemoteError, match="no results"):
            fit.set_result_idx(result_idx=0)
        # It is the call that refuses, not the server: it still answers.
        assert client.meta__ping().get("ok") is True
        fit.run()
        assert isinstance(fit.set_result_idx(result_idx=0), dict)


# ── 11. chisurf.run() pattern ────────────────────────────────────


class TestChisurfRunPattern:

    def test_run_expression_via_call(self, client):
        """Simulate chisurf.run(\"chisurf.fits[0].set_result_idx(2)\") pattern."""
        _add_ds(client, "RunPat")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        # This is what chisurf.run("chisurf.fits[0].set_result_idx(2)") would do
        fit = flist[0]
        fit.run()
        # One result stored, so index 2 clips onto it rather than failing.
        result = fit.set_result_idx(result_idx=2)
        assert isinstance(result, dict)
        assert "ok" in result

    def test_run_expression_multiple_calls(self, client):
        """Multiple proxy RPC calls in sequence (like GUI does)."""
        _add_ds(client, "MultiPat")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        fit = ProxyFitList(client)[0]
        # Run first: selecting a result before one exists is what the GUI would
        # never do, and the server refuses it explicitly.
        r1 = fit.run()
        r2 = fit.set_result_idx(result_idx=0)
        r3 = fit.update()
        assert isinstance(r1, dict)
        assert isinstance(r2, dict)
        assert isinstance(r3, dict)

    def test_enumerate_fits_pattern(self, client):
        """for idx, f in enumerate(chisurf.fits): ... pattern."""
        _add_ds(client, "EnumPat")
        ft1 = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        ft2 = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft1.get("ok") or not ft2.get("ok"):
            pytest.skip("fit__create not available")
        flist = ProxyFitList(client)
        uids = []
        for idx, f in enumerate(flist):
            uids.append(f.uid)
            assert isinstance(f.run(), dict)
        assert ft1["uid"] in uids
        assert ft2["uid"] in uids

    def test_fits_index_access(self, client):
        """chisurf.fits[idx] pattern works."""
        _add_ds(client, "IdxPat")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        flist = ProxyFitList(client)
        fit = flist[0]
        assert fit.uid == ft["uid"]
        assert fit.name is not None

    def test_proxy_truthiness(self, client):
        """bool(ProxyFitList) and bool(ProxyDatasetList) work."""
        flist = ProxyFitList(client)
        assert not flist  # empty
        dlist = ProxyDatasetList(client)
        assert not dlist  # empty

        _add_ds(client, "Truthy")
        assert dlist  # non-empty after invalidation
        dlist._invalidate()
        assert len(dlist) == 1
        assert dlist  # truthy


# ── 12. Unicode and special characters ──────────────────────────


class TestUnicodeData:

    def test_unicode_dataset_name(self, client):
        """Unicode characters in dataset name survive round-trip."""
        name = "DatenSatz_über_100_µs"
        r = client.call("dataset.load", {
            "reader_name": "UniR", "filename": "/tmp/uni.dat",
            "name": name,
            "curve_data": {"x": [0.0, 1.0], "y": [2.0, 3.0]},
        })
        assert r.get("ok") is True
        info = client.dataset__get(dataset_index=r["dataset_index"])
        assert info["name"] == name

    def test_unicode_fit_name(self, client):
        """Unicode in fit name."""
        _add_ds(client, "UniFitDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="Fít_Nömé_über")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")
        info = client.fit__get(fit_index=ft["fit_index"])
        assert info["name"] == "Fít_Nömé_über"

    def test_unicode_in_curve_data(self, client):
        """Unicode chars in filename (not in numeric data)."""
        r = client.call("dataset.load", {
            "reader_name": "UniCurveR",
            "filename": "/tmp/ünïcödé.dat",
            "name": "UnicodeCurve",
            "curve_data": {"x": [0.0, 1.0], "y": [2.0, 3.0]},
        })
        assert r.get("ok") is True
        curve = client.dataset__curve_data(dataset_index=r["dataset_index"])
        assert curve.get("ok") is True
        assert curve["x"] == [0.0, 1.0]

    def test_unicode_parameter_name(self, client):
        """Parameter names with unicode (though unusual)."""
        _add_ds(client, "UniParamDS")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL)
        if not ft.get("ok"):
            pytest.skip(f"fit__create: {ft.get('error')}")
        info = client.fit__get(fit_index=ft["fit_index"])
        params = info.get("model", {}).get("parameters_all", [])
        if params:
            p = params[0]
            result = client.parameter__set_value(p["name"], 42.0, fit_index=ft["fit_index"])
            assert result.get("ok") is True


# ── 13. Concurrent operations ───────────────────────────────────


class TestConcurrentOperations:

    def test_two_sequential_dataset_adds(self, client):
        """Sequential add_dataset calls from one client."""
        for i in range(5):
            r = _add_ds(client, f"Seq{i}")
            assert r.get("ok") is True
        assert len(client.dataset__list()) == 5

    def test_concurrent_pings(self, client):
        """Multiple pings from different clients."""
        cmd, pub = _PORTS
        clients = [ChisurfClient(cmd_port=cmd, pub_port=pub) for _ in range(3)]
        for c in clients:
            c.connect()
        results = [c.meta__ping() for c in clients]
        for r in results:
            assert r.get("ok") is True
        for c in clients:
            c.close()

    def test_large_list_response(self, client):
        """list_fits with many fits doesn't truncate."""
        _add_ds(client, "LargeList")
        created = []
        for i in range(30):
            ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                    fit_name=f"ListFit{i}")
            if ft.get("ok"):
                created.append(ft)
        if not created:
            pytest.skip("fit__create not available")
        fits = client.fit__list()
        assert len(fits) == len(created)

    def test_interleaved_add_list_remove(self, client):
        """Add fits, list them, remove some, list again."""
        _add_ds(client, "InterDS")
        created = []
        for i in range(10):
            ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                    fit_name=f"Inter{i}")
            if ft.get("ok"):
                created.append(ft)
        if not created:
            pytest.skip("fit__create not available")
        assert len(client.fit__list()) == len(created)
        for ft in created[::2]:
            client.fit__remove(fit_indices=[ft["fit_index"]])
        assert len(client.fit__list()) == len(created) - len(created[::2])


# ── 14. Proxy plugin pattern integration ────────────────────────


class TestProxyPluginPatterns:
    """End-to-end tests for plugin access patterns through the proxy."""

    def test_fit_model_lazy_fetch_n_points(self, client):
        """fit.model.n_points lazy-fetches via fit__get when accessed through proxy."""
        _add_ds(client, "LazyN")
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="LazyFit")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")

        proxy_list = ProxyFitList(client)
        fits = list(proxy_list)
        assert len(fits) >= 1
        fit = fits[-1]
        model = fit.model
        assert model.name is not None

    def test_fit_data_filename_via_proxy(self, client):
        """fit.data.filename works through proxy lazy-fetch."""
        _add_ds(client, "LazyData", x=[0.0, 1.0], y=[2.0, 3.0])
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="LazyFit2")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")

        proxy_list = ProxyFitList(client)
        fits = list(proxy_list)
        fit = fits[-1]
        data = fit.data
        assert data is not None
        assert hasattr(data, "name")

    def test_fit_save_positional_args(self, client):
        """fit.save(path, 'csv') works with positional args through proxy."""
        import tempfile, os
        _add_ds(client, "SavePos", x=[0.0, 1.0], y=[2.0, 3.0])
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="SaveFit")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")

        proxy_list = ProxyFitList(client)
        fits = list(proxy_list)
        fit = fits[-1]
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "test_save")
            result = fit.save(out, "csv")
            # The call should not crash and should reach the server
            assert isinstance(result, dict)
            assert "ok" in result

    def test_enumerate_fits_attribute_access(self, client):
        """enumerate(fits) and attribute access works like plugins do."""
        _add_ds(client, "EnumDS", x=[0.0], y=[1.0])
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="EnumFit")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")

        proxy_list = ProxyFitList(client)
        for i, fit in enumerate(proxy_list):
            assert fit.name is not None
            assert fit.uid is not None
            if i == 0:
                _ = fit.chi2

    def test_parameters_all_through_proxy(self, client):
        """fit.model.parameters_all list access through proxy after lazy-fetch."""
        _add_ds(client, "ParamDS", x=[0.0, 1.0], y=[2.0, 3.0])
        ft = client.fit__create(dataset_index=0, model_name=TCSPC_MODEL,
                                fit_name="ParamFit")
        if not ft.get("ok"):
            pytest.skip("fit__create not available")

        proxy_list = ProxyFitList(client)
        for fit in proxy_list:
            if fit.name == "ParamFit":
                params = fit.model.parameters_all
                assert isinstance(params, list)
                if params:
                    p = params[0]
                    assert hasattr(p, "name")
                    assert hasattr(p, "value")
                break
