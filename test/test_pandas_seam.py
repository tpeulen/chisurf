"""Guard: the shipped package never imports pandas.

**pandas is not the storage model.** The storage model is the columnar store
behind :mod:`chisurf.core.datastore` (``tttrlib.DataStore``), and every table
in the tree is built on it. This test is the completed migration's guard
rail: it fails the moment anything in the shipped package imports pandas
again, at module scope or inside a function.

Test files are exempt on purpose — a test building a fixture frame as an
independent oracle (comparing chisurf's own CSV writer against
``pandas.DataFrame.to_csv``, say) or simulating a file an external tool wrote
is interop, not chisurf depending on pandas, and that is a legitimate thing
for a test to do.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"

#: Any spelling of the import, at module scope or inside a function.
_IMPORT_RE = re.compile(r"^\s*(?:import\s+pandas|from\s+pandas\s+import)", re.MULTILINE)


def _current_importers() -> set[str]:
    """Return every shipped file that imports pandas.

    Returns
    -------
    set of str
        Repository-relative POSIX paths.
    """
    found = set()
    for path in _PKG.rglob("*.py"):
        # A test building a fixture frame IS interop -- that is what pandas is
        # for in a test. It is not chisurf depending on pandas.
        if any(part in ("test", "tests") for part in path.parts):
            continue
        if _IMPORT_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_nothing_shipped_imports_pandas():
    """A table that needs storing goes through the columnar seam, not a frame."""
    importers = _current_importers()
    assert not importers, (
        "these import pandas, which the shipped package no longer depends on:\n  "
        + "\n  ".join(sorted(importers))
        + "\nUse chisurf.core.datastore (write_table / write_csv_table / "
        "store_from_arrays / store_from_rows) rather than a DataFrame."
    )
