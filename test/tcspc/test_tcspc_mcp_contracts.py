from __future__ import annotations

from pathlib import Path


def test_model_macros_expose_unload_irf_contract():
    src = Path("chisurf/macros/model.py").read_text(encoding="utf-8")
    assert "def unload_irf(" in src


def test_model_actions_irf_handlers_use_fit_object_contract():
    src = Path("chisurf/core/actions/model_actions.py").read_text(encoding="utf-8")
    assert "return model_macros.change_irf(int(irf_idx), str(irf_name), fit=fit)" in src
    assert "return model_macros.unload_irf(fit=fit)" in src


# The widget-side counterpart of these contracts is gone: the IRF is now a
# declarative ``curve_input`` dispatching ``model.change_irf`` /
# ``model.unload_irf``, so the handlers it used to assert on no longer exist. The
# macro and action contracts above are the durable half and still hold.
