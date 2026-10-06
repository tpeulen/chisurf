---
type: Subsystem
title: Ribbon and hubs
description: How a plugin's manifest address becomes a ribbon tab, group and button, how hubs (meta tools) host other plugins, and the guards that keep every tool in exactly one place.
resource: chisurf/gui/widgets/ribbon/
tags: [gui, ribbon, plugins, hubs, navigation]
timestamp: '2026-10-05T00:00:00Z'
---

# What it is

The ribbon has **no layout file**. A plugin's manifest `display_name` is its
address, `"Tab:Group:Name"`: the first segment is the tab, the last the button,
everything between the group (`"Tab:A:B:Name"` → group `"A › B"`, any depth;
`"Tab:Name"` → a group named after its tab). The rules live once, Qt-free, in
`chisurf/gui/widgets/ribbon/layout.py` (`split_address`, `is_listed`,
`group_records`, `plugin_layout`, `TAB_ORDER`). `PluginMethodsMixin._create_plugin_tabs`
(`ribbon_plugins.py`) builds the tabs from `group_records`, and the layout test reads
`plugin_layout`. `Setup:` and `Help:` plugins are drawn into the File and Main tabs
by their own hosts (`ribbon_categories.py`). The menubar "Plugins" menu reads the
same addresses (`chisurf/gui/__init__.py`, `populate_plugins`).

A **hub** (meta tool) is an ordinary plugin with an address whose window hosts
other plugins as panels: TTTR Tools, File tools, Image Tools, Calculators,
Wizards, Games, Settings, Structure Tools (with Trajectory Tools nested),
Decay Analysis, Burst Analysis, ALEX Suite, FCS (with the FCS correlator
nested). The ribbon knows nothing about hubs. A hosted tool leaves the ribbon
only because its own manifest says `menu_hidden`. Hub list rows show each child's
icon through `chisurf.emtk.plugin_icons.entry_icon`.

# The layout (2026-10-05)

Domain tabs, left to right (`TAB_ORDER`):

| Tab | Groups → buttons |
|---|---|
| File | Recent · Project · Fits · Application (built in) · **Setup**: Settings, Switch User, Menu Switch · **Data**: File tools |
| Main | **Window**: the toolbar's window actions, minus those File shows (`ribbon_file.FILE_ACTIONS`) · **Help** |
| Spectroscopy | **Correlation**: FCS, PCH · **Decay**: Decay Analysis · **Kinetics**: Hidden Markov model · **Single-Molecule**: ALEX Suite, Burst Analysis, Intensity trace, Trace Browser, ebFRET |
| Imaging | Image Tools |
| Structure | **Modelling**: ChiMOL, Structure Tools |
| Tools | **Calculators**: Calculators, Light Path Simulator, Spectra Downloader, Wizards · **Photon data**: TTTR Tools · **System**: Code Editor, Games, MMFDB Admin · **Views**: Acquisition, Global View, ndX |

Hub scopes that decide where a new tool goes:

- **TTTR Tools**: photon-level work on a stream (ALEX Creator, Micro-time Shifter,
  Photon Table, Count Rate Analysis, Audifier).
- **File tools**: file and container work (Split/Convert, header editor, ⇄ .pto,
  PTO Inspector, Time Windows, BID → Analysis, MFD Prepare).
- **Image Tools**: every imaging tool, including CLSM Generator.
- **Decay Analysis**: decay tools, including VV/VH Anisotropy and Synthetic Decay.
- **Calculators**: stand-alone calculators, κ² included. The FCS diffusion
  calculator is hosted by FCS only.

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

1. **Native Burst Analysis: done 2026-10-06 (T-20261005-BURSTEMTK).** The ribbon's
   Burst Analysis opens `burst_analysis/gui/native.py` on `chisurf/emtk/tool_hub.py`
   (`entrypoints.emtk`): the legacy steps in order, each the native app of its plugin
   (Burst Selection's included), with the workflow hand-off of the Qt shell. Accurate
   FRET and Photon-by-photon kinetics are reachable natively as its side tools. Left:
   the ALEX Suite still subclasses the Qt shell (card AS4) and the hub inherits two
   ToolHubApp limits (fixed rail, header badge); the ordered list is in
   [burst-survey.md](../plugins/emtk-ports/burst-survey.md).
2. **Ribbon buttons that still open Qt:** none. MMFDB Admin is native
   since 2026-10-06 (T-20261005-MMFDBEMTK, `entrypoints.emtk`; parity in
   `okf/plugins/emtk-ports/mmfdb_admin/REPORT.md`). (Intensity
   trace landed as emtk; Screenshot is no longer a plugin but the main window's
   *Screenshot* action, `chisurf/gui/screenshot_action.py`, shown in Main › Window.)

4. **CLI-only tools have no GUI home:** `fcs_convert`, `proteinmc`. That is correct
   until they gain an app; `test_hub_membership` will then ask for a hub.
5. **Panel captions are clipped** at the ribbon's default height in offscreen grabs
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
