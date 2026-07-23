"""FCS model-selector resolution guard (headless, offscreen).

Mirrors the TCSPC resolution check in ``test_model_editor_integration.py`` for
the FCS experiment: every FCS model configured in the bundled experiment config
must resolve to a class exposing a non-empty ``name`` (the string the model
combobox shows and ``add_fit`` matches on), so a renamed/deleted widget fails
here instead of silently vanishing from the menu.  Explicitly covers the new
``MdfFCSWidget`` (Enderlein Gauss--Lorentz MDF model).
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


def _fcs_model_paths():
    import yaml
    import chisurf.core.settings as settings

    cfg = pathlib.Path(settings.__file__).parent / "experiment_configs.yaml"
    data = yaml.safe_load(cfg.read_text())
    return list(data.get("fcs", {}).get("models", []))


def _resolve(path):
    module_name, class_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), class_name)


def test_every_configured_fcs_model_resolves_with_a_name(qapp):
    paths = _fcs_model_paths()
    assert paths, "no FCS models configured"
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
    assert not problems, "configured FCS models that won't appear in the menu:\n" + "\n".join(problems)
    assert any("MDF" in n for n in names), f"MDF FCS model missing from {names}"


def test_mdf_model_class_is_a_model_curve(qapp):
    """The MDF widget must inherit ModelCurve so it plugs into the fit machinery."""
    from chisurf.core.models.model import ModelCurve
    from chisurf.gui.widgets.models.fcs.mdf_widget import MdfFCSModel, MdfFCSWidget

    assert issubclass(MdfFCSModel, ModelCurve)
    assert issubclass(MdfFCSWidget, MdfFCSModel)
    assert str(getattr(MdfFCSWidget, "name", "")).strip()
