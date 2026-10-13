"""Regression tests for defects mypy flagged: attribute fallback, GMM settings, dead duplicate defs."""

import ast
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
    pytest.importorskip("PyQt5")
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    model = BurstSelectionModel()
    model.gmm.max_iter = "12"
    model.gmm.tol = "0.5"
    assert model.gmm_settings["max_iter"] == 12
    assert model.gmm_settings["tol"] == 0.5
    with pytest.raises(AttributeError):
        model.gmm.not_a_setting = 1


@pytest.mark.parametrize(
    "path",
    [
        "chisurf/gui/widgets/fitting/parameter_widgets.py",
    ],
)
def test_no_method_defined_twice_in_a_class(path):
    tree = ast.parse((ROOT / path).read_text())
    dupes = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        seen = set()
        for fn in cls.body:
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_decorator = any(
                    isinstance(d, ast.Attribute)
                    and d.attr in ("setter", "getter", "deleter")
                    or isinstance(d, ast.Name)
                    and d.id == "overload"
                    for d in fn.decorator_list
                )
                if fn.name in seen and not has_decorator:
                    dupes.append(f"{cls.name}.{fn.name}")
                seen.add(fn.name)
    assert not dupes
