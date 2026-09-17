"""Headless tests for the ``pda.from_bursts`` RPC service.

The service turns a gated burst selection (per-file photon intervals, the
ndX ``.bst`` shape) into a PDA S1/S2 experimental histogram. The happy
path needs real TTTR data, so it is skipped when the fixture is absent; the
input-validation paths run everywhere.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.session import SessionState

TTTR_FILE = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
ROUTINE = "SPC-130"


def _dispatcher() -> ServiceDispatcher:
    d = ServiceDispatcher(SessionState())
    d._build_default_registry()
    return d


def _result(reply):
    """Unwrap a ServiceResult/ServiceDispatcher reply to its dict."""
    return reply.result if hasattr(reply, "result") else reply


def test_pda_from_bursts_is_registered():
    assert "pda.from_bursts" in _dispatcher().list_methods()


def test_no_gui_import_in_server():
    """The service must stay Qt-free (no chisurf.gui import)."""
    import ast
    import inspect

    import chisurf.server.services.pda as svc

    tree = ast.parse(inspect.getsource(svc))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.name if isinstance(node, ast.Import) else (node.module or "")
                assert not name.startswith("chisurf.gui"), f"server imports GUI: {name}"


def test_missing_burst_slices_is_rejected():
    from chisurf.server.services.pda import from_bursts

    reply = from_bursts(None, burst_slices=None, channels=[[0], [1]])
    assert reply["ok"] is False and "burst_slices" in reply["error"]


def test_missing_channels_is_rejected():
    from chisurf.server.services.pda import from_bursts

    reply = from_bursts(None, burst_slices={"x.ptu": [[0, 10]]}, channels=None)
    assert reply["ok"] is False and "channels" in reply["error"]


def test_inprocess_client_exposes_bridge_methods():
    """The ndX in-process client must expose every analysis-bridge target."""
    from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

    client = make_inprocess_chisurf_client()
    if client is None:  # pragma: no cover - optional stack
        pytest.skip("RPC stack unavailable")
    reply = client.call("list_methods", {})
    result = reply.get("result", reply) if isinstance(reply, dict) else reply
    methods = set(result.get("methods", result) if isinstance(result, dict) else result)
    for m in (
        "pda.from_bursts",
        "burst_fcs.correlate_file",
        "burst_mle.workflow.prepare",
        "fit.create",
        "dataset.load",
    ):
        assert m in methods, f"{m} not exposed to ndX"


@pytest.mark.skipif(not TTTR_FILE.is_file(), reason=f"{TTTR_FILE} not available")
def test_pda_from_bursts_builds_s1s2_histogram():
    import tttrlib

    n = len(tttrlib.TTTR(str(TTTR_FILE), ROUTINE))
    burst_slices = {str(TTTR_FILE): [[0, n // 4], [n // 2, n // 2 + n // 4]]}

    reply = _dispatcher().dispatch(
        "pda.from_bursts",
        {
            "burst_slices": burst_slices,
            "channels": [[0], [1]],
            "reading_routine": ROUTINE,
            "micro_time_ranges": [[0, 4096]],
            "minimum_number_of_photons": 20,
            "maximum_number_of_photons": 200,
        },
    )
    result = _result(reply)
    assert result["ok"] is True, result
    curves = result["result"]["curves"]
    assert result["result"]["n_files"] == 1
    assert len(curves) == 1
    # maximum_number_of_photons=200 -> a 201x201 S1/S2 histogram with real counts.
    assert curves[0]["shape"] == [201, 201]
    assert curves[0]["n_photons"] > 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
