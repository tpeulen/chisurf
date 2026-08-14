"""The nucleic trace must be drawn on the atoms it traces.

Reported as: "the backbone of the nucleic acid is offset, thus it looks like
there are sticks sticking out of the backbone". The sticks were the base
connectors, drawn correctly to the real sugar while the tube ran somewhere else.

The cause is a category error rather than an arithmetic one. PyMOL's
``RepCartoonSmoothLoops`` averages control points, and it is applied to *loops*
-- because a moving average over points on a HELIX is not a smoothing but a
contraction toward the helix axis. A duplex C4' trace is a helix of radius ~9 A,
and the shipped default ran two passes of it, displacing the trace a measured
1.68 A (max 2.43 A) against a tube radius of 0.4 -- roughly four radii.

These tests measure the displacement on real B-form DNA (1RTD carries a
DNA/RNA duplex) rather than on a synthetic strand, because the size of the error
is the whole point, and because it depends on the *pitch of the real helix* in a
way no synthetic strand reproduces. It is sharply window-sensitive too: the same
structure goes from 2.4 A at the shipped ``window=1`` to 8.3 A at ``window=3``,
so a half-width that reads like a quality knob is really a displacement knob.

The companion render test could not catch this: it pinned
``backbone_smooth_cycles`` to 0 in its config while the shipped default was 2,
so it rendered a configuration nobody ran.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[4]
PDB = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "1rtd.pdb"
DISPLAY_JSON = (
    REPO / "chisurf" / "plugins" / "chimol" / "chimol" / "chimol_display.json"
)


def _read_structure():
    """1RTD, read once for the module.

    ``radii="vdw"`` deliberately: the CHARMM path types every atom and spends
    most of its time warning about the nucleotide ligand, which this test does
    not look at.
    """
    from chisurf.core.fio.structure.coordinates import read_coordinates

    out = read_coordinates(str(PDB), radii="vdw")
    return out[0] if isinstance(out, tuple) else out


def _duplex_traces(atoms) -> list[np.ndarray]:
    """The C4' trace of every nucleic chain, longest first."""
    names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    chains = np.asarray(atoms["chain"]).astype(str)
    xyz = np.asarray(atoms["xyz"], dtype=float)

    mask = np.isin(names, ["C4'", "C4*"])
    traces = []
    for chain in sorted(set(chains[mask])):
        selected = mask & (chains == chain)
        if int(selected.sum()) >= 8:
            traces.append(xyz[selected])
    return sorted(traces, key=len, reverse=True)


@pytest.fixture(scope="module")
def structure():
    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    return _read_structure()


@pytest.fixture(scope="module")
def traces(structure):
    found = _duplex_traces(structure)
    if not found:
        pytest.skip("no nucleic chain in the fixture")
    return found


def test_averaging_a_helix_contracts_it(traces):
    """The mechanism, measured -- this is *why* the default is off.

    Not a regression guard: if this ever stops being true the smoothing has
    changed meaning, and the default should be revisited rather than the number
    here adjusted.
    """
    from chimol.geometry.cartoon import (
        _smooth_backbone_points,
    )

    worst = 0.0
    for trace in traces:
        smoothed = _smooth_backbone_points(trace, cycles=2, window=1)
        worst = max(worst, float(np.linalg.norm(smoothed - trace, axis=1).max()))
    # 2.43 A measured; the bound is loose because the exact figure belongs to
    # this structure's pitch, while the sign and the scale are what matter.
    assert worst > 1.5, (
        f"expected a helix to contract under averaging, saw {worst:.2f} A"
    )


def test_the_shipped_default_leaves_the_trace_on_the_atoms(traces):
    """The defect, at the shipped setting.

    The tube radius is 0.4, so anything approaching an Angstrom of displacement
    already detaches the base connectors that start on the curve.
    """
    from chimol.geometry.cartoon import (
        _smooth_backbone_points,
    )

    config = json.loads(DISPLAY_JSON.read_text())
    section = config.get("cartoon", config)
    cycles = int(section.get("nucleic_smooth_cycles", 0))
    window = int(section.get("backbone_smooth_window", 1))

    for trace in traces:
        smoothed = _smooth_backbone_points(trace, cycles=cycles, window=window)
        offset = float(np.linalg.norm(smoothed - trace, axis=1).max())
        assert offset < 0.4, (
            f"shipped nucleic smoothing moves the trace {offset:.2f} A off the "
            f"C4' atoms (cycles={cycles}, window={window})"
        )


def _nucleic_chain_inputs(atoms):
    """(sub-array, coords, res_ids, chain_ids, colors) for one nucleic chain."""
    names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    chains = np.asarray(atoms["chain"]).astype(str)

    nucleic = np.isin(names, ["C4'", "C4*"])
    if not np.any(nucleic):
        return None
    keep_chain = sorted(set(chains[nucleic]))[0]
    selected = chains == keep_chain
    if not np.any(selected & nucleic):
        return None

    sub = atoms[selected]
    coords = np.asarray(sub["xyz"], dtype=float)
    res_ids = np.unique(np.asarray(sub["res_id"]))
    chain_ids = np.array([keep_chain] * len(res_ids))
    colors = np.tile(np.array([1.0, 1.0, 1.0, 1.0]), (len(res_ids), 1))
    return sub, coords, res_ids, chain_ids, colors


@pytest.mark.parametrize("cycles", [0, 2])
def test_the_base_connectors_are_drawn(structure, cycles):
    """Every base is connected to the trace, at any smoothing setting.

    The rungs are *collected* while the residues are walked and *drawn* after
    the trace is smoothed -- the two halves live in different loops, and
    nothing here asserted the second half ran. It did not: the drawing block
    was written into the protein tube builder instead, where its names do not
    exist, so nucleic acids lost their base connectors while `cartoon` on any
    protein with secondary structure raised ``NameError: rungs``.

    Measured at C1', which each rung routes through and caps with a sphere of
    ``ladder_radius`` (0.12). Without the rungs the nearest geometry is the
    base ring, ~1.5 A away across the glycosidic bond, so the threshold
    separates the two cases by an order of magnitude rather than by a margin.

    Parametrised over smoothing because the anchoring is what couples the two
    halves: a rung starts on the array the tube is swept along, so turning
    smoothing on must move the start, never drop the rung.
    """
    from chimol.geometry import cartoon

    inputs = _nucleic_chain_inputs(structure)
    if inputs is None:
        pytest.skip("no nucleic chain selected")
    sub, coords, res_ids, chain_ids, colors = inputs

    result = cartoon._generate_nucleic_cartoon_arrays(
        sub, coords, res_ids, chain_ids, colors,
        config={
            "coordinate_scale": 1.0,
            "nucleic_ao_strength": 0.0,
            "nucleic_smooth_cycles": cycles,
        },
    )
    assert result is not None, "no nucleic cartoon was generated"
    verts = np.asarray(result[0], dtype=float)

    names = np.char.strip(np.asarray(sub["atom_name"]).astype(str))
    sugar = coords[np.isin(names, ["C1'", "C1*"])]
    assert len(sugar) >= 4, "fixture has too few sugars to measure"

    gaps = np.array([
        float(np.linalg.norm(verts - point, axis=1).min()) for point in sugar
    ])
    assert gaps.max() < 0.5, (
        f"{int((gaps >= 0.5).sum())}/{len(gaps)} bases have no connector to the "
        f"trace (worst gap {gaps.max():.2f} A at cycles={cycles})"
    )


def test_the_mesh_is_built_around_the_atoms(structure):
    """End to end: every trace atom has tube surface near it.

    A weaker statement than it looks -- the base connectors also put geometry
    near the sugar -- so it is here to catch a gross regression in the builder,
    with the two measurements above carrying the actual contract.
    """
    from chimol.geometry import cartoon

    atoms = structure
    names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    chains = np.asarray(atoms["chain"]).astype(str)

    nucleic = np.isin(names, ["C4'", "C4*"])
    keep_chain = sorted(set(chains[nucleic]))[0]
    selected = chains == keep_chain
    if not np.any(selected & nucleic):
        pytest.skip("no nucleic chain selected")

    sub = atoms[selected]
    coords = np.asarray(sub["xyz"], dtype=float)
    res_ids = np.unique(np.asarray(sub["res_id"]))
    chain_ids = np.array([keep_chain] * len(res_ids))
    colors = np.tile(np.array([1.0, 1.0, 1.0, 1.0]), (len(res_ids), 1))

    result = cartoon._generate_nucleic_cartoon_arrays(
        sub, coords, res_ids, chain_ids, colors,
        config={"coordinate_scale": 1.0, "nucleic_ao_strength": 0.0},
    )
    assert result is not None, "no nucleic cartoon was generated"
    verts = np.asarray(result[0], dtype=float)
    assert len(verts) > 0

    trace = coords[np.isin(np.char.strip(np.asarray(sub["atom_name"]).astype(str)),
                           ["C4'", "C4*"])]
    gaps = np.array([
        float(np.linalg.norm(verts - point, axis=1).min()) for point in trace
    ])
    assert gaps.max() < 2.0, (
        f"no cartoon geometry within 2 A of a trace atom (worst "
        f"{gaps.max():.2f} A) -- the tube is not where the chain is"
    )
