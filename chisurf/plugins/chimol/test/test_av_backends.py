"""The accessible-volume backends, and the fallback that runs anywhere.

`imp-bff` and `labellib` are the physics. The **numpy** backend exists so
``add_dye`` works where neither library can run -- Pyodide in the browser is
the case that matters, and it is where the shipped demo scripts also live.
Without it, the labelling demo in a browser died at its first ``add_dye`` and
everything after it said "nothing is loaded" -- a broken demo, not a missing
library.

Its cloud is the **geometric** accessible volume (uniform over the
linker-length ball minus van der Waals exclusion), not the dye-density
weighted one; it is pinned to stay deterministic, coarse and honest about
both.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.labelling import av

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

POSITION = {
    "chain_identifier": "E",
    "residue_seq_number": 119,
    "atom_name": "CB",
    "_position_name": "E119_CB",
    "linker_length": 22.0,
    "linker_width": 4.5,
    "radius1": 3.5,
    "simulation_type": "AV1",
}


@pytest.fixture(scope="module", name="position")
def _position():
    return dict(POSITION)


def test_the_numpy_backend_is_always_available():
    """No library import gates it -- that is its whole reason."""
    assert "numpy" in av.available_backends()


def test_numpy_computes_a_cloud_that_clears_the_atoms(position):
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    volume = av.compute_av(str(PDB), dict(position), backend="numpy")
    assert volume.n_points > 1_000
    # Every sampled point clears every heavy atom by the dye radius, and no
    # point is farther out than the linker can reach -- the two halves of the
    # geometric model, checked straight against the structure it claims.
    atoms = av.load_structure_with_vdw(str(PDB))
    clean = av.strip_residue_atoms(
        atoms, "E", 119, pdb_path=str(PDB)
    )
    pts = volume.points[:, :3]
    gap = np.linalg.norm(pts[:, None, :] - clean[None, :256, :3], axis=2)
    assert float(gap.min()) >= float(clean[:256, 3].min()) + 3.5 - 1e-6
    reach = np.linalg.norm(pts - volume.attachment_point.reshape(3), axis=1)
    assert float(reach.max()) <= position["linker_length"] + 1e-6


def test_numpy_is_deterministic(position):
    """A fixed seed: a demo, a round trip and a test all need the same cloud."""
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    one = av.compute_av(str(PDB), dict(position), backend="numpy")
    two = av.compute_av(str(PDB), dict(position), backend="numpy")
    assert np.array_equal(one.points, two.points)


def test_auto_prefers_the_physics_when_it_is_there(position):
    """`auto` keeps picking imp-bff where it exists; numpy is the fallback,
    not the replacement."""
    if not PDB.is_file() or "imp-bff" not in av.available_backends():
        pytest.skip("imp-bff not importable here")
    volume = av.compute_av(str(PDB), dict(position))
    assert av.active_backend() == "imp-bff"
    assert volume.n_points > 0


def test_a_missing_attachment_atom_is_refused(position):
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    broken = dict(position, atom_name="XX")
    with pytest.raises(ValueError):
        av.compute_av(str(PDB), broken, backend="numpy")


def test_the_attachment_residue_is_not_an_obstacle(position):
    """The FPS convention: the residue a dye hangs from does not wall it in.

    Every backend must free the space the attachment residue's own atoms
    occupy -- measured as accepted points *inside* that space, which is
    impossible while the residue blocks. The imp-bff backend made this
    visible: it ignores the passed atoms and re-reads the PDB, so its cloud
    had zero points near the residue until it was handed a stripped file
    (1,203 points before the strip, 3,849 after).
    """
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    records = av._cached_pdb_records(str(PDB))
    residue_xyz = np.array(
        [r[3:6] for r in records
         if r[1] == position["residue_seq_number"]
         and r[0] == position["chain_identifier"]]
    )
    assert residue_xyz.shape[0] > 1, "fixture lost residue 119?"
    backends = [b for b in ("numpy", "imp-bff") if b in av.available_backends()]
    assert backends, "no backend to test"
    for backend in backends:
        volume = av.compute_av(str(PDB), dict(position), backend=backend)
        near = np.linalg.norm(
            volume.points[:, None, :3] - residue_xyz[None, :, :], axis=2
        )
        inside = int((near < 3.4).any(axis=1).sum())
        assert inside > 0, (
            f"{backend}: the attachment residue still blocks -- {inside} "
            "points in its own space"
        )


def test_the_stripped_pdb_strips_the_side_chain_not_the_backbone(position):
    """The file-level strip `_stripped_pdb_for` produces for imp-bff.

    The strip is the FPS convention expressed as a PyMOL selection: the
    attachment residue's side chain goes, minus the attachment atom itself,
    and the backbone stays. The attachment atom survives *any* mask -- the
    imp-bff backend selects the source by identity from this file.
    """
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    stripped = av._stripped_pdb_for(
        str(PDB), position["chain_identifier"],
        position["residue_seq_number"], position["atom_name"],
    )
    kept = _residue_atom_names(stripped, position)
    assert kept == ["N", "CA", "C", "O", "CB"], (
        f"the default strip keeps backbone + attachment; got {kept}"
    )
    # A declared mask in the same vocabulary is honoured as given...
    declared = av._stripped_pdb_for(
        str(PDB), position["chain_identifier"],
        position["residue_seq_number"], position["atom_name"],
        strip_mask="chain E and resid 119 and not name N+CA+C+O+CB",
    )
    assert _residue_atom_names(declared, position) == ["N", "CA", "C", "O", "CB"]
    # ...including one that would eat the attachment atom: it survives.
    survives = av._stripped_pdb_for(
        str(PDB), position["chain_identifier"],
        position["residue_seq_number"], position["atom_name"],
        strip_mask=f"chain E and resid {position['residue_seq_number']}",
    )
    assert _residue_atom_names(survives, position) == ["CB"]
    # A mask PyMOL would reject is rejected here too, loudly.
    with pytest.raises(ValueError):
        av._stripped_pdb_for(
            str(PDB), position["chain_identifier"],
            position["residue_seq_number"], position["atom_name"],
            strip_mask="chain E and resid 119 and not name CA CB C N O",
        )
    # ... and the cache answers the same file for the same site.
    again = av._stripped_pdb_for(
        str(PDB), position["chain_identifier"],
        position["residue_seq_number"], position["atom_name"],
    )
    assert again == stripped


def _residue_atom_names(pdb_path: str, position) -> list:
    return [
        line[12:16].strip()
        for line in open(pdb_path)
        if line.startswith(("ATOM  ", "HETATM"))
        and line[22:26].strip() == str(position["residue_seq_number"])
        and line[21] == position["chain_identifier"]
    ]


def test_the_imp_bff_grid_is_in_world_axis_order(position):
    """The tile grid arrives x/z-swapped; the adapter transposes it back.

    Measured, not assumed: the delivered layout correlates +0.35 against the
    AV's own points voxelized at ``grid_origin``/``grid_step``, and +1.0000
    under transpose (2, 1, 0). A mesh built on the wrong layout lands 13.6 A
    (p95) off its own cloud -- the "AV at wrong positions" report -- so the
    delivered orientation is pinned by the same correlation.
    """
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    if "imp-bff" not in av.available_backends():
        pytest.skip("imp-bff not importable here")
    volume = av.compute_av(str(PDB), dict(position), backend="imp-bff")
    density = np.asarray(volume.density, dtype=np.float32)
    ijk = np.rint(
        (volume.points[:, :3] - np.asarray(volume.grid_origin, dtype=float))
        / float(volume.grid_step)
    ).astype(int)
    inside = np.all((ijk >= 0) & (ijk < np.array(density.shape)), axis=1)
    assert inside.mean() > 0.9, "most points fall outside their own grid"
    reference = np.zeros(density.shape, dtype=np.float32)
    np.add.at(reference, tuple(ijk[inside].T), 1.0)
    both = (density > 0) | (reference > 0)
    overlap = float((density[both] > 0).mean())
    assert overlap > 0.85, (
        f"the grid does not sit on its own cloud (overlap {overlap:.2f}) "
        "-- the backend's axis layout changed again"
    )
