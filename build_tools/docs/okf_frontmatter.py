#!/usr/bin/env python
"""Write Open Knowledge Format front matter into the documentation pages.

Reads every Markdown page under ``docs/``, derives its ``type``, ``title``,
``description`` and ``tags`` (see :mod:`build_tools.docs.okf` for how), and
writes the header in. Pages produced by a generator are skipped — their
generator emits the header itself, so touching them here would only be undone
on the next regeneration.

Existing headers are preserved by default: a description someone improved by
hand is not reverted to the derived one. ``--refresh`` overrides that.

Usage::

    python build_tools/docs/okf_frontmatter.py            # write
    python build_tools/docs/okf_frontmatter.py --check     # fail if a page lacks one
    python build_tools/docs/okf_frontmatter.py --refresh   # re-derive every field
    python build_tools/docs/okf_frontmatter.py --report    # print the derived headers
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from build_tools.docs.okf import (  # noqa: E402
    OKF_VERSION,
    RESERVED_NAMES,
    apply_front_matter,
    derive_meta,
    read_front_matter,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "docs"

#: Directories under ``docs/`` that hold no pages of ours.
SKIP_PARTS = frozenset({"_build", "_ext", "_old_manual", "__pycache__"})

#: Pages written by a generator. Their front matter comes from the generator;
#: see :mod:`build_tools.docs.generate_plugin_docs`, :mod:`make_registers` and
#: :mod:`make_bibliography`.
GENERATED_GLOBS = (
    "reference/plugins/*.md",
    "reference/parameters.md",
    "reference/figures.md",
    "reference/tables.md",
    "reference/code.md",
    "references/index.md",
)

#: The bundle root declares which version of the specification it targets.
ROOT_INDEX = "index.md"


def is_generated(relative: pathlib.PurePosixPath) -> bool:
    """Return whether a page is produced by one of the doc generators."""
    return any(relative.match(pattern) for pattern in GENERATED_GLOBS)


def iter_pages(docs_root: pathlib.Path = DOCS_ROOT) -> list[pathlib.Path]:
    """Return every Markdown page under ``docs/`` that this tool owns."""
    pages: list[pathlib.Path] = []
    for path in sorted(docs_root.rglob("*.md")):
        if SKIP_PARTS.intersection(path.parts):
            continue
        relative = pathlib.PurePosixPath(path.relative_to(docs_root).as_posix())
        if is_generated(relative):
            continue
        pages.append(path)
    return pages


def meta_for(path: pathlib.Path, *, preserve: bool, docs_root: pathlib.Path = DOCS_ROOT) -> dict:
    """Return the front matter a page should carry."""
    relative = pathlib.PurePosixPath(path.relative_to(docs_root).as_posix())
    text = path.read_text(encoding="utf-8")
    keep: dict = {}
    if relative.as_posix() == ROOT_INDEX:
        keep["okf_version"] = OKF_VERSION
    return derive_meta(relative, text, keep=keep, preserve=preserve)


def main(argv: list[str] | None = None) -> int:
    """Write, check or report the documentation's front matter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report pages without a conformant header and exit non-zero.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-derive every field, discarding hand-edited values.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print each page's derived header instead of writing it.",
    )
    parser.add_argument("paths", nargs="*", help="Limit to these pages.")
    arguments = parser.parse_args(argv)

    if arguments.paths:
        pages = [pathlib.Path(p).resolve() for p in arguments.paths]
    else:
        pages = iter_pages()

    missing: list[str] = []
    written = 0
    for path in pages:
        relative = path.relative_to(DOCS_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        existing = read_front_matter(text)

        if arguments.check:
            if pathlib.PurePosixPath(relative).name in RESERVED_NAMES:
                continue
            if not existing.get("type"):
                missing.append(relative)
            continue

        meta = meta_for(path, preserve=not arguments.refresh)
        if arguments.report:
            print(f"# {relative}")
            for key, value in meta.items():
                print(f"  {key}: {value}")
            continue

        updated = apply_front_matter(text, meta)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            written += 1

    if arguments.check:
        for relative in missing:
            print(f"missing OKF front matter: docs/{relative}")
        if missing:
            print(f"\n{len(missing)} page(s) without a header — run {pathlib.Path(__file__).name}")
            return 1
        print(f"{len(pages)} documentation pages carry OKF front matter")
        return 0

    if not arguments.report:
        print(f"{written} page(s) updated of {len(pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
