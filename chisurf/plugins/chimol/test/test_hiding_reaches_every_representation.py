"""What the hierarchy switches off leaves the picture -- in every depiction.

"hierarchy seems to do nothing", then, with a screenshot of a biofilm with
every box unchecked and the spheres still on screen: "all eles in hier turned
off why still displaying".

Wiring the panel to the viewer was only the first half. The second was that a
depiction's rows and a depiction's *visibility* were two questions asked in
different places: each builder read its own mask (``cartoon_mask``,
``ball_mask``, ``lines_mask`` …), and consulting ``visible_row_mask`` on top of
it was a convention three of the nineteen builders followed. So the mask went
to all-hidden and the cartoon, the spheres, the wireframe, the surface and the
dots carried on drawing -- while ``get_atom_sphere_data`` dutifully reported
nothing, which is how the fault stayed invisible to the tests that existed.

``Viewer.drawable_rows`` is now the one place the question is answered, and it
answers both halves including the trap that hid the fault: ``None`` (no scope)
means *every drawable row*, not *every row*. It also bridges the two row
spaces -- hiding is per atom, half the depictions are per residue -- because a
composition by length alone silently agreed to everything.

This file is the guard. It drives each depiction on a real structure through
the real panel and asserts the geometry handed to the renderer goes away and
comes back, so a builder that forgets is a red test rather than a report with a
screenshot.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

#: Every built-in depiction that draws from coordinate rows. ``nonbonded``
#: is left out on purpose: 148l has no unbonded atoms, so it draws nothing to
#: begin with and the check would pass without meaning anything.
DEPICTIONS = ("cartoon", "spheres", "sticks", "lines", "surface", "dots")

SCRIPT = '''
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("load 148l.pdb")
cmd.do("hierarchy_panel")
app.renderer._draw()
panel = gui.panels.get("hierarchy")
root = panel._root()

def drawn():
    scene = viewer._scene
    return sum(len(getattr(o.geometry, "positions", ()))
               for o in (getattr(scene, "objects", None) or ()))

for rep in %(reps)r:
    cmd.do("hide everything")
    cmd.do("show " + rep)
    app.renderer._draw()
    full = drawn()
    panel._toggle(root)                 # everything off
    app.renderer._draw()
    off = drawn()
    panel._toggle(root)                 # everything back on
    app.renderer._draw()
    emit(rep, "%%d %%d %%d" %% (full, off, drawn()))
''' % {"reps": list(DEPICTIONS)}

PARTIAL = '''
app = open_app(size=(900, 600))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("load 148l.pdb")
cmd.do("hide everything")
cmd.do("show cartoon")
cmd.do("hierarchy_panel")
app.renderer._draw()
panel = gui.panels.get("hierarchy")
root = panel._root()

def drawn():
    scene = viewer._scene
    return sum(len(getattr(o.geometry, "positions", ()))
               for o in (getattr(scene, "objects", None) or ()))

emit("full", drawn())
chain = (getattr(root, "children", None) or [None])[0]
residues = (getattr(chain, "children", None) or [])[:40]
for node in residues:
    panel._toggle(node)
app.renderer._draw()
emit("some_off", drawn())
emit("residues_off", len(residues))
for node in residues:
    panel._toggle(node)
app.renderer._draw()
emit("restored", drawn())
'''


@pytest.fixture(scope="module")
def ran():
    return probe(SCRIPT, timeout=900)


@pytest.mark.parametrize("rep", DEPICTIONS)
def test_switching_everything_off_empties_the_picture(ran, rep):
    full, off, back = (int(v) for v in ran[rep].split())
    assert full > 0, f"{rep} drew nothing to begin with -- the check is vacuous"
    assert off == 0, (
        f"{rep} still handed {off} vertices to the renderer with every row hidden"
    )


@pytest.mark.parametrize("rep", DEPICTIONS)
def test_switching_it_back_on_restores_the_picture(ran, rep):
    full, _off, back = (int(v) for v in ran[rep].split())
    assert back == full, f"{rep} came back different: {back} vs {full}"


@pytest.fixture(scope="module")
def partial():
    return probe(PARTIAL, timeout=600)


def test_hiding_part_of_a_chain_hides_part_of_the_cartoon(partial):
    """Per-atom hiding, per-residue depiction: the two row spaces have to meet."""
    full, some = int(partial["full"]), int(partial["some_off"])
    assert int(partial["residues_off"]) > 0
    assert 0 < some < full, (
        "the cartoon is unchanged by switching forty of its residues off"
    )
    assert int(partial["restored"]) == full


def test_the_question_has_one_answer():
    """`drawable_rows` is the viewer's, and it composes both halves."""
    import numpy as np

    from chimol.core.viewer import Viewer

    assert callable(Viewer.drawable_rows)
    source = Viewer.drawable_rows.__doc__ or ""
    assert "visible_row_mask" in source, "the resolver stopped documenting what it composes"
