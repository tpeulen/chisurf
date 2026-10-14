#!/usr/bin/env python3
"""Extract ChiSurf's translatable UI strings into Qt ``.ts`` catalogues.

ChiSurf's user-facing text lives in three surfaces (see
``okf/references/ui-glossary.md`` and the ``chisurf.core.support.i18n`` module docstring):

* **data-driven** — ``*.view.json`` (AutoForm), ``*guide*.json`` and ``manifest.json``
  plugin specs, walked as data.
* **imperative** — ``chisurf.core.support.i18n.tr(...)`` calls in ``.py`` (window titles,
  custom-section labels), found by walking the AST (:func:`_collect_from_python`).

Every string lands in the one flat ``chisurf`` context. :func:`merge_catalogue` then merges
them into ``chisurf/gui/i18n/chisurf_<code>.ts`` for each target locale, in pure Python (the
Qt ``pylupdate5`` merge went with the Qt shell): a string already in the catalogue keeps its
translation, a new one is added ``unfinished``, a string no longer collected -- and every
message of a retired Qt form's context -- is marked ``obsolete``, which keeps its translation
on record without installing it. The emtk shell reads the ``.ts`` files directly
(:mod:`chisurf.emtk.i18n`); nothing is compiled.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

REPO = pathlib.Path(__file__).resolve().parents[2]
CHISURF = REPO / "chisurf"
I18N_DIR = CHISURF / "gui" / "i18n"

#: Target locales to (re)generate. English is the source language; its ``.ts`` is
#: a translator template (empty translations) and is not installed at runtime.
DEFAULT_LOCALES = ("en", "de", "es", "fr", "pt", "ru")

#: Translation context shared by every collected string. Must match
#: :data:`chisurf.core.support.i18n.DEFAULT_CONTEXT`.
CONTEXT = "chisurf"

#: Keys carrying user-facing text in view.json / manifest.json, collected
#: wherever they appear in the nested spec. Mirrors the runtime translation seams
#: in ``chisurf/core/dataspec`` and ``chisurf/core/plugin/manifest.py``.
#: ``display_name`` and ``categories`` are deliberately excluded — they double as
#: menu-path / identity keys and stay canonical; a ``display_name``'s *segments* are
#: collected by :func:`_collect_menu_path`, since each is drawn through ``tr()``.
TEXT_KEYS = frozenset(
    {
        # AutoForm section fields
        "title",
        "description",
        "label",
        "suffix",
        "placeholder",
        "add_label",
        "remove_label",
        "component_title",
        "subtitle",
        "text",
        "x_label",
        "y_label",
        "hint",
        "tooltip",
        "units",
        "caption",
        "special_text",
        "descriptions",
        "labels",
        "options",
        "choices",
        "menu",
        # manifest / rpc fields
        "summary",
        "experimental_message",
        "deprecation_message",
    }
)

#: A few literal strings the runtime synthesizes (not present in any spec).
EXTRA_LITERALS = ("(required)",)


def _collect_from_json(node: object, out: set[str]) -> None:
    """Collect authored text without translating binding identities or hidden choice values."""

    def text(value):
        if isinstance(value, str) and value.strip():
            out.add(value)
        elif isinstance(value, list):
            for item in value:
                text(item)
        elif isinstance(value, dict):
            for item in value.values():
                text(item)

    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"options", "choices"}:
                if (
                    node.get("type") == "choice"
                    and not node.get("labels")
                    and isinstance(value, list)
                ):
                    for option in value:
                        # The renderer displays a (value, label) pair's second slot.
                        text(
                            option[1]
                            if isinstance(option, (list, tuple)) and len(option) == 2
                            else option
                        )
            elif key in TEXT_KEYS:
                text(value)
            _collect_from_json(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_from_json(item, out)


def _collect_labels(node: object, out: set[str]) -> None:
    """Collect the string members of every ``labels`` list in the spec."""
    if isinstance(node, dict):
        labels = node.get("labels")
        if isinstance(labels, list):
            for lab in labels:
                if isinstance(lab, str) and lab.strip():
                    out.add(lab)
        for value in node.values():
            _collect_labels(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_labels(item, out)


def _collect_from_python(strings: set[str]) -> None:
    """Collect literal strings passed to the imperative ``i18n.tr(...)`` seam.

    Imperative GUI code (message boxes, window titles, custom-section labels)
    localizes text through :func:`chisurf.core.support.i18n.tr`, in the same flat
    ``chisurf`` context as the data-driven strings; the AST walk collects the
    literals.

    Matched call shapes (first argument a string literal):

    * ``i18n.tr("…")`` — the canonical form (receiver named ``i18n``);
    * a bare ``tr("…")`` where ``tr`` is the imported function;

    ``self.tr(...)`` is deliberately **not** matched: Qt resolves it under the
    enclosing class's context, not ``chisurf``, so it would not round-trip
    through this flat catalogue.
    """
    for path in sorted(CHISURF.rglob("*.py")):
        if _not_shipped(path):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            raise ValueError(f"Invalid translation source {path}: {error}") from error
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            # ``mark("…")`` is emtk's marker for a table of labels translated where it is drawn.
            is_tr = (
                isinstance(func, ast.Attribute)
                and func.attr in ("tr", "mark")
                and isinstance(func.value, ast.Name)
                and func.value.id == "i18n"
            ) or (isinstance(func, ast.Name) and func.id in ("tr", "Msg", "mark"))
            if not is_tr:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if first.value.strip():
                    strings.add(first.value)


def _not_shipped(path: pathlib.Path) -> bool:
    """Exclude tests and the plugin scaffold from the shipped UI text contract."""
    return any(
        part in {"test", "tests", "__pycache__"} or "cookiecutter" in part for part in path.parts
    ) or path.name.startswith("test_")


def _collect_menu_path(path: pathlib.Path, data: object, out: set[str]) -> None:
    """Collect the captions of a plugin manifest's menu path (``display_name``).

    The path stays canonical in the manifest -- it is the plugin's address -- but each segment is
    drawn translated: the ribbon's tab, group and button, the menus and the Tools dock call
    ``tr(segment)``. Without the segments in the catalogue those captions never translate.
    """
    if path.name != "manifest.json" or not isinstance(data, dict):
        return
    name = data.get("display_name")
    if isinstance(name, str):
        out.update(part.strip() for part in name.split(":") if part.strip())


def _collect_startup_labels(out: set[str]) -> None:
    """Collect the stage labels the emtk shell's splash draws through ``tr()``.

    The stages are declared in ``chisurf/startup/services.d/*.json``; only the ``emtk``
    surface's labels are drawn translated (the Qt splash shows its labels as declared).
    """
    for path in sorted((CHISURF / "startup" / "services.d").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for service in data.get("services", []):
            label = service.get("label")
            if service.get("surface") == "emtk" and isinstance(label, str) and label.strip():
                out.add(label)


def collect_strings() -> set[str]:
    """Walk view.json + manifest.json + ``i18n.tr`` calls; return unique strings."""
    strings: set[str] = set(EXTRA_LITERALS)
    specs = sorted(
        set(CHISURF.rglob("*view.json"))
        | set(CHISURF.rglob("manifest.json"))
        | set(CHISURF.rglob("*guide*.json"))
    )
    for path in specs:
        if _not_shipped(path):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"Invalid translation declaration {path}: {error}") from error
        _collect_from_json(data, strings)
        _collect_labels(data, strings)
        _collect_menu_path(path, data, strings)
    _collect_startup_labels(strings)
    _collect_from_python(strings)
    # Drop empties / pure-format placeholders.
    return {s for s in strings if s and s.strip()}


def _write_ts(tree: ET.ElementTree, path: pathlib.Path) -> None:
    """Write a ``.ts`` tree with the catalogues' layout (indent, kept trailing blanks)."""
    ET.indent(tree, space="    ")
    content = ET.tostring(tree.getroot(), encoding="unicode")
    content = re.sub(r" +(?=\n)", lambda match: "&#32;" * len(match[0]), content)
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n' + content + "\n", encoding="utf-8"
    )


def merge_catalogue(path: pathlib.Path, strings: set[str], language: str) -> dict[str, int]:
    """Merge the collected *strings* into the ``.ts`` catalogue at *path* (created if absent).

    Parameters
    ----------
    path : pathlib.Path
        ``chisurf_<code>.ts``.
    strings : set of str
        Every source string collected for the ``chisurf`` context.
    language : str
        The catalogue's ``language`` attribute for a new file.

    Returns
    -------
    dict
        Counts: ``added`` (new, unfinished), ``revived`` (obsolete again in use),
        ``obsoleted`` (no longer collected, or a retired context), ``kept``.
    """
    counts = {"added": 0, "revived": 0, "obsoleted": 0, "kept": 0}
    if path.is_file():
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.Element("TS", {"version": "2.1", "language": language})
        tree = ET.ElementTree(root)
    context = next(
        (c for c in root.findall("context") if c.findtext("name") == CONTEXT), None
    )
    if context is None:
        context = ET.SubElement(root, "context")
        ET.SubElement(context, "name").text = CONTEXT
    seen: set[str] = set()
    for ctx in root.findall("context"):
        own = ctx is context
        for message in ctx.findall("message"):
            source = message.findtext("source") or ""
            translation = message.find("translation")
            if translation is None:
                translation = ET.SubElement(message, "translation", {"type": "unfinished"})
            kind = translation.get("type")
            if own and source in strings:
                seen.add(source)
                if kind in {"obsolete", "vanished"}:
                    # Back in use: a translation on record is reinstated, an empty one
                    # waits for a translator.
                    if "".join(translation.itertext()):
                        translation.attrib.pop("type", None)
                    else:
                        translation.set("type", "unfinished")
                    counts["revived"] += 1
                else:
                    counts["kept"] += 1
            elif kind not in {"obsolete", "vanished"}:
                translation.set("type", "obsolete")
                counts["obsoleted"] += 1
    for source in sorted(strings - seen):
        message = ET.SubElement(context, "message")
        ET.SubElement(message, "source").text = source
        ET.SubElement(message, "translation", {"type": "unfinished"})
        counts["added"] += 1
    _write_ts(tree, path)
    return counts


def preserve_finished_translations(before: str, path: pathlib.Path) -> None:
    """Retain unambiguous human translations when a retired form's context moves."""
    finished: dict[str, set[str]] = {}
    for message in ET.fromstring(before).findall(".//message"):
        translation = message.find("translation")
        source = message.findtext("source")
        if (
            not source
            or translation is None
            or translation.get("type") in {"unfinished", "obsolete", "vanished"}
            or message.get("numerus") == "yes"
            or translation.find("numerusform") is not None
        ):
            continue
        text = "".join(translation.itertext())
        if text:
            finished.setdefault(source, set()).add(text)
    tree = ET.parse(path)
    for message in tree.getroot().findall(".//message"):
        translation = message.find("translation")
        source = message.findtext("source")
        if not source:
            continue
        choices = finished.get(source, set())
        if (
            translation is None
            or translation.get("type") != "unfinished"
            or len(choices) != 1
            or message.get("numerus") == "yes"
            or translation.find("numerusform") is not None
        ):
            continue
        text = "".join(translation.itertext())
        old = next(iter(choices))
        if text and text != old:
            continue
        translation.text = old
        translation.attrib.pop("type", None)
    _write_ts(tree, path)


def main() -> int:
    """Collect strings and merge them into the ``.ts`` catalogues."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locales",
        nargs="+",
        default=list(DEFAULT_LOCALES),
        help="Locale codes to (re)generate .ts for (default: %(default)s).",
    )
    args = parser.parse_args()

    I18N_DIR.mkdir(parents=True, exist_ok=True)
    print("Collecting strings from view.json + manifest.json + i18n.tr() calls …")
    strings = collect_strings()
    print(f"  {len(strings)} unique source strings")
    for code in args.locales:
        ts = I18N_DIR / f"chisurf_{code}.ts"
        counts = merge_catalogue(ts, strings, code)
        print(f"  → {ts.relative_to(REPO)} {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
