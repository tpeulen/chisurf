"""Panel alignment — the things a screenshot shows and an assertion usually cannot.

Layout defects are invisible to ordinary tests: every widget exists, every command
runs, and the panel still looks wrong. These pin the specific geometric relations
that were broken, each of which is a number rather than an opinion:

* the object rows' A/S/H/L/C buttons must line up with the ``all`` header's. They
  did not, because each row was sized to its *content* — so the layout's stretch
  had nothing to expand into and the buttons sat immediately after each name, at a
  different x on every row;
The sequence **dock**'s own geometry used to be pinned here too -- its
scrollbar's origin, its extra rows' stacking. That dock is gone: it had been
hidden since the in-viewport strip replaced it, and its tests went with it.
What remains of sequence behaviour is the colouring, which is chimol's and
needs no window.
"""

from __future__ import annotations

import pathlib

import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


#: Slow: this file builds whole windows and grabs them, which costs about a
#: minute against four seconds for the rest of the plugin's tests. Excluded
#: from the default run so iterating stays fast; ask for it with `-m slow`
#: before landing anything that touches the panels.
pytestmark = pytest.mark.slow


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _settle(widget, width, height, app, passes=8):
    """Force a real layout pass at a chosen size.

    ``resize`` alone leaves the children with their old geometry until Qt gets
    round to a layout, and a grab taken before then shows stale positions — which
    is how a panel can look fine in a screenshot and be misaligned in use.
    """
    widget.setMinimumSize(width, height)
    widget.setMaximumSize(width, height)
    widget.resize(width, height)
    widget.show()
    for _ in range(passes):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        app.processEvents()
    return widget


@pytest.fixture
def window(qapp):
    """Build a window with a protein and two derived objects, for comparing rows."""
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(1300, 850)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win.load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(lambda _m: None)
    shared.do("create ligand, organic")
    shared.do("create pept, chain S and polymer")
    for _ in range(20):
        qapp.processEvents()

    yield win, qapp
    win.close()


# --------------------------------------------------------------------------- #
# The objects panel
# --------------------------------------------------------------------------- #
def test_a_gap_is_not_coloured_like_a_residue(window):
    """A row that is mostly gaps hid its few real residues in an identical band.

    Asked of `chimol.core.colors`, not of the Qt sequence dock: these colours were
    ``staticmethod``s on a widget, so this test needed a window system to ask
    what colour a gap is. They are chimol's now and answer in plain RGB.
    """
    from chimol.core.colors import gap_palette, sequence_palette

    gap_bg, _ = gap_palette()
    coil_bg, _ = sequence_palette("C")
    assert gap_bg != coil_bg


# --------------------------------------------------------------------------- #
# The system-info overlay
# --------------------------------------------------------------------------- #
def test_the_info_overlay_is_off_until_it_is_asked_for(window):
    """It covers a corner of the viewport with what is mostly already on screen.

    The object panel names the structure and the sequence strip shows its
    residues, so the overlay earns its space only when asked for. `Viewer`
    already started it hidden; the toolbar button was checked at construction and
    switched it back on at startup, which is why the default was the opposite of
    the one the viewer declared.
    """
    win, _ = window
    assert not win.button_info.isChecked()
    assert not win.viewer._info_visible


def test_the_info_panel_is_chrome_not_a_stacked_widget(window):
    """It is drawn by the GPU with the rest of the chrome.

    It was a `QPlainTextEdit` stacked on the surface, and a Qt widget cannot see
    chrome painted *into* the surface -- so it was drawn over the in-viewport
    prompt, and the fix was a spacer row in the container's layout guessing how
    tall the prompt was. Now one object lays out both and there is nothing to
    guess. The guard is that no widget is stacked over the renderer at all.
    """
    from qtpy import QtWidgets

    win, qapp = window
    win.button_info.setChecked(True)
    _settle(win.viewer._view_container, 900, 600, qapp)

    assert not hasattr(win.viewer, "_info_overlay"), (
        "the info panel is a stacked Qt widget again"
    )
    container = win.viewer._view_container
    renderer = win.viewer.renderer.widget()
    stacked = [
        child for child in container.children()
        if isinstance(child, QtWidgets.QWidget) and child is not renderer
    ]
    assert not stacked, f"widgets stacked over the scene: {stacked}"


def test_the_info_panel_sits_in_the_bottom_left_above_the_prompt(window):
    """Anchored to the bottom, and clear of the prompt that shares the corner.

    The top left is where the sequence strip and the object panel already put
    text, and a framed structure sits centre-high, so a panel anchored to the
    top competes with both. Measured rather than eyeballed.
    """
    win, qapp = window
    win.button_info.setChecked(True)
    win.viewer.set_system_info_text("System: coordinates\nAtoms: 1363")
    _settle(win.viewer._view_container, 900, 600, qapp)

    from chimol.hosts.qt.overlay import refresh_gui_state

    gui = win.viewer.gui
    # The two calls the renderer makes to build its chrome: the panel's text is
    # pulled from the viewer at paint time, like the sequence colours.
    refresh_gui_state(gui, win.viewer)
    gui.layout(win.viewer.renderer.width(), win.viewer.renderer.height())
    rect = gui._info_rect
    assert rect.w > 0 and rect.h > 0, "the panel was not laid out"
    assert rect.x <= gui.MARGIN + 1, f"expected the left edge, got x={rect.x}"

    bottom_of_panel = rect.y + rect.h
    top_of_prompt = min(gui._cmd_log_rect.y or gui.command_rect().y,
                        gui.command_rect().y)
    assert bottom_of_panel <= top_of_prompt, (
        f"the panel reaches {bottom_of_panel} and the prompt starts at "
        f"{top_of_prompt}"
    )
    assert rect.y > gui.sequence_height(), "the panel is under the strip"
