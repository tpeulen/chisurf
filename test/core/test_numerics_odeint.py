"""``chisurf.core.math.numerics.odeint`` against ``scipy.integrate.odeint``.

scipy is the oracle; the engine itself (bff.odeint, LSODA) is checked in
imp.bff ``test/numerics/test_odeint.py``. This file pins the shim's scipy
call forms and the one real caller, the kinetic reaction system behind the
stopped-flow model -- including a stiff scheme, which is why LSODA and not
an explicit Runge-Kutta replaced scipy here.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.math.numerics import ODEintWarning, odeint

integrate = pytest.importorskip("scipy.integrate")


def _relax(y, t, kf, kr):
    return np.array([-kf * y[0] + kr * y[1], kf * y[0] - kr * y[1]])


def test_args_and_full_output_match_scipy():
    t = np.linspace(0, 10, 101)
    y, info = odeint(_relax, [1.0, 0.0], t, args=(2.0, 1.0), full_output=True)
    ys, infos = integrate.odeint(_relax, [1.0, 0.0], t, args=(2.0, 1.0), full_output=True)
    np.testing.assert_allclose(y, ys, rtol=1e-6, atol=1e-10)
    assert set(info) == set(infos)
    assert info["message"] == infos["message"]
    np.testing.assert_array_equal(info["mused"], infos["mused"])


def test_tfirst():
    t = np.linspace(0, 1, 11)
    y = odeint(lambda tt, yy: -yy, [1.0], t, tfirst=True)
    np.testing.assert_allclose(y[:, 0], np.exp(-t), rtol=1e-6)


def _scheme(rate_pairs, c0):
    from chisurf.core.math.reaction.continuous import ReactionSystem

    rs = ReactionSystem()
    for educts, products, es, ps, k in rate_pairs:
        rs.add_reaction(
            educts=educts, products=products, educt_stoichiometry=es,
            product_stoichometry=ps, rate=k,
        )
    rs.initial_concentrations = c0
    return rs


@pytest.mark.parametrize(
    "reactions, c0, t",
    [
        ([([0], [1], [1], [1], 1.0), ([1], [0], [1], [1], 0.1)], [1.0, 0.0], np.linspace(0, 60, 600)),
        (
            # A + B <-> C fast, C -> D slow: stiff.
            [([0, 1], [2], [1, 1], [1], 1e4), ([2], [0, 1], [1], [1, 1], 1e3),
             ([2], [3], [1], [1], 1e-2)],
            [1.0, 1.0, 0.0, 0.0],
            np.linspace(0, 300, 1000),
        ),
    ],
)
def test_reaction_system_integrates_like_scipy(reactions, c0, t):
    rs = _scheme(reactions, c0)
    rs.times = t
    rs.calc()
    ys = integrate.odeint(
        rs.rate_equation, rs.initial_concentrations.flatten(), t,
        args=(rs.reactions,), mxstep=15000000,
    )
    np.testing.assert_allclose(rs.concentrations, ys, rtol=1e-6, atol=1e-9)


def test_a_failure_warns_like_scipy():
    t = np.logspace(-6, 6, 61)

    def robertson(y, tt):
        return np.array([
            -0.04 * y[0] + 1e4 * y[1] * y[2],
            0.04 * y[0] - 1e4 * y[1] * y[2] - 3e7 * y[1] ** 2,
            3e7 * y[1] ** 2,
        ])

    with pytest.warns(ODEintWarning, match="Excess work done"):
        y = odeint(robertson, [1.0, 0.0, 0.0], t, mxstep=5)
    assert np.isnan(y[-1]).all()


def test_a_user_jacobian_is_refused():
    with pytest.raises(NotImplementedError):
        odeint(_relax, [1.0, 0.0], [0.0, 1.0], args=(1.0, 1.0), Dfun=lambda y, t, a, b: None)
