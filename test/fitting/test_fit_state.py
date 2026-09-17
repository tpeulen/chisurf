from __future__ import annotations

import numpy as np

import chisurf.core.models.pda2c.simple as pda_simple_mod
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project.fit_state import (
    apply_state_to_fit,
    fit_to_state,
)


class DummyLinearModel(ModelCurve):
    """Minimal concrete model used for testing fit_state helpers.

    The model represents a simple line ``y = p0 + p1 * x`` with two
    :class:`FittingParameter` instances. This keeps the test independent of
    complex experiment‑specific models while still exercising the real
    parameter / chinet plumbing.
    """

    name = "DummyLinearModel"

    def __init__(self, fit: Fit, **kwargs):  # type: ignore[override]
        super().__init__(fit, **kwargs)
        # Two scalar parameters that will be discovered by find_parameters
        self.p0 = FittingParameter(name="p0", value=1.0)
        self.p1 = FittingParameter(name="p1", value=2.0)
        self.find_parameters()

    def _update_model(self, **kwargs):  # type: ignore[override]
        x = self.fit.data.x
        if x is None:
            x = np.arange(self.fit.data.y.size, dtype=float)
        self.x = x
        self.y = float(self.p0.value) + float(self.p1.value) * x

    def update(self, **kwargs) -> None:  # type: ignore[override]
        # Use the default ModelCurve behaviour
        super().update(**kwargs)


def _make_dummy_fit() -> Fit:
    x = np.arange(5, dtype=float)
    y = np.ones_like(x)
    data = DataCurve(x=x, y=y)
    return Fit(model_class=DummyLinearModel, data=data)


def test_fit_state_roundtrip_with_links():
    # Prepare original fit with non‑default parameter settings
    fit1 = _make_dummy_fit()
    m1 = fit1.model
    params1 = m1.parameters_all_dict

    # Sanity: we expect both parameters to be present
    assert "p0" in params1 and "p1" in params1

    params1["p0"].value = 3.14
    params1["p0"].bounds = (0.0, 10.0)
    params1["p0"].bounds_on = True

    params1["p1"].value = -1.23
    params1["p1"].fixed = True
    # Link p1 to p0
    params1["p1"].link = params1["p0"]

    state = fit_to_state(fit1)

    # Basic structure checks
    assert state["model_class"] == DummyLinearModel.__name__
    assert "parameters" in state
    # Keyed by uid since state version 4 -- a uid identifies the object, the
    # name identifies its role, and both are needed to restore a link into
    # freshly constructed models. The name lives inside each entry.
    by_name = {v["name"]: v for v in state["parameters"].values()}
    assert set(by_name) == {"p0", "p1"}

    p1_state = by_name["p1"]
    assert p1_state["fixed"] is True
    p0_state = by_name["p0"]
    assert p1_state["link_target"] == p0_state["uid"]
    assert p1_state["link_target_name"] == "p0"

    # Create a fresh fit and apply the stored state
    fit2 = _make_dummy_fit()
    m2 = fit2.model
    params2 = m2.parameters_all_dict

    # Ensure the fresh fit starts out different
    assert not np.isclose(params2["p0"].value, 3.14)
    assert not np.isclose(params2["p1"].value, -1.23)

    apply_state_to_fit(fit2, state)

    # Values, bounds and flags should now match the original
    assert np.isclose(params2["p0"].value, 3.14)
    assert params2["p0"].bounds_on is True
    assert np.allclose(params2["p0"].bounds, [0.0, 10.0])

    assert params2["p1"].fixed is True

    # Linked parameter should share the master's value and point to it
    assert params2["p1"].link is params2["p0"]
    assert np.isclose(params2["p1"].value, params2["p0"].value)


def test_model_get_set_state_roundtrip():
    """Model.get_state/set_state should mirror fit_state helpers."""
    fit1 = _make_dummy_fit()
    m1 = fit1.model
    params1 = m1.parameters_all_dict

    params1["p0"].value = 4.2
    params1["p1"].value = -0.7
    params1["p1"].fixed = True
    params1["p1"].link = params1["p0"]

    state = m1.get_state()

    # Fresh model should start out different
    fit2 = _make_dummy_fit()
    m2 = fit2.model
    params2 = m2.parameters_all_dict
    assert not np.isclose(params2["p0"].value, 4.2)
    assert not np.isclose(params2["p1"].value, -0.7)

    m2.set_state(state)

    assert np.isclose(params2["p0"].value, 4.2)
    assert np.isclose(params2["p1"].value, params2["p0"].value)
    assert params2["p1"].fixed is True
    assert params2["p1"].link is params2["p0"]


def test_fit_get_set_state_roundtrip_and_update_called():
    """Fit.get_state/set_state must round-trip state and trigger update()."""
    fit1 = _make_dummy_fit()
    params1 = fit1.model.parameters_all_dict
    params1["p0"].value = 1.23
    params1["p1"].value = 4.56

    state = fit1.get_state()

    fit2 = _make_dummy_fit()
    params2 = fit2.model.parameters_all_dict

    # Ensure defaults differ
    assert not np.isclose(params2["p0"].value, 1.23)
    assert not np.isclose(params2["p1"].value, 4.56)

    # Track whether update() is invoked
    called = {"update": False}

    def _fake_update(*args, **kwargs):
        called["update"] = True

    fit2.update = _fake_update

    fit2.set_state(state)

    assert np.isclose(params2["p0"].value, 1.23)
    assert np.isclose(params2["p1"].value, 4.56)
    assert called["update"] is True


class _DummyModelForFinalize(ModelCurve):
    """Model stub used to verify Fit.set_state behaviour.

    It records whether ``set_state`` and ``finalize`` have been called so we
    can assert that :meth:`Fit.set_state` delegates correctly.
    """

    name = "DummyFinalizeModel"

    def __init__(self, fit: Fit, **kwargs):  # type: ignore[override]
        super().__init__(fit, **kwargs)
        self._flag_set_state_called = False
        self._flag_finalize_called = False

    def _update_model(self, **kwargs):  # type: ignore[override]
        # Minimal implementation: keep y array shape consistent with x
        if getattr(self, "x", None) is None:
            x = self.fit.data.x
            if x is None:
                x = np.arange(self.fit.data.y.size, dtype=float)
            self.x = x
        self.y = np.zeros_like(self.x)

    def update(self, **kwargs) -> None:  # type: ignore[override]
        super().update(**kwargs)

    def get_state(self) -> dict:  # pragma: no cover - trivial
        return {"marker": 1}

    def set_state(self, state: dict) -> None:
        self._flag_set_state_called = True

    def finalize(self):  # type: ignore[override]
        self._flag_finalize_called = True


def test_fit_set_state_calls_model_set_state_and_finalize():
    """Fit.set_state must delegate to model.set_state and then finalize()."""
    x = np.arange(3, dtype=float)
    y = np.ones_like(x)
    data = DataCurve(x=x, y=y)
    fit = Fit(model_class=_DummyModelForFinalize, data=data)

    model = fit.model
    # Sanity: flags start out False
    assert model._flag_set_state_called is False
    assert model._flag_finalize_called is False

    # Apply an arbitrary state; our dummy model only records the calls.
    fit.set_state({"marker": 2})

    assert model._flag_set_state_called is True
    assert model._flag_finalize_called is True


def test_a_described_models_state_keeps_its_structure_and_values():
    """The component count of a lifetime or FRET fit is its structure, and the state keeps it."""
    import pytest

    pytest.importorskip("IMP.bff")
    from chisurf.core.models.description import for_family

    x = np.arange(64, dtype=float) * 0.1
    data = DataCurve(x=x, y=np.exp(-x / 4.0) * 100 + 1)
    for family, key, canonical in (
        ("tcspc_lifetime", "lifetime.components.3", "lifetime.tau.2"),
        ("tcspc_fret_gaussian", "tcspc_fret_gaussian.components.2", "distance.mean.1"),
    ):
        first = Fit(model_class=for_family(family), data=data).model
        first.structure = key
        next(p for p in first.parameters_all if p.canonical_id == canonical).value = 7.25
        second = Fit(model_class=for_family(family), data=data).model
        assert second.structure != key
        second.set_state(first.get_state())
        assert second.structure == key
        assert next(
            p for p in second.parameters_all if p.canonical_id == canonical
        ).value == pytest.approx(7.25)


def test_pda_probch0_length_preserved_via_model_state():
    """The PDA model's state override must preserve its species count.

    ``Pda2cSimpleModel`` cannot be built from a plain DataCurve -- it reads
    ``fit.data.pda``, real burst data. The previous version worked around that
    with ``__new__`` and then assigned to ``parameters_all_dict``, a read-only
    property, so it could only ever raise. A subclass that skips the data
    requirement exercises the same override on a real species group.
    """

    class _DetachedPdaModel(pda_simple_mod.Pda2cSimpleModel):
        """The model's state logic without its data dependency."""

        def __init__(self):
            self.pch0 = pda_simple_mod.ProbCh0(name="pch0")

    m1 = _DetachedPdaModel()
    m1.pch0.append(amplitude=1.0, pch0=0.2)
    m1.pch0.append(amplitude=2.0, pch0=0.8)
    n1 = len(m1.pch0)
    assert n1 == 2

    state = m1.get_state()
    assert state["extra"]["pda_probch0_n"] == n1

    m2 = _DetachedPdaModel()
    assert len(m2.pch0) != n1
    m2.set_state(state)
    assert len(m2.pch0) == n1

    # It must shrink as well as grow, or a reloaded project accumulates species.
    m3 = _DetachedPdaModel()
    for _ in range(5):
        m3.pch0.append(amplitude=1.0, pch0=0.5)
    m3.set_state(state)
    assert len(m3.pch0) == n1


# A ``Pda2cGaussianDistanceModel`` test used to sit here. No such class has ever
# existed in this tree -- the test was written against an API that was never
# implemented, and it stubbed the model through ``__new__`` besides. The
# behaviour it meant to cover, "model state preserves a variable-length
# component group", is covered above for ProbCh0 and by the lifetime and
# Gaussian round-trips earlier in this file.
def test_fit_state_preserves_error_estimates():
    """Fitted uncertainties must survive a save/load round trip.

    The uncertainty is part of the result, not a display detail: without it a
    reloaded project shows parameters with no error bars and the fit has to be
    re-run to recover them. This affects both the ``.csp`` path and MMFDB
    archival, since both serialize through ``fit_to_state``.
    """
    fit = _make_dummy_fit()
    fit.model.p0.error_estimate = 0.125
    fit.model.p1.error_estimate = 0.0625

    state = fit_to_state(fit)
    parameter_states = state["parameters"].values()
    assert all("error_estimate" in p for p in parameter_states)

    # Wipe, then restore from the serialized state.
    fit.model.p0.error_estimate = 0.0
    fit.model.p1.error_estimate = 0.0
    apply_state_to_fit(fit, state)

    assert fit.model.p0.error_estimate == 0.125
    assert fit.model.p1.error_estimate == 0.0625


def test_fit_state_without_error_estimates_still_loads():
    """Projects saved before errors were serialized must keep loading."""
    fit = _make_dummy_fit()
    fit.model.p0.error_estimate = 0.5
    state = fit_to_state(fit)

    legacy = {
        uid: {k: v for k, v in p.items() if k != "error_estimate"}
        for uid, p in state["parameters"].items()
    }
    apply_state_to_fit(fit, {**state, "parameters": legacy})

    # No key means "not recorded"; the live value is simply left alone.
    assert fit.model.p0.error_estimate == 0.5


def test_fit_state_error_estimate_survives_a_real_fit():
    """The value written is the one a real fit actually produced.

    ``_make_dummy_fit`` has no uncertainties and so no weighted residuals to
    minimise; this builds a fittable curve instead, so the round trip is
    checked against genuine covariance-derived errors rather than values
    assigned by hand.
    """
    from chisurf.core.data import DataGroup
    from chisurf.core.fitting.fit import FitGroup

    rng = np.random.default_rng(1)
    x = np.linspace(0.0, 5.0, 64)
    sigma = 0.05
    y = 1.0 + 2.0 * x + rng.normal(0.0, sigma, x.size)
    data = DataCurve(x=x, y=y, ey=np.ones_like(y) * sigma)
    fit = FitGroup(data=DataGroup([data]), model_class=DummyLinearModel)
    fit.fit_range = 0, len(fit.model.y)
    fit.run()
    fit.update_error_estimates()

    expected = {p.name: float(p.error_estimate) for p in fit.model.parameters}
    assert any(v > 0.0 for v in expected.values()), "fit produced no error estimates"

    state = fit_to_state(fit)
    for p in fit.model.parameters:
        p.error_estimate = 0.0
    apply_state_to_fit(fit, state)

    for p in fit.model.parameters:
        assert float(p.error_estimate) == expected[p.name]
