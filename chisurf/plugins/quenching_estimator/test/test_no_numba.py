"""Guard: the QuEst engine imports numba nowhere (retired 2026-10-05)."""

from __future__ import annotations

import pathlib
import re

_PLUGIN = pathlib.Path(__file__).resolve().parent.parent
_IMPORT = re.compile(r"^\s*(import\s+numba\b|from\s+numba\b)", re.MULTILINE)


def test_shipped_source_does_not_import_numba():
    offenders = [
        str(p.relative_to(_PLUGIN))
        for p in _PLUGIN.rglob("*.py")
        if "test" not in p.relative_to(_PLUGIN).parts
        and _IMPORT.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not offenders, f"numba is retired; port these to NumPy: {offenders}"
