"""Tests for the Gopich-Szabo plugin (core orchestration, RPC, CLI, GUI)."""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.plugins.burst.burst_gs import core
from chisurf.plugins.burst.burst_gs.backend import services


# ──────────────────────────────────────────────────────────────────────────────
# Simulation and analysis
# ──────────────────────────────────────────────────────────────────────────────
def test_the_simulation_reproduces_its_own_equilibrium():
    """More time is spent in the state that is harder to leave."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.0, 1.0), 50e3, 60, 300, seed=2)
    # E = 0 and E = 1, so the colour *is* the state: the acceptor fraction must
    # match the equilibrium population of state 2, k12 / (k12 + k21) = 0.75.
    assert bursts.colors.mean() == pytest.approx(0.75, abs=0.02)


@pytest.mark.slow
def test_analyse_recovers_the_simulated_kinetics():
    """The plugin's own entry point recovers rates and efficiencies."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 250, 200, seed=5)
    analysis = core.analyse(
        bursts, n_states=2, initial_rates=[1e3, 1e3], initial_efficiencies=[0.3, 0.7]
    )
    assert analysis.fit.rate_matrix[1, 0] == pytest.approx(3000.0, rel=0.15)
    assert analysis.fit.rate_matrix[0, 1] == pytest.approx(1000.0, rel=0.15)
    assert "Rates" in analysis.report()
    assert analysis.fit.relaxation_times[0] == pytest.approx(1.0 / 4000.0, rel=0.2)


@pytest.mark.slow
def test_the_h2mm_cross_check_agrees():
    """Two independent engines with different time conventions must agree.

    This is the strongest available check on either method: H2MM fits a
    per-tick transition *probability* with its own EM code, this fits a *rate*
    by direct likelihood maximisation. Nothing but correctness would make them
    land on the same numbers.
    """
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 250, 200, seed=5)
    analysis = core.analyse(
        bursts, n_states=2, initial_rates=[1e3, 1e3], initial_efficiencies=[0.3, 0.7],
        cross_check_h2mm=True,
    )
    comparison = analysis.h2mm
    assert "error" not in comparison, comparison.get("error")
    assert comparison["max_efficiency_difference"] < 0.02
    assert comparison["ratio_k12"] == pytest.approx(1.0, abs=0.15)
    assert comparison["ratio_k21"] == pytest.approx(1.0, abs=0.15)


def test_the_transition_scan_is_skipped_for_more_than_two_states():
    """The transition-state construction is defined for a single barrier."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 20, 100, seed=6)
    analysis = core.analyse(
        bursts, n_states=3, max_iterations=40, scan_transition_time=True
    )
    assert analysis.transit_times.size == 0
    assert "transition_scan_skipped" in analysis.info


def test_a_failed_cross_check_does_not_take_the_fit_down():
    """A broken comparison reports an error rather than raising."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 10, 60, seed=8)
    analysis = core.analyse(bursts, n_states=2, max_iterations=30)
    # A negative tick cannot produce a valid discrete-time layout.
    comparison = core.compare_with_h2mm(bursts, analysis.fit, n_states=2, tick=-1.0)
    assert "error" in comparison


# ──────────────────────────────────────────────────────────────────────────────
# The H2MM tick, and the memory it commits
# ──────────────────────────────────────────────────────────────────────────────
def test_a_fine_tick_is_coarsened_to_fit_the_memory_budget():
    """A tick fine enough to give every photon its own gap must be refused.

    H2MM allocates a propagator **and** an ``n_states**4`` rho tensor per
    distinct inter-photon gap. Choosing the tick from a fitted relaxation time
    is unbounded from below, so a fit that wanders towards fast rates asks for
    a cache proportional to the photon count — gigabytes, allocated at once,
    from a parameter nobody set. This pins the coarsening that prevents it.
    """
    rng = np.random.default_rng(0)
    gaps = rng.exponential(2e-5, 200_000)
    # 1 ps: every one of the 200,000 gaps rounds to its own integer.
    tick, note = core.choose_h2mm_tick(gaps, [1e-3], n_states=5, tick=1e-12)
    assert tick > 1e-12
    assert "coarsened" in note

    slots = np.unique(np.round(gaps / tick)).size
    committed = slots * 8 * (5 ** 2 + 5 ** 4)
    assert committed <= core.H2MM_MEMORY_BUDGET


def test_a_reasonable_tick_is_left_alone():
    """The budget must not silently degrade a tick that was already fine."""
    rng = np.random.default_rng(1)
    gaps = rng.exponential(2e-5, 20_000)
    tick, note = core.choose_h2mm_tick(gaps, [2.5e-4], n_states=2)
    assert note == ""
    assert tick == pytest.approx(2.5e-4 / 40.0)


def test_more_states_force_a_coarser_tick():
    """The cache grows as the fourth power of the state count, so the tick must too."""
    rng = np.random.default_rng(2)
    gaps = rng.exponential(2e-5, 100_000)
    two, _ = core.choose_h2mm_tick(gaps, [1e-3], n_states=2, tick=1e-11)
    five, _ = core.choose_h2mm_tick(gaps, [1e-3], n_states=5, tick=1e-11)
    assert five > two


def test_a_non_positive_tick_is_refused():
    """Zero or negative would still produce a monotone sequence, and wrong rates."""
    with pytest.raises(ValueError, match="positive duration"):
        core.choose_h2mm_tick([1e-5, 2e-5], [1e-4], tick=0.0)


def test_gaps_without_any_positive_value_are_refused():
    """Nothing to discretise is an error, not an empty cache."""
    with pytest.raises(ValueError, match="no positive inter-photon gaps"):
        core.choose_h2mm_tick([0.0, -1.0], [1e-4])


def test_the_report_and_dict_survive_a_minimal_run():
    """``to_dict`` is JSON-serialisable, which the RPC layer depends on."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 10, 60, seed=9)
    analysis = core.analyse(bursts, n_states=2, max_iterations=30)
    payload = analysis.to_dict()
    assert json.loads(json.dumps(payload))["fit"]["n_photons"] == bursts.n_photons


# ──────────────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────────────
def test_an_unknown_macro_time_resolution_is_refused(tmp_path, monkeypatch):
    """A missing tick must stop the run, not silently produce rescaled rates."""
    import pandas as pd

    frame = pd.DataFrame(
        {"First File": ["a"], "First Photon": [0], "Last Photon": [10]}
    )

    class _Header:
        macro_time_resolution = 0.0

    class _Tttr:
        header = _Header()
        macro_times = np.arange(10)
        routing_channels = np.zeros(10, dtype=int)
        micro_times = np.zeros(10, dtype=int)

    monkeypatch.setattr(core, "load_bur_dataframe", lambda paths: frame)
    monkeypatch.setattr(core, "load_tttrs_for_dataframe", lambda *a, **k: {"a": _Tttr()})
    with pytest.raises(ValueError, match="macro-time resolution"):
        core.load_photons([tmp_path / "x.bur"], tmp_path)


def test_loading_converts_ticks_to_seconds(tmp_path, monkeypatch):
    """Macro-time ticks become real seconds, which is what the rates are in."""
    import pandas as pd

    frame = pd.DataFrame(
        {"First File": ["a"], "First Photon": [0], "Last Photon": [20]}
    )
    channels = np.tile([0, 1], 10)

    class _Tttr:
        header = type("H", (), {"macro_time_resolution": 1e-7})()
        macro_times = np.arange(20) * 10
        routing_channels = channels
        micro_times = np.zeros(20, dtype=int)

    monkeypatch.setattr(core, "load_bur_dataframe", lambda paths: frame)
    monkeypatch.setattr(core, "load_tttrs_for_dataframe", lambda *a, **k: {"a": _Tttr()})
    bursts, info = core.load_photons([tmp_path / "x.bur"], tmp_path, min_photons=5)
    assert info["macro_time_resolution"] == pytest.approx(1e-7)
    # Ten ticks of 100 ns between photons.
    assert np.diff(bursts.times)[0] == pytest.approx(1e-6)
    assert info["photons_per_stream"] == [10, 10]


def test_the_sentinel_rows_of_a_bur_table_are_not_looked_up():
    """The ``2n+1`` interleave must not send ``"0"`` to the TTTR loader.

    A sentinel row's ``First File`` is not a measurement, and ``tttrlib`` does
    not raise on the resulting path — it returns an empty object whose header
    reports a negative macro-time resolution.
    """
    import pandas as pd

    from chisurf.core.fluorescence.burst.photons import load_tttrs_for_dataframe

    frame = pd.DataFrame(
        {"First File": ["0", "", "nan"], "First Photon": [0, 0, 0], "Last Photon": [0, 0, 0]}
    )
    assert load_tttrs_for_dataframe(frame, ".", file_type="auto") == {}


def test_a_real_bur_table_loads_despite_its_sentinel_rows():
    """The guardrail the monkeypatched loading tests above cannot give.

    Reads the repo's own Becker&Hickl fixture, whose first unique ``First File``
    value is the sentinel ``"0"``: the resolution has to come from a real
    measurement, not from the empty object that placeholder loads as.
    """
    plugins_burst = pathlib.Path(__file__).resolve().parents[2]
    data_dir = plugins_burst / "burst_selection/tests/data/bh_spc132_sm_dna"
    bur = data_dir / "burstwise_All 0.1000#15" / "bi4_bur" / "m000.bur"
    if not bur.exists():
        pytest.skip("burst fixture not available")

    bursts, info = core.load_photons([bur], data_dir, file_type="auto")
    assert info["macro_time_resolution"] == pytest.approx(1.35e-08)
    # ``Last Photon`` is inclusive (RF-804), so every one of the table's 203
    # non-sentinel rows yields a burst. This fixture predates the writer's
    # convention fix and stores exclusive stops, hence one extra photon per
    # burst here — the counts pin the reader, not the fixture.
    assert info["n_bursts"] == 203
    assert info["n_photons"] == 15512
    assert bursts.times[-1] > 0.0


# ──────────────────────────────────────────────────────────────────────────────
# RPC
# ──────────────────────────────────────────────────────────────────────────────
def test_the_rpc_fit_accepts_a_simulation_request():
    """``burst_gs.jobs.fit`` can generate its own photons."""
    reply = services.fit(
        {
            "simulate": {"k_forward": 3000.0, "k_backward": 1000.0, "n_bursts": 20,
                         "photons_per_burst": 80, "seed": 3},
            "n_states": 2,
            "max_iterations": 60,
        }
    )
    assert reply["ok"], reply.get("error")
    assert reply["result"]["fit"]["n_bursts"] == 20


def test_the_rpc_fit_accepts_flat_photon_arrays():
    """The flat ``times``/``colors``/``offsets`` layout round-trips."""
    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 8, 60, seed=4)
    reply = services.fit(
        {
            "times": bursts.times.tolist(),
            "colors": bursts.colors.tolist(),
            "offsets": bursts.offsets.tolist(),
            "n_colors": 2,
            "n_states": 2,
            "max_iterations": 40,
        }
    )
    assert reply["ok"], reply.get("error")
    assert reply["result"]["fit"]["n_photons"] == bursts.n_photons


def test_the_rpc_log_likelihood_matches_the_library():
    """The service is a thin wrapper, and stays one."""
    from chisurf.core.fluorescence.burst import gopich_szabo as gs

    bursts = core.simulate_two_state(3000.0, 1000.0, (0.25, 0.75), 50e3, 6, 50, seed=10)
    matrix = gs.rate_matrix_from_rates([3000.0, 1000.0], 2)
    reply = services.log_likelihood(
        {
            "times": bursts.times.tolist(),
            "colors": bursts.colors.tolist(),
            "offsets": bursts.offsets.tolist(),
            "n_colors": 2,
            "rate_matrix": matrix.tolist(),
            "efficiencies": [0.25, 0.75],
        }
    )
    assert reply["ok"]
    assert reply["log_likelihood"] == pytest.approx(
        gs.log_likelihood(bursts, matrix, gs.emission_from_efficiencies([0.25, 0.75]))
    )


def test_a_malformed_rpc_request_reports_an_error():
    """A bad payload returns ``ok: False``, never an exception across the wire."""
    reply = services.fit({"times": [[0.0, 1.0]]})
    assert reply["ok"] is False
    assert "colors" in reply["error"]


def test_every_declared_rpc_method_is_registered():
    """The manifest and the dispatcher registration must not drift apart."""
    manifest = json.loads(
        (pathlib.Path(__file__).parent.parent / "manifest.json").read_text()
    )
    registered: list[str] = []
    services.register_services(
        type("D", (), {"register": lambda self, name, fn: registered.append(name)})()
    )
    assert sorted(registered) == sorted(m["name"] for m in manifest["rpc_methods"])


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def test_the_cli_can_simulate_and_report(tmp_path):
    """``burst-gs --simulate`` runs headless and writes JSON."""
    from click.testing import CliRunner

    from chisurf.plugins.burst.burst_gs.cli import cli

    out = tmp_path / "result.json"
    result = CliRunner().invoke(
        cli,
        ["--simulate", "--sim-bursts", "25", "--sim-photons", "80",
         "--max-iterations", "150", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "Rates" in result.output
    payload = json.loads(out.read_text())
    assert payload["fit"]["n_bursts"] == 25


def test_the_cli_refuses_to_run_with_no_input():
    """No files and no ``--simulate`` is a usage error, not an empty fit."""
    from click.testing import CliRunner

    from chisurf.plugins.burst.burst_gs.cli import cli

    result = CliRunner().invoke(cli, [])
    assert result.exit_code != 0
    assert "simulate" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# View model
# ──────────────────────────────────────────────────────────────────────────────
def test_the_view_model_refuses_to_run_without_data():
    """``can_run`` explains what is missing rather than failing later."""
    from chisurf.plugins.burst.burst_gs.gui.view_model import BurstGsViewModel

    model = BurstGsViewModel()
    assert "burst table" in model.can_run()
    model.use_simulation = True
    assert model.can_run() == ""


def test_the_view_model_produces_rows_and_series():
    """Every source named in the view spec is backed by the view model."""
    import json as _json

    from chisurf.plugins.burst.burst_gs.gui.view_model import BurstGsViewModel

    model = BurstGsViewModel()
    model.use_simulation = True
    model.sim_n_bursts = 20
    model.sim_photons_per_burst = 80
    model.max_iterations = 80
    model.scan_transition_time = True
    model.transit_points = 6
    assert model.compute() is True

    assert len(model.rate_rows()) == 2
    assert len(model.state_rows()) == 2
    assert model.transit_series() and len(model.transit_series()[0]["x"]) == 6
    assert model.efficiency_series()

    spec = _json.loads(
        (pathlib.Path(__file__).parent.parent / "gui" / "burst_gs.view.json").read_text()
    )
    sources: list[tuple[str, str]] = []

    def walk(section):
        for child in section.get("sections", []):
            if "source" in child:
                sources.append((child["source"], child.get("type", "")))
            walk(child)

    walk(spec)
    assert sources, "the view spec declares no sources — the walk is broken"
    for source, kind in sources:
        assert hasattr(model, source), f"the view spec reads '{source}', the model has none"
        # AutoForm's plot and info widgets both bail out on a source that is not
        # *callable*, rendering an empty panel with no error anywhere. A
        # property of the right name passes every attribute check and still
        # shows nothing, so callability is the property worth asserting.
        assert not isinstance(getattr(type(model), source, None), property), (
            f"'{source}' feeds a {kind} section and must be a method, not a property"
        )
        assert callable(getattr(model, source)), f"'{source}' is not callable"
        assert getattr(model, source)(), f"'{source}' rendered nothing after a run"


def test_a_failed_load_is_reported_not_raised():
    """A missing file leaves an explanation in the report and returns False."""
    from chisurf.plugins.burst.burst_gs.gui.view_model import BurstGsViewModel

    model = BurstGsViewModel()
    model.bur_files = ["/nonexistent/does-not-exist.bur"]
    assert model.compute() is False
    assert "Could not load" in model.results_text


def test_the_view_model_exports_csv(tmp_path):
    """The CSV carries the fitted parameters."""
    from chisurf.plugins.burst.burst_gs.gui.view_model import BurstGsViewModel

    model = BurstGsViewModel()
    model.use_simulation = True
    model.sim_n_bursts = 15
    model.sim_photons_per_burst = 60
    model.max_iterations = 60
    assert model.compute() is True
    path = tmp_path / "out.csv"
    model.export_csv(str(path))
    text = path.read_text()
    assert "k_12_per_s" in text and "log_likelihood" in text
