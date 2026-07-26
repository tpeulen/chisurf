"""A multi-run ALV file must yield one *distinct* curve per run.

The ALV-5000/6000 "Correlation (Multi, Averaged)" mode writes the average and
every single run as extra columns of one table. ``openASC_old`` collected them
into ``data = [[]] * len(curvelist)``, which aliases a *single* list into every
slot: each row appended all of its columns to that one list, so every curve came
back as the same row-major-interleaved array with ``n_lags * n_curves`` points
and each lag time repeated once per curve. Duplicated lag times then make
``np.diff(times)`` zero in the FCS noise model.

The file below mirrors the header of a real ALV-5000/E-WIN cross-correlation
export (one average + three runs) so the reader takes the very same branch.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: Lag times [ms] of the synthetic correlation table.
LAG_TIMES = [2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4, 1.0e-3]

#: One column per curve: the average followed by three single runs. The values
#: are deliberately far apart so an interleaved read cannot pass by accident.
CURVES = [
    [0.30, 0.25, 0.20, 0.15, 0.10],
    [0.31, 0.26, 0.21, 0.16, 0.11],
    [0.32, 0.27, 0.22, 0.17, 0.12],
    [0.33, 0.28, 0.23, 0.18, 0.13],
]

DURATION_S = 20.0


def _write_multi_run_asc(path: pathlib.Path) -> pathlib.Path:
    """Write a minimal ALV-5000 multi-run cross-correlation export.

    Parameters
    ----------
    path : pathlib.Path
        Directory the file is written to.

    Returns
    -------
    pathlib.Path
        Path of the written ``.ASC`` file.
    """
    lines = [
        "ALV-5000/E-WIN Data",
        'Date :\t"06.12.2013"',
        'Time :\t"12:58:32"',
        "Temperature [K] :\t     298.16000",
        "Viscosity [cp]  :\t       0.89000",
        "Refractive Index:\t       1.33200",
        "Wavelength [nm] :\t     488.00000",
        f"Duration [s]    :\t        {DURATION_S:.0f}",
        "Runs            :\t         3",
        'Mode            :\t"SINGLE CROSS CH0"',
        "MeanCR0 [kHz]   :\t     100.35390",
        "MeanCR1 [kHz]   :\t      96.75777",
        "",
        '"Correlation (Multi, Averaged)"',
        '"Lag [ms]"\t"Average"\t" 1, 100.000"\t" 2, 100.000"\t" 3, 100.000"\t',
    ]
    for row, lag in enumerate(LAG_TIMES):
        columns = "\t".join(f"  {curve[row]:.5E}" for curve in CURVES)
        lines.append(f"  {lag:.5E}\t{columns}\t")
    lines += ["", '"Count Rate"']
    for i in range(8):
        t = DURATION_S * (i + 1) / 8.0
        lines.append(f"   {t:12.5f}\t{100.0 + i:12.5f}\t{96.0 + i:12.5f}")

    asc = path / "ALV-5000_multi_run.ASC"
    asc.write_text("\n".join(lines) + "\n", encoding="iso8859_15")
    return asc


@pytest.fixture(name="multi_run_asc")
def fixture_multi_run_asc(tmp_path):
    """Path of a synthetic ALV-5000 multi-run file."""
    return _write_multi_run_asc(tmp_path)


def test_every_run_keeps_its_own_correlation(multi_run_asc):
    """The columns become separate curves instead of one shared, aliased list."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import openASC_old

    correlations = openASC_old(multi_run_asc)["Correlation"]

    assert len(correlations) == len(CURVES)
    for correlation, expected in zip(correlations, CURVES):
        correlation = np.asarray(correlation)
        # `[[]] * n` gave every curve len(LAG_TIMES) * len(CURVES) rows.
        assert correlation.shape == (len(LAG_TIMES), 2)
        np.testing.assert_allclose(correlation[:, 0], LAG_TIMES)
        np.testing.assert_allclose(correlation[:, 1], expected)


def test_lag_times_are_strictly_increasing(multi_run_asc):
    """Interleaving repeated each lag once per curve, zeroing ``np.diff``."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import read_asc

    datasets = read_asc(multi_run_asc)

    assert len(datasets) == len(CURVES)
    for dataset in datasets:
        times = np.asarray(dataset["correlation_times"])
        assert times.shape == (len(LAG_TIMES),)
        assert np.all(np.diff(times) > 0.0)
        assert np.all(np.isfinite(dataset["correlation_amplitude_weights"]))


def test_the_runs_differ_from_each_other(multi_run_asc):
    """All curves were byte-identical while they shared one list."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import read_asc

    amplitudes = [np.asarray(d["correlation_amplitudes"]) for d in read_asc(multi_run_asc)]

    for other in amplitudes[1:]:
        assert not np.array_equal(amplitudes[0], other)
