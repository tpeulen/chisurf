"""A model widget must be *definable*: ABCMeta and Qt's metaclass must agree.

``Model`` is an abstract base class (``ABCMeta``); a ``QWidget`` carries Qt's
``wrappertype``. A class that inherits both without a metaclass combining them
raises ``TypeError: metaclass conflict`` while it is being **defined** — so the
whole module fails to import, and every model in it silently disappears from the
model menu. ``ModelWidget`` exists to carry that combined metaclass
(``_ModelWidgetMeta``); the failure mode is that a new model widget inherits
``QtWidgets.QWidget`` directly instead, which looks right and is not.

That is what happened to ``EtModelFreeWidget``: ``chisurf.gui.widgets.models.
tcspc.et`` could not be imported at all, and the Et model-free entry was missing.
"""
from __future__ import annotations

import importlib
import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MODEL_WIDGETS = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "gui" / "widgets" / "models"


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _model_widget_modules():
    """Every module under ``chisurf/gui/widgets/models`` (packages excluded)."""
    root = MODEL_WIDGETS.parents[3]
    return [
        ".".join(path.relative_to(root).with_suffix("").parts)
        for path in sorted(MODEL_WIDGETS.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]


def test_there_are_model_widget_modules_to_check():
    """A path typo here would make the sweep below pass by checking nothing."""
    modules = _model_widget_modules()
    assert len(modules) > 10
    assert "chisurf.gui.widgets.models.tcspc.et" in modules


@pytest.mark.parametrize("module", _model_widget_modules())
def test_every_model_widget_module_imports(qapp, module):
    """An import error here is a model that cannot appear in the GUI at all."""
    importlib.import_module(module)


def test_the_combined_metaclass_is_what_makes_that_possible(qapp):
    """``ModelWidget``'s metaclass must derive from *both* of its parents'.

    Stated directly so the reason the sweep above passes cannot be quietly
    removed: without this, mixing a model into a widget is a TypeError.
    """
    import abc

    from qtpy import QtWidgets

    from chisurf.core.models.model import Model
    from chisurf.gui.widgets.models.model_widget import ModelWidget

    meta = type(ModelWidget)
    assert issubclass(meta, abc.ABCMeta)
    assert issubclass(meta, type(QtWidgets.QWidget))
    assert issubclass(ModelWidget, Model)


def test_the_et_model_free_widget_is_a_model_widget(qapp):
    """The regression that motivated this file: it must import and be named.

    ``name`` is the string the model combobox shows and ``add_fit`` matches on,
    and it is inherited from the model — which is only reachable if the class
    could be defined in the first place.
    """
    from chisurf.gui.widgets.models.model_widget import ModelWidget
    from chisurf.gui.widgets.models.tcspc.et import EtModelFreeWidget

    assert issubclass(EtModelFreeWidget, ModelWidget)
    assert str(getattr(EtModelFreeWidget, "name", "")).strip() == "Et-Model free"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
