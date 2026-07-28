"""Every burst-analysis companion must follow one contract, or it misaligns.

A burst folder is merged **column-wise, by position**: the ``.bur`` tables give
one row per burst, and each companion (``bv4``, ``2c4``, ``bg4``, ``bh4``, the
per-state MLE folders) contributes columns to the same rows. Nothing validates
that at read time — a companion that gets the layout wrong does not fail, it
shifts, and one burst's lifetime is reported against another burst's efficiency.

These pin the contract itself and the names the burst plugins declare, so a new
analysis cannot quietly write something the folder reader will never merge.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio.fluorescence.burst_companion import (
    CompanionError,
    companion_path,
    is_companion_dir,
    read_companion,
    write_companion,
)

COLUMNS = ["Thing A", "Thing B"]


def test_a_companion_round_trips_one_row_per_burst(tmp_path):
    rows = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    path = write_companion(tmp_path, "xx4", "m000", COLUMNS, rows)

    assert path == tmp_path / "xx4" / "m000.xx4"
    lines = path.read_text().splitlines()
    assert lines[0] == "Thing A\tThing B\t", "the header keeps its trailing tab"
    # Zero-interleaved: 2N+1 physical rows, data on the odd ones.
    assert len(lines) == 1 + 2 * len(rows) + 1
    columns, back = read_companion(path)
    assert columns == COLUMNS
    assert np.allclose(back, rows)
    raw = np.loadtxt(path, skiprows=1, delimiter="\t")
    assert np.allclose(raw[0::2], 0.0), "the padding rows must stay zero"


def test_a_directory_that_would_never_be_read_is_refused(tmp_path):
    """The reader discovers companions by the trailing '4'. Anything else is lost.

    This is not hypothetical: the per-state MLE folders were first named
    ``bg4_s0``, which is written happily and merged by nothing.
    """
    with pytest.raises(CompanionError, match="does not end in '4'"):
        write_companion(tmp_path, "bg4_s0", "m000", COLUMNS, [[1.0, 2.0]])
    with pytest.raises(CompanionError):
        companion_path(tmp_path, "results", "m000")

    assert is_companion_dir("bh4") and is_companion_dir("s0_bg4")
    assert not is_companion_dir("bi4_bur"), "the burst directory is not a companion"
    assert not is_companion_dir("bur")


def test_duplicate_columns_are_refused(tmp_path):
    """Companions merge into one frame; a duplicate name is dropped with its data."""
    with pytest.raises(CompanionError, match="duplicate column"):
        write_companion(tmp_path, "xx4", "m000", ["Tau", "Tau"], [[1.0, 2.0]])


def test_a_shape_mismatch_is_refused(tmp_path):
    with pytest.raises(CompanionError, match="does not match"):
        write_companion(tmp_path, "xx4", "m000", COLUMNS, [[1.0, 2.0, 3.0]])


def test_non_finite_values_become_the_sentinel(tmp_path):
    """A skipped burst keeps its row; NaN would read differently per reader."""
    path = write_companion(
        tmp_path, "xx4", "m000", COLUMNS, [[np.nan, 1.0], [np.inf, 2.0]]
    )
    _, back = read_companion(path)
    assert np.isfinite(back).all()
    assert back[0, 0] == 0.0 and back[1, 0] == 0.0


def test_the_burst_plugins_declare_discoverable_companions():
    """Every companion name a burst plugin writes must be discoverable."""
    from chisurf.plugins.burst.burst_h2mm.core.export import H2MM_COMPANION

    # Every companion directory the burst plugins write. Sub-populations are
    # *columns* of the burst row (Tau S0 (green)), not folders of their own —
    # see the state-split MLE — so this list stays short by design.
    declared = [H2MM_COMPANION, "bg4", "br4", "by4", "bv4", "2c4"]

    bad = [name for name in declared if not is_companion_dir(name)]
    assert not bad, f"companion(s) a burst folder reader would never merge: {bad}"


def test_the_h2mm_companion_columns_are_namespaced():
    """Columns from different companions land in one frame — names must not clash."""
    from chisurf.plugins.burst.burst_h2mm.core.export import H2MM_COMPANION_COLUMNS

    assert all(c.startswith("H2MM ") for c in H2MM_COMPANION_COLUMNS), (
        H2MM_COMPANION_COLUMNS
    )
    assert len(set(H2MM_COMPANION_COLUMNS)) == len(H2MM_COMPANION_COLUMNS)
