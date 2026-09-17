"""GUI-side translation bootstrap.

Binds ChiSurf's Qt-free core translation seam (:mod:`chisurf.core.support.i18n`) to a
real Qt translator and installs a :class:`~qtpy.QtCore.QTranslator` for the
configured UI language onto the running :class:`~qtpy.QtWidgets.QApplication`.

Call :func:`install_translation` once, right after the ``QApplication`` is
created and **before** any window is built or any ``.ui`` file is loaded — Qt
only translates strings that are looked up *after* the translator is installed.
The single call:

1. sets the core backend to ``QCoreApplication.translate`` so every
   data-driven ``view.json`` / ``manifest.json`` string (routed through
   :func:`chisurf.core.support.i18n.tr`) is localized; and
2. loads ``chisurf/gui/i18n/chisurf_<code>.qm`` for the configured locale, which
   also covers all ``.ui`` strings for free.

The canonical source language is English (``en``); it needs no catalogue and the
translator install is skipped for it (Qt falls back to the source text).
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

#: Directory holding the compiled ``.qm`` catalogues (built from ``.ts`` sources).
I18N_DIR = pathlib.Path(__file__).parent / "i18n"

#: Keeps installed translators alive for the lifetime of the application.
_installed: list[QtCore.QTranslator] = []


class _LanguageNotifier(QtCore.QObject):
    """App-wide announcer that the active UI language changed.

    Every language picker (the Settings combo, the ribbon flag dropdown, …)
    connects to :data:`language_changed` and refreshes its own display, so
    switching the language through any one of them keeps the others in sync.
    """

    #: Emitted with the newly applied locale code after :func:`apply_language`.
    language_changed = QtCore.Signal(str)


#: Process-wide singleton notifier (a plain QObject; no QApplication required to
#: construct). Import and connect to ``language_changed`` from any picker widget.
language_notifier = _LanguageNotifier()


def _live_notifier() -> _LanguageNotifier:
    """Return :data:`language_notifier`, recreating it if its C++ side was deleted.

    A module-level ``QObject`` can outlive its underlying C++ object across
    ``QApplication`` teardown/recreation (which happens between test modules; the
    real app keeps a single ``QApplication`` for its lifetime, so this never
    fires there). Reviving it keeps ``emit()``/``connect()`` from hitting a dead
    wrapper.
    """
    global language_notifier
    try:
        language_notifier.signalsBlocked()  # cheap touch; raises if C++ is gone
    except RuntimeError:
        language_notifier = _LanguageNotifier()
    return language_notifier


#: Human-readable, self-endonym display names for known locale codes. Codes not
#: listed fall back to the bare code so a new ``.qm`` is still selectable.
LANGUAGE_DISPLAY_NAMES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ja": "日本語",
    "zh": "中文",
    "ru": "Русский",
}

#: Flag emoji per locale, for the compact flag-dropdown switchers. English maps
#: to the Union Jack (🇬🇧) rather than the US flag — ChiSurf's UI English follows
#: British conventions. Locales without an entry fall back to a globe (🌐).
LANGUAGE_FLAGS = {
    "en": "🇬🇧",
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "it": "🇮🇹",
    "pt": "🇵🇹",
    "nl": "🇳🇱",
    "ja": "🇯🇵",
    "zh": "🇨🇳",
    "ru": "🇷🇺",
}


def language_flag(code: str) -> str:
    """Return the flag emoji for a locale ``code`` (globe 🌐 when unknown)."""
    return LANGUAGE_FLAGS.get(str(code or "").strip(), "🌐")


#: Painted-flag recipes per locale. Emoji flags (regional-indicator pairs) render
#: unreliably in Qt menus/buttons — many font stacks show the two letters in
#: dotted boxes instead of a flag — so the pickers use small painted icons built
#: from these specs instead. Each entry is ``(kind, data)``; unknown codes fall
#: back to the two-letter code on a neutral pill. Colours follow common flag
#: references. ``en`` is the Union Jack (ChiSurf UI English follows British usage).
_FLAG_SPECS: dict[str, tuple[str, object]] = {
    "de": ("hbands", [("#000000", 1), ("#DD0000", 1), ("#FFCE00", 1)]),
    "fr": ("vbands", [("#0055A4", 1), ("#FFFFFF", 1), ("#EF4135", 1)]),
    "it": ("vbands", [("#009246", 1), ("#FFFFFF", 1), ("#CE2B37", 1)]),
    "ru": ("hbands", [("#FFFFFF", 1), ("#0039A6", 1), ("#D52B1E", 1)]),
    "nl": ("hbands", [("#AE1C28", 1), ("#FFFFFF", 1), ("#21468B", 1)]),
    "es": ("hbands", [("#AA151B", 1), ("#F1BF00", 2), ("#AA151B", 1)]),
    "pt": ("vbands", [("#006600", 2), ("#FF0000", 3)]),
    "ja": ("circle", ("#FFFFFF", "#BC002D")),
    "zh": ("star", ("#DE2910", "#FFDE00")),
    "en": ("union_jack", None),
}

#: Cache of painted flag icons keyed by ``(code, height)`` so repeated menu/combo
#: rebuilds don't re-paint.
_flag_icon_cache: dict[tuple[str, int], QtGui.QIcon] = {}


def _flag_pixmap(code: str, w: int, h: int) -> QtGui.QPixmap:
    """Paint a flag for ``code`` into a ``w×h`` pixmap (HiDPI-aware)."""
    app = QtWidgets.QApplication.instance()
    dpr = float(app.devicePixelRatio()) if app is not None else 1.0
    pm = QtGui.QPixmap(int(round(w * dpr)), int(round(h * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.GlobalColor.transparent)

    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    rect = QtCore.QRectF(0.0, 0.0, float(w), float(h))
    p.setClipRect(rect)

    spec = _FLAG_SPECS.get(str(code or "").strip())
    kind = spec[0] if spec else "code"
    data = spec[1] if spec else code

    if kind in ("hbands", "vbands"):
        bands = data  # list[(hex, weight)]
        total = sum(weight for _c, weight in bands) or 1
        off = 0.0
        for colour, weight in bands:
            frac = weight / total
            if kind == "hbands":
                band = QtCore.QRectF(0.0, off * h, float(w), frac * h)
            else:
                band = QtCore.QRectF(off * w, 0.0, frac * w, float(h))
            p.fillRect(band, QtGui.QColor(colour))
            off += frac
    elif kind == "circle":
        bg, fg = data
        p.fillRect(rect, QtGui.QColor(bg))
        r = min(w, h) * 0.30
        p.setBrush(QtGui.QColor(fg))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(QtCore.QPointF(w / 2.0, h / 2.0), r, r)
    elif kind == "star":
        bg, fg = data
        p.fillRect(rect, QtGui.QColor(bg))
        _draw_star(p, QtCore.QPointF(w * 0.32, h * 0.42), min(w, h) * 0.22, QtGui.QColor(fg))
    elif kind == "union_jack":
        _draw_union_jack(p, w, h)
    else:  # unknown code → two-letter code on a neutral pill
        p.fillRect(rect, QtGui.QColor("#5a5a6a"))
        p.setPen(QtGui.QColor("#ffffff"))
        f = p.font()
        f.setPixelSize(int(h * 0.62))
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, str(code or "?")[:2].upper())

    # Hairline border so pale flags (e.g. the white band of fr/nl) read on any bg.
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 60), 1))
    p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
    p.end()
    return pm


def _draw_star(p: QtGui.QPainter, centre: QtCore.QPointF, r: float, colour: QtGui.QColor) -> None:
    """Draw a filled five-pointed star centred at ``centre`` with radius ``r``."""
    import math

    poly = QtGui.QPolygonF()
    for i in range(5):
        ang = -math.pi / 2 + i * 2 * math.pi / 5
        poly.append(QtCore.QPointF(centre.x() + r * math.cos(ang), centre.y() + r * math.sin(ang)))
        inner = -math.pi / 2 + (i + 0.5) * 2 * math.pi / 5
        poly.append(
            QtCore.QPointF(
                centre.x() + r * 0.4 * math.cos(inner), centre.y() + r * 0.4 * math.sin(inner)
            )
        )
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(colour)
    p.drawPolygon(poly)


def _draw_union_jack(p: QtGui.QPainter, w: int, h: int) -> None:
    """Paint a simplified but recognisable Union Jack into a ``w×h`` area."""
    blue = QtGui.QColor("#012169")
    white = QtGui.QColor("#FFFFFF")
    red = QtGui.QColor("#C8102E")
    p.fillRect(QtCore.QRectF(0.0, 0.0, float(w), float(h)), blue)

    tl, tr = QtCore.QPointF(0, 0), QtCore.QPointF(w, 0)
    bl, br = QtCore.QPointF(0, h), QtCore.QPointF(w, h)
    # White then red diagonals (saltire).
    p.setPen(QtGui.QPen(white, max(2.0, h * 0.26), cap=QtCore.Qt.PenCapStyle.FlatCap))
    p.drawLine(tl, br)
    p.drawLine(tr, bl)
    p.setPen(QtGui.QPen(red, max(1.0, h * 0.10), cap=QtCore.Qt.PenCapStyle.FlatCap))
    p.drawLine(tl, br)
    p.drawLine(tr, bl)
    # White then red upright cross (St George), drawn over the saltire.
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    vw, hh = w * 0.34, h * 0.34
    p.fillRect(QtCore.QRectF((w - vw) / 2, 0, vw, h), white)
    p.fillRect(QtCore.QRectF(0, (h - hh) / 2, w, hh), white)
    vw2, hh2 = w * 0.18, h * 0.18
    p.fillRect(QtCore.QRectF((w - vw2) / 2, 0, vw2, h), red)
    p.fillRect(QtCore.QRectF(0, (h - hh2) / 2, w, hh2), red)


def language_flag_icon(code: str, height: int = 14) -> QtGui.QIcon:
    """Return a painted flag :class:`QIcon` for ``code`` (cached by size).

    Painted icons are used instead of emoji flags because regional-indicator
    emoji render unreliably in Qt menus/buttons. The icon is a 4:3 flag; unknown
    locales get the two-letter code on a neutral pill.
    """
    code = str(code or "").strip()
    key = (code, int(height))
    icon = _flag_icon_cache.get(key)
    if icon is None:
        w = int(round(height * 4 / 3))
        icon = QtGui.QIcon(_flag_pixmap(code, w, height))
        _flag_icon_cache[key] = icon
    return icon


def _qm_path(code: str) -> pathlib.Path:
    """Return the expected ``.qm`` catalogue path for a locale ``code``."""
    return I18N_DIR / f"chisurf_{code}.qm"


def available_languages() -> list[str]:
    """Return the selectable UI language codes.

    Always includes the canonical source language ``en`` (which needs no
    catalogue), plus every locale that ships a compiled ``chisurf_<code>.qm``
    catalogue. Sorted with ``en`` first, then alphabetically.
    """
    codes = {"en"}
    try:
        for qm in I18N_DIR.glob("chisurf_*.qm"):
            code = qm.stem.removeprefix("chisurf_").strip()
            if code:
                codes.add(code)
    except Exception:  # pragma: no cover - defensive
        pass
    rest = sorted(c for c in codes if c != "en")
    return ["en", *rest]


def language_display_name(code: str) -> str:
    """Return the human-readable name for a locale ``code`` (endonym if known)."""
    code = str(code or "").strip()
    return LANGUAGE_DISPLAY_NAMES.get(code, code or "English")


def apply_language(code: str, app: QtWidgets.QApplication | None = None) -> str:
    """Switch the active UI language *live*, removing any previous catalogue.

    Newly created widgets/dialogs render in ``code`` immediately; already-open
    windows only fully retranslate after a restart (Qt re-reads most static text
    at build time). Does not persist the choice — use
    :func:`chisurf.core.support.i18n.set_locale` for that. Returns the applied code
    (``en`` when the requested catalogue is missing). Emits
    :data:`language_notifier` ``language_changed`` so every open picker re-syncs.
    """
    app = app or QtWidgets.QApplication.instance()
    # Drop previously installed catalogues so switching back to English (or to a
    # different language) does not leave stale translations installed.
    if app is not None:
        for tr in _installed:
            app.removeTranslator(tr)
    _installed.clear()
    applied = install_translation(app, code)
    _live_notifier().language_changed.emit(applied)
    return applied


def install_translation(
    app: QtWidgets.QApplication | None = None,
    code: str | None = None,
) -> str:
    """Bind the core translation backend and install the UI-language catalogue.

    Parameters
    ----------
    app
        The application to install the translator on. Defaults to the running
        ``QApplication.instance()``.
    code
        Locale code to load. Defaults to the configured ``gui.language`` setting
        (:func:`chisurf.core.support.i18n.get_locale`).

    Returns
    -------
    str
        The locale code that was applied (``"en"`` if none/unavailable).
    """
    from chisurf.core.support import i18n

    app = app or QtWidgets.QApplication.instance()

    # Route all data-driven strings through Qt's translation lookup. Safe even
    # for English: with no catalogue installed, translate() returns the source.
    i18n.set_translation_backend(QtCore.QCoreApplication.translate)

    code = (code or i18n.get_locale() or i18n.DEFAULT_LOCALE).strip()
    if not code or code == i18n.DEFAULT_LOCALE:
        return i18n.DEFAULT_LOCALE

    qm = _qm_path(code)
    if not qm.is_file():
        logger.info("No translation catalogue for language %r (%s); using English.", code, qm)
        return i18n.DEFAULT_LOCALE

    translator = QtCore.QTranslator(app)
    if not translator.load(str(qm)):
        logger.warning("Failed to load translation catalogue %s; using English.", qm)
        return i18n.DEFAULT_LOCALE

    if app is not None:
        app.installTranslator(translator)
    _installed.append(translator)
    logger.info("Installed UI translation: %s", code)
    return code
