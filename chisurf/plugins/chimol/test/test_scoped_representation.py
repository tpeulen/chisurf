"""``show <rep>, <selection>`` must show the selection and nothing else.

Two independent faults made ``hide everything; show cartoon, polymer.nucleic``
draw the entire structure on 1RTD, and each is invisible to a test that only
asks whether *something* was drawn:

* the representation mask was read before the flag. A loaded object carries an
  all-True mask rather than ``None``, so ``hide everything`` cleared the flag
  and left 2028/2028 residues set behind it; the scoped show then OR-ed the
  selection onto a mask that already covered everything. The "off everywhere"
  case the code did handle -- a ``None`` mask -- is one a real object never
  reaches;
* residues were matched by number alone. A residue number is unique only within
  its chain, so the nucleic selection also reached every protein residue that
  happened to be numbered the same: 194 rows for 90 nucleotides, the extra 102
  amino acids appearing as loose loops beside the duplex.

1RTD is the fixture because it is what makes both measurable -- two protein
chains and two nucleic chains, with the numbering overlapping between them.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "1rtd.pdb"
)

NUCLEOTIDES = {"DA", "DC", "DG", "DT", "A", "C", "G", "U", "2DA"}


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def window(qapp):
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")

    win = MolViewPluginWindow()
    win.load_structure_from_path(PDB, name="1rtd")
    yield win
    win.close()


@pytest.fixture
def cmd(window):
    from chimol.commands.command import Cmd

    c = Cmd(window)
    c.set_message_callback(lambda _m: None)
    c.set_error_callback(lambda _m: None)
    return c


def _state(window):
    return next(iter(window.viewer.objects.values())).state


def _masked_residue_names(window) -> np.ndarray:
    state = _state(window)
    mask = np.asarray(state.cartoon_mask, dtype=bool)
    names = np.char.strip(np.asarray(state.residue_names).astype(str))
    return names[mask]


def test_a_scoped_show_after_hide_shows_only_the_selection(window, cmd):
    """The first fault: the flag decides what the stored mask means."""
    cmd.do("hide everything")
    state = _state(window)
    assert state.show_cartoon is False, "hide everything did not clear the flag"

    cmd.do("show cartoon, polymer.nucleic")
    mask = np.asarray(state.cartoon_mask, dtype=bool)
    assert state.show_cartoon is True
    assert mask.any(), "the scoped show drew nothing"
    assert not mask.all(), (
        f"the scoped show drew every one of {mask.size} residues -- the stale "
        "mask left behind by `hide everything` was widened instead of replaced"
    )


def test_a_scoped_show_does_not_reach_into_other_chains(window, cmd):
    """The second fault: a residue is ``(chain, number)``, not a number."""
    cmd.do("hide everything")
    cmd.do("show cartoon, polymer.nucleic")

    names = _masked_residue_names(window)
    strays = sorted({n for n in names.tolist() if n not in NUCLEOTIDES})
    assert not strays, (
        f"{len(names)} residues shown for a nucleic selection, including "
        f"{strays} -- residue numbers were matched across chains"
    )


def test_a_scoped_hide_is_a_no_op_while_the_rep_is_off(window, cmd):
    """Nothing is drawn, so there is nothing for a scoped hide to take away.

    It has to leave the flag alone too: turning it on to record a subtraction
    from an invisible representation is how a hide ends up showing something.
    """
    cmd.do("hide everything")
    state = _state(window)
    before = np.asarray(state.cartoon_mask, dtype=bool).copy()

    cmd.do("hide cartoon, polymer.nucleic")

    assert state.show_cartoon is False, "a scoped hide turned the cartoon on"
    after = state.cartoon_mask
    if after is not None:
        assert np.array_equal(np.asarray(after, dtype=bool), before)


def test_a_chain_selection_selects_that_chain(window, cmd):
    """The general statement of the second fault, on protein chains.

    1RTD numbers its two protein chains over the same range, so a
    number-only match doubles this count.
    """
    cmd.do("hide everything")
    cmd.do("show cartoon, chain A")

    state = _state(window)
    mask = np.asarray(state.cartoon_mask, dtype=bool)
    chains = np.char.strip(np.asarray(state.residue_chain_ids).astype(str))
    reached = sorted(set(chains[mask].tolist()))
    assert reached == ["A"], f"chain A selected residues in chains {reached}"
