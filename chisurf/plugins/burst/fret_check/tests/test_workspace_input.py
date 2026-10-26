"""The measurement to check is a photon stream of the Datasets workspace, picked in the Input
section of the Measurement window; the window has no drop hook of its own."""

from __future__ import annotations

from chisurf.plugins.burst.fret_check.app.frame import SmFretApp, receive_photons
from test.gui.burst_workspace import draw, no_input_dialog, pick_row, restore_workspace


def test_a_picked_photon_stream_is_opened(monkeypatch, tmp_path):
    from chisurf.core.plugin.workspace_input import register_result

    no_input_dialog(monkeypatch)
    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build

    photons = build(tmp_path / "measurement").parent / "m000.spc"
    opened = []
    with restore_workspace():
        register_result(str(photons), kind="photons", name=photons.name)
        app = SmFretApp(runner="sync")
        monkeypatch.setattr(app, "open", opened.append)
        draw(app)
        assert "workspace_input_rows" in app.item_rects
        pick_row(app, photons.name)
    assert [str(p) for p in opened] and opened[0].endswith("m000.spc")
    assert not hasattr(app, "files_dropped")


def test_the_hand_off_opens_the_address(monkeypatch):
    app = SmFretApp(runner="sync")
    opened = []
    monkeypatch.setattr(app, "open", opened.append)
    receive_photons(app, {"file": "/data/m000.pto/m000.spc"})
    assert opened == ["/data/m000.pto/m000.spc"]
