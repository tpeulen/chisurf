"""The simulated FRET efficiency has to reproduce the static accessible-volume average.

Theory (Forster, with the dyes treated as points in their accessible volumes): when
neither dye moves during the donor lifetime and both sample their volume uniformly
over the ensemble, the efficiency is the average over donor/acceptor point pairs

    <E> = < 1 / (1 + (r / R0)^6) >

with the *same* R0 the simulation uses, and the simulated efficiency
``1 - QY_DA / QY_D`` has to land on it. Averaging the other way round,
``E(<r>)``, is not the same number (0.22 against 0.26 for E55 -> E124).

This test exists because the baseline FRET run once read 0.473 and then 0.726
for that pair while the AV distance barely moved, and the disagreement looked
like a unit or averaging bug. It was not: with the default stickiness the
trapped walkers do not sample the accessible volume at all (see
``okf/references/known-issues.md``, QuEst "Open 1"). Switching stickiness off
(``slow_factor`` 1) removes the disagreement, which is what is pinned here; the
sticky case is pinned as *different* so the two are not conflated again.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

BASELINE_DIR = Path(__file__).parent / "baselines"
_spec = importlib.util.spec_from_file_location(
    "quest_static_limit_generate", BASELINE_DIR / "generate.py"
)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

R0 = 52.0
SEEDS = (1, 2, 3, 4)


def _static_mean_efficiency() -> float:
    """<E> over donor/acceptor AV point pairs, same R0, 400 000 random pairs."""
    from chisurf.plugins.quenching_estimator.core.av import AV

    def build(residue):
        return np.asarray(
            AV(
                str(gen.STRUCTURE),
                chain_identifier="E",
                residue_seq_number=residue,
                atom_name="CB",
                simulation_grid_resolution=0.5,
                save_av=False,
                verbose=False,
                **gen.AV_PARAMETER,
            ).points,
            dtype=float,
        )

    donor, acceptor = build(gen.FRET_PAIR[0]), build(gen.FRET_PAIR[1])
    rng = np.random.default_rng(0)
    n = 400_000
    r = np.linalg.norm(
        donor[rng.integers(0, len(donor), n)] - acceptor[rng.integers(0, len(acceptor), n)], axis=1
    )
    return float(np.mean(1.0 / (1.0 + (r / R0) ** 6)))


def _simulated_efficiency(slow_factor: float, seed: int) -> float:
    from chisurf.plugins.quenching_estimator.core import simulate_project
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
        default_amino_acid_interactions,
    )

    project = gen._project(gen.FRET_PAIR[0], acceptor=gen.FRET_PAIR[1])
    table = default_amino_acid_interactions(slow_factor=slow_factor)
    for entry in table.values():
        entry["kQ"] = 0.0  # no PET channel: E = 1 - QY_DA exactly
    project["amino_acid_interactions"] = table
    project["random_seed"] = seed
    project["fret"]["R0"] = R0
    for dye in project["fret"]["dyes"]:
        dye["random_seed"] = seed
    result = simulate_project(project, save_outputs=False, render_data=False)
    assert result.quantum_yield_donor == pytest.approx(1.0)  # no quencher: E = 1 - QY_DA
    assert result.fret_efficiency is not None
    return float(result.fret_efficiency)


def test_unsticky_simulation_matches_the_static_av_average() -> None:
    expected = _static_mean_efficiency()
    assert 0.2 < expected < 0.3  # the geometry itself: not the 0.73 the sticky run gave
    mean = float(np.mean([_simulated_efficiency(1.0, seed) for seed in SEEDS]))
    # One walk of 400 ns samples few of the AV pairs: seed-to-seed sd is ~0.02 (0.238..0.285
    # over six runs, mean 0.256) and the mean of four has sd ~0.01. 0.05 is 5 sd of that and
    # still far below the 0.45 gap an E <-> 1-E swap or a unit error would open.
    assert mean == pytest.approx(expected, abs=0.05)


def test_default_stickiness_is_not_the_static_average() -> None:
    expected = _static_mean_efficiency()
    mean = float(np.mean([_simulated_efficiency(0.1, seed) for seed in SEEDS]))
    # Compounded stickiness (0.1 per overlapping residue sphere, down to 1e-8) traps the
    # walkers, so the efficiency follows where they got stuck. Measured 0.46..0.85.
    assert mean > expected + 0.1
