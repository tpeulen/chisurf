"""The ALEX Suite's own analyses, against data whose answer is known.

Nothing here touches Qt. The three things this plugin computes that no other
ChiSurf tool does — the ALEX period, the shared-shape titration fit and the
legacy CSV layout — are checked against synthetic data with a planted answer,
because "it produced numbers" is not a test of any of them.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from chisurf.plugins.burst.alex_suite.api import (
    Condition,
    Corrections,
    LegacyExport,
    Metadata,
    Thresholds,
    build_stack,
    es_histograms,
    fit_binding,
    fit_shared_gaussians,
    run_titration,
    write_legacy_export,
)


def burst_table(n, e_true, *, s_true=0.5, size=200, seed=0):
    """Synthesise a burst table whose bursts have a known E and S."""
    rng = np.random.default_rng(seed)
    total = rng.poisson(size, n).astype(float) + 20.0
    green = total * s_true
    i_da = rng.binomial(green.astype(int), e_true).astype(float)
    return {
        "Number of Photons (green)": green - i_da,
        "Number of Photons (red)": i_da,
        "Number of Photons (yellow)": total - green,
        "Duration (ms)": np.full(n, 1.0),
    }


def two_population_table(n, frac_high, *, low=0.25, high=0.65, seed=0):
    """Return a table mixing low-E and high-E populations in a known ratio."""
    n_high = int(round(n * frac_high))
    a = burst_table(n - n_high, low, seed=seed)
    b = burst_table(n_high, high, seed=seed + 1000)
    return {key: np.concatenate([a[key], b[key]]) for key in a}


# ── histograms ──────────────────────────────────────────────────────────


def test_histogram_finds_the_planted_efficiency():
    """The E histogram peaks at the efficiency the bursts were drawn with."""
    result = es_histograms(
        burst_table(5000, 0.4), thresholds=Thresholds(total_min=0), bins=(101, 101)
    )
    peak = result.e_centres[int(np.argmax(result.e_hist))]
    assert abs(peak - 0.4) < 0.02
    assert result.hist_2d.shape == (101, 101)
    assert result.e.size == result.n_bursts_total == 5000


def test_stoichiometry_gate_does_not_empty_a_non_alex_table():
    """A table without an acceptor-excitation channel keeps all its bursts.

    S is NaN there, and every comparison against NaN is False — so a gate
    applied without checking would select *nothing* while looking like a
    stoichiometry filter that was simply strict.
    """
    table = burst_table(500, 0.5)
    del table["Number of Photons (yellow)"]
    result = es_histograms(table, thresholds=Thresholds(total_min=0))
    assert result.e.size == 500
    assert not np.isfinite(result.s).any()


def test_gamma_moves_the_efficiency_the_way_the_correction_says():
    """γ > 1 pulls E down; the corrected peak follows the closed form."""
    table = burst_table(20000, 0.5, seed=7)
    plain = es_histograms(table, thresholds=Thresholds(total_min=0))
    corrected = es_histograms(
        table, corrections=Corrections(gamma=2.0), thresholds=Thresholds(total_min=0)
    )
    expected = 0.5 / (0.5 + 2.0 * 0.5)
    assert abs(corrected.e_centres[int(np.argmax(corrected.e_hist))] - expected) < 0.03
    assert corrected.e.mean() < plain.e.mean()


def test_unrecognisable_columns_are_refused_rather_than_guessed():
    """A table whose channels cannot be identified raises, naming the problem."""
    with pytest.raises(ValueError, match="could not identify"):
        es_histograms({"a": np.arange(10.0), "b": np.arange(10.0)})


# ── titration ───────────────────────────────────────────────────────────


def _series(kd=50.0, hill=1.0, concentrations=(0.0, 5.0, 15.0, 50.0, 150.0, 500.0, 2000.0)):
    """Conditions whose bound fraction follows a known isotherm."""
    conditions = []
    for i, c in enumerate(concentrations):
        frac = c**hill / (kd**hill + c**hill) if c > 0 else 0.0
        conditions.append(
            Condition(
                concentration=c,
                source=two_population_table(4000, frac, seed=i * 17),
                label=f"{c:g} nM",
            )
        )
    return conditions


def test_titration_recovers_the_planted_kd():
    """The whole pipeline gets the centres, the fractions and K_d back."""
    result = run_titration(_series(), n_components=2, thresholds=Thresholds(total_min=0))
    centres = np.sort(result.fit.centres)
    assert abs(centres[0] - 0.25) < 0.03
    assert abs(centres[1] - 0.65) < 0.03
    assert result.binding is not None
    assert abs(result.binding.kd - 50.0) / 50.0 < 0.15
    assert abs(result.binding.hill - 1.0) < 0.2


def test_the_isotherm_is_read_from_the_population_that_grows():
    """With two complementary populations the *rising* one is the report.

    Both spans are equal, so "largest change" is a coin toss — and the losing
    half of that toss plots the free species and labels a falling curve with a
    K_d. Arithmetically fine; unreadable as a binding isotherm.
    """
    result = run_titration(_series(), n_components=2, thresholds=Thresholds(total_min=0))
    reported = result.fit.fractions[:, result.component]
    assert reported[-1] > reported[0]
    # And it is the high-FRET population, which is the one the ligand produces.
    assert result.fit.centres[result.component] == result.fit.centres.max()


def test_shared_shape_means_one_centre_for_the_whole_series():
    """Every condition is described by the same two positions and widths."""
    stack = build_stack(_series(), thresholds=Thresholds(total_min=0))
    fit = fit_shared_gaussians(stack, 2)
    assert fit.centres.shape == (2,)
    assert fit.widths.shape == (2,)
    assert fit.amplitudes.shape == (len(stack), 2)
    # Amplitudes are non-negative: a negative "amount of a species" would make
    # the fraction the isotherm is read from stop being a fraction.
    assert (fit.amplitudes >= 0).all()
    assert np.allclose(fit.fractions.sum(axis=1), 1.0)


def test_centres_come_back_sorted_so_component_0_is_stable():
    """Component 0 is the lowest-E population, whatever the optimiser found first."""
    stack = build_stack(_series(), thresholds=Thresholds(total_min=0))
    fit = fit_shared_gaussians(stack, 3)
    assert (np.diff(fit.centres) >= 0).all()


def test_fixed_shape_holds_the_starting_values():
    """``fix_centres``/``fix_widths`` is the old 'fixed x0 and sigma' preset."""
    stack = build_stack(_series(), thresholds=Thresholds(total_min=0))
    start_centres = np.array([0.2, 0.7])
    start_widths = np.array([0.05, 0.05])
    fit = fit_shared_gaussians(
        stack, 2, centres=start_centres, widths=start_widths, fix_centres=True, fix_widths=True
    )
    assert np.allclose(fit.centres, start_centres)
    assert np.allclose(fit.widths, start_widths)


def test_stack_is_ordered_by_concentration():
    """A stack plot that is not monotonic in the titrant reads as noise."""
    conditions = list(reversed(_series()))
    stack = build_stack(conditions, thresholds=Thresholds(total_min=0))
    assert (np.diff(stack.concentrations) > 0).all()


def test_one_site_model_holds_the_hill_coefficient_at_one():
    """``one_site`` is the Hill model with n fixed."""
    concentrations = np.array([1.0, 10.0, 30.0, 100.0, 300.0, 1000.0])
    fractions = concentrations / (100.0 + concentrations)
    fit = fit_binding(concentrations, fractions, model="one_site")
    assert fit.hill == 1.0
    assert abs(fit.kd - 100.0) / 100.0 < 0.05


def test_a_titration_needs_more_than_one_condition():
    """One measurement is not a series, and saying so beats a shapeless error."""
    with pytest.raises(ValueError, match="at least two"):
        build_stack(_series(concentrations=(0.0,)))


# ── the legacy export ───────────────────────────────────────────────────


def test_legacy_export_writes_the_five_files_with_their_section_headers(tmp_path):
    """The layout is the contract: five files, quoted, with the old headers."""
    table = burst_table(2000, 0.45)
    histograms = es_histograms(table, thresholds=Thresholds(total_min=0), bins=(51, 51))
    written = write_legacy_export(
        tmp_path / "run",
        histograms,
        metadata=Metadata(sample_name="dsDNA", buffer="TE"),
        search_parameters={"min_photons": 30},
        parts=LegacyExport(original_bursts=True),
        burst_table=table,
    )
    names = [p.name for p in written]
    assert names == [
        "run_meta.csv",
        "run_hist_E.csv",
        "run_hist_S.csv",
        "run_hist_2D.csv",
        "run_original_bursts.csv",
    ]

    meta = (tmp_path / "run_meta.csv").read_text()
    for section in (
        "BURST SEARCH PARAMETERS",
        "THRESHOLDS",
        "EXPERIMENTAL",
        "ACCURATE FRET",
        "PLOT OPTIONS",
    ):
        assert f'"{section}"' in meta
    assert '"sample_name","dsDNA"' in meta

    with open(tmp_path / "run_hist_E.csv", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][:3] == ["BIN CENTERS E", "E HISTOGRAM", "E FIT"]
    assert len(rows) == 1 + histograms.e_centres.size

    with open(tmp_path / "run_hist_2D.csv", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["2D HISTOGRAM"]
    assert len(rows) == 1 + histograms.hist_2d.shape[0]


def test_legacy_export_pads_a_fit_computed_on_another_grid(tmp_path):
    """A short fit column pads rather than truncating the histogram beside it."""
    histograms = es_histograms(
        burst_table(500, 0.5), thresholds=Thresholds(total_min=0), bins=(31, 31)
    )
    write_legacy_export(
        tmp_path / "run",
        histograms,
        parts=LegacyExport(metadata=False, s_histogram=False, histogram_2d=False),
        e_fit=np.ones(5),
    )
    with open(tmp_path / "run_hist_E.csv", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 1 + 31
    assert rows[-1][2] == "0.0"


def test_legacy_export_refuses_to_invent_a_burst_table(tmp_path):
    """Asking for the bursts without giving them is an error, not an empty file."""
    histograms = es_histograms(burst_table(100, 0.5), thresholds=Thresholds(total_min=0))
    with pytest.raises(ValueError, match="original_bursts"):
        write_legacy_export(
            tmp_path / "run",
            histograms,
            parts=LegacyExport(
                metadata=False,
                e_histogram=False,
                s_histogram=False,
                histogram_2d=False,
                original_bursts=True,
            ),
        )
