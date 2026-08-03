"""The RPC surface must round-trip an arbitrary scheme."""

import pytest

from chisurf.plugins.calculator.fcs_saturation_calc.backend.services import register_services


class DummyDispatcher:
    """Minimal stand-in for a ServiceDispatcher that records handlers."""

    def __init__(self):
        self.handlers = {}

    def register(self, name, handler):
        self.handlers[name] = handler


def _call(**overrides):
    dispatcher = DummyDispatcher()
    register_services(dispatcher)
    params = {
        "power_mW": 2.0,
        "extinction": 100000.0,
        "dark_matrix": [[0.0, 2.5e8, 0.0], [0.0, 0.0, 0.0], [0.0, 2.5e6, 0.0]],
        "exc_matrix": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
        "brightness": [0.0, 1.0, 0.0],
    }
    params["dark_matrix"][0][2] = 5.0e5
    params.update(overrides)
    return dispatcher.handlers["fcs_saturation.compute"](params)


def test_rpc_services_registered_and_computing():
    res = _call()
    assert len(res["g_saturated"]) == 300
    assert res["v_eff_over_v0"] > 1.0
    # With bunching on, the short-lag amplitude can exceed the unperturbed one:
    # the photokinetic term raises G before the dark states have relaxed. It is
    # the diffusion-only amplitude that carries the volume expansion.
    assert _call(include_bunching=False)["g_saturated_0"] < res["g_unperturbed_0"]


def test_rpc_zero_power_is_unsaturated():
    res = _call(power_mW=0.0)
    assert res["v_eff_over_v0"] == 1.0
    assert res["g_saturated_0"] == pytest.approx(res["g_unperturbed_0"])


def test_rpc_accepts_a_two_state_scheme():
    res = _call(
        dark_matrix=[[0.0, 2.5e8], [0.0, 0.0]],
        exc_matrix=[[0.0, 0.0], [1.0, 0.0]],
        brightness=[0.0, 1.0],
    )
    assert res["v_eff_over_v0"] > 1.0
