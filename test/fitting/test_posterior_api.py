"""The posterior query has to be reachable, not only importable (PRD-70).

The three estimators reach RPC as three separate job protocols even though they
answer the same question. These tests pin the one query surface --
``fit.posterior`` on the server and ``ChiSurfAPI.posterior`` in process -- and
that its payload survives the trip to JSON.
"""
import json

import numpy as np
import pytest

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.api import ChiSurfAPI
from chisurf.server.services import fits as fit_service


class _State:
    """Minimal stand-in for the server's session state."""

    def __init__(self, fits):
        """Hold the list of fits the service resolves against."""
        self.fits = fits


def _fit(seed: int = 0):
    """Return a converged ``c + a*x**2`` fit."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 64)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, 0.05, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.05))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    fit.run()
    return fit


def test_the_rpc_answers_for_every_cheap_engine():
    """``stored`` and ``laplace`` cost nothing and must both work over RPC."""
    fit = _fit()
    state = _State([fit])
    for engine in ("stored", "laplace"):
        r = fit_service.fit_posterior(state, fit_index=0, engine=engine)
        assert r["ok"], r
        assert r["engine"] == engine
        names = {m["name"] for m in r["marginals"]}
        assert names == set(fit.model.parameter_names)
        for m in r["marginals"]:
            assert m["method"] in ("laplace", "mcmc", "profile", "none")
            assert np.isfinite(m["value"])


def test_an_unknown_engine_is_refused_rather_than_guessed():
    """A typo must not silently return the wrong estimator's answer."""
    fit = _fit()
    r = fit_service.fit_posterior(_State([fit]), fit_index=0, engine="bayes")
    assert not r.get("ok", False)
    assert "unknown posterior engine" in str(r.get("error", ""))


def test_a_missing_fit_is_refused():
    """Querying a fit that is not there must not look like an empty answer."""
    r = fit_service.fit_posterior(_State([]), fit_index=3)
    assert not r.get("ok", False)


def test_targets_joint_and_conditioning_all_reach_the_engine():
    """The whole query vocabulary must survive the RPC boundary."""
    fit = _fit()
    state = _State([fit])
    names = list(fit.model.parameter_names)

    only = fit_service.fit_posterior(
        state, fit_index=0, engine="laplace", targets=[names[0]]
    )
    assert [m["name"] for m in only["marginals"]] == [names[0]]

    joint = fit_service.fit_posterior(
        state, fit_index=0, engine="laplace", joint=names
    )
    assert joint["joint"] is not None
    corr = np.asarray(joint["joint"]["correlation"])
    assert corr.shape == (2, 2)
    assert np.allclose(np.diag(corr), 1.0)

    base = fit_service.fit_posterior(state, fit_index=0, engine="laplace")
    held = fit_service.fit_posterior(
        state, fit_index=0, engine="laplace",
        condition={names[0]: float(base["marginals"][0]["value"]) + 0.1},
        targets=[names[1]],
    )
    assert held["ok"]
    # Conditioning re-optimises the rest, and these two are correlated.
    unconditioned = [m for m in base["marginals"] if m["name"] == names[1]][0]
    assert held["marginals"][0]["value"] != pytest.approx(
        unconditioned["value"], abs=1e-9
    )


def test_the_payload_survives_json():
    """It goes over a JSON-RPC transport, so it must contain no numpy scalars."""
    fit = _fit()
    r = fit_service.fit_posterior(
        _State([fit]), fit_index=0, engine="laplace",
        joint=list(fit.model.parameter_names),
    )
    encoded = json.dumps(r)
    assert json.loads(encoded)["engine"] == "laplace"


def test_log_evidence_is_reported_only_when_it_exists():
    """A profile scan maximises rather than integrates and has none."""
    fit = _fit()
    state = _State([fit])
    lap = fit_service.fit_posterior(state, fit_index=0, engine="laplace")
    assert lap["log_evidence"] is not None
    stored = fit_service.fit_posterior(state, fit_index=0, engine="stored")
    assert stored["log_evidence"] is None


def test_the_api_facade_reaches_the_same_answer():
    """``ChiSurfAPI`` is the documented stable surface; it must work locally."""
    fit = _fit()
    cs.fits.append(fit)
    try:
        api = ChiSurfAPI()
        index = len(cs.fits) - 1
        r = api.posterior(fit_index=index, engine="laplace")
        assert r["ok"], r
        direct = fit_service.fit_posterior(_State([fit]), fit_index=0, engine="laplace")
        by_name = {m["name"]: m for m in r["marginals"]}
        for m in direct["marginals"]:
            assert by_name[m["name"]]["value"] == pytest.approx(m["value"])
    finally:
        cs.fits.remove(fit)


def test_the_rpc_is_registered():
    """An unregistered service function is unreachable however good it is."""
    import json as _json
    import pathlib
    spec = _json.loads(
        (pathlib.Path(cs.__file__).parent / "server" / "server_methods.json").read_text()
    )
    entries = spec if isinstance(spec, list) else spec.get("methods", spec)
    rpcs = {e["rpc"] for e in entries if isinstance(e, dict) and "rpc" in e}
    assert "fit.posterior" in rpcs
