"""Guard: tables go into HDF5 through the columnar seam, never through a frame.

**The rule: write with** :func:`chisurf.core.datastore.write_table`, **never with
a frame's HDF5 writer.** ``to_hdf`` / ``HDFStore`` reach an optional package that
a freshly solved environment does not carry, so a writer that uses one is *dead*
there — and dead quietly, since it works in every developer environment that
still has the package installed from before it was dropped. That is exactly how
seven such call sites survived the removal unnoticed.

Concretely:

* **no writer.** ``to_hdf`` and ``HDFStore`` are banned outright in the shipped
  package. There is no allow-list for them, because there is no file a new one
  belongs in;
* **readers are allow-listed and the list is shrinking.**
  ``test/pandas_hdf5_read_allowlist.txt`` names the places that still read the
  older frame-written layout, which files from earlier releases are in. That
  fallback is deliberate and is a *named decline* where the package is absent
  (:class:`~chisurf.core.datastore.LegacyTableError`) — but it is a fallback,
  never the path a newly written file takes, and every entry is a candidate for
  deletion once its files are converted;
* the seam reads the columnar layout **first** and the frame one second.
  Reversing that puts every read through an exception, and hides the day the
  frame branch stops working.

This test fails on a new writer anywhere, on a new reader outside the list, and
on a stale entry — a listed file that no longer reads a frame — so the list
cannot quietly stop describing the tree.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "pandas_hdf5_read_allowlist.txt"

#: A frame written into HDF5, by either spelling. ``HDFStore`` counts as a write
#: even when it is opened for reading: it is the same package either way, and
#: nothing in this tree opens one to read.
_WRITE_RE = re.compile(r"\.to_hdf\s*\(|\bHDFStore\s*\(")
#: A frame read out of HDF5.
_READ_RE = re.compile(r"\bpd\.read_hdf\s*\(|\bpandas\.read_hdf\s*\(")


def _load_allowlist() -> set[str]:
    """Return the allow-listed reader paths.

    Returns
    -------
    set of str
    """
    lines = _ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _matching(pattern: re.Pattern) -> set[str]:
    """Return every shipped file whose source matches ``pattern``.

    Parameters
    ----------
    pattern : re.Pattern
        Compiled expression to search each file with.

    Returns
    -------
    set of str
        Repository-relative POSIX paths.
    """
    found = set()
    for path in _PKG.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_nothing_writes_a_table_through_a_frame():
    """No allow-list, because there is no file a new one of these belongs in."""
    writers = _matching(_WRITE_RE)
    assert not writers, (
        "these write HDF5 through a DataFrame, which needs an optional package a "
        "freshly solved environment does not have:\n  "
        + "\n  ".join(sorted(writers))
        + "\nUse chisurf.core.datastore.write_table."
    )


def test_no_new_frame_reader():
    """A frame read is the legacy path and belongs only where it is recorded."""
    current = _matching(_READ_RE)
    unlisted = current - _load_allowlist()
    assert not unlisted, (
        "these read HDF5 through a DataFrame without being recorded as legacy "
        "fallbacks:\n  "
        + "\n  ".join(sorted(unlisted))
        + f"\nRead through chisurf.core.datastore, or add the file to "
        f"{_ALLOWLIST.name} with the reason."
    )


def test_the_allowlist_has_no_stale_entries():
    """A file that no longer reads a frame must leave the list, or the list stops
    describing the tree and the migration cannot be measured by it."""
    stale = _load_allowlist() - _matching(_READ_RE)
    assert not stale, (
        "these no longer read HDF5 through a DataFrame and should be struck "
        f"from {_ALLOWLIST.name}:\n  " + "\n  ".join(sorted(stale))
    )


def test_the_seam_prefers_the_columnar_layout():
    """Order is behaviour, not taste: the frame branch first would put every read
    through an exception and hide the day it stops working at all."""
    source = (_PKG / "core" / "datastore.py").read_text(encoding="utf-8")
    body = source[source.index("def read_table_frame("):]
    assert body.index("read_table(") < body.index("pd.read_hdf(")
