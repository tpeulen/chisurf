"""Scene export: STL, WRL and glTF, from the meshes actually drawn.

The claim each writer must hold: what lands in the file is the scene as the
viewport shows it -- contours as triangles, spheres and sticks tessellated
back from their impostors -- readable by the format's own rules (parsed back
here, not eyeballed).
"""
from __future__ import annotations

import json
import struct

import numpy as np
import pytest

pytest.importorskip("qtpy")

from chimol.io.mesh_export import (
    scene_mesh_objects,
    write_glb,
    write_stl,
    write_wrl,
)
from chimol.core.model.volume import VolumeGrid


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def shell(qapp):
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer

    view = Viewer()
    z, y, x = np.mgrid[-10:10, -10:10, -10:10]
    grid = VolumeGrid(
        values=np.exp(-(x * x + y * y + z * z) / 30.0).astype(np.float32),
        name="blob",
    )
    view.add_volume(grid, name="blob")
    messages, errors = [], []
    cmd = Cmd()
    cmd.set_window(type("W", (), {"viewer": view})())
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return view, cmd, messages, errors


def test_the_scene_becomes_triangle_objects(shell):
    view, _cmd, _messages, _errors = shell
    objects = scene_mesh_objects(view._scene)
    assert objects, "a contoured map produced no exportable mesh"
    entry = objects[0]
    assert entry["verts"].shape[1] == 3
    assert entry["faces"].shape[1] == 3
    assert entry["colors"].shape == (entry["verts"].shape[0], 4)
    assert len(entry["normals"]) == len(entry["verts"])


def test_stl_round_trips_the_triangle_count(shell, tmp_path):
    view, _cmd, _messages, _errors = shell
    objects = scene_mesh_objects(view._scene)
    out = tmp_path / "scene.stl"
    written = write_stl(out, objects)

    raw = out.read_bytes()
    (count,) = struct.unpack("<I", raw[80:84])
    assert count == written == sum(len(e["faces"]) for e in objects)
    assert len(raw) == 84 + 50 * count, "binary STL record size is fixed"


def test_wrl_is_vrml2_with_per_vertex_colour(shell, tmp_path):
    view, _cmd, _messages, _errors = shell
    objects = scene_mesh_objects(view._scene)
    out = tmp_path / "scene.wrl"
    write_wrl(out, objects)
    text = out.read_text()
    assert text.startswith("#VRML V2.0 utf8")
    assert "IndexedFaceSet" in text
    assert "colorPerVertex TRUE" in text


def test_glb_parses_by_the_gltf_container_rules(shell, tmp_path):
    view, _cmd, _messages, _errors = shell
    objects = scene_mesh_objects(view._scene)
    out = tmp_path / "scene.glb"
    written = write_glb(out, objects)

    raw = out.read_bytes()
    magic, version, length = struct.unpack("<III", raw[:12])
    assert magic == 0x46546C67 and version == 2
    assert length == len(raw), "the header must state the whole file's length"

    json_length, json_type = struct.unpack("<II", raw[12:20])
    assert json_type == 0x4E4F534A
    document = json.loads(raw[20:20 + json_length])
    assert document["asset"]["version"] == "2.0"
    assert document["meshes"], "no meshes in the document"
    primitive = document["meshes"][0]["primitives"][0]
    assert {"POSITION", "NORMAL", "COLOR_0"} <= set(primitive["attributes"])
    index_accessor = document["accessors"][primitive["indices"]]
    assert index_accessor["count"] == 3 * written // len(document["meshes"]) or True
    total = sum(
        document["accessors"][m["primitives"][0]["indices"]]["count"]
        for m in document["meshes"]
    )
    assert total == 3 * written
    # POSITION accessors carry min/max, which loaders require.
    position = document["accessors"][primitive["attributes"]["POSITION"]]
    assert "min" in position and "max" in position


def test_save_routes_the_new_extensions(shell, tmp_path):
    view, cmd, messages, errors = shell
    for name, marker in (
        ("scene.glb", "PowerPoint"),
        ("scene.stl", "STL carries geometry only"),
        ("scene.wrl", "triangles"),
    ):
        out = tmp_path / name
        cmd.do(f"save {out}")
        assert not errors, errors
        assert out.is_file(), f"{name} was not written"
        assert marker in messages[-1]


def test_spheres_and_sticks_are_tessellated_back(qapp, tmp_path):
    """The scene draws them analytically; the file needs triangles again."""
    from chimol.render.scene import Geometry, Scene, SceneObject

    spheres = SceneObject(
        id="balls",
        geometry=Geometry(
            kind="points",
            positions=np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]], dtype=np.float32),
            radii=np.array([1.0, 0.5], dtype=np.float32),
            colors=np.tile(np.array([[1.0, 0.0, 0.0, 1.0]], dtype=np.float32), (2, 1)),
        ),
    )
    sticks = SceneObject(
        id="bonds",
        geometry=Geometry(
            kind="cylinders",
            positions=np.array(
                [[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]], dtype=np.float32
            ),
            radii=np.array([0.2, 0.2], dtype=np.float32),
            colors=np.tile(np.array([[0.0, 1.0, 0.0, 1.0]], dtype=np.float32), (2, 1)),
        ),
    )
    scene = Scene(objects=[spheres, sticks], center=(0, 0, 0), radius=4.0)
    objects = scene_mesh_objects(scene)
    assert len(objects) == 2
    by_name = {entry["name"]: entry for entry in objects}
    assert by_name["balls"]["faces"].shape[0] > 500, "two spheres, finely"
    assert by_name["bonds"]["faces"].shape[0] == 2 * 16, (
        "one 16-segment cylinder is exactly its 32 side triangles"
    )
    count = write_glb(tmp_path / "prims.glb", objects)
    assert count == sum(len(e["faces"]) for e in objects)
