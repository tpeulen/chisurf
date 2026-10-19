---
type: Subsystem
title: Ribbon and hubs
description: How a plugin's manifest address becomes a ribbon tab, group and button, how hubs (meta tools) host other plugins, and the guards that keep every tool in exactly one place.
resource: chisurf/gui/widgets/ribbon/, chisurf/core/plugin/ribbon_layout.py, chisurf/emtk/shell_ribbon.py
tags: [gui, ribbon, plugins, hubs, navigation]
timestamp: '2026-10-12T00:00:00Z'
---

# What it is

The ribbon has **no layout file**. A plugin's manifest `display_name` is its
address, `"Tab:Group:Name"`: the first segment is the tab, the last the button,
everything between the group (`"Tab:A:B:Name"` → group `"A › B"`, any depth;
`"Tab:Name"` → a group named after its tab). The rules live once, Qt-free, in
`chisurf/core/plugin/ribbon_layout.py` (`split_address`, `is_listed`,
`group_records`, `plugin_layout`, `TAB_ORDER`). `PluginMethodsMixin._create_plugin_tabs`
(`ribbon_plugins.py`) builds the tabs from `group_records`, and the layout test reads
`plugin_layout`. `Setup:` and `Help:` plugins are drawn into the File and Main tabs
by their own hosts (`ribbon_categories.py`). The menubar "Plugins" menu reads the
same addresses (`chisurf/gui/__init__.py`, `populate_plugins`).

The emtk shell (`python -m chisurf`, the default window) builds its ribbon from the same
function: `chisurf/emtk/shell_ribbon.py::plugin_tree` feeds `plugin_layout` the native
plugins, and `emtk.ribbon.Ribbon` draws the tabs, groups and buttons. Its menu bar and
Tools dock read the same tree (`menu_tree`), so all three agree. The maturity markers
(⚠️, ⛔) come from `chisurf/core/plugin/maturity.py` in both shells. The parity record
against this ribbon is [Qt retirement (shell)](qt-retirement.md), resume item 5.

A **hub** (meta tool) is an ordinary plugin with an address whose window hosts
other plugins as panels: Image Tools, Calculators,
Wizards, Games, Settings, FRET (docking + pair selection),
Burst Analysis, ALEX Suite, FCS (the five-step correlator workflow; its rail holds
only the workflow's own steps). The ribbon knows nothing about hubs. A hosted tool leaves the ribbon
only because its own manifest says `menu_hidden`. Hub list rows show each child's
icon through `chisurf.emtk.plugin_icons.entry_icon`.

# The layout (2026-10-08)

Domain tabs, left to right (`TAB_ORDER`):

| Tab | Groups → buttons |
|---|---|
| File | Recent · Project · Fits · Application (built in) · **Setup**: Settings, Switch User, Menu Switch · **Data**: BID→Analysis · MFD Prepare · PTO Inspector · Split/Convert · TTTR Header editor · TTTR→Time-Window BIDs · ⇄ .pto (the former File tools hub, dissolved: seven ordinary tools) |
| Main | **Window**: the toolbar's window actions, minus those File shows (`ribbon_file.FILE_ACTIONS`) · **Help** |
| Spectroscopy | **Correlation**: 2D-FLCS, Burst-wise FCS, Diffusion/Volume Calculator, FCS, FCS Filter Calculator, Lifetime-FCS Simulator, PCH (the FCS toolbox's tool rail dissolved 2026-10-19; FCS is the `fcs_correlator` workflow) · **Decay**: Histogram-Microtime, IRF Estimation, Lazy Lifetime Analysis, MaxEnt MEM, Synthetic Decay Generator, VV/VH Anisotropy Decay, VV/VH G-Factor Calculator (the former Decay Analysis hub, dissolved: seven ordinary tools) · **Kinetics**: Hidden Markov model · **Single-Molecule**: ALEX Suite, Burst Analysis, Intensity trace, Trace Browser, ebFRET · **Imaging**: Image Tools |
| Structure | **Modelling**: ChiMOL · **FRET**: Docking & Screening, FPS JSON Editor · **Computation**: HydroPro, QuEst · **Trajectory**: Align, Convert, Energy Calculator, FRET, Join, Remove Clashed, Rotate/Translate, Save Topol (the Traj Tools hub, removed 2026-10-19) |
| Tools | **Calculators**: Calculators, Light Path Simulator, Spectra Downloader, Wizards · **Photon data**: ALEX Creator, Audifier, Count Rate Analysis, Microtime Shifter, Photon Table (the former TTTR Tools hub, removed 2026-10-19: five ordinary tools) · **System**: Code Editor, Games, MMFDB Admin · **Views**: Acquisition, Global View, ndX |

Hub scopes that decide where a new tool goes:

- **Tools › Photon data**: photon-level work on a stream; every tool is its own
  button (no hub). Count Rate Analysis and Audifier carry their own detector editor.
- **Image Tools**: every imaging tool, including CLSM Generator.
- **Spectroscopy › Decay**: every decay tool is an ordinary tool of its own (no hub).
- **Calculators**: stand-alone calculators, κ² included. The FCS diffusion
  calculator is its own Spectroscopy › Correlation tool.
- **Spectroscopy › Correlation**: every FCS tool is its own button; the FCS workflow reaches the
  filter calculator by the `fcs_correlator_files` hand-off (**Filter Calc...**), not by hosting it.
- **Structure tab has no hub** (owner, 2026-10-12): the former Structure Tools
  hub was dissolved; each structure tool is its own ribbon button, grouped by
  `GROUP_ORDER["Structure"]` (Modelling, FRET, Computation, Trajectory). The trajectory
  tools are ordinary buttons too (Traj Tools removed 2026-10-19); the shared card window shell is
  `chisurf/emtk/card_shell.py`.

# Task colours (2026-10-11)

Every kind of task has one colour, declared once in `chisurf/emtk/task_colors.yaml`
(category → dark/light `fill`, `text`, `ink`; `groups` maps `"Tab:Group"` / `"Tab:*"`,
`plugins` overrides one tool — Wizards sits in *Calculators* but is orange —, `docks`
names the shell's own panels by key or prefix; `neutral` is core chrome).
`chisurf/emtk/task_colors.py` only reads it and assigns: `plugin_categories` (by where the
shipped `plugin_layout` puts each plugin), `dock_category`, `accent` → an
`emtk.style.ThemedAccent`. **All drawing is emtk's** (`emtk/accents.py`, emtk `0ec0daf`):
`DockWindow.accent`/`header_tint` (tab strong/muted with a line, strip stripe, floating
title, headers inside), `RibbonGroup.accent` (caption + underline), `RibbonButton.accent`
(bar on a tool of another kind), `accents.region` around `draw_child` (hosted app *and its
hosted apps* tinted through `emtk.style.ambient_colours`), `accents.headers/caption/mark_item`
for the Tools tree. The theme variant is picked at draw time from `WINDOW_BG`; every tint
backs off until the theme's text reads at 4.5:1 (or no worse than the theme's own colour).
The shell assigns accents each frame in `EmtkShellApp._colour_docks` (fit windows appear
later). Colour key for users: [getting started](../../docs/getting_started/index.md)
"Colours tell the kind of task".

# Guards

- `test/plugins/test_ribbon_layout.py`: pins tab → group → buttons from the shipped
  default settings (`EXPECTED`). A deliberate move updates it in the same change.
- `test/gui/test_ribbon_layout_build.py`: the real ribbon builds every tab and panel
  `plugin_layout` computes.
- `test/plugins/test_hub_membership.py`: every hosted tool is `menu_hidden`, no tool
  is in two hubs, and every hidden tool with a GUI is hosted somewhere. Children are
  read from each hub's own declaration (`panels.json`, registries, panel tables, and
  for Qt-only hubs the plugins their panel code imports). Each exception carries a
  reason, and a stale exception fails the test.
- `test/plugins/test_plugin_menu_tabs.py`: the closed tab vocabulary.

## Where to pick this up

8. Open: hub dissolution is an open class. File tools was dissolved (as Structure Tools was, and TTTR Tools on 2026-10-19 — owner: "no need for meta plugin in emtk"): its seven tools are plain File › Data plugins and the hub, its tests and its Qt-inventory row are gone; Split/Convert and Time Windows now own their saved options. Traj Tools and the FCS toolbox's tool rail followed on 2026-10-19 (the FCS entry is now the `fcs_correlator` workflow; its Filter Calc button is a hand-off). Remaining hubs, to dissolve or keep by decision: Image Tools, Burst Analysis, ALEX Suite, Setup, Calculators and Wizards (`CalculatorHubApp`), Games. `test/plugins/test_hub_membership.py` (`_declared_children`) is the live list. Measure: dissolving one means deleting its `menu_hidden` flags, re-pinning `EXPECTED` in `test_ribbon_layout.py`, and striking the hub's row from the two `shell_*_qt_inventory.json` files. Trap: `test_plugin_help_guide_seam.py` reads manifests from HEAD, so it stays red for a deleted hub until the commit lands; a dissolved tool also needs a distinct manifest icon (`test_plugin_icon_manifest.py`) because it now shares the ribbon with its neighbours.

7. Measure: task colours with `test/native_emtk/test_task_colors.py` (palette loads, every
   manifest plugin has a category, contrast ≥ 4.5 in dark and light, a hosted tab drawn in
   its colour) and emtk `tests/test_accents.py`. A new ribbon group needs a `groups` line in
   `task_colors.yaml` or the coverage test names it. Open: (a) the shell has **no light-theme
   switch** — light was verified with `style_colors_light` applied to the palette via
   `emtk.style.use_palette` (inverted dark palette), so a real light theme should be checked
   when one lands; (b) table header rows (`TABLE_HEADER_BG`, a module constant, not a `Col`
   role) stay the theme blue inside tinted docks; (c) 12 categories cannot all be
   colour-blind distinct — lightness varies (fill luminance 0.05–0.17) but olive/brown/orange
   and blue/indigo/violet pairs rely on the label. Screenshot recipe: `HostedDriver(shell,
   (1440, 900), scale=1|2)` with Decay Analysis, HMM, Image Tools, Wizards, Documentation
   opened; light = invert every upper-case tuple of `emtk.style` with `use_palette` before
   the shell is made.

6. Measure: the emtk shell's ribbon must stay equal to this one tab for tab:
   `test/native_emtk/test_emtk_shell_ribbon.py::test_parity_with_the_qt_ribbon`. A deliberate
   move here updates `EXPECTED` in `test_ribbon_layout.py` and needs no change there, because
   both read `plugin_layout`; re-capture the Qt half with `capture_shell_s5_qt_before.py`.

5. Open: **Panel captions are clipped** at the ribbon's default height in offscreen grabs
   (descenders). This predates the regroup.

Done 2026-10-05, third pass: the TTTR script tools are retired after their gaps were
closed in the hosted tools. Histogram-Microtime has the inter-photon filter
(`gap_selection`) and the FCS correlator has a Method choice. Guide 73 now
describes those two tools.

Done 2026-10-05, second pass: TTTR Tools runs on `chisurf/emtk/tool_hub.py`. Groups
follow `GROUP_ORDER`. Ribbon icons were letter placeholders for every plugin whose
emoji lives only in its manifest, because the plugin-tab builder and the toolbar
did not pass the manifest to `create_plugin_icon_with_fallback`. That function now
reads `package_dir/manifest.json` itself (guard:
`test/plugins/test_plugin_icon_manifest.py`).

### Resume history (moved out of Where to pick this up)

Moved here unchanged: notes that are history, done work or standing rules rather than the next step.

1. **Native Burst Analysis: done 2026-10-06 (T-20261005-BURSTEMTK).** The ribbon's
   Burst Analysis opens `burst_analysis/gui/native.py` on `chisurf/emtk/tool_hub.py`
   (`entrypoints.emtk`): the legacy steps in order, each the native app of its plugin
   (Burst Selection's included), with the workflow hand-off of the Qt shell. Accurate
   FRET and Photon-by-photon kinetics are reachable natively as its side tools.
   **The ALEX Suite is native too (2026-10-06, T-20261006-ALEXHUB):** its ribbon button
   opens `alex_suite/gui/native.py`, Burst Analysis's hub with ALEX's seven numbered steps
   walked by Next (µs-ALEX converted on arrival, a demo measurement on the files step) and
   four side tools; the five burst steps it shares with Burst Analysis are listed in
   `test_hub_membership.py`'s `SHARED`. Left: the hub inherits three ToolHubApp limits
   (fixed rail, header badge, a status line wider than its room covers Back / Next: worked
   around in `AlexHubApp` only, see known-issues) and the Qt shells
   are still on disk; the ordered list is in
   [burst-survey.md](../plugins/emtk-ports/burst-survey.md).

2. **Ribbon buttons that still open Qt:** none. MMFDB Admin is native
   since 2026-10-06 (T-20261005-MMFDBEMTK, `entrypoints.emtk`; parity in
   `okf/plugins/emtk-ports/mmfdb_admin/REPORT.md`). (Intensity
   trace landed as emtk; Screenshot is no longer a plugin but the main window's
   *Screenshot* action, `chisurf/gui/screenshot_action.py`, shown in Main › Window.)

4. **CLI-only tools have no GUI home:** `fcs_convert`, `proteinmc`. That is correct
   until they gain an app; `test_hub_membership` will then ask for a hub.

# Traps

- **The address is live.** A segment typo opens a new tab or a sibling group that
  differs only in case. `test_plugin_registry.py` guards case consistency, and the
  first `categories` entry must equal the tab.
- **Do not trust the module-level `name` fallback.** Several plugins mirror their
  address in `__init__.py` as `name = ...`. The manifest wins, but a stale fallback
  misleads whoever reads it. They were updated in this regrouping.
- **The toolbar setting resolves by the last segment** (`gui/main.py`,
  `plugins.toolbar_plugins`), so a move does not drop a toolbar button. Users'
  copied settings keep the old addresses, and that is fine.


# Where to pick this up

W6g fold (2026-10-08): Imaging manifests move under Spectroscopy; Correlation
and Decay addresses normalize, while categories/IDs/entrypoints remain intact.
The35matched manifest snapshot preserves pre-change routes; actualQt1400px and
640px scrolled before/after scenes and triggered Image Tools route are verified.
Settings loader migrates historical full-address disabled/order/statefulness/
toolbar preferences with explicit-current-key precedence. Continuation panels
retain every8-record chunk; scroll tests reach the last button. Hidden FRET is
not surfaced by a menu fold; its explicit workflow unit owns visibility.
Remaining W6g work: shared tooltip/i18n/demo/window gates; the full programme
resume is in [the current job](../validation/release-readiness-w6g/current-job.md).
