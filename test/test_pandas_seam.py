"""Guard: the shipped package's pandas surface only ever shrinks.

**The direction is out.** pandas is an *interop* format here — something handed
to a notebook, or read from a file only it knows — not the storage model. The
storage model is the columnar store behind
:mod:`chisurf.core.datastore`, and every table that moves onto it is a file that
should stop importing pandas.

That is a many-session migration, so this test measures it rather than
finishing it. ``test/pandas_import_allowlist.txt`` lists every non-test file that still
imports pandas — a test building a fixture frame *is* interop, which is what
pandas is kept for — and the test fails on:

* a **new** importer that is not on the list — write the table through
  :mod:`chisurf.core.datastore` instead;
* a **stale** entry, i.e. a listed file that no longer imports pandas — strike
  it, or the list stops describing the tree and the migration cannot be measured
  by it.

The count in the list header is the tracker. It is not somewhere to add
yourself.

**What removing pandas from the code does and does not achieve.** It does not
remove the package from a solved environment on its own: ``seaborn-base`` and
``statsmodels`` still require it. (The conda ``pdb2pqr`` recipe used to pin
``pandas >=1.0`` too, and was the reason an earlier measurement found pandas
would not leave the dev env at all — ``pdb2pqr`` itself was dropped instead,
since ProteinMC's statistical hydrogen-bond potential only ever needed the
backbone amide H, which is now built in-tree from ideal geometry.) What
removing pandas from the code achieves regardless is that ChiSurf's own tables
stop being frames — which is where the memory, the dtypes and the missing
values are won, and those are worth having whether or not the package is
installed.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "pandas_import_allowlist.txt"

#: Any spelling of the import, at module scope or inside a function.
_IMPORT_RE = re.compile(r"^\s*(?:import\s+pandas|from\s+pandas\s+import)", re.MULTILINE)


def _load_allowlist() -> set[str]:
    """Return the allow-listed importer paths.

    Returns
    -------
    set of str
    """
    lines = _ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


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
        # kept for. Counting those would make the tracker measure the wrong
        # thing and never reach zero for a good reason.
        if any(part in ("test", "tests") for part in path.parts):
            continue
        if _IMPORT_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_no_new_pandas_importer():
    """A table that needs storing goes through the columnar seam, not a frame."""
    unlisted = _current_importers() - _load_allowlist()
    assert not unlisted, (
        "these import pandas without being on the shrinking allow-list:\n  "
        + "\n  ".join(sorted(unlisted))
        + "\nUse chisurf.core.datastore (write_table / write_csv_table / "
        "store_from_arrays) rather than a DataFrame."
    )


def test_the_allowlist_has_no_stale_entries():
    """A file that no longer imports pandas must leave the list, or the count
    stops meaning anything and the migration cannot be measured by it."""
    stale = _load_allowlist() - _current_importers()
    assert not stale, (
        f"these no longer import pandas and should be struck from "
        f"{_ALLOWLIST.name}:\n  " + "\n  ".join(sorted(stale))
    )
