# ChiMOL — molecular viewer

ChiMOL loads structures, draws them, selects parts of them, measures them and
writes them back out. Its command language, selection grammar and object menus
follow PyMOL, so PyMOL scripts and habits largely carry over.

## The window

The molecule owns the window. The **menus** and the **toolbar row** (Open,
Plane, Surf, Cfg, AA, SS, Seq, Info, Density, Tree) sit at the top, the
**sequence strip** below them, the **object list** at the top right, the
**mouse-mode block** at the bottom right and the **command prompt** along the
bottom edge. All of them are part of the viewer's frame; the line under it
counts the open objects and holds **Help** and **Guide**.

## Opening a structure

* **File → Open** or the **Open** button: PDB, mmCIF, trajectories, MRC maps, RMF.
* **Demo** menu: shipped example scenes.
* At the prompt: `load path/to/file.pdb` or `fetch 148l`.

## The mouse

Left drag rotates, middle drag moves, right drag zooms, the wheel moves the
slab. The mouse-mode block lists every button and modifier combination.

## The command line

Press **Return** to focus the prompt, type a command, Return again to run it:
`show sticks, sele`, `color red, sele`, `select resi 54`, `png`.

## Objects

Each row of the object list has **A**ction, **S**how, **H**ide, **L**abel and
**C**olour menus; the eye toggles visibility. `all` and `sele` are always there.

## Further reading

* [The molecular viewer (ChiMOL)](docs/guides/44_molecular_viewer.md)
* [Molecular surfaces](docs/concepts/molecular_surfaces.md)
* [Structures and trajectories](docs/concepts/structure_trajectories.md)
