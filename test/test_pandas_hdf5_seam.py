"""Guard: nothing in the shipped package touches HDF5 through a frame.

**The rule: HDF5 goes through** :mod:`chisurf.core.datastore`, **never through a
frame.** ``to_hdf`` / ``read_hdf`` / ``HDFStore`` reach an optional package that
a freshly solved environment does not carry, so a call that uses one is *dead*
there — and dead quietly, since it works in every developer environment that
still has the package installed from before it was dropped. That is exactly how
seven such call sites survived the package's removal unnoticed.

There is **no allow-list**, for writers or for readers. There was one for
readers, holding the two places that still opened the older frame-written
layout; both are gone. A fallback to that reader is a path that works on a
developer's machine and fails on everyone else's, which is the same defect the
writers had — so a file in the older layout is now *refused*, by name, as a file
to convert rather than a file to read.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"

#: A frame written into HDF5, by either spelling. ``HDFStore`` counts even when
#: opened for reading: it is the same package either way.
_WRITE_RE = re.compile(r"\.to_hdf\s*\(|\bHDFStore\s*\(")
#: A frame read out of HDF5.
_READ_RE = re.compile(r"\bpd\.read_hdf\s*\(|\bpandas\.read_hdf\s*\(")


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
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_nothing_writes_a_table_through_a_frame():
    """No allow-list, because there is no file one of these belongs in."""
    writers = _matching(_WRITE_RE)
    assert not writers, (
        "these write HDF5 through a DataFrame, which needs an optional package a "
        "freshly solved environment does not have:\n  "
        + "\n  ".join(sorted(writers))
        + "\nUse chisurf.core.datastore.write_table."
    )


def test_nothing_reads_a_table_through_a_frame():
    """Not even as a fallback. A fallback to this reader works on a developer's
    machine and fails on everyone else's — the same defect the writers had."""
    readers = _matching(_READ_RE)
    assert not readers, (
        "these read HDF5 through a DataFrame:\n  "
        + "\n  ".join(sorted(readers))
        + "\nUse chisurf.core.datastore.read_table / read_table_frame. A file in "
        "the older frame layout is a file to convert, not to read."
    )


def test_the_seam_has_no_frame_reader_behind_it():
    """read_table_frame converts a columnar table; it does not fall back."""
    source = (_PKG / "core" / "datastore.py").read_text(encoding="utf-8")
    body = source[source.index("def read_table_frame("):]
    body = body[: body.index("\ndef ", 1)]
    assert "read_hdf" not in body
    assert "read_table(" in body
