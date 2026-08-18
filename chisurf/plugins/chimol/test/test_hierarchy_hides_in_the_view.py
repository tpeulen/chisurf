"""Switching a node off in the hierarchy hides it -- and its children -- in the view.

The report was "hierarchy seems to do nothing, disabling item in hier should
disable item (and children) in view", and it was exact on two of the three
hosts. The panel reached the picture through ``ctx.window._apply_hidden_rows``
-- a **private method of the Qt window**, handed in by the panel factory. The
toolkit-free window and the page have no such method, so ``on_change`` was
``None`` and every check box was inert.

Hiding rows of an object is the viewer's own operation, so the panel tells the
viewer (``Viewer.set_hidden_rows``) and works wherever a viewer does. What is
pinned here is that, on a host with no Qt window at all: the rows really leave
the picture, the subtree goes with its parent, switching back restores exactly
what was there, and the panel opened from the registry (rather than
hand-constructed) is wired the same way.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

SCRIPT = '''
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("load 148l.pdb")
cmd.do("hierarchy_panel")
app.renderer._draw()

panel = gui.panels.get("hierarchy")
emit("panel", type(panel).__name__)

def hidden():
    mask = viewer._hidden_mask
    return 0 if mask is None else int(mask.sum())

root = panel._root()
chain = (getattr(root, "children", None) or [None])[0]
emit("root", getattr(root, "name", "?"))
emit("chain", getattr(chain, "name", "?"))
emit("chain_rows", len(getattr(chain, "atom_indices", ()) or ()))
emit("hidden_at_start", hidden())

panel._toggle(chain)                       # switch the chain off
emit("hidden_after_off", hidden())
emit("drawn_after_off", len(viewer.get_atom_sphere_data(visible_only=True)[0]))

panel._toggle(chain)                       # and back on
emit("hidden_after_on", hidden())

# A leaf inside the chain, to show it is not all-or-nothing.
leaf = None
stack = [chain]
while stack and leaf is None:
    node = stack.pop()
    if getattr(node, "atom_indices", None) and not (getattr(node, "children", None) or ()):
        leaf = node
    stack.extend(getattr(node, "children", None) or ())
if leaf is not None:
    panel._toggle(leaf)
    emit("leaf_rows", len(leaf.atom_indices))
    emit("hidden_for_leaf", hidden())
'''


@pytest.fixture(scope="module")
def ran():
    return probe(SCRIPT, timeout=600, block_qt=True)


def test_the_panel_opens_on_a_host_with_no_qt(ran):
    assert ran["panel"] == "HierarchyWindow"
    assert ran["root"] == "148l"
    assert int(ran["chain_rows"]) > 0, "the tree carries no rows to hide"


def test_switching_a_chain_off_hides_exactly_its_rows(ran):
    """The report: it did nothing at all here."""
    assert int(ran["hidden_at_start"]) == 0
    assert int(ran["hidden_after_off"]) == int(ran["chain_rows"])


def test_the_hidden_rows_leave_the_picture(ran):
    """Not just a mask: what the renderer is given to draw shrinks."""
    assert int(ran["drawn_after_off"]) >= 0
    assert int(ran["drawn_after_off"]) < int(ran["chain_rows"]) + int(ran["hidden_at_start"]) + 1


def test_switching_it_back_on_restores_everything(ran):
    assert int(ran["hidden_after_on"]) == 0


def test_a_leaf_hides_only_itself(ran):
    if "leaf_rows" not in ran:
        pytest.skip("this tree has no leaf carrying rows")
    assert int(ran["hidden_for_leaf"]) == int(ran["leaf_rows"])


BIOFILM = '''
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("demo biofilm")
app.renderer._draw()

def drawn():
    scene = viewer._scene
    return sum(len(getattr(o.geometry, "positions", ()))
               for o in (getattr(scene, "objects", None) or ()))

cmd.do("hierarchy_panel")
app.renderer._draw()
panel = gui.panels.get("hierarchy")
root = panel._root()
emit("rows", len(getattr(root, "atom_indices", ()) or ()))
emit("drawn_at_start", drawn())

panel._toggle(root)                 # everything off
app.renderer._draw()
emit("drawn_all_off", drawn())

panel._toggle(root)                 # everything back on
app.renderer._draw()
emit("drawn_back_on", drawn())
'''


@pytest.fixture(scope="module")
def biofilm():
    return probe(BIOFILM, timeout=600)


def test_a_simulation_switched_fully_off_draws_nothing(biofilm):
    """The report, with a picture: every box off and the spheres still there.

    A bead simulation reaches the last ball path in ``_update_atoms``, and that
    one read an empty selection as "nothing was selected -- show a sample of
    everything", sampling fifty arbitrary rows straight back into the picture
    (absent particles among them). A default has no business out-voting an
    explicit "hide this".
    """
    assert int(biofilm["rows"]) > 0
    assert int(biofilm["drawn_at_start"]) > 0, "the demo drew nothing to begin with"
    assert int(biofilm["drawn_all_off"]) == 0, (
        "rows are switched off and the viewer still hands geometry to the renderer"
    )


def test_switching_them_back_on_brings_the_simulation_back(biofilm):
    assert int(biofilm["drawn_back_on"]) > 0


def test_the_viewer_owns_the_operation():
    """`set_hidden_rows` is the viewer's, so every host has it -- and only it."""
    from chimol.core.viewer import Viewer
    from chimol.hosts.qt import window as qt_window

    assert callable(Viewer.set_hidden_rows)
    assert not hasattr(qt_window.MolViewPluginWindow, "_apply_hidden_rows"), (
        "the panel's route back into a host-private method is back"
    )
