"""The agent chain on PIE (alternating-laser) data, and the pipeline-scripting leg.

The cw suite (``test_smfret_agent.py``) proves the chain recovers the
simulation truth when every donor photon is a donor-excitation photon. PIE
is the harder, everyday case: the donor decay stream is gated to the donor
micro-time window, the burst table carries a stoichiometry column, and the
species gate has to do real work — with PIE an E-only gate wrongly keeps
acceptor-only molecules (their leakage-only donor counts push E high), which
is exactly what the S gate is for. These tests pin that every API the agent
drives is usable on PIE: detection with alternation roles, S gating, the
sub-ensemble decay of the S-selected species, the distance-distribution fit
against simulation truth, correction factors (explicit, defaulted, and
auto-calibrated), and — the pipeline leg — ``run_python`` scripting the same
chain from the plugin and core APIs, which is how the agent builds analysis
pipelines for the user.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("tttrlib")

from chisurf.core.agent.tools import burst as burst_tools
from chisurf.core.agent.tools import scripting

SCENARIO_KWARGS = {
    "excitation": "pie",
    "populations": ((0.75, 0.8),),
    "donor_only": 0.15,
    "acceptor_only": 0.15,
    "duration_s": 2.0,
    "seed": 3,
}
TRUTH_DISTANCE_A = 43.29  # R0 * (1/E - 1)^(1/6) at E = 0.75, R0 = 52


@pytest.fixture(scope="module")
def pie_file(tmp_path_factory):
    """One simulated PIE measurement for the whole module."""
    from chisurf.plugins.burst.fret_check.sim import Scenario, simulate

    directory = tmp_path_factory.mktemp("pie")
    data = simulate(Scenario("pie suite", **SCENARIO_KWARGS))
    path = directory / "pie.ht3"
    data.write(str(path))
    return path


def _analyse(context, pie_file, **kwargs):
    return burst_tools.run_burst_analysis(context, path=str(pie_file), **kwargs)


def test_detection_reports_the_alternation_roles(context, pie_file):
    """The PIE measurement is recognised: alternating, both colours, windows."""
    detected = burst_tools.detect_smfret(context, path=str(pie_file))["detected"]
    assert "PIE" in detected["kind"] or detected["excitation"] == "alternating"
    assert detected["donor_channels"] and detected["acceptor_channels"]
    assert detected["n_photons"] > 0


def test_stoichiometry_gating_excludes_donor_and_acceptor_only(context, pie_file):
    """An E-only gate wrongly keeps acceptor-only molecules; the S gate removes them."""
    _analyse(context, pie_file)

    by_e = burst_tools.select_species(context, column="E", min=0.5, max=1.0)
    by_s = burst_tools.select_species(context, column="S", min=0.3, max=0.8)

    assert by_e["n_selected"] > by_s["n_selected"], (
        "with PIE the E gate keeps acceptor-only molecules the S gate removes"
    )
    assert by_s["n_selected"] > 0
    # The S-gated population is the FRET species: E centred on 0.75.
    assert 0.70 < by_s["E_of_selection"]["p50"] < 0.80


def test_the_chain_recovers_the_distance_on_pie(context, pie_file):
    """S-gated species -> sub-ensemble decay -> fitted distance near the truth."""
    _analyse(context, pie_file)
    species = burst_tools.select_species(context, column="S", min=0.3, max=0.8)
    decay = burst_tools.extract_subensemble_decay(context)
    fit = burst_tools.fit_distance_distribution(
        context, n_states=1, forster_radius=52.0, donor_lifetime=4.0, fit_sigma=True
    )

    assert decay["photons"] > 0
    assert decay["n_bursts_used"] == species["n_selected"]
    distance = fit["distances_A"][0]
    assert 0.8 * TRUTH_DISTANCE_A < distance < 1.2 * TRUTH_DISTANCE_A, (
        f"PIE fitted distance {distance} A vs simulation truth {TRUTH_DISTANCE_A} A"
    )
    assert 0.0 < fit["efficiencies"][0] < 1.0
    assert fit["width_mode"] == "fitted"


def test_correction_factors_are_reported_and_applied(context, pie_file):
    """Partial factor dicts work (neutrals filled), and what was used is reported."""
    result = _analyse(
        context, pie_file, correct=True, factors={"gamma": 1.0, "alpha": 0.06}
    )
    assert result["corrected"] is not None
    assert 0.6 < result["corrected"]["E"]["p50"] < 0.9
    # The tool filled the missing factors with the neutral values and reports
    # all four — the model can state exactly what correction was applied.
    assert set(result["factors_used"]) == {"gamma", "alpha", "delta", "beta"}
    assert result["factors_used"]["delta"] == 0.0
    assert result["factors_used"]["beta"] == 1.0
    assert result["auto_calibrated"] is False


def test_auto_calibration_fills_the_factors_from_the_measurement(context, pie_file):
    """PIE can self-calibrate; the user's explicit factors would win anyway."""
    result = _analyse(context, pie_file, correct=True, auto_calibrate=True)
    assert result["auto_calibrated"] is True
    assert result["corrected"] is not None
    used = result["factors_used"]
    assert set(used) == {"gamma", "alpha", "delta", "beta"}
    assert all(isinstance(v, float) for v in used.values())


def test_the_agent_can_script_the_pipeline_over_the_plugin_apis(context, pie_file):
    """The pipeline leg: run_python drives the plugin/core APIs directly.

    This is how the agent builds an analysis pipeline for the user — not a
    new analysis implementation, but the same seams the tools wrap, scripted
    end to end and returning its numbers.
    """
    code = (
        "from chisurf.plugins.burst.fret_check import entry as fret_check\n"
        "from chisurf.plugins.burst.burst_selection.api.io import (\n"
        "    write_container, write_decay_container,\n"
        ")\n"
        "from chisurf.core.fluorescence.decay_fit_model import fit_fret_model\n"
        "import numpy as np\n"
        f"raw = r'{pie_file}'\n"
        "res = fret_check.analyse(path=raw, key=raw, settings={'min_photons': 30, 'T': 5e-4})\n"
        "bursts = res['bursts']\n"
        "from chisurf.plugins.burst.fret_check import jobs as fj\n"
        "table = fj.bursts_from_dict(bursts)\n"
        "first = np.asarray(table.columns()['First Photon'], dtype=int)\n"
        "last = np.asarray(table.columns()['Last Photon'], dtype=int)\n"
        "E = np.asarray(table.E)\n"
        "mask = (E >= 0.5) & (E <= 1.0)\n"
        "donor = res['experiment']['donor_channels']\n"
        "stream = {'channels': [int(c) for c in donor], 'micro_time_ranges': []}\n"
        "n = table.n\n"
        "burst_table = {**table.columns(), 'First File': [Path(raw).name] * n}\n"
        "container = write_container(Path(raw), burst_table, run='burstwise')\n"
        "out = write_decay_container(f'{container}/burstwise', mask, 0, stream=stream)\n"
        "ds = out['dataset_index']\n"
        "import chisurf as cs\n"
        "curve = cs.imported_datasets[ds]\n"
        "y = np.asarray(curve.y); x = np.asarray(curve.x)\n"
        "f = fit_fret_model(y, bin_width=float(x[1]-x[0]), n_states=1,\n"
        "                   donor_lifetime=4.0, forster_radius=52.0,\n"
        "                   start_bin=int(np.argmax(y)))\n"
        "result = float(f['distances'][0])\n"
        "print('pipeline distance (A):', result)\n"
    )
    outcome = scripting.run_python(context, code, purpose="PIE pipeline over the plugin APIs")
    assert outcome["ok"], outcome.get("error")
    assert "pipeline distance (A):" in outcome["stdout"]
    value = float(outcome["stdout"].rsplit(":", 1)[1])
    assert 0.8 * TRUTH_DISTANCE_A < value < 1.2 * TRUTH_DISTANCE_A


def test_tool_results_survive_json_round_trip_on_pie(context, pie_file):
    """Every tool's result must be model-readable: JSON-serialisable."""
    _analyse(context, pie_file, correct=True)
    outputs = [
        burst_tools.inspect_bursts(context),
        burst_tools.select_species(context, column="S", min=0.3, max=0.8),
        burst_tools.extract_subensemble_decay(context),
        burst_tools.fit_distance_distribution(context, fit_sigma=True),
    ]
    for output in outputs:
        encoded = json.dumps(output)
        assert "NaN" not in encoded and "Infinity" not in encoded
