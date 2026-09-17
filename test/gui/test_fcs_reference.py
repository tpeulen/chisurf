"""The FCS plot normalisations: ``(G - b) / Gdiff`` and ``N * (G - b)``.

The modes read their parameters from the plot controller first and from the
model's current values otherwise. They lived on the hand-built parse widget
and were lost when that editor became JSON-described; they are registered in
``chisurf.core.plotting.reference_modes`` now and the FCS catalogue names them.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

import chisurf.core.plotting.transforms as plot_transforms
from chisurf.core.fluorescence.fcs import fcs_diffusion_reference
from chisurf.core.plotting.reference_modes import modes_named

X = np.array([0.0, 0.25, 1.0])
G = np.array([2.2, 2.0, 1.7])


def _model(**values):
    """A model whose parameters have the given current values."""
    return types.SimpleNamespace(
        parameters_all_dict={k: types.SimpleNamespace(value=v) for k, v in values.items()}
    )


def _mode(key, model):
    return {mode.key: mode for mode in modes_named([key], model=model)}[key]


def _context(model, y, **parameters):
    return plot_transforms.PlotReferenceContext(
        fit=None, model=model, curve_key="data", x=X, y=y, curves={}, parameters=parameters
    )


def test_fcs_diffusion_reference_excludes_baseline():
    """The diffusion reference is ``diffusion / abs(N)``, without ``b``."""
    expected = 1.0 / 2.0 * (1.0 + X / 0.5) ** -1.0 * (1.0 + X / (3.5 * 3.5 * 0.5)) ** -0.5
    reference = fcs_diffusion_reference(X, {"N": 2.0, "td": 0.5, "s": 3.5, "b": 1.2})
    np.testing.assert_allclose(reference, expected)


def test_fcs_diffusion_mode_normalizes_as_g_minus_b_over_gdiff():
    model = _model(N=2.0, td=0.5, s=3.5, b=1.2)
    result = _mode("fcs_diffusion", model).callback(_context(model, G, b=1.2))
    gdiff = fcs_diffusion_reference(X, {"N": 2.0, "td": 0.5, "s": 3.5})
    np.testing.assert_allclose(result.y, (G - 1.2) / gdiff)


def test_fcs_molecule_mode_uses_parameter_overrides():
    """The controller's N and b win over the model's."""
    model = _model(N=2.0, td=0.5, s=3.5, b=1.2)
    result = _mode("fcs_molecules", model).callback(_context(model, G, N=4.0, b=1.0))
    np.testing.assert_allclose(result.y, 4.0 * (G - 1.0))


def test_the_controls_start_at_the_model_values():
    mode = _mode("fcs_molecules", _model(N=3.0, b=1.1))
    assert {p.key: p.default for p in mode.parameters} == {"N": 3.0, "b": 1.1}


def test_fcs_reference_missing_parameters_raises():
    """Without N the diffusion reference does not exist; the mode says so."""
    model = _model(td=0.5, s=3.5)
    with pytest.raises(ValueError):
        _mode("fcs_diffusion", model).callback(_context(model, np.ones(3), b=1.0, N=0.0))


def test_the_fcs_parse_model_offers_both_modes():
    from chisurf.core.models.fcs.parse import ParseFCSModel

    assert set(ParseFCSModel.reference_modes) == {"fcs_diffusion", "fcs_molecules"}
