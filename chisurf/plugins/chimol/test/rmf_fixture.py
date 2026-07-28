"""Write a small multi-resolution RMF, so the reader can be tested on a real one.

No ``.rmf`` file exists in this repository and none should: a checked-in binary
is a provenance question and cannot be varied per test. RMF can write as well as
read, so the fixture is *made* -- which also means the file's shape is stated in
Python next to the test that depends on it, rather than being an opaque blob
whose contents have to be taken on trust.

The shape written here is the one an IMP model has: molecules in several copies,
each represented at a fine resolution *and* at a coarse one hung off the same
node as an ``Alternatives`` representation. That is what makes a resolution
chooser necessary, and it is exactly the structure a synthetic payload dict
cannot exercise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:  # pragma: no cover - exercised by the skip marker
    import RMF
except ImportError:  # pragma: no cover
    RMF = None


#: Resolutions written into the fixture, fine first. "Resolution" in IMP is
#: residues per bead, so a *larger* number is a coarser depiction.
FINE_RESOLUTION = 1.0
COARSE_RESOLUTION = 10.0


def write_multiresolution_rmf(
    path: Path,
    *,
    n_molecules: int = 2,
    n_copies: int = 2,
    n_fine: int = 10,
    n_coarse: int = 2,
    n_frames: int = 3,
    seed: int = 0,
) -> dict:
    """Write an RMF with two resolutions per molecule copy.

    Parameters
    ----------
    path : pathlib.Path
        Where to write. The suffix decides the RMF backend; ``.rmf3`` is the
        usual one.
    n_molecules : int
        Distinct molecules, named ``Mol0``, ``Mol1``, ...
    n_copies : int
        Copies of each molecule, as an assembly has.
    n_fine, n_coarse : int
        Particles per copy at the fine and the coarse resolution.
    n_frames : int
        Trajectory frames. Coordinates jitter between them so a frame change is
        observable.
    seed : int
        Seed for the coordinates.

    Returns
    -------
    dict
        What was written: ``n_fine_total``, ``n_coarse_total``, ``n_particles``,
        ``n_frames``, ``molecules``, ``resolutions``. Tests assert against this
        rather than re-deriving the arithmetic.

    Raises
    ------
    RuntimeError
        If the RMF package is not importable.
    """
    if RMF is None:
        raise RuntimeError("writing an RMF fixture requires the 'RMF' package")

    rng = np.random.default_rng(seed)
    fh = RMF.create_rmf_file(str(path))
    fh.add_frame("f0", RMF.FRAME)

    particlef = RMF.ParticleFactory(fh)
    chainf = RMF.ChainFactory(fh)
    copyf = RMF.CopyFactory(fh)
    statef = RMF.StateFactory(fh)
    fragmentf = RMF.FragmentFactory(fh)
    altf = RMF.AlternativesFactory(fh)
    resf = RMF.ExplicitResolutionFactory(fh)

    root = fh.get_root_node()
    state = root.add_child("State_0", RMF.REPRESENTATION)
    statef.get(state).set_state_index(0)

    def _add_particles(parent, count, first_residue, radius):
        """Hang ``count`` beads off ``parent`` and return their nodes.

        Radii *vary* within a representation, because in a real model they do:
        a bead's radius follows how much sequence it covers. A fixture where
        every bead is the same size cannot tell a viewer that keeps per-bead
        radii from one that quietly substitutes a single global size, which is
        precisely the bug this fixture exists to catch.
        """
        nodes = []
        for i in range(count):
            node = parent.add_child(f"bead_{first_residue + i}", RMF.REPRESENTATION)
            fragmentf.get(node).set_residue_indexes(
                list(range(first_residue + i, first_residue + i + 1))
            )
            particle = particlef.get(node)
            own_radius = radius * (0.6 + 0.8 * (i / max(1, count - 1)))
            particle.set_radius(own_radius)
            particle.set_mass(own_radius**3)
            particle.set_coordinates(
                RMF.Vector3(*rng.normal(scale=20.0, size=3).tolist())
            )
            nodes.append(node)
        return nodes

    molecules = []
    n_fine_total = 0
    n_coarse_total = 0
    # Chain ids run across the whole assembly, not within a molecule: two copies
    # of the same molecule legitimately number their residues the same way, and
    # the chain is what tells them apart. A fixture that reuses chain ids across
    # molecules makes every copy look like the same chain, which is a property no
    # real file has and which quietly merges them downstream.
    chain_ids = iter(
        [chr(ord("A") + i) for i in range(26)]
        + [f"{chr(ord('A') + i)}{d}" for d in range(10) for i in range(26)]
    )
    for mol_index in range(n_molecules):
        name = f"Mol{mol_index}"
        molecules.append(name)
        for copy_index in range(n_copies):
            molecule = state.add_child(name, RMF.REPRESENTATION)
            copyf.get(molecule).set_copy_index(copy_index)

            chain_id = next(chain_ids)
            chain = molecule.add_child(chain_id, RMF.REPRESENTATION)
            chainf.get(chain).set_chain_id(chain_id)
            resf.get(chain).set_explicit_resolution(FINE_RESOLUTION)
            _add_particles(chain, n_fine, 1, radius=2.0)
            n_fine_total += n_fine

            # ``n_coarse=0`` writes an ordinary single-representation file, which
            # is what almost every RMF is -- the case that must keep opening
            # exactly as it did, with no chooser offered.
            if n_coarse <= 0:
                continue

            # The coarse depiction of the *same* chain, hung off it as an
            # alternative rather than as more children -- which is what makes it
            # an alternative and not extra matter in the same model.
            coarse = fh.get_root_node().add_child(
                f"{name}_copy{copy_index}_coarse", RMF.REPRESENTATION
            )
            resf.get(coarse).set_explicit_resolution(COARSE_RESOLUTION)
            coarse_chain = coarse.add_child(chain_id, RMF.REPRESENTATION)
            chainf.get(coarse_chain).set_chain_id(chain_id)
            _add_particles(coarse_chain, n_coarse, 1, radius=8.0)
            n_coarse_total += n_coarse
            altf.get(chain).add_alternative(coarse, RMF.PARTICLE)

    # Extra frames, so playback and the frame/atom sync are testable.
    particles = [
        node
        for node in _walk(fh.get_root_node())
        if particlef.get_is(node)
    ]
    for frame in range(1, n_frames):
        fh.add_frame(f"f{frame}", RMF.FRAME)
        for node in particles:
            particle = particlef.get(node)
            xyz = np.asarray(particle.get_coordinates(), dtype=float)
            particle.set_coordinates(
                RMF.Vector3(*(xyz + rng.normal(scale=1.0, size=3)).tolist())
            )

    del fh
    return {
        "n_fine_total": n_fine_total,
        "n_coarse_total": n_coarse_total,
        "n_particles": n_fine_total + n_coarse_total,
        "n_frames": n_frames,
        "molecules": molecules,
        "resolutions": (FINE_RESOLUTION, COARSE_RESOLUTION),
    }


def _walk(node):
    """Yield ``node`` and every node beneath it, depth first."""
    yield node
    for child in node.get_children():
        yield from _walk(child)
