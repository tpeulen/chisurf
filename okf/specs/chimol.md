---
type: Specification
title: ChiMOL — Target
description: A PyMOL clone that is command-compatible with PyMOL and better than it, built by reading both the PyMOL and ChimeraX sources.
resource: chisurf/plugins/chimol/
tags: [target, chimol, viewer, structure, pymol, chimerax]
timestamp: '2026-07-26T00:00:00Z'
---

> The target for the molecular viewer. Measured current state and findings:
> [pymol-parity](/plugins/pymol-parity.md). Current shape:
> [chimol subsystem](/subsystems/index.md).

## Purpose

ChiMOL **replaces PyMOL** for this group's work. Not resembles it, not covers the
common cases — replaces it, so that a person who knows PyMOL can stop opening
PyMOL. That means two commitments that pull in different directions, and both
have to hold:

1. **Command-compatible with PyMOL.** A PyMOL script runs. PyMOL muscle memory
   works. The selection grammar, the command names, the argument order, the
   defaults and the *semantics* are PyMOL's.
2. **Better than PyMOL.** Where ChimeraX or a fresh implementation does something
   better — rendering above all — ChiMOL takes the better one, without breaking
   the first commitment.

The two sources are read, not guessed at:

* **PyMOL** (`junk/pymol-open-source`) is the authority on **behaviour**. What a
  command does, what its defaults are, which table it consults. When ChiMOL and
  PyMOL disagree about what `orient` means, PyMOL is right by definition.
* **ChimeraX** (`junk/ChimeraX`) is a reference for **how to do it well**:
  rendering, geometry, session design, command-argument typing, the UI, and the
  bundle system. It is not the compatibility authority and its command *language*
  is explicitly not a target — ChiMOL's commands stay PyMOL's.

**One carve-out: voxel maps.** For volumetric data, Chimera/ChimeraX is the
authority on *behaviour* as well, in the way PyMOL is everywhere else. PyMOL has
no heritage here worth preserving — `isomesh` and `volume` are thin beside what
this work needs — and volumes are most of what this group actually looks at. So
the data model, the defaults, the terminology and the interface follow Chimera,
and where the two disagree about what a map should do, Chimera is right by
definition. PyMOL's *command names* are still used where it has them, since a
script that says `isomesh` should keep working.

Concretely, this is already what the opening contour does: a rank enclosing the
densest one per cent, a binary map at 0.5 and a signed map mirrored to `[-v, v]`
are all Chimera's `initial_surface_levels`, not something derived here. Deriving
it here was tried first and was worse — see the log for 2026-07-27.

**A second carve-out: integrative models.** PyMOL has no notion of a bead that
stands for a range of residues, so there is nothing to be compatible *with*. The
rule ChiMOL follows instead is the one the field's own tools follow: a bead model
is drawn as **beads, each at its own radius**, and never as a cartoon or a trace.
A bead has no backbone, so a ribbon splined through beads depicts a chain path
that was never determined — it is a wrong picture before it is a slow one. Every
reader applies the rule, not just the one that happens to know what it loaded:
recognising the model belongs in the viewer, beside the data, rather than in each
file format's loader.

The size at which the depiction changes is a rendering decision, not a modelling
one. Past a budget the beads are drawn as **sphere impostors** — a point shaded
as a sphere by the fragment shader — which is an exact sphere where a mesh is a
polyhedron, at one vertex instead of a hundred and sixty. Nothing is dropped and
nothing is subsampled: a model is not allowed to be quietly shown as a fraction
of itself.

**One route from a file into the viewer.** "Every reader applies the rule" is
not achieved by teaching each reader the rule; it is achieved by giving them
nowhere else to go. Readers produce one payload and the viewer has one method
that consumes it. A format with its own route does not merely risk drifting from
the common one — it *cannot receive* anything the common one learns, and the
divergence is silent, because a second path that draws something plausible
raises nothing. RMF had such a route and so had none of the bead rule at all:
one global radius, decimated to a fraction of its particles, hierarchy check
boxes that moved nothing.

**A model may state more than one depiction of itself.** Coarse-graining is a
modelling choice the file records, not a rendering budget, so the choice between
resolutions belongs to the person reading the model. Which depiction is drawn
and which parts are switched off are *different questions*, kept as separate
masks and composed only at draw time: sharing one mask means choosing a
resolution silently un-hides what was hidden. A file opens on the representation
in its own hierarchy — alternatives are loaded and not drawn — so reading a file
never changes what it has always looked like.

## Principles

### Read the source before implementing

Every value inferred from observation has been wrong here, and every value read
from source has been right. This is not a style preference — it is the single
highest-yield rule this effort has produced. Two cases worth remembering:

* the atom-sort priority was derived from data, disagreed with two real
  structures, and was diagnosed as "the files are non-canonical". Reading
  `AtomInfoAssignParameters` showed the *rule* was wrong;
* hydrogen counts were going to be derived from free valences. Measured against a
  hydrogenated protein, that is wrong for **41.6%** of atoms.

### Carry data, verify it mathematically

Where a table is needed and no library may be added, transcribe PyMOL's with a
checked-in generator, then verify the transcription by its own mathematical
properties — closure, determinant, identity, multiplicity. **And assert its
size**: a truncated extraction passes every property check, because whatever
survives is self-consistent.

### No external library where a source read will do

Adding a dependency for space groups, chemistry or geometry is not the answer
when the data is in a source tree that is already checked out. A carried,
verified table keeps ChiMOL dependency-light and keeps it *agreeing with PyMOL*
rather than agreeing with a third party.

### One table, one seam

Every vocabulary duplicated between a parser and an evaluator has drifted here,
and the drift is silent — the feature keeps answering, with the stale answer.
Found in the keyword list, `alter`'s property map, five atom dtypes, the
representation mask-vs-flag pair, three copies of the colouring, and the camera
commands' idea of what a selection is. When two pieces of code need the same
knowledge, they read it from one place.

### A gap that is shown beats a gap that is hidden

Disabled menu entries explain themselves. Unknown settings are reported, not
accepted. A space group with no operators is **named** and the command declines,
because a symmetry mate built from a guess looks plausible and would be believed.
An approximate hydrogen is worse than a missing one, because it looks like data.

## What "better than PyMOL" means

Concretely, and in priority order:

1. **Rendering.** The view is the product, and this is where ChimeraX is ahead of
   PyMOL. Its model, read from `src/bundles/graphics/src/opengl.py`,
   `fragmentShader.txt` and `std_commands/src/lighting.py`, is:

   | Piece | What it is |
   | --- | --- |
   | key / fill / ambient | three intensities, not one hard-coded direction |
   | `shadows` | one directional shadow map |
   | `multishadow` | **N shadow maps over a sphere of directions** — real ambient occlusion, not a per-vertex estimate |
   | `silhouette` | edge detection on the depth buffer (`depth_jump`) |
   | `depth_cue` | distance fog |

   The presets are the useful part, because they are *named looks* rather than
   sliders: `simple`, `full` (shadows + multishadow), `soft` (multishadow only,
   ambient 1.5, no key light), `gentle` (cheaper multishadow), `flat`
   (silhouettes, no shading). `soft` and `gentle` are what make a ChimeraX figure
   look like a ChimeraX figure.

   ChiMOL's order of work, cheapest visual win first: **silhouettes**, then a
   `lighting` command with ChimeraX's preset names, then **multishadow occlusion**
   to replace the current per-vertex estimate, then depth cue. PyMOL has no
   equivalent of any of these outside its ray tracer, so this is the axis on which
   "better than PyMOL" is actually won.
2. **Trajectories that play.** ChiMOL is the viewer for chisurf's modelling
   output, so a structure that *moves* is the normal case here rather than the
   exception, and a cartoon is what people want to watch it in. The standard is
   that stepping frames keeps up with the eye.

   Two rules follow, and both are about where work is allowed to happen. First,
   **anything that does not depend on the frame is not allowed to be recomputed
   per frame** — which atom is a residue's backbone nitrogen, how a ribbon
   segment's triangles are wired together, and so on. These caches are keyed to
   topology, so they must be discarded by anything that renumbers atoms rather
   than being left to rot. Second, **quality may be traded while the view is
   moving, never while it is still**: a scrub can draw fewer triangles and skip
   baked shading, provided the ribbon does not move somewhere else and provided
   full quality returns the moment it settles. That trade is made by measuring
   how fast frames arrive, never by a mode a caller sets — a mode can be left on,
   and would then quietly hand a coarse picture to a headless render.

   A per-vector `np.cross` costs about ten times what the component form does,
   so per-residue Python loops over three floats are the usual reason this is
   slow. Vectorise where the recurrence allows; where it genuinely does not,
   keep the loop but take NumPy out of it.
3. **Honesty about limits.** PyMOL will happily add hydrogens to a ligand whose
   bond orders it does not know. ChiMOL says so instead.
4. **A session you can still read in ten years.** Not a pickle of internal
   structures: a documented container that cannot execute code when opened.
5. **Verifiable behaviour.** Every carried table and transcribed algorithm has a
   test that would fail if it were wrong, not merely one that runs it.

## What to take from ChimeraX beyond rendering

Surveyed, not yet adopted. Recorded here so the ideas are not rediscovered.

**Typed command arguments.** `core/src/commands/cli.py` gives each argument an
`Annotation` subclass that knows how to parse itself and say what went wrong —
`BoolArg`, `OnOffArg`, `IntArg`, `FloatArg`, `FloatOrDeltaArg`, `StringArg`,
`AttrNameArg`, `OpenFileNameArg` and a couple of dozen more. ChiMOL's command
layer takes everything as a string and does ad-hoc `int()`/`float()` conversion
with a hand-written message at each site — which is why "window must be at least
size 2" and "order must be a whole number" are separately worded. The annotations
are the fix, and they are compatible with keeping PyMOL's *syntax*: the grammar
stays PyMOL's, only the parsing and the diagnostics improve.

**The bundle system.** 193 bundles, each a `bundle_info.xml` declaring its
dependencies, categories, and — the interesting part — **Providers registered
against named Managers**: a bundle states "I provide *define attribute* for the
*open command* manager" rather than importing something and calling a
registration function. Capabilities are declared, discovered and lazily loaded,
so nothing has to import a bundle to learn what it offers. ChiSurf's
`manifest.json` plugins are the analogue and already declare RPC methods; the
providers/managers idea generalises that to every extension point. This is a
**ChiSurf-wide** question, not a ChiMOL one — see [plugins](plugins.md).

**The UI.** Noted as worth reading and *not yet read* — the panel/tool layout and
the log/command-line integration are the parts to look at first. No conclusions
drawn here yet, deliberately.

## Compatibility contract

* **Command names, argument order and defaults are PyMOL's.** Where PyMOL's
  spelling is odd — `ends` as a four-way integer, `get_bonds` returning positions
  within the selection rather than atom indices — ChiMOL matches the oddity and
  documents it.
* **Where a format cannot be shared, say so at the point of writing.** ChiMOL
  writes its own session format; saving to `.pse` states plainly that PyMOL
  cannot read the result, rather than letting it be discovered later.
* **Extensions are additive.** New arguments and new commands are allowed;
  changing what an existing PyMOL command does is not.

## Definition of done

ChiMOL replaces PyMOL when a user of this group can do a day's structural work
without opening PyMOL, and the picture they produce is better than the one PyMOL
would have given them. Progress against that is tracked in
[pymol-parity](/plugins/pymol-parity.md), which holds the measured gap, the tier
list and the findings — this concept holds only the target.

## Testing

Beyond the [testing workflow](/workflows/testing.md), two rules this effort has
had to learn the hard way:

* **"It ran without error" is not "it works".** A 120-entry object-menu sweep
  passed while `orient` was a stub, `zoom` did nothing on a ligand, and three
  representations drew no geometry at all. Assert the observable outcome.
* **Offscreen Qt does not exercise GL.** A green offscreen suite says nothing
  about the picture. Render with a real window and *look at it*.
