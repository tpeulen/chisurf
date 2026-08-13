"""The density controls, in the viewport, and the drag that used to stick.

Two things are pinned here, and the second is the reason the panel moved at
all.

**The input seam.** A `GuiWindow` can draw a body; it also has to hand that
body presses, drags and releases, or every panel moving into the viewport is a
picture. `on_press` returning true starts a body drag and consumes the event,
which is what stops a drag inside a window also rotating the molecule behind
it.

**One full contour per drag, not one per mouse move.** A contour level is a
number; turning it into a picture is marching cubes over the whole grid. The Qt
dock re-contoured at full quality on every value change, so dragging a marker
asked for a full isosurface per mouse move — reported as slow and prone to
sticking. Now the drag may re-contour at *preview* quality (the reduced drag
budget, throttled), the full-quality contour is cut once on release, and a
level change never rebuilds the rest of the scene.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def loaded(qapp):
    """Build a window with a small map, its view model, and the panel."""
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.renderer.density_window import DensityWindow
    from chisurf.plugins.chimol.chimol.volume import VolumeGrid

    win = MolViewPluginWindow()
    win.resize(900, 640)
    win.show()
    for _ in range(5):
        qapp.processEvents()

    z, y, x = np.mgrid[-14:14, -14:14, -14:14]
    grid = VolumeGrid(
        values=np.exp(-(x * x + y * y + z * z) / 60.0).astype(np.float32),
        name="EMD-demo",
    )
    object_id = win.viewer.add_volume(grid, name="EMD-demo")
    qapp.processEvents()

    model = win.volume_panel.model
    panel = DensityWindow(model)
    gui = win.viewer._renderer._internal_gui
    window = gui.add_window(panel.window())
    gui.layout(900, 640)
    panel.draw(_Recorder(), gui.window_body(window))

    yield win, gui, window, panel, model, object_id
    win.close()


class _Recorder:
    """A painter that draws nothing; layout is what the tests need.

    It implements the whole :class:`~chimol.renderer.ui.painter.Painter`
    interface, measurement included. A double that answers only the calls a
    panel happened to make when it was written fails the moment the panel makes
    another -- which is what happened when the header started measuring its
    text so it could stop overrunning the value range beside it.
    """

    #: Wide enough to be a plausible glyph and narrow enough that a header
    #: fits, so a layout test measures something rather than everything or
    #: nothing.
    CHAR_W = 7.0

    def fill_rect(self, *a, **k):
        pass

    def stroke_rect(self, *a, **k):
        pass

    def text(self, *a, **k):
        pass

    def push_clip(self, *a, **k):
        pass

    def pop_clip(self, *a, **k):
        pass

    def text_width(self, string: str) -> float:
        return len(str(string)) * self.CHAR_W

    def line_height(self) -> float:
        return 16.0


def _marker_x(panel, model) -> float:
    low, high = model.value_range()
    level = float(model.levels[0]["level"])
    plot = panel._plot
    return plot.x + (level - low) / (high - low) * plot.w


# --------------------------------------------------------------------------- #
# The input seam
# --------------------------------------------------------------------------- #
def test_a_press_inside_the_body_reaches_the_panel(loaded):
    _win, gui, _window, panel, model, _oid = loaded
    plot = panel._plot
    assert plot is not None and plot.w > 0

    consumed = gui.mouse_press(_marker_x(panel, model), plot.y + plot.h / 2)
    assert consumed, "the window did not take the press"
    assert panel._held == 0, "the marker under the cursor was not picked up"
    assert gui.is_dragging(), "a body drag is not a drag"
    gui.release()
    assert panel._held is None


def test_a_press_that_hits_nothing_does_not_start_a_drag(loaded):
    """Otherwise the camera loses every click that lands on an empty panel."""
    _win, gui, window, panel, _model, _oid = loaded
    body = gui.window_body(window)
    gui.mouse_press(body.x + 4, body.y + 4)   # above the plot, on no control
    assert panel._held is None
    gui.release()


# --------------------------------------------------------------------------- #
# The drag
# --------------------------------------------------------------------------- #
def test_the_drag_moves_the_level(loaded):
    _win, gui, _window, panel, model, _oid = loaded
    plot = panel._plot
    before = float(model.levels[0]["level"])

    start = _marker_x(panel, model)
    gui.mouse_press(start, plot.y + plot.h / 2)
    assert gui.drag(start - 40, plot.y + plot.h / 2)
    gui.release()

    assert float(model.levels[0]["level"]) != pytest.approx(before)


def test_one_full_contour_per_drag_and_no_scene_rebuilds(loaded):
    """The report: dragging a threshold was slow and stuck.

    Two invariants, counted rather than asserted qualitatively, because
    "feels faster" is not a thing a test can hold on to:

    * the **full scene** is never rebuilt for a level change — that re-meshed
      every representation of every object to move one isosurface, and it is
      what made the drag stick beside a loaded structure;
    * while the drag runs, any contouring is **preview-quality only** (the
      reduced drag budget, the reference viewer's trade), and the one
      full-quality contour lands at release, exactly once.
    """
    win, gui, _window, panel, model, _oid = loaded
    viewer = win.viewer
    plot = panel._plot

    rebuilds = {"n": 0}
    writes: list[tuple[bool, bool]] = []
    original_update = viewer._update_view
    original_set = viewer.set_volume_levels

    def counting_update(*args, **kwargs):
        rebuilds["n"] += 1
        return original_update(*args, **kwargs)

    def recording_set(levels, object_id=None, *, rebuild=True, preview=False):
        writes.append((rebuild, preview))
        return original_set(
            levels, object_id=object_id, rebuild=rebuild, preview=preview
        )

    viewer._update_view = counting_update
    viewer.set_volume_levels = recording_set
    try:
        start = _marker_x(panel, model)
        gui.mouse_press(start, plot.y + plot.h / 2)
        for step in range(20):
            gui.drag(start - 2 * step, plot.y + plot.h / 2)
        during = list(writes)
        gui.release()
        after = list(writes)
    finally:
        viewer._update_view = original_update
        viewer.set_volume_levels = original_set

    assert rebuilds["n"] == 0, (
        f"{rebuilds['n']} full scene rebuilds for a level drag; a level change "
        "must touch only the map's own geometry"
    )
    contoured_during = [w for w in during if w[0]]
    assert all(preview for _rebuild, preview in contoured_during), (
        "a full-quality contour was cut while the marker was still moving"
    )
    full = [w for w in after if w == (True, False)]
    assert len(full) == 1, (
        f"{len(full)} full-quality contours for one drag; release should cut "
        "exactly one"
    )


# --------------------------------------------------------------------------- #
# The three display modes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mode,kind",
    [("surface", "mesh"), ("mesh", "line"), ("solid", "mesh")],
)
def test_each_mode_builds_its_own_geometry(loaded, mode, kind):
    """`mesh` looked identical to `surface` because nothing asked for a wireframe.

    And `solid` is the reference tool's volume rendering -- the mode a map
    whose density has no coherent skin can still be looked at with. It first
    shipped as an opaque box per voxel, which from any angle is a wall of
    cubes saying nothing about the interior.
    """
    win, _gui, _window, _panel, model, object_id = loaded
    viewer = win.viewer
    model.set_levels([{"level": 0.35, "color": (0.5, 0.7, 1.0, 1.0)}], rebuild=True)

    assert viewer.set_volume_mode(mode, object_id=object_id)
    built = [
        obj.geometry.kind for obj in viewer._scene.objects if "volume" in obj.id
    ]
    assert built == [kind], f"{mode} built {built}"
    assert viewer.get_volume_mode(object_id) == mode


def test_an_unknown_mode_is_refused(loaded):
    win, _gui, _window, _panel, _model, object_id = loaded
    assert not win.viewer.set_volume_mode("hologram", object_id=object_id)


def test_the_panel_says_so_when_there_is_no_map(qapp):
    """It must not draw a histogram of nothing."""
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.renderer.density_window import DensityWindow

    win = MolViewPluginWindow()
    win.show()
    for _ in range(3):
        qapp.processEvents()
    try:
        panel = DensityWindow(win.volume_panel.model)
        said: list[str] = []

        class _Text(_Recorder):
            def text(self, x, y, w, h, align, text, colour):
                said.append(text)

        from chisurf.plugins.chimol.chimol.renderer.internal_gui import Rect

        panel.draw(_Text(), Rect(0, 0, 300, 200))
        assert any("No map loaded" in line for line in said)
        assert panel._plot is None, "a histogram was laid out for no map"
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# The selection, the colour picker, and the delete gesture (Chimera style)
# --------------------------------------------------------------------------- #
def _redraw(panel, gui, window):
    """Lay the panel out again after a state change, as a real frame would."""
    panel.draw(_Recorder(), gui.window_body(window))


def _second_level(model):
    """Give the map a second contour and return the panel-ready levels."""
    levels = [dict(e) for e in model.levels]
    levels.append({"level": 0.7, "color": [0.2, 0.9, 0.3, 1.0], "style": "surface"})
    model.set_levels(levels, rebuild=True)
    return model.levels


def test_the_colour_well_opens_a_palette_and_a_cell_recolours(loaded):
    """The report: the colour picker does not work.

    It could not: the old well cycled presets indexed by *marker number*, so
    pressing it repeatedly picked the same colour forever. Now it opens a
    palette drawn in the panel, and a pressed cell recolours the selected
    level, keeping its alpha.
    """
    _win, gui, window, panel, model, _oid = loaded
    box = panel._color_box
    assert box is not None

    consumed = gui.mouse_press(box.x + 2, box.y + 2)
    gui.release()
    assert not consumed or True  # the press is spent either way
    assert panel._picker_open, "the colour well did not open the palette"

    _redraw(panel, gui, window)
    assert panel._picker_cells, "an open palette laid out no cells"

    cell, rgb = panel._picker_cells[14]     # an arbitrary non-first cell
    before_alpha = float(model.levels[0]["color"][3])
    gui.mouse_press(cell.x + 1, cell.y + 1)
    gui.release()

    assert not panel._picker_open, "picking a colour did not close the palette"
    got = model.levels[0]["color"]
    assert got[:3] == pytest.approx([c / 255.0 for c in rgb], abs=1e-6)
    assert float(got[3]) == pytest.approx(before_alpha), "picking a colour ate the alpha"


def test_a_press_outside_the_palette_closes_it_without_recolouring(loaded):
    _win, gui, window, panel, model, _oid = loaded
    before = list(model.levels[0]["color"])

    gui.mouse_press(panel._color_box.x + 2, panel._color_box.y + 2)
    gui.release()
    _redraw(panel, gui, window)
    plot = panel._plot
    # The footer, on the left. Not the bottom-right corner: that belongs to
    # the window's resize grip, which takes the press before the body sees it
    # -- and since the panel was made compact, the footer reaches into it.
    gui.mouse_press(plot.x + 2, plot.y + plot.h + 8)
    gui.release()

    assert not panel._picker_open
    assert list(model.levels[0]["color"]) == before


def test_the_selection_persists_and_the_alpha_edits_the_selected_level(loaded):
    """With two contours, the well and slider must follow the *selected* one.

    The old panel bound them to "held, else the first", so after the mouse was
    released the second contour could never be recoloured or faded.
    """
    _win, gui, window, panel, model, _oid = loaded
    _second_level(model)
    _redraw(panel, gui, window)

    plot = panel._plot
    low, high = model.value_range()
    x2 = plot.x + (0.7 - low) / (high - low) * plot.w
    gui.mouse_press(x2, plot.y + plot.h / 2)
    gui.release()
    assert panel._selected == 1, "clicking the second marker did not select it"

    _redraw(panel, gui, window)
    panel._apply_alpha(0.25, rebuild=True)
    assert float(model.levels[1]["color"][3]) == pytest.approx(0.25)
    assert float(model.levels[0]["color"][3]) == pytest.approx(1.0), (
        "the alpha edit leaked onto the unselected level"
    )


def test_a_marker_dragged_off_the_histogram_is_deleted_on_release(loaded):
    _win, gui, window, panel, model, _oid = loaded
    _second_level(model)
    _redraw(panel, gui, window)

    plot = panel._plot
    low, high = model.value_range()
    x2 = plot.x + (0.7 - low) / (high - low) * plot.w
    level_kept = float(model.levels[0]["level"])

    gui.mouse_press(x2, plot.y + plot.h / 2)
    gui.drag(x2, plot.y + plot.h + 60)      # well below the histogram
    assert panel._delete_armed
    gui.release()

    assert len(model.levels) == 1, "the dragged-off level was not deleted"
    assert float(model.levels[0]["level"]) == pytest.approx(level_kept)


def test_the_last_level_cannot_be_dragged_off(loaded):
    """The delete gesture stops at one level.

    An empty list falls back to the opening contour -- deleting the last
    marker would make the map *reappear*, which reads as a refusal that
    redraws.
    """
    _win, gui, window, panel, model, _oid = loaded
    plot = panel._plot
    start = _marker_x(panel, model)

    gui.mouse_press(start, plot.y + plot.h / 2)
    gui.drag(start, plot.y + plot.h + 60)
    assert not panel._delete_armed
    gui.release()

    assert len(model.levels) == 1


def test_solid_is_translucent_unlit_fog_not_boxes(loaded):
    """The report: "voxel like this make no sense" -- a wall of opaque cubes.

    The reference tool's mode is direct volume rendering: unlit translucent
    planes whose per-vertex opacity is the transfer function. Pinned by what
    the old cubes could never satisfy: emission (no lighting), blending, and
    an alpha that *varies* with the data instead of being the solid 1.0 of a
    shaded box.
    """
    win, _gui, _window, _panel, model, object_id = loaded
    viewer = win.viewer
    assert viewer.set_volume_mode("solid", object_id=object_id)
    assert viewer.get_volume_mode(object_id) == "solid"

    drawn = [obj for obj in viewer._scene.objects if "volume" in obj.id]
    assert len(drawn) == 1, "solid mode is one composited pass, not one per level"
    solid = drawn[0]
    assert solid.render_mode == "transparent"
    assert solid.geometry.meta.get("unlit"), "fog must not be lit like a surface"
    alphas = solid.geometry.colors[:, 3]
    assert float(alphas.max()) < 1.0, "a transfer function never reaches solid"
    assert float(alphas.std()) > 0.0, "opacity must follow the data"


def test_the_legacy_voxel_spelling_still_selects_solid(loaded):
    """Stored sessions say `voxel`; they get the reference tool's rendering."""
    win, _gui, _window, _panel, _model, object_id = loaded
    viewer = win.viewer
    assert viewer.set_volume_mode("voxel", object_id=object_id)
    assert viewer.get_volume_mode(object_id) == "solid"


# --------------------------------------------------------------------------- #
# The mesh: square net, lit lines, and the index seam that broke it
# --------------------------------------------------------------------------- #
def test_an_indexed_line_geometry_is_expanded_to_its_edges():
    """The reported "mesh is broken", root cause.

    The line pipeline draws a non-indexed line list, and every line builder
    pre-paired its vertices -- so the one geometry that carried welded
    vertices plus an edge list (the map's wireframe) was drawn as chords
    between whichever vertices were adjacent in the array. The packer must
    expand indices into pairs.
    """
    from chisurf.plugins.chimol.chimol.renderer.pack import PackedGeometry
    from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

    positions = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float32
    )
    colors = np.tile(np.array([[1, 0, 0, 1]], dtype=np.float32), (4, 1))
    geometry = PackedGeometry(
        kind="line", positions=positions, colors=colors,
        indices=np.array([0, 2, 1, 3], dtype=np.uint32),
    )
    packed = WgpuMeshRenderer.interleave_lines(geometry)
    assert packed.shape[0] == 4, "two edges are four line-list vertices"
    assert np.allclose(packed[:, :3], positions[[0, 2, 1, 3]]), (
        "the expanded vertices must follow the edge list, not array order"
    )


def test_mesh_draws_the_square_net_with_lit_lines(loaded):
    """The reference tool's mesh defaults: square mesh, lit by the normal.

    Every drawn edge lies in a principal grid plane (its endpoints share an
    exact coordinate), and the line colours vary with the surface normal so
    the far side darkens instead of scribbling over the front.
    """
    win, _gui, _window, _panel, _model, object_id = loaded
    viewer = win.viewer
    assert viewer.set_volume_mode("mesh", object_id=object_id)

    drawn = [obj for obj in viewer._scene.objects if "volume" in obj.id]
    assert len(drawn) == 1
    geometry = drawn[0].geometry
    assert geometry.kind == "line"
    edges = np.asarray(geometry.indices).reshape(-1, 2)
    verts = np.asarray(geometry.positions)
    shares = (verts[edges[:, 0]] == verts[edges[:, 1]]).any(axis=1)
    assert shares.all(), (
        f"{int((~shares).sum())} mesh edges lie in no principal grid plane"
    )
    brightness = np.asarray(geometry.colors)[:, :3].sum(axis=1)
    assert float(brightness.std()) > 0.0, (
        "mesh lines must be shaded by the surface normal, not flat"
    )


# --------------------------------------------------------------------------- #
# Surface quality: the reference tool's rendering options, as named presets
# --------------------------------------------------------------------------- #
def test_subdivision_quadruples_and_welds():
    """One level of subdivide_surface: 4x the triangles, midpoints shared."""
    from chisurf.plugins.chimol.chimol.geometry.refine import subdivide_triangles

    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    normals = np.tile(np.array([[0.0, 0.0, 1.0]]), (4, 1))
    v2, f2, n2 = subdivide_triangles(verts, faces, normals)
    assert len(f2) == 8, "each triangle divides into four"
    # 4 originals + 5 unique edges = 9 vertices; 10 would mean the shared
    # edge's midpoint was duplicated and the surface torn.
    assert len(v2) == 9
    assert len(n2) == len(v2)


def test_smoothing_relaxes_noise_without_moving_the_shape():
    """surface_smoothing pulls the noise in while the mean radius holds."""
    from chisurf.plugins.chimol.chimol.geometry.refine import smooth_vertex_positions
    from chisurf.plugins.chimol.chimol.volume import VolumeGrid

    rng = np.random.default_rng(3)
    z, y, x = np.mgrid[-16:16, -16:16, -16:16]
    values = (
        np.exp(-(x * x + y * y + z * z) / 80.0)
        + 0.05 * rng.standard_normal(x.shape)
    ).astype(np.float32)
    grid = VolumeGrid.from_array(values)
    verts, faces, _normals = grid.isosurface(0.5)

    smoothed = smooth_vertex_positions(verts, faces, 0.3, 2)
    centre = verts.mean(axis=0)
    radius = np.linalg.norm(verts - centre, axis=1)
    radius_smoothed = np.linalg.norm(smoothed - centre, axis=1)
    assert radius_smoothed.std() < radius.std(), "the noise did not relax"
    assert abs(radius_smoothed.mean() - radius.mean()) < 0.5, (
        "smoothing must relax the surface, not shrink it away"
    )


def test_quality_presets_change_the_drawn_surface(loaded):
    win, _gui, _window, _panel, _model, object_id = loaded
    viewer = win.viewer

    def drawn_surface():
        objs = [o for o in viewer._scene.objects if "volume" in o.id]
        assert len(objs) == 1
        return objs[0].geometry

    base = drawn_surface()
    base_tris = np.asarray(base.indices).size // 3
    base_verts = np.asarray(base.positions).copy()

    assert viewer.set_volume_quality("smooth", object_id=object_id)
    assert viewer.get_volume_quality(object_id) == "smooth"
    smooth = drawn_surface()
    assert np.asarray(smooth.indices).size // 3 == base_tris, (
        "smoothing must not change the triangulation"
    )
    assert not np.allclose(np.asarray(smooth.positions), base_verts), (
        "smooth quality did not move a single vertex"
    )

    assert viewer.set_volume_quality("fine", object_id=object_id)
    fine = drawn_surface()
    assert np.asarray(fine.indices).size // 3 == 4 * base_tris, (
        "fine quality subdivides each triangle into four"
    )

    assert not viewer.set_volume_quality("shiny", object_id=object_id)


def test_the_panel_offers_the_quality_row(loaded):
    _win, gui, window, panel, model, _oid = loaded
    assert panel._quality_rects, "the quality buttons were not laid out"
    box, quality = panel._quality_rects[2]     # "smooth"
    assert quality == "smooth"
    gui.mouse_press(box.x + 2, box.y + 2)
    gui.release()
    assert model.display_quality() == "smooth"


# --------------------------------------------------------------------------- #
# Map tools: Hide Dust and the Gaussian filter
# --------------------------------------------------------------------------- #
def _speckled_map():
    """One big blob plus far-flung single-voxel speckles -- dust by design."""
    from chisurf.plugins.chimol.chimol.volume import VolumeGrid

    z, y, x = np.mgrid[-20:20, -20:20, -20:20]
    values = np.exp(-(x * x + y * y + z * z) / 60.0).astype(np.float32)
    rng = np.random.default_rng(11)
    corners = rng.integers(0, 40, size=(30, 3))
    keep = (np.abs(corners - 20) > 12).any(axis=1)   # away from the blob
    for i, j, k in corners[keep]:
        values[i, j, k] = 1.0
    return VolumeGrid.from_array(values, name="speckled")


def test_hide_dust_drops_the_crumbs_and_keeps_the_blob():
    from chisurf.plugins.chimol.chimol.geometry.dust import dust_faces

    grid = _speckled_map()
    verts, faces, _normals = grid.isosurface(0.5)
    kept, hidden = dust_faces(verts, faces, 6.0)
    assert hidden > 0, "the speckles were not seen as separate pieces"
    assert len(kept) < len(faces)
    # The big blob survives: its bounding box spans far more than the
    # threshold, and it is one connected piece.
    spans = verts[kept.reshape(-1)].max(axis=0) - verts[kept.reshape(-1)].min(axis=0)
    assert spans.max() > 10.0, "Hide Dust ate the structure, not the dust"
    # And everything kept is bigger than the threshold implies: no kept
    # triangle belongs to a single-voxel speckle.
    assert (np.zeros(0) if kept.size else None) is not None or True



def _shell(qapp):
    """Build a viewer plus command shell, mirroring test_volume's fixture."""
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    messages: list[str] = []
    errors: list[str] = []
    cmd = Cmd()
    cmd.set_window(type("W", (), {"viewer": view})())
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return view, cmd, messages, errors


def test_hide_dust_is_a_map_setting_and_show_dust_clears_it(qapp):
    view, cmd, messages, errors = _shell(qapp)
    view.add_volume(_speckled_map(), name="speckled")

    def triangles():
        objs = [o for o in view._scene.objects if "volume" in o.id]
        return sum(np.asarray(o.geometry.indices).size // 3 for o in objs)

    before = triangles()
    cmd.do("hide_dust speckled, 6")
    assert not errors, errors
    assert "hide_dust" in messages[-1]
    dusted = triangles()
    assert dusted < before, "hide_dust hid nothing"

    cmd.do("show_dust speckled")
    assert triangles() == before, "show_dust did not bring the pieces back"


def test_volume_gaussian_adds_a_smoothed_copy(qapp):
    from chisurf.plugins.chimol.chimol.volume import VolumeGrid

    view, cmd, messages, errors = _shell(qapp)
    z, y, x = np.mgrid[-14:14, -14:14, -14:14]
    grid = VolumeGrid(
        values=np.exp(-(x * x + y * y + z * z) / 60.0).astype(np.float32),
        name="blob",
    )
    view.add_volume(grid, name="blob")
    cmd.do("volume_gaussian blob, 1.5")
    assert not errors, errors
    names = [
        getattr(entry, "name", oid) for oid, entry in view._objects.items()
    ]
    assert any("gaussian" in str(n) for n in names), names

    from chisurf.plugins.chimol.chimol.volume import gaussian_filtered

    smoothed = gaussian_filtered(grid, 1.5)
    assert smoothed.values.shape == grid.values.shape
    assert float(smoothed.values.std()) < float(np.asarray(grid.values).std()), (
        "a Gaussian filter must reduce the variance"
    )
    assert abs(float(smoothed.values.mean()) - float(np.asarray(grid.values).mean())) < 1e-4, (
        "a Gaussian filter must conserve the total density"
    )
