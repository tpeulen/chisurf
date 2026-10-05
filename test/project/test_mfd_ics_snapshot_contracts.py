"""Scientific contracts for calibrated image carpets and measured burst payloads."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

from chisurf.core.fitting.fit import Fit
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data, _resolve


@pytest.mark.parametrize("class_name", ["ImageCorrelationModel", "IcsGaussian2DModel"])
def test_ics_reader_calibration_remains_fixed_after_fit_window_rebind(class_name):
    """Rebinding the carpet must retain the reader's calibrated pixel-size lock."""
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith(class_name))
    cls = _resolve(entry["configured_path"])
    fit = Fit(model_class=cls, data=_data(entry, cls))
    fit.model.update()
    pixel = next(p for p in fit.model.parameters_all if p.canonical_id == "pxl_size")
    assert pixel.fixed
    fit.fit_range = (1, len(fit.data.y) - 1)
    fit.model.update()
    assert pixel.fixed
    project = capture_session([fit.data], [fit])
    restored = restore_session(project)
    assert capture_session(restored.datasets, restored.fits).fits == project.fits


def _measured_mfd_fit():
    """Read the bundled measured burst folder through the actual MFD reader."""
    entry = next(e for e in CATALOGUE if e["experiment"] == "mfd")
    cls = _resolve(entry["configured_path"])
    fit = Fit(model_class=cls, data=_data(entry, cls))
    fit.fit_range = (0, len(fit.data.y))
    return fit


def test_mfd_adapter_restores_three_state_topology_before_parameter_routing():
    """The state count determines all distance, population and rate ports."""
    fit = _measured_mfd_fit()
    fit.model.n_states = 3
    state = fit.model.get_state()
    other = _measured_mfd_fit()
    other.model.set_state(state)
    assert other.model.n_states == 3
    assert [p.name for p in other.model.parameters_all] == [
        p.name for p in fit.model.parameters_all
    ]


def test_real_mfd_payload_preserves_typed_measurements_and_scientific_evaluation():
    """A detached payload supplies the same real histogram and burst-time measure."""
    fit = _measured_mfd_fit()
    payload = fit.data.mfd
    state = payload.get_session_state()
    restored = type(payload).from_session_state(state)
    assert restored.get_session_state() == state
    assert type(restored) is type(payload)
    assert restored.preparation.counts.dtype == payload.preparation.counts.dtype
    np.testing.assert_array_equal(restored.preparation.counts, payload.preparation.counts)
    np.testing.assert_equal(
        restored.preparation.mean_micro_time, payload.preparation.mean_micro_time
    )
    fit.model.n_states = 3
    fit.model.state_group._distances[0].value = 38.0
    fit.model.state_group._distances[1].value = 55.0
    fit.model.state_group._distances[2].value = 72.0
    fit.model.update()
    expected = fit.model.y.copy()
    assert np.isfinite(expected).all() and expected.sum() > 0
    score = fit.model.burstwise_score(max_bursts=12, seed=47)
    assert np.isfinite(score.score)
    fit.data.mfd = restored
    fit.model.update()
    np.testing.assert_allclose(fit.model.y, expected, rtol=1e-12, atol=1e-12)
    assert fit.model.burstwise_score(max_bursts=12, seed=47).score == score.score
    for expected_array, actual_array in zip(payload.arrivals(), restored.arrivals()):
        np.testing.assert_array_equal(actual_array, expected_array)


def test_real_mfd_fresh_file_link_edit_recompute_resave(tmp_path, monkeypatch):
    """Duplicate-named measured fits restore exact links and editable predictions."""
    fits = [_measured_mfd_fit(), _measured_mfd_fit()]
    for fit in fits:
        fit.name = "same measured fit label"
        fit.model.n_states = 3
        for parameter, distance in zip(fit.model.state_group._distances, (38.0, 55.0, 72.0)):
            parameter.value = distance
    source = fits[1].model.state_group._distances[0]
    source.error_estimate = 0.625
    target = fits[0].model.state_group._distances[1]
    target.bounds = (20.0, 110.0)
    target.bounds_on = True
    target.error_estimate = 0.375
    target.fixed = True
    target.link = source
    local = fits[0].model.state_group._distances[2]
    local.link = fits[0].model.state_group._distances[0]
    for fit in fits:
        fit.model.update()
    initial = fits[0].model.y.copy()
    project = capture_session([fit.data for fit in fits], fits)
    path = save_file(project, tmp_path / "measured-mfd.cs.pto")
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps({"predictions": [fit.model.y.tolist() for fit in fits]}))
    probe = """
import sys
from test.project import scientific_catalogue_probe
sys.meta_path.insert(0, scientific_catalogue_probe._BlockMMFDB())
from chisurf.core.experiments.mfd.reader import MfdReader
from chisurf.core.fluorescence.mfd import fit as compute
from chisurf.core.fluorescence.mfd import prepare
def deny(*args, **kwargs):
    raise AssertionError('fresh restore reread original MFD measurement')
MfdReader.read = deny
compute.load_mfd_data = deny
prepare.prepare_burst_folder = deny
scientific_catalogue_probe.main()
"""
    fresh = subprocess.run(
        [sys.executable, "-c", probe, str(path), str(expected)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr

    def no_measurement_read(*args, **kwargs):
        """Reject all attempts to reopen the original measurement during restore."""
        raise AssertionError("session restore reread measured MFD source")

    from chisurf.core.experiments.mfd.reader import MfdReader
    from chisurf.core.fluorescence.mfd import fit as mfd_compute

    monkeypatch.setattr(MfdReader, "read", no_measurement_read)
    monkeypatch.setattr(mfd_compute, "load_mfd_data", no_measurement_read)
    restored = restore_session(load_file(path))
    assert capture_session(restored.datasets, restored.fits).fits == project.fits
    consumer, producer = restored.fits
    linked = consumer.model.state_group._distances[1]
    produced = producer.model.state_group._distances[0]
    assert linked.link is produced
    assert linked.unique_identifier == target.unique_identifier
    assert produced.unique_identifier == source.unique_identifier
    assert linked._port.get_uid() == target._port.get_uid()
    assert produced._port.get_uid() == source._port.get_uid()
    assert linked.fixed and linked.bounds_on and linked.bounds == (20.0, 110.0)
    assert linked.error_estimate == 0.625
    assert consumer.model.state_group._distances[2].link is consumer.model.state_group._distances[0]
    produced.value = 46.0
    consumer.model.update()
    assert not np.allclose(consumer.model.y, initial)
    linked.link = None
    assert linked.error_estimate == 0.375
    linked.fixed = False
    linked.value = 62.0
    consumer.model.update()
    assert linked.link is None and not linked.fixed
    changed = capture_session(restored.datasets, restored.fits)
    second = restore_session(load_file(save_file(changed, tmp_path / "edited-mfd.cs.pto")))
    assert capture_session(second.datasets, second.fits).fits == changed.fits
    np.testing.assert_allclose(second.fits[0].model.y, consumer.model.y, rtol=1e-12, atol=1e-12)


def test_restored_measured_mfd_runs_bounded_real_refit_and_resaves(tmp_path, monkeypatch):
    """The restored measurement drives a real constrained scientific optimisation."""
    import chisurf

    fit = _measured_mfd_fit()
    fit.model.n_states = 3
    for parameter, distance in zip(fit.model.state_group._distances, (38.0, 55.0, 72.0)):
        parameter.value = distance
    for parameter in fit.model.parameters_all:
        parameter.fixed = True
    fit.model.state_group._donor_only.fixed = False
    fit.model.state_group._donor_only.value = 0.85
    fit.model.update()
    path = save_file(capture_session([fit.data], [fit]), tmp_path / "before-refit.cs.pto")
    restored = restore_session(load_file(path))
    fitted = restored.fits[0]
    initial = fitted.chi2
    assert fitted.model.n_free == 1
    monkeypatch.setitem(chisurf.core.settings.cs_settings["optimization"]["leastsq"], "maxfev", 18)
    fitted.run(record_result=False, estimate_errors=False, finalize=False, notify=False)
    assert np.isfinite(fitted.chi2) and fitted.chi2 < initial
    assert fitted.model.state_group._donor_only.value != 0.85
    assert np.isfinite(fitted.model.y).all() and fitted.model.y.sum() > 0
    recaptured = capture_session(restored.datasets, restored.fits)
    after = restore_session(load_file(save_file(recaptured, tmp_path / "after-refit.cs.pto")))
    assert capture_session(after.datasets, after.fits).fits == recaptured.fits
    np.testing.assert_allclose(after.fits[0].model.y, fitted.model.y, rtol=1e-12, atol=1e-12)
