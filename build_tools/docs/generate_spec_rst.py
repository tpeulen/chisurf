"""Render an OKF specification into reStructuredText, for docs that lack MyST.

PTO.MFDB is normative and has two audiences: agents, which read the OKF bundle,
and people reading the photon-container format documentation next to the
container's own spec. Writing it twice would make the two disagree — which is
the failure mode the profile itself exists to prevent — so the markdown in
``okf/specs/`` is the source and this emits the rst.

Why a purpose-built converter rather than a library: the alternative is a
general markdown-to-rst dependency for one file, and a general converter is
*permissive* — it renders what it does not understand as something plausible.
A silently mangled normative table is worse than a build failure, so this
handles exactly the constructs the specs use and raises
:class:`UnsupportedMarkdown` on anything else.

Usage
-----
``python build_tools/docs/generate_spec_rst.py [--check]``

``--check`` regenerates in memory and exits non-zero if the committed rst is
stale, which is what the guardrail test runs.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: ``(markdown source, generated rst)``, both repo-relative.
SPECS: list[tuple[str, str]] = [
    ("okf/specs/pto-mfdb.md", "modules/tttrlib/doc/formats/pto-mfdb.rst"),
]

GENERATED_HEADER = """.. This file is GENERATED from {source} by
   build_tools/docs/generate_spec_rst.py -- do not edit it here.
   Edit the markdown and re-run: pixi run docs-specs
"""

#: Heading level -> reST underline character.
UNDERLINES = {1: "=", 2: "-", 3: "~", 4: "^"}


class UnsupportedMarkdown(RuntimeError):
    """A construct this converter would have had to guess at."""


def _strip_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML frontmatter from the body.

    Only the flat ``key: value`` pairs the OKF frontmatter uses are read; the
    body is returned verbatim.

    Parameters
    ----------
    text : str
        Full file contents.

    Returns
    -------
    tuple of (dict, str)
        The frontmatter mapping and the remaining body.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise UnsupportedMarkdown("frontmatter is not terminated")
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("'\"")
    return meta, text[end + 5 :]


def _inline(text: str) -> str:
    """Convert inline markdown spans to reST.

    Parameters
    ----------
    text : str
        One line of markdown, outside any literal block.

    Returns
    -------
    str
        The reST equivalent.
    """
    # Links first, so their labels are not re-processed as emphasis.
    def _link(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://")):
            return f"`{label} <{target}>`_"
        # An OKF-relative path means nothing outside the bundle; keep the words.
        return f"*{label}*"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    # reST wants double backticks for literals.
    text = re.sub(r"(?<!`)`([^`]+)`(?!`)", r"``\1``", text)
    return text


def _table(rows: list[str]) -> list[str]:
    """Convert a pipe table to a ``list-table`` directive.

    ``list-table`` is used rather than a grid table because it needs no column
    arithmetic, so a long cell cannot silently break the borders.

    Parameters
    ----------
    rows : list of str
        The pipe-table lines, including the header separator.

    Returns
    -------
    list of str
        reST lines.
    """
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]]

    out = [".. list-table::", "   :header-rows: 1", ""]
    for row in [header, *body]:
        for i, cell in enumerate(row):
            bullet = "   * - " if i == 0 else "     - "
            out.append(f"{bullet}{_inline(cell) if cell else '..'}")
    out.append("")
    return out


def _convert(body: str, title: str, slug: str) -> str:
    """Convert a spec body to reST.

    Parameters
    ----------
    body : str
        Markdown with frontmatter already removed.
    title : str
        Document title, from the frontmatter.
    slug : str
        Cross-reference label for the document, e.g. ``pto_mfdb_format``.

    Returns
    -------
    str
        The rendered reStructuredText.

    Raises
    ------
    UnsupportedMarkdown
        On any construct this converter does not handle.
    """
    out: list[str] = [f".. _{slug}:", "", title, UNDERLINES[1] * len(title), ""]
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            out.append("")
            i += 1
            continue

        if stripped.startswith("```"):
            out.extend(["::", ""])
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                out.append("   " + lines[i] if lines[i] else "")
                i += 1
            if i >= len(lines):
                raise UnsupportedMarkdown("unterminated fenced code block")
            out.append("")
            i += 1
            continue

        if stripped.startswith("#"):
            # OKF specs use `#` for their top-level *sections*; the document
            # title comes from the frontmatter. So every heading drops one
            # level, or the first `#` would become a sibling of the title and
            # split the page into two documents.
            level = len(stripped) - len(stripped.lstrip("#")) + 1
            if level not in UNDERLINES:
                raise UnsupportedMarkdown(f"heading depth {level - 1}")
            heading = _inline(stripped[level - 1 :].strip())
            out.extend(["", heading, UNDERLINES[level] * len(heading), ""])
            i += 1
            continue

        if stripped.startswith("|"):
            table: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            if len(table) < 2 or not set(table[1].replace("|", "").strip()) <= set("-: "):
                raise UnsupportedMarkdown("pipe table without a header separator")
            out.extend(_table(table))
            continue

        if stripped.startswith(">"):
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(_inline(lines[i].strip().lstrip(">").strip()))
                i += 1
            out.extend(["", ".. note::", ""])
            out.extend(f"   {q}" if q else "" for q in quote)
            out.append("")
            continue

        indent = len(line) - len(line.lstrip())
        if re.match(r"^[-*] ", stripped):
            out.append(" " * indent + "- " + _inline(stripped[2:]))
            i += 1
            continue
        if re.match(r"^\d+\. ", stripped):
            number, _, rest = stripped.partition(". ")
            out.append(" " * indent + f"{number}. " + _inline(rest))
            i += 1
            continue

        out.append(" " * indent + _inline(stripped))
        i += 1

    # Collapse runs of blank lines; reST does not care, diffs do.
    rendered: list[str] = []
    for line in out:
        if line == "" and rendered and rendered[-1] == "":
            continue
        rendered.append(line)
    return "\n".join(rendered).strip() + "\n"


def render(source: Path) -> str:
    """Render one spec file to reST text.

    Parameters
    ----------
    source : Path
        Path to the markdown spec.

    Returns
    -------
    str
        Full file contents, including the generated-file header.
    """
    meta, body = _strip_frontmatter(source.read_text(encoding="utf-8"))
    title = meta.get("title") or source.stem
    slug = source.stem.replace("-", "_") + "_format"
    try:
        rel = source.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = source.name
    return GENERATED_HEADER.format(source=rel) + "\n" + _convert(body, title, slug)


def main(argv: list[str] | None = None) -> int:
    """Generate, or check, every registered spec.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments; ``sys.argv[1:]`` when omitted.

    Returns
    -------
    int
        Process exit status: ``1`` if ``--check`` found a stale file.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the generated file is out of date",
    )
    args = parser.parse_args(argv)

    stale: list[str] = []
    for src_rel, dst_rel in SPECS:
        source = REPO_ROOT / src_rel
        target = REPO_ROOT / dst_rel
        if not source.exists():
            print(f"missing spec source: {src_rel}", file=sys.stderr)
            return 1
        rendered = render(source)
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == rendered:
            print(f"up to date: {dst_rel}")
            continue
        if args.check:
            stale.append(dst_rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote: {dst_rel}")

    if stale:
        print(
            "stale generated spec(s): " + ", ".join(stale) + "\nrun: pixi run docs-specs",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
