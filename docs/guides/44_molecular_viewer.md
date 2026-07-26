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
