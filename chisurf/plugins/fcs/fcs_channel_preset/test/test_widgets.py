from __future__ import annotations

from pathlib import Path

import pytest
from qtpy import QtWidgets


def test_fcs_channel_dialog(qapp, qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Construction builds an AutoForm host over the view-model."""
    db_path = str(tmp_path / "sample_management.db")

    monkeypatch.setattr(
        "chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_setup_utils.resolve_database_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        "chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_setup_utils.resolve_active_user_id",
        lambda: "user_default",
    )
    monkeypatch.setattr(
        "chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups.resolve_active_user_id",
        lambda: "user_default",
    )

    from chisurf.gui.autoform.auto_form import AutoForm
    from chisurf.plugins.fcs.fcs_channel_preset import FCSChannelWidget

    widget = FCSChannelWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "FCS Channel Definitions" in widget.windowTitle()
    assert isinstance(widget.auto_form, AutoForm)
    assert widget.model is widget.auto_form.model


def test_pairs_section_registered() -> None:
    """The custom pairs section key resolves once the plugin gui is imported."""
    import chisurf.plugins.fcs.fcs_channel_preset.gui.sections  # noqa: F401
    from chisurf.gui.autoform.sections.registry import get_section_factory

    assert get_section_factory("fcs_channel_pairs") is not None


def test_view_model_add_and_collect(qapp) -> None:
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
