"""Voxel maps: the grid, its placement, its contours, and reading MRC.

The placement is what these mostly pin. A map drawn at the wrong scale, in the
wrong place or transposed does not look broken -- it looks like a result, and it
is believed. So the MRC tests build files whose headers exercise the two things
that reader gets asked to do and that a naive one gets wrong: axes stored in an
order other than x, y, z, and the two competing origin conventions.

Where IMP is importable its own reader is used as an independent check, so
carrying the format logic here rather than depending on IMP costs no confidence.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest
from chimol.core.model.volume import VolumeGrid
from chimol.io.mrc import load_mrc_grid


# --------------------------------------------------------------------------- #
# Writing an MRC file, so the reader can be tested against a known header
# --------------------------------------------------------------------------- #
def write_mrc(
    path,
    values,  # indexed [x, y, z]
    *,
    step=(1.0, 1.0, 1.0),
    mapc=1,
    mapr=2,
    maps=3,  # which spatial axis is fast / medium / slow
    xyz_origin=None,  # MRC2000 origin, in physical units
    start=(0, 0, 0),  # ncstart / nrstart / nsstart, in voxels
    mrc2000=True,
):
    """Write a minimal but honest MRC file.

    ``values`` is given in spatial ``[x, y, z]`` order and is permuted here to
    whatever the requested ``mapc``/``mapr``/``maps`` implies, which is what
    makes the axis-order test meaningful rather than circular.
    """
    values = np.asarray(values, dtype=np.float32)
    # A writer that left the axis words unset stores the data in plain order;
    # mirror that here rather than transposing by a nonsense permutation.
    if {mapc, mapr, maps} != {1, 2, 3}:
        mapc, mapr, maps = 1, 2, 3
        crs_to_ijk = (0, 1, 2)
        put_axis_words = (0, 0, 0)
    else:
        crs_to_ijk = (mapc - 1, mapr - 1, maps - 1)
        put_axis_words = (mapc, mapr, maps)
    # File axes are (slow, medium, fast) = (s, r, c); spatial axis of c is
    # crs_to_ijk[0], and so on.
    samples = np.transpose(values, (crs_to_ijk[2], crs_to_ijk[1], crs_to_ijk[0]))
    ns, nr, nc = samples.shape

    header = bytearray(1024)

    def put_i32(offset, *vals):
        struct.pack_into("<%di" % len(vals), header, offset, *vals)

    def put_f32(offset, *vals):
        struct.pack_into("<%df" % len(vals), header, offset, *vals)

    put_i32(0, nc, nr, ns)
    put_i32(12, 2)  # mode 2 = float32
    put_i32(16, *start)
    size = [values.shape[a] for a in range(3)]
    put_i32(28, *size)  # mx, my, mz
    put_f32(40, *[size[a] * step[a] for a in range(3)])
    put_f32(52, 90.0, 90.0, 90.0)
    put_i32(64, *put_axis_words)
    put_i32(92, 0)  # nsymbt
    if mrc2000:
        header[208:212] = b"MAP "
        if xyz_origin is not None:
            put_f32(196, *xyz_origin)

    with open(path, "wb") as handle:
        handle.write(bytes(header))
        handle.write(np.ascontiguousarray(samples, dtype="<f4").tobytes())
    return path


@pytest.fixture
def blob():
    """A deliberately non-cubic map, so a transposition cannot hide."""
    values = np.zeros((6, 5, 4), dtype=np.float32)
    values[4, 1, 2] = 10.0  # an asymmetric marker
    values[1:3, 2:4, 1:3] = 3.0
    return values


# --------------------------------------------------------------------------- #
# The grid itself
# --------------------------------------------------------------------------- #
def test_a_map_can_be_built_from_an_array_in_memory():
    """AVs and image stacks are already arrays; a file must not be required."""
    grid = VolumeGrid.from_array(np.ones((3, 4, 5)), step=(1.0, 2.0, 3.0))
    assert grid.shape == (3, 4, 5)
    assert grid.voxel_count == 60
    assert tuple(grid.step) == (1.0, 2.0, 3.0)


def test_an_isotropic_step_may_be_given_as_one_number():
    grid = VolumeGrid.from_array(np.ones((2, 2, 2)), step=1.5)
    assert tuple(grid.step) == (1.5, 1.5, 1.5)


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"array": np.ones((4, 4))}, "2-D"),
        ({"array": np.zeros((0, 2, 2))}, "empty"),
        ({"array": np.ones((2, 2, 2)), "step": (1.0, 0.0, 1.0)}, "zero step"),
        ({"array": np.ones((2, 2, 2)), "step": (1.0, -2.0, 1.0)}, "negative step"),
        ({"array": np.ones((2, 2, 2)), "step": (1.0, np.nan, 1.0)}, "nan step"),
    ],
)
def test_a_map_that_cannot_be_placed_is_refused(kwargs, reason):
    """Refused, not defaulted: a map at the wrong scale reads as data."""
    with pytest.raises(ValueError):
        VolumeGrid.from_array(**kwargs)


def test_placement_applies_step_then_rotation_then_origin():
    grid = VolumeGrid.from_array(np.ones((2, 2, 2)), origin=(10.0, 0.0, 0.0), step=(2.0, 3.0, 4.0))
    assert grid.index_to_world((0, 0, 0)) == pytest.approx([10.0, 0.0, 0.0])
    assert grid.index_to_world((1, 1, 1)) == pytest.approx([12.0, 3.0, 4.0])
    # A quarter turn about z sends +x to +y.
    turned = VolumeGrid.from_array(
        np.ones((2, 2, 2)),
        rotation=[[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    )
    assert turned.index_to_world((1, 0, 0)) == pytest.approx([0.0, 1.0, 0.0])


def test_an_anisotropic_step_is_not_squashed():
    """A confocal z step is rarely its xy step; treating it as cubic squashes it."""
    grid = VolumeGrid.from_array(np.ones((10, 10, 10)), step=(0.1, 0.1, 0.5))
    low, high = grid.extent()
    assert (high - low) == pytest.approx([0.9, 0.9, 4.5])


# --------------------------------------------------------------------------- #
# Bounding the display cost
# --------------------------------------------------------------------------- #
def test_a_small_map_is_not_strided_at_all():
    grid = VolumeGrid.from_array(np.ones((20, 20, 20)))
    assert grid.stride_for_limit() == 1
    assert grid.strided() is grid, "an ordinary map must not be copied"


def test_a_large_map_is_strided_under_the_budget():
    grid = VolumeGrid.from_array(np.zeros((300, 300, 300), dtype=np.float32))
    strided = grid.strided(voxel_limit_m=1.0)
    assert strided.voxel_count <= 1_000_000
    assert strided is not grid


def test_striding_keeps_the_map_in_the_same_place_and_size():
    """The step scales with the stride, or the map shrinks as it coarsens."""
    values = np.zeros((64, 64, 64), dtype=np.float32)
    grid = VolumeGrid.from_array(values, origin=(5.0, -3.0, 2.0), step=(0.5, 0.5, 0.5))
    strided = grid.strided(voxel_limit_m=0.001)
    assert strided is not grid
    low_full, high_full = grid.extent()
    low_strided, high_strided = strided.extent()
    assert low_strided == pytest.approx(low_full)
    # The last sample may be dropped by the stride, so the far corner is allowed
    # to fall short by up to one strided voxel -- but not to move.
    assert np.all(high_strided <= high_full + 1e-6)
    assert np.all(high_strided >= high_full - strided.step - 1e-6)


# --------------------------------------------------------------------------- #
# Contours
# --------------------------------------------------------------------------- #
def test_a_contour_encloses_the_dense_region():
    values = np.zeros((20, 20, 20), dtype=np.float32)
    values[6:14, 6:14, 6:14] = 1.0
    grid = VolumeGrid.from_array(values, step=(1.0, 1.0, 1.0))
    surface = grid.isosurface(0.5)
    assert surface is not None
    verts, faces, normals = surface
    assert verts.shape[0] > 0 and faces.shape[0] > 0
    assert normals.shape == verts.shape
    # The contour of a centred cube sits around that cube, not somewhere else.
    assert verts.min(axis=0) == pytest.approx([5.0, 5.0, 5.0], abs=1.5)
    assert verts.max(axis=0) == pytest.approx([14.0, 14.0, 14.0], abs=1.5)


def test_a_contour_follows_the_maps_placement():
    values = np.zeros((20, 20, 20), dtype=np.float32)
    values[6:14, 6:14, 6:14] = 1.0
    placed = VolumeGrid.from_array(values, origin=(100.0, 0.0, -50.0), step=(2.0, 1.0, 1.0))
    verts = placed.isosurface(0.5)[0]
    assert verts[:, 0].min() > 100.0
    assert verts[:, 2].min() < 0.0


def test_a_level_outside_the_data_says_so_rather_than_inventing_a_surface():
    grid = VolumeGrid.from_array(np.zeros((8, 8, 8), dtype=np.float32) + 0.5)
    assert grid.isosurface(10.0) is None
    assert grid.isosurface(-10.0) is None


def test_the_default_level_lands_inside_the_data():
    rng = np.random.default_rng(11)
    values = rng.random((16, 16, 16)).astype(np.float32)
    values[4:8, 4:8, 4:8] += 5.0
    grid = VolumeGrid.from_array(values)
    level = grid.default_level()
    low, high = grid.value_range()
    assert low < level < high
    assert grid.isosurface(level) is not None


def test_a_flat_map_has_no_contour_to_draw():
    grid = VolumeGrid.from_array(np.full((8, 8, 8), 2.0, dtype=np.float32))
    assert grid.isosurface() is None


def test_a_histogram_is_available_for_choosing_a_level():
    grid = VolumeGrid.from_array(np.linspace(0, 1, 512).reshape(8, 8, 8))
    counts, edges = grid.histogram(bins=32)
    assert counts.sum() == 512
    assert edges.shape == (33,)


# --------------------------------------------------------------------------- #
# Reading MRC: the two things a naive reader gets wrong
# --------------------------------------------------------------------------- #
def test_a_plain_map_round_trips(tmp_path, blob):
    path = write_mrc(tmp_path / "plain.mrc", blob, step=(1.0, 1.0, 1.0))
    grid = load_mrc_grid(path)
    assert grid.shape == blob.shape
    assert np.allclose(grid.values, blob)


@pytest.mark.parametrize(
    "mapc,mapr,maps",
    [(1, 2, 3), (3, 1, 2), (2, 3, 1), (1, 3, 2), (3, 2, 1), (2, 1, 3)],
)
def test_axes_stored_in_any_order_read_back_the_same_map(tmp_path, blob, mapc, mapr, maps):
    """`mapc`/`mapr`/`maps` are a permutation, not decoration.

    Ignoring them loads the map transposed: for a non-cubic map that is not even
    the right shape, and for a cubic one it is a silently rotated map that still
    looks plausible.
    """
    path = write_mrc(
        tmp_path / f"perm_{mapc}{mapr}{maps}.mrc",
        blob,
        mapc=mapc,
        mapr=mapr,
        maps=maps,
    )
    grid = load_mrc_grid(path)
    assert grid.shape == blob.shape, f"axis order {mapc}{mapr}{maps} came back wrong"
    assert np.allclose(grid.values, blob)


def test_a_bad_axis_assignment_falls_back_rather_than_scrambling(tmp_path, blob):
    """Some writers leave the axis words zero; a partial permutation is refused."""
    path = write_mrc(tmp_path / "noaxes.mrc", blob, mapc=0, mapr=0, maps=0)
    grid = load_mrc_grid(path)
    assert grid.shape == blob.shape


def test_the_mrc2000_origin_is_used_when_it_is_set(tmp_path, blob):
    path = write_mrc(tmp_path / "xyzorigin.mrc", blob, xyz_origin=(12.5, -4.0, 7.25))
    grid = load_mrc_grid(path)
    assert tuple(grid.origin) == pytest.approx((12.5, -4.0, 7.25))


def test_the_start_indices_place_the_map_when_the_xyz_origin_is_zero(tmp_path, blob):
    """Many modern files leave the xyz origin at zero and mean the start indices.

    Preferring the format version over the value is what puts a map next to the
    model instead of around it.
    """
    path = write_mrc(tmp_path / "startorigin.mrc", blob, step=(2.0, 2.0, 2.0), start=(3, 4, 5))
    grid = load_mrc_grid(path)
    assert tuple(grid.origin) == pytest.approx((6.0, 8.0, 10.0))


def test_absurd_start_indices_are_treated_as_uninitialised(tmp_path, blob):
    path = write_mrc(tmp_path / "junkstart.mrc", blob, start=(10**6, 0, 0))
    grid = load_mrc_grid(path)
    assert tuple(grid.origin) == pytest.approx((0.0, 0.0, 0.0))


def test_the_voxel_step_comes_from_the_cell(tmp_path, blob):
    path = write_mrc(tmp_path / "step.mrc", blob, step=(0.5, 1.25, 3.0))
    grid = load_mrc_grid(path)
    assert tuple(grid.step) == pytest.approx((0.5, 1.25, 3.0))


def test_a_truncated_file_is_refused(tmp_path, blob):
    path = write_mrc(tmp_path / "short.mrc", blob)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) - 64])
    with pytest.raises(ValueError, match="truncated"):
        load_mrc_grid(path)


def test_an_unsupported_mode_is_named_rather_than_reinterpreted(tmp_path, blob):
    """Modes 3 and 4 are complex transforms; showing them as density is a lie."""
    path = write_mrc(tmp_path / "mode3.mrc", blob)
    data = bytearray(path.read_bytes())
    struct.pack_into("<i", data, 12, 3)
    path.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="mode 3"):
        load_mrc_grid(path)


def test_the_legacy_point_cloud_still_works_and_is_placed(tmp_path, blob):
    """The old entry point now derives from the grid instead of re-parsing."""
    from chimol.io.mrc import load_mrc_as_points

    path = write_mrc(tmp_path / "points.mrc", blob, xyz_origin=(50.0, 0.0, 0.0))
    positions, meta = load_mrc_as_points(path)
    assert positions.shape[1] == 3
    assert positions.shape[0] > 0
    assert positions[:, 0].min() >= 50.0, "the point cloud ignored the origin"
    assert meta["origin"] == pytest.approx((50.0, 0.0, 0.0))


# --------------------------------------------------------------------------- #
# Cross-check against IMP's reader where it is available
# --------------------------------------------------------------------------- #
def test_agrees_with_imps_reader(tmp_path, blob):
    """An independent implementation, so carrying this logic costs no confidence.

    Skipped rather than failed where IMP is absent: ChiMOL runs standalone and
    does not depend on it.
    """
    IMP_em = pytest.importorskip("IMP.em", reason="IMP not available")

    path = write_mrc(tmp_path / "imp.mrc", blob, step=(1.5, 1.5, 1.5), xyz_origin=(3.0, 4.0, 5.0))
    ours = load_mrc_grid(path)

    theirs = IMP_em.read_map(str(path), IMP_em.MRCReaderWriter())
    header = theirs.get_header()
    assert (header.get_nx(), header.get_ny(), header.get_nz()) == ours.shape
    assert header.get_spacing() == pytest.approx(float(ours.step[0]), abs=1e-4)
    their_origin = (theirs.get_origin()[0], theirs.get_origin()[1], theirs.get_origin()[2])
    assert their_origin == pytest.approx(tuple(ours.origin), abs=1e-4)

    their_values = np.asarray(
        [theirs.get_value(i) for i in range(theirs.get_number_of_voxels())],
        dtype=np.float32,
    )
    # IMP indexes x fastest; ours is [x, y, z], so its flat order is the reverse.
    assert np.allclose(their_values, ours.values.transpose(2, 1, 0).ravel(), atol=1e-5)


# --------------------------------------------------------------------------- #
# A map in the scene
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def shell(qapp):
    """A blob map, in a viewer, reachable from the command line."""
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer

    view = Viewer()
    zz, yy, xx = np.mgrid[0:24, 0:24, 0:24]
    values = np.exp(-(((xx - 12) ** 2 + (yy - 12) ** 2 + (zz - 12) ** 2) / 40.0)).astype(np.float32)
    grid = VolumeGrid.from_array(values, step=(1.0, 1.0, 1.0), name="blob")

    messages, errors = [], []
    cmd = Cmd()
    cmd.set_window(type("W", (), {"viewer": view})())
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    try:
        yield view, grid, cmd, messages, errors
    finally:
        view.deleteLater()


def test_a_map_becomes_a_scene_object(shell):
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(grid)
    scene = view._scene
    assert scene is not None and len(scene.objects) == 1
    geometry = scene.objects[0].geometry
    assert geometry.positions.shape[0] > 0
    assert geometry.indices is not None


def test_a_map_is_visible_although_it_has_no_coordinates(shell):
    """The visibility filter tests for coordinates; a map has none.

    Without the map being asked about explicitly it was dropped from the scene
    with no message at all.
    """
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(grid)
    assert view._coords is None
    assert view._scene is not None and view._scene.objects


def test_two_maps_do_not_share_an_object_id(shell):
    """Ids are qualified on the map-only path too, or the second overwrites."""
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(grid, name="one")
    view.add_volume(VolumeGrid.from_array(grid.values.copy(), name="two"), name="two")
    ids = [obj.id for obj in view._scene.objects]
    assert len(ids) == len(set(ids)), ids


def test_a_map_adopts_the_frame_of_what_is_already_loaded(shell):
    """Scene coordinates are relative to an object's centre.

    A map that centred on itself was drawn at the middle of the scene whatever
    its true position -- a density that wraps a structure appeared as a small
    blob inside it. The picture is the only place that shows.
    """
    view, grid, _cmd, _msgs, _errs = shell
    view.add_coordinates(np.zeros((4, 3)))  # something to define the frame
    existing = np.asarray(view._raw_center, dtype=float)

    offset = VolumeGrid.from_array(grid.values, origin=(500.0, 0.0, 0.0), step=(1.0, 1.0, 1.0))
    object_id = view.add_volume(offset)
    with view.activate_object(object_id):
        assert np.allclose(np.asarray(view._raw_center, dtype=float), existing)
    # ...and the geometry lands far from the origin, as its origin says.
    verts = [obj.geometry.positions for obj in view._scene.objects if obj.id.endswith("volume_0")][
        0
    ]
    assert verts[:, 0].min() > 100.0


def test_mesh_style_draws_lines_rather_than_a_filled_surface(shell):
    """`isomesh` asked for a wireframe and got a solid surface.

    A ``wireframe`` flag on a triangle mesh is read by nothing downstream, so it
    looked correct in the code and drew the wrong thing on the screen.
    """
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(
        grid,
        levels=[{"level": grid.default_level(), "style": "mesh", "color": (0.0, 0.0, 1.0, 1.0)}],
    )
    geometry = view._scene.objects[0].geometry
    assert geometry.kind == "line"
    assert geometry.indices.shape[1] == 2


def test_the_wireframe_does_not_send_every_edge_twice():
    """Interior edges are shared; drawing both copies doubles the lines."""
    from chimol.geometry.edges import _triangle_edges

    faces = np.array([[0, 1, 2], [1, 2, 3]])  # two triangles sharing edge 1-2
    edges = _triangle_edges(faces)
    assert edges.shape == (5, 2)  # 3 + 3 - 1 shared
    assert len({tuple(e) for e in edges}) == 5


# --------------------------------------------------------------------------- #
# The commands
# --------------------------------------------------------------------------- #
def test_isosurface_adds_a_contour(shell):
    view, grid, cmd, messages, errors = shell
    view.add_volume(grid)
    cmd.do("isosurface dense, blob")
    assert not errors, errors
    assert len(view.get_volume_levels()) >= 1


def test_a_level_outside_the_map_is_refused_with_the_range(shell):
    """The range is the useful part: a level means nothing without the scale."""
    view, grid, cmd, messages, errors = shell
    view.add_volume(grid)
    cmd.do("isosurface bad, blob, 999")
    assert errors, "a level above the map should be refused"
    assert "999" in errors[-1] and "to" in errors[-1]


def test_asking_about_a_map_that_is_not_loaded_says_so(shell):
    _view, _grid, cmd, _messages, errors = shell
    cmd.do("map_info")
    assert errors and "no maps" in errors[-1].lower()


def test_naming_a_map_that_does_not_exist_lists_the_ones_that_do(shell):
    view, grid, cmd, _messages, errors = shell
    view.add_volume(grid, name="blob")
    cmd.do("map_info nosuchmap")
    assert errors and "blob" in errors[-1]


def test_volume_switches_the_map_to_solid_rendering(shell):
    """`volume` is PyMOL's volume-rendering command; it now delivers one.

    It used to be a registered refusal ("not implemented yet") -- once the
    `solid` style exists, a command that declines while the panel's button
    works would be lying about the program.
    """
    view, grid, cmd, messages, errors = shell
    view.add_volume(grid)
    cmd.do("volume v, blob")
    assert not errors, errors
    assert messages and "fog" in messages[-1]
    assert view.get_volume_mode() == "solid"


def test_map_info_reports_placement_and_range(shell):
    view, _grid, cmd, messages, errors = shell
    placed = VolumeGrid.from_array(
        np.linspace(0, 1, 8**3, dtype=np.float32).reshape(8, 8, 8),
        origin=(3.0, 4.0, 5.0),
        step=(0.5, 0.5, 2.0),
        name="placed",
    )
    view.add_volume(placed)
    cmd.do("map_info placed")
    assert not errors, errors
    report = messages[-1]
    assert "8 x 8 x 8" in report
    assert "0.5" in report and "2" in report  # the anisotropic step
    assert "3" in report and "4" in report  # the origin


# --------------------------------------------------------------------------- #
# Everything derived from the samples is computed once
# --------------------------------------------------------------------------- #
def test_a_contour_is_cut_once_per_level_not_once_per_ask(blob, monkeypatch):
    """The histogram panel and the scene both ask; the map answers from memory.

    A colour change, an opacity change and a surface/mesh toggle all redraw
    the same level -- re-running marching cubes for each was most of why the
    map controls felt slow.
    """
    from chimol.core.model import volume as volume_module

    grid = VolumeGrid.from_array(blob)
    calls = {"n": 0}
    real = volume_module.marching_cubes

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(volume_module, "marching_cubes", counting)
    first = grid.isosurface(0.35)
    second = grid.isosurface(0.35)
    assert calls["n"] == 1, "the same level was contoured twice"
    assert first is second, "the memo did not hand back the same surface"
    assert not first[0].flags.writeable, (
        "a shared surface must be read-only, or one caller corrupts the next"
    )


def test_the_histogram_and_range_are_not_rescanned_per_paint(blob):
    """The density window redraws every frame; the map must not be re-read."""
    grid = VolumeGrid.from_array(blob)
    counts_a, edges_a = grid.histogram(200)
    counts_b, edges_b = grid.histogram(200)
    assert counts_a is counts_b and edges_a is edges_b
    assert grid.value_range() == grid.value_range()
    assert grid._cache, "nothing was memoised at all"


def test_a_level_change_does_not_rebuild_the_rest_of_the_scene(shell):
    """Dragging a threshold beside a structure re-meshed the structure too.

    The level write must swap only the map's own ``volume_*`` objects; every
    other scene object survives identically.
    """
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(grid)
    before = {obj.id: obj for obj in view._scene.objects}
    assert before, "the map did not reach the scene"

    calls = {"n": 0}
    original = view.update_view

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    view.update_view = counting
    try:
        ok = view.set_volume_levels(
            [{"level": 0.5, "color": (1.0, 0.0, 0.0, 1.0), "style": "surface"}]
        )
    finally:
        view.update_view = original

    assert ok
    assert calls["n"] == 0, "a level change fell back to a full scene rebuild"
    after_ids = {obj.id for obj in view._scene.objects}
    assert after_ids == set(before), (before.keys(), after_ids)
    drawn = [obj for obj in view._scene.objects if "volume_" in obj.id]
    assert drawn and drawn[0] is not before[drawn[0].id], (
        "the map's geometry was not actually replaced"
    )


# --------------------------------------------------------------------------- #
# Opening contours: the reference tool is the authority for maps
# --------------------------------------------------------------------------- #
def test_the_default_level_encloses_the_densest_one_percent():
    """`initial_surface_levels`' rule: a rank, not a mean and a sigma.

    A rank is free of both the scale and the *shape* of the distribution, which
    matters because none of the maps here share either.
    """
    rng = np.random.default_rng(5)
    values = rng.normal(0.0, 1.0, (40, 40, 40)).astype(np.float32)
    grid = VolumeGrid.from_array(values)
    level = grid.default_level()
    enclosed = float((values >= level).mean())
    assert enclosed == pytest.approx(0.01, abs=0.003), enclosed


def test_a_binary_map_contours_at_a_half():
    """An accessible volume *is* a binary mask, and this is why the case exists.

    A rank-based level on a mask that fills a third of its box lands at 1.0 --
    inside the occupied region -- and draws a surface within the volume instead
    of around it. The reference tool special-cases this and so does ChiMOL.
    """
    zz, yy, xx = np.mgrid[0:30, 0:30, 0:30]
    occupied = ((xx - 15) ** 2 + (yy - 15) ** 2 + (zz - 15) ** 2) < 200
    grid = VolumeGrid.from_array(occupied.astype(np.float32), name="av")
    assert grid.is_binary()
    assert grid.default_levels() == [0.5]
    # ...and the contour really does wrap the occupied region.
    verts = grid.isosurface(0.5)[0]
    filled = np.argwhere(occupied)
    assert verts.min(axis=0) == pytest.approx(filled.min(axis=0), abs=2.0)
    assert verts.max(axis=0) == pytest.approx(filled.max(axis=0), abs=2.0)


def test_a_map_signed_both_ways_opens_with_a_symmetric_pair():
    """A difference map's negative lobe is half of what it is for."""
    zz, yy, xx = np.mgrid[0:30, 0:30, 0:30]
    positive = np.exp(-(((xx - 12) ** 2 + (yy - 15) ** 2 + (zz - 15) ** 2) / 30.0))
    negative = np.exp(-(((xx - 20) ** 2 + (yy - 15) ** 2 + (zz - 15) ** 2) / 30.0))
    grid = VolumeGrid.from_array((positive - negative).astype(np.float32))
    assert grid.is_polar()
    levels = grid.default_levels()
    assert len(levels) == 2
    assert levels[0] == pytest.approx(-levels[1])


def test_noise_around_zero_does_not_make_a_map_polar():
    """Judged on both tails carrying weight, not on a negative minimum alone."""
    rng = np.random.default_rng(9)
    zz, yy, xx = np.mgrid[0:30, 0:30, 0:30]
    blob = np.exp(-(((xx - 15) ** 2 + (yy - 15) ** 2 + (zz - 15) ** 2) / 30.0)) * 100
    values = (blob + rng.normal(0.0, 1.0, blob.shape)).astype(np.float32)
    grid = VolumeGrid.from_array(values)
    assert values.min() < 0, "the fixture needs a negative tail to be meaningful"
    assert not grid.is_polar()
    assert len(grid.default_levels()) == 1


def test_a_flat_map_offers_no_level_at_all():
    grid = VolumeGrid.from_array(np.full((8, 8, 8), 3.0, dtype=np.float32))
    assert grid.default_levels() == []


def test_the_negative_lobe_gets_a_distinguishable_colour():
    """Transcribed from `_negative_color`, including the too-dark rescue."""
    from chimol.core.model.volume import _negative_lobe_color

    # White inverts to black, which would be invisible; it becomes red.
    assert _negative_lobe_color((1.0, 1.0, 1.0, 1.0)) == (1.0, 0.0, 0.0, 1.0)
    # A dark inverse is brightened rather than left unreadable.
    result = _negative_lobe_color((0.5, 0.7, 1.0, 1.0))
    assert max(result[:3]) == pytest.approx(1.0)
    assert result[3] == 1.0


def test_a_polar_map_is_drawn_as_two_coloured_contours(shell):
    view, _grid, _cmd, _msgs, _errs = shell
    zz, yy, xx = np.mgrid[0:24, 0:24, 0:24]
    positive = np.exp(-(((xx - 9) ** 2 + (yy - 12) ** 2 + (zz - 12) ** 2) / 25.0))
    negative = np.exp(-(((xx - 16) ** 2 + (yy - 12) ** 2 + (zz - 12) ** 2) / 25.0))
    view.add_volume(VolumeGrid.from_array((positive - negative).astype(np.float32), name="diff"))
    objects = view._scene.objects
    assert len(objects) == 2, "both lobes should be drawn"
    colours = {tuple(round(float(c), 3) for c in obj.geometry.colors[0]) for obj in objects}
    assert len(colours) == 2, "the two lobes must be told apart by colour"


# --------------------------------------------------------------------------- #
# The map panel
# --------------------------------------------------------------------------- #
def test_the_panel_is_a_view_of_the_map_not_a_copy(shell):
    """Levels live on the map object; the panel reads and writes them there.

    A panel that cached what it displayed would drift from what is drawn -- the
    failure this codebase keeps finding -- so the view model holds no list.
    """
    view, grid, _cmd, _msgs, _errs = shell
    from chimol.plugins.density.model import VolumeViewModel

    view.add_volume(grid, name="blob")
    model = VolumeViewModel(view)
    assert [round(entry["level"], 6) for entry in model.levels] == [
        round(entry["level"], 6) for entry in view.get_volume_levels()
    ]

    model.levels = [{"level": 0.3, "color": (1.0, 0.0, 0.0, 1.0), "style": "mesh"}]
    assert [round(e["level"], 6) for e in view.get_volume_levels()] == [0.3]


def test_the_opening_contours_are_stored_not_only_drawn(shell):
    """A map was drawn with levels the object did not have.

    `_update_volume` derived defaults at draw time and stored nothing, so the
    panel -- and every `get_volume_levels` caller -- saw an empty list while a
    contour was plainly on screen. Two answers to one question.
    """
    view, grid, _cmd, _msgs, _errs = shell
    view.add_volume(grid, name="blob")
    stored = view.get_volume_levels()
    assert stored, "the opening contour has to be on the object"
    drawn = [obj.geometry.meta.get("map_level") for obj in view._scene.objects]
    assert [round(float(e["level"]), 6) for e in stored] == [
        round(float(level), 6) for level in drawn
    ]


def test_the_panel_summarises_the_map_and_says_when_there_is_none(shell):
    view, grid, _cmd, _msgs, _errs = shell
    from chimol.plugins.density.model import VolumeViewModel

    model = VolumeViewModel(view)
    assert "no map" in model.summary().lower()
    assert model.level_histogram_data() is None
    assert model.value_range() is None

    view.add_volume(grid, name="blob")
    summary = model.summary()
    assert "blob" in summary and "24×24×24" in summary
    counts, edges = model.level_histogram_data()
    assert counts.sum() > 0 and edges.shape[0] == counts.shape[0] + 1
    assert model.value_range() == grid.value_range()


def test_the_panel_view_spec_uses_the_shared_section(shell):
    """The panel is AutoForm over a view spec, not a hand-rolled layout."""
    from chimol.plugins.density.model import VolumeViewModel

    view, _grid, _cmd, _msgs, _errs = shell
    spec = VolumeViewModel(view).view_spec()
    # chimol's own spec loader (`emtk.view_spec`) hands back the authored
    # document as a dict; ChiSurf's dataspec wraps the same file in objects.
    # The model no longer imports ChiSurf for this, so both shapes are read.
    sections = spec["sections"] if isinstance(spec, dict) else spec.sections
    keys = [
        section.get("key", "") if isinstance(section, dict) else getattr(section, "key", "")
        for section in sections
    ]
    assert "level_histogram" in keys, keys


# --------------------------------------------------------------------------- #
# Fetching from the three repositories
# --------------------------------------------------------------------------- #
def test_an_identifier_names_its_repository():
    """`fetch 148l` is a structure, `fetch EMD-3061` is a map."""
    from chimol.commands.command import Cmd

    cmd = Cmd()
    assert cmd._repository_for("148l") == "pdb"
    assert cmd._repository_for("1RTD") == "pdb"
    assert cmd._repository_for("EMD-3061") == "emdb"
    assert cmd._repository_for("emd_1234") == "emdb"
    assert cmd._repository_for("pdb_00001abc") == "pdb"


def test_every_repository_is_reachable():
    from chimol.commands.command import Cmd

    assert set(Cmd.REPOSITORIES) == {"pdb", "emdb", "pdb-ihm", "alphafold", "shareloc", "npc"}
    for spec in Cmd.REPOSITORIES.values():
        assert spec["url"].startswith("http")
        # Appended to the downloaded file's name: ".cif", or "_sml.csv" for
        # the NPC tables whose files are named "<cell>_sml.csv".
        assert "." in spec["suffix"]


def test_an_emdb_id_that_carries_no_number_is_refused_clearly(monkeypatch, tmp_path):
    """The EMDB fetch never worked: its pattern matched a literal backslash.

    Every identifier failed to parse, so the command reported "could not parse"
    for correct input -- which reads as the user's mistake rather than the
    command's. This pins both that a real id parses and that a bad one is named.
    """
    from chimol.commands.builtin import loader as loader_mod
    from chimol.commands.command import Cmd

    monkeypatch.setattr(loader_mod, "_download_dir", lambda: tmp_path)
    cmd = Cmd()
    errors = []
    cmd.set_error_callback(errors.append)
    cmd.set_window(type("W", (), {"viewer": object()})())

    requested = []
    import urllib.request

    def _refuse(url, *a, **k):
        requested.append(url)
        raise OSError("no network in tests")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)

    cmd._fetch_one("EMD-3061", "emdb")
    assert requested and "emd_3061.map.gz" in requested[-1], requested
    assert "EMD-3061" in errors[-1]

    errors.clear()
    requested.clear()
    cmd._fetch_one("nonsense", "emdb")
    assert not requested, "a number-less EMDB id should not be requested at all"
    assert "EMDB number" in errors[-1]


def test_each_repository_builds_the_url_it_should(monkeypatch, tmp_path):
    # An empty download directory: `fetch` re-uses an entry it already has, so a
    # test about *which URL is requested* has to start from one it does not.
    from chimol.commands.builtin import loader as loader_mod
    from chimol.commands.command import Cmd

    monkeypatch.setattr(loader_mod, "_download_dir", lambda: tmp_path)
    cmd = Cmd()
    cmd.set_error_callback(lambda _m: None)
    cmd.set_window(type("W", (), {"viewer": object()})())
    requested = []
    import urllib.request

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda url, *a, **k: (_ for _ in ()).throw(OSError(requested.append(url) or "x")),
    )

    cmd._fetch_one("148l", "pdb")
    assert requested[-1] == "https://files.rcsb.org/download/148l.pdb"
    cmd._fetch_one("8zzz", "pdb-ihm")
    assert requested[-1] == "https://pdb-ihm.org/cif/8zzz.cif"
    cmd._fetch_one("EMD-3061", "emdb")
    assert "EMD-3061/map/emd_3061.map.gz" in requested[-1]


def test_a_map_file_loads_as_a_map_object_not_a_point_cloud(tmp_path, blob, qapp):
    """The point cloud threw the volume away: no level, nothing for the panel."""
    from chimol.hosts.qt.window import MolViewPluginWindow

    path = write_mrc(tmp_path / "loaded.mrc", blob, step=(1.5, 1.5, 1.5))
    window = MolViewPluginWindow()
    try:
        object_id = window.load_structure_from_path(path)
        assert window.viewer.get_volume(object_id) is not None
        assert window.viewer.get_volume_levels(object_id), "it should open contoured"
    finally:
        window.close()
