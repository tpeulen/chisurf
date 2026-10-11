"""Physical TTTR lags stay in canonical milliseconds through merger, writer, reader and fit."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.core.experiments.fcs.reader import FCS
from chisurf.core.fluorescence.fcs.merge import save_mean_correlation
from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import fit_simple_diffusion
from chisurf.plugins.fcs.fcs_merger.gui.app import create_app
from chisurf.plugins.fcs.fcs_merger.gui.model import read_folder

REPO = Path(__file__).resolve().parents[5]


def chunk_builder():
    path = REPO / "okf/plugins/emtk-ports/fcs_merger/scripts/make_chunks.py"
    spec = importlib.util.spec_from_file_location("physical_merger_chunks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build


def test_measured_chunk_lag_uses_raw_ticks_header_and_canonical_ms(tmp_path):
    import tttrlib

    folder = chunk_builder()(tmp_path / "physical", n_chunks=2)
    legacy = chunk_builder()(tmp_path / "old-seconds", n_chunks=2, legacy_seconds=True)
    curves, _, _ = read_folder(folder)
    old, _, _ = read_folder(legacy)
    stream = tttrlib.TTTR(str(REPO / "test/data/tttr/BH/132/BH_SPC132.spc"), "SPC-130")
    raw = tttrlib.Correlator(n_bins=7, n_casc=25)
    raw.set_macrotimes(stream.macro_times, stream.macro_times)
    ch = np.asarray(stream.routing_channels)
    raw.set_weights(np.isin(ch, [0, 1]).astype(float), np.isin(ch, [8, 9]).astype(float))
    expected = np.asarray(raw.x_axis) * stream.header.macro_time_resolution * 1000
    expected = expected[expected > 0]
    # The fixture writer intentionally emits five significant digits.
    np.testing.assert_allclose(curves[0]["x"], expected, rtol=5e-5)
    np.testing.assert_allclose(curves[0]["x"], np.asarray(old[0]["x"]) * 1000, rtol=1e-4)
    np.testing.assert_array_equal(curves[0]["y"], old[0]["y"])
    assert curves[0]["duration"] == old[0]["duration"] == 10
    assert curves[0]["channel_a"] == old[0]["channel_a"]


def test_writer_reader_and_fit_preserve_physical_milliseconds(tmp_path):
    import tttrlib

    stream = tttrlib.TTTR(str(REPO / "test/data/tttr/BH/132/BH_SPC132.spc"), "SPC-130")
    lag = tttrlib.Correlator(tttr=stream, channels=([0, 1], [8, 9]), n_bins=7, n_casc=25).x_axis
    tau = np.asarray(lag, float) * 1000
    expected_td_ms = 0.8
    y = 1 + 0.3 / (1 + tau / expected_td_ms) / np.sqrt(1 + tau / (expected_td_ms * 3.5**2))
    path = tmp_path / "known-ms.cor"
    save_mean_correlation({"x": tau, "y": y, "duration": 10, "count_rate": 2}, path)
    curve = FCS(experiment_reader="kristine").read(str(path))[0]
    assert curve.X_UNITS == "milliseconds"
    np.testing.assert_allclose(curve.x, tau[tau > 0], rtol=5e-5)
    fitted, *_ = fit_simple_diffusion(curve.x, curve.y)
    assert fitted == pytest.approx(expected_td_ms, rel=0.12)


def test_merger_axis_declares_canonical_ms_and_legacy_inputs_are_not_reinterpreted(tmp_path):
    # Existing files carry no unit tag; loader keeps their literal values.
    folder = chunk_builder()(tmp_path / "old", n_chunks=2, legacy_seconds=True)
    app = create_app()
    try:
        app.load_folder(folder)
        app.job.future.result(timeout=10)
        app.job.poll()
        driver = Driver(app, size=(1200, 800))
        painter = driver.draw(3)
        assert "Lag time (ms)" in [call[6] for call in painter.calls if call[0] == "text"]
        on_disk = np.loadtxt(folder / "chnk-0000.cor")
        np.testing.assert_array_equal(app.model.correlations[0]["x"], on_disk[:, 0])
    finally:
        app.close()
