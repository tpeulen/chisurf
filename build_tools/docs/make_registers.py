#!/usr/bin/env python
"""Build the figure, table and code registers of the documentation.

Three indexes, generated from the pages themselves plus one hand-kept file of
provenance:

``docs/reference/figures.md`` (*Abbildungsverzeichnis*)
    every image, its caption, the page it appears on, and **where it came
    from** — the script and function that drew it, or the recipe that produced
    the screenshot. Without the origin an image can only ever be replaced by
    hand, and in practice is never refreshed at all.
``docs/reference/tables.md`` (*Tabellenverzeichnis*)
    every table, with the page and section it belongs to, and whether it is
    generated or written.
``docs/reference/code.md``
    every code block, with its language and whether it is **verified** —
    compiled at minimum, executed where the block says it can be.

Provenance for figures is kept in ``docs/references/figures.yaml``, keyed by the
image path. Anything used but not recorded there is listed in the register as
*unrecorded*, which is the worklist.

Usage::

    python build_tools/docs/make_registers.py [--check]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DOCS = REPO_ROOT / "docs"
PROVENANCE = DOCS / "references" / "figures.yaml"

#: Directories whose pages are user documentation.
SECTIONS = (
    "getting_started",
    "fundamentals",
    "concepts",
    "guides",
    "manual",
    "reference",
    "references",
)

_MYST_FIGURE = re.compile(
    r"^```\{figure\}\s*(?P<src>\S+)\s*\n(?P<options>(?::\w[\w-]*:.*\n)*)\s*\n?"
    r"(?P<caption>(?:(?!```).*\n)*?)```",
    re.M,
)
_MD_IMAGE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)")
_RST_IMAGE = re.compile(r"^\s*\.\.\s+(?:image|figure)::\s*(?P<src>\S+)", re.M)
_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*(?:\{#[-\w]+\})?$")
_RST_TITLE = re.compile(r"^([!-/:-@\[-`{-~])\1{1,}\s*$")
_MD_TABLE = re.compile(r"^\|(?P<header>[^\n]*)\|[ \t]*\n\|[\s:|-]+\|[ \t]*$", re.M)
_RST_TABLE = re.compile(r"^\s*\.\.\s+(?:list-table|csv-table|table)::\s*(?P<title>.*)$", re.M)
_FENCE = re.compile(r"^```(?P<lang>[\w-]*)(?P<info>[^\n]*)\n(?P<body>.*?)^```", re.M | re.S)
_RST_CODE = re.compile(r"^\s*\.\.\s+code-block::\s*(?P<lang>\S+)", re.M)


def pages() -> list[pathlib.Path]:
    """Every user-facing documentation page, in section order."""
    found: list[pathlib.Path] = []
    for section in SECTIONS:
        directory = DOCS / section
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() in (".md", ".rst") and "_build" not in path.parts:
                found.append(path)
    return found


def load_provenance() -> dict:
    """Read the hand-kept origin of each image."""
    if not PROVENANCE.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(PROVENANCE.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover
        print(f"  (could not read {PROVENANCE.name}: {exc})")
        return {}


def _relative(page: pathlib.Path) -> str:
    return page.relative_to(REPO_ROOT).as_posix()


def _resolve_image(page: pathlib.Path, src: str) -> str:
    """Return the image path as it is keyed in the provenance file."""
    src = src.strip()
    if src.startswith("/"):
        return src.lstrip("/")
    try:
        return (page.parent / src).resolve().relative_to(DOCS).as_posix()
    except Exception:
        return src


def collect_figures() -> list[dict]:
    """Every figure used by a documentation page."""
    figures: list[dict] = []
    for page in pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        for match in _MYST_FIGURE.finditer(text):
            caption = " ".join(match.group("caption").split())
            options = dict(
                re.findall(r":(\w[\w-]*):\s*(.*)", match.group("options") or "")
            )
            figures.append(
                {
                    "page": _relative(page),
                    "src": _resolve_image(page, match.group("src")),
                    "caption": caption,
                    "name": options.get("name", ""),
                }
            )
        for match in _MD_IMAGE.finditer(text):
            figures.append(
                {
                    "page": _relative(page),
                    "src": _resolve_image(page, match.group("src")),
                    "caption": match.group("alt"),
                    "name": "",
                }
            )
        for match in _RST_IMAGE.finditer(text):
            figures.append(
                {
                    "page": _relative(page),
                    "src": _resolve_image(page, match.group("src")),
                    "caption": "",
                    "name": "",
                }
            )
    return figures


def collect_tables() -> list[dict]:
    """Every table, with the section heading it sits under."""
    tables: list[dict] = []
    for page in pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        heading = ""
        for number, line in enumerate(lines):
            match = _HEADING.match(line)
            if match:
                heading = match.group("title")
            elif (
                number + 1 < len(lines)
                and _RST_TITLE.match(lines[number + 1] or "")
                and line.strip()
            ):
                heading = line.strip()
            if re.match(r"^\|", line) and number + 1 < len(lines) and re.match(
                r"^\|[\s:|-]+\|", lines[number + 1]
            ):
                columns = [c.strip() for c in line.strip().strip("|").split("|")]
                tables.append(
                    {
                        "page": _relative(page),
                        "section": heading,
                        "columns": ", ".join(c for c in columns if c),
                        "line": number + 1,
                    }
                )
            directive = _RST_TABLE.match(line)
            if directive:
                tables.append(
                    {
                        "page": _relative(page),
                        "section": heading,
                        "columns": directive.group("title").strip(),
                        "line": number + 1,
                    }
                )
    return tables


def collect_code() -> list[dict]:
    """Every code block, with the verification it is subject to."""
    blocks: list[dict] = []
    for page in pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        heading = ""
        for match in _FENCE.finditer(text):
            language = (match.group("lang") or "text").lower()
            if language.startswith("{"):
                continue
            before = text[: match.start()]
            headings = _HEADING.findall(before)
            heading = headings[-1][1] if headings else ""
            info = (match.group("info") or "").strip()
            blocks.append(
                {
                    "page": _relative(page),
                    "section": heading,
                    "language": language,
                    "lines": match.group("body").count("\n"),
                    "runnable": "run" in info.split(),
                    "line": before.count("\n") + 1,
                }
            )
        for match in _RST_CODE.finditer(text):
            blocks.append(
                {
                    "page": _relative(page),
                    "section": "",
                    "language": match.group("lang").lower(),
                    "lines": 0,
                    "runnable": False,
                    "line": text[: match.start()].count("\n") + 1,
                }
            )
    return blocks


def _figure_rows(figures, provenance) -> tuple[list[str], int]:
    rows, unrecorded = [], 0
    for index, figure in enumerate(sorted(figures, key=lambda f: (f["page"], f["src"])), 1):
        record = provenance.get(figure["src"], {}) or {}
        origin = record.get("origin", "")
        caption = figure["caption"] or record.get("caption", "")
        exists = (DOCS / figure["src"]).exists()
        if not origin:
            unrecorded += 1
            origin = "**unrecorded**"
        rows.append(
            f"| {index} | `{figure['src']}`{'' if exists else ' ⚠️ missing'} | "
            f"{_cell(caption)} | {_cell(origin)} | [{figure['page']}]({_link(figure['page'])}) |"
        )
    return rows, unrecorded


def _cell(text: str) -> str:
    """Return *text* as one table cell, shortened without breaking its markup.

    Cutting at a fixed character count can land in the middle of a formula and
    leave an unpaired ``$``, which the renderer then closes against the *next*
    dollar on the page — several rows further down, swallowing everything
    between them into one nonsensical formula. Shortening therefore backs up to
    the last point where the delimiters are balanced.
    """
    text = " ".join(str(text or "").split())
    # A register is an index, not a place for live links: a role that is cut in
    # half by the shortening below reaches the reader as its own source text,
    # and one that survives whole points somewhere the row cannot show anyway.
    text = re.sub(r"\{(?:src|cite|doc|ref|numref)\}`([^`]*)`", r"`\1`", text)
    text = text.replace("|", "\\|")
    if len(text) <= 160:
        return text or "—"
    cut = 160
    while cut > 40 and (text.count("$", 0, cut) % 2 or text.count("`", 0, cut) % 2):
        cut -= 1
    return text[:cut].rstrip() + "…"


def _link(page: str) -> str:
    return "/" + page[len("docs/"):] if page.startswith("docs/") else page


def render_figures(figures, provenance) -> str:
    rows, unrecorded = _figure_rows(figures, provenance)
    return "\n".join(
        [
            "(figure-index)=",
            "# Figure index",
            "",
            "Every image the documentation shows, with its caption, **where it came",
            "from**, and the page it appears on. The origin is what makes a figure",
            "refreshable: a plot names the script and function that drew it, a",
            "screenshot names the recipe that produced it. Provenance is kept in",
            "[`figures.yaml`](../references/figures.yaml); an image used without an",
            "entry there is marked **unrecorded** below, and that is the worklist.",
            "",
            f"*{len(rows)} figures, {unrecorded} unrecorded.*",
            "",
            "| # | Image | Caption | Origin | Page |",
            "| --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def render_tables(tables) -> str:
    rows = [
        f"| {index} | {_cell(table['section'])} | {_cell(table['columns'])} | "
        f"[{table['page']}]({_link(table['page'])}) |"
        for index, table in enumerate(tables, 1)
    ]
    return "\n".join(
        [
            "(table-index)=",
            "# Table index",
            "",
            "Every table in the documentation, with the section it belongs to and its",
            "columns. Tables carrying *generated* content — the plugin catalogue, the",
            "parameter glossary, the Literature page — are rebuilt by their",
            "generators; the rest are written by hand and are checked when the page",
            "they sit on is reviewed.",
            "",
            f"*{len(rows)} tables.*",
            "",
            "| # | Section | Columns | Page |",
            "| --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def render_code(blocks) -> str:
    runnable = sum(1 for block in blocks if block["runnable"])
    python = sum(1 for block in blocks if block["language"] in ("python", "py"))
    rows = [
        f"| {index} | `{block['language']}` | {_cell(block['section'])} | "
        f"{block['lines']} | {'run' if block['runnable'] else ('compiled' if block['language'] in ('python', 'py') else '—')} | "
        f"[{block['page']}]({_link(block['page'])}) |"
        for index, block in enumerate(blocks, 1)
    ]
    return "\n".join(
        [
            "(code-index)=",
            "# Code index",
            "",
            "Every code block in the documentation. **Python blocks are verified**:",
            "each is compiled by `test_doc_code.py`, so a snippet that cannot even be",
            "parsed fails the suite, and a block marked ```` ```python run ```` is",
            "additionally executed. A block that must not be run — one that deletes",
            "files, needs a measurement, or shows a fragment — simply omits the",
            "marker and is still compiled.",
            "",
            f"*{len(rows)} blocks, {python} Python, {runnable} executed.*",
            "",
            "| # | Language | Section | Lines | Verified | Page |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def generate(check: bool = False) -> int:
    provenance = load_provenance()
    outputs = {
        DOCS / "reference" / "figures.md": render_figures(collect_figures(), provenance),
        DOCS / "reference" / "tables.md": render_tables(collect_tables()),
        DOCS / "reference" / "code.md": render_code(collect_code()),
    }
    stale = []
    for path, content in outputs.items():
        if check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != content:
                stale.append(path.name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    if check:
        if stale:
            print("stale registers: " + ", ".join(stale))
            print("run build_tools/docs/make_registers.py")
            return 1
        print("registers are up to date")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when a register is stale")
    return generate(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
