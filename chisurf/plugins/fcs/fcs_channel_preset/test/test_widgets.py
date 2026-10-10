from __future__ import annotations

from pathlib import Path

import pytest


def test_view_model_add_and_collect() -> None:
    """add_pair appends a record and save-time collection derives kind/name."""
    from chisurf.plugins.fcs.fcs_channel_preset.gui.view_model import FCSChannelViewModel

    model = FCSChannelViewModel()
    n_before = len(model.pairs)
    model.add_pair("prompt_green", "prompt_red", "GR")
    model.add_pair("prompt_green", "prompt_green", "")  # auto-named ACF
    assert len(model.pairs) == n_before + 2

    data = model._collect_setup_data()
    pairs = data["pairs"]
    assert pairs[0]["name"] == "GR"
    assert pairs[0]["kind"] == "CCF"
    assert pairs[1]["kind"] == "ACF"
    assert pairs[1]["name"].endswith("_ACF")


def test_the_qt_embed_hosts_the_emtk_app(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Qt surfaces that embed the editor get a QWidget around the emtk app, nothing of their own."""
    pytest.importorskip("qtpy.QtWidgets")
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    from chisurf.gui.widgets.emtk_embed import FCSChannelEmbed

    widget = FCSChannelEmbed()
    try:
        assert "FCS Channel Definitions" in widget.windowTitle()
        assert widget.app is widget.host.control
    finally:
        widget.close()
