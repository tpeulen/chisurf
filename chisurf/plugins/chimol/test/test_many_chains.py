"""A structure with hundreds of chains must not eat the viewport.

Reported with a screenshot: the NPC (`pdbdev_00000012`, 234 184 atoms) filled
the entire window with one sequence row per chain and left no molecule.

The fix was to stop splitting. **PyMOL keeps one row per object** — checked in
`Seeker.cpp`, where `nRow++` closes the per-object loop — and shows chains
*within* it, `seq_view_format 3` writing the chain id as its own column at each
boundary. A row per chain reads fine on a four-chain protein and is unusable on
an integrative model, which is the case that found it.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")

from chimol.app.molview_main_window import (  # noqa: E402
    MolViewPluginWindow,
)
from chimol.renderer.internal_gui import InternalGui  # noqa: E402

CHAINS, PER_CHAIN = 250, 300


@pytest.fixture(scope="module")
def rows():
    letters = [f"C{i:03d}" for i in range(CHAINS)]
    chains = np.repeat(letters, PER_CHAIN)
    total = CHAINS * PER_CHAIN
    codes = (list("ACDEFGHIKLMNPQRSTVWY") * (total // 20 + 1))[:total]
    numbers = list(range(1, total + 1))
    return MolViewPluginWindow._sequence_rows_for_object(
        "o1", "npc", codes, numbers, [], chains
    )


def test_two_hundred_and_fifty_chains_make_one_row(rows):
    assert len(rows) == 1
    assert rows[0].name == "npc"


def test_the_strip_stays_a_band_whatever_the_structure(rows):
    gui = InternalGui()
    gui.sequence_visible = True
    gui.sequences = rows
    gui.layout(900, 640)
    assert gui.sequence_height() <= 640 * gui.SEQ_MAX_FRACTION + gui.SEQ_ROW_H


def test_every_residue_is_still_reachable(rows):
    """One row is only acceptable if nothing was dropped to get it."""
    mapping = [i for i in rows[0].residue_indices if i >= 0]
    assert mapping == list(range(CHAINS * PER_CHAIN))


def test_the_chain_ids_are_in_the_row(rows):
    assert rows[0].codes.startswith("C000 ")
    assert "C001 " in rows[0].codes


def test_a_small_structure_reads_the_same_way():
    chains = np.array(["A"] * 3 + ["B"] * 2)
    built = MolViewPluginWindow._sequence_rows_for_object(
        "o1", "148l", list("ACDEF"), [1, 2, 3, 10, 11], [], chains
    )
    assert len(built) == 1
    assert built[0].codes == "A ACDB EF"
    assert built[0].residue_indices == [-1, -1, 0, 1, 2, -1, -1, 3, 4]
