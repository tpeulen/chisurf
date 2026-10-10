import json
import pathlib

import numpy as np
import pytest
from emtk.testing import RecordingPainter

_SPC = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test"
    / "data"
    / "tttr"
    / "BH"
    / "132"
    / "BH_SPC132.spc"
)


def _show(app, role):
    """Open a step the way the rail does and draw a frame; True when it is the selected one."""
    app.select(role)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    return app.selected == role


def test_fcs_correlator_app():
    from chisurf.plugins.fcs.fcs_correlator.gui.app import FcsHubApp, make_app

    app = make_app()
    try:
        assert isinstance(app, FcsHubApp)
        assert app.workflow is not None
    finally:
        app.close()


def test_workflow_leads_with_channel_definitions():
    """No detector-setup step: channel definitions are step 1, opens on files."""
    from chisurf.plugins.fcs.fcs_correlator.gui.app import STEP_ROLES, make_app

    assert STEP_ROLES == ("channel_def", "files", "filter", "correlator", "merger")
    app = make_app()
    try:
        assert app.selected == "files"
    finally:
        app.close()


def test_lifetime_filter_load_species_select_unload(tmp_path):
    """Loading a filter switches the correlator to species-selection mode."""
    from chisurf.plugins.fcs.fcs_correlator.correlator_model import CorrelatorSettingsModel

    model = CorrelatorSettingsModel()
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


def test_species_a_and_b_are_picked_by_index():
    """With filters loaded the A/B choices are species indices (the step app draws them as combos)."""
    from chisurf.plugins.fcs.fcs_correlator.correlator_model import CorrelatorSettingsModel

    model = CorrelatorSettingsModel()
    model.set_lifetime_filters(np.random.rand(2, 16), ["Fast", "Slow"])
    assert model.filter_mode is True
    assert model._filter_labels == ["Fast", "Slow"]
    model._species_b = 1
    assert model._species_b == 1


@pytest.mark.skipif(not _SPC.exists(), reason="SPC test data not available")
def test_files_carry_over_to_correlator():
    """Selecting files in step 2 must load photon data into the correlator (step 4).

    Regression: the correlator read the container type from a non-existent
    ``filetype`` key (it lives under ``tttr_reading.file_type``) and
    ``tttrlib.TTTR(path, "")`` returns an empty object without raising, so the
    correlator silently received zero photons.
    """
    from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app

    app = make_app()
    try:
        app.files_step.add_paths([str(_SPC)])
        assert _show(app, "correlator")
        model = app.correlator_model
        assert model._tttr is not None
        assert len(model._tttr) > 0
    finally:
        app.close()
