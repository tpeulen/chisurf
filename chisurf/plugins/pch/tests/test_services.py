import numpy as np
import pytest

from chisurf.plugins.pch.backend.services import _fit_handler, register_services
from chisurf.server.dispatcher import ServiceDispatcher
from chisurf.server.session import SessionState


def test_register_services():
    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    register_services(dispatcher)
    assert dispatcher.has_method("pch.load_tttr")
    assert dispatcher.has_method("pch.compute")
    assert dispatcher.has_method("pch.fit")


def test_fit_handler_simple():
    state = SessionState()
    dispatcher = ServiceDispatcher(state)
    register_services(dispatcher)

    k_vals = list(range(10))
    p_exp = [0.5, 0.3, 0.1, 0.05, 0.03, 0.01, 0.005, 0.003, 0.001, 0.001]

    result = dispatcher.dispatch(
        "pch.fit",
        {
            "k_vals": k_vals,
            "p_exp": p_exp,
            "n_components": 1,
            "initial_epsilons": [2.0],
            "initial_Ns": [3.0],
            "fit_low": 0,
            "fit_high": 9,
        },
    )
    assert result.get("ok", True)
    r = result.get("result", {})
    assert "epsilons" in r
    assert "avg_Ns" in r
    assert len(r["epsilons"]) == 1
    assert r["chi2"] >= 0


def test_fit_handler_refuses_starting_values_that_do_not_match_n_components():
    """Too few starting values must fail loudly, not fit a degenerate model.

    The handler concatenates ``initial_epsilons + initial_Ns`` into one vector
    and splits the optimiser's answer at *n_components*.  With one ε and one
    ⟨N⟩ but ``n_components=2`` that split used to hand the ⟨N⟩ over as a second
    ε and leave the occupancy list empty, so ``pch_mixture`` convolved nothing
    and ``p_fit`` came back as a delta at k = 0 under ``ok: True``.
    """
    k_vals = list(range(10))
    p_exp = [0.5, 0.3, 0.1, 0.05, 0.03, 0.01, 0.005, 0.003, 0.001, 0.001]
    base = {"k_vals": k_vals, "p_exp": p_exp, "fit_low": 0, "fit_high": 9}

    for name in ("initial_epsilons", "initial_Ns"):
        params = dict(base, n_components=2, initial_epsilons=[2.0, 2.0], initial_Ns=[3.0, 3.0])
        params[name] = [1.0]
        result = _fit_handler(**params)
        assert result["ok"] is False
        assert name in result["error"]
        assert "result" not in result

    assert _fit_handler(**base, n_components=0)["ok"] is False


def test_pch_mixture_refuses_unequal_parameter_lists():
    """A mismatched (ε, ⟨N⟩) pairing raises instead of returning a delta."""
    from chisurf.plugins.pch.api.algorithms import pch_mixture

    k_vals = np.arange(10, dtype=float)
    with pytest.raises(ValueError):
        pch_mixture(k_vals, [3.0, 8.0], [2.0])
