import json
import pathlib

import numpy as np
import pytest
from qtpy import QtWidgets

_SPC = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
)


def test_fcs_correlator_tool(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_correlator.tool import FcsCorrelatorTool
    from chisurf.gui.widgets.navigation import NavigationPanelTool
    widget = FcsCorrelatorTool()
    qtbot.addWidget(widget)
    assert isinstance(widget, NavigationPanelTool)


def test_workflow_leads_with_channel_definitions(qapp, qtbot):
    """No detector-setup step: channel definitions are step 1, opens on files."""
    from chisurf.plugins.fcs.fcs_correlator.tool import (
        CORRELATOR_PANELS,
        FcsCorrelatorTool,
    )

    roles = [p.get("role") for p in CORRELATOR_PANELS]
    assert "detector" not in roles
    assert roles[0] == "channel_def"
    assert roles == ["channel_def", "files", "filter", "correlator", "merger"]

    tool = FcsCorrelatorTool()
    qtbot.addWidget(tool)
    # opens on the file-drop step
    assert tool.nav_list.currentRow() == tool._nav_row_for_role("files")


def test_lifetime_filter_load_species_select_unload(qapp, qtbot, tmp_path):
    """Loading a filter switches the correlator to species-selection mode."""
    from chisurf.gui.autoform import AutoForm
    from chisurf.plugins.fcs.fcs_correlator.correlator_panel import (
        CorrelatorSettingsModel,
    )

    model = CorrelatorSettingsModel()
    form = AutoForm(model)
    qtbot.addWidget(form)
    model._form = form
    assert model.filter_mode is False

    nbins = 32
    payload = {
        "mode": "single",
        "metadata": {"species_labels": ["Fast", "Slow"]},
        "total_path": None,
        "species_patterns": None,
        "nuisance_count": 1,
        "nuisance_labels": ["BG"],
        "filters": np.random.rand(3, nbins).tolist(),  # 2 species + 1 nuisance
        "reconstruction": np.zeros(nbins).tolist(),
        "weighted_residuals": np.zeros(nbins).tolist(),
        "total_decay": np.zeros(nbins).tolist(),
        "species_decays": [np.zeros(nbins).tolist()] * 2,
    }
    path = tmp_path / "filters.json"
    path.write_text(json.dumps(payload))

    n = model.load_lifetime_filter_file(str(path))
    assert n == 2  # nuisance filters excluded
    assert model.filter_mode is True
    assert model._filter_labels == ["Fast", "Slow"]

    # species subset (A=0, B=1) has exactly the two chosen rows
    sub = model._subset_species(model._lifetime_filters, [0, 1])
    assert np.asarray(sub).shape == (2, nbins)

    model.clear_lifetime_filter()
    assert model.filter_mode is False


def test_channel_combos_switch_to_species(qapp, qtbot):
    """The A/B combo section lists species when filters are loaded."""
    from chisurf.plugins.fcs.fcs_correlator.correlator_panel import (
        CorrelatorSettingsModel,
        _ChannelComboWidget,
    )

    model = CorrelatorSettingsModel()
    widget = _ChannelComboWidget(model)
    qtbot.addWidget(widget)

    model.set_lifetime_filters(np.random.rand(2, 16), ["Fast", "Slow"])
    widget.refresh()
    assert widget.lbl_a.text() == "Species A:"
    assert [widget.combo_a.itemText(i) for i in range(widget.combo_a.count())] == [
        "Fast",
        "Slow",
    ]
    widget.combo_b.setCurrentIndex(1)
    assert model._species_b == 1


@pytest.mark.skipif(not _SPC.exists(), reason="SPC test data not available")
def test_files_carry_over_to_correlator(qapp, qtbot):
    """Selecting files in step 2 must load photon data into the correlator (step 4).

    Regression: the correlator read the container type from a non-existent
    ``filetype`` key (it lives under ``tttr_reading.file_type``) and
    ``tttrlib.TTTR(path, "")`` returns an empty object without raising, so the
    correlator silently received zero photons.
    """
    from chisurf.plugins.fcs.fcs_correlator.tool import FcsCorrelatorTool

    tool = FcsCorrelatorTool()
    qtbot.addWidget(tool)

    tool.nav_list.setCurrentRow(1)  # Files & Steps
    tool._workflow_panels["files"].file_list.add_paths([str(_SPC)])

    tool.nav_list.setCurrentRow(3)  # Correlator
    model = tool._correlator_model
    assert model._tttr is not None
    assert len(model._tttr) > 0
