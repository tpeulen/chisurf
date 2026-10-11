"""Bind ChiSurf's translation catalogues to :mod:`emtk.i18n` without importing Qt.

The catalogues (``chisurf/gui/i18n/chisurf_<code>.ts``) are registered with the
shared toolkit seam under the ``"chisurf"`` domain; the toolkit parses them
lazily. :func:`read_catalog` remains for catalogue audits.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from chisurf.core.support import i18n as core_i18n

SUPPORTED_LOCALES = ("en", "de", "fr", "es", "pt", "ru")
_installed = False


def catalog_directory() -> Path:
    """Return bundled catalogs without importing the legacy GUI package."""
    return core_i18n.catalogue_directory()


def read_catalog(
    path: str | Path, *, include_unfinished: bool = False
) -> dict[str, dict[str, str]]:
    """Read singular translations; optionally retain unfinished source entries for audits."""
    root = ET.parse(path).getroot()
    contexts: dict[str, dict[str, str]] = {}
    for context in root.findall("context"):
        name = context.findtext("name") or core_i18n.DEFAULT_CONTEXT
        messages = contexts.setdefault(name, {})
        for message in context.findall("message"):
            source = message.findtext("source")
            translation = message.find("translation")
            if not source or translation is None:
                continue
            status = translation.get("type")
            if status in {"obsolete", "vanished"} or (
                status == "unfinished" and not include_unfinished
            ):
                continue
            # Plurals require count-aware selection and must not become concatenated text.
            if message.get("numerus") == "yes" or translation.find("numerusform") is not None:
                continue
            text = "".join(translation.itertext())
            if text or include_unfinished:
                messages[source] = text
    return contexts


def install(locale: str | None = None, directory: str | Path | None = None) -> str:
    """Register ChiSurf's catalogues with :mod:`emtk.i18n` and select a language.

    The catalogues are registered once under the ``"chisurf"`` domain and parsed
    lazily by the toolkit (one language at a time, never twice); every
    data-driven ChiSurf label then translates through the same seam as the
    toolkit's own text. ``directory`` registers an additional catalogue
    directory for the same domain.
    """
    from emtk import i18n as toolkit_i18n

    global _installed

    from chisurf.emtk.shared_i18n import install_shared_translations

    install_shared_translations()
    core_i18n.register_catalogues()
    if directory is not None:
        toolkit_i18n.add_catalogue(core_i18n.DOMAIN, Path(directory))
    # A language already switched live (set_locale, not persisted) must survive a child tool's install().
    live = toolkit_i18n.get_locale() != "en"
    selected = locale or (
        toolkit_i18n.get_locale() if (_installed or live) else core_i18n.get_locale()
    )
    toolkit_i18n.set_locale(selected)
    _installed = True
    # No backend: the core seam delegates to emtk.i18n under the "chisurf" domain.
    core_i18n.set_translation_backend(None)
    return toolkit_i18n.get_locale()


def set_locale(locale: str) -> str:
    """Switch native UI translation immediately without writing settings."""
    from emtk import i18n as toolkit_i18n

    toolkit_i18n.set_locale(locale)
    return toolkit_i18n.get_locale()
