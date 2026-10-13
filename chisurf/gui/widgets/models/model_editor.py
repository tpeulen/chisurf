"""Live-wiring seam between a fit's model and its on-screen editor/plots.

Every model is a pure, Qt-free compute model whose editor is generated:

* :func:`build_model_editor` returns the editor widget for the model panel — an
  :class:`~chisurf.gui.widgets.models.auto_model_widget.AutoModelWidget` built
  from the model's ``view_spec()``.
* :func:`model_plot_specs` (from :mod:`chisurf.emtk.fit_pages.plots`) returns the
  ``(plot_class, options)`` list for the fit window, resolved from ``view_spec().plots``.

The ``plot_classes`` attribute this used to fall back on is gone (see the
`GUI & AutoForm <okf/subsystems/gui-autoform.md>`_ concept):
a model naming GUI plot classes was the last hard dependency from the compute
side onto the GUI, and nothing declares one any more.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf import logging

# Re-exported: the fit window's pages resolve Qt-free in chisurf.emtk.fit_pages.plots (the
# emtk shell reads them there); the editor tests still spell them from here.
from chisurf.emtk.fit_pages.plots import FIT_PLOT_KEYS, model_plot_specs  # noqa: F401

#: Attribute under which a pure model caches its on-screen editor widget. Stored
#: in the model's ``__dict__`` (skipped by ``view_spec()`` auto-derive because it
#: is underscore-prefixed, and not pickled because ``Base.__getstate__`` only
#: keeps metadata + name).
_EDITOR_ATTR = "_chisurf_model_editor"


def _is_alive(widget) -> bool:
    """Return True if ``widget`` is a live Qt object (not a deleted C++ shell).

    Clearing the model layout can destroy a cached editor; accessing such a
    dangling wrapper raises ``RuntimeError``. A cheap attribute touch detects it
    across PyQt/PySide without importing binding-specific helpers.
    """
    if widget is None:
        return False
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False


def build_model_editor(model) -> QtWidgets.QWidget:
    """Return the editor widget for ``model``, building it once and caching it.

    The widget is cached on the model (:data:`_EDITOR_ATTR`) so later
    show/hide/lookup operate on the same one. A model that *is* a widget (there
    are none in the tree; a third-party one could be) is returned unchanged.

    Parameters
    ----------
    model : chisurf.core.models.model.Model
        The fit's model.

    Returns
    -------
    QtWidgets.QWidget
        The (cached) :class:`AutoModelWidget` bound to ``model``.
    """
    if isinstance(model, QtWidgets.QWidget):
        return model
    existing = getattr(model, _EDITOR_ATTR, None)
    if _is_alive(existing):
        return existing
    from chisurf.gui.autoform import AutoForm

    widget = AutoForm(model)
    try:
        setattr(model, _EDITOR_ATTR, widget)
    except Exception:  # pragma: no cover - defensive
        pass
    return widget


def model_editor_widget(model):
    """Return the on-screen editor widget for ``model``, or ``None``.

    The cached :class:`AutoModelWidget`, if one has been built (via
    :func:`build_model_editor`). Use this where code manipulates the editor
    directly (show/hide/screenshot).
    """
    if isinstance(model, QtWidgets.QWidget):
        return model
    widget = getattr(model, _EDITOR_ATTR, None)
    return widget if _is_alive(widget) else None


def show_model_editor(model) -> None:
    """Show ``model``'s editor widget if it has one (no-op otherwise)."""
    widget = model_editor_widget(model)
    if widget is not None:
        widget.show()


def hide_model_editor(model) -> None:
    """Hide ``model``'s editor widget if it has one (no-op otherwise)."""
    widget = model_editor_widget(model)
    if widget is not None:
        widget.hide()
