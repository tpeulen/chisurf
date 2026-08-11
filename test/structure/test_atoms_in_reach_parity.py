"""``atoms_in_reach`` must still return what its numba version returned.

The kernel was a two-pass loop compiled with ``@nb.jit``: measure every atom's
squared distance to the attachment atom, then copy the ones inside ``dmaxsq``
into fresh arrays. It is a boolean mask, so it vectorises exactly — and the
port has to be *exactly* that, because the callers index the two returned
arrays against each other and against nothing else.

The reference is a committed fixture recorded from the numba original **before
it was deleted**, not a live comparison. Comparing against numba at test time
turns into a skip the day numba leaves the environment, and a skip reads like a
pass.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.structure.av.utils import atoms_in_reach

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "numba_parity" / "atoms_in_reach.npz"
)


@pytest.fixture(scope="module")
def cases():
    """The recorded (input, output) pairs, as a list of dicts."""
    if not _FIXTURE.is_file():
        pytest.skip(f"missing fixture {_FIXTURE}")
    with np.load(_FIXTURE) as data:
        n = int(data["n_cases"])
        return [
            {k: data[f"{k}_{i}"] for k in ("xyz", "vdw", "dmaxsq", "atom_i", "ra", "vdwr")}
            for i in range(n)
        ]


def test_the_fixture_covers_empty_partial_and_full_selections(cases):
    """A parity fixture that only ever selects everything proves nothing."""
    counts = {len(c["ra"]) for c in cases}
    sizes = {len(c["xyz"]) for c in cases}
    assert 0 in counts, "no case selects nothing"
    assert any(0 < len(c["ra"]) < len(c["xyz"]) - 1 for c in cases), "no partial selection"
    assert any(len(c["ra"]) == len(c["xyz"]) - 1 for c in cases), "no all-but-self selection"
    assert len(sizes) > 1


def test_the_selection_matches_the_numba_reference(cases):
    """Same atoms, same radii, same order, bit for bit."""
    for i, c in enumerate(cases):
        ra, vdwr = atoms_in_reach(
            xyz=c["xyz"], vdw=c["vdw"], dmaxsq=float(c["dmaxsq"]), atom_i=int(c["atom_i"])
        )
        np.testing.assert_array_equal(ra, c["ra"], err_msg=f"case {i}: coordinates")
        np.testing.assert_array_equal(vdwr, c["vdwr"], err_msg=f"case {i}: radii")


def test_the_attachment_atom_is_never_in_its_own_neighbourhood(cases):
    """Distance zero is inside every cutoff, so excluding self is load-bearing."""
    for c in cases:
        ra, _ = atoms_in_reach(
            xyz=c["xyz"], vdw=c["vdw"], dmaxsq=float(c["dmaxsq"]), atom_i=int(c["atom_i"])
        )
        assert not np.any(np.all(ra == c["xyz"][int(c["atom_i"])], axis=1))


def test_the_two_returned_arrays_stay_aligned(cases):
    """Callers zip coordinates against radii; a mismatch would be silent."""
    for c in cases:
        ra, vdwr = atoms_in_reach(
            xyz=c["xyz"], vdw=c["vdw"], dmaxsq=float(c["dmaxsq"]), atom_i=int(c["atom_i"])
        )
        assert len(ra) == len(vdwr)
        assert ra.dtype == np.float64 and vdwr.dtype == np.float64
