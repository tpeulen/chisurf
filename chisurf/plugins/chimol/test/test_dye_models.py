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
    assert av.conformer_coords is not None
    assert av.conformer_coords.shape[0] == av.params["_rotamers_kept"]
    assert "MODEL     1" in av.rotamer_pdb()

    # The rotamers conformer ensemble is placed into an object with stick representation and frames
    rot_entry = next((e for e in viewer.objects.values() if e.name.endswith("_rotamers")), None)
    assert rot_entry is not None, "rotamers object was not created"
    assert rot_entry.state.show_sticks is True
    assert rot_entry.state.show_cartoon is False
    assert rot_entry.state.frames is not None
    assert rot_entry.state.frames.shape[0] == av.params["_rotamers_kept"]
    assert viewer.get_total_frames() == av.params["_rotamers_kept"]

    # Frame inspection: jumping to frame 2 updates the active rotamer
    cmd.do("frame 2")
    assert viewer.get_current_frame() == 1
    assert rot_entry.state.active_frame == 1

    # Entire AV envelope is visible by default (binary mask contoured at level 0.5)
    assert av_entry.state.volume is not None
    assert av_entry.state.volume.is_binary()
    assert av_entry.state.volume_levels[0]["level"] == 0.5

    out_pdb = tmp_path / "saved_rotamers.pdb"
    cmd.do(f"save_rotamers {av_entry.name}, {out_pdb}")
    assert errors == [], errors
    assert out_pdb.is_file()
    assert "MODEL     1" in out_pdb.read_text()

    # Deleting the AV object cleans up both the mean position bead and the rotamers conformers object
    cmd.do(f"delete {av_entry.name}")
    assert av_entry.object_id not in viewer.objects
    assert rot_entry.object_id not in viewer.objects


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


def test_imp_bff_registered_libraries():
    try:
        from chimol.plugins.labelling.dyes import get_dye, registered_rotamer_libraries

        libs = registered_rotamer_libraries()
        if not libs:
            pytest.skip("IMP.bff rotamer data not available")
        assert "AlexaFluor 488 C1R" in libs
        preset = get_dye("AlexaFluor 488 C1R")
        assert preset is not None
        assert preset.simulation_type == "ROTAMER"
        assert preset.rotamer_library == "AlexaFluor 488 C1R"

        p = parse_dye_spec("AlexaFluor 488 C1R")
        assert p["simulation_type"] == "ROTAMER"
        assert p["rotamer_library"] == "AlexaFluor 488 C1R"

        p = parse_dye_spec("rotamer 'AlexaFluor 488 C1R'")
        assert p["simulation_type"] == "ROTAMER"
        assert p["rotamer_library"] == "AlexaFluor 488 C1R"

        p = parse_dye_spec("rotamer AlexaFluor 488 C1R 2.5")
        assert p["simulation_type"] == "ROTAMER"
        assert p["rotamer_library"] == "AlexaFluor 488 C1R"
        assert p["clash_distance"] == 2.5
    except ImportError:
        pytest.skip("IMP.bff not available")


def test_imp_bff_rotamer_positions_and_attributes():
    try:
        import IMP.bff as bff  # noqa: F401
        from chimol.plugins.labelling.models import compute_positions
    except ImportError:
        pytest.skip("IMP.bff not available")

    params = {
        "simulation_type": "ROTAMER",
        "rotamer_library": "AlexaFluor 488 C1R",
        "chain_identifier": "E",
        "residue_seq_number": 119,
        "atom_name": "CA",
    }
    av = compute_positions(str(_PDB), params)
    assert av.params["simulation_type"] == "ROTAMER"
    assert av.params["rotamer_library"] == "AlexaFluor 488 C1R"
    assert av.params["_rotamers_total"] == 33
    assert av.n_points == 33
    assert np.isfinite(av.mean_position).all()
    assert av.rotamers is not None
    assert av.conformer_coords is not None
    assert av.conformer_coords.shape == (33, 83, 3)
    assert av.orientations is not None
    assert av.orientations.shape == (33, 3)
    pdb_text = av.rotamer_pdb()
    assert "MODEL     1" in pdb_text
    assert "ENDMDL" in pdb_text
    assert "HETATM" in pdb_text


def test_imp_bff_add_dye_and_distance_in_viewer(qapp, tmp_path):
    try:
        import IMP.bff as bff  # noqa: F401
    except ImportError:
        pytest.skip("IMP.bff not available")

    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.plugins.labelling.distance import Distance
    from chimol.viewport.headless import SceneSink

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

    n_before = len(viewer.objects)
    cmd.do("add_dye resi 119 and name CA, rotamer 'AlexaFluor 488 C1R'")
    assert errors == [], errors
    assert len(viewer.objects) > n_before, "no AV object was made"
    assert any("rotamers kept" in s for s in said)

    cmd.do("add_dye resi 127 and name CA, rotamer 'AlexaFluor 594 C1R'")
    assert errors == [], errors

    av_entries = [e for e in viewer.objects.values() if getattr(e.state, "av", None) is not None]
    assert len(av_entries) == 2
    d = Distance("119-127", av_entries[0].state.av, av_entries[1].state.av)
    assert d.rmp > 0.0
    assert d.rda_mean > 0.0
    assert d.rda_mean_e > 0.0

    out_bff_pdb = tmp_path / "saved_bff_rotamers.pdb"
    cmd.do(f"save_rotamers {av_entries[0].name}, {out_bff_pdb}")
    assert errors == [], errors
    assert out_bff_pdb.is_file()
    assert "MODEL     1" in out_bff_pdb.read_text()


def test_switch_model_rotamer_or_av_default(qapp):
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.plugins.labelling.dyes import (
        adapt_dye_model,
        find_av_preset_for_rotamer,
        find_rotamer_library_for_dye,
        parse_dye_spec,
    )
    from chimol.plugins.labelling.wizard import LabellingRunner, LabellingWizard
    from chimol.viewport.headless import SceneSink

    # 1. Spec parsing with default (AV) and explicit switch
    p_default = parse_dye_spec("Alexa488")
    assert p_default["simulation_type"] == "AV1"

    p_rot = parse_dye_spec("Alexa488", model="ROTAMER")
    assert p_rot["simulation_type"] == "ROTAMER"
    assert p_rot["rotamer_library"] == "AlexaFluor 488 C1R"

    p_kw = parse_dye_spec("Cy5 model=rotamer")
    assert p_kw["simulation_type"] == "ROTAMER"
    assert p_kw["rotamer_library"] == "Lumiprobe Cy5 C2R"

    p_mode = parse_dye_spec("Cy5 mode=av")
    assert p_mode["simulation_type"] == "AV1"

    # 2. Dye mapping helpers
    assert find_rotamer_library_for_dye("Alexa488") == "AlexaFluor 488 C1R"
    assert find_rotamer_library_for_dye("Cy5") == "Lumiprobe Cy5 C2R"
    assert find_av_preset_for_rotamer("AlexaFluor 488 C1R") == "Alexa488"
    assert find_av_preset_for_rotamer("Lumiprobe Cy5 C2R") == "Cy5"
    assert adapt_dye_model("Alexa488", "ROTAMER") == "rotamer 'AlexaFluor 488 C1R'"
    assert adapt_dye_model("rotamer 'AlexaFluor 488 C1R'", "AV") == "Alexa488"

    # 3. Wizard default and menu switch
    wiz = LabellingWizard()
    assert wiz.model == "AV"
    assert any("Model: AV (default)" in r.label for r in wiz.panel())
    model_menu = wiz.menu("model")
    assert len(model_menu) == 2
    assert any("AV (accessible volume, default)" in m.label for m in model_menu)
    assert any("Rotamer (conformer ensemble)" in m.label for m in model_menu)

    # In AV mode, dye menu contains AV presets and not rotamers
    dye_menu_av = wiz.menu("dye")
    assert any(m.label == "Alexa488" for m in dye_menu_av)
    assert not any("rotamer" in (m.command or "") for m in dye_menu_av)

    # Switch wizard to rotamer mode
    wiz.model = "ROTAMER"
    assert any("Model: Rotamer" in r.label for r in wiz.panel())
    dye_menu_rot = wiz.menu("dye")
    assert any(m.label == "AlexaFluor 488 C1R" for m in dye_menu_rot)

    # 4. Interactive runner action and add_dye command switch
    viewer = Viewer(renderer_factory=SceneSink)
    host = ViewerHost(viewer)
    cmd = Cmd(None)
    host.cmd = cmd
    cmd.set_window(host)
    errors: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.do(f'load "{_PDB}"')

    runner = LabellingRunner()
    runner.start(cmd, viewer)
    assert runner.model == "AV"
    runner.action(cmd, viewer, "dye", "Alexa488")
    assert runner.dye == "Alexa488"
    # Switch to rotamer: dye adapts
    runner.action(cmd, viewer, "model", "ROTAMER")
    assert runner.model == "ROTAMER"
    assert runner.dye == "rotamer 'AlexaFluor 488 C1R'"
    # Switch back to AV: dye adapts
    runner.action(cmd, viewer, "model", "AV")
    assert runner.model == "AV"
    assert runner.dye == "Alexa488"

    # Test add_dye with default model (AV) vs model=rotamer
    cmd.do("add_dye resi 119 and name CA, Alexa488")
    assert errors == [], errors
    av_default = next(
        e.state.av for e in viewer.objects.values() if getattr(e.state, "av", None) is not None
    )
    assert av_default.params["simulation_type"] == "AV1"

    cmd.do("add_dye resi 127 and name CA, Alexa488, model=rotamer")
    assert errors == [], errors
    av_rot = [
        e.state.av for e in viewer.objects.values() if getattr(e.state, "av", None) is not None
    ][-1]
    assert av_rot.params["simulation_type"] == "ROTAMER"
    assert av_rot.params["rotamer_library"] == "AlexaFluor 488 C1R"

    # Rotamers object created with sticks and multi-frame trajectory
    rot_obj = next(
        (e for e in viewer.objects.values() if "127" in e.name and e.name.endswith("_rotamers")),
        None,
    )
    assert rot_obj is not None
    assert rot_obj.state.show_sticks is True
    assert rot_obj.state.frames.shape[0] == av_rot.conformer_coords.shape[0]

    # Inspection across frames
    cmd.do("frame 2")
    assert viewer.get_current_frame() == 1
    assert rot_obj.state.active_frame == 1
    cmd.do("frame +1")
    assert viewer.get_current_frame() == 2
    assert rot_obj.state.active_frame == 2

    # Entire AV envelope is visible by default
    av_entry_rot = [e for e in viewer.objects.values() if getattr(e.state, "av", None) is not None][
        -1
    ]
    assert av_entry_rot.state.volume.is_binary()
    assert av_entry_rot.state.volume_levels[0]["level"] == 0.5
