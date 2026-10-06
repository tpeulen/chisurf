"""Load ChiSurf translation catalogs for native EMTK without importing Qt."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from chisurf.core.support import i18n as core_i18n

SUPPORTED_LOCALES = ("en", "de", "fr", "es", "pt", "ru")
_installed = False


def catalog_directory() -> Path:
    """Return bundled catalogs without importing the legacy GUI package."""
    return Path(__file__).resolve().parents[1] / "gui" / "i18n"


def read_catalog(path: str | Path) -> dict[str, dict[str, str]]:
    """Read finished, singular translations grouped by their original context."""
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
            if translation.get("type") in {"unfinished", "obsolete", "vanished"}:
                continue
            # Plurals require count-aware selection and must not become concatenated text.
            if message.get("numerus") == "yes" or translation.find("numerusform") is not None:
                continue
            text = "".join(translation.itertext())
            if text:
                messages[source] = text
    return contexts


def install(locale: str | None = None, directory: str | Path | None = None) -> str:
    """Install catalogs and bind data-driven ChiSurf labels to EMTK translation."""
    from emtk import i18n as toolkit_i18n

    global _installed

    from chisurf.emtk.shared_i18n import install_shared_translations

    install_shared_translations()
    directory = Path(directory) if directory is not None else catalog_directory()
    for language in SUPPORTED_LOCALES:
        path = directory / f"chisurf_{language}.ts"
        if not path.is_file():
            continue
        contexts = read_catalog(path)
        default: dict[str, str] = {}
        for context, mapping in contexts.items():
            toolkit_i18n.add_translations(language, mapping, context=context)
            # Use the catalog's generic ChiSurf context when a source is ambiguous.
            for source, translation in mapping.items():
                default.setdefault(source, translation)
        default.update(contexts.get(core_i18n.DEFAULT_CONTEXT, {}))
        toolkit_i18n.add_translations(language, default, context="default")
    selected = locale or (toolkit_i18n.get_locale() if _installed else core_i18n.get_locale())
    toolkit_i18n.set_locale(selected)
    _installed = True
    core_i18n.set_translation_backend(lambda context, text: toolkit_i18n.tr(text, context=context))
    return toolkit_i18n.get_locale()


def set_locale(locale: str) -> str:
    """Switch native UI translation immediately without writing settings."""
    from emtk import i18n as toolkit_i18n

    toolkit_i18n.set_locale(locale)
    return toolkit_i18n.get_locale()
