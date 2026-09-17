"""Dye models are a registry: AV1/AV3 (the backends) and rotamer libraries (explicit conformers).

A rotamer library is a multi-MODEL PDB of dye+linker conformers with three
anchor atoms the residue also has (SG CB CA for a cysteine dye); every
conformer is superposed onto the residue's anchors, kept if it does not clash
with the protein, and the fluorophore positions of the survivors are the
distribution -- an AccessibleVolume like any other, so the object, the mean
bead, distances and fps.json all follow. ``add_dye <sele>, rotamer <lib.pdb>``
and the wizard's dye menu reach it.
"""

from __future__ import annotations

import pathlib

import chimol
import numpy as np
import pytest
from chimol.plugins.labelling.dyes import parse_dye_spec
from chimol.plugins.labelling.models import (
    DYE_MODELS,
    DyeModel,
    load_rotamer_library,
    register_model,
    rotamer_positions,
    unregister_models,
)

_PDB = pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos" / "148l.pdb"


def _write_library(path: pathlib.Path, n: int = 24, reach: float = 8.0) -> None:
    """A fan of conformers: anchors SG/CB/CA at a fixed triad, a fluorophore F swung around."""
    lines = []
    sg, cb, ca = np.array([0.0, 0.0, 0.0]), np.array([1.8, 0.0, 0.0]), np.array([2.5, 1.4, 0.0])
    for i in range(n):
        a = 2 * np.pi * i / n
        # some conformers reach back "into" the CA direction (they will clash with a protein)
        f = sg + reach * np.array([-np.cos(a) * 0.3, np.sin(a), np.cos(a)])
        lines.append(f"MODEL     {i + 1}")
        lines.append(f"REMARK weight {1.0 + (i % 3)}")
        for j, (name, xyz) in enumerate((("SG", sg), ("CB", cb), ("CA", ca), ("F", f)), start=1):
            lines.append(
                "HETATM%5d %-4s DYE A   1    %8.3f%8.3f%8.3f  1.00  0.00           %s"
                % (j, name, xyz[0], xyz[1], xyz[2], "S" if name == "SG" else "C")
            )
        lines.append("ENDMDL")
    path.write_text("\n".join(lines) + "\n")


def test_the_grammar_knows_the_models():
    assert set(DYE_MODELS) >= {"AV1", "AV3", "ROTAMER"}
    p = parse_dye_spec("rotamer lib.pdb 3.2")
    assert p == {"simulation_type": "ROTAMER", "rotamer_library": "lib.pdb", "clash_distance": 3.2}
    p = parse_dye_spec(
        "rotamer_library=lib.pdb simulation_type=rotamer anchor_atoms=SG,CB,CA fluorophore_atom=F"
    )
    assert p["anchor_atoms"] == "SG,CB,CA" and p["fluorophore_atom"] == "F"
    assert parse_dye_spec("Cy5")["simulation_type"] == "AV1"


def test_a_library_loads_and_conformers_are_placed_and_clash_filtered(tmp_path):
    lib_path = tmp_path / "dye.pdb"
    _write_library(lib_path)
    lib = load_rotamer_library(lib_path)
    assert lib.n_conformers == 24 and lib.atom_names == ["SG", "CB", "CA", "F"]
    assert lib.weights.tolist()[:3] == [1.0, 2.0, 3.0]

    # a "protein": the residue's triad somewhere else in space, plus a wall of atoms on one side
    R = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float)  # a rotation
    t = np.array([10.0, 20.0, 30.0])
    res = (lib.coords[0][:3] @ R.T) + t
    wall = np.array([[10.0, 20.0, 30.0 + z] for z in np.linspace(3, 9, 7)]) + np.array([0, -1.5, 0])
    xyz = np.vstack([res, wall])
    names = np.array(["SG", "CB", "CA"] + ["O"] * len(wall))
    mask = np.array([True, True, True] + [False] * len(wall))
    pos, w, kept = rotamer_positions(
        xyz, names, mask, lib, ("SG", "CB", "CA"), fluorophore_atom="F", clash_distance=3.0
    )
    assert 0 < len(kept) < lib.n_conformers, "the wall must reject some conformers and not all"
    # a rigid superposition: each placed fluorophore keeps its distance to the SG
    d = np.linalg.norm(pos - res[0], axis=1)
    own = np.linalg.norm(lib.coords[kept, 3] - lib.coords[kept, 0], axis=1)
    assert np.allclose(d, own, atol=1e-6)
    assert w.tolist() == [lib.weights[i] for i in kept]


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_add_dye_with_a_rotamer_library_makes_an_av_object(qapp, tmp_path):
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.viewport.headless import SceneSink

    lib_path = tmp_path / "dye.pdb"
    _write_library(lib_path, reach=6.0)
    viewer = Viewer(renderer_factory=SceneSink)
    host = ViewerHost(viewer)
    cmd = Cmd(None)
    host.cmd = cmd
    cmd.set_window(host)
    errors: list[str] = []
    said: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.set_message_callback(said.append)
    cmd.do(f'load "{_PDB}"')
    cmd.do("mutate resi 119, CYS")  # SG, CB, CA to anchor on
    n_before = len(viewer.objects)
    cmd.do(f"add_dye resi 119 and name SG, rotamer {lib_path} fluorophore_atom=F")
    assert errors == [], errors
    assert len(viewer.objects) > n_before, "no AV object was made"
    av_entry = next(e for e in viewer.objects.values() if getattr(e.state, "av", None) is not None)
    av = av_entry.state.av
    assert av.params["simulation_type"] == "ROTAMER"
    assert 0 < av.params["_rotamers_kept"] <= av.params["_rotamers_total"] == 24
    assert av.n_points == av.params["_rotamers_kept"]
    assert np.isfinite(av.mean_position).all()


def test_a_plugin_can_register_a_dye_model():
    def compute(pdb_path, params):
        raise RuntimeError("not called")

    assert register_model(DyeModel("SPHERE", ("radius",), compute, owner="test"))
    try:
        assert parse_dye_spec("sphere 4.0") == {"simulation_type": "SPHERE", "radius": 4.0}
        from chimol.plugins.labelling.wizard import LabellingWizard

        labels = [e.label for e in LabellingWizard().menu("dye")]
        assert any("sphere" in label for label in labels)
    finally:
        unregister_models("test")
    assert "SPHERE" not in DYE_MODELS
