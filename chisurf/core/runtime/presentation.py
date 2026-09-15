"""The seam a view attaches to, so the model never reaches for one.

Some model-layer work has to *tell* a view something: a project finished
loading and the fit list is new, a fit ran and the curves moved. Written the
obvious way that is ``from chisurf.gui import run_on_gui_thread`` inside
:mod:`chisurf.core`, which inverts the dependency the architecture rests on --
the model then cannot be imported without a widget toolkit present, cannot be
driven by a script or the server, and cannot be tested headlessly.

So the direction is turned around. The model calls :func:`notify` and knows
nothing about who listens; the view calls :func:`set_presenter` once, at
start-up, and supplies the only thing it is asked for: *run this callable
where a view can safely be touched.* On Qt that is
``chisurf.gui.run_on_gui_thread``; in a script, a test or the server there is
no presenter and the callable simply runs where it is.

**No presenter is the normal case, not a degraded one.** Headless is how the
CLI, the server and most of the test suite use this package, so the default
has to be the one that works there: :func:`notify` runs the callable inline
and returns its result. A GUI is one presenter among several rather than the
assumed one.

Errors are swallowed, deliberately and only here. A refresh that fails must
not take down the computation that asked for it -- the model has already done
its work and published its result by the time it notifies, and the notify is
the last statement rather than a step the caller depends on. A failure is
logged at debug level, which is where a missing repaint is diagnosed.

Examples
--------
From the model, after something the view should see::

    from chisurf.core.runtime import presentation
    presentation.notify(window.update)

From the view, once, at start-up::

    import chisurf.gui
    presentation.set_presenter(chisurf.gui.run_on_gui_thread)
"""
from __future__ import annotations

import typing

import chisurf.logging

__all__ = ["set_presenter", "get_presenter", "notify", "defer"]

#: The view's "run this where a view may be touched", or ``None`` headless.
_presenter: typing.Optional[typing.Callable] = None

#: The view's "run this soon, but not inside the current call", or ``None``.
_deferrer: typing.Optional[typing.Callable] = None


def set_presenter(presenter=None, deferrer=None) -> None:
    """Install the view's dispatchers. Called once, by the view.

    Parameters
    ----------
    presenter : callable, optional
        ``presenter(func, *args, **kwargs)`` -- run *func* where a view may
        safely be touched, and return its result if it can.
        ``chisurf.gui.run_on_gui_thread`` is the Qt one. ``None`` detaches,
        which is what a test that installed a fake should do afterwards.
    deferrer : callable, optional
        ``deferrer(func)`` -- run *func* after the current call has returned,
        for work that must not happen inside it: rebuilding the widgets that
        the *currently running* action is loading data for, say. On Qt that
        is a zero-delay single-shot timer. Falls back to *presenter*, and
        then to running inline.
    """
    global _presenter, _deferrer
    _presenter = presenter
    _deferrer = deferrer


def get_presenter():
    """Return the installed presenter, or ``None`` when headless."""
    return _presenter


def notify(func, *args, **kwargs):
    """Run *func* where a view may be touched; inline when there is no view.

    Returns whatever *func* (or the presenter) returns, and ``None`` if it
    raised -- see the module docstring for why a failed refresh is not
    allowed to propagate.
    """
    if func is None:
        return None
    target = _presenter
    try:
        if target is None:
            return func(*args, **kwargs)
        return target(func, *args, **kwargs)
    except Exception:
        chisurf.logging.debug(
            "presentation.notify: %r failed", func, exc_info=True)
        return None


def defer(func, *args, **kwargs):
    """Run *func* after the current call returns; inline when headless.

    The distinction from :func:`notify` matters exactly once: when the model
    is *in the middle of* the operation whose result the view would rebuild
    itself from. Doing that inline gives the view a half-built model.
    """
    if func is None:
        return None
    if _deferrer is not None:
        try:
            return _deferrer(lambda: func(*args, **kwargs))
        except Exception:
            chisurf.logging.debug(
                "presentation.defer: %r failed", func, exc_info=True)
            return None
    return notify(func, *args, **kwargs)
