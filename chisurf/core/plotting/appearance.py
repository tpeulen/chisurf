"""How a fit plot looks: the ``gui.plot`` settings, read live, as what a plot draws.

Every reader goes through here at the moment it draws, never through a copy
taken at import. A module-level ``colors = settings["gui"]["plot"]["colors"]``
is a snapshot: *Settings ▸ Plots* replaces that dictionary when it applies an
edit, so the snapshot kept the old palette until the next start and every
colour, the line width and the fit-range band looked as if they were ignored.

Qt-free: the plot windows (through chiplot), the settings panel's preview and
the tests read the same functions, so the preview cannot drift from the plots.
"""

from __future__ import annotations

import logging
import weakref
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

#: The shipped values, for a settings dictionary that lacks a key.
DEFAULTS: dict[str, Any] = {
    "colors": {
        "data": "#ffa629",
        "model": "#d400cd",
        "irf": "#4284f5",
        "residuals": "#df0101",
        "auto_corr": "#ff00ff",
        "region_selector": "#26a298",
        "region_selector_alpha": 50,
        "active_transparency": 1.0,
        "inactive_transparency": 0.4,
    },
    "line_width": 2.0,
    "font_size": 0,
    "enable_grid": True,
    "grid_alpha": 0.3,
    "show_data_grid": True,
    "show_residual_grid": True,
    "show_acorr_grid": True,
    "enable_region_selector": True,
    "show_legend": True,
    "label_axis": True,
}

#: Curve roles with a colour of their own (``gui.plot.colors`` keys).
CURVE_ROLES = ("data", "model", "irf", "residuals", "auto_corr")

#: The panels of a fit plot that have a grid switch: role -> settings key.
GRID_PANELS = {
    "data": "show_data_grid",
    "residuals": "show_residual_grid",
    "acorr": "show_acorr_grid",
}

#: The data trace is drawn at this fraction of the line width: it is noisy, and at
#: full width the noise thickens into a band that hides the model running through it.
DATA_WIDTH_FACTOR = 0.5

#: chiplot's ``grid(alpha=...)`` at which a plot shows the theme's own grid; the
#: grid-opacity setting is drawn relative to it.
GRID_REFERENCE_ALPHA = 0.3

#: The factor on the theme's gridlines at ``alpha = 1``: solid lines (the theme
#: draws its grid at an alpha of 20 out of 255).
GRID_FULL_STRENGTH = 255.0 / 20.0


#: Who wants to hear that a plot setting changed: bound methods (held weakly, so an open plot that
#: is closed or dropped never keeps the list alive or gets called) and plain functions.
_subscribers: list[weakref.ref | Callable[[str], None]] = []


def subscribe(callback: Callable[[str], None]) -> Callable[[], None]:
    """Be told, with the name of the changed field, whenever a plot setting changes.

    This is the one notification every open plot subscribes to: *Settings ▸ Plots* calls
    :func:`notify` after it writes a value, and each subscriber restyles itself from the
    live readers in this module. A bound method is held weakly.

    Parameters
    ----------
    callback : callable
        Called as ``callback(name)``; *name* is the settings field that changed (``""``: several).

    Returns
    -------
    callable
        Takes no arguments; ends the subscription.
    """
    entry: weakref.ref | Callable[[str], None]
    entry = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else callback  # type: ignore[arg-type]
    _subscribers.append(entry)

    def unsubscribe() -> None:
        try:
            _subscribers.remove(entry)
        except ValueError:
            pass

    return unsubscribe


def notify(name: str = "") -> None:
    """Tell every subscriber that the plot setting *name* changed (the values are already stored).

    A subscriber that raises is logged and does not stop the others.
    """
    for entry in list(_subscribers):
        callback = entry() if isinstance(entry, weakref.ref) else entry
        if callback is None:
            try:
                _subscribers.remove(entry)
            except ValueError:
                pass
            continue
        try:
            callback(name)
        except Exception:  # noqa: BLE001 - one plot that cannot restyle must not strand the rest
            logger.exception("plot appearance subscriber failed for %r", name)


def plot_settings() -> dict:
    """The live ``gui.plot`` dictionary (empty when the settings cannot be read)."""
    try:
        from chisurf.core.settings import cs_settings
    except Exception:  # noqa: BLE001 - no settings: the shipped look
        return {}
    block = (cs_settings.get("gui") or {}).get("plot")
    return block if isinstance(block, dict) else {}


def _value(key: str, settings: dict | None = None) -> Any:
    block = plot_settings() if settings is None else settings
    return block.get(key, DEFAULTS[key])


def _color_value(key: str, settings: dict | None = None) -> Any:
    block = plot_settings() if settings is None else settings
    colors = block.get("colors") or {}
    return colors.get(key, DEFAULTS["colors"][key])


def hex_rgb(value: Any, default: tuple[int, int, int] = (180, 180, 190)) -> tuple[int, int, int]:
    """``"#abc"`` / ``"#aabbcc"`` / ``"#aabbccdd"`` as an ``(r, g, b)`` triple.

    Parameters
    ----------
    value : Any
        A hex colour string.
    default : tuple of int
        Returned for anything that is not a hex colour.

    Returns
    -------
    tuple of int
    """
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    try:
        if len(raw) in (6, 8):
            return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        pass
    return default


def curve_color(role: str, settings: dict | None = None) -> str:
    """The colour of a curve role (one of :data:`CURVE_ROLES`) as stored, e.g. ``"#ffa629"``."""
    return str(_color_value(role, settings))


def line_width(role: str = "model", settings: dict | None = None) -> float:
    """The width a curve of *role* is drawn at: the line width, half of it for data."""
    width = float(_value("line_width", settings))
    return width * DATA_WIDTH_FACTOR if role == "data" else width


def region_rgba(settings: dict | None = None) -> tuple[int, int, int, int] | None:
    """The fit-range band's fill, or ``None`` when the selector is switched off."""
    if not bool(_value("enable_region_selector", settings)):
        return None
    r, g, b = hex_rgb(_color_value("region_selector", settings))
    alpha = int(min(max(float(_color_value("region_selector_alpha", settings)), 0.0), 255.0))
    return (r, g, b, alpha)


def grid_alpha(panel: str, settings: dict | None = None) -> float | None:
    """The grid opacity of a fit-plot panel (``data``/``residuals``/``acorr``); ``None``: no grid."""
    if not bool(_value("enable_grid", settings)):
        return None
    block = plot_settings() if settings is None else settings
    if not bool(block.get(GRID_PANELS[panel], True)):
        return None
    return min(max(float(_value("grid_alpha", settings)), 0.0), 1.0)


def grid_strength(alpha: float) -> float:
    """A chiplot grid alpha as a factor on the theme's gridlines.

    ``0`` draws none, :data:`GRID_REFERENCE_ALPHA` the theme's grid and ``1`` solid
    lines, linear in between on either side. The theme's grid is faint, so a scale
    that is linear all the way would leave "100 %" barely brighter than the theme.

    Parameters
    ----------
    alpha : float
        The grid alpha, 0-1.

    Returns
    -------
    float
    """
    a = min(max(float(alpha), 0.0), 1.0)
    if a <= GRID_REFERENCE_ALPHA:
        return a / GRID_REFERENCE_ALPHA
    reach = (a - GRID_REFERENCE_ALPHA) / (1.0 - GRID_REFERENCE_ALPHA)
    return 1.0 + reach * (GRID_FULL_STRENGTH - 1.0)


def fit_opacity(active: bool, settings: dict | None = None) -> float:
    """Opacity of the curves of the selected fit (*active*) or of the other fits of a group."""
    key = "active_transparency" if active else "inactive_transparency"
    return min(max(float(_color_value(key, settings)), 0.0), 1.0)


def show_legend(settings: dict | None = None) -> bool:
    """Whether a new fit plot shows its legend."""
    return bool(_value("show_legend", settings))


def label_axes(settings: dict | None = None) -> bool:
    """Whether a fit plot names its axes."""
    return bool(_value("label_axis", settings))


def font_size(settings: dict | None = None) -> int:
    """Point size of the axis text; ``0`` follows the interface font."""
    try:
        return max(int(_value("font_size", settings) or 0), 0)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "CURVE_ROLES",
    "DATA_WIDTH_FACTOR",
    "DEFAULTS",
    "GRID_FULL_STRENGTH",
    "GRID_PANELS",
    "GRID_REFERENCE_ALPHA",
    "curve_color",
    "fit_opacity",
    "font_size",
    "grid_alpha",
    "grid_strength",
    "hex_rgb",
    "label_axes",
    "line_width",
    "notify",
    "plot_settings",
    "region_rgba",
    "show_legend",
    "subscribe",
]
