"""A representation's mask is indexed by what the registry says it is.

Every representation scopes itself with a mask naming which rows of the object
it draws, and the rows are either the object's **atoms** or the **residues** of
its guide trace -- 1363 and 163 of them for 148L. Which one is a property of
the representation, and it was written nowhere: each writer sized its mask from
whichever array was to hand.

So ``hide everything`` sized ``ball_mask`` from ``state.coords``, the residue
trace, and wrote 163 booleans into a per-atom field; and switching one residue
to spheres -- what the GUI does when you change a residue's representation --
wrote a residue-indexed mask *and threw the object's existing sphere scope
away*, because the lengths disagreed. Nothing raised: every reader guards on
the length and falls back when it does not match, so the spheres quietly
stopped being scoped, the ray tracer traced the whole molecule for a scene
showing one ligand, and changing one residue's representation changed what the
others drew.

The fix is a declaration rather than a guard:
``BUILTIN_REPRESENTATIONS`` names, for every representation, the state it
scopes itself with and the domain that state is indexed by -- and the seven
hand-written lists that used to hold pieces of this (three in the show/hide
command alone) read it instead.
"""
from __future__ import annotations

import pytest

from chimol.core.services.representations import (
    ATOMS,
    BUILTIN_REPRESENTATIONS,
    REPRESENTATIONS,
    RESIDUES,
)
from toolkit_free import probe


pytestmark = pytest.mark.usefixtures("bond_family")


# --------------------------------------------------------------------------- #
# The registry itself
# --------------------------------------------------------------------------- #
def test_every_builtin_declares_where_its_state_lives():
    for spec in BUILTIN_REPRESENTATIONS:
        assert spec.flag_field, f"{spec.name} has no visibility flag"
        assert spec.setter, f"{spec.name} has no whole-object setter"
        assert spec.domain in (ATOMS, RESIDUES), spec.name


def test_the_ribbon_is_the_trace_and_the_spheres_are_the_atoms():
    """PyMOL's spellings, resolved in one place instead of five."""
    for alias, name in (
        ("spheres", "atoms"), ("balls", "atoms"), ("ball", "atoms"),
        ("ribbon", "trace"), ("ca_trace", "trace"), ("ribbon_trace", "trace"),
        ("licorice", "sticks"), ("bonds", "sticks"),
        ("wire", "lines"), ("wireframe", "lines"),
        ("nb_spheres", "nonbonded"), ("points", "dots"),
        ("surf", "surface"), ("mesh", "metaball"), ("metaballs", "metaball"),
        ("label", "labels"), ("grid", "plane"),
    ):
        spec = REPRESENTATIONS.get(alias)
        assert spec is not None and spec.name == name, f"{alias} -> {spec}"


def test_the_cartoon_and_the_trace_are_the_per_residue_ones():
    assert REPRESENTATIONS.get("cartoon").domain == RESIDUES
    assert REPRESENTATIONS.get("trace").domain == RESIDUES
    for name in ("atoms", "sticks", "lines", "nonbonded", "dots", "surface",
                 "metaball", "labels"):
        assert REPRESENTATIONS.get(name).domain == ATOMS, name


def test_a_name_that_cannot_be_scoped_says_so():
    """`plane` is whole-object; asking for its mask field must not invent one."""
    assert REPRESENTATIONS.scoped("plane") is None
    assert REPRESENTATIONS.scoped("spheres") is not None


def test_the_atom_indexed_field_list_agrees_with_the_registry():
    """`analysis/` may not import `core`, so the two are checked against here.

    ``atom_order.ATOM_INDEXED_FIELDS`` is what a reorder permutes with the
    atoms. A residue-domain mask in that list would be permuted by an atom
    ordering -- and an atom-domain one left out would not be permuted at all.
    """
    from chimol.analysis.atom_order import ATOM_INDEXED_FIELDS

    for spec in BUILTIN_REPRESENTATIONS:
        if not spec.mask_field:
            continue
        if spec.domain == ATOMS:
            assert spec.mask_field in ATOM_INDEXED_FIELDS, spec.mask_field
        else:
            assert spec.mask_field not in ATOM_INDEXED_FIELDS, spec.mask_field


def test_a_stored_scene_carries_every_representations_state():
    """The bookmark's field list is the registry's, not a copy of it."""
    from chimol.core.services.views import _REPRESENTATION_FIELDS

    for spec in BUILTIN_REPRESENTATIONS:
        for field in (spec.flag_field, spec.mask_field):
            if field:
                assert field in _REPRESENTATION_FIELDS, f"{spec.name}: {field}"


def test_every_representation_can_be_completed():
    from chimol.commands.completion import REPRESENTATIONS as COMPLETIONS

    for spec in BUILTIN_REPRESENTATIONS:
        assert spec.name in COMPLETIONS, spec.name


def test_the_command_no_longer_carries_its_own_lists():
    """Three of them lived in `_toggle_representation` alone."""
    import inspect

    from chimol.commands.builtin.rendering import RenderingMixin

    source = inspect.getsource(RenderingMixin._toggle_representation)
    for gone in ('"ball_mask"', '"set_cartoon_visible"', "_ALL_REPRESENTATIONS",
                 '"nb_spheres"'):
        assert gone not in source, f"the command still keeps its own table: {gone}"


# --------------------------------------------------------------------------- #
# ...and the masks that are actually written
# --------------------------------------------------------------------------- #
SCRIPT = '''
import numpy as np
app = open_app(size=(700, 500))
cmd, viewer = app.cmd, app.viewer
cmd.do("load 148l.pdb")
key = list(viewer.objects)[0]
state = viewer.objects[key].state
n_atoms = int(np.asarray(state.all_atom_coords).shape[0])
n_res = int(np.asarray(state.coords).shape[0])
emit("n_atoms", n_atoms)
emit("n_residues", n_res)

from chimol.core.services.representations import BUILTIN_REPRESENTATIONS, RESIDUES
expected = {spec.mask_field: (n_res if spec.domain == RESIDUES else n_atoms)
            for spec in BUILTIN_REPRESENTATIONS if spec.mask_field}

def wrong_domains():
    bad = []
    for field, want in expected.items():
        mask = getattr(state, field, None)
        if mask is not None and int(np.asarray(mask).size) != want:
            bad.append("%s=%d want %d" % (field, np.asarray(mask).size, want))
    return ",".join(bad) or "none"

# Every way there is of turning a representation on and off.
cmd.do("hide everything"); viewer.update_view()
emit("after hide everything", wrong_domains())
for name in ("cartoon", "trace", "spheres", "sticks", "lines", "nonbonded",
             "dots", "labels"):
    cmd.do("show %s" % name); viewer.update_view()
emit("after showing each", wrong_domains())
for name in ("cartoon", "spheres", "sticks", "lines"):
    cmd.do("show %s, resi 20-30" % name); viewer.update_view()
    cmd.do("hide %s, resi 25" % name); viewer.update_view()
emit("after scoped show and hide", wrong_domains())

# The GUI's path: change one residue's representation to spheres. That is a
# command -- the sequence strip and the object menu both issue `as/show <rep>,
# resi N` -- so it is exercised as one. It used to be exercised through a
# `viewer.set_residue_representation(...)` that no part of the product called
# any more, which meant the residue-to-atom translation under test was one no
# user could reach while the one they do reach went unasked.
cmd.do("hide everything"); cmd.do("show cartoon")
cmd.do("show sticks, resi 20-30"); viewer.update_view()
sticks_before = int(np.asarray(state.sticks_mask).sum())
# Scope the spheres somewhere known and far away first. An unscoped `show
# spheres` above widened the scope to everything -- that is what a global show
# means -- and the measurement below is a *delta*, so it needs a starting scope
# of a size it knows, and one that does not already contain the residues about
# to be added.
cmd.do("show spheres, resi 100-102"); viewer.update_view()
balls_before = 0 if state.ball_mask is None else int(np.asarray(state.ball_mask).sum())
# Two residues named the way a user names them, by number.
index = np.asarray(viewer._atom_residue_indices())
picked_rows = [4, 9]
picked_resi = [int(np.asarray(state.residue_ids)[row]) for row in picked_rows]
for number in picked_resi:
    cmd.do("show spheres, resi %d" % number); viewer.update_view()
emit("after residue reps", wrong_domains())
emit("sticks_kept", "yes" if int(np.asarray(state.sticks_mask).sum()) == sticks_before else "no")

# ...and it selected exactly those two residues' atoms, not two arbitrary rows.
emit("balls_added", int(np.asarray(state.ball_mask).sum()) - balls_before)
emit("atoms_in_those_residues", int(np.isin(index, picked_rows).sum()))

# An unscoped show means the whole object, and says so by dropping the scope.
# The molecule loads with `ball_mask` already narrowed to its ligands, so an
# `as spheres` that respected that scope drew a space-filling picture of the
# zinc site and called it the molecule.
cmd.do("hide everything"); viewer.update_view()
cmd.do("show spheres, resi 20-30"); viewer.update_view()
emit("scoped_balls", "none" if state.ball_mask is None
     else str(int(np.asarray(state.ball_mask).sum())))
cmd.do("as spheres"); viewer.update_view()
emit("global_balls", "none" if state.ball_mask is None
     else str(int(np.asarray(state.ball_mask).sum())))
emit("traced_atoms", str(int(np.asarray(viewer.sphere_visible_mask()).sum())))
# ...and the picture agrees with the tracer: a mesh built over every atom, not
# the fifty-point sampling the unscoped case used to fall through to.
built = viewer.objects[key].built_scene_objects or []
emit("ball_vertices", str(max([int(np.asarray(o.geometry.positions).shape[0])
                               for o in built
                               if "ball" in str(o.id) or "atom" in str(o.id)] or [0])))

# Put the cartoon back: the block below is about the cartoon's own scope, and a
# scoped hide of a representation that is switched off writes nothing.
cmd.do("show cartoon"); viewer.update_view()

# Every representation reads an absent scope the same way: as all of its rows.
# Asked of each in turn, because the one that did not -- spheres -- was found
# from a screenshot rather than from a test, and the other nine were never
# checked at all.
absent_vs_all = []
# The **registry's** specs, not the scene builder's own tuple: the bond
# family (sticks, lines, nonbonded) is built by the `representations`
# plugin now, and its state is the object's named fields all the same --
# which is exactly what this loop checks for every state-field spec.
from chimol.core.services.representations import REPRESENTATIONS as _ALL_REPS
for spec in _ALL_REPS.specs():
    if not (spec.mask_field and spec.flag_field):
        continue
    cmd.do("hide everything"); viewer.update_view()
    rows = viewer.rows_in_domain(spec.domain, state)
    if rows <= 0:
        continue
    def drawn():
        viewer.update_view()
        built = viewer.objects[key].built_scene_objects or []
        return sum(int(np.asarray(o.geometry.positions).shape[0]) for o in built)
    setattr(state, spec.flag_field, True)
    setattr(state, spec.mask_field, np.ones(rows, dtype=bool))
    explicit = drawn()
    setattr(state, spec.flag_field, True)
    setattr(state, spec.mask_field, None)
    absent = drawn()
    absent_vs_all.append("%s=%d/%d" % (spec.name, absent, explicit))
emit("absent_vs_all", " ".join(absent_vs_all))
cmd.do("hide everything"); cmd.do("show cartoon"); viewer.update_view()

# A global show puts back what a scoped hide took away (PyMOL's `show cartoon`).
def cartoon_rows():
    """How many residues the cartoon covers -- `None` means all of them."""
    mask = state.cartoon_mask
    return n_res if mask is None else int(np.asarray(mask).sum())

cmd.do("hide cartoon, resi 5"); viewer.update_view()
scoped = cartoon_rows()
cmd.do("show cartoon"); viewer.update_view()
emit("scoped_then_global", "%d then %d of %d" % (scoped, cartoon_rows(), n_res))
'''


@pytest.fixture(scope="module")
def written():
    return probe(SCRIPT, timeout=900)


@pytest.mark.parametrize("moment", [
    "after hide everything",
    "after showing each",
    "after scoped show and hide",
    "after residue reps",
])
def test_no_mask_is_written_in_the_wrong_domain(written, moment):
    assert written[moment] == "none", f"{moment}: {written[moment]}"


def test_switching_one_residue_to_spheres_selects_that_residues_atoms(written):
    """Not one row per residue in a field indexed by atom."""
    assert int(written["balls_added"]) == int(written["atoms_in_those_residues"])
    assert int(written["balls_added"]) > 1


def test_an_unscoped_show_widens_the_scope_to_the_whole_object(written):
    """`as spheres` means every atom, whatever the object was scoped to.

    148L loads with `ball_mask` covering its 64 ligand and solvent atoms, so a
    global show that kept the existing scope turned the flag on and drew those
    64 spheres -- a space-filling picture of the zinc site, with the 1363-atom
    protein it had just replaced nowhere on screen.

    The new scope is written out in full rather than cleared. "No mask" reads
    as "all rows" to a builder, but it is also what an untouched object
    carries, and the loader re-derives defaults from exactly that: a cleared
    scope came back on the next frame as the hetero-atom default, empty for a
    bead simulation, and `as spheres` on the biofilm demo drew nothing.
    """
    assert written["scoped_balls"] not in ("none", "0"), "the scoped show wrote no scope"
    assert written["global_balls"] == written["n_atoms"], (
        f"`as spheres` left a scope of {written['global_balls']} of "
        f"{written['n_atoms']} atoms"
    )
    assert int(written["traced_atoms"]) == int(written["n_atoms"]), (
        "the ray tracer sees a different molecule from the one on screen"
    )
    # A merged sphere mesh over 1363 atoms, not the fifty-point sparse
    # sampling the builder fell through to while it read a missing scope as
    # "nothing to scope with" rather than as "all of them". The tracer and the
    # builder have to agree about what `None` means; when they did not, `ray`
    # drew a space-filling model of a molecule the screen showed as dots.
    assert int(written["ball_vertices"]) > 1000, (
        f"the spheres were drawn from {written['ball_vertices']} vertices"
    )


def test_switching_one_residue_to_spheres_leaves_the_other_reps_alone(written):
    """The report: changing a residue's representation changed the others.

    The per-atom sphere mask was rebuilt at residue length whenever the two
    disagreed, which is every time, so the scope the user had set was discarded.
    """
    assert written["sticks_kept"] == "yes"


def test_no_scope_means_every_row_to_every_builder(written):
    """The convention `drawable_rows` documents, asked of all ten builders.

    A representation's mask is a *scope*, and `None` means "not narrowed" --
    which the ray tracer has always read as "all rows". The sphere builder read
    it as "no rows to work from" instead and fell through to a fifty-point
    sampling, so `ray` and the screen drew different molecules. Nine other
    builders take the same argument and nobody had asked them.
    """
    pairs = dict(part.split("=") for part in written["absent_vs_all"].split())
    assert len(pairs) >= 10, f"only {len(pairs)} representations were measured"
    disagreed = {name: value for name, value in pairs.items()
                 if value.split("/")[0] != value.split("/")[1]}
    assert not disagreed, f"absent scope drew something else: {disagreed}"


def test_a_global_show_shows_something(written):
    """A representation whose scope is empty must not stay invisible.

    `hide sticks, all` leaves an all-false mask; `show sticks` then sets the
    flag and nothing appears. `set_sticks_visible` special-cased exactly that,
    for sticks, and nothing did it for the other nine -- so it is the rule now
    rather than one setter's private fix.
    """
    scoped, _, restored, _, total = written["scoped_then_global"].split()
    assert int(scoped) < int(total), written["scoped_then_global"]
    assert int(restored) >= int(scoped), written["scoped_then_global"]
