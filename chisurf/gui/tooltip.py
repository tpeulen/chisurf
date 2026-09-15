"""App-wide tooltip word-wrapping.

Long tooltips otherwise render as a single very wide line that can span the whole
screen. :func:`wrap_tooltip` folds tooltip text to a configurable width, and
:func:`install_tooltip_wrapping` applies that folding automatically to *every*
widget tooltip in the application through an application-level event filter that
displays the folded tooltip itself (``QToolTip.showText``) — so any
``setToolTip(...)`` call anywhere in ChiSurf is folded without having to change
the call site.

Configuration lives in the ChiSurf settings YAML under ``gui.tooltip``::

    gui:
      tooltip:
        enabled: true      # install the global folding filter
        wrap_width: 72      # fold plain tooltips longer than this many chars
        curve_preview:
          enabled: true    # draw a curve thumbnail in dataset/curve tooltips
          width: 300
          height: 140

Explicitly multi-line tooltips (already containing newlines) and rich-text/HTML
tooltips (starting with ``<``) are left untouched — Qt wraps those itself.
"""

from __future__ import annotations

import textwrap

from qtpy import QtCore, QtWidgets

#: Fallback width when the setting is missing or unreadable.
_DEFAULT_WIDTH = 72


def _tooltip_cfg() -> dict:
    try:
        from chisurf.core.settings import cs_settings

        cfg = cs_settings.get("gui", {}).get("tooltip", {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def tooltip_wrap_width() -> int:
    """Return the configured tooltip wrap width (``gui.tooltip.wrap_width``)."""
    try:
        width = int(_tooltip_cfg().get("wrap_width", _DEFAULT_WIDTH))
    except (TypeError, ValueError):
        return _DEFAULT_WIDTH
    return width if width > 0 else _DEFAULT_WIDTH


def tooltip_wrapping_enabled() -> bool:
    """Return whether the global tooltip-folding filter should be installed."""
    return bool(_tooltip_cfg().get("enabled", True))


def curve_preview_config() -> dict:
    """Return the ``gui.tooltip.curve_preview`` settings (with defaults filled in).

    Returns
    -------
    dict
        ``{"enabled": bool, "width": int, "height": int}``. Callers that render a
        curve thumbnail into a tooltip check ``enabled`` first and fall back to a
        plain-text tooltip when it is ``False``.
    """
    cfg = _tooltip_cfg().get("curve_preview", {})
    if not isinstance(cfg, dict):
        cfg = {}
    out = {"enabled": bool(cfg.get("enabled", True)), "width": 300, "height": 140}
    for key in ("width", "height"):
        try:
            value = int(cfg.get(key, out[key]))
        except (TypeError, ValueError):
            continue
        if value > 0:
            out[key] = value
    return out


def curve_preview_enabled() -> bool:
    """Return whether curve thumbnails are drawn into tooltips."""
    return curve_preview_config()["enabled"]


def wrap_tooltip(text: str, width: int | None = None) -> str:
    """Word-wrap ``text`` to ``width`` (default: the configured width).

    Existing explicit line breaks are preserved (each paragraph wrapped
    independently); rich-text/HTML tooltips are returned unchanged. Plain
    tooltips are localized here (:func:`chisurf.core.support.i18n.tr`) — the app-wide
    tooltip event filter routes every ``setToolTip`` through this function, so
    this is the single seam that localizes imperative tooltip strings.
    """
    from chisurf.core.support.i18n import tr

    text = str(text or "").strip()
    if not text or text.startswith("<"):
        return text
    text = tr(text)
    if width is None:
        width = tooltip_wrap_width()
    out: list[str] = []
    for para in text.splitlines():
        para = para.strip()
        out.append(textwrap.fill(para, width=width) if para else "")
    return "\n".join(out)


def set_tooltip(widget: QtWidgets.QWidget, text: str, width: int | None = None) -> None:
    """Set a folded tooltip on ``widget`` (convenience for call sites)."""
    widget.setToolTip(wrap_tooltip(text, width))


class _TooltipWrapFilter(QtCore.QObject):
    """Show a folded tooltip for every widget that has one.

    On a ``QEvent.ToolTip`` we display the widget's tooltip *ourselves* via
    :meth:`QToolTip.showText` with the folded text and consume the event, so Qt's
    default (unfolded, one-wide-line) tooltip never runs. We only intervene when
    the widget actually has a tooltip; otherwise the event is passed through so
    Qt can propagate it to a parent (tooltip inheritance).
    """

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if event.type() == QtCore.QEvent.ToolTip and isinstance(obj, QtWidgets.QWidget):
            tip = obj.toolTip()
            if tip:
                QtWidgets.QToolTip.showText(event.globalPos(), wrap_tooltip(tip), obj)
                return True
        return False


_filter_singleton: _TooltipWrapFilter | None = None


def install_tooltip_wrapping(app: QtWidgets.QApplication | None = None) -> None:
    """Install the global tooltip-folding filter on the application (once)."""
    global _filter_singleton
    if _filter_singleton is not None or not tooltip_wrapping_enabled():
        return
    app = app or QtWidgets.QApplication.instance()
    if app is None:
        return
    _filter_singleton = _TooltipWrapFilter(app)
    app.installEventFilter(_filter_singleton)
