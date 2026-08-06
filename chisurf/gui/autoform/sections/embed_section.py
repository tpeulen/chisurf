"""A general ``embed`` custom section: host any existing widget inside a form.

Lets a ``.view.json`` drop a ready-made widget (a plugin editor, a tool panel)
straight into an AutoForm — no per-widget glue code. This is what attaches the
FCS channel and detector-definition editors *inside* the onboarding wizard
(instead of popping them as detached floating windows), and it is reusable by any
wizard/tool that needs to embed an existing widget.

Authoring::

    {"type": "custom", "key": "embed",
     "options": {"widget": "chisurf.plugins.fcs.fcs_channel_preset.gui.tool:FCSChannelWidget"}}

    {"type": "custom", "key": "embed", "options": {"attr": "histogram_widget"}}

``options`` keys:

* ``widget`` — dotted import path ``"pkg.module:ClassName"`` or
  ``"pkg.module.ClassName"``; a *fresh* instance is constructed.
* ``attr`` — name of a model attribute (or zero-argument method) holding a widget
  that already exists, which is adopted as it is. This is what a panel loaded
  from a ``.ui`` file needs: its widgets are built by ``uic``, wired by name and
  referenced from a dozen places, so constructing a second copy is not the same
  thing as showing the one that is already there. Exactly one of ``widget`` and
  ``attr`` is used, ``attr`` first.
* ``kwargs`` — mapping passed to the widget constructor (``widget`` form only).
* ``pass_model`` — when ``True``, the bound model is passed as ``model=`` kwarg
  (``widget`` form only).
* ``expanding`` — mark the widget to take spare vertical space (default ``True``).
  Set ``false`` for a compact panel of controls, which should stay at the height
  it needs.
"""

from __future__ import annotations

import importlib

from qtpy import QtWidgets

from chisurf import logging

from .registry import register_section


def _resolve(path: str):
    """Import and return the object named by ``"pkg.module:Attr"`` or ``"pkg.module.Attr"``."""
    if ":" in path:
        module_name, attr = path.split(":", 1)
    else:
        module_name, _, attr = path.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _adopt(model, attr: str):
    """Return the widget the model already holds under `attr`, or ``None``."""
    value = getattr(model, attr, None)
    if callable(value):
        try:
            value = value()
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning(f"embed section: {attr}() failed: {exc}")
            return None
    if value is None:
        logging.warning(f"embed section: model has no widget at {attr!r}")
    return value


@register_section("embed")
def _embed_section_factory(model, target=None, **options):
    """Return the widget named by ``options['attr']`` or ``options['widget']``."""
    attr = options.get("attr", "")
    if attr:
        widget = _adopt(model, str(attr))
        if widget is None:
            return None
        if options.get("expanding", True):
            widget._autoform_expanding = True
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                 QtWidgets.QSizePolicy.Expanding)
        return widget

    path = options.get("widget", "")
    if not path:
        logging.warning("embed section: neither 'attr' nor 'widget' given")
        return None
    try:
        cls = _resolve(str(path))
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning(f"embed section: could not import {path!r}: {exc}")
        return None

    kwargs = dict(options.get("kwargs", {}) or {})
    if options.get("pass_model", False):
        kwargs.setdefault("model", model)
    try:
        widget = cls(**kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning(f"embed section: could not construct {path!r}: {exc}")
        return None

    if options.get("expanding", True):
        widget._autoform_expanding = True
        widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    return widget


__all__ = ["_embed_section_factory"]
