"""Every module under ``chisurf/gui/widgets/models`` must import.

What lives there now is deprecation shims: a user copy of
``experiment_configs.yaml`` *replaces* the bundled model list and a pickled
project pins class paths, so an old path such as
``chisurf.gui.widgets.models.fcs.MaxEntFCSWidget`` still has to resolve — to the
pure model that replaced it. A path that raises on import drops its entry from
the model menu **without saying so**, which is the failure this file exists to
catch.

It replaces ``test_model_widget_metaclass.py``. That file asserted that
``ModelWidget`` carried a metaclass combining ``ABCMeta`` with Qt's, which is
what made a hand-written *model widget* definable at all. There are none left
(PRD-38), ``model_widget.py`` is deleted, and the file had been red since the
module it named as its worked example was removed.
"""

from __future__ import annotations

import importlib
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MODEL_WIDGETS = (
    pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "widgets" / "models"
)


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _model_widget_modules():
    """Every module under ``chisurf/gui/widgets/models``, packages included."""
    root = MODEL_WIDGETS.parents[3]
    return [
        ".".join(path.relative_to(root).with_suffix("").parts).removesuffix(".__init__")
        for path in sorted(MODEL_WIDGETS.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def test_there_are_model_modules_to_check():
    """A path typo here would make the sweep below pass by checking nothing."""
    modules = _model_widget_modules()
    assert len(modules) > 10
    assert "chisurf.gui.widgets.models.model_editor" in modules


@pytest.mark.parametrize("module", _model_widget_modules())
def test_every_model_module_imports(qapp, module):
    """An import error here is a model menu entry that vanishes silently."""
    importlib.import_module(module)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("chisurf.gui.widgets.models.fcs.DyeShapeFCSWidget", "FCS dye shape"),
        ("chisurf.gui.widgets.models.fcs.MaxEntFCSWidget", "FCS MaxEnt"),
        ("chisurf.gui.widgets.models.fcs.MaxEntRHWidget", "FCS MaxEnt rH"),
        ("chisurf.gui.widgets.models.fcs.ParseFCSWidget", "Parse-Model"),
        ("chisurf.gui.widgets.models.proteinmc.ProteinMCModelWidget", "ProteinMC"),
        ("chisurf.gui.widgets.models.stopped_flow.ReactionWidget", "Reaction-System"),
        ("chisurf.gui.widgets.models.pda2c.Pda2cSimpleModelWidget", "PDA2c-discrete"),
        ("chisurf.gui.widgets.models.global_model.GlobalFitModelWidget", "Global fit"),
    ],
)
def test_deprecated_widget_paths_resolve_to_the_pure_model(qapp, path, expected):
    """An old class path still resolves, and to a model with the right name.

    ``add_fit`` matches on ``model.name``, so a path that resolves to the *wrong*
    class is as broken as one that does not resolve — and just as quiet.
    """
    from qtpy import QtWidgets

    module_name, class_name = path.rsplit(".", 1)
    cls = getattr(importlib.import_module(module_name), class_name)
    assert cls is not None, f"{path} resolved to None"
    assert not issubclass(cls, QtWidgets.QWidget), f"{path} is still a widget"
    assert str(getattr(cls, "name", "")).strip() == expected


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
