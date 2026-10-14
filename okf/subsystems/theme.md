---
type: Subsystem
title: Light and dark theme
description: The emtk window's colour theme. emtk.theme holds a value for every palette name of emtk.style (windows, docks, tabs, tables, fields, menus, plots, code, the host surface). Settings → Dark theme / Light theme switches it live and stores it in gui.theme. A guard keeps literal colours out of the windows.
resource: chisurf/core/settings/theme.py
tags: [gui, emtk, theme, colour, settings, accessibility]
timestamp: '2026-10-14T00:00:00Z'
---

# Where to pick this up

The list of 2026-10-14 is closed. What remains is retired with the Qt host or is by design.

1. **Measure.** `test/test_theme_tokens.py` now scans three kinds of colour in shipped emtk
   code:
   - literal colours handed to `text_colored` / `push_style_color`;
   - literal colours handed to painter and draw-list calls (`fill_rect`, `add_rect_filled`,
     `add_text`, …);
   - module constants named as a surface or its text (`*_BG`, `BACKDROP`, `PANEL*`,
     `*TITLE*`, `*TEXT*`, `DIM`, `BRIGHT`, `*GRID*`) that are drawn with.

   It reports zero. Exempt by design:
   - the games (`plugins/misc/games/`), which keep their own board palettes;
   - the splash (`emtk/splash.py`), artwork drawn before a theme is applied.

   Data colours (series, gates, regions, graph edges) and accent rims are free to be
   constants. Trap: a data colour picked for the dark plot can vanish on a white one.
   Fixed so far: `burst_background` `REGION_FILL` was white at 30, and
   `tttr_time_windows` `BOUNDARY_COLOUR` was a light grey. The scan cannot see this:
   read a light screenshot of the tool on its data.
2. **Retired with the Qt host (S6), not emtk surfaces.** `WINDOW_BG` exports that only
   colour a Qt `ControlHost` (`test_theme_tokens.qt_host_only_constants`):
   - in use: `help/gui/help_app.py` (via `help/gui/tool.py`),
     `calculator/kappa2_dist/gui/app.py` (via `gui/widgets/models/tcspc/kappa2_helpers.py`),
     `code_editor/gui/editor_app.py` (via its `gui/tool.py`),
     `gui/widgets/fitting/plot_settings_host.py` `BACKGROUND`;
   - exported, read by nothing: `fit_pages/surface.py` `BACKGROUND`, and `WINDOW_BG` in
     accurate_fret, alex_suite, burst_2cde, burst_analysis (2), burst_background,
     burst_browser, burst_bva, burst_fusion, burst_gs, burst_irf_bg, phasor_calculator,
     tttr_count_rate_analysis, tttr_header_edit, tttr_splitter and tttr_time_windows.

   Delete them with their Qt tools.
3. **Not screenshotted: the ProteinMC network page.** It needs a ProteinMC fit with a
   labelling file. Its background now follows the theme, and its nodes, edges, labels and
   frame cursor are mid tones or theme text. Check it on the next ProteinMC session.

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

**Second pass (emtk 0.1.20 `4e3f3b0` + `d1d07c9`, chisurf).**

- The node editor follows the theme.
  - emtk: `nodes.Style.follow_theme` / `sync_theme`; a light mini map.
  - chisurf: the node-graph settings draw the grid in the theme's text colour.
    `GraphControl` rebuilds its style on a theme switch and runs host `style_hooks`, which
    keep Global View's background, now the theme's `PLOT_BG`.
- ImPlot3D is reset to automatic colours with ImPlot.
- **State-scheme canvas:** backdrop, grid, frame and plain rate badges come from the theme;
  the coloured discs and badges keep white ink.
- **ProteinMC network page:** the plot background follows the theme; the cursor, edges and
  nodes are mid tones.
- **ebFRET:** frames, dialog, titles and errors come from the theme.
- **Smaller sites:** the channel-definition cells, notebook cell headers, the Global View
  legend, help callouts, the mmfdb spectra placeholder, the IRF crosshair, the plot-settings
  grid preview and the chiplot grips.
- **Code editor:** its colour scheme defaults to `Theme` (Light on a light window, Dark on a
  dark one). A picked scheme or an edited colour wins.
- **emtk tk host:** its wheel notch comes from `tk_wheel_unit` (Tk 8.6 on macOS reports
  lines). That was the root cause of `test_tk_host`'s -360.

**Guard.** `test/test_theme_tokens.py` checks:

- no shipped emtk code hands `text_colored` / `push_style_color`, or a painter / draw-list
  call, a literal colour tuple, and draws no surface constant;
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
