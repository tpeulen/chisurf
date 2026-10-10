"""Render the flrCIF / MMFDB extension vocabulary into ``docs/concepts``.

The ``.dic`` files in mmfdb are the schema authority; this page is a projection
of them, so it is generated, never edited. Every category and item of the two
extension dictionaries (``mmfdb_flr_ext.dic``, ``mmfdb_workflow_ext.dic``) is
listed with its type and description.

Usage
-----
``python build_tools/docs/generate_flrcif_vocabulary.py [--check]``

``--check`` exits non-zero when the committed page is stale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "concepts" / "flrcif_vocabulary.md"
EXTENSIONS = ("mmfdb_flr_ext.dic", "mmfdb_workflow_ext.dic")

_HEADER = """---
type: Concept
title: The flrCIF and MMFDB vocabulary
description: Generated reference of the categories and items ChiSurf persists, defined in the mmfdb extension dictionaries.
tags: [concepts, mmfdb, flrcif, vocabulary]
anchor: concept-flrcif-vocabulary
---

(concept-flrcif-vocabulary)=
# The flrCIF and MMFDB vocabulary

Everything ChiSurf and ndX persist is expressed in the PDB-IHM FLR dictionary
(flrCIF) plus two MMFDB extension dictionaries, `mmfdb_flr_ext.dic` and
`mmfdb_workflow_ext.dic`. The dictionaries are the schema authority; this page
is generated from them by `build_tools/docs/generate_flrcif_vocabulary.py`.
A declared analysis feature names one of these items as its `term`.
The [MMFDB admin guide](../guides/102_mmfdb_admin.md) shows where these records are browsed
and curated.

"""


def _cell(text: str) -> str:
    """Escape a description for a markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def render() -> str:
    """Return the page text generated from the bundled extension dictionaries."""
    sys.path.insert(0, str(REPO / "modules" / "mmfdb" / "src"))
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    dic = MmcifDictionary(*[MmcifDictionary.DATA_DIR / n for n in EXTENSIONS])
    out = [_HEADER]
    for name in sorted(dic._categories):
        cat = dic._categories[name]
        if not cat.items:
            continue
        out.append(f"## `_{name}`\n")
        if cat.description:
            out.append(_cell(cat.description) + "\n")
        out.append("| Item | Type | Description |\n|---|---|---|")
        for attr in sorted(cat.items):
            item = cat.items[attr]
            out.append(
                f"| `{item.name}` | {item.type_code or ''} | {_cell(item.description)} |"
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write (or with ``--check`` verify) the generated page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is stale; run this script without --check", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
