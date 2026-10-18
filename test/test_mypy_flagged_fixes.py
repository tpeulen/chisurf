"""Regression tests for defects mypy flagged: attribute fallback, GMM settings, dead duplicate defs."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_parameter_group_missing_attribute_raises_attribute_error():
    from chisurf.core.parameter import Parameter, ParameterGroup

    group = ParameterGroup(parameters=[Parameter(name="a", value=1.0)])
    with pytest.raises(AttributeError):
        group.no_such_attribute
    assert not hasattr(group, "no_such_attribute")
    assert group.parameter_names == ["a"]


def test_gmm_settings_coerce_to_default_type():
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    model = BurstSelectionModel()
    model.gmm.max_iter = "12"
    model.gmm.tol = "0.5"
    assert model.gmm_settings["max_iter"] == 12
    assert model.gmm_settings["tol"] == 0.5
    with pytest.raises(AttributeError):
        model.gmm.not_a_setting = 1
