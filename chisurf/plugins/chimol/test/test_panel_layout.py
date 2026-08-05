"""Panel alignment — the things a screenshot shows and an assertion usually cannot.

Layout defects are invisible to ordinary tests: every widget exists, every command
runs, and the panel still looks wrong. These pin the specific geometric relations
that were broken, each of which is a number rather than an opinion:

* the object rows' A/S/H/L/C buttons must line up with the ``all`` header's. They
  did not, because each row was sized to its *content* — so the layout's stretch
  had nothing to expand into and the buttons sat immediately after each name, at a
  different x on every row;
* the sequence scrollbar must begin where the sequence begins, not at the far left
  of the dock, or its travel is out of step with the letters it scrolls;
* the extra sequence rows must sit directly under the sequence, not float below a
  gap left by the last widget absorbing the dock's spare height.
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
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(1300, 850)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
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
def _button_right_edge(widget, key, reference):
    """Return a menu button's right edge, in ``reference``'s coordinates."""
    from qtpy import QtCore

    button = widget.buttons[key] if hasattr(widget, "buttons") else widget
    corner = button.mapTo(reference, QtCore.QPoint(button.width(), 0))
    return corner.x()


def test_every_row_spans_the_list(window):
    """A row sized to its content leaves the stretch nothing to work with."""
    win, qapp = window
    _settle(win.objects.widget, 900, 150, qapp)
    listing = win.objects.object_list

    assert listing.count() >= 3
    viewport = listing.viewport().width()
    for index in range(listing.count()):
        row = listing.itemWidget(listing.item(index))
        assert row is not None
        # Within the list's own item inset, but nothing like content-width.
        assert row.width() > viewport * 0.9


def test_the_menu_buttons_line_up_across_rows(window):
    """Different names must not put the buttons at different x."""
    win, qapp = window
    panel = _settle(win.objects.widget, 900, 150, qapp)
    listing = win.objects.object_list

    edges = set()
    for index in range(listing.count()):
        row = listing.itemWidget(listing.item(index))
        edges.add(_button_right_edge(row._menus, "C", panel))
    assert len(edges) == 1, f"rows disagree about where the buttons go: {edges}"


def test_the_rows_line_up_with_the_all_header(window):
    """The header is an ordinary widget and always spanned; the rows did not.

    They still differ by the list's vertical scrollbar, which the header reserves
    space for -- so the two columns agree whether or not the bar is showing.
    """
    win, qapp = window
    panel = _settle(win.objects.widget, 900, 150, qapp)
    listing = win.objects.object_list

    header_edge = _button_right_edge(win.objects._all_menus, "C", panel)
    row = listing.itemWidget(listing.item(0))
    row_edge = _button_right_edge(row._menus, "C", panel)
    assert abs(header_edge - row_edge) <= 2


def test_widening_the_panel_keeps_them_aligned(window):
    """The rows are sized to the viewport, so a resize has to re-stretch them."""
    win, qapp = window
    for width in (700, 1100):
        panel = _settle(win.objects.widget, width, 150, qapp)
        listing = win.objects.object_list
        header_edge = _button_right_edge(win.objects._all_menus, "C", panel)
        row = listing.itemWidget(listing.item(0))
        assert abs(header_edge - _button_right_edge(row._menus, "C", panel)) <= 2


# --------------------------------------------------------------------------- #
# The sequence dock
# --------------------------------------------------------------------------- #
def test_the_scrollbar_starts_where_the_sequence_starts(window):
    """It spanned the label column too, so its travel did not match the letters."""
    from qtpy import QtCore

    win, qapp = window
    dock = _settle(win.sequence.widget, 1000, 140, qapp)

    bar_x = win.seq_scrollbar.mapTo(dock, QtCore.QPoint(0, 0)).x()
    seq_x = win.seq_list.mapTo(dock, QtCore.QPoint(0, 0)).x()
    assert abs(bar_x - seq_x) <= 2


def test_the_scrollbar_is_as_wide_as_the_sequence(window):
    win, qapp = window
    _settle(win.sequence.widget, 1000, 140, qapp)
    assert abs(win.seq_scrollbar.width() - win.seq_list.width()) <= 2


def test_extra_rows_sit_directly_under_the_sequence(window):
    """The last widget was absorbing the dock's spare height and pushing them down."""
    from qtpy import QtCore

    win, qapp = window
    dock = _settle(win.sequence.widget, 1000, 140, qapp)

    sequence_bottom = win.seq_list.mapTo(dock, QtCore.QPoint(0, win.seq_list.height())).y()
    rows = list(win._sequence_rows.values())
    assert rows, "the derived objects should each have a sequence row"
    first_row_top = min(
        info["list"].mapTo(dock, QtCore.QPoint(0, 0)).y() for info in rows
    )
    assert 0 <= first_row_top - sequence_bottom <= 12


def test_the_rows_are_evenly_stacked(window):
    """Uneven spacing reads as a broken panel even when every row is present."""
    from qtpy import QtCore

    win, qapp = window
    dock = _settle(win.sequence.widget, 1000, 140, qapp)
    tops = sorted(
        info["list"].mapTo(dock, QtCore.QPoint(0, 0)).y()
        for info in win._sequence_rows.values()
    )
    if len(tops) < 2:
        pytest.skip("needs at least two derived objects")
    gaps = [b - a for a, b in zip(tops, tops[1:])]
    assert max(gaps) - min(gaps) <= 2


# --------------------------------------------------------------------------- #
# What the rows say
# --------------------------------------------------------------------------- #
def test_an_object_with_no_sequence_says_so(window):
    """It used to draw a hundred and seventy identical dashes instead."""
    win, _ = window
    ligand = next(
        info for oid, info in win._sequence_rows.items()
        if info["button"].text() == "ligand"
    )
    listing = ligand["list"]
    assert listing.count() == 1
    assert "no sequence" in listing.item(0).text()


def test_a_partly_aligned_object_keeps_its_columns(window):
    """The padding is what aligns residue i of one object over residue i of another.

    So an object that *does* contribute residues keeps the full-width row -- only
    one contributing nothing collapses to a note.
    """
    win, _ = window
    peptide = next(
        info for oid, info in win._sequence_rows.items()
        if info["button"].text() == "pept"
    )
    listing = peptide["list"]
    assert listing.count() == win.seq_list.count()
    letters = {listing.item(i).text() for i in range(listing.count())}
    assert letters - {"-", "."}, "it should contribute at least one residue"


def test_a_gap_is_not_coloured_like_a_residue(window):
    """A row that is mostly gaps hid its few real residues in an identical band."""
    from chisurf.plugins.chimol.chimol.app.sequence_dock import SequenceDock

    gap_bg, _ = SequenceDock.gap_palette()
    coil_bg, _ = SequenceDock.default_sequence_palette("C")
    assert gap_bg != coil_bg


# --------------------------------------------------------------------------- #
# The system-info overlay
# --------------------------------------------------------------------------- #
def test_the_info_overlay_is_off_until_it_is_asked_for(window):
    """It covers a corner of the viewport with what is mostly already on screen.

    The object panel names the structure and the sequence strip shows its
    residues, so the overlay earns its space only when asked for. `MolView`
    already started it hidden; the toolbar button was checked at construction and
    switched it back on at startup, which is why the default was the opposite of
    the one the viewer declared.
    """
    win, _ = window
    assert not win.button_info.isChecked()
    assert not win.viewer._info_visible
    assert not win.viewer._info_overlay.isVisible()


def test_the_info_overlay_sits_in_the_bottom_left(window):
    """Anchored to the bottom, not the top.

    The top left is where the sequence strip and the object panel already put
    text, and a framed structure sits centre-high, so an overlay anchored to the
    top competes with both. Measured rather than eyeballed: a widget aligned to
    the wrong edge is invisible to a test that only asks whether it exists.
    """
    win, qapp = window
    win.button_info.setChecked(True)
    _settle(win.viewer._container, 900, 600, qapp)

    overlay = win.viewer._info_overlay
    container = win.viewer._container
    assert overlay.isVisible()

    geom = overlay.geometry()
    assert geom.left() <= 1, f"expected the left edge, got x={geom.left()}"
    below = container.height() - geom.bottom()
    assert below <= 2, f"expected the bottom edge, {below}px of gap below it"
    assert geom.top() > container.height() // 2, (
        "the overlay should hang from the bottom, not fill the viewport"
    )
