"""Translations, from one place, for every surface.

QuEst describes each parameter exactly once, in
`quest/settings/parameter_catalog.json` — label, unit, description. The docs,
the web UI and the Qt form are all generated from it. Translating *that* is
therefore the whole job: a German label reaches `doc/parameters.md`, the
browser and the desktop form without any of them knowing a translation
happened.

A locale file (`quest/settings/locales/<code>.json`) carries two things:

``parameters``
    Per catalog path, a translated ``label`` and ``description``. Anything
    absent falls back to the English catalog entry, key by key — a partial
    translation is useful and must never be an error.
``ui``
    The strings that are *not* parameters: panel titles, buttons, plot axes,
    dialog captions, the help text. Keyed by dotted names; `en.json` defines
    the key set and every other locale falls back to it.

English is not a locale file's job to define. The catalog *is* English, so
`en.json` carries only ``ui`` and the category names.

Choosing a locale
-----------------
:func:`resolve_locale` prefers an explicit argument, then ``QUEST_LOCALE``, then
the operating system's language, then English. An unknown code is not an error:
it resolves to English, because a user with `LANG=cs_CZ` wants QuEst to start,
not to explain itself.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from chisurf.plugins.quenching_estimator.settings import parameter_catalog

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALES_DIR",
    "SYSTEM_LOCALE_ENV_VARS",
    "system_locale",
    "available_locales",
    "locale_data",
    "normalize_locale",
    "resolve_locale",
    "translate_catalog",
    "ui_strings",
    "ui",
]

DEFAULT_LOCALE = "en"
LOCALES_DIR = Path(__file__).resolve().parents[1] / "settings" / "locales"

#: Environment variable that overrides everything but an explicit argument.
LOCALE_ENV_VAR = "QUEST_LOCALE"


def normalize_locale(value: str | None) -> str | None:
    """`de_DE.UTF-8` → `de`. Returns None for anything unusable."""
    if not value:
        return None
    code = str(value).strip().replace("-", "_").split(".")[0].split("_")[0].lower()
    return code or None


@lru_cache(maxsize=1)
def available_locales() -> dict[str, str]:
    """Locale code → its name *in that language*, e.g. `{"de": "Deutsch"}`.

    A language named in English in a language picker ("German") is the one
    thing a reader who needs it cannot read.
    """
    found: dict[str, str] = {}
    for path in sorted(LOCALES_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        code = normalize_locale(data.get("locale") or path.stem)
        if code:
            found[code] = data.get("name") or code
    return found


#: Where the operating system states its language, most specific first. Read
#: directly rather than through `locale.getdefaultlocale()`, which is deprecated
#: and slated for removal in Python 3.15 — and which only read these anyway.
#: `locale.getlocale()` is not a substitute: it reports the *current* locale,
#: which is `(None, None)` until something calls `setlocale`.
SYSTEM_LOCALE_ENV_VARS = ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")


def system_locale() -> str | None:
    """The language the operating system asks for, or None."""
    for name in SYSTEM_LOCALE_ENV_VARS:
        value = os.environ.get(name)
        if value and value not in ("C", "POSIX"):
            # LANGUAGE is a colon-separated preference list.
            return value.split(":")[0]
    return None


def resolve_locale(requested: str | None = None) -> str:
    """The locale to use: argument, then `QUEST_LOCALE`, then the OS, then English."""
    candidates = [requested, os.environ.get(LOCALE_ENV_VAR), system_locale()]

    known = available_locales()
    for candidate in candidates:
        code = normalize_locale(candidate)
        if code and code in known:
            return code
    return DEFAULT_LOCALE


@lru_cache(maxsize=8)
def locale_data(code: str) -> dict[str, Any]:
    """The raw contents of one locale file; `{}` when there is none."""
    path = LOCALES_DIR / f"{normalize_locale(code) or DEFAULT_LOCALE}.json"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf8") as handle:
        return json.load(handle)


@lru_cache(maxsize=8)
def ui_strings(code: str | None = None) -> dict[str, str]:
    """Every non-parameter string, with English filling any gap."""
    resolved = resolve_locale(code)
    strings = dict(locale_data(DEFAULT_LOCALE).get("ui", {}))
    if resolved != DEFAULT_LOCALE:
        strings.update(locale_data(resolved).get("ui", {}))
    return strings


def ui(key: str, code: str | None = None) -> str:
    """One UI string. An unknown key returns the key, which is visible but harmless."""
    return ui_strings(code).get(key, key)


@lru_cache(maxsize=8)
def translate_catalog(code: str | None = None) -> dict[str, Any]:
    """The parameter catalog with labels, descriptions and categories translated.

    The shape is identical to :func:`quest.settings.parameter_catalog`, so every
    consumer — the doc generator, the view-spec generator, the web API — keeps
    working with no knowledge of locales. Untranslated keys keep their English
    text rather than disappearing.
    """
    catalog = json.loads(json.dumps(parameter_catalog()))  # deep copy, plain types
    resolved = resolve_locale(code)
    catalog["locale"] = resolved
    if resolved == DEFAULT_LOCALE:
        return catalog

    data = locale_data(resolved)
    categories: Mapping[str, str] = data.get("categories", {})
    translations: Mapping[str, Mapping[str, str]] = data.get("parameters", {})

    for path, entry in catalog.get("parameters", {}).items():
        translated = translations.get(path, {})
        for field in ("label", "description"):
            if translated.get(field):
                entry[field] = translated[field]
        category = entry.get("category")
        if category in categories:
            # The English category is kept so callers that group by it — the
            # view-spec generator does — do not need translating themselves.
            entry["category_label"] = categories[category]

    for field in ("title", "description"):
        if data.get(f"catalog.{field}"):
            catalog[field] = data[f"catalog.{field}"]
    return catalog


def clear_cache() -> None:
    """Forget everything read from disk. For tests that write locale files."""
    for cached in (available_locales, locale_data, ui_strings, translate_catalog):
        cached.cache_clear()
