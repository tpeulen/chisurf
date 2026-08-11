---
type: Guide
title: The molecular viewer (ChiMOL)
description: Loading structures into ChiMOL, ChiSurf's built-in molecular viewer, and using selections, representations and rendering to inspect and export them.
tags: [guides, molecular, viewer]
---

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
The command surface is a substantial subset, not the whole of PyMOL. The ray
tracer draws every representation the viewport does — cartoon, sticks, spheres,
surface, wireframe — and sees through a translucent one, but not **labels**,
which are rasterised glyphs; it names what it left out rather than letting you
hunt for it in the picture. The current
coverage and the known gaps are tracked in the OKF bundle under
`okf/plugins/pymol-parity.md`.
:::

## The window

The molecule owns the window, the way it does in PyMOL. Three things sit on top
of the 3-D view rather than beside it — the **sequence strip** across the top,
the **object list** at the top right, and the **mouse-mode block** at the bottom
right — because they are reference material you glance at without looking away
from what you are doing.

All three are drawn by the GPU as part of the frame, not painted over it, so
they update on the frame they change and cost the same on a 4K display as on a
laptop screen. There is no separate refresh to wait for: recolour a selection
and the sequence strip is already showing it.

Under the view is the **command console**: an always-visible prompt with the
output of everything you have run above it. It is the fastest way to drive the
viewer, and nothing has to be opened first.

The movie transport and its scrubber appear only when there is something to
play — a trajectory, or a timeline you set with `mset`. The **Hierarchy**,
**RMF** and **Map** panels start closed and open themselves when a file gives
them something to show; **View ▸ Panel Tabs** opens any of them by hand, and
right-clicking a tab bar brings back one you have closed.

## Loading and looking

Open a structure with **File ▸ Open**, or from the command line inside the
viewer:

```text
load 148l.pdb
fetch 1rtd                  # from the PDB, by accession code
fetch EMD-3061              # ...or a density map from EMDB
fetch PDBDEV_00000012       # ...or an integrative model from PDB-IHM
```

`fetch` recognises the repository from the identifier — a four-character code is
a PDB entry, `EMD-…` is an EMDB map, `PDBDEV_…` is an integrative model — so the
canonical identifier is all you need. Naming a repository explicitly
(`fetch 8zzz, pdb-ihm`) still works, and is how you reach an entry whose id
looks like another repository's. An EMDB map arrives as a **map object** with a
contour on it, not as a structure; see [voxel maps](#voxel-maps).

| Repository | Looks like | Gives you |
| --- | --- | --- |
| `pdb` | `148l`, `pdb_00001abc` | a structure |
| `emdb` | `EMD-3061`, `emd_1234` | a density map |
| `pdb-ihm` | `PDBDEV_00000012`, `ihm-12` | an integrative model |

Structure files load as PDB, mmCIF or **BinaryCIF** (`.bcif`) — the last is the
same content as an mmCIF in a compact binary encoding, and reads to exactly the
same model.

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

### Integrative (bead) models

An entry from PDB-IHM is not a list of atoms. It is a list of **beads**, each
standing for a *range* of residues and carrying its own radius — tens of
ångström for a domain, a couple for a well-determined loop. The sizes are the
shape of the thing, so the viewer keeps them and draws each bead at its own.

Such an object opens in the **sphere** representation, and there is nothing to
switch it to: a bead has no backbone, so a cartoon through one traces a ribbon
that does not exist, and no interbead distance is a bond. Colouring, selecting,
measuring and superposing work as they do anywhere else — one bead behaves as
one residue, so `spectrum count` runs over beads and `resi 40-60` selects them.

```text
fetch PDBDEV_00000012            # the nuclear pore, all eight spokes
spectrum molecule, lightblue_palecyan_palegreen_paleyellow_wheat_salmon_lightpink
```

**Colour by what the model is made of.** `spectrum molecule` takes its values
from the entry's own hierarchy, so all sixteen copies of a nucleoporin get one
colour and the eight-fold symmetry appears as a repeating pattern. `spectrum
chain` gives every copy its own colour instead, and `spectrum count` — ramping
over 234,184 beads in file order — says nothing about the structure at all.
`molecule`, `chain_node` and `state` are the hierarchy levels; everything else
is a per-atom property as usual.

**Beads are shaded by how enclosed they are.** A quarter of a million spheres
drawn flat is unreadable: nothing casts a shadow, and at this scale perspective
separates nothing, so the picture carries no cue about what is in front.
Ambient occlusion darkens a bead that has neighbours in every direction and
leaves an exposed one bright, which is what makes the rings and the channel
read as solid. It is baked into the colours once, so it costs nothing per frame
and cannot shimmer as the camera moves; `balls.ao_strength` in the display
configuration controls it, and `0` turns it off.

A pale ramp is worth choosing deliberately here — occlusion works by darkening,
and a fully saturated hue has little room left to darken.

```{figure} figures/chimol_npc_molecule.png
:name: fig-chimol-npc
:width: 620px

The eight-spoke nuclear pore, all 234,184 beads, exactly as the demo draws it.
Colour comes from the entry's hierarchy — one per nucleoporin, shared by all
sixteen copies — so the eight-fold symmetry shows as a repeating pattern rather
than as a mosaic. The depth is ambient occlusion: beads buried inside the
assembly darken, exposed ones stay bright.
```

An entry that deposits both resolved atoms and beads — the common case — gets
both depictions at once: the beads are spheres, the resolved residues keep their
cartoon and their bonds, and secondary structure is assigned over the atoms
alone.

**The Hierarchy panel shows how the model is organised.** An integrative entry
describes its own composition — which molecule each chain is a copy of — and the
viewer reads it into the same tree an RMF from IMP produces:

```text
8ZZC — Integrative structure … of eight spokes of a nuclear pore complex
├── Nup84 [MOLECULE]
│   ├── A (Nup84) [CHAIN]
│   ├── H (Nup84@11) [CHAIN]
│   └── … 16 copies
├── Nup85 [MOLECULE]
└── … 31 nucleoporins in 544 copies
```

That is the eight-fold symmetry of the pore stated as composition rather than
inferred from the picture, and it is what a flat cloud of 234,184 beads cannot
tell you.

Each node knows which particles belong to it — the count is shown after the name
— so **un-checking a node hides them**. Switch off `Nup84` and its 10,560 beads
leave the picture; switch one copy back on and the molecule shows as partially
checked. This is visibility, not representation: nothing else about how the
structure is drawn changes, and re-checking brings it back exactly as it was.

Past **20,000 beads** the viewer switches from a mesh sphere per bead to a
*sphere impostor*: one point, shaded as a sphere by the graphics card. In outline
and in shading it is an exact sphere where a mesh is a polyhedron, and it is what
makes a model of this size open at all. One limitation: an impostor is drawn at
the depth of its centre, so where beads overlap each other or other geometry the
nearer centre wins the whole disc rather than the two surfaces intersecting.
Below the threshold, where the beads are meshes, they intersect properly. The
threshold is `balls.impostor_min_atoms` in the display configuration.

### RMF models from IMP

An `.rmf` / `.rmf3` written by IMP is the same kind of thing as an integrative
mmCIF — beads, organised into a hierarchy — with a trajectory as well, and it is
read into exactly the same shape. Everything above applies to it unchanged:
per-bead radii, the sphere representation, impostors past the threshold, the
hierarchy panel and its check boxes, `spectrum`, `resi`, `distance` and `zoom`.

```text
load model.rmf3            # or File > Open; `fetch` does not serve RMF
```

Restraints, provenance and the per-frame score series come with it, and the
trajectory drives the frame slider. Measurements follow playback: a `distance`
is re-read from the frame on show, not frozen at the first one.

#### A simulation is more than motion

An MD trajectory moves atoms and changes nothing else, and for a long time every
frame path here assumed that. An **agent simulation** does not: its particles
appear, grow, and change what they are doing. RMF has always stored a **radius**
and a **colour** per frame, so a file can say all three, and ChiMOL now reads
them:

| What the file says | What you see |
| --- | --- |
| radius 0 in this frame | the particle is not drawn — it does not exist yet |
| a radius that grows | it grows, interpolated between stored frames |
| a colour that changes | it changes colour without moving |

Values that do not vary cost nothing: a model that states one radius and one
colour is read into one array, with no time axis at all.

Being un-drawn for lack of a radius is kept apart from being **hidden**, which
is what the hierarchy panel's check boxes do. Switch a chain off, step the movie,
and it stays off.

#### Whether the camera follows the frame

```text
set movie_recenter, off
```

By default the camera re-centres on the frame being shown, which is what keeps a
molecule that wanders across its box in view. For a structure that **grows**,
that is the wrong behaviour: the camera follows the centroid, the centroid of a
thickening film rises with it, and the substratum slides downward while the
surface stays put — so the film appears to sink rather than to grow. Turn it off
and the floor stays where it is.

The setting is global, as `set` is in PyMOL, so a demo that changes it says so
rather than leaving the next one to inherit it. PyMOL has no equivalent — it
never re-centres.

```{figure} figures/chimol_biofilm_late.png
:name: fig-chimol-biofilm
:width: 620px

A simulated biofilm at the end of its run, from **Demo ▸ Biofilm growth**. Each
bead is one cell; the colour is its modelled oxygen state, taken from how deep it
sits below the local top of the film. A cell never moves once it is born, so
every colour change in the movie is a cell being **buried** by the ones that grew
over it. Green is the aerobic surface, amber the transition, red the anoxic
interior.
```

What the model does and — just as importantly — what it leaves out is in
{ref}`concept-biofilm-growth`.

The demo that produces this has no file to fetch: the simulator that ships beside
ChiSurf is run on first use — a few seconds — and the result is cached in the
settings directory, so what you watch is what the model produced on your machine.
Change the configuration (`IMP/swarm/examples/biofilm_growth.yaml`: colony
geometry, growth rates, the depth thresholds that set the colours) and delete the
cached `.rmf` to see the difference.

#### Choosing a resolution

An IMP model is often deposited at more than one **resolution** — the same
molecule as ten beads and as one — with the coarser depictions stored as
*alternatives* to the finer. Where a file does this, the RMF panel grows a
**Resolution** box listing what is available; a file with a single
representation, which is most of them, shows no box at all.

Resolution here is IMP's: **residues per bead**, so a larger number is coarser.

```text
Resolution [ 1  ▾ ]      1 · 10 · all (superimposed)
```

The file opens on the representation that lives in its own hierarchy, so it
looks as it always did, and the alternatives are loaded but not drawn until
asked for. Choosing `all (superimposed)` draws every representation at once,
which is occasionally useful for comparing them and is not a sensible way to
work.

Choosing a resolution is **not** the same as hiding: it changes which depiction
of the model is drawn, and it leaves whatever you switched off in the Hierarchy
panel switched off. Hide `Nup84`, then switch to the coarse depiction, and
`Nup84` is still hidden — in its coarse form too, because it is one molecule
however finely it is drawn.

### Voxel maps

A great deal of what gets looked at here is a density rather than a structure:
an accessible volume showing where a tethered dye can physically be, an
occupancy density from an ensemble, an electron-density or cryo-EM map, a 3-D
microscopy stack. ChiMOL loads these as **map objects** and contours them, so a
model can be looked at inside its data.

```text
load_map density.mrc         # MRC / CCP4 / MAP, gzipped or not
fetch EMD-3061               # ...or straight from EMDB
map_info                     # size, voxel step, origin, value range
isosurface dens, density     # a solid contour at a level from the data
isomesh dens, density, 0.08, skyblue
volume_level density, 0.12   # move the contour
```

```{figure} figures/chimol_map_isomesh.png
:name: fig-chimol-map
:width: 640px

A density contoured as an `isomesh` around the structure it belongs to. The
wireframe leaves the model visible inside, which is the point of that mode; the
same contour as `isosurface` is a solid envelope.
```

**A map lands where the file says it does.** The reader honours the voxel step,
the origin, and the axis order — MRC files may store their axes in any order, and
a map read as though it were `x, y, z` is silently transposed. It also honours
anisotropy: a confocal stack whose z step differs from its xy step is not
squashed into a cube.

### The Map panel

The **Map** tab shows the map's value distribution with each contour as a marker
on it, so a level is chosen by *looking* rather than by typing a number and
re-rendering:

```{figure} figures/chimol_map_panel.png
:name: fig-chimol-map-panel
:width: 620px

The Map panel. Each contour is a marker on the histogram — here a filled surface
(blue) and a wireframe (orange) on the same map. Drag a marker to move that
level, click empty histogram to add one, right-click a marker to remove it.
```

The counts are on a log scale: a density is overwhelmingly background, and on a
linear axis the fraction of a per cent worth contouring is a flat line at zero.
The `Level` box still takes an exact value when one is known, and the style and
colour controls act on the selected marker.

This editor is not specific to maps — it is chisurf's shared `level_histogram`
section, so any tool that has to ask for a threshold over a distribution (a
burst gate, a photon-count cut) gets the same one from its `.view.json`.

**The opening contour is chosen by rank, not by value.** With no level given,
the level enclosing the densest **one per cent** of voxels is used. A rank is
free of both the scale and the shape of the distribution, and none of these maps
share either — an accessible volume runs 0 to 1, a photon-count stack to a few
hundred, a cryo-EM map to whatever the reconstruction produced.

Two kinds of map are treated specially, and both matter here:

| Map | Opens at | Why |
| --- | --- | --- |
| **binary** (a mask — an accessible volume *is* one) | `0.5` | a rank-based level lands *inside* the occupied region and draws a surface within the volume rather than around it |
| **signed both ways** (a difference map) | `[-v, +v]`, two colours | the negative lobe is half of what such a map is for |

`map_info` prints the value range, and a level outside it is refused *with* the
range rather than quietly drawing nothing.

**More than one level at a time.** Repeated `isosurface`/`isomesh` calls add
contours rather than replacing them, each with its own colour, which is how a
dense core inside a diffuse shell is read. `volume_level` replaces them.

:::{note}
For volumetric data ChiMOL follows **Chimera**, not PyMOL — the data model, the
defaults and the terminology — while keeping PyMOL's command names where it has
them. PyMOL's volume support is thin, and densities are most of what gets looked
at here.
:::

**Large maps are strided, not refused.** Anything past a voxel budget is
subsampled for display, so a big map opens and a contour change stays quick;
`map_info` says when that is happening.

**Dragging a level lets the surface follow.** While a marker is being dragged
the map is re-contoured under a reduced budget — coarser, but fast enough to
keep up with the mouse — and the full-quality contour is cut once, on release.
A level change touches only the map's own geometry: the rest of the scene
(cartoon, sticks, surfaces) is not rebuilt, and re-drawing an unchanged level
(a colour or opacity edit, a surface/mesh toggle) reuses the cached contour.

:::{admonition} Direct volume rendering is not implemented yet
:class: warning
`volume` is registered but declines, and says to use `isosurface` or `isomesh`
instead. Ray-cast volume rendering — the mode that suits microscopy and diffuse
probability densities, where no single threshold is meaningful — is planned, as
is a histogram panel for dragging contour levels.
:::

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
| EMDB density map | Fetch a map and contour it |
| NPC (integrative, PDB-IHM) | A model made of beads, not atoms |
| Biofilm growth (simulated) | Cells divide, stack and change state |

Each is a plain **ChiMOL script** — one command per line — living in
`chimol/demos/` and run exactly as `@file.pml` runs one. So a demo is also
documentation you can read, and a development harness: a demo that stops working
is a command that stopped working.

Most name a file. **Biofilm growth** names one that does not exist until it is
computed: the simulation runs on first use and is cached, so the demo shows a
result rather than a picture of one. Where the simulator is not installed the
menu entry says so instead of failing to open a file.

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
is not one of these is reported as an error rather than silently ignored. The
ambient term is capped at its full strength — the mixing formula makes the
diffuse light turn negative beyond it, shading a face turned from the light
*brighter* than one facing it — so `ambient_light_intensity` above 1 renders
the same as 1 (the `soft`/`gentle`/`flat` presets all sit above this and land
on the cap).

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

### Seeing through a surface

```text
show surface
set transparency, 0.5        # PyMOL's sense: 0 is opaque, 1 invisible
set two_sided_lighting, on   # light the inside faces you can now see
```

`transparency` is the **complement** of the alpha the renderer works in, and the
setting carries the conversion so there is one stored number rather than two
that must agree: `set transparency, 0.4` stores an alpha of 0.6, and
`get transparency` answers 0.4.

`ray` sees through it too: a traced image composites front to back, so what is
inside a translucent surface comes out as it does in the viewport. That costs
nothing on an opaque scene — the walk stops at the first solid surface — and
roughly 2.4× on a translucent one.

`two_sided_lighting` only matters once the surface is see-through. A back face
has its normal pointing away from you, so the inside of the shell comes out
unlit black without it — which is why PyMOL's own ligand-site preset turns it on
in the same breath as the transparency, and why `preset ligand_sites` here does
too.

:::{note}
`unset transparency` restores **0.15**, not PyMOL's opaque 0: ChiMOL ships a
slightly translucent surface and `unset` restores the default the program
actually has. Set it to 0 explicitly for PyMOL's look.
:::

### How finely the surface is built

```text
surface_quality 0        # PyMOL's scale, and the default
surface_quality 1        # "good" -- roughly 4x the triangles
surface_quality -2       # coarse and fast, for a first look
set surface_normal, 0.6  # the separation level 0 selects, in Angstrom
```

The level chooses a grid spacing, from `surface_miserable` (2.0 Å) up to
`surface_best` (0.25 Å) and finer; all four separations are settings too, so a
level can be retuned rather than abandoned. Measured on T4 lysozyme, levels
−3 / −1 / 0 / 1 build **2 446 / 13 654 / 25 876 / 105 922** vertices — so the
top levels are genuinely expensive, which is why PyMOL calls its highest ones
"nearly impractical".

:::{warning}
Levels above 1 grow fast and are capped at 320 samples per axis, so on a large
assembly the finest levels stop getting finer. That ceiling exists because the
grid is cubic: halving the spacing is eight times the memory.
:::

### A picture behind the scene, so transparency reads

Transparency is invisible against one flat colour. A surface at `alpha 0.4` over
black is merely a *darker* surface: there is nothing behind it for the eye to
catch, so lowering the alpha reads as dimming rather than as seeing through. Give
the background structure and the same surface reads as glass immediately.

```text
bg_image stars               # a generated deep-sky field
bg_image nebula              # the same field, stronger cloud
bg_image ~/pictures/sky.png  # any image file
bg_image off                 # back to the flat bg_color
bg_image                     # report what is set
```

`stars` and `nebula` are **generated**, not shipped: a few lines of numpy drawn
at the widget's own size, from a fixed seed. That means no image is stretched to
fit, and a screenshot taken twice is the same picture — so a rendering change
shows up as a rendering change, not as a re-rolled sky. They are deliberately
dark and vignetted toward the centre, so the backdrop never competes with the
molecule sitting in front of it.

This pairs with a translucent surface or metaball:

```text
bg_image stars
show metaballs
set metaball.alpha, 0.45
```

### Clipping, and how to get out of it

**Shift+wheel** (or ctrl+wheel) moves the near clipping plane, slicing away
whatever is in front of it. It is the fastest way to look inside a structure —
and the fastest way to make the viewer look broken, because a *cut* closed
surface does not look cut. Everything inside it becomes fully visible and
unblended, so a translucent surface with a cartoon inside suddenly shows a stark
white ribbon with hard edges, which reads as transparency having failed.

If a view has gone strange, this is the first thing to suspect:

```text
clip reset                   # planes back where framing put them
zoom                         # re-frames, and therefore also unclips
clip near, -5                # or move it yourself
clip slab, 20
```

The status bar reports the near plane whenever the wheel moves it, and says
`Clipping: off` once it is back — so the gesture is never silent.

### When a new version changes a default

Your settings live in `~/.chisurf/chimol_display.json`, and they are yours —
nothing rewrites them behind your back. But a default that improves between
versions has to be able to reach you, or you keep a value nobody intended and
the viewer quietly stops matching what the documentation describes.

So ChiMOL compares your file with the one it ships with at start-up, and asks:

> *3 display settings differ from the ones this version ships with.*
> **Use the new defaults** / **Keep mine** — with every difference listed as
> `metaball.sigma_factor: 3.0 → 4.0`, so you can see which are yours.

Choosing **Keep mine** changes nothing. Ticking **Don't ask again** stops the
question for good — independently of which button you press, so you can keep
your settings *and* stop being asked.

To turn it back on, open **Cfg** and tick *"Tell me when this version ships
different display defaults"* at the bottom, then **Save**. (The tick box edits
the document in the editor, like everything else there, so nothing is written
until you save.)

:::{note}
Settings that merely fell behind a rename or a changed default are brought
forward silently, without asking — those are values you never chose. The prompt
is for the rest: differences that no migration can identify, which are either
your own choices or a value stranded by a default that moved twice inside one
version.
:::

### Tuning a metaball

A metaball is a density field around the atoms, contoured at a threshold. Two
settings decide what it looks like, and they pull against each other:

```text
set metaball.sigma_factor, 4.0   # how far each atom's field reaches
set metaball.iso_value, 0.10     # where the surface is drawn in that field
set metaball.alpha, 0.55         # translucency
```

`sigma_factor` is the smoothing. Raise it and neighbours fuse into rounder
lobes; raise it too far and the surface stops following the molecule at all —
at 6.5 it enclosed roughly **6.5×** the atoms' own volume, the fold vanished
into a featureless egg, and no `iso_value` could pull it back, because past a
certain width even the highest threshold still encloses everything. Lower it too
far and the opposite happens: the surface wraps each helix on its own and the
envelope tears open into the background between them, which zoomed in reads as a
shredded surface rather than as detail.

The shipped 4.0 sits between those, chosen on a helical bundle rather than a
compact protein — a globular fold survives a much tighter field than a stalk
does, so tuning on one hides what the other would show.

:::{tip}
Smoothing is not free. A wider field costs more per atom *and* enlarges the
padded box; with `max_dim` capped, the grid then coarsens, so a wide sigma loses
detail twice over. The shipped width builds a scrubbing trajectory at ~33 fps
where 6.5 managed ~11.
:::

:::{note}
Use `bg_image` with silhouettes and you get the opposite of the `bg_color white`
advice above: against a dark sky, outlines want to be light. `bg_image off`
restores whatever `bg_color` was last set.
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
all of its members — `order ligands, location=top` moves the whole block. It is
also an ordinary word **inside a selection**, so one command reaches every
member:

```text
show spheres, ligands        # both molecules
color red, ligands           # both molecules
zoom ligands                 # frames all of them, not just the first
count_atoms ligands and elem C
```

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
count_atoms donors or acceptors           # anything that could hydrogen bond
count_atoms byring (resn NAG)             # complete the rings it touches
```

Atom classes are derived from *which atoms a residue contains*, not from a table
of residue names, so modified residues and unusual ligands land in the right
class: `polymer`, `organic`, `inorganic`, `solvent`, `backbone`, `sidechain`,
`guide`, `metals`, `hetatm`.

`donors` and `acceptors` (PyMOL's `don.` and `acc.`) come from the same
chemistry the polar-contact search uses — residue templates where there is one,
bond angles where there is not. `byring` completes every ring an atom belongs
to, and like PyMOL it returns **only** the rings: an atom in none is dropped, so
`byring (name CA)` answers "the prolines".

:::{tip}
Anything ChiMOL cannot evaluate — `masked`, `text_type`, `flag` and similar —
raises an error naming the reason instead of returning an empty selection. An
empty result therefore means *your selection matched nothing*, not *this keyword
is unimplemented*.

A **name** that resolves to nothing is an error for the same reason:
`count_atoms lgi` reports `Invalid selection name "lgi"` rather than `0`, as
PyMOL does. Prefix it with `?` — `count_atoms ?lgi` — where a script means
"undefined is allowed here".
:::

**A selection is not confined to one object.** As in PyMOL, it is evaluated over
every loaded molecule, so `count_atoms chain A` counts chain A wherever it is
and `show cartoon, polymer` reaches all of them. Scope it by naming an object
first — `zoom 148l and resi 54` — or by naming a group.

**Chain identifiers of more than one character work.** A PDB file has a single
column for the chain, but an mmCIF asym id runs `A`…`Z` and then `AA`, `AB`, …,
which is what any large assembly needs: the eight-spoke nuclear pore has 544
chains, 518 of them two characters. `chain AB` selects that chain and nothing
else, and `spectrum chain` gives 544 colours rather than 26.

Writing such a structure back out as **PDB** cannot preserve them — the format
has one column and no more — so `save` truncates the ids to their first
character and warns, naming the chains that become indistinguishable. Save as
mmCIF to keep them.

### Selecting with the mouse

The mouse-mode block at the bottom right is the reference: it lists what every
button does under every modifier, and clicking the mode line at its top cycles
through PyMOL's modes. In the default *3-Button Viewing* mode:

| Gesture | Action | Effect |
| --- | --- | --- |
| click an atom | `+/-` | its residue joins or leaves the selection |
| shift-drag | `+Box` | every residue in the box joins the selection |
| shift-middle-drag | `-Box` | every residue in the box leaves it |
| ctrl-shift-click | `Sele` | the clicked residue becomes the selection |

A drag paints a dashed rectangle while the button is down. Selected residues get
a ring in the 3-D view and a pink block in the sequence strip; clicking empty
space clears the selection. What the mouse builds is the `sele` selection, so
`show sticks, sele` or `color red, sele` continue from it, and the `sele` row of
the object list carries the same five menus pointed at it.

Mask a region — `mask resi 1-40` — to stop the mouse reaching it.

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

### Polar contacts

`distance` also finds contacts in bulk, through PyMOL's `mode` argument:

```text
distance hb, all, all, mode=2          # every hydrogen bond in the structure
distance hb, chain A, chain B, mode=2  # only across the interface
distance hb, all, all, mode=2, label=0 # dashes without the numbers
distance c, all, all, 4.0, mode=3      # any contact within 4 A, bonds excluded
distance com, chain A, chain B, mode=4 # one line, centroid to centroid
```

| `mode` | What it draws |
| --- | --- |
| 0 | every interatomic distance inside `cutoff` |
| 1 | only pairs that are bonded |
| 2 | polar contacts (hydrogen bonds) |
| 3 | like 0, but skipping atoms within `distance_exclusion` bonds |
| 4 | one distance, between the two selections' centroids |
| 5 / 6 / 7 | pi interactions: both kinds / ring-ring only / cation-ring only |
| 9 | halogen bonds |
| 10 | salt bridges |

The **A ▸ find ▸ polar contacts** submenu is the same command, pre-written for
the usual questions (within the selection, side chains only, to solvent, across
to everything else), and `preset technical`, `preset ligands` and
`preset ligand_sites` all draw them as part of the recipe.

What counts as a hydrogen bond is not a single distance. The donor–acceptor
cutoff *slides with the A–D–H angle*, from `h_bond_cutoff_center` head-on
(3.6 Å) down to `h_bond_cutoff_edge` at the widest angle accepted (3.2 Å at
63°), and a hydrogen sitting behind the acceptor's lone pairs is rejected
whatever its distance:

```text
set h_bond_cutoff_center, 3.5    # stricter head-on
set h_bond_max_angle, 45         # stricter on geometry
set h_bond_cutoff_edge, 0        # flatten it to a plain distance test
set h_bond_exclusion, 3          # ignore pairs this many bonds apart
set dash_width, 1.5              # thinner dashes
set dash_length, 0.2             # longer dashes, fewer gaps
```

:::{note}
Most crystal structures have no hydrogens, so the hydrogen is **placed** on the
donor's open valence, aimed at the acceptor. Measured on a fully hydrogenated
protein, asking the same question with and without its hydrogens finds **99.2 %**
of the same contacts, plus about 9 % extra — rotatable hydroxyls and ammonium
groups whose real hydrogen points elsewhere while a placed one is free to aim at
the partner. `h_add` first if you want the file's own answer.

Which atoms donate and accept comes from the same residue template `h_add` uses,
so a backbone carbonyl oxygen accepts and does not donate. Two consequences
worth knowing: a **ligand** or modified residue has no template and falls back to
free-valence counting, which makes its carbonyl oxygens read as donors too (as
they do in PyMOL); and **proline does not donate**, where PyMOL invents an amide
hydrogen for it that the residue does not have.
:::

### Hydrogen-bond networks

A bundle of dashes says which atoms are bonded; it does not say which bonds
belong *together*. `hbond_network` groups them — two bonds are in the same
network when they share an atom — and draws each network in its own colour:

```text
hbond_network polymer, exclude, 2   # the protein's own networks, 2 bonds and up
hbond_network all, bridge, 3        # ...with ordered water joining the halves
hbond_network solvent, only         # the water wires alone
```

| Argument | Meaning |
| --- | --- |
| `selection` | where to look; contacts are found inside it, as `mode=2` does |
| `waters` | `bridge` (water joins a network), `exclude` (protein only), `only` (water-to-water) |
| `min_size` | drop networks smaller than this — every structure has dozens of lone surface contacts |
| `name` | prefix for the objects; `hbnet_1` is the largest network |

Each network becomes its own measurement object, so `disable hbnet_3` hides one
and the console lists what each is: how many bonds and residues it spans, how
much of it is water, and whether it crosses chains — which is what makes an
interface network worth a second look.

The contacts themselves are exactly the ones `distance ..., mode=2` finds, with
the same settings. The grouping is what is added; PyMOL has no notion of a
network, so this is not something a PyMOL script can be compared against.

### Where two chains touch

`interchain_distances` runs a distance search over **every pair of chains** and
collects the lot under one name — PyMOL's `util.interchain_distances`, and what
its **A ▸ find ▸ any contacts ▸ between chains** entries call:

```text
interchain_distances ic, all, 4.0        # any contact within 4 A, across chains
interchain_distances ic, all, -1, 2      # ...polar contacts instead
```

The point is what it leaves out. Asking for contacts in the whole selection at
once buries the interface under every contact *inside* each chain; this asks
only the cross-chain question. A selection that spans one chain says so rather
than drawing an empty measurement.

### Salt bridges, halogen bonds and pi interactions

Three more finders, each with its own criteria rather than a variation on the
polar-contact test, reached the way PyMOL reaches them — a `distance` mode, and
an entry in **A ▸ find**:

```text
distance sb, all, all, mode=10       # salt bridges
distance hal, all, all, mode=9       # halogen bonds
pi_interactions pi, all              # ring stacking and cation-ring, together
distance pp, all, all, mode=6        # ...ring-ring only
distance pc, all, all, mode=7        # ...cation-ring only
```

A **salt bridge** is two non-hydrogen atoms of opposite formal charge within
5 Å. There is no angle term — the accuracy lives entirely in the charges, and a
PDB file does not carry them. They come from residue nomenclature, PyMOL's own
table, and it is deliberately asymmetric: only `OD2` of an aspartate, only `OE2`
of a glutamate, only `NH1` of an arginine (with `NH2` pinned to zero), plus
`NZ`, `OXT` and a nucleotide's `OP2`. Charging both oxygens of a carboxylate
would double-count every bridge. **A plain `HIS` is neutral** — a histidine
counts only under the protonated names `HIP`, `HISP` or `HISH`, because its
protonation state is a decision PyMOL declines to make for you, and so does
this. A charge in the file always wins over the table.

A **halogen bond** is checked both ways round. With the halogen donating
(D–X···A–B) the sigma hole is on the far side of its own bond, so D–X···A has to
be nearly straight (≥ 140°). With the halogen accepting (D–H···X–B) it offers a
lone pair side-on, so the H···X–B angle is bounded on *both* sides (90–170°) —
a straight-through approach there would be the sigma hole, not a lone pair.

**Pi interactions** reduce each planar ring to a centre and a normal. Ring-ring
is face-to-face (centres within 4.4 Å, normals within 30°) or edge-to-face
(within 5.5 Å, normals more than 60° apart), and a pair whose normals both point
*across* the line joining the centres is dropped as coplanar — two rings side by
side in one plane are as close as a stacked pair and are not stacked. Pi-cation
is a cone, not a sphere: within 6.6 Å of the centre **and** 30° of the ring's
axis.

:::{note}
A ring counts when its atoms are planar, and planarity comes from the residue
templates or from the bond angles. Every aromatic side chain and every
nucleobase is found — 18 rings in T4 lysozyme, counting each tryptophan's two —
and so is a **ligand's** ring *when the structure carries its hydrogens*: three
neighbours are enough to measure flatness from.

Without hydrogens a ligand ring is missed, because a two-neighbour carbon
carries no angle that separates sp2 from sp3 and a PDB file has no bond orders
to say. **PyMOL behaves identically here** — its `ObjectMoleculeGetAtomGeometry`
returns "unknown" for two neighbours too, and its chemistry pass has the same
nothing to work from. Load the hydrogenated structure if the ligand's stacking
is the question.
:::

### Clashes

`clashes` is PyMOL's **bump check** — the one its mutagenesis wizard runs on a
rotamer — available on any selection:

```text
clashes resi 54            # this residue against everything
clashes chain A, chain B   # only across the interface
clashes sele               # whatever is picked
```

Every overlapping pair is drawn the way PyMOL's sculpting draws it
(`SculptCGOBump`): not a line from atom to atom, but a short mark at the
**contact point** — the position dividing the pair in proportion to their radii
— extending only a little either side of it, with a *width* set by how deep the
overlap is. A clash is therefore a stub sitting in the gap between two atoms
rather than a line drawn through both of them, which is what keeps a crowded
site readable. The colour is PyMOL's ramp: green until the overlap passes
`sculpt_vdw_vis_mid` (0.1 Å), then to red over the next `sculpt_vdw_vis_max`
(0.3 Å). The console reports the **strain**: the summed overlap, which is the
number the wizard ranks rotamers by. Two rules stop it from crying wolf, both
PyMOL's:

* a hydrogen bond is not a clash. The pair's cutoff drops by
  `sculpt_hb_overlap` (1.0 Å) for the hydrogen and `sculpt_hb_overlap_base`
  (0.35 Å) for the heavy atoms, without which every hydrogen bond in the
  structure reports as an overlap;
* bonded neighbours are excluded — 1-2 and 1-3 outright, and a 1-4 pair
  contributes strain but is never drawn, because a torsion the geometry
  already fixes is not something to put a red line across.

Radii are PyMOL's own (`C` 1.70, `N` 1.55, `O` 1.52), not the force-field radii
the structure reader stores — 0.3 Å per atom is the difference between fifteen
real overlaps in a refined structure and eight hundred imagined ones.

:::{tip}
Give it a **selection**, as the wizard does. `clashes all` includes the
backbone's own tight contacts — an `O` and the next residue's `C` really are
inside their van der Waals sum — and they bury whatever you were looking for.
:::

### Mutating a residue

`mutate` is PyMOL's mutagenesis wizard as a command:

```text
mutate resi 54, TRP        # the least-strained rotamer
mutate resi 54, TRP, 3     # ...or the third one the report lists
mutate sele, ALA           # whatever is picked
```

The backbone stays exactly where it is; the side chain is built onto it from an
idealised fragment, set to each rotamer of PyMOL's library in turn, and scored
by the same bump check `clashes` runs. The console prints the table the
wizard's panel shows — frequency and strain per rotamer — and marks the one
taken:

```text
mutate: TRP, 9 rotamers (taking #5)
    1   30.8%  strain  34.25  N-CA-CB-CG=-67, CA-CB-CG-CD1=100
 *  5    9.9%  strain  29.45  N-CA-CB-CG=61, CA-CB-CG-CD1=-90
```

so a second run with a number takes a different one. The **most frequent**
rotamer and the **least strained** are usually not the same, which is the whole
reason PyMOL shows both rather than picking silently.

| Detail | What happens |
| --- | --- |
| backbone | `N`, `CA`, `C`, `O` are the target's own, untouched |
| hydrogens | follow the structure — a crystal structure without them gets none |
| a residue with no `N`/`CA`/`C` | refused, as the wizard refuses it |
| `GLY`, `ALA` | one conformation; there is no chi angle to set |

Rebuilt as itself on 148L, the library's closest rotamer lands **0.50 Å** from
the deposited side chain on average (31 of 33 residues within 1 Å) — that is
the resolution of a rotamer library, which is a set of cluster means, not an
error in the build.

:::{note}
The rotamer library is PyMOL's **backbone-independent** one. PyMOL's wizard
defaults to the backbone-dependent library (phi/psi-binned, 1.4 MB), which is
better science; the reader for it is in
`chimol/analysis/make_residue_library.py --dependent`, and it is not shipped
because nothing yet asks to be phi/psi-aware.
:::

### The mutagenesis wizard

Choosing a rotamer means *looking* at each one, so mutation is the one place a
command is the wrong surface. **Wizard ▸ Mutagenesis** opens PyMOL's simplest
GUI: a small panel under the object list, and a line in the top-left of the
view saying what it is waiting for.

```{list-table}
:header-rows: 1
:widths: 30 70

* - Row
  - What it does
* - `Mutate THR`54/E to …`
  - the residue chooser — the twenty, grouped by class as PyMOL groups them
* - `< rotamer 5/9 >`
  - show the next conformation — a state change of the preview, not a rebuild
* - `10%  strain 29.4`
  - frequency and strain of the one on screen; opens the full list to jump
* - `Bump check: on`
  - draw the clash lines for the previewed conformation
* - `Apply` / `Clear` / `Done`
  - keep it, put the original residue back, or leave (leaving discards)
```

Pick a residue first — a click in the view or the sequence, or `select resi 54`
— then start the wizard; it takes whatever is selected. **Nothing is committed
until Apply**, and not because the change is undone: choosing a target builds
every rotamer once into a separate object called `mutation`, **one state per
rotamer**, exactly as PyMOL's `do_library` does. The structure you are mutating
is never touched, so `Clear` and `Done` are a delete rather than a restore, and
stepping is a state change costing about 30 ms rather than a rebuild of the
whole molecule (which, measured on a 1363-atom protein, took 2.2 s a step —
two thirds of it re-baking ambient occlusion for atoms that had not moved).

The same thing from the console, which is what the panel's rows send:

```text
wizard mutagenesis
wizard target, TRP
wizard rotamer, next      # or: wizard rotamer, 3
wizard bump, toggle
wizard apply              # or: wizard clear / wizard done
```

:::{note}
The `mutation` object appears in the object list while the wizard is open, with
its states, and you can hide or colour it like any other. Its states belong to
*it* — the panel's `<` and `>` step them, and the movie transport at the bottom
of the panel keeps meaning the trajectory, since asking the whole scene for
state seven to step a nine-state rotamer re-derives the scene bounds from a
fourteen-atom object. The camera is held across every wizard action for the same
reason: you framed the residue, and previewing must not take that away.
:::

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

## Presets — one command to a figure

A preset is a short recipe of ordinary commands that takes a freshly loaded
structure to something worth looking at. They are PyMOL's, transcribed from
`preset.py` with PyMOL's names, and they are in the object panel's **A** menu
under *preset* as well as on the command line:

```text
preset                       # list them
preset pretty                # cartoon ramped along the sequence, ligands as sticks
preset publication           # pretty, with the loops smoothed
preset technical, 148l       # chain rainbow, lines everywhere, ligands as sticks
preset ball_and_stick
preset b_factor_putty        # tube thickness and colour from the b-factor
preset classified            # cartoon / sticks / spheres by atom class
preset interface             # chains coloured, interface residues as sticks
preset default               # back to lines and nonbonded, coloured by element
```

`simple`, `simple_no_solv`, `ligands`, `ligand_sites`, `ligand_cartoon`,
`pretty_solv` and `pub_solv` complete PyMOL's set.

:::{note}
Where chimol cannot do one step of a recipe it does the rest and **says which
step it skipped** — `preset technical` reports that it drew no polar contacts,
because that needs a hydrogen-bond finder chimol has not got. A preset never
quietly produces less than it claims.

Two differences apply throughout: PyMOL scopes a setting to a selection
(`set stick_radius, 0.14, sele`) while chimol's settings are one global display
config, so a preset that changes a setting changes it everywhere and says so;
and PyMOL's `ribbon` is a thinner representation than its cartoon, while chimol
draws one cartoon for both.
:::

Chains are coloured from PyMOL's own 40-colour cycle, in PyMOL's order — chain A
is the carbon green, B cyan, C light magenta — so a figure reads the same way in
both programs.

### Side chains that grow out of the ribbon

The commonest figure there is — a cartoon with sticks on a few residues — is a
mess drawn naively, because each stick residue also draws its backbone N, C and
O running inside the ribbon. `cartoon_side_chain_helper` drops exactly those
bonds where a cartoon already covers them:

```text
show cartoon
show sticks, byres (resi 20-26)
set cartoon_side_chain_helper, on
```

It is a **bond** filter, not an atom filter: the backbone atoms stay in the
model and stay pickable. Proline keeps its N–CA, which closes its ring, and a
residue at the end of a cartoon segment keeps its backbone bonds so the sticks
still reach the ribbon. `preset ligand_cartoon` turns it on for you.

:::{note}
The camera stays where you put it. Only a camera command (`zoom`, `orient`,
`center`, `reset`) or loading a structure moves it — colouring, changing a
representation, adding a label or any `set` leave your framing alone, as they do
in PyMOL. Resizing the window keeps the same framing too, re-deriving the
distance so a tall window does not cut the molecule off at the sides.
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

Both run over every object the selection reaches, and `stored` is shared across
them, so a group is the natural way to gather from several molecules at once:

```text
iterate ligands and elem C, stored.setdefault('b', []).append(b)
```

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
ray render.png, 1200, 900    # ray-traced, with real shadows
ray                          # ...at the size of the viewport
ray 1600                     # ...1600 wide, at the viewport's aspect
```

Sizes follow PyMOL's rule. With none given the trace is the size of the **scene
column** — the viewport minus the panel's column and the sequence viewer's band,
which is the rectangle the molecule is drawn into — so the picture is framed
exactly as it is on screen. Give one dimension and the other preserves the
current aspect; give both and you get what you asked for, framed to that aspect.

`ray` traces **the scene you are looking at**: cartoon, sticks, spheres, surface
and wireframe all reach the image, and a wireframe becomes round-capped
cylinders one `line_width` of pixels thick, as it does in PyMOL. Two things it
does not draw, and reports rather than dropping in silence:

* **labels** — a label is rasterised glyphs and the tracer has no glyph. Use
  `png` when the labels are the point of the figure;
* nothing at all, when nothing is shown — `ray` says so instead of falling back
  to the atoms and drawing a molecule the viewport was not showing.

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
| Selection scope | Every loaded object, as PyMOL's; groups are ordinary names |
| Presets | All 15 of PyMOL's, transcribed; skipped steps are reported |
| Camera, `get_view`/`set_view` | Matches PyMOL's 18-float tuple exactly |
| Object menus (A/S/H/L/C) | 1:1 with PyMOL's |
| `get_area` | Follows `dot_solvent` / `dot_density` / `solvent_radius` |
| Ray tracing | Every representation the viewport draws, except labels |
| Undo | Coordinates only, per object, 16 deep (PyMOL's scope) |
| Settings | 47 registered of PyMOL's 769 |

`okf/plugins/pymol-parity.md` tracks the rest.

## See also

- Tool: **ChiMOL** (`chisurf/plugins/chimol/`).
