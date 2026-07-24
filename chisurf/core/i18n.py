"""App-wide translation seam (Qt-free).

ChiSurf's user-facing text lives in three places: the data-driven ``*.view.json``
(AutoForm) and ``manifest.json`` plugin specs parsed under :mod:`chisurf.core`,
the runtime-loaded ``.ui`` files, and imperative ``setText``/``QMessageBox`` call
sites in the GUI. This module is the single indirection every *data-driven*
string flows through so the whole modern UI can be translated from one place.

The core layer must stay import-clean of Qt (the headless/server path in
:mod:`chisurf.server` must not pull in a GUI toolkit), so :func:`tr` defaults to
the **identity** function. The GUI binds a real translator at startup via
:func:`set_translation_backend` — typically ``QCoreApplication.translate`` — after
which the same :func:`tr` calls return localized text. This mirrors the
settings-driven, swappable design of :mod:`chisurf.gui.tooltip`.

The active locale is read from the ChiSurf settings YAML under ``gui.language``
(a two-letter code such as ``"en"`` or ``"de"``); ``"en"`` is the canonical
source language and needs no catalogue.

Examples
--------
>>> from chisurf.core import i18n
>>> i18n.tr("Convolution")            # identity by default
'Convolution'
>>> i18n.set_translation_backend(lambda ctx, text: {"Convolution": "Faltung"}.get(text, text))
>>> i18n.tr("Convolution")
'Faltung'
>>> i18n.set_translation_backend(None)  # restore identity (e.g. for tests)
"""

from __future__ import annotations

import typing

#: Default UI language (the canonical source language; needs no catalogue).
DEFAULT_LOCALE = "en"

#: Qt translation context used for every data-driven ChiSurf string. Keeping a
#: single context keeps the extractor and the ``.ts`` catalogue flat and simple.
DEFAULT_CONTEXT = "chisurf"

#: Signature of a translation backend: ``(context, source_text) -> translated``.
TranslationBackend = typing.Callable[[str, str], str]

_backend: TranslationBackend | None = None


def set_translation_backend(backend: TranslationBackend | None) -> None:
    """Install (or clear) the process-wide translation backend.

    Parameters
    ----------
    backend
        A callable ``(context, source_text) -> translated_text``. Passing
        ``None`` restores the identity behaviour (useful in tests and on the
        headless/server path). The GUI passes ``QCoreApplication.translate``.
    """
    global _backend
    _backend = backend


def has_translation_backend() -> bool:
    """Return whether a non-identity translation backend is installed."""
    return _backend is not None


def tr(text: str | None, context: str = DEFAULT_CONTEXT) -> str | None:
    """Translate ``text`` through the active backend (identity if none).

    Empty/``None`` values pass straight through so call sites can wrap optional
    fields unconditionally. Any backend exception falls back to the source text
    — a missing translation must never break the UI.

    Parameters
    ----------
    text
        The canonical (English) source string, or ``None``/``""``.
    context
        Qt translation context; defaults to :data:`DEFAULT_CONTEXT`.

    Returns
    -------
    str or None
        The translated string, or the input unchanged.
    """
    if _backend is None or not text:
        return text
    try:
        return _backend(context, text)
    except Exception:
        return text


def get_locale() -> str:
    """Return the configured UI language code (``gui.language``, default ``en``).

    Reads the ChiSurf settings YAML lazily so importing this module stays cheap
    and Qt-free. Any failure falls back to :data:`DEFAULT_LOCALE`.
    """
    try:
        from chisurf.core.settings import cs_settings

        gui = cs_settings.get("gui", {}) if hasattr(cs_settings, "get") else {}
        code = str((gui or {}).get("language", DEFAULT_LOCALE) or DEFAULT_LOCALE).strip()
        return code or DEFAULT_LOCALE
    except Exception:
        return DEFAULT_LOCALE


def set_locale(code: str) -> None:
    """Persist the UI language code to the ChiSurf settings (``gui.language``).

    The change takes effect on the next GUI start (the translator is installed
    once at startup). Silently ignores persistence failures.
    """
    try:
        # Import from the submodule (not the settings package __init__) to avoid
        # touching a file other agent instances may be editing in this shared tree.
        from chisurf.core.settings.settings_utils import set_language

        set_language(str(code).strip() or DEFAULT_LOCALE)
    except Exception:
        pass
