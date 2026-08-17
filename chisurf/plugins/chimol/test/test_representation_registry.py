"""A plugin can add a representation, and ``show``/``hide``/``as`` treat it as a built-in.

The registry (``chimol.core.representations``) is the plugin door into the
scene: a ``RepresentationSpec`` with a builder; the viewer keeps a per-object
``RepState`` (visible + atom mask); the commands scope it like a built-in.
Pinned here: geometry appears in the scene when shown, disappears when hidden,
``show rep, sele`` narrows it to the selection's atoms, ``hide everything``
takes it down, and unloading the plugin removes the name.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

import chimol
from chimol.core.representations import REPRESENTATIONS, BuildContext, RepresentationSpec
from chimol.plugins import load_plugins
from chimol.render.scene import Geometry, Material, SceneObject

_PDB = str(pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos" / "148l.pdb")


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _atom_stars(ctx: BuildContext):
    """A star (point) at every atom in scope: the simplest possible representation."""
    xyz = ctx.all_atom_coords
    if xyz is None:
        return []
    keep = ctx.masked()
    if not keep.any():
        return []
    colors = ctx.atom_colors()
    pos = np.asarray(xyz[keep], dtype=np.float32)
    rgba = np.asarray(colors[keep] if colors is not None else np.ones((pos.shape[0], 4)), dtype=np.float32)
    geom = Geometry(kind="points", positions=pos, colors=rgba, radii=np.full(pos.shape[0], 0.3, dtype=np.float32))
    return [SceneObject(id="stars", geometry=geom, material=Material())]


class _StarsPlugin:
    name = "stars"

    def register(self, api):
        api.add_representation(RepresentationSpec(name="stars", build=_atom_stars, aliases=("star",),
                                                  doc="a point per atom"))


class _WindowStub:
    def __init__(self, viewer):
        self.viewer = viewer

    def __getattr__(self, name):
        raise AttributeError(name)


def _viewer_and_cmd(qapp):
    from chimol.commands.command import Cmd
    from chimol.core.viewer import MolView
    from chimol.io.structure import load_structure_payload
    from chimol.render.headless import SceneSink

    viewer = MolView(renderer_factory=SceneSink)
    _structure, payload = load_structure_payload(_PDB)
    viewer.apply_payload(payload)
    cmd = Cmd(None, plugins=False)
    cmd.set_window(_WindowStub(viewer))
    errors: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.set_message_callback(lambda _m: None)
    return viewer, cmd, errors


def _stars_in(viewer):
    scene = getattr(viewer, "_scene", None)
    objs = [o for o in (scene.objects if scene else []) if "stars" in str(o.id)]
    return sum(int(o.geometry.positions.shape[0]) for o in objs)


def test_a_registered_representation_shows_hides_and_scopes(qapp):
    viewer, cmd, errors = _viewer_and_cmd(qapp)
    loaded = load_plugins(cmd, [_StarsPlugin()])
    assert "stars" in REPRESENTATIONS
    try:
        n_atoms = int(viewer._all_atom_coords.shape[0])
        assert _stars_in(viewer) == 0
        cmd.do("show stars")
        assert errors == [], errors
        assert _stars_in(viewer) == n_atoms
        assert viewer.rep_visible("stars")

        cmd.do("hide star, resi 1-100")           # the alias, scoped
        assert errors == [], errors
        shown = _stars_in(viewer)
        assert 0 < shown < n_atoms

        cmd.do("hide stars")
        assert _stars_in(viewer) == 0
        cmd.do("show stars, resi 44")              # scoped show from off: only those atoms
        assert 0 < _stars_in(viewer) < 20
        cmd.do("show stars")
        assert _stars_in(viewer) == n_atoms

        cmd.do("hide everything")                  # takes registered ones down too
        assert _stars_in(viewer) == 0
        cmd.do("as stars")
        assert _stars_in(viewer) == n_atoms
        cmd.do("toggle_rep stars")
        assert _stars_in(viewer) == 0
    finally:
        loaded.unload("stars")
    assert "stars" not in REPRESENTATIONS
    cmd.do("show stars")
    assert errors and "stars" in errors[-1]


def test_a_broken_builder_does_not_take_the_scene_down(qapp):
    def boom(ctx):
        raise RuntimeError("no")

    class _Bad:
        name = "bad"

        def register(self, api):
            api.add_representation(RepresentationSpec(name="boom", build=boom))

    viewer, cmd, errors = _viewer_and_cmd(qapp)
    loaded = load_plugins(cmd, [_Bad()])
    try:
        cmd.do("show cartoon")
        cmd.do("show boom")
        scene = viewer._scene
        assert scene is not None and scene.objects, "the built-ins must still draw"
        assert not any("boom" in str(o.id) for o in scene.objects)
    finally:
        loaded.unload("bad")


def test_the_first_owner_keeps_a_name():
    spec = RepresentationSpec(name="cartoon_x", build=lambda ctx: [])
    assert REPRESENTATIONS.register(spec, owner="t1")
    try:
        assert not REPRESENTATIONS.register(spec, owner="t2")
        assert REPRESENTATIONS.get("cartoon_x") is spec
    finally:
        REPRESENTATIONS.unregister_owner("t1")
        REPRESENTATIONS.unregister_owner("t2")
    assert "cartoon_x" not in REPRESENTATIONS
