"""The structure hierarchy, drawn in the viewport.

The Qt dock is a `QTreeView` over a model with per-node check boxes. This reads
the **same `HierarchyNode` tree** — not a copy — and draws it through the six
painter operations, so it runs on the desktop and in the browser from one
implementation.

The behaviour worth pinning is the one the tri-state check boxes expressed:
switching a node off takes its **subtree** with it, and what reaches the viewer
is the set of coordinate rows those nodes cover.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chimol.core.hierarchy import HierarchyNode  # noqa: E402
from chimol.plugins.hierarchy.window import HierarchyWindow  # noqa: E402
from chimol.chrome.gui import InternalGui  # noqa: E402


class _Recorder:
    def __init__(self):
        self.texts: list[str] = []

    def fill_rect(self, *a, **k):
        pass

    def stroke_rect(self, *a, **k):
        pass

    def gradient_rect(self, *a, **k):
        pass

    def text(self, x, y, w, h, align, text, colour):
        self.texts.append(str(text))

    def push_clip(self, *a, **k):
        pass

    def pop_clip(self, *a, **k):
        pass


def _node(name, kind, children=(), atoms=()):
    node = HierarchyNode(name=name, node_type=kind)
    node.atom_indices = list(atoms)
    for child in children:
        node.children.append(child)
        child.parent = node
    return node


@pytest.fixture
def panel():
    tree = _node("NPC", "assembly", [
        _node("Nup84", "molecule", [
            _node("A", "chain", [
                _node("1", "residue", atoms=[0, 1]),
                _node("2", "residue", atoms=[2, 3]),
            ]),
        ]),
        _node("Nup85", "molecule", [
            _node("B", "chain", [_node("1", "residue", atoms=[4, 5])]),
        ]),
    ])

    class _State:
        rmf_hierarchy = tree

    class _Entry:
        state = _State()

    class _Viewer:
        objects = {"o1": _Entry()}

        def get_active_object_id(self):
            return "o1"

    applied: list[list[int]] = []
    applied_to: list[str | None] = []

    # `on_change` carries the id of the object the tree belongs to: hiding
    # used to be applied to the *active* object, which is the map when a map
    # was loaded last -- the checkbox then toggled nothing visible.
    def _apply(rows, object_id=None):
        applied.append(rows)
        applied_to.append(object_id)

    window = HierarchyWindow(_Viewer(), on_change=_apply)
    gui = InternalGui(run_command=lambda _c: None)
    frame = gui.add_window(window.window())
    gui.layout(820, 520)
    window.draw(_Recorder(), gui.window_body(frame))
    return window, gui, applied


def _row(panel, name):
    for node, depth, rect, indent in panel._rows:
        if node.name == name:
            return node, depth, rect, indent
    raise AssertionError(f"no row for {name}")


def test_only_the_top_levels_are_open_to_begin_with(panel):
    """The default is depth-based, and that is a performance decision.

    Fully expanded, a nuclear pore's tree flattens to ~200 000 rows and the
    walk cost 327 ms -- paid on **every repaint**, so the viewport stuttered
    while the camera moved. Shut, the first draw is 0.2 ms.
    """
    window, _gui, _applied = panel
    assert [(n.name, d) for n, d, _r, _i in window._rows] == [
        ("NPC", 0), ("Nup84", 1), ("Nup85", 1),
    ]


def test_the_arrow_opens_and_shuts_the_subtree(panel):
    window, gui, _applied = panel
    _node_, _d, rect, indent = _row(window, "Nup84")
    press = (indent + 4, rect.y + rect.h / 2)

    gui.mouse_press(*press)
    gui.release()
    window.draw(_Recorder(), gui.window_body(gui.window("hierarchy")))
    names = [n.name for n, _d, _r, _i in window._rows]
    assert "A" in names, "the arrow did not open the subtree"
    assert "Nup85" in names, "opening took a sibling with it"

    gui.mouse_press(*press)
    gui.release()
    window.draw(_Recorder(), gui.window_body(gui.window("hierarchy")))
    names = [n.name for n, _d, _r, _i in window._rows]
    assert "A" not in names, "the arrow did not shut it again"
    assert "Nup85" in names


def test_switching_a_node_off_takes_its_subtree(panel):
    """What the Qt panel's tri-state check boxes expressed."""
    window, gui, applied = panel
    _node_, _d, rect, indent = _row(window, "Nup85")

    gui.mouse_press(indent + 16, rect.y + rect.h / 2)
    gui.release()

    assert applied, "nothing reached the viewer"
    assert applied[-1] == [4, 5], applied[-1]


def test_switching_it_back_on_restores_everything(panel):
    window, gui, applied = panel
    _node_, _d, rect, indent = _row(window, "Nup85")
    press = (indent + 16, rect.y + rect.h / 2)

    gui.mouse_press(*press)
    gui.release()
    assert applied[-1] == [4, 5]

    gui.mouse_press(*press)
    gui.release()
    assert applied[-1] == []


def test_a_press_on_the_label_changes_nothing(panel):
    """Only the arrow and the box act; the row is not a hit target itself."""
    window, gui, applied = panel
    _node_, _d, rect, indent = _row(window, "Nup85")
    before = len(applied)
    gui.mouse_press(indent + 120, rect.y + rect.h / 2)
    gui.release()
    assert len(applied) == before


def test_it_says_so_when_there_is_no_tree():
    class _Viewer:
        objects = {}

        def get_active_object_id(self):
            return None

    window = HierarchyWindow(_Viewer())
    painter = _Recorder()
    from chimol.chrome.gui import Rect

    window.draw(painter, Rect(0, 0, 300, 200))
    assert any("Nothing loaded" in text for text in painter.texts)
    assert window._rows == []
    # The field is drawn **before** the tree is looked up. It was drawn after,
    # so an empty viewer showed one sentence and no box -- and "the filter does
    # not work" was literally true: there was nothing to type into.
    assert window._search_rect is not None


# --------------------------------------------------------------------------- #
# The search box
# --------------------------------------------------------------------------- #
def _names(window):
    return [node.name for node, _d, _r, _i in window._rows]


def _redraw(window, gui):
    window.draw(_Recorder(), gui.window_body(gui.window("hierarchy")))


def test_clicking_the_field_takes_the_caret(panel):
    """Text entry in a painted panel needs somewhere for the key to go."""
    window, gui, _applied = panel
    window.attach(gui)
    box = window._search_rect
    assert box is not None, "the field was not laid out"

    gui.mouse_press(box.x + 10, box.y + box.h / 2)
    gui.release()
    assert gui.focused_field is window.search


def test_typing_filters_the_tree(panel):
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "nup85":
        assert gui.key_press(0, character, 0), "the field did not take the key"
    _redraw(window, gui)

    names = _names(window)
    assert "Nup85" in names
    assert "Nup84" not in names


def test_a_match_brings_its_whole_subtree(panel):
    """Searching for a chain must bring the chain's residues.

    Getting the chain with no residues in it is not the chain.
    """
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "nup85":
        gui.key_press(0, character, 0)
    _redraw(window, gui)

    names = _names(window)
    assert "B" in names and "1" in names, names


def test_a_match_keeps_its_ancestors(panel):
    """A hit three levels down is unreachable if its parents are filtered out."""
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "nup84":
        gui.key_press(0, character, 0)
    _redraw(window, gui)
    assert _names(window)[0] == "NPC"


def test_no_match_shows_nothing_rather_than_everything(panel):
    """An empty result is empty -- not the unfiltered tree.

    Ported from the Qt dock's filter tests when that dock was deleted: the
    proxy model made this free and a hand-written walk does not.
    """
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "does-not-exist":
        gui.key_press(0, character, 0)
    _redraw(window, gui)
    assert _names(window) == []


def test_the_search_is_case_insensitive(panel):
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "nUp84":
        gui.key_press(0, character, 0)
    _redraw(window, gui)
    assert "Nup84" in _names(window)


def test_filtering_does_not_change_what_is_drawn(panel):
    """A search must not hide a single bead.

    What is *typed* never touches what is *switched off*. That separation is
    why the Qt panel put a proxy model between the tree and the view.
    """
    window, gui, applied = panel
    window.attach(gui)
    before = len(applied)
    gui.focus_field(window.search)
    for character in "nup85":
        gui.key_press(0, character, 0)
    _redraw(window, gui)
    assert len(applied) == before, "a search reached the viewer"


def test_backspace_clears_and_the_tree_comes_back(panel):
    from chimol.hosts.keys import KEY_BACKSPACE

    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    for character in "nup85":
        gui.key_press(0, character, 0)
    for _ in range(5):
        gui.key_press(KEY_BACKSPACE, "", 0)
    _redraw(window, gui)

    assert window.search.text == ""
    assert "Nup84" in _names(window)


def test_escape_gives_the_keyboard_back(panel):
    """Otherwise every shortcut is swallowed by a box nobody is looking at."""
    from chimol.hosts.keys import KEY_ESCAPE

    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    assert gui.key_press(KEY_ESCAPE, "", 0)
    assert gui.focused_field is None


def test_clicking_a_row_gives_the_keyboard_back(panel):
    """Typing after clicking a row must reach the shortcuts, not the search."""
    window, gui, _applied = panel
    window.attach(gui)
    gui.focus_field(window.search)
    _node_, _d, rect, indent = _row(window, "Nup85")

    gui.mouse_press(indent + 16, rect.y + rect.h / 2)
    gui.release()
    assert gui.focused_field is None


def test_a_focused_field_takes_the_key_from_the_prompt(panel):
    """Two carets on screen is two places a keystroke could be going."""
    window, gui, _applied = panel
    window.attach(gui)
    gui.command_line.visible = True
    gui.focus_command(True)

    gui.focus_field(window.search)
    assert not gui.command_line.focused

    gui.key_press(0, "x", 0)
    assert window.search.text == "x"
    assert gui.command_line.text == ""


# --------------------------------------------------------------------------- #
# The scroll bar
# --------------------------------------------------------------------------- #
def test_a_tree_taller_than_the_window_gets_a_bar(panel):
    """A wheel is not discoverable.

    A panel with no bar says nothing about how much of itself you are
    looking at.
    """
    window, gui, _applied = panel
    from chimol.chrome.gui import Rect

    window.draw(_Recorder(), Rect(0, 0, 300, 200))
    assert window._bar is None, "a tree that fits does not get a bar"

    for molecule in window._root().children:
        window._expanded.add(id(molecule))
    window.draw(_Recorder(), Rect(0, 0, 300, 60))
    assert window._bar is not None


def test_dragging_the_bar_scrolls(panel):
    window, gui, _applied = panel
    from chimol.chrome.gui import Rect

    for molecule in window._root().children:
        window._expanded.add(id(molecule))
    rect = Rect(0, 0, 300, 60)
    window.draw(_Recorder(), rect)
    bar = window._bar

    assert window.press(bar.x + 2, bar.y + 2, rect), "the bar must claim the drag"
    window.drag(bar.x + 2, bar.y + bar.h, rect)
    assert window._scroll > 0
    window.release()
    assert window._bar_drag is None


# --------------------------------------------------------------------------- #
# A structure with no RMF tree
# --------------------------------------------------------------------------- #
def test_a_plain_structure_gets_a_chain_tree():
    """Object → chain → residue, built from the atom table.

    Without this the panel answered *"No hierarchy"* for every PDB, which is
    every structure most people open.
    """
    import numpy as np

    atoms = np.zeros(4, dtype=[
        ("chain", "U2"), ("res_id", "i8"), ("res_name", "U4"),
    ])
    atoms["chain"] = ["A", "A", "B", "B"]
    atoms["res_id"] = [1, 2, 1, 1]
    atoms["res_name"] = ["MET", "ALA", "GLY", "GLY"]

    class _State:
        rmf_hierarchy = None

    _State.atoms = atoms

    class _Entry:
        state = _State()
        name = "1abc"

    class _Viewer:
        objects = {"o1": _Entry()}

        def get_active_object_id(self):
            return "o1"

    window = HierarchyWindow(_Viewer())
    root = window._root()
    assert root is not None
    assert root.name == "1abc", "the display name, not the internal object id"
    assert [child.name for child in root.children] == ["A", "B"]
    assert [leaf.name for leaf in root.children[0].children] == ["MET1", "ALA2"]
    assert root.children[1].children[0].atom_indices == [2, 3]
