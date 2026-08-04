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
`symexp`/`get_symmetry`/`set_symmetry`.

**Remaining:** `cealign` (skipped by request), `matrix_copy`,
`ramp_new`, `cartoon_putty`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.
`set_bond`/`get_bond` (per-*bond* settings, not the bond list) need a per-bond
settings store and are deliberately not started.

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

`qtgl.py` renders straight to the default framebuffer: there is **no
framebuffer-object scaffolding, no depth texture, no full-screen-quad pass and no
second shader program**. Silhouettes, multishadow occlusion and depth cue all
need that scaffolding, so it is the real first task and it is shared:

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
