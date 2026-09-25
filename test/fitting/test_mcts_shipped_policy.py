"""End to end: photons from tttrlib, a ChiSurf fit, bff's shipped search policy.

The decay is one the lifetime family generates at known parameters, recorded
as photons by tttrlib's simulator through ``IMP.bff.PhotonExperiment``. The
search is the one the GUI starts -- ``prepare_model_search`` then
``run_native_search`` with default settings, which load the action policy bff
ships -- and the winner is applied to the live model.
"""

from __future__ import annotations

import numpy as np
import pytest

bff = pytest.importorskip("IMP.bff")

from chisurf.core.fitting.mcts.dispatcher import prepare_model_search  # noqa: E402
from chisurf.core.fitting.mcts.execution import (  # noqa: E402
    NativeSearchSettings,
    run_native_search,
)

from .test_description_model import _simulated, _view  # noqa: E402

pytestmark = pytest.mark.skipif(
    not bff.PhotonExperiment.get_available() or not bff.get_shipped_action_policy(),
    reason="needs bff built with TTTRLib and a shipped action policy",
)


def test_a_photon_recorded_decay_is_searched_under_the_shipped_policy():
    counts = np.asarray(bff.PhotonExperiment.record_pattern(list(_simulated()), 7))
    fit, model = _view(counts)
    prepared = prepare_model_search(fit)
    assert prepared.supported, prepared.reasons

    result = run_native_search(prepared.problem, NativeSearchSettings(simulations=16))

    assert prepared.problem.get_has_action_policy()
    best = result.get_best_state()
    prepared.binding.apply_state(prepared.problem, best)
    assert model.structure == best.get_structure_key() == "lifetime.components.2"
    taus = sorted(
        p.value
        for p in model.lifetimes.visible_parameters()
        if p.canonical_id.startswith("lifetime.tau")
    )
    assert taus == pytest.approx([0.6, 3.2], rel=0.1)
