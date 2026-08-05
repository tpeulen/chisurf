---
type: Parity Tracker
title: ChiMOL vs PyMOL parity
description: Measured gap between ChiMOL and PyMOL, with a prioritised route to replacing it.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, pymol, parity]
timestamp: '2026-07-25T00:00:00Z'
---

# Why this file exists

The **target** — a PyMOL clone that is command-compatible with PyMOL and better
than it — is stated in [specs/chimol](/specs/chimol.md). This file is the
*measured gap* against that target: the tier list, what is done, and the findings
from closing each item. It needs to survive between sessions, or each round
rediscovers the same gaps and closes the easy ones twice.

Two sources are read, and they answer different questions.
**PyMOL** (`junk/pymol-open-source`) is the authority on *behaviour*: what a
command does and what its defaults are. **ChimeraX** (`junk/ChimeraX`) is the
reference for *how to do it well* — rendering above all — and is explicitly not
the compatibility authority.

Reading them has repeatedly overturned conclusions drawn from observation alone;
see [the log](/log.md) for cases where a measured "constant" turned out to be a
different algorithm, and for one where the data was blamed before the rule was.

# The measured gap

| | PyMOL | ChiMOL |
| --- | --- | --- |
| Code | 515 823 lines C++ + 52 154 Python | 29 442 Python |
| Commands | 303 | 119 |
| Settings | 790 | 74 registered |
| Representations | 16 | 11 |
| Selection keywords | 85 canonical | 85 canonical, 169 spellings |

ChiMOL is roughly **5 % of PyMOL by volume**. Most of that difference is not
missing features but PyMOL's own scale: shaders, pickers, movie machinery, CGO,
volume rendering, four file-format families, and twenty years of edge cases. The
useful question is not "how do we write 500 000 lines" but **which parts are load
bearing for this group's work**, and those are tiered below.

# Where to pick this up

The findings below are what has been *closed*. This section is the open front,
kept at the top so a new session does not have to reconstruct it. Ordered by
what a user actually hits.

**1. Settings — the standout gap, and it has a measured worklist.** 790 in
PyMOL, 55 registered here. The raw remainder (735) is misleading: most of it is
sculpting, roving, stereo, movie, shader and session bookkeeping that does not
apply. What matters is the **228 that PyMOL's own Python layer references**,
which is the closest available proxy for real-world use. Re-derive it with:

* parse `layer1/SettingInfo.h` for `REC_<x>(idx, name, level, default)` — **strip
  `/* … */` comments first**, or ~20 records with trailing comments are silently
  missed and the total reads 770 instead of 790; `REC__` is a retired slot;
* count each name's occurrences under `modules/pymol/` and `modules/pmg_tk/`;
* subtract `chimol.settings.setting_names()`.

The appearance-bearing names at the top of that ranking, which is where to
start: `transparency`, `surface_color`, `surface_type`, `two_sided_lighting`,
`stick_color`, `ribbon_color`, `stick_ball`, `sphere_mode`, `valence`,
`light`, and the `util.py` lighting family (`specular_intensity`,
`spec_direct`, `spec_count`, `reflect`, `power`, `ray_shadow_decay_factor`).
`cartoon_highlight_color` and `cartoon_fancy_helices` are the two the `pretty`
and `publication` presets still report as skipped. The `dash_*` family and the
six `h_bond_*` came off this list with the polar-contact finder, and
`transparency` / `two_sided_lighting` with the surface work -- which leaves
`surface_color`, `surface_type`, `stick_color`, `ribbon_color`, `stick_ball`,
`sphere_mode`, `valence` and the `util.py` lighting family at the top.

`surface_quality` **is fixed** -- it was three defects wearing one name, and the
finding generalises: a registered setting with a live config path and a passing
test still had no effect at all. Before registering more names, **count what the
setting produces**, not whether it stores.

**Register a name only if code reads it** — a setting that reads nothing is what
the settings table exists to prevent, and it is why the three cartoon settings
above are absent rather than accepted-and-ignored.

**2. Rendering.** Two measured defects left in the ray tracer.

*Meshes are double-shaded* — occlusion and cast shadow are baked into the vertex
colours and then shaded again, costing 44 % of the colour. Described under
*`ray` renders the scene, not the molecule*.

*Nothing but a sphere casts a shadow.* The shadow query walks a tree built over
the spheres alone, so on a cartoon-only display — the default — `shadow` is
identically 1 and `ray_shadow` does nothing at all: a helix lying across another
does not darken it. PyMOL shadows every primitive. This was unaffordable when a
shadow ray cost a sweep of the whole scene and **is affordable now** (see *every
ray tested every primitive* below), so it is a rendering decision rather than a
performance one: it will change every cartoon and surface image, and should be
measured against PyMOL's output on the same view before being turned on. The
seam is `_jit_shadow_soft`, which already takes the triangle array and a tree —
pointing it at the scene tree instead of the sphere tree is the whole change.

**Transparency is done** — see *the tracer walks through a surface* below — and
so is **speed**: `ray` was 143–651× slower than it needed to be.

**3. Tier 2 leftovers**, in rough order of use: `matrix_copy`, `ramp_new`,
`cartoon_dumbbell`, `ellipsoid`, `cell`, `slice`.

**4. The other `distance` modes.** 0–4 are done; 5–7 (π–π, π–cation), 9
(halogen bonds) and 10 (salt bridges) are not, and the **A ▸ find** submenu
shows each disabled with that reason. They are separate detectors, not
variations on the hydrogen-bond test: PyMOL keeps 5–7 in its incentive build and
implements 9/10 in `layer3/Interactions.cpp`, which is the file to read. The
plumbing they would need — a multi-segment dashed measurement, the combined
atom table, the settings — is now in place, so each is its own small predicate
rather than a new subsystem.

**Two smaller things the polar-contact work left measured but not done.** The
contact object is not a real *object*: it does not appear in the panel, cannot
be enabled/disabled or deleted by name, and `hide everything` does not touch it
(PyMOL's `dist` creates an `ObjectDist` that the panel lists). And with
`label=1` the numbers overlap badly on anything denser than a few contacts —
PyMOL has the same problem and answers it by having every preset pass
`label=0`, which is what chimol does too.

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
| Selection *scope* | **done** | Every object, as PyMOL's one atom table; groups included |
| `save` (PDB/mmCIF export) | **done** | Writes what the viewer holds, not the source file |
| `label` | **done** | Expression language, not templates; `L` menu now live |
| `create` / `extract` | **done** | Child drawn in its parent's frame, true coordinates kept |
| `origin` | **done** | Needed the two-point camera the view tuple defines |
| Undo / redo | **done** | PyMOL's scope: coordinates, per object, ring of 16 |
| Sessions (`save`/`load` a whole state) | **done** | Own zip format, not PyMOL's pickled `.pse` |

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

A sixth was found later, and only by clicking in the *viewport* panel: an entry
needing a typed value (`rename object`, `copy to object`, `align to ...`) was
**skipped there** — `_emit` dropped any template carrying `{text}`, on the
grounds that there is nowhere in the viewport to type. That is a menu entry that
does nothing when clicked, in the panel that is now the primary one. Those
entries write themselves into the command line instead, with the placeholder
selected so the next keystroke replaces it; the command line is one row below
the panel. The sweep test could not have caught it, because it drives the
*docked* panel's path.

The sweep also turned out to be **passing two entries that did nothing**, and
only the new unknown-name error exposed it: it filled every `{text}` with the
literal `copied`, which is right for `copy to object` (a name for something the
command creates) and wrong for `align to ...` / `super to ...`, where the slot
is a *target selection that must already exist*. A made-up name resolved to an
empty mask, so both commands returned quietly and the assertion held. The filler
now picks a value that suits the slot. The lesson is the file's recurring one:
**a fixture is an assertion too, and nothing checks it.**

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
`group`/`ungroup`/`order`, `bond`/`unbond`/`get_bonds`, `h_add`/`h_fill`, `smooth`,
`protect`/`deprotect`, `sort`, `mask`/`unmask`,
`symexp`/`get_symmetry`/`set_symmetry`, `distance` modes 0-4 (polar contacts).

**Remaining:** `cealign` (skipped by request), `matrix_copy`, `ramp_new`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.
`set_bond`/`get_bond` (per-*bond* settings, not the bond list) need a per-bond
settings store and are deliberately not started — which is also why
`preset ball_and_stick` reports that it could not colour its sticks white.
(`cartoon_putty` was listed in both columns; it is done.)

## Symmetry: hand-entered data, machine-checked

`symexp`, `get_symmetry`, `set_symmetry`. The generation follows
`ExecutiveSymExp`: transform in **fractional** space, shift the copy so it lands
beside the original rather than an arbitrary number of cells away, convert back,
and keep it only if some atom comes within the cutoff.

**The operators are PyMOL's own**, transcribed out of `modules/pymol/xray.py`
(`sym_base` + `space_group_map`) into `analysis/space_groups.py` by a generator
checked in beside the data: **547 names over 528 distinct operator sets**, up to
192 operators each. No crystallography library is a dependency — no `gemmi`,
`spglib` or `cctbx` — and none is wanted: sharing PyMOL's table is what makes a
mate here *the same mate* PyMOL would build, rather than approximately the same.

An earlier revision of this section described a 27-group table entered by hand.
That was replaced: a hand table covers the common cases and diverges from PyMOL
everywhere else, which is the wrong trade for a parity project.

Operators are looked up in order of trust: supplied explicitly or read from the
file (exact, whatever the group), then PyMOL's table, then **nothing** — in which
case the space group is named and the command declines. A mate built from guessed
operators looks entirely plausible and would be believed.

**Reading them out of an mmCIF is parsing, not line-shaping.** The file source
outranks the verified table, so a misread there beats everything the table
guarantees. The first version took the whole `_symmetry_equiv` loop row as the
operator; a PDBx loop carries `_symmetry_equiv.id` beside `pos_as_xyz`, so
`3 x+1/2,y+1/2,z` became a rotation with **determinant 3** — a threefold
*scaling*, moving that mate by up to 19.6 Å — and the quoted form RCSB writes
raised out of `symexp`. So the loop *header* is parsed, the column of
`pos_as_xyz` is taken (either tag order, either tag spelling), quotes are honoured
per field, and the non-loop `tag value` form is read too. All four layouts are
pinned, twice: same operators out of each, and every operator an isometry — the
check the det-3 row failed.

**A transcription can fail silently, so the whole table is verified
mathematically.** All 547 groups are closed under composition modulo lattice
translations, every rotation is an isometry (determinant exactly ±1 — 4355 proper
and 3303 improper, since the table covers all 230 groups and the centrosymmetric
ones contain inversions), every group has exactly one identity, and none lists an
operator twice. **7658 operators verified.** The chiral groups proteins
crystallise in are checked separately for determinant +1 only, where an improper
rotation would be an extraction error rather than a legitimate mirror. A size
guard sits alongside, because a *truncated* extraction would pass every
mathematical check — whatever survived would still be self-consistent.

Two other checks worth keeping: a mate must be a **rigid** copy (symmetry is an
isometry, so internal distances cannot change), and a pure lattice translation
must offset the molecule by exactly one cell edge — which is the strongest test of
the fractional-to-Cartesian transform.

**Performance.** The first version rebuilt the neighbour tree per candidate: 107
tree builds over every atom, and on HIV-RT's 17 784 atoms that dominated
everything. Hoisting the tree and rejecting candidates by bounding box first
brings the whole expansion to **0.26 s**.

## `sort`: the ordering was the easy half

The priority table is transcribed from `AtomInfoAssignParameters`. Two of its
properties are counter-intuitive, and both were got wrong by guessing before the
source was read:

* **priority depends only on the Greek letter, not the branch number.** `CG2` and
  `OG1` both score 5, and the *name* comparison settles them — giving `CG2` first,
  which is what deposited files contain. Folding the branch digit into the
  priority put `OG1` first and disagreed with **both** real structures checked
  (148L and hGBP1), at 10% and 2% of atoms. Reading the C++ turned a
  "the files are non-canonical" conclusion into "the rule was wrong";
* **a one-character `C` or `O` scores 997/998**, so the canonical order is
  `N, CA, CB, ..., C, O, OXT` — side chain *before* the carbonyl. That is not PDB
  write order, so sorting a freshly loaded file genuinely reorders it (74% of
  atoms move), and matching PyMOL means accepting that.

**The consequence, not the ordering, is the dangerous part.** A reorder
invalidates every array indexed by atom and every bond index. The atom-indexed
fields are written out rather than detected by shape — a residue-length array can
coincidentally match the atom count, and being wrong there pairs colours with the
wrong coordinates — and a **guardrail test** walks the state dataclass and fails
on any array field that is neither listed as atom-indexed nor listed as exempt.
It found three unclassified fields on its first run.

Mutation testing was informative beyond confirming the tests bite:

| broken deliberately | caught? |
| --- | --- |
| per-atom colour array not permuted | yes, 2 failures |
| manual `bond_edits` keys not remapped | yes |
| `bond_pairs` indices not remapped | **no** |

The last one is not a gap in the tests but a fact about the code: `sort` rebuilds
afterwards, which re-infers bonds from coordinates and overwrites whatever the
remap set. So that line is belt-and-braces for a direct API caller, and the
`bond_edits` remap is the part that has to be right — it is replayed on top of
each fresh inference. Said so in the code rather than leaving a line that looks
tested and is not.

`mask`/`unmask` are threaded into the pick site, because a flag nothing reads is
decoration. Kept separate from `protect`: one is about the mouse, the other about
transforms, and conflating them would mean hiding an atom from selection also
froze it.

## `smooth` is four decisions, none of them in the help text

Transcribed from `layer3/Executive.cpp::ExecutiveSmooth`. The command's own
documentation describes a window average; the behaviour depends on four things it
does not mention, and each changes the numbers:

* the half-windows are `window / 2` in **integer** arithmetic, taken
  independently as `backward` and `forward`, so an even window spans an odd
  number of states — `window=4` averages five;
* `ends` is a **four-way choice**, not a boolean: `0` skips one state at each
  end, `1` skips none, `2` skips a whole half-window, `3` wraps the trajectory;
* the average divides by the number of states actually **found**, not by the
  window width. Dividing by the width pulls states near an unskipped end towards
  the origin, which reads as the trajectory collapsing at its ends;
* `cutoff` stops the window extending across a jump and pads with the last good
  position, which is what keeps an atom that crosses a periodic boundary from
  being averaged with its own image.

Two mathematical properties are asserted alongside the transcription, because
they hold for *any* correct running mean and catch what a transcription test
cannot: a constant trajectory is unchanged, and a linear ramp is preserved away
from the ends. Both mutations tried against the suite — dividing by the window
width, and misreading the halves as asymmetric — are caught (5 and 1 failures).

## `protect` needed something to honour it

A flag nothing reads is decoration, so `protect`/`deprotect` are tested through
`translate` and `rotate` rather than by reading the mask back: protected atoms
move 0.000 Å while the rest move exactly the requested distance.

The transform seam moves every array at once, which is right for an unprotected
object and wrong as soon as `protect` has been used. Rather than teach
`apply_transform_to_object` which of its arrays are atom-indexed and which are
derived, the protected atoms are snapshotted, the transform runs, and their rows
are written back before the derived arrays are rebuilt — keeping the knowledge of
what is derived in the one place that already has it. With nothing protected the
helper returns `None`, so the common path is untouched.

## Polar contacts: one finder unblocked three visible things

`distance ... mode=2`. Before it, `preset technical` and `preset ligands` both
reported drawing no polar contacts and the object menu's **A ▸ find** submenu was
disabled outright — one missing piece behind three symptoms, which is what made
it the item to do next rather than the biggest one.

The algorithm is transcribed from `ObjectMoleculeTestHBond`,
`ObjectMoleculeFindBestDonorH`, `ObjectMoleculeGetCheckHBond`,
`ObjectMoleculeGetAvgHBondVector` and `CoordSetFindOpenValenceVector`. Three
details are invisible to a reader who does not open the C++ and each changes
the answer:

* **the cutoff is a curve, not a number.** The donor–acceptor limit slides with
  the A–D–H angle from `h_bond_cutoff_center` (3.6 Å, head-on) to
  `h_bond_cutoff_edge` (3.2 Å, at `h_bond_max_angle` = 63°). The names read
  backwards from what they do — *center* is the angle-zero end;
* **the virtual hydrogen sits 1.0 Å out**, not at the real X–H bond length:
  `FindBestDonorH` adds a *unit* open-valence vector. Only the direction is
  used, but "fixing" the length moves the angle and with it the cutoff;
* **an atom with no neighbours aims its hydrogen straight at the acceptor**
  (`copy3f(seek, v)` with the *unnormalised* seek vector), so the angle is zero
  and the test collapses to "within 3.6 Å". That is not a bug — it is how PyMOL
  finds water-mediated contacts in a hydrogen-less PDB, and it is reproduced.

### Donors and acceptors without bond orders

PyMOL derives them from bond orders, which a PDB does not carry, and fills the
gap twice: a hard-coded table of double bonds for standard residues applied while
connecting (`assign_pdb_known_residue`), and valence arithmetic for the rest.
chimol already holds the equivalent of the first — the `h_add` residue template,
which knows each named atom's hydrogen count and whether its centre is planar.
So a templated atom is typed from the template (which is what makes a backbone
carbonyl oxygen an acceptor and *not* a donor), an untemplated one from the
element's expected valence with the geometry read off its bond angles
(`ObjectMoleculeGetAtomGeometry`), and explicit hydrogens beat both.

Following PyMOL's own logic reproduces its ligand behaviour by construction: an
untemplated carbonyl oxygen reads as a donor in both, because a single bond and a
free valence slot look the same. **One deviation is deliberate**: PyMOL reads a
proline nitrogen's three single bonds as a tertiary amine, marks it a donor and
invents an amide hydrogen the residue does not have. The template says zero.

### The measurement that says the invented hydrogens are right

`hGBP1_closed.pdb` carries its hydrogens, so the same question can be asked
twice. With them: **735** contacts. With them stripped, so every hydrogen used is
a placed one: **803**, of which **729 are the same pairs — 99.2 % recall**. The
9 % extra are rotatable donors (hydroxyls, ammonium groups) whose real hydrogen
points elsewhere while a placed one is free to aim at the acceptor, plus a few
3₁₀-like i→i+3 backbone pairs. That is the direction the error should go.

On 148L the finder returns 234 contacts in 0.02 s, over 40 of them the i→i−4
backbone bonds that *define* an α-helix — the check that a unit test choosing its
own geometry cannot make.

### What came with it

`distance` grew PyMOL's full signature (`[name,] s1, s2 [, cutoff [, mode]]`,
plus `label`/`quiet`/`reset`) and modes 0–4; measurements became multi-segment
and **dashed**, through `dash_length`/`dash_gap`/`dash_width`/`dash_color`; the
**A ▸ find ▸ polar contacts** submenu is transcribed from `menu.py::polar`, with
halogen/salt-bridge/π left visible-and-disabled rather than dropped. Thirteen
settings moved from the missing list to the registered one (55 → 68), all of
them read by code.

## `transparency` runs the other way, and the setting says so

`transparency` and `two_sided_lighting`: first and fourth on the settings
worklist, and the two `preset ligand_sites` had been reporting as skipped.

**PyMOL counts transparency; chimol stores alpha; they run opposite ways.**
`transparency 0` is fully opaque and `alpha 1` is. Storing both is two numbers
that must agree and eventually will not, so `SettingSpec` gained `stored`/`shown`
transforms and the complement is declared once in the table: `set transparency,
0.4` echoes 0.4 and stores 0.6, `get` answers 0.4. A guardrail asserts that any
spec converting on the way in converts back on the way out -- a one-way
transform would compound the error on every subsequent `set`.

`unset transparency` restores **chimol's** 0.15, not PyMOL's opaque 0. `unset`
restores *the default*, and the default has to be the one this program ships;
changing that is a config-version migration, not something a settings entry may
do quietly.

### The picture caught what the tests could not

Wiring `two_sided_lighting` to the existing `twoSided` uniform *worked* by every
test -- and drew the wrong thing. That uniform flips the normal toward the
**light**, which is a different effect, written for flat nucleic base plates.
PyMOL's two-sided lighting flips a back face toward the **viewer**
(`gl_FrontFacing`); the old rule darkens a front face lit only by the fill
light, by flipping its normal away from that fill light. Fixed, with the
honest caveat that on a closed surface the two criteria mostly coincide, so the
measured difference in that scene is negligible (-8.09 vs -8.17): it is a
correctness fix justified by the failure mode it removes, not by a number.

**And the first metric was wrong.** Mean brightness over lit pixels *fell* 7.6 %
when two-sided lighting was turned on, which read as a bug. It is not: the newly
lit back faces are mid-grey and veil brighter cartoon pixels behind them. Only
the side-by-side images settled it -- off leaves the far half of the shell dark
and patchy, on gives a coherent closed envelope. A scalar over the whole frame
cannot tell "back faces now lit" from "bright cartoon now obscured", and
choosing one before looking is how a correct change gets reverted.

`preset ligand_sites` sets both for real now. Its fourth PyMOL step,
`surface_quality 0`, is deliberately **not** passed through: PyMOL's is a level
(0-4, coarse to fine) and chimol's is a grid *spacing* in Angstrom, where 0 is
not "coarse" but "infinitely fine". It would hang rather than approximate, so it
is named in the skipped list -- a real parity wart, written down instead of
guessed at.

## The tracer walks through a surface, and the twin that hid a bug is gone

`ray` took the nearest hit along each ray and sliced the colour to RGB, so a
surface at `transparency 0.6` traced solid: the viewport showed a glass shell
with the cartoon inside, `ray` an opaque grey blob. Now each ray composites
front to back -- every hit contributes its alpha, the remainder passes on, and
what is still transmitted at the end is background.

**It costs nothing when it is not used.** Measured on 148L at 300x220: opaque
renders in 3.60 s with four layers allowed against 3.83 s with one, because the
walk ends at the first solid hit. Translucent is 9.06 s -- 2.4x, not 4x, since
the walk also stops once the remaining transmittance cannot change a byte.

**The NumPy twin is deleted, and it had already rotted.** `trace()` kept a
pure-NumPy implementation of the same tracer behind `if _HAVE_NUMBA` *and* an
`except Exception` fallback. Nothing ran it while numba was installed -- so when
transparency was added to both, the NumPy one went in wrong (it referenced
`max_layers` without taking the parameter) and every test still passed. A
fallback nobody runs is not a safety net; it is an untested branch that fails
the day you need it. `_trace_numpy` and its three helpers are gone, numba is a
hard import, and the file is ~380 lines lighter.

Two process notes from doing it:

* **a bulk deletion by regex overreached** -- "from this `def` to the next" also
  swallowed `_LINE_SIDES` and `TRACEABLE_KINDS`, which sat between two
  functions. Diffing the *set of top-level names* against `HEAD` is what proved
  the repair complete; reading the diff would not have.
* **the first test asserted the wrong thing.** Colouring the molecule red and
  comparing "redness" fails because `color red` reddens the *surface* too, so
  the opaque case scores redder than the translucent one. The premise was wrong,
  not the code. It is now two spheres driven through `trace()` directly, where
  red can only reach the centre pixel by passing through the shell -- plus the
  converse, that an opaque shell must not leak it.

## `surface_quality` was three defects wearing one name

Flagged as a units wart -- PyMOL takes a level, chimol a grid spacing -- and each
measurement found something worse underneath.

**It is not a different quantity.** `RepSurfaceSetSettings` shows the level is a
*selector* for a point separation in Angstrom, which is exactly what chimol
stores. Eight levels over four base separations (`surface_best`,
`surface_normal`, `surface_poor`, `surface_miserable`), all transcribed, and the
four bases registered because the table reads them.

**Then the level did nothing.** Levels -3 to 1 moved 148L from 26 286 to 27 238
vertices -- 3.6 % across an eightfold request. `max_dim` caps the grid at 96
samples per axis and **rescales the spacing to fit**, so every fine level
collapsed onto the same grid.

**Then the reason turned out to be worse.** `_all_atom_coords` is in *scene*
units -- Angstrom x `_scale_factor` (10) -- and the configured spacing was passed
through as though it were scene units too. `0.8` asked for **0.08 A**, and the
cap clamped it straight back. The spacing had never had a measurable effect in
this path; `max_dim` was making the whole decision. `add_volume` already does the
conversion, so the bug is one path forgetting what its neighbour remembers.

With the conversion right and the cap following the request (ceiling 320
samples/axis, measured at 0.66 s for the finest realistic level on 1300 atoms):
2 446 / 13 654 / 25 876 / 105 922 vertices at levels -3 / -1 / 0 / 1. A 43x range,
monotone, and visibly different -- level -3 is a smooth blob and level 1 resolves
individual atoms.

**The default changed number without changing picture.** An honest 0.8 A would
have made every existing surface *coarser* than what users see (13 654 against
27 114). 0.5 A is PyMOL's own `surface_normal`, is `surface_quality 0`, and
reproduces today's appearance at 25 876 -- so that is the shipped value, moved by
a config-version migration (7 -> 8) that only touches copies still holding the
old default.

### And a fourth, found by pulling the same thread

`solvent_radius` was registered **twice**, onto two different config keys:
`surface.probe_radius`, which the surface mesh reads, and
`surface.solvent_radius`, which `get_area` reads. The later entry silently
shadows the earlier in the name table, so `set solvent_radius, 2.5` moved the
number the *area calculation* used and left the surface on screen untouched. One
physical quantity, two storages, disagreeing quietly -- which is exactly what the
`transparency` transform two hundred lines above it exists to prevent.

Both entries had plausible docstrings, the name resolved, nothing failed. Only
instrumenting the live path -- watching the config value stay at 1.4 while `set`
reported success -- showed it. Collapsed onto one key; `solvent_radius` now moves
the surface (34 770 / 30 744 / 25 260 vertices at probes 1.0 / 1.4 / 2.5 A, the
right direction: a bigger probe bridges more crevices). Two guardrails added --
no name registered twice, and no one name writing several config entries. The
reverse stays legal: `cartoon_side_chain_helper` and `ribbon_side_chain_helper`
are deliberately one setting here.

**Worth carrying: "the setting is registered" and "the setting works" are
different claims.** Four defects sat behind one flagged wart -- wrong type, no
effect, 10x units, two homes -- and every one of them had a live config path, a
passing test and a correct-looking name. Only measuring the *output* caught
them.

## The camera stayed where the user put it, once the aspect was fixed

Every scene rebuild refitted the camera, and a rebuild is what colouring, a
representation change, a label, a bond edit and **every** `set` all trigger.
Measured on 148L: `zoom resi 20-26` frames at distance 357, and **12 of 12**
ordinary commands put it straight back to 1730. Framing a site is the first half
of almost every task in a viewer and the second half undid it.

**This had been attempted and reverted, and the recorded reason was a symptom
seen through another defect.** The note said flipping the default was not
sufficient because `ray` then traced an empty image for every representation —
so the load-time fit looked as though it had nothing to measure. It measured
fine. The empty images were the aspect defect below: a never-shown window has no
viewport, so the camera went thirty times too far away, and refitting on every
rebuild hid it because the last rebuild landed after the widget had a size. With
`_aspect()` fixed, the same flip passes `test_ray_command.py` untouched.

Two things it needed on top, both found by measuring rather than reasoning:

* `_rebuild_after_coordinate_change` reuses `set_structure` — the *load* path —
  to re-derive after an edit, so `h_add` on a zoomed-in residue still jumped
  out. `set_structure`/`set_coordinates` grew a `fit_camera` argument; loading
  frames, re-deriving does not;
* nothing re-derived the distance on a **resize**, which refit-on-every-rebuild
  had been covering by accident. `resizeGL` now re-frames when the viewport's
  *shape* changes — distance only, since the clips carry a user's `clip`
  adjustments and a resize is not a request to discard them.

The resize correction **scales** the distance rather than recomputing it, which
is the other thing only a measurement finds: the scroll wheel moves the camera
without touching what was framed, so recomputing would snap a hand-zoomed view
back to the last `zoom`. `portrait_factor` is now one function in
`view_state.py` read by both the framing and the resize, rather than the rule
written twice.

0 of 12 after. The seven call sites that had been patched to `fit_camera=False`
one at a time are gone with the default; the only places that ask to frame are
now the three load paths. `test_camera_persistence.py` pins both halves: what
must not move the camera, and what must — with the trap that `orient resi 20-26` after
`zoom resi 20-26` correctly leaves the distance alone, so a "camera commands
still work" test has to start from a different framing than it asks for.

**Worth carrying: when an attempt fails, record what was measured, not what was
concluded.** "Reverted because `ray` broke" was true and sent the next session
to the wrong subsystem; "reverted because `ray` traced empty images, cause
unknown" would have cost one afternoon less.

## The portrait correction ran on a window that did not exist

Five tests in `test_camera_framing.py` were red, every one by a factor of
**exactly 30**, and the round number pointed at the wrong thing: chimol scales
coordinates by `_scale_factor` (default 10), which is close enough to feel
related. It is not. `scene_width()` subtracts the internal panel's 220-pixel
column and clamps what is left to **1**, so a `MolView` that has never been laid
out (100×30) reported an aspect of 1/30 — and PyMOL's portrait framing
correction, told the window was thirty times taller than wide, put the camera
thirty times too far away.

`_aspect()` now returns 1.0 below a 16-pixel viewport: an aspect measured off a
one-pixel column is not a measurement, and there is nothing to correct until
there is a window. Two guardrail tests, one per direction — the unlaid-out case
frames square, a genuine 400×900 portrait still corrects.

The lesson is the misdirection. A factor that matches a constant you already
know is not evidence; printing the actual `scene_width()` and `_aspect()` took a
minute and named it outright.

## Hydrogens need a template, and the reason is measurable

`h_add`/`h_fill`. The geometry is a transcription of
`layer2/HydrogenAdder.cpp::ObjectMoleculeSetMissingNeighborCoords`, where the
trap is the control flow rather than the constants: the `switch (n_system)`
**falls through**, so one existing neighbour on a tetrahedral centre yields the
second, third *and* fourth directions, each built from the ones before. Read as
an if/elif it produces one hydrogen where three are wanted.

**The count cannot be derived from valences without bond orders.** PyMOL works
from valences and warns in `h_add`'s own help that PDB files lack them for
ligands. Measured here on `hGBP1_closed.pdb` (4671 deposited hydrogens),
`valence(element) - heavy neighbours` is wrong for **41.6% of atoms** — it adds a
hydrogen to every carbonyl carbon, every carboxyl oxygen and every aromatic
carbon. So standard residues use a template of "how many hydrogens, and what
geometry", which is exact for proteins.

Validated against that protein by stripping its hydrogens and putting them back:

| | |
| --- | --- |
| counts correct | **99.78%** (4634 / 4644) |
| median position error | **0.10 Å** |
| within 1.0 Å | 97.8% |
| clashes introduced | none below 0.8 Å |

The 2.8% beyond 1 Å are **all** rotatable terminal groups — SER/THR/TYR
hydroxyls, CYS thiols, and the amide and guanidinium NH₂ groups — whose torsion
the geometry does not determine and which PyMOL also places arbitrarily. A test
asserts that set, so a *backbone* atom appearing there would fail rather than be
absorbed into the tolerance.

Two corrections a per-residue template cannot express, both found by that
comparison and both the *only* disagreements in 4644 atoms:

* **the N-terminus is an ammonium, not an amide** — three hydrogens on a
  tetrahedral centre. Detected from the bond graph (a backbone nitrogen with no
  preceding carbonyl), so it needs no separate residue name;
* **histidine's tautomer is a property of the structure, not the residue.**
  ND1-protonated is assumed unless the file already carries a hydrogen on NE2.
  Without hydrogens to read, the two are indistinguishable — so it is stated
  rather than implied.

A residue with no template is **named and skipped**, not approximated. An
approximate hydrogen is worse than a missing one, because it looks like data.

## Sessions carry everything, and the field list is derived

`session_save` / `session_load` / `session_info`, with `save x.pse` and
`load x.pse` routed by extension because that is what a PyMOL user types. A
reloaded session renders **pixel-for-pixel identically** to the one saved --
verified by comparing two real GL framebuffers, which is the only check that
covers the whole path.

**The object field list is derived from the state dataclass, not written out.**
That dataclass has 53 fields; a hand-kept list drifts the first time one is
added, and the drift is silent -- the session saves, reloads, and quietly lacks
whatever was new. A test guards it by round-tripping `bond_edits`, a field added
by separate work and named nowhere in the session code.

Three things that were bugs first:

* **JSON objects only have string keys, and some of ours are tuples.** The
  bond-edit map is keyed by an `(i, j)` atom pair. Skipping non-string keys
  dropped every recorded bond *order* while keeping the bonds, so a reloaded
  session had single bonds where doubles had been set. Non-string-keyed dicts are
  now stored as key/value pairs.
* **The camera has to be restored after the GUI refresh.** Rebuilding the object
  panel re-zooms, replacing the saved distance (slot 11) and clip planes (15, 16)
  with ones computed from the bounding sphere. Rotation and pivot survived, so
  the view looked restored while the framing was wrong -- three numbers out of
  eighteen, invisible unless compared element by element. `load_session` returns
  the view so whoever touches the camera last is the one restoring it.
* **`get_view` is a command; the viewer's accessor is `get_view_state`.** Reaching
  for the command name stored a null view behind an `except` clause.

**Deliberately not PyMOL-compatible.** A `.pse` is a pickle of PyMOL's C
structures. chimol writes a zip of `manifest.json` plus `arrays.npz`: readable
without chimol, and loading one cannot execute code (`allow_pickle=False`). A
format people exchange should not be a code-execution path. Saving to `.pse` says
so, and a real PyMOL session handed to `session_load` is named as such rather
than reported as corrupt -- that is the mistake a PyMOL user will actually make.

Anything a session cannot carry -- an opaque RMF hierarchy handle, say -- is
**named in the message** rather than dropped, and a field from a newer session is
reported instead of crashing the load.

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

A group name inside an *atom selection* — `show cartoon, ligands` — is handled
by the multi-object resolver described in the next section. It was the last
place a group was not a first-class name.

## One atom table, not one object

PyMOL's selector runs over **one global atom table spanning every loaded
object** (`layer3/Selector.cpp`). chimol evaluated per object and against the
*active* one, and three consequences followed, each of them silent:

* a **group name** selected nothing — `count_atoms ligands` said `0`, and every
  representation, colour and camera command aimed at a group did nothing at all.
  The object panel's group rows emit exactly those commands, so a whole row of
  A/S/H/L/C buttons was inert;
* a plain `chain A` meant chain A **in the active object**, so `count_atoms all`
  under-counted by every other molecule on screen;
* a name that resolved to nothing **answered `0`** instead of erroring, which
  made a typo indistinguishable from an empty selection.

`_resolve_selection_to_atom_masks` returns `(object_id, name, mask)` per object;
the union is assembled in the command layer rather than inside the evaluator,
which stays per-object. The singular `_resolve_selection_to_atom_mask` remains
for the commands that genuinely want one object (`get_area`, `symexp`,
`pair_fit`) and **prefers the active object** among the hits, so those keep
answering about the molecule in front of the user.

Rules transcribed from `SelectorSelect0`, in its order: object, stored
selection, group, then `Invalid selection name "x"` — with a leading `?` as the
"undefined is allowed here" escape (`?sele`), which needed a tokenizer change or
the one spelling that suppresses the error would have raised it.

Framing had to follow: `MolView.zoom`/`center`/`orient` take a `selections`
list, because measuring one member of a group and reporting success is exactly
the failure that looks like it worked.

Migrated to the plural resolver: `show`/`hide`/`as`, `color`, `spectrum` — one
ramp over the whole selection, or a group restarts the palette at each member —
`zoom`/`center`/`orient`/`origin`, `count_atoms`, `select`, `label`, `remove`,
`alter`/`iterate`/`*_state`, and `mask`/`protect`. The last pair matters more
than it looks: their default is `all` and their purpose is one molecule sitting
in front of another, so reaching only the active object left exactly the
molecule you were trying to stop clicking through. `alter`/`iterate` share one
`stored` namespace across the objects, which is what makes accumulating over a
group work. Deliberately still single-object: `get_area` (its occlusion model is
per object), `save`, `symexp`, `pair_fit`, `intra_rms`, and bond editing.

**Three defects fell out of using it**, all pre-existing and invisible until a
command reached a second object:

* `color` refused every object `create` had made — it required a residue table
  that a copied ligand does not have, and blamed *atom coordinates that were
  right there*;
* an object without a residue table is drawn by the point-sphere path, which
  read `colors_per_ca` and never the per-atom override — so `color` wrote a
  value nothing looked at, and the molecule stayed its default colour while the
  command reported success. **The state and the scene disagreed**, which is why
  a state assertion would have passed; it took a screenshot;
* `hide everything` with no selection only reached the *active* object, because
  nine of the ten representation setters write the active object's state and
  only `spheres` had a spanning `_all` variant.

## The presets wore PyMOL's labels and made a different picture

A preset is the one-click path from "loaded" to "looks like a figure", and the
busiest entry in PyMOL's object menu. Ours were **four hand-rolled lines** —
`hide everything, {sele}; show cartoon, {sele}` — under the labels *simple*,
*ball and stick*, *ligand sites* and *technical*. Same words, different picture,
which is worse than not having them: the label is a promise about what you will
get.

All fifteen are transcribed from `modules/pymol/preset.py` now
(`cmd/presets.py`), with PyMOL's names, reachable as a `preset` command and from
the menu — whose shape follows `menu.presets`, including the *ligand sites*
submenu of surface variants. What chimol cannot do, it **names**: `technical`
and `ligands` report that they drew no polar contacts (that needs a
hydrogen-bond finder, not `distance`, which measures between two picked atoms);
`pretty` reports the three cartoon settings chimol's cartoon does not implement;
the surface variants that differ only by `surface_type`/transparency are shown
disabled with the reason. A preset that quietly does less than PyMOL's is the
failure the module exists to avoid.

Two divergences apply throughout and are stated once rather than left to be
discovered: PyMOL scopes a setting to a selection and chimol's settings are one
global config, and PyMOL's `ribbon` is thinner than its cartoon while chimol
draws one cartoon for both.

**The chain colour cycle had to come first.** `util.cbc` is what `simple`,
`technical`, `ligands` and `interface` colour with, and it walks PyMOL's
40-entry `_color_cycle` in `get_chains` order. chimol had **eight invented
colours assigned in first-seen order** — so every multi-chain figure came out
differently from PyMOL, and differently again depending on how the file was
written. Transcribed as `colors.CHAIN_COLOR_CYCLE`; chain A is the carbon green,
B cyan, C light magenta.

## Side chains that grow out of the ribbon

`cartoon_side_chain_helper`, transcribed from `SideChainHelper.cpp` into
`analysis/side_chain_helper.py`. PyMOL's `pretty` and `ligand_cartoon` presets
set it, and it is why they look the way they do: a cartoon with sticks on a few
residues is a mess otherwise, because each stick residue also draws its backbone
N, C and O inside the ribbon.

The thing to get right is that it is a **bond filter, not an atom filter** — the
atoms stay in the model and stay pickable, and it is the bonds *between* them
that are dropped where a cartoon already covers them. Suppressed: `CA-C`,
`N-CA`, `N-C`, `C-O`/`C-OXT`, and every hydrogen on CA and N. Kept: `CA-CB`,
which is what the side chain hangs from. Two exceptions carry the meaning —
**proline** keeps its `N-CA` because its ring needs it, and `marked` atoms (a
cartoon here, none on the bonded neighbour) keep their backbone bonds so sticks
at the end of a segment still reach the ribbon. Measured on 148L residues 20–26:
62 stick bonds become 35, and the 27 dropped are exactly 7 `N-CA`, 7 `CA-C`,
7 `C-O` and 6 `C-N`.

PyMOL's nucleic branch (`na_mode`, the `C[45][*']` bonds) is not transcribed, so
the helper only ever hides protein backbone bonds.

**Vectorised, because it runs on every scene rebuild.** The first cut was a
per-bond Python loop: 4 ms on 1 000 bonds is invisible, but **1.3 s on 500 000**,
and this repository's demos reach that. Every test in the rule is on the two
endpoints, so it rewrites as gathered boolean arrays with the same result —
**332 ms at 500 000 bonds, 4× faster**, identical hidden counts at every size.
It is left there rather than tuned further because the filter runs *after* the
sticks mask, so its input is the scoped bond list: a binding site is ~60 bonds,
and reaching 500 000 means sticks on everything, which is a heavy scene already.

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

## The refusal outlived the limitation

"The tracer draws spheres only and cannot render a cartoon" was true when it was
written and stopped being true when `render_scene` learned triangle meshes — the
cartoon *is* a triangle mesh, and so are sticks, surface and metaballs. What kept
it true in practice was the **guard**: `ray` decided what to do from the count of
visible *spheres*, which a cartoon-only display (PyMOL's default, and chimol's)
leaves at zero, so it returned early with the message and never reached the scene
path sitting fifty lines below that could have drawn it. A capability nobody
could invoke, behind an error message asserting it did not exist.

The lesson generalises: **a stated limitation is a claim with a shelf life.** It
was re-read as documentation by everyone who came after, including the guide and
this tracker, and the one test covering it asserted the *refusal* — so the suite
defended the bug. When a limitation is lifted somewhere else in the tree, the
sentence stating it is a call site that needs updating.

`ray` now asks the scene what it holds. Also from that work:

* **`line` geometry is traced**, as PyMOL does it: a segment becomes a *sausage*
  (`ray->sausage3fv`, `layer1/CGO.cpp` `CGO_LINE`), split at the midpoint into
  two capped cylinders so each half keeps its own atom's colour
  (`CGO_SPLITLINE`). The tracer has no cylinder primitive, so the shaft is
  tessellated and the caps stay spheres — which it intersects exactly. Width
  follows PyMOL's `line_radius`-else-`PixelRadius * line_width / 2`, so a line is
  *n pixels* wide at any output resolution.
* **`text` is the one kind that cannot be traced**, and is named in a message
  rather than dropped.
* **The fallback could contradict the viewport.** With the scene empty after
  `hide everything`, `ray` fell through to `get_atom_sphere_data`, which still
  offered 32 ligand atoms — and drew a molecule that was not on screen. A viewer
  that produced a scene has already said everything it draws; the atom path is
  now only for a viewer that has no scene at all.

Still open: transparency (a `render_mode="transparent"` surface traces opaque),
and the baked-occlusion interaction below.

## A mesh that is really spheres should say so

Routing `ray` through the scene made `as spheres` **380× slower** before anyone
noticed the picture was the same: the viewport draws space-filling spheres as one
merged mesh, so 1363 atoms of 148L arrived as 210 240 triangles — **113.9 s**,
against **0.3 s** for the 1363 spheres the tracer intersects exactly and without
facets. The ball mesh now carries the centres and radii it was built from in
`Geometry.meta["spheres"]` and `render_scene` prefers them: 113.9 s → 0.3 s.

The record is kept **at the builder**, not rebuilt in the tracer from
`get_atom_sphere_data`, for the same reason the sphere fallback had to go: a
second source for "which atoms are drawn" is a second answer.

And the builder existed **twice** — the shared `_build_balls_mesh` and an inline
copy of it in the scene builder, sixty lines of the same tessellation plus a
duplicated nested guard with identical conditions. They had already diverged
(only the inline one baked occlusion), and the `meta["spheres"]` record landed in
the copy nobody was calling, which is how the duplication surfaced. **A duplicated
builder does not merely drift: it cannot *receive* what the other learns** — the
same shape as the RMF reader's private route into the viewer. 83 lines deleted;
`_build_balls_mesh` takes the bake as an argument and is the one builder.

## Every ray tested every primitive

The sphere-mesh finding above is the same bug seen through a keyhole. Trading
210 240 triangles for 1363 spheres bought a 380× speedup because the tracer's
cost was **linear in the primitive count per ray** — so the fix that worked for
one representation could not work for any of the others, whose triangles are not
secretly spheres. A cartoon is 39 252 triangles and a solvent surface 51 748, and
each of them was intersected by every sample, for every transparency layer.

Measured on 148L at 320×240 with 2×2 samples, before and after a BVH:

| Representation | Geometry | Before | After | |
| --- | --- | --- | --- | --- |
| cartoon | 39 252 triangles | 19.12 s | 0.126 s | **151×** |
| sticks | 33 216 triangles | 8.96 s | 0.062 s | **144×** |
| surface | 51 748 triangles | 35.00 s | 0.198 s | **177×** |
| lines | 5 536 caps + shafts | 51.11 s | 0.152 s | **337×** |
| spheres | 1 314 spheres | 0.32 s | 0.058 s | 5.6× |

A publication-sized cartoon — 1024×768, 2×2 samples — went from **195 s to
0.30 s (651×)**. The win grows with resolution because the one linear cost left
is building the tree, which is paid once per render rather than once per ray.

`spheres` gains least because it was already the cheap case: it is the one
representation whose primitive count the earlier fix had brought down to 1314.
That is the tell that the sphere-mesh work had treated a symptom.

**The picture is unchanged, and that was checked rather than assumed.** Rendering
each representation through both tracers and differencing the images: cartoon,
sticks and surface are **bit-identical**, every pixel. The tree changes which
primitives a ray tests, never what a hit is.

`spheres` and `lines` do differ, in 3.6 % and 0.03 % of pixels, and the cause is
a defect the tree exposed rather than caused: the shadow query returned
**whichever occluder came first in the array**, so how soft a contact shadow came
out depended on the order the scene happened to be built in. PyMOL takes the
nearest one, and takes it precisely when the decay is on —
`nearest_shadow = (shadow_decay != _0)` in `layer1/Ray.cpp` — because the decay
is a function of how far the occluder is, so any other occluder answers a
different question. Every one of the 2 788 changed pixels is **brighter, none
darker**, which is what the nearest occluder implies under
`occlusion = 1 − exp(−(t − decay_range) · decay)` and is how the change was
confirmed to be that one change and nothing else.

A second defect fell out of the same place: the hit primitive was passed to the
shadow query as the sphere to skip, **without checking it was a sphere**, so a
triangle hit excluded the sphere sharing its index from casting. Invisible on a
pure cartoon (no spheres) and on pure spheres (indices agree); it needed a mixed
scene, which is exactly what a wireframe is.

**What made this survivable for so long** is that the tracer was correct. There
was no wrong picture to notice, only a slow one, and slow reads as "ray tracing
is expensive" — a statement about the technique rather than about this
implementation. The 380× sphere-mesh finding should have been the alarm: a
speedup that large is rarely a property of the geometry, it is usually the
complexity class.

The tree is a binned-SAH BVH in
[`renderer/bvh.py`](/chisurf/plugins/chimol/chimol/renderer/bvh.py); spheres and
triangles share one index space so a mixed scene is one tree and one descent.
The guardrails are in `test/test_bvh.py`, and the one that matters is the last:
every correctness test there passes just as well against an exhaustive search,
so cost is asserted separately, or removing the tree would leave a green suite.

Two traps found building it, both of which draw a plausible wrong picture rather
than failing:

* **A cartoon is full of exactly axis-aligned triangles**, whose bounding box is
  exactly flat in one dimension. A ray travelling in that plane computes
  `0 × inf`, and the NaN loses every comparison — so the triangle silently
  leaves the image. The bounds are padded at build time.
* **A traversal stack that overflows drops geometry**, so the build caps depth
  and forces a leaf rather than letting a pathological split sequence outgrow
  the stack. An over-full leaf is merely slow, which is the right way for this
  to fail.

## The depth cue was normalised against the wrong range

Measured while checking that the traced cartoon looked right — it came out dark,
and the cause was not the cartoon. The fog fraction was `best_t / far_clip`:
distance from the **camera**, over a far plane fitted to nothing. On 148L the
camera sits 1730 units out with a far plane at 2442, so the whole molecule
occupied 0.58–0.83 of the range and every pixel of it was fogged 24–69 %. No
pixel anywhere in the image was unfogged, which is a dimmer, not a depth cue.

PyMOL normalises over its front-to-back **clipping** range —
`ffact = (front - dist) * invFrontMinusBack` (`layer1/Ray.cpp`) — and those planes
are fitted around the object, so its fog spans the molecule exactly. `trace` now
takes `fog_front`/`fog_back`, and `render_scene` derives them from the scene's own
bounding sphere. Measured on the 148L cartoon: mean lit pixel 21.9 → 33.3,
p95 60 → 96, brightest 173 → 255.

`camera.far_clip` had **no other consumer** — it was named as a clipping distance
and only ever used as the fog denominator, which is how it survived: a wrong
value for the fog looked like a right value for something else. Two call sites
had grown a `× 1.2` widening of it, compensating for a fog they had not
diagnosed; both are gone.

## Three defects found by *using* the feature, not by testing it

Each was invisible to the suite and obvious the moment a real command ran:

* **`label` stored the text and showed nothing.** PyMOL's `ExecutiveLabel`
  follows the text with `OMOP_VISI(cRepLabelBit, cVis_SHOW)`
  (`layer3/Executive.cpp`) — labelling *turns the representation on*. ChiMOL's
  did not, so `label name CA, resi` reported "Labelled 11 atoms" over an
  unchanged view and the fix was a `show labels` the user had to guess. A
  success message over a blank view is the worst shape a defect can take.
* **`ray` raised before casting a ray, whenever there was a window.** It set its
  progress display up with six `QProgressDialog` calls; `ChiSurfProgress` is a
  facade that carries most of that surface deliberately, so five worked and
  `setMinimumSize` raised. The headless path skips the display entirely — so the
  tests, which are headless, exercised the one path that worked. The caller now
  uses the facade's own spelling, and the facade grew the two members it was
  missing (`setMinimumSize`, `deleteLater`), because an incomplete compatibility
  shim is worse than none: it invites exactly this call site.
* **Seven scoped-representation masks were unclassified for `sort`.**
  `test_sort_mask::test_every_array_field_is_classified` — the guardrail written
  for precisely this — had been red since the masks landed. Six are atom-indexed;
  `trace_mask` is per *residue*, like `cartoon_mask`, because the trace is one
  point per CA.

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

# Rendering: the next front, and what it needs

The target ([specs/chimol](/specs/chimol.md)) puts rendering first, because it is
where "better than PyMOL" is actually won. ChimeraX's model is surveyed there.
This section is the *implementation* finding, so the next round starts from the
design rather than rediscovering it.

## Silhouettes — the algorithm, transcribed

From `graphics/src/fragmentShader.txt` (`USE_DEPTH_OUTLINE`) and
`opengl.py::Silhouette._draw_depth_outline`. A full-screen pass over the **depth
texture**:

1. sample this fragment's depth `d0`;
2. take `ds` = the **minimum** depth over a disc of radius `thickness` around it,
   excluding the centre;
3. discard unless
   `nf*(d0 - ds) >= jump * (1 - nf1*ds) * (1 - nf1*d0)`, where `nf` is the
   perspective near/far ratio and `nf1 = 1 - nf`;
4. otherwise write the silhouette colour.

The `(1 - nf1*ds)(1 - nf1*d0)` factor is the part that is not guessable: it
**linearises the non-linear depth buffer**, so `depth_jump` is a fraction of
*scene* depth rather than of buffer values. Without it the outline thickness
varies with distance and the setting means nothing consistent. Under an
orthographic projection `nf = 1`, the factor collapses to 1, and the test is a
plain depth difference — so a first implementation can be checked against the
simple case before trusting the general one.

Defaults: `thickness = 1` px, `color` black, `depth_jump = 0.03`.

## What chimol lacks

**Superseded — read the section above first.** The scaffolding described here as
missing exists (`renderer/postprocess.py`), and silhouettes are built on it. What
was missing was that switching it on broke the window; that is fixed. The
remaining items are multishadow occlusion and depth cue, which reuse the same
target. Kept for the design it records:

`qtgl.py` rendered straight to the default framebuffer: no
framebuffer-object scaffolding, no depth texture, no full-screen-quad pass and no
second shader program. Silhouettes, multishadow occlusion and depth cue all
need that scaffolding, so it was the first task and it is shared:

1. an FBO with a colour **and depth texture**, sized to the viewport and rebuilt
   on resize;
2. `paintGL` renders into it, then blits colour to the default framebuffer;
3. a texture-window helper — quad VAO plus a shader program taking the depth
   texture — for post-process passes to reuse.

Only then is the silhouette pass a small addition. Doing it the other way round —
bolting one pass into `paintGL` — is what makes the second and third effects
expensive.

**This must be verified in a real window.** Offscreen Qt creates no GL context, so
none of it is exercised by the offscreen suite; see the capture notes above.

## The viewport had no depth cue, and the settings for it were pointed at the tracer

`depth_cue`, `fog` and `fog_start` are **global** settings in PyMOL:
`SceneSetFog` (`layer1/Scene.cpp`) applies them to the *viewport*, and the ray
tracer follows unless `ray_trace_fog` / `ray_trace_fog_start` override — which
is why PyMOL has those two as separate names at all. chimol registered all three
against `ray.*` and applied them only to the tracer, so the interactive view had
**no depth cue at all** and the traced image disagreed with the viewport it was
supposed to reproduce.

The shader was already written for it. `fogDensity`, `fogColor`, the uniform
lookup and a `mix` in the fragment shader were all in place, and
`self._fog_density = 0.0` in `__init__` was **the only assignment anywhere in
the tree**. A complete feature held off by one initialiser — the fourth thing
this session that was built and unreachable, after the tracer's refusal, the
scaffolding, and the silhouette composite.

Two things had to be right, and both are transcribed rather than invented:

* **The shape.** PyMOL's fog is *linear between two planes*, not exponential in
  distance. `fog = (g_Fog_end + eye_pos.z) * g_Fog_scale` (`data/shaders/default.vs`)
  is a **visibility** — 1 unfogged — with `g_Fog_scale = 1/(end − start)`.
  chimol's shader had `1 − exp(−density · |viewPos|)`, which is a different
  curve and makes `fog_start` mean nothing.
* **The planes.** `FogStart = (back − front) · fog_start + front`, and
  `FogEnd = FogStart + (back − FogStart)/fog` when `fog` is in (0, 1), else
  `back`. Front and back are the planes fitted **around the scene** — camera
  distance either side of the target radius — not the camera's far plane. That
  is the identical distinction the tracer's fog fix turned on, and getting it
  wrong there had fogged every pixel 24–69 % with none left unfogged.

Measured on 148L as spheres, cue off against cue on: **91.6 % of lit pixels come
back unfogged** and the recessed ones fall to 0.48 of their brightness. The
guardrail asserts *both halves of that pair* — something fogged **and** something
not — because a dimmer passes either one alone. That is what the tracer's fog
failure looked like from inside a single-number check.

Defaults are PyMOL's: `depth_cue` **on**, `fog` 1.0, `fog_start` 0.45
(`SettingInfo.h` 84, 88, 192).

**One store, read where it is used.** `_fog_planes` reads the config on every
frame instead of caching onto the renderer, so `set depth_cue, off` cannot leave
a stale copy behind — which is exactly the failure the silhouette settings still
have, one section down.

Still open: the config path is `ray.depth_cue` / `ray.fog_start` /
`ray.fog_intensity`, which now reads wrong for settings that govern both
renderers. Moving them to a section of their own is a **key move**, and the
migration table only knows how to update a *default* — so it needs a small
extension to the loader rather than a table entry, and is worth doing with
`silhouette`'s two-store problem in the same change.

## The FBO scaffolding was built, and switching it on broke the window

The "what chimol lacks" list below said there was **no** render-to-texture
scaffolding and named it the next task. It has been there for some time, with
silhouettes on top of it — the entry was a claim with a shelf life, like the
tracer's refusal. What was true is that **nobody could have used it**: turning
silhouettes on took the sequence strip off the screen and jumped the molecule
half an inch up the window.

Three defects, all in how the offscreen pass meets the rest of the frame, and
all invisible to the suite because nothing rendered a *window* with an effect on.

* **The overlay was painted before the composite.** `_render_overlay` draws with
  QPainter, which targets the **widget's** framebuffer rather than the bound
  one, so the chrome went down first and the composite blit then erased it. The
  strip lost **53 %** of its ink. The two early-return paths in `paintGL`
  already ran `end()` first; only the path that draws a molecule did not.
* **The offscreen buffer was the window's full height** while the direct path
  reserves a band for the strip, so the scene was rendered centred in a taller
  frame than the one it is shown in and visibly shifted — and the blit, sized to
  that buffer, covered the band as well.
* **A window that has not been laid out built a 1-pixel-wide framebuffer.** The
  same `scene_width` floor that once told the camera the window was thirty times
  taller than wide: the scene renders into it, `end` blits a one-pixel column
  back, and **the molecule disappears**. The effect passes now decline below
  `_MIN_MEASURABLE_SCENE`, which is what they already do when no effect is on.

**The metric lied before the picture did, again.** The first measurement said
"10.28 % of pixels changed — the setting works". It did change the picture: it
was deleting the strip and moving the molecule. A real outline moves **0.15 %**.
That ratio is now the assertion, because *more* change is the failure here, not
less — and it is the same lesson the two-sided lighting work recorded one
section down, arrived at from the opposite direction.

Guardrails in `test_lighting.py`, which already renders real framebuffers. The
strip one asserts **ink coverage**, not pixel equality: painting after a
composite leaves QPainter different GL state and moves glyph antialiasing by up
to 12/255 (mean 0.38) with the two crops indistinguishable side by side, while
erasure takes the ink to nearly nothing. Both were checked against the old code
and do fail there.

The third defect also caught the *test* out before the code: a window restored
from a persisted dock layout handed the 3-D widget 109×350 — less than the
panel's own 220-pixel column — so the helper forces a viewport and **asserts**
it got one rather than skipping. A guardrail that quietly stands down is what
this file exists to avoid.

Still open here: `set silhouette, on` is not a registered setting, so the feature
is reachable only through the ChimeraX-style `lighting silhouette=on`. And
`set_lighting` writes `_post` directly while `_DISPLAY_CONFIG["silhouette"]` is
read only at construction — two stores for one state, so the config is a startup
default that a live change never reaches. Registering the name means fixing that
first, or it is one more setting that stores and does nothing.

## Every frame rebuilt the whole scene, through a colour query

Found while costing the impostor route below, and it made that route
unnecessary. `paintGL` → `_render_overlay` → `_refresh_gui_state` →
`get_residue_colors` → **`_build_scene_for_current_object`**. The sequence strip
has no signal telling it that `color`, `spectrum` or `ss` ran, so it re-reads the
residue colours every frame — reasonable — but the only way to get them ran the
whole scene builder. With a surface shown that is a density grid, marching
cubes, gradients and ambient occlusion, **sixty times a second**.

148L at 1280×860: surface **82.12 ms → 4.25 ms** (12 fps → 235 fps), cartoon
28.34 → 4.12, spheres 17.34 → 4.94, sticks 11.61 → 3.91. The colour computation
is split out as `_recompute_colors_per_ca`, which is all `get_residue_colors`
now calls.

**The measurement is the transferable part.** Frame time was *flat against pixel
count* — 8× the pixels, same milliseconds — which rules out fill and vertex work
together and says the cost is fixed CPU work per frame. That is what redirected
the search from the shaders to the profiler. **Ask a frame to scale before
assuming what it spends on.**

The call site carried the comment *"Reading them back is a cached array copy,
which costs nothing beside drawing the molecule itself."* It was the most
expensive thing in the frame. Same shape as the refusal that outlived its
limitation: **a comment asserting a cost is a claim with a shelf life**, and this
one was load-bearing — it is why nobody looked here.

One hazard the split introduced and the fix had to close: `get_residue_colors`
sized its array from `self._coords.shape[0]`, which on a **trajectory** is the
frame count, not the residue count. The old code got away with it because the
rebuild set the array correctly and a shape check then rejected the *return
value*; computing it directly would have stored a wrongly-sized array on the
viewer for the renderer to read. `_ca_coords_2d` is now the one definition of
what a per-residue array is sized by, and it is read-only, so a colour query
cannot advance a trajectory.

Guardrail in `test_trajectory_performance.py`, structural rather than timed like
everything else in that file: the scene builder must not be entered at all. It
was checked against the old code and does fail there.

## Shader techniques worth taking, read from a WebGL viewer

Surveyed 2026-08-05 in `junk/ngl/src/shader/`, which is a small, complete and
readable set — the opposite of PyMOL's, and the reason to read it for *how* while
reading PyMOL for *what*. Not started; listed by what each would buy.

**1. Impostor sticks and cylinders — and the measurement says take it for
*quality*, not for speed.** `CylinderImpostor.vert` + `.frag` (130 + 356 lines)
ray-cast a cylinder in the fragment shader from one quad, which is exact at any
zoom where 148L's sticks are **33 216 triangles** approximating a few hundred
capped cylinders. `HyperballStickImpostor.frag` goes further and renders the
smooth hyperboloid join PyMOL cannot draw at all.

The speed argument was measured and **does not hold at this scale**. Once the
per-frame scene rebuild above was removed, 210 240 vertices (spheres) cost
0.9 ms more per frame than 5 536 (lines) — so trading vertices for fragment work
has about a millisecond to win on an ordinary molecule, against a ~3.9 ms floor
that is the sequence strip's text. Impostors stay the right answer above
`impostor_min_atoms` (20 000), which is what they were added for.

Where it would still pay is the **ray tracer**: a real cylinder primitive would
replace the tessellated 8-sided shafts `_sausages` builds, cutting the traced
primitive count and removing facets — the same trade `meta["spheres"]` already
makes for balls, and the tracer intersects analytic primitives exactly.

**2. `interior_fragment.glsl` — 8 lines, and it fixes clipping.** When a clip
plane cuts a surface, the shell reads as hollow because the camera sees the
*inside* of far-side triangles lit as if they were outside. NGL colours any
back-facing fragment with an interior colour and darkens it, so a cut surface
reads as solid material. This is the same `gl_FrontFacing` test the
`two_sided_lighting` work already put in the shader, so the hook exists. Related
to the interior-cull item in the integrative-model notes.

**3. `opaque_back_fragment.glsl` — the cheap half of order-independent
transparency.** Forcing back faces opaque makes a translucent closed surface
depth-sort correctly without sorting anything, which is the defect that makes
GL transparency disagree with the (now correct) traced transparency.

**4. `SDFFont.vert`/`.frag` — labels that stay crisp.** Signed-distance-field
glyphs scale to any zoom from one small atlas, where rasterised glyphs blur.
Worth noting this does *not* help `ray`, which has no glyph and says so.

**5. `matrix_scale.glsl` — four lines.** Recovers the scale from a model matrix
so an impostor's radius survives a scaled transform. Cheap insurance the moment
item 1 lands, and exactly the class of bug the two-coordinate-array finding was.

# The window, not the commands

Measured 2026-08-03 by photographing the window in a realistic state and reading
PyMOL's layout rules from its source rather than from memory. The *panel* was a
faithful PyMOL clone — object list with A/S/H/L/C, mouse-mode block, sequence
strip. The window around it was not, in three ways that a construction test
cannot see and a screenshot shows immediately.

| | PyMOL | ChiMOL, before |
| --- | --- | --- |
| Movie panel | zero height until a movie exists | full-width scrubber + nine buttons for `State 1/1` |
| Command prompt | always on screen (`internal_prompt`, default 1) | a background tab in a side stack |
| Side panels | none — the object list is *in* the viewport | a third of the window, holding a filter box and white space |

**The movie rule is exact and worth quoting**: `MovieGetPanelHeight`
(`layer1/Movie.cpp`) returns zero unless `MovieGetLength()` or
`SceneGetNFrame(G) > 1`. In chimol `mset` sets the frame count, so the two
conditions collapse to one. It was the loudest thing in the panel — a salmon bar
across the whole block — and it controlled a timeline of one.

**The prompt is not a nicety.** `internal_prompt` and `internal_feedback` are
both on by default and PyMOL draws them at the bottom of the viewport, because
typing commands *is* how the program is driven. Ours had a console with output,
history and completion, docked as the fifth tab of a stack whose first tab was
showing — so the first thing a PyMOL user reaches for was invisible until found.
It is now the row under the view, full width.

**An empty panel is worse than no panel**: it reads as a broken layout. The three
side panels have nothing until a file brings it — a hierarchy, an RMF, a map — so
they start hidden and *reveal themselves* when they have content
(`_reveal_panel_with_content`). Hidden, not removed: the View menu and a
right-click on a tab bring them back, and nothing else tells someone their
integrative model has a hierarchy to browse.

## The layout was authored and never applied

Chasing the above found a defect in the **shared** dock area, so every view in
ChiSurf is affected. `set_layout_state` applied the authored `sizes` at build
time, when the splitter is about 100×30 — `setSizes` clamps each share to the
children's minimums, and the resize that follows redistributes by rules of Qt's
own. Measured on the chimol default: an authored **700/170 came out 230/614**,
inverted, giving most of the window to the console it meant to give a strip to.

Two attempts failed before the third worked, and both failures are worth
recording. Re-applying once on the event loop lands *before* the window is
resized. Stretch factors do not survive either — `QSizePolicy`'s stretch is a
`uchar`, so an authored `700` silently becomes `255`, and even at the right
ratio the split still came out inverted. What works is to treat the numbers as
**proportions and re-apply them on every resize**, until the user drags that
divider — at which point their choice replaces the author's for good. That is
also the behaviour anyone expects from a divider they just moved.

## Two menu entries that did nothing

Both found by using the window rather than testing it, and both silent:

* **View ▸ Toggle Sequence** toggled a dock retired when the strip moved into
  the viewport. `_set_tab_visible` looped over every tab, matched the name
  against none, and returned; the entry ticked and unticked and the strip never
  moved. It writes the `seq_view` setting now — the same place `set` writes, so
  the menu and the command line cannot disagree.
* A **group name inside an atom selection** answered *emptily*: `group stuff,
  ligs 148l` then `show cartoon, stuff` did nothing and reported nothing, and
  `count_atoms stuff` said `0` rather than "unknown selection". Note this was
  *worse* than the "not accepted in a selection" this file used to record — it
  was accepted, and lied. **Fixed** by the multi-object resolver; see
  [One atom table, not one object](#one-atom-table-not-one-object) below.

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
