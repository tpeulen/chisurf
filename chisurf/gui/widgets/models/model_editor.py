"""Live-wiring seam between a fit's model and its on-screen editor/plots.

Every model is a pure, Qt-free compute model whose editor is generated:

* :func:`build_model_editor` returns the editor widget for the model panel — an
  :class:`~chisurf.gui.widgets.models.auto_model_widget.AutoModelWidget` built
  from the model's ``view_spec()``.
* :func:`model_plot_specs` returns the ``(plot_class, options)`` list for the fit
  subwindow, resolved from ``view_spec().plots``.

The ``plot_classes`` attribute this used to fall back on is gone (see the
`GUI & AutoForm <okf/subsystems/gui-autoform.md>`_ concept):
a model naming GUI plot classes was the last hard dependency from the compute
side onto the GUI, and nothing declares one any more.
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf import logging

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


def model_plot_specs(model):
    """Return ``[(plot_class, options), ...]`` for the fit subwindow.

    Resolved from the model's ``view_spec().plots``: each entry names a plot by
    registry key, and the accessors its options carry are resolved here because
    JSON cannot hold a callable.

    Returns an empty list when the model declares no plots — a fit window with no
    plot tabs is a visible, fixable state; silently substituting some other
    model's plots is not.
    """
    try:
        view = model.view_spec()
    except Exception as exc:  # pragma: no cover - defensive
        logging.debug(f"model_plot_specs: view_spec() failed: {exc}")
        view = None

    if view is not None:
        try:
            from chisurf.gui.autoform.sections.builtin import (
                _resolve_accessor,
                resolve_distribution_options,
            )
            from chisurf.gui.autoform.sections.registry import resolve_plot_specs

            specs = resolve_plot_specs(view)
            if specs:
                resolved = []
                for cls, opts in specs:
                    opts = dict(opts)
                    # distribution plots keep accessors under distribution_options
                    if "distribution_options" in opts:
                        opts = resolve_distribution_options(opts)
                    # other plots (e.g. residual2d) may name a top-level accessor
                    if isinstance(opts.get("accessor"), str):
                        opts["accessor"] = _resolve_accessor(opts["accessor"])
                    # multi-source image plots name one accessor per source, and
                    # optionally an accessor reporting how many frames/lags exist
                    if isinstance(opts.get("sources"), dict):
                        opts["sources"] = {
                            key: (
                                {**spec, "accessor": _resolve_accessor(spec["accessor"])}
                                if isinstance(spec, dict) and isinstance(spec.get("accessor"), str)
                                else spec
                            )
                            for key, spec in opts["sources"].items()
                        }
                    if isinstance(opts.get("max_frames_accessor"), str):
                        opts["max_frames_accessor"] = _resolve_accessor(opts["max_frames_accessor"])
                    resolved.append((cls, opts))
                return resolved
        except Exception as exc:  # pragma: no cover - defensive
            logging.error(f"model_plot_specs: could not resolve plots: {exc}")

    return []
