"""End-to-end GUI test of the burst MLE-lifetime wizard on real smFRET data.

Drives the wizard the way the workflow does — set detectors, load a .bur, build
the decay, provide IRF/background, run the fit — and asserts the results are
sane. This catches the silent-failure bugs where the current detector loses its
IRF (so update_fit bails) and the decay/plot end up empty.

Skipped when the BH smFRET DNA test data is not present.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

DATA = Path("/Users/tpeulen/dev/tttr-data/bh/bh_spc132_sm_dna")
BUR = DATA / "sliding_window_All 0.1500#60_3" / "bi4_bur" / "m000.bur"
HANDOFF = DATA / "burst_analysis_handoff" / "burst_analysis_handoff.json"

pytestmark = pytest.mark.skipif(
    not (BUR.exists() and HANDOFF.exists()),
    reason="BH smFRET DNA test data not available",
)


@pytest.fixture
def fitted_wizard(qapp):
    """A wizard with channels, a burst file, IRF/bg and one fit run for green."""
    from qtpy import QtWidgets

    import tttrlib  # noqa: F401  (ensures the extension is importable)
    from chisurf.core.fluorescence.burst import extract_mle_irf_background
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    QtWidgets.QApplication.processEvents()

    settings = json.loads(HANDOFF.read_text())["channel_settings"]
    w.channel_definer.load_data_into_tables(settings)
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    w.burst_files_list.add_file(str(BUR))
    w.load_burst_data()
    w.update_burst_files()
    QtWidgets.QApplication.processEvents()

    # Provide IRF/background from the non-burst photons (as the IRF & Background
    # step / Send-to-MLE would), for every real detector.
    tttr = next(iter(w.tttrs.values()))
    idx = np.asarray(w.get_burst_indices_for_current_file(), dtype=int)
    in_burst = np.zeros(len(tttr), bool)
    in_burst[idx] = True
    patterns = extract_mle_irf_background(
        tttr, w.channel_definer.detectors,
        micro_time_binning=w.micro_time_binning, mask=~in_burst, min_photons=20,
    )
    for det, pat in patterns.items():
        if det:  # skip any stray empty-name key
            w.irf_np[det] = np.asarray(pat["irf"], float)
            w.bg_np[det] = np.asarray(pat["bg"], float)

    w.update_decay_of_detector()
    w.update_fit()
    QtWidgets.QApplication.processEvents()
    return w


def test_detector_state_has_no_empty_detector(fitted_wizard):
    # A spurious "" detector must never appear (it shadowed the real one).
    for store in (fitted_wizard.irf_np, fitted_wizard.bg_np,
                  fitted_wizard.channel_settings):
        assert "" not in store
        assert None not in store


def test_current_detector_keeps_its_irf(fitted_wizard):
    # The regression: the current detector lost its IRF (popped when its file
    # widget was empty), so update_fit silently bailed.
    det = fitted_wizard.current_detector
    assert det in fitted_wizard.irf_np, "current detector lost its IRF"
    assert det in fitted_wizard.bg_np
    assert np.asarray(fitted_wizard.irf_np[det]).size > 0


def test_decay_is_built(fitted_wizard):
    decay = fitted_wizard.decay_of_current_file
    assert decay is not None, "decay was never built (blank Intensity plot)"
    decay = np.asarray(decay)
    assert decay.size > 0 and decay.sum() > 0


def test_fit_produces_a_plausible_lifetime(fitted_wizard):
    # tau must move off the initial and land in a physical range; a silent no-fit
    # leaves it at the initial / zero.
    tau = fitted_wizard.doubleSpinBox_tau_result.value()
    assert 0.1 < tau < 10.0, f"implausible / non-fit tau={tau}"


def test_intensity_plot_has_data(fitted_wizard):
    # The Intensity panel must show the decay (and model), not be empty.
    items = fitted_wizard.combined_plot.listDataItems()
    assert items, "Intensity plot is empty after a fit"
    assert any(
        it.getData()[1] is not None and len(it.getData()[1]) > 0 for it in items
    )


def test_irf_is_not_corrupted_by_detector_switching(fitted_wizard):
    # Regression (single-source-of-truth): switching detectors used to capture the
    # *processed* IRF (shift/threshold applied) and restore it as raw, so repeated
    # A->B->A switches steadily corrupted the pattern. irf_np is now the sole
    # store and must be byte-for-byte stable across switches.
    import numpy as np

    w = fitted_wizard
    # a non-trivial shift/threshold so any re-processing would change the array
    w.shift = 5
    dets = list(w.channel_definer.detectors.keys())
    green0 = np.array(w.irf_np["green"], copy=True)
    for _ in range(3):
        for det in dets:
            w.comboBox_window.setCurrentText(det)
    assert np.array_equal(np.asarray(w.irf_np["green"]), green0), \
        "IRF was mutated by detector switching"


def test_irf_survives_ui_refresh_with_empty_file_widget(fitted_wizard):
    # The real Send-to-MLE regression: an IRF/bg set programmatically (no dropped
    # files) must NOT be destroyed when update_irf_files/update_bg_files run with
    # an empty file widget. Previously _update_hist_files popped the detector,
    # leaving update_fit to bail silently.
    import numpy as np

    det = fitted_wizard.current_detector
    n = int(np.asarray(fitted_wizard.irf_np[det]).size) or 512
    fitted_wizard.irf_np[det] = np.ones(n, float)
    fitted_wizard.bg_np[det] = np.ones(n, float)
    fitted_wizard.update_irf_files()
    fitted_wizard.update_bg_files()
    assert det in fitted_wizard.irf_np and np.asarray(fitted_wizard.irf_np[det]).size > 0
    assert det in fitted_wizard.bg_np and np.asarray(fitted_wizard.bg_np[det]).size > 0
