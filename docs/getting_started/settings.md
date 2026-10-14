---
type: Getting Started
title: Settings, theme and fonts
description: Where ChiSurf keeps its settings, how to switch between the dark and the light theme, and how to set the fonts, sizes and magnification of the window.
tags: [getting-started, settings]
---

# Settings, theme and fonts

**Settings** (the ⚙️ entry under *File → Setup* in the **Tools** tree, or *Settings → Edit*)
opens the Settings tool: a list of destinations on the left, the selected one on the right.
Every destination edits `settings_chisurf.yaml` in your settings folder (or a file beside it);
the packaged defaults sit underneath it, so the file holds only what you changed.

## Theme

*Settings → Dark theme* and *Settings → Light theme* switch the colours of the whole window at
once: docks, tabs, tables, fields, menus, plots, the console and the workspace. The choice is
saved to `gui.theme` (`dark`, the default, or `light`), so the next start opens in it. Both
themes keep text readable on every surface (WCAG contrast of at least 4.5:1). The colours of
data in a plot, task colours and button roles (the blue main action, the red destructive one)
each have a light and a dark variant of their own.

```{figure} ../images/settings_theme_light.png
:alt: The ChiSurf window in the light theme with a TCSPC lifetime fit: light docks, white tables and plots, a blue Fit button and red Remove buttons.

The light theme, with a TCSPC lifetime fit open.
```

From Python: `from emtk import theme; theme.apply_theme("light")` switches the running window
without saving; `chisurf.core.settings.theme.choose("light")` also saves it.

## Fonts

The **Fonts** destination sets the faces, sizes and magnification of the window. Every change
applies at once -- text is drawn again in the new face or size and every dock relays itself
out -- and is saved to `gui.fonts`, so the next start uses it too. **Reset to defaults** returns
to the shipped look. Each control explains itself in its tooltip; **Help** and **Guide** walk
through them.

```{figure} ../images/settings_fonts.png
:alt: The Settings tool with the Fonts destination: Interface, Editor and console, Documentation, Formulas and Rendering sections, each with a sample line in its font.

Settings → Fonts. Under each section a sample line is drawn in that section's font and
follows every change.
```

| Section | Setting | What it does |
|---|---|---|
| Interface | Face | The face of buttons, labels, menus and tables. `monospace` is the built-in face: sharpest and fastest. |
| | Size | All interface text, in points (8 pt shipped). Code, documentation and formulas follow it unless they have a size of their own. |
| | Magnification | Scales the whole window -- text, spacing, icons and plots -- like a browser zoom. Clicks still land where things are drawn. |
| Editor and console | Face, Size | The Console dock, the code editor and code blocks. Only monospaced faces are listed. A font picked in the code editor's own settings wins in that tool. |
| Documentation | Text face, Text size | Running text of the Documentation dock and the help windows. Its A− / A+ zoom on top. |
| | Heading face, Heading scale, Bold headings | Headings; the scale is the ratio between levels (a page title is the text size times its fourth power). |
| | Caption size | Figure captions and footnotes; by default one step below the text. |
| Formulas | Face, Size | The text face of formulas (`auto`: STIX Two, else Times New Roman, else DejaVu Serif). |
| Rendering | Resolution | Glyph raster scale of installed faces: 1× puts one glyph pixel on one screen pixel (sharpest); higher is smoother and softer. |
| | Smooth edges | Grey-scale anti-aliasing on or off. |
| | Fallback faces | Faces tried, in order, for a character the chosen face lacks (CJK, symbols, subscripts). |

Sizes of 0 read *Same as interface* (or *Same as text*): the role follows the size it is set
against rather than a number of its own. Any face field also takes a fallback chain,
`Inter, Verdana, prose`.

```{figure} ../images/settings_fonts_zoom125.png
:alt: The ChiSurf window at 800 × 600 with magnification 1.25: the ribbon folds its groups and the documentation toolbar wraps its zoom buttons onto a second row.

An 800 × 600 window at magnification 1.25: the window lays itself out for the smaller room,
the ribbon folds its groups into menus and toolbars wrap.
```

### Without the window

The block is plain YAML and can be edited by hand; a value out of range is clamped and a face
that is not installed falls back to the default, so a settings file copied from another
machine never stops ChiSurf from starting:

```yaml
gui:
  fonts:
    ui: {family: monospace, size: 9.0, bold: false}
    code: {family: "Menlo, monospace", size: 11.0, bold: false}
    prose: {family: prose, size: 10.5, bold: false}
    zoom: 1.25
```

From Python (the console, a macro) the same settings are emtk's font configuration:

```python
from emtk import fonts
fonts.update(zoom=1.25, code={"family": "Menlo"})   # applies on the next frame
fonts.config().to_dict()                              # what Settings → Fonts saves
```

The Qt window (`python -m chisurf --qt`) keeps its own `gui.application_font_size`; its console
takes the editor face from `gui.fonts.code` when that names an installed family.
