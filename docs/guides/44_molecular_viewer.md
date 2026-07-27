# The molecular viewer (ChiMOL)

:::{admonition} Theory
:class: seealso
The two molecular surfaces, the solvent probe, and how surface area is sampled
are covered in the concept page {ref}`concept-molecular-surfaces`. For dye
positions on a structure see {ref}`concept-accessible-volume`.
:::

## What it does

ChiMOL is ChiSurf's built-in molecular viewer. It loads structures, draws them,
selects parts of them, measures them, and writes them back out. Its command
language, selection grammar and object menus follow **PyMOL**, so a PyMOL script
and PyMOL muscle memory largely carry over.

Use it when a structural question sits inside an analysis session — checking
whether a labelling site is exposed, isolating a ligand, colouring a chain by a
per-residue quantity you have just computed — without leaving ChiSurf for a
separate program.

:::{admonition} Not a PyMOL replacement yet
:class: warning
The command surface is a substantial subset, not the whole of PyMOL. Notably the
ray tracer draws **spheres only**: it cannot yet trace a cartoon, and says so
rather than producing a misleading picture. The current coverage and the known
gaps are tracked in the OKF bundle under `okf/plugins/pymol-parity.md`.
:::

## Loading and looking

Open a structure with **File ▸ Open**, or from the command line inside the
viewer:

```text
load 148l.pdb
fetch 1rtd                  # from the PDB, by accession code
```

Objects appear in the **Objects** panel, one row each. Every row carries the same
five menus PyMOL uses, and the grey `all` row applies them to everything at once:

```{figure} figures/chimol_objects_panel.png
:name: fig-chimol-objects
:width: 680px

The Objects panel, here with the ligand and its peptidoglycan split off into
objects of their own. Each molecule gets a row with PyMOL's five menus —
**A**ction, **S**how, **H**ide, **L**abel and **C**olour — and the grey `all`
row applies a choice to every object at once.
```

### Playing a trajectory

```text
mplay                # play, as PyMOL does
mplay 5              # ...advancing five frames per step
mplay 5, 60          # ...and aiming for 60 steps a second
minterpolate 4       # draw four positions between each pair of frames
mpause               # stop where it is
mstop                # stop and rewind
```

`mplay`'s two arguments are additions; with none it behaves exactly as PyMOL's
does. A **step** above one is how a long trajectory is watched end to end
without waiting for every frame.

**`minterpolate`** fills the gaps in. Each atom is straight-lined between the
two stored frames the playhead lies between, so a coarse step still moves
smoothly instead of jumping, and a trajectory whose frames are far apart looks
like motion rather than a slideshow. It is worth having even at step 1 for that
reason. `minterpolate 1` turns it off; with no argument it reports the setting.

The interpolation is linear, which real motion between two frames is not — but
over a single frame's worth of it the error is far smaller than the jump the eye
sees without it, and nothing is stored or recomputed to get it.

**Playback never blocks the window.** The next frame is asked for only once the
last one is on screen, so the application keeps answering the mouse, the menus
and a resize while a trajectory runs, and the rate simply drops to whatever the
machine sustains rather than the window going dead.

### How a trajectory redraws

Stepping through frames rebuilds the ribbon each time, and a cartoon is the most
expensive thing the viewer draws. Two things keep that interactive.

**A scrub draws a draft.** While frames arrive back to back, the cartoon is
tessellated more coarsely — sampled less finely along the chain and around its
cross-section — and the ambient occlusion and cast shadows are not baked. As
soon as the frame holds still for about a fifth of a second, it is redrawn in
full. The draft is the *same ribbon* with fewer triangles, so it does not shift
position and then settle somewhere else; what changes is the triangle count and
the shading.

This is decided by **how fast frames are arriving**, not by a playback mode. A
single frame change — one click of the frame spinner, a headless render, a
script that sets one frame and grabs an image — is never drafted. There is no
setting that can be left on and quietly give you a coarse picture.

**Topology is not recomputed.** Which atom is a given residue's backbone
nitrogen does not change when the molecule moves, so it is worked out once and
reused across frames; likewise the triangle connectivity of each ribbon segment,
which depends only on how finely that segment is tessellated. Both are discarded
the moment they could go stale — `sort` and `remove` renumber the atoms, so the
backbone lookup is dropped and rebuilt.

Together with drawing the mesh indexed rather than expanding it into a flat
triangle list, a cartoon frame change on a 5235-atom, 570-residue trajectory went
from about **240 ms to under 10 ms** — 4 frames a second to over 100. Playing that
trajectory in a real window runs at ~30 fps while the interface answers the mouse
on its normal 20 ms beat.

Where the arithmetic is genuinely sequential and cannot be expressed as array
operations — carrying the ribbon's up-vector along the chain, and placing the
vertices of each cross-section — it is compiled with numba where numba is
installed, and falls back to the NumPy form where it is not. Both produce the
same ribbon; a test compares them.

If you want the full-quality ribbon while scrubbing, the draft settings are
tessellation values in the `cartoon` display config; raising them trades frame
rate back for triangles.

### Trajectories and holding part of a structure still

A window average over the coordinate states suppresses high-frequency vibration,
so a movie shows the motion rather than the noise:

```text
smooth                       # 1 pass, 5-state window
smooth all, 2, 9             # 2 passes, 9-state window
smooth all, 1, 5, 1, 0, 3    # ...wrapping the trajectory (ends=3)
```

`ends` is a four-way choice, not a flag: `0` leaves one state at each end alone,
`1` smooths right to the ends, `2` leaves a whole half-window, `3` treats the
trajectory as cyclic. A `cutoff` keeps an atom that crosses a periodic boundary
from being averaged with its own image.

To move part of a structure and leave the rest:

```text
protect resi 1-40
translate [10, 0, 0]         # only residues 41+ move
deprotect all
```

`protect` shields atoms from `translate` and `rotate`, and the command reports how
many it held so a silent no-op is not mistaken for a move.

### Crystal symmetry

To tell a lattice contact from a biological interface, build the neighbouring
copies in the crystal:

```text
get_symmetry                 # the cell, the space group, where the operators came from
symexp mate, all, 5.0        # one object per mate within 5 A
set_symmetry all, 78.8, 150.7, 280.9, 90, 90, 90, P 21 21 21
```

Each mate becomes its own object named after the operator and lattice translation
that made it, so a contact can be traced back to its symmetry element. The
original stays the active object — `symexp` adds context, it does not change what
you are working on.

:::{note}
The cell comes from the file's `CRYST1` record. The operators come from the file
if it carries them, otherwise from **PyMOL's own space-group table** — all 547
names it ships, up to 192 operators each — so a mate here is the same mate PyMOL
would build. **When neither has them, the space group is named and the command
declines** rather than guessing: a mate built from wrong operators looks entirely
plausible and would be believed. Supply them with `set_symmetry` in that case.

The table is carried rather than computed (no crystallography library is a
dependency), so it is checked mathematically rather than by eye: every one of the
547 groups must be closed under composition modulo lattice translations, every
rotation must be an isometry, and each group must have exactly one identity —
7658 operators verified.
:::

### Trying it out: the Demo menu

The **Demo** menu runs a set of short scripts, so the viewer can be exercised
without a lot of clicking:

| Entry | What it shows |
| --- | --- |
| Cartoon and colour | A structure, coloured N to C |
| Selections | The PyMOL selection grammar, in colour |
| Every representation | Including the ones ChiMOL has and PyMOL does not |
| Lighting presets | `simple`, `soft`, `flat`, `default` in turn |
| Publication figure | Flat shading with silhouettes |
| Trajectory + intra_fit | Why fitting makes a movie readable |
| Measuring | Surface area, bonds, hydrogens |

Each is a plain **ChiMOL script** — one command per line — living in
`chimol/demos/` and run exactly as `@file.pml` runs one. So a demo is also
documentation you can read, and a development harness: a demo that stops working
is a command that stopped working.

Run one from the command line instead:

```text
@demos/cartoon.pml
```

**Demo ▸ Edit a demo script…** opens it in a script editor — ChiSurf's code
editor when ChiSurf is present, and a small built-in one when ChiMOL is running
standalone — so a demo is a starting point to modify rather than a fixed recital.
**New script…** opens an empty one.

### Making it look good

The viewer's lighting follows ChimeraX's model — a key light, a fill light and an
ambient term, each with its own intensity — and its **named looks** rather than a
row of sliders:

```text
lighting soft                # all ambient, no key light: the ChimeraX look
lighting flat                # bright and unshaded, with outlines
lighting simple              # key + fill, modest ambient
lighting default             # back to the plain key light
lighting                     # report the current settings
```

Any single parameter can be set on its own, or after a preset to adjust it:

```text
lighting soft, ambient_light_intensity=1.2
lighting depth_jump=0.05     # no preset: just this one parameter
```

The names are ChimeraX's — `key_light_intensity`, `fill_light_intensity`,
`ambient_light_intensity`, `specular_strength`, `shininess`, `rim_strength`,
`rim_power`, `silhouette`, `silhouette_thickness` and `depth_jump`. A name that
is not one of these is reported as an error rather than silently ignored.

Silhouettes are the other half, and PyMOL has no equivalent outside its ray
tracer:

```text
lighting flat                # turns them on
lighting default, silhouette=1
```

They come from a depth-buffer pass, so they outline the molecule against the
background *and* mark where one part passes in front of another — which is what
makes a crowded cartoon readable. On a black background a black outline is
invisible, so pair them with `bg_color white`.

:::{note}
`lighting full` and the shadow parts of the other presets are **not applied
yet** — they need shadow maps, which are not built. The command names what it
skipped rather than quietly giving you a different look. For the same reason
`soft` and `gentle` are currently identical: in ChimeraX they differ only in
shadow-map resolution.
:::

### Tidying and shielding

```text
sort                         # canonical atom order, all objects
sort 148l                    # just one
mask resi 1-40               # stop the mouse selecting these
unmask all
```

`sort` is mainly needed after `alter` has changed the names the order depends on.
It reorders more than you may expect on a freshly loaded file, because PyMOL's
canonical order puts the side chain **before** the carbonyl —
`N, CA, CB, CG, ..., C, O, OXT` — which is not how a PDB file is written.

`mask` is about the mouse and `protect` is about transforms; they are deliberately
separate, so hiding an atom from selection does not also freeze it.

### Adding hydrogens

Crystal structures usually have none:

```text
h_add                        # every residue with a template
h_add polymer                # just the protein
h_fill resi 42               # replace the hydrogens there, after moving something
```

`h_add` leaves already-hydrogenated atoms alone; `h_fill` removes and re-places
them, which is what you want after moving a heavy atom.

Counts come from a **residue template** rather than from counting free valences.
That is not a shortcut avoided for tidiness — measured against a fully
hydrogenated protein, `valence(element) − heavy neighbours` is wrong for **41.6%
of atoms**, because a double bond looks like a free valence when the file carries
no bond orders. It puts a hydrogen on every carbonyl carbon, every carboxyl
oxygen and every aromatic carbon. PyMOL warns about the same thing in `h_add`'s
own help.

Against that protein, the template gets **99.8% of counts right** and places
hydrogens with a median error of **0.10 Å**. The remaining spread is torsional:
hydroxyls, thiols and amide NH₂ groups can rotate freely, and nothing in the
geometry fixes which way they point — PyMOL places them arbitrarily too.

:::{note}
Two things a template cannot settle, both reported rather than assumed:

* **a residue with no template is skipped and named.** Ligands and modified
  residues need bond orders, which PDB files do not carry;
* **histidine's tautomer is not in the coordinates.** ND1-protonated is assumed
  unless the file already has a hydrogen on NE2. On a real protein this was the
  *only* disagreement with the deposited hydrogens, in 5 residues out of 578.
:::

### Saving a session

A figure in progress is not a PDB file plus a note about what was typed. Save the
whole thing:

```text
session_save figure.cms      # objects, colours, camera, groups, scenes, settings
session_load figure.cms      # put it all back
session_info figure.cms      # what is in there, without loading it
save figure.pse              # same thing; the extension routes here
```

Everything the viewer holds comes back — representations, per-atom colours,
manual bonds and their orders, which groups are collapsed, the named scenes, and
the camera down to its clip planes. A reloaded session renders pixel-for-pixel
identically to the one that was saved.

:::{warning}
`.pse` here is **chimol's own session format, not PyMOL's.** PyMOL's `.pse` is a
pickle of its internal C structures; nothing outside PyMOL can read one, and
chimol does not pretend to. Writing to `.pse` is allowed because that is the
extension a PyMOL user types, and chimol says so when it writes one. Handing a
real PyMOL `.pse` to `session_load` reports the format difference rather than a
decoding error.
:::

The file is a plain zip — a `manifest.json` you can read and an `arrays.npz` of
the numeric data — so a session you keep for years is not opaque, and loading one
cannot execute code (arrays are read with `allow_pickle=False`). That is the other
reason not to copy a pickled format.

### Organising the panel

Once a session has more than a handful of objects, the panel is easier to read
with them grouped. A **group** is a container row, not an object:

```text
group ligands, lig nag       # collect two objects under one row
group ligands, close         # collapse it; the molecules stay loaded
group ligands               # with no members, toggles open/closed
ungroup lig                  # take one back out
```

```{figure} figures/chimol_groups_panel.png
:name: fig-chimol-groups
:width: 680px

Two groups in the Objects panel. `ligands` is open, so its members are drawn
indented beneath it; `parts` is collapsed. A group row carries the same five
menus an object row does, and a menu choice made there is applied to every
member — so **H ▸ everything** on `ligands` hides both molecules.
```

Collapsing a group only hides its rows. Nothing is unloaded, and every command
still reaches the members by name.

The full set of actions matches PyMOL's: `add`, `remove`, `open`, `close`,
`toggle`, `auto`, `empty` (release the members), `purge` (delete them),
`excise` (delete them and the group) and `raise`.

Row order is `order`:

```text
order nag lig                # exactly this order
order *, yes                 # sort everything by name
order lig, location=top      # move one to the top
```

A group name may be used wherever an object name is wanted, and it stands for
all of its members — `order ligands, location=top` moves the whole block.

:::{note}
One place a group is *not* yet accepted is inside an atom selection:
`show cartoon, ligands` does not resolve, because a selection is evaluated
against a single object. Use the group's row menus, or name the members.
:::

The camera follows PyMOL's commands and its 18-float view tuple, so a view can
be copied between the two programs:

```text
orient                      # align the principal axes with the screen
zoom chain A                # frame a selection
turn y, 90                  # rotate about a screen axis
get_view                    # the 18 floats, to save or paste elsewhere
```

`origin` deserves a note because nothing appears to happen when you run it:

```text
origin resn NAG             # rotate about the ligand from now on
turn y, 40                  # ...which is when you see the difference
```

The pivot moves while the picture stays put — as in PyMOL, the view compensates.
The next rotation is what reveals it.

## Selecting

Selections use PyMOL's grammar. The vocabulary is generated from PyMOL's own
keyword table, including the abbreviations:

```text
select site, chain A and resi 54          # named selection
count_atoms polymer and not backbone      # sidechains
count_atoms byres (resn NAG around 4)     # whole residues near the ligand
count_atoms name CA within 8 of resn NAG
count_atoms c. A and n. CA                # abbreviations
count_atoms ss H                          # helices
count_atoms pepseq FEML                   # a sequence motif
```

Atom classes are derived from *which atoms a residue contains*, not from a table
of residue names, so modified residues and unusual ligands land in the right
class: `polymer`, `organic`, `inorganic`, `solvent`, `backbone`, `sidechain`,
`guide`, `metals`, `hetatm`.

:::{tip}
Anything ChiMOL cannot evaluate — `donors`, `byring`, `text_type` and similar —
raises an error naming the reason instead of returning an empty selection. An
empty result therefore means *your selection matched nothing*, not *this keyword
is unimplemented*.
:::

## Drawing

```text
hide everything
show cartoon, polymer
show spheres, organic
show sticks, resi 54
color grey80, polymer
color orange, organic
```

`as` replaces rather than adds, exactly as in PyMOL:

```text
as cartoon, polymer         # cartoon only, everything else off
```

## Measuring

`get_area` reports surface area. Which surface depends on `dot_solvent`, and the
two differ by roughly a factor of two, so the command states which it used:

```text
set dot_solvent, on         # solvent-accessible; off gives van der Waals
set dot_density, 3          # 0-4; higher is more accurate and slower
get_area                    # the whole object
get_area resi 54            # one residue, still occluded by everything around it
```

The selection chooses what is *reported*; every atom of the structure still
occludes. That is the point — a buried cysteine has almost no accessible area
even though the residue in isolation has plenty, and that is exactly what decides
whether it can be labelled.

Other queries:

```text
get_chains                  # ['E', 'S']
get_extent resn NAG         # bounding box, in Angstrom
get_title
distance d1, resi 10 and name CA, resi 20 and name CA
rms polymer, other_object and polymer
```

## Bonds

Bonds are inferred from the coordinates, using PyMOL's rule: two atoms are bonded
when their separation, less the mean of their van der Waals radii, is within
`connect_cutoff`. Sulfur is allowed a little more reach and hydrogen a little
less, and two hydrogens are never bonded.

```text
set connect_cutoff, 0.35     # the default; larger is more permissive
count_atoms bonded
count_atoms bound_to resn NAG
count_atoms bymol resn NAG   # the whole bonded molecule
count_atoms resn NAG extend 2
```

:::{note}
Element-aware radii matter more than they sound. A single distance cutoff has to
be wide enough for the longest real bond — a disulfide is 2.05 Å — which makes it
wide enough for a *contact* between two heavier atoms, and for one hydrogen to
"bond" to another across a hydrogen bond. Since `bymol`, `bound_to` and `extend`
all walk the bond graph, a false bond propagates into every one of them.
:::

## Superposing structures

`align` finds its own correspondence between two objects and fits them:

```text
align mobile, reference
super mobile, reference                       # sequence-independent
align mobile, reference, cutoff=2.0, cycles=5
```

Both fit and then re-fit, dropping the pairs that stayed further apart than
`cutoff` — so a flexible loop or a displaced domain does not drag the rest of the
superposition with it. `cutoff` is a distance in Angstrom, and so is the RMSD
reported at the end, over the pairs that survived (`using 158/162 atoms`).

When you already know which atoms should match — because the two are not the same
sequence, or because only a domain or a ligand should drive the fit — state the
correspondence instead. `pair_fit` matches atoms **in order** within each pair:

```text
pair_fit mob and resi 10-25 and name CA, ref and resi 22-37 and name CA
```

Several pairs contribute to one least-squares fit, so a superposition that one
stretch would leave ambiguous can be pinned down by adding another:

```text
pair_fit mob and resi 10-25 and name CA, ref and resi 10-25 and name CA, \
         mob and resi 60-75 and name CA, ref and resi 60-75 and name CA
```

The fit moves the whole mobile object, not only the atoms named in it.

:::{note}
`intra_fit` and `intra_rms` fit the *states* of one object to each other. chimol
holds a single coordinate set per object, so they have nothing to work on and are
not implemented.
:::

## Colouring by a computed quantity

`spectrum` ramps any per-atom property across a palette. Combined with `get_area`
it turns accessibility into a picture:

```text
set dot_solvent, on
set dot_density, 3
get_area all, 1, 1          # the third argument writes areas into the b-factor
spectrum b, blue_white_red, all, 0, 25
```

```{figure} figures/chimol_accessibility.png
:name: fig-chimol-accessibility
:width: 560px

T4 lysozyme (PDB 148L) as a space-filling model, coloured by solvent-accessible
surface area from `get_area`: red where the surface is exposed, blue where it is
buried. The explicit `0, 25` range matters — the most exposed atom is an outlier,
and an automatic range leaves the whole surface reading blue.
```

The same machinery colours by anything `iterate` can see, so a per-residue
quantity from an analysis — a fitted lifetime, a FRET efficiency, a fluctuation
amplitude — reaches the structure the same way: write it into the b-factor with
`alter`, then `spectrum b`.

## Showing a quantity as thickness

A **putty** cartoon is a tube whose radius carries the same number, which reads
more directly than colour for a single quantity and combines with colour for two:

```text
alter polymer, b = 0.0             # start from something known
get_area all, 1, 1                 # ...or fill b with accessibility
cartoon putty
show cartoon, polymer
```

The mapping follows PyMOL's settings. The default transform is a z-score, so it is
unit-free and works whatever the property is:

```text
set cartoon_putty_radius, 0.4      # base radius, before the per-residue scale
set cartoon_putty_scale_min, 0.6   # clamps, applied after the power
set cartoon_putty_scale_max, 4.0
set cartoon_putty_scale_power, 1.5 # exaggerates the spread
set cartoon_putty_transform, normalized_nonlinear
```

Other transforms measure against the data's own range (`relative_*`), against the
`cartoon_putty_range` setting (`scaled_*`), or take the value as a radius directly
(`absolute_*`) — useful when two structures must share a thickness scale, which
the default z-score deliberately does not do.

:::{tip}
The factors are smoothed along the chain, so one outlying residue produces a bulge
rather than a bead. Set `cartoon_putty_range` larger to compress the spread if a
single outlier still dominates.
:::

## Getting data in and out

`iterate` runs a Python statement per atom and accumulates into a persistent
`stored` namespace; `alter` writes properties back:

```text
iterate name CA, stored.setdefault('b', []).append(b)
alter chain E, b = 0.0
alter_state 1, resn NAG, x = x + 10        # coordinates live in alter_state
```

`alter` changes **properties**; `alter_state` changes **coordinates**. That split
is PyMOL's, and it is not cosmetic — moving atoms invalidates the geometry
derived from them, and changing a b-factor does not.

Split a selection into its own object, and write it out:

```text
create ligand, organic       # copy
extract ligand, organic      # move -- the source loses those atoms
save ligand.pdb, ligand
save whole.cif               # mmCIF, for large residue numbers
```

Files carry the coordinates **as the viewer holds them**, including any transform
applied in the session. Re-exporting the input file instead would silently
discard the work.

`undo` and `redo` cover coordinate changes only, per object, sixteen deep — the
same narrow scope as PyMOL's. They do not undo a colour, a representation or a
deletion.

## Images

```text
png figure.png, 1200, 900    # the viewport as displayed
ray render.png, 1200, 900    # ray-traced: spheres only, for now
```

If the ray tracer is asked to render a cartoon it says so and suggests
`show spheres`, rather than emitting a picture that quietly omits the molecule.

## Headless and scripted use

The viewer is a Qt widget, but the parts that compute do not need a window. The
surface-area calculation is a plain function:

```python
import numpy as np
from chisurf.plugins.chimol.chimol.analysis.surface_area import atom_surface_areas
from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
import chisurf.core.structure as cs_struct

atoms = _read_full_model(cs_struct.Structure, "148l.pdb").atoms
is_cys = np.char.strip(atoms["res_name"].astype(str)) == "CYS"

areas = atom_surface_areas(
    np.asarray(atoms["xyz"], dtype=float),
    np.asarray(atoms["radius"], dtype=float),
    dot_solvent=True,          # accessible surface
    solvent_radius=1.4,
    dot_density=3,
    mask=is_cys,               # report these; everything still occludes
)
print(f"cysteine SASA: {areas.sum():.1f} A^2")
```

To drive the command language without a GUI session, build a viewer and hand it
to `Cmd`:

```python
from qtpy import QtWidgets
from chisurf.plugins.chimol.chimol.cmd.command import Cmd
from chisurf.plugins.chimol.chimol.renderer.view import MolView

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
view = MolView()
view.add_structure(_read_full_model(cs_struct.Structure, "148l.pdb"), name="148l")


class Host:
    viewer = view

    def _refresh_objects_from_viewer(self):
        pass

    def windowTitle(self):
        return "chimol"


cmd = Cmd(Host())
cmd.set_message_callback(print)
cmd.set_error_callback(print)
cmd.do("set dot_solvent, on")
cmd.do("get_area polymer")
```

Run it under an offscreen Qt platform (`QT_QPA_PLATFORM=offscreen`). The ray
tracer needs no GPU and no display, which is how the figure above was made; the
OpenGL viewport does need a display, so `png` will not work headlessly while
`ray` will.

## Where things stand

| Area | State |
| --- | --- |
| Selection grammar | PyMOL's keyword table, 85 keywords with abbreviations |
| Camera, `get_view`/`set_view` | Matches PyMOL's 18-float tuple exactly |
| Object menus (A/S/H/L/C) | 1:1 with PyMOL's |
| `get_area` | Follows `dot_solvent` / `dot_density` / `solvent_radius` |
| Ray tracing | Spheres only; no cartoon |
| Undo | Coordinates only, per object, 16 deep (PyMOL's scope) |
| Settings | 47 registered of PyMOL's 769 |

`okf/plugins/pymol-parity.md` tracks the rest.
