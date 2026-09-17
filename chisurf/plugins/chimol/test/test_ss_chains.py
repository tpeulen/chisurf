"""Secondary structure knows where one chain ends and the next begins.

The bug
-------
:func:`assign_ss_c3_from_atoms` built one flat ``(n, 4, 3)`` backbone array from
every residue in the structure and ran DSSP down it as if it were a single
polypeptide. Three consequences, none of which raise anything:

* the **last residues of one chain were read as turning into the first of the
  next** -- DSSP's helix patterns are stated as sequence offsets, i bonded to
  i+4, and once the array index stops tracking chain position an i+4 can be in
  another molecule entirely;
* **proline donated hydrogen bonds**. Its nitrogen is in the pyrrolidine ring
  and carries no hydrogen; DSSP has excluded it as a donor since 1983. The
  amide H was modelled onto it anyway, inventing the i,i+4 bonds that make a
  helix;
* a residue **missing a backbone atom was dropped from the middle** of the
  array and the codes were then padded at the *end*, so every residue after the
  gap got the code belonging to its neighbour.

What is deliberately *not* segmented
------------------------------------
The hydrogen-bond map itself. A beta bridge is a spatial pairing, and
inter-chain sheets are ordinary -- a domain-swapped dimer, a barrel built from
several chains. The first version of this fix ran DSSP per chain and lost 40 of
1DG3's 68 strand residues, which is why that structure is pinned below.

So the split is: **helices per segment, bridges across the whole structure**,
with only the three-residue windows that straddle a break masked out.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from chimol.analysis import ss as S

#: Two helices of 148L, by residue number, used as the two chains. Real backbone
#: geometry rather than a built one: the peptide C-N bond has to be a real 1.33 A
#: bond, and getting it wrong is what the segment split keys on.
#:
#: They must be *different* helices. Laying a helix end-to-end against a copy of
#: itself does not discriminate -- the fused thing is still a helix, so the
#: chain-blind answer happens to be right and the test pins nothing. These two
#: do discriminate: run together and chain-blind, chain B's first residue turns
#: from coil into helix, read as a turn continuing out of chain A.
_HELIX_A = (93, 106)
_HELIX_B = (38, 50)

_CACHE = Path.home() / ".chisurf/structures/chimol/chimol_pdb_148l.pdb"


def _lysozyme():
    """148L's atoms, or a skip."""
    if not _CACHE.exists():
        pytest.skip("148l is not in the local structure cache")
    from chisurf.core.fio.structure import coordinates

    return coordinates.read_coordinates(str(_CACHE))


def _names(atoms):
    return np.char.strip(np.asarray(atoms["atom_name"]).astype(str))


def _slice_residues(atoms, first, last):
    ids = np.asarray(atoms["res_id"], dtype=int)
    return atoms[(ids >= first) & (ids <= last)]


def _translated_copy(atoms, chain, shift):
    """The same residues again, relabelled and moved."""
    out = atoms.copy()
    out["chain"] = chain
    out["xyz"] = np.asarray(out["xyz"], dtype=float) + shift
    return out


def _continuation_shift(first, second):
    """Move *second* so it starts where *first* stopped.

    Deliberately end-to-end: the second chain's first residue lands where the
    first chain's next residue would have been. That is the arrangement a
    chain-blind assignment cannot tell from one continuous chain, and the one
    this whole change exists to get right.
    """
    ca_a = np.asarray(first["xyz"], dtype=float)[_names(first) == "CA"]
    ca_b = np.asarray(second["xyz"], dtype=float)[_names(second) == "CA"]
    return (ca_a[-1] + (ca_a[-1] - ca_a[-2])) - ca_b[0]


def _chain(residues, label):
    """One helix of 148L, relabelled as its own chain."""
    out = _slice_residues(_lysozyme(), *residues).copy()
    out["chain"] = label
    return out


@pytest.fixture(scope="module")
def one_chain():
    """Chain A on its own, for comparison."""
    return _chain(_HELIX_A, "A")


@pytest.fixture(scope="module")
def other_chain():
    """Chain B on its own, in the place it occupies in ``two_chains``."""
    first, second = _chain(_HELIX_A, "A"), _chain(_HELIX_B, "B")
    return _translated_copy(second, "B", _continuation_shift(first, second))


@pytest.fixture(scope="module")
def two_chains(one_chain, other_chain):
    """Two different helices, laid end to end as chains A and B."""
    return np.concatenate([one_chain, other_chain])


def _length(atoms):
    return S._backbone_record(atoms).coords.shape[0]


def test_a_chain_change_breaks_the_backbone_into_segments(two_chains, one_chain, other_chain):
    """The premise. Without two segments nothing below can hold."""
    record = S._backbone_record(two_chains)
    assert record is not None
    assert [stop - start for start, stop in record.segments] == [
        _length(one_chain),
        _length(other_chain),
    ]


def test_a_long_gap_breaks_a_segment_even_within_one_chain(one_chain):
    """A disordered loop carries one chain label across a physical hole."""
    far = _translated_copy(one_chain, "A", np.array([0.0, 0.0, 60.0]))
    far["res_id"] = np.asarray(far["res_id"], dtype=int) + 500
    record = S._backbone_record(np.concatenate([one_chain, far]))
    assert len(record.segments) == 2, record.segments


def test_the_helix_is_recognised_at_all(one_chain):
    """The control. A test about helices needs one to be found."""
    n = _length(one_chain)
    codes = S.assign_ss_c3_from_atoms(one_chain, n_res=n, verbose=False)
    assert codes.count("H") >= 6, "".join(codes)


def test_the_junction_between_two_chains_is_not_read_as_helix(two_chains, one_chain, other_chain):
    """No residue may be helical *because of* its neighbour in another chain.

    Checked against the chain's own answer rather than against a fixed count:
    what matters is that the codes stop depending on what follows the chain end.
    """
    n_a, n_b = _length(one_chain), _length(other_chain)
    alone_a = S.assign_ss_c3_from_atoms(one_chain, n_res=n_a, verbose=False)
    alone_b = S.assign_ss_c3_from_atoms(other_chain, n_res=n_b, verbose=False)
    together = S.assign_ss_c3_from_atoms(two_chains, n_res=n_a + n_b, verbose=False)
    assert together is not None

    assert together[:n_a] == alone_a, (
        "chain A was assigned differently once chain B was laid after it -- "
        f"the junction leaked: {''.join(together[:n_a])} vs {''.join(alone_a)}"
    )
    # The half that used to be wrong: chain-blind, B's first residue turns from
    # coil into helix, read as a turn continuing out of A.
    assert together[n_a:] == alone_b, (
        f"chain B differs from itself alone: {''.join(together[n_a:])} vs {''.join(alone_b)}"
    )


def test_proline_cannot_donate_a_hydrogen_bond(one_chain):
    """Its nitrogen is in the ring; the modelled H is fiction."""
    record = S._backbone_record(one_chain)
    before = int(record.donor.sum())

    prolines = one_chain.copy()
    ids = np.asarray(prolines["res_id"], dtype=int)
    prolines["res_name"][ids % 3 == 0] = "PRO"
    record = S._backbone_record(prolines)
    assert int(record.donor.sum()) < before, (
        "marking residues PRO did not remove them as hydrogen-bond donors"
    )


def test_proline_changes_the_answer(one_chain):
    """Not only the mask -- the assignment has to move because of it.

    A donor mask that is computed and then ignored would pass the test above.
    """
    n = _length(one_chain)
    plain = S.assign_ss_c3_from_atoms(one_chain, n_res=n, verbose=False)

    prolines = one_chain.copy()
    ids = np.asarray(prolines["res_id"], dtype=int)
    prolines["res_name"][ids % 2 == 0] = "PRO"
    broken = S.assign_ss_c3_from_atoms(prolines, n_res=n, verbose=False)
    assert broken.count("H") < plain.count("H"), (
        f"a helix of alternating prolines kept its H bonds: {''.join(broken)}"
    )


def test_a_residue_missing_a_backbone_atom_does_not_shift_the_rest():
    """The codes after a gap must stay on their own residues.

    A dropped residue used to shorten the array, and the padding went on the
    end -- so every code after the hole belonged to the residue before it.
    """
    intact = _lysozyme()
    n = int((_names(intact) == "CA").sum())
    full = S.assign_ss_c3_from_atoms(intact, n_res=n, verbose=False)

    # Drop one residue's carbonyl oxygen, well inside the structure; that
    # residue can no longer be assigned, and every later one used to shift.
    victim = int(np.asarray(intact["res_id"], dtype=int)[_names(intact) == "CA"][40])
    keep = ~((np.asarray(intact["res_id"], dtype=int) == victim) & (_names(intact) == "O"))
    gapped = S.assign_ss_c3_from_atoms(intact[keep], n_res=n, verbose=False)

    assert len(gapped) == len(full) == n
    # Everything well after the hole must still line up. The dropped residue
    # and its immediate neighbours legitimately change -- they lost a hydrogen
    # bond -- but the far tail is what the index shift used to destroy.
    disagreements = sum(1 for a, b in zip(gapped[60:], full[60:]) if a != b)
    assert disagreements == 0, (
        f"{disagreements} codes past the gap shifted:\n"
        f"  {''.join(gapped[60:])}\n  {''.join(full[60:])}"
    )


def test_inter_chain_sheets_survive():
    """The regression the segmented-map version introduced, pinned.

    1DG3 is five segments and 68 strand residues assigned chain-blind. Running
    the *bridge* search per segment as well drops it to 28 -- those strands pair
    across chains, and there is nothing in the output to say they went missing.
    """
    from chisurf.core.fio.structure import coordinates

    path = Path.home() / ".chisurf/structures/chimol/chimol_pdb_1dg3.pdb"
    if not path.exists():
        pytest.skip("1dg3 is not in the local structure cache")

    atoms = coordinates.read_coordinates(str(path))
    n_res = int((_names(atoms) == "CA").sum())
    codes = S.assign_ss_c3_from_atoms(atoms, n_res, verbose=False)
    record = S._backbone_record(atoms)

    assert len(record.segments) > 1, "1dg3 should break into several segments"
    strands = codes.count("E")
    assert strands >= 55, f"only {strands} strand residues; inter-chain bridges are being lost"
