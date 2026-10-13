"""The sequence strip's chains, the label size, and the pick marker.

Three reports, one file, because all three are the same shape of fault: a value
that was configured, drawn or loaded and then read by nothing.

* ``label.size`` sat in the display config at 14 while ``paint_labels``
  hard-coded 10, so the setting could not change anything and what was on
  screen was smaller than the config claimed;
* the strip ran every chain together into one row named after the object, so
  residue numbers -- which restart per chain -- repeated with nothing to say
  which chain they belonged to. PyMOL splits by chain and labels the row
  ``object/chain``;
* a measurement's first pick drew nothing at all, so a mis-aim and a mis-click
  looked the same.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "1rtd.pdb"
)


@pytest.fixture(scope="module")
def session():
    from native_window import NativeWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = NativeWindow(size=(900, 620))
    shared = win.cmd
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)

    def run(line: str) -> None:
        win.run_menu_command(line)

    run(f"load {PDB}")
    win.refresh_objects()
    yield run, win
    win.close()


# --------------------------------------------------------------------------- #
# The sequence strip: one row per chain, PyMOL's slash syntax
# --------------------------------------------------------------------------- #
def _rows(win):
    return win.viewer.gui.sequences


def test_one_row_per_object_with_the_chains_inside_it(session):
    """PyMOL's shape, from `Seeker.cpp`: `nRow++` closes the per-object loop."""
    _run, win = session
    rows = _rows(win)
    assert len(rows) == 1
    assert rows[0].residue_indices


def test_the_chain_ids_appear_as_columns(session):
    """A row spanning several chains repeats residue numbers otherwise."""
    _run, win = session
    row = _rows(win)[0]
    _atoms, _res, _el, _n = None, None, None, None
    markers = [i for i, index in enumerate(row.residue_indices) if index < 0]
    assert markers, "no chain markers in a multi-chain structure"
    # A marker names no residue, so it must not point at one.
    assert all(row.residue_indices[i] == -1 for i in markers)


def test_every_residue_is_reachable_exactly_once(session):
    _run, win = session
    row = _rows(win)[0]
    mapping = [i for i in row.residue_indices if i >= 0]
    assert sorted(mapping) == list(range(len(win.viewer._residue_ids)))


def test_a_click_on_a_marker_selects_nothing(session):
    """Otherwise a chain label selects whatever shares its column index."""
    _run, win = session
    gui = win.viewer.gui
    row = _rows(win)[0]
    marker = next(i for i, index in enumerate(row.residue_indices) if index < 0)

    gui._emit_select(row, [marker], False)
    assert win.viewer._selected_residues == []


def test_a_click_on_a_residue_column_selects_that_residue(session):
    _run, win = session
    gui = win.viewer.gui
    row = _rows(win)[0]
    columns = [i for i, index in enumerate(row.residue_indices) if index >= 0][:3]

    gui._emit_select(row, columns, False)
    assert sorted(win.viewer._selected_residues) == [row.residue_indices[c] for c in columns]


def test_an_object_without_chains_has_no_markers():
    """No chain column is not a reason to invent one."""
    from chimol.hosts.base import sequence_rows_for_object

    rows = sequence_rows_for_object(
        "o1", "beads", list("ACDEF"), [1, 2, 3, 4, 5], [], None
    )
    assert len(rows) == 1
    assert rows[0].name == "beads"
    assert rows[0].codes == "ACDEF"
    assert rows[0].residue_indices == [0, 1, 2, 3, 4]


# --------------------------------------------------------------------------- #
# Label size
# --------------------------------------------------------------------------- #
def test_the_label_size_setting_is_read(session):
    run, win = session
    renderer = win.viewer.renderer
    before = renderer._label_size()
    assert before > 10.0, "the hard-coded 10 is back"
    try:
        run("set label_size, 24")
        assert renderer._label_size() == pytest.approx(24.0)
    finally:
        run(f"set label_size, {before}")


def test_paint_labels_honours_the_size_it_is_given():
    """The painter, not just the setting: the two were disconnected before.

    The toolkit-free painter every host draws labels with now (the chrome's
    quad painter); the Qt host's ``QPainter`` version drew them for itself
    alone, and the other hosts showed a distance's dashes with no number.
    """
    from chimol.viewport.screen_overlays import DEFAULT_LABEL_SIZE, paint_labels
    from emtk.quad_painter import QuadPainter

    class _Label:
        pos = (0.0, 0.0, 0.0)
        text = "8.92"
        color = (1.0, 1.0, 0.0, 1.0)

    def _project(points):
        n = len(points)
        return np.full(n, 40.0), np.full(n, 40.0), np.ones(n, dtype=bool)

    def _ink(asked):
        """Width and height of the drawn glyph quads, in pixels."""
        painter = QuadPainter()
        assert paint_labels(painter, [_Label()], _project, asked) == 1
        vertices = painter.vertices()
        assert len(vertices), "nothing was drawn"
        xs, ys = vertices[:, 0], vertices[:, 1]
        return float(xs.max() - xs.min()), float(ys.max() - ys.min())

    default_w, default_h = _ink(None)
    big_w, big_h = _ink(DEFAULT_LABEL_SIZE * 2)
    assert big_h > default_h, "asking for a bigger label drew the same size"
    assert big_w > default_w
    # And the default is the shipped one, not the 10 that was hard-coded.
    small_w, small_h = _ink(10.0)
    assert default_h > small_h, "the default is still the hard-coded 10"


def test_a_distance_label_reaches_the_frame():
    """A ``distance`` draws its number on this host too, not only its dashes.

    On a window of its own: the module's shared session is left in whatever
    state the tests above put it.
    """
    from native_window import PDB_148L, NativeWindow

    win = NativeWindow(size=(900, 620))
    try:
        _messages, errors = win.capture_messages()
        # T4 lysozyme: one chain, so each selection is one atom.
        win.run_menu_command(f"load {PDB_148L}")
        win.run_menu_command("distance d1, resi 10 and name CA, resi 40 and name CA")
        win.pump(2)
        assert errors == []
        renderer = win.viewer.renderer
        assert renderer._labels, (
            "the measurement carried no label into the scene: "
            f"{[o.id for o in win.viewer._scene.objects]} {_messages[-2:]}"
        )
        assert renderer._labels[0].text.replace(".", "").isdigit()
        chrome = renderer._chrome_quads()
        under = renderer._with_screen_overlays(None)
        assert under is not None and len(under), "the labels drew no glyphs"
        assert chrome is not None and len(chrome) >= len(under)
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# The pick marker
# --------------------------------------------------------------------------- #
def test_a_measurement_pick_is_marked_and_then_released(session):
    run, win = session
    viewer = win.viewer
    coords = np.asarray(viewer._coords, dtype=float)

    run("wizard measurement")
    try:
        state = viewer.objects[viewer.get_active_object_id()].state
        names = np.array([str(n).strip() for n in state.atoms["atom_name"]])
        ca = [int(i) for i in np.where(names == "CA")[0][:2]]

        before = viewer._selection_atom_positions(coords)
        n_before = 0 if before is None else len(before)

        viewer.pick_hook(ca[0])
        after = viewer._selection_atom_positions(coords)
        assert after is not None and len(after) == n_before + 1, "the first pick drew no marker"
        assert viewer._pick_markers == [ca[0]]

        viewer.pick_hook(ca[1])
        # The pair became a measurement, which is its own drawing.
        assert viewer._pick_markers == []
        done = viewer._selection_atom_positions(coords)
        assert (0 if done is None else len(done)) == n_before
    finally:
        run("wizard delete, all")
        run("wizard done")
        assert viewer._pick_markers == []


def test_a_measurement_with_no_dashes_draws_no_label(session):
    """A number attached to nothing is indistinguishable from one adrift."""
    run, win = session
    viewer = win.viewer
    point = np.zeros((2, 3), dtype=float)
    viewer.measurements = {
        "degenerate": {
            "kind": "distance",
            "positions": point,
            "label": "0.00",
            "color": [1.0, 1.0, 0.0, 1.0],
        }
    }
    try:
        objects = viewer._update_measurements()
        assert not [o for o in objects if o.id.startswith("meas_text_")]
    finally:
        viewer.measurements = {}


# --------------------------------------------------------------------------- #
# The info panel and the in-viewport prompt share a corner
# --------------------------------------------------------------------------- #
def test_the_info_panel_is_laid_out_between_the_strip_and_the_prompt():
    """One object places all three now, so the relation is arithmetic.

    The panel was a ``QPlainTextEdit`` stacked on the surface while the prompt is
    painted *into* it, so Qt could not see the prompt and the panel covered it;
    keeping them apart meant a spacer row in the container's layout sized by
    guessing how tall the prompt would get. `InternalGui` owns both now.

    Driven directly rather than through a window: this is a layout rule, and a
    window whose 3-D view happens to be short is testing something else.
    """
    from chimol.ui.gui import InternalGui

    gui = InternalGui()
    gui.info_visible = True
    gui.info_text = "System: coordinates\nAtoms: 1363\nResidues: 166"
    gui.command_line.visible = True
    gui.layout(900, 600)

    rect = gui._info_rect
    assert rect.w > 0 and rect.h > 0, "the panel was not laid out"
    assert rect.x <= gui.MARGIN + 1, f"expected the left edge, got x={rect.x}"

    top_of_prompt = min(gui._cmd_log_rect.y or gui.command_rect().y, gui.command_rect().y)
    assert rect.y + rect.h <= top_of_prompt, (
        f"the panel reaches {rect.y + rect.h} and the prompt starts at {top_of_prompt}"
    )
    assert rect.y >= gui.sequence_height(), "the panel runs under the strip"


def test_a_viewport_with_no_room_drops_the_panel_rather_than_overlapping():
    """A box over the strip or the prompt is worse than no box.

    That is exactly how the widget this replaced behaved, and the reason it was
    reported: it kept its height and drew over whatever was under it.
    """
    from chimol.ui.gui import InternalGui

    gui = InternalGui()
    gui.info_visible = True
    gui.info_text = "System: coordinates"
    gui.command_line.visible = True
    gui.layout(900, 60)

    assert gui._info_rect.w == 0 and gui._info_rect.h == 0


def test_a_long_path_is_wrapped_rather_than_run_off_the_panel():
    """The info text carries absolute paths, which have no spaces to break at."""
    from chimol.ui.gui import InternalGui

    gui = InternalGui()
    gui.info_visible = True
    gui.info_text = "File: " + "/very_long_directory_name" * 6
    gui.layout(900, 600)

    assert gui._info_lines, "nothing was laid out"
    assert len(gui._info_lines) > 1, "the path was not wrapped"
    assert max(len(line) for line in gui._info_lines) <= gui.INFO_MAX_CHARS


def test_the_panel_pulls_its_text_and_palette_from_the_viewer(session):
    """It is chrome, so it is pulled at paint time rather than pushed."""
    from chimol.ui.gui_state import refresh_gui_state

    _run, win = session
    viewer = win.viewer
    gui = viewer.gui

    viewer.set_system_info_visible(True)
    viewer.set_system_info_text("System: coordinates")
    refresh_gui_state(gui, viewer)

    assert gui.info_visible is True
    assert "System: coordinates" in gui.info_text
    assert set(gui.info_colors) == {"background", "text", "border"}
    assert len(gui.info_colors["background"]) == 4

    viewer.set_system_info_visible(False)
    refresh_gui_state(gui, viewer)
    assert gui.info_visible is False
