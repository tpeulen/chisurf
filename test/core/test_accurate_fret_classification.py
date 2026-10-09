"""Unassigned burst observations must never become fabricated reference classes."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tttrlib

from chisurf.core.datastore import numeric_column, row_count
from chisurf.core.fio.pto import Measurement
from chisurf.core.fluorescence.fret.accurate import AutoCalibration
from chisurf.plugins.burst.accurate_fret import core
from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel
from chisurf.plugins.burst.accurate_fret.test.test_accurate_fret_plugin import _simulate

REPO = Path(__file__).resolve().parents[2]
REAL_BUR = REPO / (
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/"
    "burst_analysis_handoff/bi4_bur/m000.bur"
)


def _controlled_result(monkeypatch, *, split=True):
    """Use declared masks to isolate assignment from the classifier algorithm."""
    masks = SimpleNamespace(
        donor_only=np.array([True, False, False, False, False]),
        acceptor_only=np.array([False, True, False, False, False]),
        fret=np.array([False, False, True, False, False]),
        fret_labels=np.array([-1, -1, 2, -1, -1]),
        counts={"donor_only": 1, "acceptor_only": 1, "fret": 1, "fret_populations": 1},
        method="declared",
        thresholds=(0.2, 0.8),
    )

    def calibration(*args, **kwargs):
        parameters = kwargs["calibration"]
        return AutoCalibration(
            calibration=parameters, factors=parameters.as_dict(), split=masks if split else None
        )

    monkeypatch.setattr(core, "auto_calibrate", calibration)
    return core.calibrate([100, 1, 50, 30, np.nan], [2, 5, 50, 40, 20], [0, 100, 80, 20, 5])


def _assert_masks(result):
    """Compare labels with the classifier's actual disjoint population masks."""
    split = result.calibration.split
    donor = np.asarray(split.donor_only, dtype=bool)
    acceptor = np.asarray(split.acceptor_only, dtype=bool)
    fret = np.asarray(split.fret, dtype=bool)
    np.testing.assert_array_equal(result.labels == -1, donor)
    np.testing.assert_array_equal(result.labels == -2, acceptor)
    np.testing.assert_array_equal(result.labels >= 0, fret)
    np.testing.assert_array_equal(result.labels[fret], np.asarray(split.fret_labels)[fret])
    np.testing.assert_array_equal(result.labels == -3, ~(donor | acceptor | fret))


def test_only_actual_reference_masks_receive_reference_labels(monkeypatch):
    """A finite unassigned observation and an invalid one both retain -3."""
    result = _controlled_result(monkeypatch)
    np.testing.assert_array_equal(result.labels, [-1, -2, 2, -3, -3])
    assert result.labels.dtype.kind == "i"
    assert len(result.efficiency) == 5


def test_absent_split_cannot_fabricate_fret_population_zero(monkeypatch):
    """No classification means every original observation remains unassigned."""
    result = _controlled_result(monkeypatch, split=False)
    np.testing.assert_array_equal(result.labels, [-3] * 5)


def test_real_logical_bur_keeps_invalid_rows_unassigned():
    """The measured BUR retains all 152 bursts, including 42 invalid observations."""
    columns = core.read_burst_table(REAL_BUR)
    mapping = tttrlib.guess_burst_columns(list(columns))
    channels = [columns[mapping[role]] for role in ("i_dd", "i_da", "i_aa")]
    result = core.calibrate(*channels, n_bootstrap=0, use_priors=False)
    _assert_masks(result)
    invalid = ~np.isfinite(np.column_stack(channels)).all(axis=1)
    assert len(result.labels) == 152
    assert invalid.sum() == 42
    np.testing.assert_array_equal(result.labels[invalid], np.full(42, -3))


def test_known_csv_classes_preserve_the_classifier_masks(tmp_path):
    """A real CSV with 2400 simulated bursts retains its actual assignments."""
    channels = _simulate()
    path = tmp_path / "known.csv"
    np.savetxt(
        path,
        np.column_stack(channels),
        delimiter=",",
        header="Green Count Rate (KHz),Red Count Rate (KHz),S delayed yellow (kHz),Tau (green)",
        comments="",
        fmt="%.17g",
    )
    columns = core.read_burst_table(path)
    mapping = tttrlib.guess_burst_columns(list(columns))
    result = core.calibrate(
        *(columns[mapping[role]] for role in ("i_dd", "i_da", "i_aa", "tau_f")), n_bootstrap=0
    )
    _assert_masks(result)
    assert len(result.labels) == 2400
    assert np.sum(result.labels == -1) > 0
    assert np.sum(result.labels == -2) > 0
    assert len(result.calibration.populations) == 2


def test_csv_keeps_every_row_and_exact_label_sentinel(monkeypatch, tmp_path):
    """Per-burst CSV preserves category values and row position including invalid rows."""
    result = _controlled_result(monkeypatch)
    path = tmp_path / "classified.csv"
    core.export_csv(path, result)
    data = np.genfromtxt(
        path,
        delimiter=",",
        names=True,
        comments="#",
        skip_header=len(result.calibration.report().splitlines()),
    )
    np.testing.assert_array_equal(data["label"], [-1, -2, 2, -3, -3])
    np.testing.assert_allclose(data["E"], result.efficiency, rtol=1e-5, equal_nan=True)


def test_pto_roundtrip_keeps_label_sentinel_and_burst_identity(monkeypatch, tmp_path):
    """The measurement container stores every classification with its original burst key."""
    result = _controlled_result(monkeypatch)
    raw = tmp_path / "m000.ptu"
    shutil.copy(REPO / "test/data/clsm/Leica_SP5.ptu", raw)
    path = core.write_container(raw, result)
    with Measurement.open(path) as measurement:
        table = measurement.get_store("accurate fret")
        assert row_count(table) == 5
        np.testing.assert_array_equal(numeric_column(table, "Burst Index"), np.arange(5))
        np.testing.assert_array_equal(numeric_column(table, "Population"), [-1, -2, 2, -3, -3])


def test_unassigned_scatter_has_a_name_and_is_excluded_from_fret_histogram(monkeypatch):
    """Finite unassigned points remain visible without adding to the FRET-only histogram."""
    result = _controlled_result(monkeypatch)
    model = AccurateFretViewModel()
    model._result = result
    names = {series["name"] for series in model.es_series()}
    assert "unassigned" in {name.lower() for name in names}
    assert model.efficiency_histogram() == []


def test_unassigned_display_uses_runtime_translation(monkeypatch):
    """The stable category ID remains numeric while its legend is translated."""
    from chisurf.plugins.burst.accurate_fret.gui import view_model

    result = _controlled_result(monkeypatch)
    model = AccurateFretViewModel()
    model._result = result
    monkeypatch.setattr(
        view_model, "tr", lambda text: "non attribué" if text == "unassigned" else text
    )
    assert "non attribué" in {series["name"] for series in model.es_series()}
    np.testing.assert_array_equal(result.labels, [-1, -2, 2, -3, -3])
