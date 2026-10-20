"""An editable ``data_table`` that shows its row key keeps that column read-only.

A table-level ``"editable": true`` makes every column editable, and emtk opens an editable
cell for typing on a single click. A shown row-key column (``#``, an id, a name that keys
the row) is then the only cell left that *selects* a row without opening an editor -- so
when it inherits ``editable``, no click selects a row and the Delete key edits a cell's
text instead of removing the row (tr-anisotropy: Delete removed nothing). The row key is
the row's identity, not a value, so the spec declares it ``"editable": false``.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "chisurf"


def _tables(node):
    if isinstance(node, dict):
        options = node.get("options")
        if node.get("key") == "data_table" and isinstance(options, dict):
            yield options
        for value in node.values():
            yield from _tables(value)
    elif isinstance(node, list):
        for value in node:
            yield from _tables(value)


def test_a_shown_row_key_column_of_an_editable_table_is_read_only():
    offenders = []
    for path in sorted(ROOT.rglob("*.view.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for options in _tables(spec):
            if not options.get("editable") or not options.get("row_key"):
                continue
            for column in options.get("columns", []):
                if column.get("key") == options["row_key"] and column.get("editable", True):
                    offenders.append(f"{path.relative_to(ROOT.parent)}: {column.get('title')!r}")
    assert not offenders, 'declare the row-key column "editable": false: ' + ", ".join(offenders)
