"""Physical clocks survive synthetic raster construction and PTU persistence."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")


@pytest.fixture(scope="module")
def producer():
    """Load the shipping producer or an explicitly archived verification source."""
    source = os.environ.get("CHISURF_RASTER_TIMING_SOURCE")
    if source is None:
        from chisurf.core.fluorescence.imaging import simulate

        return simulate
    name = "_raster_timing_verified_producer"
    spec = importlib.util.spec_from_file_location(name, Path(source))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scan(producer, dt=0.064, n_micro=128, window_dt=0.01):
    """Return a real seeded scan with independently selected clock resolutions."""
    sample = tttrlib.SimSystem()
    irf = producer._gaussian_irf(n_micro, 10.0, 1.5)
    species = producer._lifetime_species(tttrlib, 0.6, irf, dt, [5000.0, 5000.0])
    sample.add_species(species)
    sample.set_rate_matrices([0.0], [0.0])
    sample.set_background([0.0, 0.0])
    sample.add_fluorophore(1.0, 1.0, 0.0, 0, False)
    stream, _image = producer._run_scan(
        tttrlib,
        sample,
        n_channels=2,
        n_pixel=4,
        pixel_size=0.5,
        n_micro=n_micro,
        dt=dt,
        dwell=0.12,
        psf_w0=0.5,
        fill_channels=[0, 1],
        window_dt=window_dt,
        seed=7,
    )
    return stream


@pytest.mark.parametrize("dt,n_micro,window_dt", [(0.064, 128, 0.01), (0.032, 256, 0.002)])
def test_scan_declares_both_physical_clocks(producer, dt, n_micro, window_dt):
    """The stream header expresses seconds; the macro clock is the laser sync, as in a measured T3 file."""
    stream = _scan(producer, dt, n_micro, window_dt)
    assert stream.header.macro_time_resolution == pytest.approx(n_micro * dt * 1e-9)
    assert stream.header.micro_time_resolution == pytest.approx(dt * 1e-9, rel=1e-12, abs=0.0)
    assert stream.header.number_of_micro_time_channels == n_micro
    assert float(stream.header.micro_time_resolution) * n_micro * 1e9 == pytest.approx(8.192)


@pytest.mark.parametrize("dt,n_micro", [(0.064, 128), (0.032, 256)])
def test_ptu_roundtrip_retains_calibrated_axes_and_events(producer, tmp_path, dt, n_micro):
    """Writing the scan preserves event identities and physical arrival delays."""
    simulation = producer.simulate_molecule_mixture(
        [producer.Blob(2, 2, 0.6, brightness=20000.0)],
        n_pixel=4,
        n_micro=n_micro,
        dt=dt,
        dwell=2.0,
        psf_w0=0.5,
        seed=7,
    )
    path = tmp_path / "sample.ptu"
    producer.write_mixture_ptu(simulation, path)
    restored = tttrlib.TTTR(str(path))
    assert restored.header.micro_time_resolution == pytest.approx(dt * 1e-9, rel=1e-12, abs=0.0)
    assert restored.header.macro_time_resolution == pytest.approx(n_micro * dt * 1e-9)
    assert restored.header.number_of_micro_time_channels == n_micro
    for name in ("macro_times", "micro_times", "routing_channels", "event_types"):
        np.testing.assert_array_equal(getattr(restored, name), getattr(simulation.tttr, name))
    photons = np.asarray(restored.event_types) == 0
    bins = np.asarray(restored.micro_times)[photons]
    ticks = np.asarray(restored.macro_times)[photons]
    assert bins.size > 100
    np.testing.assert_allclose(bins * restored.header.micro_time_resolution * 1e9, bins * dt)
    np.testing.assert_allclose(ticks * restored.header.macro_time_resolution, ticks * n_micro * dt * 1e-9)


def test_writer_replaces_placeholder_microtime_metadata(producer, tmp_path):
    """Persistence uses the declared simulation axis even for an array-built stream."""
    simulation = producer.simulate_irf_measurement(n_pixel=4, dwell=0.12, brightness=5000.0)
    simulation.tttr.header.set_micro_time_resolution(1.0)
    simulation.tttr.header.set_number_of_micro_time_channels(1024)
    producer.write_mixture_ptu(simulation, tmp_path / "irf.ptu")
    restored = tttrlib.TTTR(str(tmp_path / "irf.ptu"))
    assert restored.header.micro_time_resolution == pytest.approx(64e-12, rel=1e-12, abs=0.0)
    assert restored.header.number_of_micro_time_channels == 128


def test_sample_and_irf_share_the_known_delay_axis(producer, tmp_path):
    """A 64 ps sample and its measured IRF retain the same 8.192 ns period."""
    sample = producer.simulate_molecule_mixture(
        [(2, 2, 0.6)], n_pixel=4, dwell=2.0, psf_w0=0.5, seed=7
    )
    irf = producer.simulate_irf_measurement(
        n_pixel=4, dwell=2.0, psf_w0=0.5, brightness=20000.0, seed=11
    )
    means = []
    for name, simulation in (("sample", sample), ("irf", irf)):
        path = tmp_path / f"{name}.ptu"
        producer.write_mixture_ptu(simulation, path)
        restored = tttrlib.TTTR(str(path))
        assert restored.header.number_of_micro_time_channels == 128
        assert restored.header.micro_time_resolution == pytest.approx(64e-12, rel=1e-12, abs=0.0)
        assert restored.header.macro_time_resolution == pytest.approx(8.192e-9)
        photons = np.asarray(restored.event_types) == 0
        means.append(float(np.asarray(restored.micro_times)[photons].mean()) * 64e-3)
    # Quantisation and the finite period bias the photon mean slightly; this
    # independent delay check does not mistake the convolved IRF for lifetime.
    assert means[1] == pytest.approx(0.64, abs=0.025)
    assert means[0] - means[1] == pytest.approx(0.6, abs=0.06)


def test_header_derived_lifetime_matches_explicit_physical_reference(producer, tmp_path):
    """A reopened sample fits in ns without an external correction to its clock."""
    from chisurf.core.datastore import column_names, column_values
    from chisurf.plugins.microscopy.region_mle.core.region_mle import (
        RegionMleSettings,
        build_irf_vv_vh,
        fit_regions,
    )

    sample = producer.simulate_molecule_mixture(
        [producer.Blob(2, 2, 0.6, brightness=20000.0)],
        n_pixel=4,
        dwell=2.0,
        psf_w0=0.5,
        seed=7,
    )
    irf = producer.simulate_irf_measurement(
        n_pixel=4, dwell=2.0, psf_w0=0.5, brightness=20000.0, seed=11
    )
    for name, simulation in (("sample", sample), ("irf", irf)):
        producer.write_mixture_ptu(simulation, tmp_path / f"{name}.ptu")
    stream = tttrlib.TTTR(str(tmp_path / "sample.ptu"))
    instrument = tttrlib.TTTR(str(tmp_path / "irf.ptu"))
    clsm = producer.clsm_from_scan(stream, 4)
    response, background = build_irf_vv_vh(
        instrument,
        detector_chs=[0, 1],
        micro_time_range=(0, 128),
        micro_time_binning=1,
    )
    settings = RegionMleSettings(
        detector_chs=[0, 1],
        micro_time_range=(0, 128),
        irf=response,
        background=background,
        regions=np.ones((4, 4), dtype=np.int32),
        min_photons=100,
        fix_r0=True,
        fix_rho=True,
        p2s_twoIstar=True,
    )
    actual = fit_regions(stream, settings, clsm=clsm, keep_curves=True)
    expected = fit_regions(stream, settings, clsm=clsm, dt=0.064, period=8.192, keep_curves=True)
    assert actual.n_molecules == expected.n_molecules == 1
    assert column_names(actual.dataframe) == column_names(expected.dataframe)
    for index, _name in enumerate(column_names(actual.dataframe)):
        np.testing.assert_allclose(
            column_values(actual.dataframe, index),
            column_values(expected.dataframe, index),
            rtol=1e-8,
            atol=1e-8,
        )
    tau = column_values(actual.dataframe, column_names(actual.dataframe).index("tau"))[0]
    assert tau == pytest.approx(0.6, rel=0.12)
    for curve, reference in zip(actual.model_curves, expected.model_curves, strict=True):
        np.testing.assert_allclose(curve, reference, rtol=1e-8, atol=1e-8)


def test_a_written_scan_reconstructs_and_phasors_without_being_told_the_scanner(producer, tmp_path):
    """A generator scan reopened from PTU/PTO auto-detects its raster and gives a finite phasor.

    The header used to call the 10 ms integration window the macro clock and carried no ``ImgHdr_*`` tags:
    every imaging step showed a ``0x0`` image, and once the image was rebuilt the automatic phasor
    frequency (``micro / macro`` resolution) was ~3e-9 cycles per channel, so every pixel read (1, 0).
    """
    y, x = np.indices((12, 12))
    brightness = 0.2 + np.exp(-0.5 * (((x - 6) / 3) ** 2 + ((y - 6) / 3) ** 2))
    tau = 2.0
    simulation = producer.simulate_clsm_from_maps(
        brightness, np.full((12, 12), tau), brightness_scale=3000.0, n_lifetime_levels=2,
        n_intensity_levels=3, irf_sigma=0.01, irf_center=0.0,
    )
    expected = np.asarray(simulation.intensity)
    for suffix in ("ptu", "pto"):
        path = tmp_path / f"scan.{suffix}"
        assert simulation.tttr.write(str(path))
        stream = tttrlib.TTTR(str(path))
        assert stream.header.macro_time_resolution == pytest.approx(256 * 0.032e-9)
        clsm = tttrlib.CLSMImage(stream, channels=[0], fill=True)
        np.testing.assert_array_equal(np.asarray(clsm.intensity).sum(axis=0), expected)
        phasor = np.asarray(clsm.get_phasor(stream, frequency=-1, minimum_number_of_photons=20))
        g, s = phasor[..., 0], phasor[..., 1]
        lit = (g > -1) & np.isfinite(g)
        omega_tau = 2 * np.pi * tau / 8.192
        assert np.median(g[lit]) == pytest.approx(1 / (1 + omega_tau**2), abs=0.05), suffix
        assert np.median(s[lit]) == pytest.approx(omega_tau / (1 + omega_tau**2), abs=0.05), suffix
