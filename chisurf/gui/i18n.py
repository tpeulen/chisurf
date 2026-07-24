"""GUI-side translation bootstrap.

Binds ChiSurf's Qt-free core translation seam (:mod:`chisurf.core.i18n`) to a
real Qt translator and installs a :class:`~qtpy.QtCore.QTranslator` for the
configured UI language onto the running :class:`~qtpy.QtWidgets.QApplication`.

Call :func:`install_translation` once, right after the ``QApplication`` is
created and **before** any window is built or any ``.ui`` file is loaded — Qt
only translates strings that are looked up *after* the translator is installed.
The single call:

1. sets the core backend to ``QCoreApplication.translate`` so every
   data-driven ``view.json`` / ``manifest.json`` string (routed through
   :func:`chisurf.core.i18n.tr`) is localized; and
2. loads ``chisurf/gui/i18n/chisurf_<code>.qm`` for the configured locale, which
   also covers all ``.ui`` strings for free.

The canonical source language is English (``en``); it needs no catalogue and the
translator install is skipped for it (Qt falls back to the source text).
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

logger = logging.getLogger(__name__)

#: Directory holding the compiled ``.qm`` catalogues (built from ``.ts`` sources).
I18N_DIR = pathlib.Path(__file__).parent / "i18n"

#: Keeps installed translators alive for the lifetime of the application.
_installed: list[QtCore.QTranslator] = []


def _qm_path(code: str) -> pathlib.Path:
    """Return the expected ``.qm`` catalogue path for a locale ``code``."""
    return I18N_DIR / f"chisurf_{code}.qm"


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
        (:func:`chisurf.core.i18n.get_locale`).

    Returns
    -------
    str
        The locale code that was applied (``"en"`` if none/unavailable).
    """
    from chisurf.core import i18n

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
