---
type: Parity Tracker
title: ChiMOL vs PyMOL parity
description: Measured gap between ChiMOL and PyMOL, with a prioritised route to replacing it.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, pymol, parity]
timestamp: '2026-07-25T00:00:00Z'
---

# Why this file exists

The goal is for ChiMOL to **replace** PyMOL for this group's work, not merely to
resemble it. That is a programme, not a task, so it needs a tracker that survives
between sessions — otherwise each round rediscovers the same gaps and closes the
easy ones twice.

Source of truth for PyMOL's behaviour is its **source**, checked out at
`junk/pymol-open-source`. Reading it has repeatedly overturned conclusions drawn
from observation alone; see [the log](/log.md) for three cases where a measured
"constant" turned out to be a different algorithm.

# The measured gap

| | PyMOL | ChiMOL |
| --- | --- | --- |
| Code | 515 823 lines C++ + 52 154 Python | 29 442 Python |
| Commands | 303 | 81 |
| Settings | 769 | 53 registered |
| Representations | 16 | 11 |
| Selection keywords | 85 canonical | 85 canonical, 169 spellings |

ChiMOL is roughly **5 % of PyMOL by volume**. Most of that difference is not
missing features but PyMOL's own scale: shaders, pickers, movie machinery, CGO,
volume rendering, four file-format families, and twenty years of edge cases. The
useful question is not "how do we write 500 000 lines" but **which parts are load
bearing for this group's work**, and those are tiered below.

# Tier 1 — daily use, blocks replacing PyMOL

| Item | Status | Notes |
| --- | --- | --- |
| `lines` (per-bond wireframe) | **done** | `RepWireBond`; was wrongly the CA trace |
| `nonbonded` (crosses) | **done** | `RepNonbonded`; waters/ions in a wireframe |
| Cartoon pipeline | **done** | Every step of `RepCartoonGeneratePoints` |
| Camera / `zoom` / view tuple | **done** | Exact against `SceneWindowSphere` |
| Object menus A/S/H/L/C | **done** | 1:1 from `pymol/menu.py` |
| Menu bar | **done** | PyMOL's grouping |
| Selection algebra | **done** | One table from `Keyword[]`; every arity class |
| `save` (PDB/mmCIF export) | **done** | Writes what the viewer holds, not the source file |
| `label` | **done** | Expression language, not templates; `L` menu now live |
| `create` / `extract` | **done** | Child drawn in its parent's frame, true coordinates kept |
| `origin` | **done** | Needed the two-point camera the view tuple defines |
| Undo / redo | **done** | PyMOL's scope: coordinates, per object, ring of 16 |

**Tier 1 is closed.** Everything a day's work touches is present. What follows is
Tier 2, which is real but has workarounds.

## The menus were never tested, and five were broken

The A/S/H/L/C menus are how most people drive the viewer, and nothing tested them:
the *command* layer was covered, the menus were not. Firing all 138 entries through
`MolViewPluginWindow._run_object_menu_command` — the path a click takes — found five
broken at once:

| Entry | What happened |
| --- | --- |
| A: remove waters | **crashed** on any structure that had waters |
| A: delete object | reading state from the emptied viewer raised, so the next repaint died |
| A: copy to object | template arguments reversed: it copied *from* the name typed |
| C: by element / by chain | menu writes `byelement`; `color` only knew `by_element` |
| C: tints > yellowtint | not a PyMOL colour at all — the menu invented it |

All five fixed, and the sweep is now a test: 157 cases, every entry plus a check
that each disabled entry explains itself.

**Why they survived.** Every structure in the test data was a protein with no
waters and no ions, so nothing could exercise the entries that act on them. Added
`solvated_fragment.pdb` — six residues, a zinc, eight waters — small enough that
150 window loads run in 23 seconds.

## The element field was one character wide

Found in the same pass. `ZN` was stored as `Z`, `CL` as `C`. Everything keyed on
the element inherited it: `metals` matched nothing on any structure ever, `elem ZN`
matched nothing, bond inference saw the wrong element, and a chlorine coloured as a
carbon. One character in `keys_formats`, in the reader shared by all of chisurf.

## Sweep the surface before extending it

Closing Tier 1 turned up four "implemented but silent" defects in a row, so before
starting Tier 2 the whole registered command surface was run against a real
structure and the *data* checked rather than the message. Six more commands were
answering cheerfully while doing nothing or crashing:

| Command | What it did | Cause |
| --- | --- | --- |
| `alter` | reported "Altered 1299 atoms", wrote none | own property map naming `chain_id`, `b_factor`, `occupancy` — no such fields |
| `alter` | shrank the molecule 10× on every call | assigned raw Angstrom into the render-space array |
| `spectrum` | ignored expression, palette **and** selection | body was `self.color("spectrum")` |
| `pseudoatom` | crashed, leaving a broken active object | invented a fifth atom dtype |
| `copy` | `NameError`, then a broken fallback object | called an undefined `_copy_state`, and `entry.id` |
| `as` | rejected `as cartoon, polymer` | no selection parameter |

All six are fixed, with `iterate_state`/`alter_state` and a persistent `stored`
namespace added alongside — without somewhere to put results, `iterate` can only
print.

### The test double was causing the bugs

`copy_object` used `copied.id` because `MockEntry` had `.id` while the real entry
has `.object_id`; the `alter` fixture declared `chain_id`/`b_factor` because
`alter` looked for those names. **Both halves were wrong together, so the tests
passed and the application was broken.** The double now matches the real viewer's
shape — `object_id`, an entry returned from `_create_object`, the `chain` field,
`set_atom_color_override` — and that is the standing rule: a divergence in the
double is a bug waiting to be written, not a convenience.

Two counts of the same lesson as the `resn` bug, which makes it the dominant
failure mode in this codebase: **a second copy of a table always drifts, and the
drift is silent because the feature keeps answering.**

## Undo is narrower than the word

PyMOL's `undo` is not a command history and matching that scope mattered more than
extending it: it stores *coordinate* snapshots, per object, in a ring of sixteen
(`cUndoMask = 0xF`), and refuses to restore one once the atom count has changed. It
does not undo a colour, a representation, a deletion or a load. Promising more would
be the wrong parity — a user expecting `undo` to bring back a deleted object is
better served by being told no.

The walk in `ObjectMoleculeUndo` is not the obvious pair of stacks: it writes the
present state into the ring *before* stepping, which is why one ring serves both
directions. A two-stack implementation passes a single undo and then drifts, so the
tests pin the reversibility rather than just the first step. chimol's snapshot has
to carry every array derived from the same edit — the trace, the render-space
positions, the atom array's Angstrom coordinates — or an undo would move the picture
back while leaving what `save` writes stale.

## The camera carries two points, not one

`origin` looked like a one-line command and was actually a camera-model gap. PyMOL's
view tuple defines **two** points — slots 12-14 the pivot in world space, slots 9-11
a camera-space offset applied after the rotation — and chimol had collapsed them
into a single orbit target. They agree until something separates them, and `origin`
is the only thing that does: `ExecutiveOrigin` always passes `preserve=1`, so moving
the pivot must leave the picture exactly where it was. The compensation is
`SceneOriginSet`'s, transcribed: the model-space difference rotated into camera
space, added to the view offset.

The property worth pinning is the invisible one. A wrong implementation looks
correct until someone rotates, so the tests assert both halves: that the
projection matrix is unchanged by `origin`, and that after it a chosen atom holds
its screen position through a 40° turn while the control case swings away.

Adding a non-zero slot 9 broke the loader's layout discriminator, which keyed on
"slot 9 is zero" to tell a PyMOL tuple from chimol's two older ones — a saved view
with an offset would have been read as a completely different camera, silently. One
corner is genuinely ambiguous (an identity rotation with a negative slot 11 could be
either format) and is resolved in PyMOL's favour, which the tests document.

## The selection language

The vocabulary now lives in one table, `cmd/sele_keywords.py`, transcribed from
`Keyword[]` in `layer3/Selector.cpp`, and both the parser and the evaluator read
it. That structure is the point, not the coverage: the parser previously kept its
own tuple of property names which had **drifted from the evaluator**, so `resn`
was implemented, evaluated correctly and *unreachable* — `resn NAG` parsed as an
implicit `AND` of two bare identifiers and reported an empty selection rather than
a missing feature. The same stale list had been copied to three call sites in
`selection.py`, where it decided whether a leading word was a keyword or an object
name; all three now ask the table.

Arity and fixity come from the `STYP_` suffix of each `SELE_` code, which the stack
reducer at the end of `SelectorSelect` spells out. Two were wrong before:
`STYP_PRP1` reduces `LIST PRP1 PVAL`, so `around`/`expand`/`extend`/`gap` are
**postfix**; `STYP_OP22` reduces `LIST OP22 VALU VALU LIST`, so
`within`/`near_to`/`beyond` are **infix**. Both had been implemented as prefix.

Atom classes (`polymer`, `organic`, `solvent`, `inorganic`, `backbone`,
`sidechain`, `guide`, `metals`) are derived per residue from the atoms present, as
`SelectorClassifyAtoms` does, in `analysis/atom_classes.py` — not from a table of
residue names, so a modified residue or an unusual ligand lands in the right class
with nothing to maintain. `metals` is by proton count, per
`AtomInfoType::isMetal`. One deviation is documented in that module: PyMOL also
requires a peptide or phosphodiester bond before calling a residue polymer, which
needs connectivity chimol does not carry there, so an isolated free amino acid
classifies as protein.

What chimol still cannot answer it now **names**: `donors`, `acceptors`,
`delocalized` (assigned chemistry), `masked`, `protected`, `fixed`, `restrained`
(editor state), `byring`/`bycell` (ring perception), `text_type`/`numeric_type`
(force-field types), `flag`, `state`. Each raises `UnsupportedSelection` with its
reason. An unimplemented keyword must not look like an empty selection — that
confusion is exactly what hid `resn`.

## Reader differences found while closing Tier 1

* **Alternate locations.** PyMOL keeps every altloc as a separate atom (148L:
  1385 atoms, 22 A + 22 B); chimol reads through IMP's
  `NonAlternativePDBSelector` and keeps only the first (1363). Defensible for a
  viewer and it round-trips cleanly, but the atom counts will not agree with
  PyMOL's on any structure with altlocs.
* **Unit boundaries are where the bugs are.** `translate` took Angstrom and
  applied them to the renderer's scene-unit arrays, so `translate [100,0,0]`
  moved the molecule 10 Å. Invisible on screen; obvious the moment a file was
  written. The distance selection operators had the same defect from the other
  side — `within 5` measured against scene units and so meant `within 0.5`. Any
  new command or operator that takes a length must convert.
* **Ligand atom names were being lost.** IMP prefixes the type of any atom it
  cannot classify as a standard amino-acid or nucleotide position with `HET:`, so
  a ligand's `N` stringified as `"HET: N  "`. Stored verbatim in the
  five-character `atom_name` field it truncated to `HET:`, giving *every* ligand
  atom the same name. Fixed in the shared reader (`_imp_atom_name` in
  `chisurf/core/fio/structure/coordinates.py`), which benefits all of chisurf, not
  only the viewer. Two consequences worth knowing: the peptidoglycan stem peptide
  of 148L (DAL, FGA) now classifies as polymer and joins the trace, since it is a
  genuine peptide; and `name`-based selections reach ligands at all.
* **`save` wrote the wrong object.** It read the *active* object's arrays while
  masking with a selection that may have resolved against another, so
  `save out.pdb, sugars` raised a length mismatch — and would have silently
  written the wrong atoms had the two objects been the same size.

# Tier 2 — routine, works around-able

**Done:** `get_area`, `get_extent`, `get_chains`, `get_title`, `iterate_state`,
`alter_state`, `spectrum` by property, `scene`, `pair_fit`, `cartoon_putty`,
`group`/`ungroup`/`order`, `bond`/`unbond`/`get_bonds`.

**Remaining:** `smooth`, `sort`, `protect`, `mask`,
`h_add`/`h_fill`, `cealign`, `matrix_copy`,
`symexp`/`symmetry`, `ramp_new`, `cartoon_putty`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.
`set_bond`/`get_bond` (per-*bond* settings, not the bond list) need a per-bond
settings store and are deliberately not started.

## Editing bonds, and the fixture that could not test it

`bond`, `unbond` and `get_bonds`, transcribed from `editing.py` and
`querying.py`. Three details that are not guessable:

* `bond` requires **exactly one atom** from each selection and both in the same
  object, because a bond lives inside one object's connectivity table. Repeating
  it on an already-bonded pair sets the *order* — that is how a single bond is
  promoted, not an error.
* `unbond` takes selections of any size and removes **every** bond between them.
  Not the cross product: only bonds that actually run from one selection to the
  other, or it would try to remove bonds that were never there.
* `get_bonds` indices are **0-based positions within the selection**, not the
  `index` property. PyMOL warns about this in capitals. They coincide for `all`,
  so a test that checks only `all` cannot tell the difference.

Bonds are re-inferred whenever coordinates change, so a manual bond kept only in
`bond_pairs` vanishes the next time an atom moves. Edits are stored as **deltas**
(`added` orders, `removed` pairs) and replayed over each fresh inference. The
direction matters: the edits are the source of truth and `bond_pairs` is derived,
so the two cannot drift. Orders live in that delta map rather than as a third
column of `bond_pairs`, because several consumers flatten that array to ask
"which atoms have a bond" and an order column reads as an atom index.

### The fixture was geometrically impossible

`solvated_fragment.pdb` — added earlier in this effort as the first fixture with
waters, an ion and a two-letter element — placed its six alanines along a helical
path *without constructing the backbone*. `C(i)-N(i+1)` came out at 4.4–5.2 Å
against a peptide bond's 1.33 Å, so the file had **no peptide bonds at all**, and
residues 4 and 5 interpenetrated (`O4-CB5 = 0.63 Å`, which is not a chemical
distance). Bond inference on it produced 40 bonds where 29 are correct: 11
spurious contacts and 4 of 5 peptide bonds missing.

Rebuilt by NeRF placement from ideal internal coordinates — the way a peptide is
actually constructed, each atom from the previous three by a length, an angle and
a torsion. The generator lives beside the file as
`make_solvated_fragment.py` and self-checks what matters: all five
`C(i)-N(i+1)` at 1.329 Å, closest contact 1.231 Å (the C=O bond), CA-CA at 3.8 Å
as an α-helix requires.

The lesson is about fixtures rather than about bonds: **a fixture is an
assertion too, and nothing checks it.** Every test built on this one was
green while the molecule it described could not exist.

## Groups are a display hierarchy, and membership belongs to the member

All eleven of PyMOL's group actions (`creating.py::group_action_dict`) plus
`ungroup` and `order`. Three decisions worth recording, each of which the
obvious alternative gets wrong:

**Membership is stored on the member, not as a list on the group.** A list plus
a back-pointer is two places that say where an object sits, and they drift the
first time an object is deleted — the failure this codebase keeps finding in its
own colour, keyword and representation state. A group therefore has no existence
apart from its members: `group_names()` is derived, and deleting the last member
removes the group, which is what PyMOL needs `ExecutiveGroupPurge` for.

**The second argument means either members or an action.** `group kinases, close`
is how PyMOL's own menu writes it, and every example in the command's help text
uses that form. Reading the word as an object name instead makes the documented
examples all report a missing object.

**Members must be drawn contiguously, and the registry does not keep them
adjacent.** Grouping the first and third objects leaves the registry order
`lig, pep, nag`, so walking it directly drew `nag` under whichever header came
last — visibly the wrong group. The display order is computed separately
(`_grouped_display_order`): a group's block goes where its first member sits, and
nothing in the viewer is reordered, so `order` still means what it says.

Two smaller ones, both found by a test rather than by reading:

* `order lig nag` has to keep the order **given**, not panel order. The shared
  name resolver sorted into panel order, which made `order` a silent no-op
  whenever the names were already in panel order — most of the time.
* A group used as a menu target expands to one command per member, which is
  PyMOL's documented "the command should be applied to all members". The
  expansion happens where the target is known (the row), because the selection
  resolver answers for one object at a time.

**Not yet:** a group name inside an *atom selection* — `show cartoon, ligands` —
because `_resolve_selection_to_atom_mask` returns a single `(object_id, mask)`
pair. Supporting it means a multi-object resolver; the group's row menus and any
command taking object names work today.

## Two coordinate arrays, and they had drifted apart

The worst defect found so far, because it made commands disagree about where the
molecule *is*. chimol keeps coordinates twice — `atoms["xyz"]` in Angstrom, and
the renderer's arrays in scene units — and `_apply_rigid_transform` **skipped
structured arrays on purpose**. So `translate` and `rotate` moved the render
arrays and left the atom array behind.

Everything that reads the atom array was then working from pre-transform
coordinates: `align`, `super`, `get_area`, `get_extent`, `alter_state`, and every
distance selection. On a displaced copy, `rms` (render arrays) reported 281 Å
while `align` (atom array) saw nothing to do, announced an RMSD of 0.000, and
moved nothing.

Both halves are fixed: the transform now reaches the atom array — through the
scale, since the translation arrives in scene units and the atom array is in
Angstrom — and `rms` converts its result out of scene units, having previously
printed a length ten times too large with an Angstrom sign on it.

One test had encoded the desynchronisation (it asserted that `save` and the atom
array *disagreed* by exactly the translation) and now asserts they agree.

**Sampling is orientation-dependent.** Fixed dot directions mean a rotated
molecule samples its own surface slightly differently — a few percent at the
default density. Pure translation is exact. Documented in the concept page; worth
knowing before comparing two structures' areas.

## `pair_fit`

`align` finds its own correspondence; `pair_fit` takes one you state, matching
atoms in order within each pair. That is what you need when the two structures are
not the same sequence, or when only a domain or a ligand should drive the fit.
Several pairs feed **one** least-squares fit, so a superposition one stretch would
leave ambiguous can be pinned down by adding another.

`intra_fit` and `intra_rms` fit the *states* of one object to each other; chimol
holds a single coordinate set per object, so they have nothing to work on and are
deliberately absent rather than stubbed.

## Bonds were inferred from one distance

chimol used a single 1.9 Å cutoff for every pair of atoms. A single cutoff has to
be wide enough for the longest real bond, which makes it wide enough for a mere
*contact* between heavier atoms — and too narrow for the longest. Both errors were
live:

* **every disulfide was missed.** S–S is 2.05 Å, past the cutoff, so no structure
  ever showed one;
* on a model *with* hydrogens the old rule produced 2278 bonds the new one does
  not, of which **2138 are hydrogen-to-hydrogen** — pairs that are never bonded —
  and most of the rest are hydrogen bonds at ~1.65 Å drawn as covalent.

Every bond-based feature inherited those: sticks and lines drew them, and `bymol`,
`bound_to` and `extend` walked across them.

Now transcribed from `is_distance_bonded` (`layer2/ObjectMolecule2.cpp`):
`|v1−v2| − (vdw1+vdw2)/2 ≤ connect_cutoff + adjustment`, with 0.35 as the cutoff,
+0.2 for sulfur, −0.2 for hydrogen, never between two hydrogens, and a coincident
guard at `R_SMALL4` — which the first transcription omitted, so duplicate atom
records bonded to themselves.

The radii come from the atom array, so this needed no new data.

## Putty

A tube whose thickness carries a number — one of the few representations that
shows a quantity rather than a shape, and for this group the quantity is rarely a
b-factor: an accessibility from `get_area`, a fitted lifetime, a per-residue
efficiency, written in with `alter` and drawn.

Scale factors transcribed from `ExtrudeComputeScaleFactors` (`layer1/Extrude.cpp`)
— all nine transforms. Two details change the picture and are pinned by tests: the
clamp is applied **after** the power, and the factors are smoothed along the chain
with a running window that leaves the ends alone (without it, one outlying residue
beads the tube instead of bulging it).

The extrusion already accepted a per-point `vert_scale`; only the scale factors and
the wiring were missing.

**Verified geometrically rather than visually**, since the ray tracer cannot draw a
cartoon: the tube's actual ring radii are measured back out of the mesh. A uniform
tube is constant at 5.0; a putty tube over a monotone property ranges 2.4–10.2,
monotone, with its thinnest point at exactly `radius x scale_min`. That pins two
settings and the transform at once, and is a stronger check than looking at a
picture.

## Scenes

`scene` stores the camera, object activity, representations and colours, with
PyMOL's per-aspect flags so a scene can carry only a viewpoint or only a
colouring. Two things are chimol-specific, both from the camera being stored
*relative to the scene centre*, which moves when what is drawn changes:

* the view is restored **last**, after the representations — restoring it first
  lets the rebuild undo it;
* `view=0` actively holds the camera across the rebuild, since otherwise "leave
  the view alone" still moves the picture.

## `get_area` is the one with physics in it

Solvent accessibility decides where a dye can be attached and how freely it moves,
so this is one of the few numbers the viewer computes that feeds back into
experiment design. Transcribed from `RepDotDoNew` in `cRepDotAreaType` mode, with
two details that a generic Shrake–Rupley gets wrong:

* the points are an **icosahedral geodesic** (12/42/162/642/2562 for `dot_density`
  0–4), reproduced exactly — dot counts verified against `Sphere_nDot`;
* each point carries **its own** solid angle, from the spherical excess of its
  incident triangles, not `4π/N`. On a geodesic sphere the twelve original
  icosahedron vertices have five neighbours where every later vertex has six, so a
  uniform weight is wrong by a few percent, worst at low density (min/max weight
  ratio is 0.74 at the default level).

Validated three ways: the weights sum to 4π to 1e-9 at every level; an isolated
sphere and two overlapping spheres match closed-form areas, converging 6.3 % →
1.5 % → 0.2 % across densities 0/2/4; and a random cluster agrees to within 1 %
with an independently written Shrake–Rupley using a *golden-spiral* sphere and
uniform weights, so a shared mistake in the tessellation cannot hide. T4 lysozyme
gives 8 200 Å² accessible against 17 700 Å² van der Waals — the factor of two that
makes labelling the surface without saying which one nearly meaningless.

Every atom occludes even when only a selection is reported, which is the whole
point: the area of a residue *in* a protein is not its area in isolation.

# Documentation

**Closed.** Theory in `docs/concepts/molecular_surfaces.md`, application in
`docs/guides/44_molecular_viewer.md`, each registered in its index and
cross-linked. Both figures regenerate from `docs/guides/make_screenshots.py`
(`_grab_chimol_viewer`), and every command and Python snippet in both pages was
executed to confirm it runs — 43 of 44 command lines pass, the exception being
`png`, which the guide itself documents as needing a display.

# `ray` renders the scene, not the molecule

Found while making the guide's figure: `ray` traced **every atom in every state**.
`hide everything` and `show spheres, resn NAG` produced the identical picture of
the whole molecule, because it called `get_atom_sphere_data`, whose contract is
explicitly "all atoms regardless of representation".

Now filtered by `sphere_visible_mask`. The rule that matters: the per-atom mask is
the authority where one exists and the boolean flag is only the whole-object
fallback — `show spheres, resn NAG` sets `_ball_mask` and leaves `_show_atoms`
alone, so reading the flag alone sees nothing.

The tracer still draws **spheres only** and cannot render a cartoon. Rather than
silently omitting the molecule it now says so and points at `show spheres`.
Cartoon ray-tracing needs ribbon primitives in the tracer and is not started.

# Capturing the GUI headlessly

Real constraints, verified:

* Offscreen clamps a `QMainWindow` to 640×603 whatever `resize` asks for, so
  **grab the widget you want rather than the window** — a child widget honours its
  own `resize`.
* `QOpenGLWidget` content never appears in a `QWidget.grab()`: that reads the
  backing store, so a window grab shows the panels over an empty viewport. Use
  `grabFramebuffer` for the 3D view and `grab()` for the surrounding layout —
  two images, not one.
* **Offscreen does not exercise GL.** Under `QT_QPA_PLATFORM=offscreen`
  `grabFramebuffer` returns black, so the ray tracer is the only headless
  capture — which is what `okf/workflows/testing.md` prescribes for visual
  tests, and it is enough for geometry. It is *not* enough for shading,
  representation flags or anything the scene builder decides: those need
  `QT_QPA_PLATFORM=cocoa` and a real window. Four defects listed below survived
  a full offscreen suite and were obvious in the first windowed render.
* `ray` driven through `MolViewPluginWindow` hands the trace to a worker and
  reports `ray: cancelled` in a script with no event loop of its own. Driving a
  bare `MolView` traces synchronously and works.
* `ObjectsDock.widget` is a **property**. Calling it (`widget()`) raises
  `TypeError: 'QWidget' object is not callable`.

:::{note}
A previous revision of this file claimed that grabbing the objects panel crashed,
and that grabbing the window crashed once the panel held two rows. **Both were
wrong.** The "crashes" were `TypeError` from calling that property, and the
tracebacks were hidden because the diagnostic scripts filtered stderr through
`grep`. Panel grabs work at any size and with any number of rows. The lesson is
the diagnostic one: a silent exit under a filtered pipe is not evidence of a
crash, and the filter has to come off before drawing a conclusion.
:::

# What only a real window showed

The capture notes above are about getting *an* image. Getting a **correct** one
needed a window with a GPU behind it: `QT_QPA_PLATFORM=cocoa`, a real
`grabFramebuffer`, and the PNG read back. Four defects were sitting in a tree
where every test passed, and none of them raised anything.

## Three representations drew nothing at all

`show spheres, all`, `show sticks, all` and `show cartoon, <sel>` produced zero
geometry. The selection branches set the per-atom *mask* and left the boolean
*flag* the scene builder also requires — so the mask said which atoms and
nothing said whether to draw them. `show lines` and an unqualified `show
cartoon` took different branches and worked, which is why it went unnoticed.

The general shape: **a representation is described by two pieces of state, and
writing one of them is a silent no-op.**

## Occlusion was counted twice, and swallowed half the picture

Ambient occlusion is multiplied into the vertex colour *and* handed to the
shader as `v_occ`. The fragment shader then damped ambient, rim, environment
and sun by `1.0 - v_occ`. A deeply occluded fragment therefore got a dark base
colour and near-zero ambient and came out solid black — whole helices vanished
into the background. Flooring the second term (`mix(0.35, 1.0, 1 - v_occ)`)
keeps occlusion reading as shape without extinguishing anything.

## `spectrum` never reached the cartoon

`spectrum count, rainbow` writes **per-atom** colours. The cartoon and the trace
read **per-residue** ones. So the command reported success, the atoms were
correctly coloured, and the ribbon went on showing the load-time blue-to-orange
gradient — a picture with no green, cyan or yellow in it. Measured on the mesh:
the green channel never exceeded 0.55 where a rainbow drives it to 1.0.

`_ca_rgba` now projects the per-atom override down to per-residue (each residue
takes its CA atom's colour, or the mean of its atoms), folded in at the single
place the per-residue array is finalised. The sequence strip was a *third* copy
of the same colouring, refreshed by `color` and not by `spectrum`.

That is the [working rule 5](#working-rules) failing for the third time, now in
its rendering form: **one colouring, three arrays, and a command that writes one
of them.**

## `nonbonded_size` is about bonds, not about polymers

PyMOL shrinks *nonbonded* atoms — ordered waters, free ions — so a shell of
full-size solvent does not bury the molecule. ChiMOL was shrinking everything
absent from the polymer colour map, which quartered every bonded ligand:
`show cartoon, polymer` plus `show spheres, organic` drew the ligand as a
scatter of dots. It now derives the mask from the inferred bond list, so it
agrees with the `nonbonded` selection keyword instead of being a second opinion
about what counts as solvent.

Worth recording as a testing lesson: at the bounding-box level, quartering every
ligand radius moves the measurement only from 0.998 to 0.892 of the van-der-Waals
envelope, because a bounding box is dominated by how far apart the atom *centres*
are. It is glaring on screen and easy to sleep through in an assertion — the
first threshold written for it (0.85) passed the bug.

## The default layout gave the viewport 40% of the window

The dock state asked for a 3:1 split by writing `"sizes": [3, 1]` among entries
that are otherwise pixel counts. QSplitter reads pixels, clamped the viewport to
its minimum width, and the 3D view ended up smaller than the side panels. The
sequence strip had the mirror problem in the other direction: 150 px allocated
for ~90 px of content, leaving a band of dead grey under the letters.

A guard test now rejects any `sizes` entry below 20, since a ratio and a very
small pixel count are indistinguishable by inspection.

# Tier 3 — specialised or superseded here

Volume rendering, `isomesh`/`isosurface`/`map_*` (ChiSurf has its own map
plugins), sculpting, wizards, the movie/`mset` programme language, stereo modes,
CGO scripting, `fab`/`fragment` building, `alias`, `log_open`.

# Where ChiMOL is deliberately ahead

* **Ambient occlusion** in the interactive viewport, normal-aware and baked per
  rebuild. PyMOL has none.
* **Cast shadows** in the interactive viewport. PyMOL casts them only when
  raytracing.
* **Settings honesty**: every registered setting is verified to drive code that
  reads it, so `set` cannot silently do nothing.

These are the answer to "surpass on the view", and they are cheap because they
exploit the one structural advantage of a rebuild-time pipeline: work done once
per geometry change is free while the camera moves.

# Working rules

1. **Read the C++ before implementing.** Every one of `refine_tips`, the
   `weighted` extent, the orientation-blend endpoints and the view-tuple sign was
   wrong when inferred from behaviour and right when read from source.
2. **Transcribe, do not approximate.** A weighted kernel that "looks like" a box
   average converges differently and shows up on screen.
3. **Pin the transcription with a test that names the C++ function**, so a later
   change cannot quietly drift.
4. **A gap that is shown is better than a gap that is hidden** — disabled menu
   entries with reasons, unknown settings reported rather than accepted,
   unsupported selection keywords named rather than returning nothing.
5. **One table, read by everyone who needs it.** Every vocabulary duplicated
   between a parser and an evaluator, or copied to three call sites, has drifted
   here at least once. The drift is silent: the feature looks implemented and
   returns the empty answer.
