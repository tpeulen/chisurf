#!/usr/bin/env python3
"""Extract ChiSurf's translatable UI strings into Qt ``.ts`` catalogues.

ChiSurf's user-facing text lives in three surfaces (see
``okf/references/ui-glossary.md`` and the ``chisurf.core.support.i18n`` module docstring):

* **data-driven** — ``*.view.json`` (AutoForm) and ``manifest.json`` plugin specs.
  These are *data*, not source literals, so Qt's ``pylupdate5`` cannot see them.
  This script walks them and emits a generated Python stub
  (``_i18n_autogen.py``) full of ``QCoreApplication.translate("chisurf", "...")``
  calls — one per unique string — which ``pylupdate5`` *can* extract.
* **declarative** — the hand-built ``.ui`` files. ``pylupdate5`` extracts these
  natively (context = the form's class name), so they are translated for free at
  runtime once a ``QTranslator`` is installed.
* **imperative** — ``chisurf.core.support.i18n.tr(...)`` calls in ``.py`` (message boxes,
  window titles, custom-section labels). ``pylupdate5`` cannot see the aliased
  ``i18n.tr`` token, so :func:`_collect_from_python` walks the AST and feeds those
  literals into the same ``_i18n_autogen.py`` stub under the ``chisurf`` context.

The script then runs ``pylupdate5`` over a generated ``.pro`` project listing the
generated stub, every ``.ui`` form, and the ``.py`` sources, merging into
``chisurf/gui/i18n/chisurf_<code>.ts`` for each target locale. Existing human
translations are preserved by ``pylupdate5``'s merge; new strings appear
``unfinished`` and dropped strings are marked ``obsolete``.

Compile the resulting ``.ts`` to ``.qm`` with ``pixi run i18n-compile``
(``lrelease``). Run this extractor with ``pixi run i18n-extract``.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
CHISURF = REPO / "chisurf"
I18N_DIR = CHISURF / "gui" / "i18n"
AUTOGEN = pathlib.Path(__file__).resolve().parent / "_i18n_autogen.py"

#: Target locales to (re)generate. English is the source language; its ``.ts`` is
#: a translator template (empty translations) and is not installed at runtime.
DEFAULT_LOCALES = ("en", "de", "es", "fr", "pt", "ru")

#: Qt translation context shared by every data-driven string. Must match
#: :data:`chisurf.core.support.i18n.DEFAULT_CONTEXT`.
CONTEXT = "chisurf"

#: Keys carrying user-facing text in view.json / manifest.json, collected
#: wherever they appear in the nested spec. Mirrors the runtime translation seams
#: in ``chisurf/core/dataspec`` and ``chisurf/core/plugin/manifest.py``.
#: ``display_name`` and ``categories`` are deliberately excluded — they double as
#: menu-path / identity keys and stay canonical (localized at the nav seam).
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
    """Recursively collect translatable string values from a parsed JSON spec."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TEXT_KEYS and isinstance(value, str) and value.strip():
                out.add(value)
            _collect_from_json(value, out)
    elif isinstance(node, list):
        # ``labels`` is a bare list of display strings; other lists hold dicts
        # that the dict branch above handles on recursion.
        for item in node:
            if isinstance(item, str):
                # Only reached for a ``labels`` list; parent key was already
                # consumed, so we cannot know the key here. Collect conservatively
                # only when the string looks like a label (short, has letters).
                continue
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
    localizes text through :func:`chisurf.core.support.i18n.tr`, which routes to
    ``QCoreApplication.translate("chisurf", text)`` — the same flat ``chisurf``
    context as the data-driven strings. ``pylupdate5`` only recognizes a literal
    ``.tr(``/``translate(`` token, so an aliased ``i18n.tr`` call is invisible to
    it; we walk the AST instead and feed the literals into the same autogen stub.

    Matched call shapes (first argument a string literal):

    * ``i18n.tr("…")`` — the canonical form (receiver named ``i18n``);
    * a bare ``tr("…")`` where ``tr`` is the imported function;
    * ``Msg("…")`` — a declared widget message
      (:class:`chisurf.gui.widgets.messages.Msg`). Declarations are evaluated at
      import, long before a translator exists, so the text is translated when the
      message is rendered; the literal still has to reach the catalogue, and this
      is the only place it appears.

    ``self.tr(...)`` is deliberately **not** matched: Qt resolves it under the
    enclosing class's context, not ``chisurf``, so it would not round-trip
    through this flat catalogue.
    """
    for path in sorted(CHISURF.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:  # noqa: BLE001 - skip unparseable/partial files
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            is_tr = (
                isinstance(func, ast.Attribute)
                and func.attr == "tr"
                and isinstance(func.value, ast.Name)
                and func.value.id == "i18n"
            ) or (isinstance(func, ast.Name) and func.id in ("tr", "Msg"))
            if not is_tr:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if first.value.strip():
                    strings.add(first.value)


def collect_strings() -> set[str]:
    """Walk view.json + manifest.json + ``i18n.tr`` calls; return unique strings."""
    strings: set[str] = set(EXTRA_LITERALS)
    specs = sorted(CHISURF.rglob("*.view.json")) + sorted(CHISURF.rglob("manifest.json"))
    for path in specs:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skip {path.relative_to(REPO)}: {exc}", file=sys.stderr)
            continue
        _collect_from_json(data, strings)
        _collect_labels(data, strings)
    _collect_from_python(strings)
    # Drop empties / pure-format placeholders.
    return {s for s in strings if s and s.strip()}


def write_autogen(strings: set[str]) -> None:
    """Write the pylupdate5-scannable stub of translate() calls."""
    # pylupdate5 is a token scanner: it only recognizes a literal ``translate(``
    # (or ``.tr(``) call token — an aliased reference is invisible. Emit direct
    # ``QtCore.QCoreApplication.translate("chisurf", "…")`` calls.
    lines = [
        "# AUTOGENERATED by build_tools/i18n/extract_strings.py — do not edit.",
        "# Exposes ChiSurf's data-driven UI strings to pylupdate5 so they land in",
        "# the .ts catalogue under the 'chisurf' context. Never imported at runtime.",
        "from qtpy import QtCore",
        "",
        "",
        "def _mark():",
    ]
    for s in sorted(strings):
        literal = json.dumps(s, ensure_ascii=False)  # safe Python/JSON string escaping
        lines.append(f"    QtCore.QCoreApplication.translate({CONTEXT!r}, {literal})")
    lines.append("")
    AUTOGEN.write_text("\n".join(lines), encoding="utf-8")


def write_pro(
    ui_files: list[pathlib.Path], py_sources: list[pathlib.Path], locales
) -> pathlib.Path:
    """Write a pylupdate5 project file listing forms, sources and translations.

    pylupdate5 resolves the paths in a ``.pro`` relative to the ``.pro`` file's
    own directory, so the project is written at the repo root and every path is
    repo-relative.
    """
    pro = REPO / "chisurf_i18n.pro"

    def _rel(p: pathlib.Path) -> str:
        return p.resolve().relative_to(REPO).as_posix()

    forms = " \\\n    ".join(_rel(p) for p in ui_files)
    sources = " \\\n    ".join(_rel(p) for p in py_sources)
    translations = " \\\n    ".join(
        (I18N_DIR / f"chisurf_{code}.ts").relative_to(REPO).as_posix() for code in locales
    )
    pro.write_text(
        f"FORMS = {forms}\n\nSOURCES = {sources}\n\nTRANSLATIONS = {translations}\n",
        encoding="utf-8",
    )
    return pro


def main() -> int:
    """Collect strings, run pylupdate5, and (re)generate the ``.ts`` catalogues."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locales",
        nargs="+",
        default=list(DEFAULT_LOCALES),
        help="Locale codes to (re)generate .ts for (default: %(default)s).",
    )
    parser.add_argument(
        "--keep-autogen",
        action="store_true",
        help="Keep the generated stub/.pro files (for debugging).",
    )
    args = parser.parse_args()

    I18N_DIR.mkdir(parents=True, exist_ok=True)

    print("Collecting strings from view.json + manifest.json + i18n.tr() calls …")
    strings = collect_strings()
    print(f"  {len(strings)} unique source strings")
    write_autogen(strings)

    ui_files = sorted(CHISURF.rglob("*.ui"))
    # Sources scanned for native tr()/translate() calls. Today only the generated
    # stub carries strings (data-driven UI); imperative ``.py`` wrapping is a
    # phased follow-up, at which point ``CHISURF.rglob('*.py')`` is added here.
    py_sources = [AUTOGEN]
    print(f"  {len(ui_files)} .ui forms, {len(py_sources)} .py source(s)")

    pro = write_pro(ui_files, py_sources, args.locales)

    pylupdate = _find_tool("pylupdate5")
    if pylupdate is None:
        print("ERROR: pylupdate5 not found on PATH (Qt dev tools).", file=sys.stderr)
        return 2

    print(f"Running {pylupdate} {pro.name} …")
    proc = subprocess.run([pylupdate, str(pro)], cwd=str(REPO))
    rc = proc.returncode

    if not args.keep_autogen:
        AUTOGEN.unlink(missing_ok=True)
        pro.unlink(missing_ok=True)

    if rc == 0:
        for code in args.locales:
            ts = I18N_DIR / f"chisurf_{code}.ts"
            print(f"  → {ts.relative_to(REPO)}")
        print("Done. Compile with: pixi run i18n-compile")
    return rc


def _find_tool(name: str) -> str | None:
    import shutil

    return shutil.which(name)


if __name__ == "__main__":
    raise SystemExit(main())
