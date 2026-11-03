"""The burst-MLE engine on the in-repository BH SPC-132 sample: every number checked against what it
must be by construction (the burst table, the file header, the photons themselves), not against a
recording of an earlier program. Real photons, nothing generated.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine

from .conftest import BURST_TABLE, CHANNEL_SETTINGS


@pytest.fixture(scope="module")
def session(sample_copy):
    """A session loaded with the sample's burst file and detectors (nothing fitted yet)."""
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    s.add_burst_files([sample_copy / BURST_TABLE])
    s.current_detector = "G|G"
    return s


def test_engine_imports_no_gui():
    import subprocess
    import sys

    code = (
        "import sys; import chisurf.plugins.burst.burst_mle_analysis.engine as e; "
        "bad=[m for m in sys.modules if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6','qtpy','emtk')]; "
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_burst_indices_are_the_photons_of_the_burst_table(session):
    """The photons from ``First Photon`` to ``Last Photon`` (inclusive) of every burst of the file
    on screen, each once (overlapping bursts share theirs), ascending."""
    from pathlib import Path

    table = session.df_bursts
    stem = Path(session.current_filename).stem
    files = [Path(str(f).replace("\\", "/")).stem for f in np.asarray(table["First File"], dtype=object)]
    first = engine.numeric_column(table, "First Photon").astype(np.int64)
    last = engine.numeric_column(table, "Last Photon").astype(np.int64)
    expected = set()
    for f, a, b in zip(files, first, last):
        if f == stem and b >= a:
            expected.update(range(int(a), int(b) + 1))
    indices = np.asarray(session.burst_indices())
    assert expected and indices.tolist() == sorted(expected)


def test_the_channel_width_is_the_header_resolution_times_the_binning(session):
    tttr = session.current_tttr()
    dt1, period = engine.header_time_ns(tttr, 1)
    assert dt1 == pytest.approx(tttr.header.micro_time_resolution * 1e9)
    for binning in (2, 32):
        dt, same_period = engine.header_time_ns(tttr, binning)
        assert dt == pytest.approx(binning * dt1) and same_period == pytest.approx(period)


def _halves(array):
    half = np.asarray(array).size // 2
    return np.asarray(array)[:half], np.asarray(array)[half:]


def test_auto_extract_gives_a_consistent_decay_irf_and_fit(session):
    session.auto_extract()
    outcome = session.outcome
    assert outcome is not None, session.status
    start, stop = session.micro_time_range
    for det in ("G|G", "R|G"):
        for half in _halves(session.irf_np[det]):  # a prompt in each polarisation
            assert np.all(np.isfinite(half)) and half.min() >= 0 and half.max() > 0
    # the decay is the burst photons inside the window, nothing outside it
    for half in _halves(session.decay):
        assert half[:start].sum() == 0 and half[stop:].sum() == 0 and half[start:stop].sum() > 0
    assert outcome.names[0] == "tau" and 0.5 < outcome.x[0] < 5.0
    assert 0.0 < outcome.two_istar < 5.0
    curves = outcome.curves
    assert curves.data.shape == curves.model.shape == curves.residuals.shape
    assert curves.model.sum() == pytest.approx(curves.data.sum(), rel=0.05)  # the model holds the photons


def test_a_narrowed_window_fits_only_what_is_inside(session):
    session.current_detector = "R|G"
    session.auto_extract()
    start, stop = session.micro_time_range
    wide = session.outcome.x[0]
    assert 0.5 < wide < 5.0
    narrow = (start + 2, stop - 10)
    session.settings.micro_time_start, session.settings.micro_time_stop = narrow
    session.build_decay()
    outcome = session.fit()
    for half in _halves(session.decay):
        assert half[: narrow[0]].sum() == 0 and half[narrow[1] :].sum() == 0
    assert outcome.curves.data.size == 2 * (narrow[1] - narrow[0])
    assert outcome.x[0] == pytest.approx(wide, rel=0.25)  # the same molecules, a shorter view


def test_a_fit_without_an_irf_says_why():
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"])
    assert s.fit() is None and "no IRF" in s.status


def test_pure_steps_handle_the_edge_cases():
    assert engine.select_fit_range(None) is None
    assert engine.select_fit_range(np.zeros(8)) is None
    d = np.zeros(20)
    d[3:7] = 10
    d[13:17] = 10
    assert engine.select_fit_range(d) == (2, 8)
    assert engine.header_time_ns(None, 1) is None
    assert engine.window_bins(None, (5, 50), 2) == (5, 50, 5, 50)
    # a window the user set is fitted as set, also past the setup's gate (step 0): before, the gate
    # clamped it and the dragged line snapped back
    assert engine.window_bins([[40, 80]], (5, 50), 4) == (5, 50, 5, 50)
    assert engine.window_bins([[0, 64]], (2, 9), 4) == (2, 9, 2, 9)
    # a window not set (-1, -1) is the first gate, in bins; without gates every channel
    assert engine.window_bins([[40, 80]], (-1, -1), 4) == (10, 20, 10, 20)
    assert engine.window_bins([[0, 64], [64, 128]], (-1, -1), 4, 2) == (0, 16, 0, 16)
    assert engine.window_bins(None, (-1, -1), 4)[:2] == (0, engine.ALL_BINS)
    arr = np.arange(16, dtype=float)
    rolled = engine.process_background(arr, 2, np.zeros(16))
    np.testing.assert_array_equal(rolled[8:], np.roll(arr[8:], 2))
    assert engine.process_background(None, 0, np.zeros(4)).tolist() == [0.0] * 4


def _tau_columns(rows):
    """Columns by name, rows ordered by file (the pool returns files in completion order) and kept in burst order within one."""
    ordered = sorted(enumerate(rows), key=lambda item: (str(item[1].get("First File")), item[0]))
    rows = [r for _i, r in ordered]
    return {
        key: np.array([r.get(key, np.nan) for r in rows], dtype=float)
        for key in sorted(
            {
                k
                for r in rows
                for k in r
                if k.startswith("Tau (") or k.startswith("Number of Photons")
            }
        )
    }


def test_the_batch_fits_every_burst_and_exports_one_row_per_burst(sample_copy, tmp_path):
    """One row per burst and detector; the burst lifetimes scatter around the lifetime of their
    summed decay; one export per detector with the rows of the burst file."""
    import shutil

    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    own = tmp_path / "own"
    shutil.copytree(sample_copy, own)  # the session exports into its own copy
    session.add_burst_files([own / BURST_TABLE])
    pooled = {}
    for det in ("G|G", "R|G"):
        session.current_detector = det
        session.auto_extract()
        pooled[det] = float(session.outcome.x[0])
    seen = []
    session.run_batch(progress=lambda done, total: seen.append((done, total)))
    n = engine.row_count(session.df_bursts)
    assert len(session.burst_results) == 2 * n
    assert seen and seen[-1][0] == seen[-1][1] == n
    mine = _tau_columns(session.burst_results)
    for det in ("G|G", "R|G"):
        taus = mine[f"Tau ({det})"]
        finite = taus[np.isfinite(taus)]
        assert finite.size > 100, det
        assert np.median(finite) == pytest.approx(pooled[det], rel=0.3), det
        photons = mine[f"Number of Photons (fit window) ({det})"]
        fitted = np.isfinite(taus)
        assert np.all(photons[fitted] >= session.settings_of(det).min_photons), det
    written = session.export_results()
    tables = {p.suffix: p for p in written if p.suffix in (".bg4", ".br4")}
    assert sorted(tables) == [".bg4", ".br4"]
    lengths = set()
    for suffix, det in ((".bg4", "G|G"), (".br4", "R|G")):
        lines = tables[suffix].read_text().splitlines()
        assert f"Tau ({det})" in lines[0].split("\t")
        lengths.add(len(lines))
    assert len(lengths) == 1, "both tables have the rows of the same burst file"


def test_session_settings_round_trip():
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"], "SPC-130")
    s.current_detector = "R|G"
    s.set_binning(16)  # first: a window is set in bins of the binning (a new one resets it)
    s.settings.tau, s.settings.fix_gamma, s.settings.micro_time_stop = 2.5, False, 99
    other = engine.MleSession()
    other.apply_settings_payload(s.settings_payload())
    assert other.settings_of("R|G").tau == 2.5 and other.settings_of("R|G").fix_gamma is False
    assert (
        other.settings_of("R|G").micro_time_stop == 99 and other.template.micro_time_binning == 16
    )
    assert other.file_type == "SPC-130" and list(other.detectors) == ["G|G", "R|G"]


def test_the_irf_thresholds_are_background_levels_taken_off_every_bin():
    """VV / VH background level: a fraction of the polarisation's peak, subtracted from every bin
    and clipped at zero -- no floor left under the prompt, no step at its foot."""
    vv = np.array([1.0, 1.0, 5.0, 11.0, 5.0, 1.0, 1.0, 1.0])
    vh = vv * 2.0
    out = engine.process_irf(
        np.hstack([vv, vh]), micro_time_range=(0, 8), binning=1, threshold_vv=0.1, threshold_vh=0.0
    )
    np.testing.assert_allclose(out[:8], np.clip(vv - 1.1, 0.0, None))
    np.testing.assert_allclose(out[8:], vh)  # a level of zero takes nothing off
