"""Load ChiSurf translation catalogs for native EMTK without importing Qt."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from chisurf.core.support import i18n as core_i18n

SUPPORTED_LOCALES = ("en", "de", "fr", "es", "pt", "ru")
_installed = False
# Parsed catalogs keyed by (path, mtime_ns, size). install() runs once per tool, and a
# hub installs again for every sub-app it embeds; re-parsing six ~3 MB XML files each
# time was ~200 ms on the first frame of every hub.
_parsed: dict[tuple[str, int, int], tuple[dict[str, dict[str, str]], dict[str, str]]] = {}


def catalog_directory() -> Path:
    """Return bundled catalogs without importing the legacy GUI package."""
    return Path(__file__).resolve().parents[1] / "gui" / "i18n"


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


def _parsed_catalog(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Return a catalog's contexts and its ``default`` fallback mapping, parsed once per file version."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _parsed.get(key)
    if cached is None:
        contexts = read_catalog(path)
        default: dict[str, str] = {}
        for mapping in contexts.values():
            # Use the catalog's generic ChiSurf context when a source is ambiguous.
            for source, translation in mapping.items():
                default.setdefault(source, translation)
        default.update(contexts.get(core_i18n.DEFAULT_CONTEXT, {}))
        cached = _parsed[key] = (contexts, default)
    return cached


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
        contexts, default = _parsed_catalog(path)
        for context, mapping in contexts.items():
            toolkit_i18n.add_translations(language, mapping, context=context)
        toolkit_i18n.add_translations(language, default, context="default")
    # A language already switched live (set_locale, not persisted) must survive a child tool's install().
    live = toolkit_i18n.get_locale() != "en"
    selected = locale or (
        toolkit_i18n.get_locale() if (_installed or live) else core_i18n.get_locale()
    )
    toolkit_i18n.set_locale(selected)
    _installed = True
    core_i18n.set_translation_backend(lambda context, text: toolkit_i18n.tr(text, context=context))
    return toolkit_i18n.get_locale()


def set_locale(locale: str) -> str:
    """Switch native UI translation immediately without writing settings."""
    from emtk import i18n as toolkit_i18n

    toolkit_i18n.set_locale(locale)
    return toolkit_i18n.get_locale()
