---
type: Index
title: Getting started
description: ChiSurf uses pixi as the canonical environment and build manager (the CI uses it too).
tags: [getting-started, index]
---

# Getting started

## Installation and environment

ChiSurf uses [pixi](https://pixi.sh) as the canonical environment and build
manager (the CI uses it too). From a checkout of the repository:

```
pixi run chisurf        # launch the GUI  (== python -m chisurf)
pixi run test           # default suite (everything not slow, e2e, gui or widget)
pixi run test-gui       # tests marked gui or widget
```

The sibling packages in `modules/` (`tttrlib`, built from C++ source, plus
`chimol`, `imp-tricks`, `mmfdb` and `ndxplorer`) are installed by
`pixi run build-extensions`; `pixi run chisurf` and the `test*` tasks already
depend on it. If imports of those modules fail, run it by hand.

`python -m chisurf` first shows the ChiSurf splash window (the stage under way,
the version, the licence) while the session and its plugins start, then the
main window; the splash closes once the main window has drawn.

```{note}
Always launch ChiSurf with `python -m chisurf` (or `pixi run chisurf`),
never by pointing Python at `__main__.py` directly — running the file adds
`chisurf/` to `sys.path` and shadows the standard-library `math` module.

```

## Entry points

| Command | Purpose |
| --- | --- |
| `chisurf` | Launch the graphical analysis platform. |
| `csc` | Command-line interface. |
| `python -m chisurf.server` | Headless ZMQ / JSON-RPC server (server mode). |
| `csg_*` | Individual plugin GUIs (see `[project.gui-scripts]`). |

## The main window

The window opens with a tabbed column on the left — the **Tools** tree,
**Read data** and **Datasets** above, **Analysis** and **Plot settings** below —
so the rest of the width belongs to the workspace, where *Start* and the fit
windows open, and to the tools, which open as docks beside them. **Log** and
**Console** share the bottom edge. See
[Multiple document interface](../manual/multiple_document_interface.md).

Docks are yours to rearrange: drag one out of the stack to another edge,
resize it, or close it. The arrangement is saved when ChiSurf exits and
restored on the next start.

To get back to the arrangement above, use **View → Reset layout**
(also on the ribbon's *Main* tab, under *Window*). It forgets the saved
layout as well as re-applying the default, so the reset survives the next start.

### The ribbon in the native window

The ChiSurf window has the same ribbon: the tabs *File*, *Main*, *Spectroscopy*,
*Structure* and *Tools*, each tool in the group its plugin manifest names and
with the manifest's icon. In a narrow window the rightmost groups fold into one
button each (▾) that lists their tools, and what still does not fit goes behind
**»**, so every tool stays one click away. In the ribbon's corner,
**Search…** lists the matching tools of every tab, ▴ folds the ribbon down to
its tabs (a tab click then shows its buttons until you pick one), **❓ Help**
opens the documentation and 🌍 switches the language. The menu bar and the
**Tools** dock list the same tools under the same groups; the dock is a tree
with a filter.

### Colours tell the kind of task

Every panel of the native window wears the colour of the kind of work it is
for, and the same colour marks that kind everywhere: the panel's tab (strong
while it is in front, muted behind, with a line of the full colour), the stripe
under its tab strip, its group caption and underline in the ribbon, the bar
beside its tool in the **Tools** tree, and — tinted — the headers, tabs and
buttons of the tool inside it. Core chrome (the **Tools** tree, *Start*) stays a
quiet grey.

```{figure} ../images/native_window_task_colors.png
:alt: The native window with a decay tool, Hidden Markov model, Image Tools, Wizards and Documentation open; Wizards in front in orange.

Wizards (orange) in front; behind it a decay tool (red), Hidden Markov model
(olive), Image Tools (green) and Documentation (blue). Read data / Datasets /
Analysis are teal (fitting), Log / Console indigo.
```

| Colour | Kind of task | Where |
|---|---|---|
| blue | Documentation | *Main → Help* (Documentation, About) |
| orange | Wizards | *Tools → Calculators → Wizards* |
| green | Imaging | *Spectroscopy → Imaging* (Image Tools) |
| red | Decay | *Spectroscopy → Decay* (IRF, MaxEnt, lifetime fits, G-factor) |
| violet | Correlation | *Spectroscopy → Correlation* (FCS, PCH, 2D-FLCS, fFCS filters, diffusion calculator) |
| magenta | Single-molecule | *Spectroscopy → Single-Molecule* (ALEX, bursts, traces) |
| olive | Kinetics | *Spectroscopy → Kinetics* (Hidden Markov model) |
| brown | Structure | *Structure* (ChiMOL, FRET docking, QuEst, HydroPro, trajectory tools) |
| teal | Fitting | Read data, Datasets, Analysis, Plot settings, fit windows |
| steel blue | Tools | *Tools* (photon data, calculators, views, system) |
| warm grey | File and setup | *File* (Settings, File tools, projects) |
| indigo | Log and console | Log, Console |

Each colour has a dark- and a light-theme variant; text on every one of them
has a contrast of at least 4.5 : 1, and neighbouring colours differ in
lightness as well as hue, so they stay apart for most colour-vision
deficiencies — the label always names the panel, the colour is the second cue.
The key is declared once in `chisurf/emtk/task_colors.yaml`; a new tool filed
under an existing ribbon group takes that group's colour.

### Moving around a plot

Every plot — fit windows, plugin plots, image views — answers the mouse the
same way: drag to pan, turn the wheel to zoom about the pointer. While the view
is panned or zoomed, a small boxed **A** sits in the plot's lower-left corner;
click it and the view fits all the data again. It goes away
once the plot follows its data, and new data then refits the view on its own —
a zoomed plot keeps your zoom until you press **A**.

## Settings, theme and fonts

**Settings** (*File → Setup* in the **Tools** tree) holds every preference; its **Fonts**
destination sets the interface, editor and documentation fonts and the magnification of the
whole window, applied at once. See [Settings, theme and fonts](settings.md).

## Your first analysis

The fastest way to see ChiSurf work end-to-end is one of the guides:

- {doc}`Fitting a fluorescence-lifetime decay </guides/10_lifetime_anisotropy_fitting>`
— load a TCSPC decay, choose a model, and fit it.
- {doc}`A complete µs-ALEX smFRET workflow </guides/27_alex_smfret_workflow>`
— from raw photons to FRET-efficiency populations.
- {doc}`Computing an FCS correlation curve </guides/09_diffusion_fcs>`
— correlate a photon stream and fit a diffusion model.

Each guide links back to the matching {doc}`concept </concepts/index>` page that
explains the underlying theory.

## Finding help inside ChiSurf

All of this documentation ships with the application: **Help → Documentation**
(or **❓ Help** in the ribbon's corner) opens it in its own window, with the
same structure as this site — getting started, the concepts, the guides, the
fitting manual, the reference, and one entry per plugin.

Worth knowing about that window:

- **Search covers the full text of every page** (`Ctrl+F`). Results are
ranked, each with the passage that matched, and the tree narrows to them.
- **Cross-references are links.** A concept page's pointer to its guide, a
DOI in a *Further reading* list, a manual page's *See also* box — all of them
go somewhere; `Alt+Left` walks back, and every page carries previous /
next along the reading order.
- **Every plugin's** `?` **button opens its page here**, and its
`Guide` button walks you through the tool's own controls.
- **The text scales** with `Ctrl++` / `Ctrl+-` (`Ctrl+0` resets),
or `Ctrl` and the scroll wheel. Headings, tables and formulas scale with
it, because the page is re-rendered rather than magnified.

Maintainers can tick *Authoring tools* in that window to edit a page in
place, list the developer documentation, and record reviews. Two levels are
tracked: **AI-reviewed** means an agent has read the page and corrected what it
could verify against the source code, and **reviewed** means a human has
confirmed it against the running application. Either clears the release gate
(`csc help review-check`), and either lapses automatically when the page is
edited.


## If startup fails

ChiSurf reports the full diagnostic traceback through logging and exits with
the original startup exception. It leaves your settings intact. Run
`pixi run chisurf` in a terminal to inspect the diagnostic. Crash reports are
written in the settings directory; a configured `CHISURF_SETTINGS_DIR` also
applies to those reports. Save the traceback when reporting a startup problem.
