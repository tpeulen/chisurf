"""End-to-end headless test of the ndX ↔ ChiSurf in-process RPC bridge (PRD-56 §7).

Builds the in-process ChiSurf client (phasor + FRET-line services), then drives it
through ndX's own chisurf-free ``PhasorService`` / ``LinesService`` facades — the
exact path the GUI uses, minus the socket.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from chisurf.plugins.ndxplorer.rpc_bridge import make_inprocess_chisurf_client

# ndX is an optional submodule under modules/ndxplorer; put it on the path (as the
# plugin does at load time) so this cross-module test can import its RPC facades.
_NDX_MODULE = pathlib.Path(__file__).resolve().parents[2] / "modules" / "ndxplorer"
if _NDX_MODULE.is_dir() and str(_NDX_MODULE) not in sys.path:
    sys.path.insert(0, str(_NDX_MODULE))

pytest.importorskip("ndxplorer", reason="ndX submodule not available")


@pytest.fixture()
def client():
    c = make_inprocess_chisurf_client()
    assert c is not None
    return c


def test_phasor_service_over_inprocess_client(client):
    from ndxplorer.rpc import PhasorService

    svc = PhasorService(client)
    # A single-exponential phasor point round-trips to its true lifetime.
    from chisurf.plugins.microscopy.img_pixel_phasor import analysis

    gp, sp = analysis.lifetime_to_phasor(2.0, 80.0)
    tau_phi, tau_m = svc.apparent_lifetime([float(gp)], [float(sp)], 80.0)
    assert tau_phi[0] == pytest.approx(2.0, rel=1e-6)
    assert tau_m[0] == pytest.approx(2.0, rel=1e-6)

    overlays = svc.overlays(80.0, sets=["semicircle", "lifetime_ticks"])
    names = {o["name"] for o in overlays}
    assert "universal semicircle" in names


def test_lines_service_phasor_and_fret_over_inprocess_client(client):
    from ndxplorer.rpc import LinesService

    svc = LinesService(client)

    phasor_lines = svc.phasor.overlays(frequency_mhz=80.0, sets=["semicircle"])
    assert phasor_lines[0]["name"] == "universal semicircle"

    fret_lines = svc.fret_line.overlays(
        components=[{"model_name": "FRET: FD (Gaussian)", "n_components": 1, "params": {}}],
        sweep={"kind": "param", "component": 0, "name": "distance.mean.0"},
        param_min=20.0,
        param_max=100.0,
        n_points=6,
    )
    assert fret_lines[0]["kind"] == "curve"
    assert len(fret_lines[0]["x"]) == 6


def test_chisurf_window_gets_the_phasor_panel(client, qtbot, tmp_path, monkeypatch):
    """ChiSurf's ndX window hands the app the client: the Phasor / FRET window is on."""
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path))
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    window = build_ndxplorer_window(chisurf_rpc=client, session_autosave=False,
                                    layout_store=None)
    try:
        assert window.app.chisurf_rpc is client
        assert window.app.panel.available("show_phasor_panel")
        phasor = next(f for f in window.app.features if f.name == "phasor")
        # The FRET models come from ChiSurf, over the client.
        assert any("FRET" in m for m in phasor.panel.fret_models())
        assert phasor.panel.sweep_params()
    finally:
        window.close()
