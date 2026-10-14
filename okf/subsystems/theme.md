---
type: Subsystem
title: Light and dark theme
description: The emtk window's colour theme. emtk.theme holds a value for every palette name of emtk.style (windows, docks, tabs, tables, fields, menus, plots, code, the host surface). Settings → Dark theme / Light theme switches it live and stores it in gui.theme. A guard keeps literal colours out of the windows.
resource: chisurf/core/settings/theme.py
tags: [gui, emtk, theme, colour, settings, accessibility]
timestamp: '2026-10-14T00:00:00Z'
---

# Where to pick this up

1. **Measure what is still dark-only.** `test/test_theme_tokens.py` scans only literal colours
   handed to `im.text_colored` / `im.push_style_color`. Two kinds of colour slip past it:
   module constants and draw-list fills. Count the constants with
   `grep -rnE "^[A-Z_]+(BG|BACKDROP|BORDER|PANEL)[A-Z_]*\s*=\s*\(\s*[0-9]{1,2},\s*[0-9]{1,2},\s*[0-9]{1,2}" chisurf | grep '\.py:'`
   (2026-10-14: 33 constants in 20 files). Most are `WINDOW_BG` exports that only colour a
   Qt `ControlHost`. The ones a light window shows:
   - `fit_pages/pages/state_scheme_emtk.py`: the state-scheme canvas;
   - `fit_pages/pages/proteinMC.py`: `set_background((20, 20, 20))`;
   - `burst_ebfret` painter fills;
   - the burst apps' `PANEL_BG`.

   Trap: pick the screenshot state with care. The 2CDE and splitter screenshots show these
   gaps only once a tool is opened on its data.
2. **Open: the node editor (`emtk/nodes.py`, 47 literals) and `emtk/implot3d` are not
   themed.** Neither is in the shell's default layout. They need a token pass like the
   one 0.1.18 gave plots and markdown.
3. **Open: the code editor's syntax palette** comes from its own colour-scheme preference
   (`palette_for(self.color_scheme, …)`), not from the theme. On the light theme its
   dark-scheme default draws light tokens on a white field. Its chrome already follows
   (`DARK_CHROME` is pushed only on the dark theme). Make the scheme default `auto`, meaning
   the theme's palette.
4. **Open: `emtk/tk_host.py`** still clears to (30, 32, 38). The tk host is not used by the
   shell.
5. **Owned by the LLTF lane:** two missing radio tooltips in `lltf.view.json` fail
   `test/test_tooltips.py`. Not theme-related.

# How it works

**emtk (0.1.18, 0.1.19).** Every colour emtk draws with is a palette name in `emtk.style`.
Controls read it as they draw; a fresh immediate-mode `Style()` copies it.
`emtk.theme.apply_theme(name, styles=[…])` sets all of them at once:

- `DARK`: the shipped values, unchanged;
- `LIGHT`: designed;
- also sets `FRAME_BORDER_SIZE` (a light field needs an edge, 1 px);
- re-themes the styles it is handed;
- resets ImPlot to its automatic colours;
- notifies `on_change` listeners.

What made the old inverted "light" (`im.style_colors_light`) leave the docks dark, and was
fixed:

- 13 widget modules bound palette colours at import (`from ..style import TEXT as _TEXT`).
  They now read `emtk.style.<NAME>` at draw time.
- Plot chrome, the auto-range button, child scrollbars, markdown, chat and the tour card
  used literals. They are now palette names:
  - `PLOT_BG`, `PLOT_GRID`, `PLOT_TICK_TEXT`, `PLOT_LABEL_TEXT`, `PLOT_LEGEND_BG`, …;
  - `SCROLL_*`;
  - `HEADING_1..4`, `TEXT_NOTE`/`TIP`/`WARNING`/`DANGER`/`QUOTE`;
  - `CODE_BG`, `CODE_INLINE_BG`, `CARD_BG`.
- Host surfaces (`ControlSurface`, the wgpu and Qt hosts) cleared to a fixed (30, 32, 38).
  Without a given background they now read `HOST_BG` every frame, and so does the test
  `Driver`'s screenshot.
- A `TextEditor` without an assigned palette takes `LIGHT_PALETTE` on a light window.

`tests/test_theme.py` (emtk) holds both themes to WCAG AA:

- `TEXT` on 17 surfaces;
- headings, links, the table header and plot text on theirs.

**chisurf.**

- `chisurf/core/settings/theme.py`: `stored()` / `apply_stored()` / `choose(name)` over
  `gui.theme`. The default is `dark`, declared in `settings_chisurf.yaml`.
- The shell applies the stored theme at startup, next to the fonts.
- *Settings → Dark theme / Light theme* (`EmtkShellApp._theme_actions`, checked items)
  switches and saves.
- chiplot's emtk canvas resolves its background and axis text from `PLOT_*` unless a caller
  set them; `set_background(None)` returns to the theme. A `themed=True` text box (the fit
  plot's χ² readout) takes the theme's legend colours.
- The console picks `OUTPUT_PALETTE_LIGHT` on a light window.
- The help window, the tour card and about 45 plugin captions and status lines (errors,
  warnings, section captions) name theme colours instead of literals.
- Hand-painted green/red buttons became button roles ([UI vocabulary](ui-vocabulary.md)).

**Guard.** `test/test_theme_tokens.py` checks four things:

- no shipped emtk code hands `text_colored` / `push_style_color` a literal colour tuple;
- the choice round-trips through `gui.theme`;
- the plot background follows the theme unless set;
- the Settings menu switches the theme.

**Screenshots read** (headless, arm64, scratch settings):

- the shell with a TCSPC Lifetime fit, dark and light. Docks, tables, fields, tabs, plots,
  the χ² box, the console and the gaps between docks all follow; nothing is left dark;
- tttr_splitter and burst_2cde in both themes.

The light shot is `docs/images/settings_theme_light.png`. User docs:
`docs/getting_started/settings.md` § Theme.

See also: [Fonts](fonts.md), [UI vocabulary](ui-vocabulary.md), [chiplot](chiplot.md).
