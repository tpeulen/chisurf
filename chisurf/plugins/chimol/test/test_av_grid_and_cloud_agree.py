"""An AV's grid and its cloud are one distribution described twice.

An accessible volume is drawn twice over: the samples as a point cloud, the
density as a contoured surface (``Viewer.add_av`` hands it to the same volume
machinery a map gets). So the two disagreeing is not an internal detail -- it
is a dye shell floating 11 A away from its own dye, which is what
``test_av_display`` was measuring when it failed.

The cause was a compensation. IMP.bff once returned its tiles x/z-swapped, a
``transpose(2, 1, 0)`` was measured and hard-coded at that seam, the library
was fixed upstream, and the compensation silently became the fault it had been
correcting. Nothing noticed, because the two descriptions were never compared
-- each backend adapter was trusted to deliver them consistent, and three of
the four also carried their own hand-rolled copy of "the grid of these points",
with their own rounding.

So there is one derivation (``_voxelise``), one inverse (``_cloud_from_grid``),
and one check: when a backend supplies both, ``AccessibleVolume`` verifies that
the grid accounts for the samples and rebuilds it from them if it does not.
What is pinned here is that invariant -- for every backend that can run, and
for a fabricated backend that gets it wrong on purpose, since the real ones are
(now) right and a test that only asks them proves nothing about the next
change.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from chimol.plugins.labelling import av
from chimol.plugins.labelling.av import AccessibleVolume

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
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


def _accounted(volume) -> float:
    """The fraction of the cloud that lands in an occupied voxel of its grid."""
    density = np.asarray(volume.density)
    ijk = np.rint(
        (volume.points[:, :3] - np.asarray(volume.grid_origin, dtype=float))
        / float(volume.grid_step)
    ).astype(int)
    inside = np.all((ijk >= 0) & (ijk < np.asarray(density.shape)), axis=1)
    hit = np.zeros(len(ijk), dtype=bool)
    hit[inside] = density[tuple(ijk[inside].T)] > 0.0
    return float(hit.mean())


@pytest.mark.parametrize("backend", ["imp-bff", "labellib", "numpy"])
def test_each_backend_delivers_a_grid_that_holds_its_own_cloud(backend):
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    if backend not in av.available_backends():
        pytest.skip(f"{backend} not importable here")
    volume = av.compute_av(str(PDB), dict(POSITION), backend=backend)
    assert volume.n_points > 100, "the backend produced no cloud to check"
    assert _accounted(volume) > 0.99, (
        f"{backend}: the grid does not describe its own samples "
        f"(accounted {_accounted(volume):.3f}) -- an axis order, a reshape "
        "order or an origin convention changed"
    )


@pytest.mark.parametrize("backend", ["imp-bff", "labellib", "numpy"])
def test_no_backend_reports_a_negative_density(backend):
    """LabelLib marks obstacles in the array it puts dye weight in."""
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    if backend not in av.available_backends():
        pytest.skip(f"{backend} not importable here")
    density = np.asarray(av.compute_av(str(PDB), dict(POSITION), backend=backend).density)
    assert float(density.min()) >= 0.0, (
        "a negative value reached the array that gets contoured as a density"
    )


# --------------------------------------------------------------------------- #
# The invariant itself, without a backend
# --------------------------------------------------------------------------- #
def _cloud(n: int = 400, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    xyz = rng.normal(scale=4.0, size=(n, 3)) + np.array([10.0, 20.0, 30.0])
    return np.column_stack([xyz, np.ones(n)])


def test_a_transposed_grid_is_repaired():
    """The exact shape of the bug: a grid that no longer matches its samples."""
    good = AccessibleVolume(points=_cloud(), grid_step=1.5)
    assert _accounted(good) == 1.0

    wrong = AccessibleVolume(
        points=good.points,
        density=np.transpose(good.density, (2, 1, 0)).copy(),
        grid_origin=good.grid_origin,
        grid_step=good.grid_step,
    )
    assert _accounted(wrong) > 0.99, "a transposed grid was accepted as delivered"


def test_a_grid_and_no_samples_gives_a_cloud():
    """LabelLib fills a grid; everything downstream reads the points."""
    seed = AccessibleVolume(points=_cloud(), grid_step=1.5)
    from_grid = AccessibleVolume(
        points=None,
        density=seed.density,
        grid_origin=seed.grid_origin,
        grid_step=seed.grid_step,
    )
    assert from_grid.n_points > 0
    assert _accounted(from_grid) == 1.0
    # ...and it describes the same distribution it was built from.
    assert np.allclose(from_grid.mean_position, seed.mean_position, atol=1.5)


def test_samples_and_no_grid_gives_a_grid():
    """The numpy fallback and the rotamer models both hand over only points."""
    volume = AccessibleVolume(points=_cloud(), grid_step=1.5)
    assert np.asarray(volume.density).ndim == 3
    assert np.asarray(volume.density).sum() > 0
    assert _accounted(volume) == 1.0


def test_the_shape_is_the_arrays_shape():
    """Not a second stored truth: the transpose updated one and not the other."""
    volume = AccessibleVolume(
        points=_cloud(), grid_step=1.5, grid_shape=(1, 1, 1)
    )  # a lie, on purpose
    assert tuple(volume.grid_shape) == np.asarray(volume.density).shape


def test_a_cloud_written_in_columns_is_read_as_one():
    """LabelLib returns ``(4, N)``; read as ``(N, 4)`` that is four samples."""
    cloud = _cloud(n=500)
    columns = AccessibleVolume(points=cloud.T.copy(), grid_step=1.5)
    assert columns.n_points == 500
    assert np.allclose(
        columns.mean_position, AccessibleVolume(points=cloud, grid_step=1.5).mean_position
    )


def test_an_empty_av_is_still_a_valid_one():
    """A site walled in by its own neighbourhood: no samples, and no crash."""
    volume = AccessibleVolume(
        points=np.zeros((0, 4)), grid_step=1.5, attachment_point=np.array([1.0, 2.0, 3.0])
    )
    assert volume.n_points == 0 and not volume.has_volume
    assert np.asarray(volume.density).ndim == 3
    assert np.allclose(volume.mean_position, [1.0, 2.0, 3.0])
