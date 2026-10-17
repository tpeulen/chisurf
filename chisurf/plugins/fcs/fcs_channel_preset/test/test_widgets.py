from __future__ import annotations


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
