"""Tests for the shared hidden-Markov-model plugin (core, RPC, CLI)."""

import json

import numpy as np
import pytest

from chisurf.plugins.core.hmm.api.models import HmmSettings
from chisurf.plugins.core.hmm.backend.services import fit_handler, list_methods, scan_handler
from chisurf.plugins.core.hmm.core.analysis import (
    as_matrix,
    dwell_times,
    fit_traces,
    scan_state_counts,
    state_segments,
    transition_rates,
)


def make_trace(n_bins=3000, seed=0):
    """Return a two-state trace and its generating state path."""
    rng = np.random.default_rng(seed)
    transmat = np.array([[0.98, 0.02], [0.05, 0.95]])
    means = np.array([[20.0], [60.0]])
    states = np.zeros(n_bins, dtype=int)
    for t in range(1, n_bins):
        states[t] = rng.choice(2, p=transmat[states[t - 1]])
    return means[states] + rng.normal(0, 4, size=(n_bins, 1)), states


def test_as_matrix_accepts_the_shapes_callers_actually_pass():
    single = np.zeros((10, 2))
    passed_through, lengths = as_matrix(single)
    np.testing.assert_array_equal(passed_through, single)
    assert lengths == [10]
    # A 1-D trace is one feature.
    X, lengths = as_matrix(np.arange(5.0))
    assert X.shape == (5, 1) and lengths == [5]
    # Several sequences are concatenated, and their lengths are kept.
    X, lengths = as_matrix([np.zeros((4, 2)), np.ones((6, 2))])
    assert X.shape == (10, 2) and lengths == [4, 6]
    with pytest.raises(ValueError, match="same number of features"):
        as_matrix([np.zeros((4, 2)), np.ones((6, 3))])
    with pytest.raises(ValueError, match="no data"):
        as_matrix([])


def test_a_list_of_one_dimensional_traces_is_several_sequences():
    """The shape a caller with three repeats actually passes.

    Read as one matrix instead, three 6000-bin traces become three bins of 6000
    channels and the fit silently estimates millions of parameters.
    """
    X, lengths = as_matrix([np.zeros(40), np.ones(60), np.zeros(50)])
    assert X.shape == (150, 1)
    assert lengths == [40, 60, 50]
    # A nested list of plain numbers is still one matrix: that is the JSON shape
    # the RPC service receives, rows being time bins.
    X, lengths = as_matrix([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    assert X.shape == (3, 2) and lengths == [3]


def test_dwell_times_do_not_run_across_a_sequence_boundary():
    states = [0, 0, 1, 1, 1, 0, 0, 0]
    dwells = dwell_times(states, time_step=2.0)
    assert dwells[0] == [4.0, 6.0]
    assert dwells[1] == [6.0]
    # The same labels split into two sequences: the run at the seam is two visits.
    split = dwell_times([0, 0, 0, 0], lengths=[2, 2])
    assert split[0] == [2.0, 2.0]


def test_state_segments_describe_the_path_as_runs():
    assert state_segments([0, 0, 1, 1, 0]) == [(0, 0, 2), (1, 2, 4), (0, 4, 5)]


def test_transition_rates_form_a_generator_matrix():
    transmat = np.array([[0.98, 0.02], [0.05, 0.95]])
    rates = transition_rates(transmat, time_step=0.001)
    assert rates[0, 1] == pytest.approx(20.0)
    assert rates[1, 0] == pytest.approx(50.0)
    np.testing.assert_allclose(rates.sum(axis=1), 0.0, atol=1e-9)


def test_fit_recovers_the_states_and_orders_them_dimmest_first():
    trace, truth = make_trace()
    fit = fit_traces(trace, HmmSettings(n_states=2, time_step=1e-3))

    assert fit.n_states == 2
    means = np.asarray(fit.means).ravel()
    assert means[0] < means[1], "state 0 must be the dimmest"
    np.testing.assert_allclose(means, [20, 60], atol=1.5)
    assert np.mean(np.asarray(fit.states) == truth) > 0.95
    # Two summaries, occupancies summing to one, dwell times in seconds.
    assert sum(s.occupancy for s in fit.summaries) == pytest.approx(1.0)
    assert fit.summaries[0].mean_dwell < 1.0
    assert len(fit.dwell_times) == 2
    np.testing.assert_allclose(np.sum(fit.transmat, axis=1), 1.0)


def test_several_traces_are_fitted_as_separate_sequences():
    first, _ = make_trace(1500, seed=1)
    second, _ = make_trace(1500, seed=2)
    fit = fit_traces([first, second], HmmSettings(n_states=2))
    assert fit.lengths == [1500, 1500]
    assert len(fit.states) == 3000


def test_state_scan_prefers_the_generating_state_count():
    trace, _ = make_trace()
    scan = scan_state_counts(trace, HmmSettings(), min_states=1, max_states=4)
    assert scan.n_states == [1, 2, 3, 4]
    assert scan.best_bic == 2


def test_rpc_handlers_round_trip_through_json():
    trace, _ = make_trace(1200)
    payload = fit_handler(
        traces=trace.tolist(), settings={"n_states": 2, "time_step": 0.001}
    )
    # Must survive serialisation: this is what crosses the ZMQ boundary.
    restored = json.loads(json.dumps(payload))
    assert restored["n_states"] == 2
    assert restored["settings"]["time_step"] == 0.001
    assert len(restored["states"]) == 1200
    assert np.asarray(restored["means"]).shape == (2, 1)

    scan = json.loads(json.dumps(scan_handler(traces=trace.tolist(), max_states=3)))
    assert scan["n_states"] == [1, 2, 3]
    assert set(list_methods()) == {"hmm.fit", "hmm.scan"}


def test_settings_reject_unknown_enumerations_early():
    with pytest.raises(ValueError, match="covariance_type"):
        HmmSettings(covariance_type="banana")
    with pytest.raises(ValueError, match="decode"):
        HmmSettings(decode="beam")
    # Unknown keys are ignored rather than crashing an older client.
    assert HmmSettings.from_dict({"n_states": 3, "nonsense": 1}).n_states == 3


def test_cli_fits_a_text_trace(tmp_path):
    from click.testing import CliRunner

    from chisurf.plugins.core.hmm.cli.main import cli

    trace, _ = make_trace(800)
    path = tmp_path / "trace.csv"
    np.savetxt(path, trace, delimiter=",")

    result = CliRunner().invoke(cli, ["fit", str(path), "--states", "2"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["n_states"] == 2
    # Without -o the per-bin path is left out; the summary is what is printed.
    assert "states" not in payload
    assert len(payload["summaries"]) == 2

    out = tmp_path / "fit.json"
    result = CliRunner().invoke(cli, ["fit", str(path), "--states", "2", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert len(json.loads(out.read_text())["states"]) == 800
