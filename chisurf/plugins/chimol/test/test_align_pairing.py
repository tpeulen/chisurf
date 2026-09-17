"""``align`` / ``super`` / ``rms`` must pair residues by identity, not position.

The bug
-------
``_align_or_super`` paired residues by their **position in the selection**,
truncated to ``min(len, len)`` -- the longer selection simply cut short. Its own
comment said so: *"For now, let's assume sequence-based matching (by index in
the selection)"*.

So any two structures differing by an insertion, a deletion, a missing loop or
merely a different first residue number were superposed on **mismatched
residues**, and the RMSD that came back was meaningless with nothing to say so.

The number that shows it: a 131-residue fragment of 148L, residues 30-160, cut
from that very structure. Superposed on its own parent the answer is exactly
zero. Pairing by position offsets every residue by 29 and reports **15.96 A**.

The fix
-------
Three rules in order -- chain and residue number, residue number alone, then
Needleman-Wunsch on the one-letter sequences. The aligner already existed in
``analysis/sequence.py`` and was called by nothing.

Falling back to position is deliberately *not* a rule. Refusing to pair is
better than a confident wrong number, so a genuinely unrelated pair of
selections now errors.
"""

from __future__ import annotations

import re

import pytest
from toolkit_free import probe

#: Residues 30-160 of 148L, taken from 148L itself. The correct RMSD against
#: its parent is exactly zero, whatever route the pairing takes to get there.
_FRAGMENT = "148l and resi 30-160"


@pytest.fixture(scope="module")
def measured():
    return probe(f"""
        app = open_app(size=(500, 380))
        app.cmd.do("fetch 148L")
        app.cmd.do("create frag, {_FRAGMENT}")

        errors = []
        app.cmd.set_error_callback(errors.append)
        messages = []
        app.cmd.set_message_callback(messages.append)

        viewer = app.viewer
        ids = {{o.get("name"): o["id"] for o in viewer.list_objects()}}
        emit("objects", ",".join(sorted(ids)))

        full = np.asarray(viewer.get_residue_positions(None, object_id=ids["148l"]))
        frag = np.asarray(viewer.get_residue_positions(None, object_id=ids["frag"]))
        emit("full_residues", full.shape[0])
        emit("frag_residues", frag.shape[0])

        for command in ("align frag, 148l", "super frag, 148l", "rms frag, 148l"):
            messages.clear()
            errors.clear()
            app.cmd.do(command)
            said = [m for m in messages if "RMSD" in m or "RMS" in m]
            emit(command.split()[0] + "_said", said[-1] if said else "NOTHING")
            emit(command.split()[0] + "_errors", len(errors))

        # What pairing by position would have produced, computed here so the
        # comparison is against this very structure rather than a remembered
        # number.
        n = min(full.shape[0], frag.shape[0])
        a, b = frag[:n], full[:n]
        d, e = a - a.mean(0), b - b.mean(0)
        u, _s, vt = np.linalg.svd(d.T @ e)
        sign = np.sign(np.linalg.det(vt.T @ u.T))
        rotation = vt.T @ np.diag([1.0, 1.0, sign]) @ u.T
        emit("positional_rmsd", float(np.sqrt(((((d @ rotation.T) - e) ** 2).sum()) / n)))
    """)


def test_the_fragment_is_shorter_than_its_parent(measured):
    """The premise: if they were the same length the bug would not show."""
    assert int(measured["frag_residues"]) < int(measured["full_residues"])


def test_pairing_by_position_would_be_badly_wrong(measured):
    """Kept as a test because it is the whole justification for the change.

    The scale matters: this is not a rounding difference, it is a 16 Angstrom
    answer to a question whose answer is zero.
    """
    assert float(measured["positional_rmsd"]) > 5.0, (
        "expected positional pairing to be grossly wrong on an offset fragment"
    )


@pytest.mark.parametrize("command", ["align", "super", "rms"])
def test_a_fragment_superposes_on_its_parent_exactly(measured, command):
    """Zero, because the fragment's coordinates came from the parent."""
    assert int(measured[f"{command}_errors"]) == 0, f"{command} reported an error"
    said = measured[f"{command}_said"]
    assert said != "NOTHING", f"{command} reported no RMSD at all"
    # The last number in the line. `align` says "(RMSD: 0.000 Å)" while `rms`
    # says "RMSD between A and B over N atoms: 0.000 Å" -- taking the token
    # after "RMSD" works for one and yields "between" for the other.
    numbers = re.findall(r"\d+\.\d+", said)
    assert numbers, f"{command} printed no number: {said}"
    assert float(numbers[-1]) < 0.05, (
        f"{command} gave RMSD {numbers[-1]}; the fragment is an exact subset"
    )


def test_every_residue_of_the_fragment_is_paired(measured):
    """Not just a low RMSD -- the *right number* of residues behind it.

    A pairing rule that matched only a handful of residues could also report a
    small RMSD, and would be just as wrong.
    """
    said = measured["align_said"]
    assert f"{measured['frag_residues']}/{measured['frag_residues']}" in said, (
        f"expected all {measured['frag_residues']} fragment residues paired: {said}"
    )
