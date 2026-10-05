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
| Tools | **Calculators**: Calculators, Light Path Simulator, Spectra Downloader, Wizards · **Photon data**: TTTR Tools · **System**: Code Editor, Games, MMFDB Admin, Screenshot · **Views**: Acquisition, Global View, ndX |

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

1. **Burst Analysis and ALEX Suite are Qt-only hubs.** The membership test reads their
   children from imports in `gui/tool.py`, which works but is the weakest declaration.
   An emtk port (or even a plain `PANELS` table) would make them data like the rest.
   Burst Analysis also hosts Accurate FRET and Photon-by-photon kinetics, whose ribbon
   buttons were removed, so in a pure-emtk session those two are reachable only through
   this Qt window.
2. **CLI-only tools have no GUI home:** `fcs_convert`, `proteinmc`. That is correct
   until they gain an app, at which point the membership test will ask for a hub
   (File tools for the converter, Structure Tools for ProteinMC).
3. **`TTTR:Correlate` and `TTTR:Generate Decay`** are broken script plugins, disabled
   by default and now `menu_hidden`. When they gain apps they belong in TTTR Tools.
4. **`traj_energy`** is a second manifest for the Energy Calculator app that
   Trajectory Tools hosts (as `traj_energy_calculator`). One of the two manifests
   should go. Deleting a plugin directory is a decision for the owner, so it is
   allow-listed for now.
5. **Panel titles are clipped** at the ribbon's default height in offscreen grabs
   (the group caption's descenders). This was already true before the regrouping.
6. **Group order inside a tab** is the order of first appearance, which is
   alphabetical by address (Calculators, Photon data, System, Views). If an order
   should be authored, add a per-tab group order beside `TAB_ORDER` and pin it in
   the layout test.

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
