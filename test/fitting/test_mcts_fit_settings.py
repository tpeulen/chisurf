"""The fit window's "Search fit settings": a second action space for the model search.

With it ticked, bff searches how every candidate structure is fitted as well
as which structure -- tolerances, evaluation budget, start values -- and
scores both with the same reward. A live model keeps its problem between
searches, so the next search without it is a structure search again.
"""

from __future__ import annotations

import numpy as np
import pytest

bff = pytest.importorskip("IMP.bff")

from chisurf.core.fitting.mcts.dispatcher import prepare_model_search  # noqa: E402
from chisurf.core.fitting.mcts.execution import (  # noqa: E402
    NativeSearchSettings,
    run_native_search,
    search_outcome,
)

from .test_description_model import _simulated, _view  # noqa: E402

pytestmark = pytest.mark.skipif(
    not hasattr(bff, "ACTION_SPACE_FIT_SETTINGS"),
    reason="this IMP.bff has no fit-settings action space",
)


def test_a_live_model_searches_structures_and_fit_settings_then_goes_back():
    counts = (
        np.asarray(bff.PhotonExperiment.record_pattern(list(_simulated()), 7))
        if bff.PhotonExperiment.get_available()
        else np.round(_simulated())
    )
    fit, model = _view(counts)

    prepared = prepare_model_search(fit, search_fit_settings=True)
    assert prepared.supported, prepared.reasons
    assert prepared.search_fit_settings
    problem = prepared.problem
    assert problem.get_action_space() == bff.ACTION_SPACE_FIT_SETTINGS
    assert len(problem.get_fit_settings_candidates()) > 1

    result = run_native_search(problem, NativeSearchSettings(simulations=16, action_policy=""))

    assert search_outcome(result)[0] == "selected"
    best = result.get_best_state()
    assert best.get_structure_key() == "lifetime.components.2"
    assert best.get_fit_settings_key()
    prepared.binding.apply_state(problem, best)
    assert model.structure == "lifetime.components.2"

    again = prepare_model_search(fit)
    assert not again.search_fit_settings
    assert again.problem.get_action_space() == bff.ACTION_SPACE_STRUCTURE
