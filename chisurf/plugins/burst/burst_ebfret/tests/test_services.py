"""The window's backend: every action as an RPC call on an in-process session."""

from __future__ import annotations

import time

import pytest

from chisurf.plugins.burst.burst_ebfret import demo
from chisurf.plugins.burst.burst_ebfret.api.client import EbfretClient
from chisurf.plugins.burst.burst_ebfret.backend import services


@pytest.fixture
def client(tmp_path):
    c = EbfretClient(seed=5)
    c.load([str(demo.write_demo(tmp_path / "demo.dat", seed=11))], 2)
    yield c
    c.close()


def test_every_manifest_method_is_registered():
    import json
    import pathlib

    registered = {}

    class Dispatcher:
        def register(self, name, handler):
            registered[name] = handler

    services.register_services(Dispatcher())
    manifest = json.loads(
        (pathlib.Path(services.__file__).parents[1] / "manifest.json").read_text()
    )
    declared = {m["name"] for m in manifest["rpc_methods"]}
    assert declared == set(registered)


def test_a_view_carries_plots_and_tables(client):
    view = client.view()
    assert view["n_series"] == 40
    assert {"signal", "raw", "obs", "mean", "noise", "dwell"} <= set(view["plots"])
    assert len(view["series_table"]) == 40
    assert view["states_table"] and view["states_table"][0]["state"] == 1


def test_run_happens_in_the_backend_and_status_follows_it(client):
    client.set("max_states", 3)
    client.set("restarts", 0)
    assert client.run()
    assert not client.run(), "a second Run while running starts nothing"
    deadline = time.monotonic() + 120
    while client.status()["running"] and time.monotonic() < deadline:
        time.sleep(0.2)
    status = client.status()
    assert not status["running"] and not status["error"]
    assert status["analyses"] == [2, 3, 4, 5, 6] or 3 in status["analyses"]
    assert any(line.startswith("K03") for line in status["log"])


def test_an_unknown_control_is_an_error_not_a_silent_no_op(client):
    with pytest.raises(RuntimeError):
        client.set("no_such_control", 1)
