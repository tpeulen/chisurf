"""PCH-experiment model-selector resolution guard (headless, offscreen).

Every model configured for the PCH experiment must resolve to a class exposing
a non-empty ``name`` (so a renamed/deleted widget fails here instead of silently
vanishing from the model combobox).  Explicitly covers the new ``FidaModel``.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pch_model_paths():
    import yaml
    import chisurf.core.settings as settings

    cfg = pathlib.Path(settings.__file__).parent / "experiment_configs.yaml"
    data = yaml.safe_load(cfg.read_text())
    return list(data.get("pch", {}).get("models", []))


def _resolve(path):
    module_name, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), class_name)


def test_every_configured_pch_model_resolves_with_a_name(qapp):
    paths = _pch_model_paths()
    assert paths, "no PCH models configured"
    problems, names = [], []
    for path in paths:
        try:
            cls = _resolve(path)
        except Exception as exc:
            problems.append(f"{path}: unresolved ({exc})")
            continue
        name = getattr(cls, "name", None)
        if not name or not str(name).strip():
            problems.append(f"{path}: missing/empty .name")
        else:
            names.append(str(name))
    assert not problems, "configured PCH models that won't appear in the menu:\n" + "\n".join(problems)
    assert any("FIDA" in n for n in names), f"FIDA model missing from {names}"


def test_fida_model_is_a_model_curve(qapp):
    from chisurf.core.models.model import ModelCurve
    from chisurf.gui.widgets.models.pch.fida_widget import FidaModel, FidaModelWidget

    assert issubclass(FidaModel, ModelCurve)
    assert issubclass(FidaModelWidget, FidaModel)
    assert str(getattr(FidaModelWidget, "name", "")).strip()
