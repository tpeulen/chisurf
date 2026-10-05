---
type: Plugin Group
title: TTTR tools
description: Photon-stream tools for converting, browsing, shifting, splitting, previewing and summarizing TTTR data.
resource: chisurf/plugins/tttr/
tags: [plugins, tttr, photons, converters]
timestamp: '2026-07-05T00:00:00Z'
---

The `tttr/` group works directly on Time-Tagged Time-Resolved photon streams.
These tools are close to [data IO](/subsystems/data-io.md): most load files via
the TTTR backend, then either transform files, extract metadata/traces/images,
or compute quick diagnostics before downstream [burst](/plugins/burst.md),
[FCS](/plugins/fcs.md), [fluorescence-decay](/plugins/fluorescence-decay.md),
or [imaging](/plugins/imaging.md) analysis.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `filetools` | Tools:File tools | Hub (shared navigation-panel shell) for everything that acts on a *file* rather than on the physics inside it: TTTR Split/Convert, pack/unpack a `.pto`, the PTO Inspector, the TTTR header editor, TTTR->Time-Window BIDs, and BID->Analysis. Every member is `menu_hidden` and appears only inside the hub. Renamed from `converter`, whose name no longer covered what it held. |
| `tttr_toolbox` | Tools:TTTR Tools | Unified toolbox (`gui/panels.json`): ALEX Creator, Micro-time Shifter, TTTR Header Editor, **Photon Table**, Split/Convert, Count Rate Analysis, Audifier. The children are `menu_hidden`; the toolbox is their menu entry. Each list row draws the child's icon in its own slot (see [hub icons](#hub-icons)). |
| `ptu_alex_creator` | Tools:Converter:ALEX Creator | Converts macro-time ALEX modulation into micro-time / PIE-style files; supports single, batch, and merged output plus histogram inspection. |
| `tttr_microtime_shifter` | Tools:TTTR:Microtime Shifter | Applies global and per-channel micro-time shifts to TTTR files with replayable transform metadata. |
| `tttr_header_edit` | Tools:TTTR:TTTR Header Editor | Views/edits header tags of any tttrlib-readable container (PTU/HT3/SPC/HDF5, auto-detected) through a declarative view; saves the edited header as PTU (the only container that persists arbitrary tags losslessly), copying the source photon events. |
| `tttr_time_windows` | Tools:Converter:TTTR->Time-Window BIDs | Splits TTTR files into fixed-duration Burst-ID windows. Embedded in the `filetools` hub (`menu_hidden`). |
| `trace_browser` | Spectroscopy:Single-Molecule:Trace Browser | Browses folders of PTU/TTTR intensity traces, stores ratings/annotations, previews traces, and exports selections. |
| `tttr_image_browser` | Imaging:Tools:Image Browser | Browses TTTR files in a folder and previews the per-detector-window intensity mosaic. GUI is the shared `image_browser` AutoForm section over a Qt-free view-model (file list with star ratings + size, mosaic canvas with per-tile labels, editable annotations, rating filter, drag-drop) on the existing Qt-free core + RPC; exports TIFF/DOCX. |
| `tttr_count_rate_analysis` | Tools:TTTR:Count Rate Analysis | Computes per-channel count rates across many TTTR files. |
| `tttr_lut_tools` | Tools:TTTR:LUT Tools | Builds micro-time lookup tables and channel-LUT settings. |
| `microtime_histogram` | Spectroscopy:Fluorescence decay:Histogram-Microtime | Creates and inspects TTTR micro-time histograms. |
| `audifier` | Tools:TTTR:Audifier | Converts photon streams to audio with a live micro-time/lifetime waterfall preview. |

Several tools expose CLI and service entrypoints in `manifest.json`, especially
the file-transforming workflows (`alex.*`, `microtime_shift.*`,
`tttr_time_windows.*`, trace/image-browser APIs). GUI state is increasingly
data-driven through AutoForm `*.view.json` files and shared toolbox shells.

See also [compiled modules](/subsystems/compiled-modules.md), [fluorescence domain](/subsystems/fluorescence-domain.md),
and [plugin system](/architecture/plugin-system.md).

## Hub icons

Every emtk hub (TTTR Tools, File tools, Image Tools, Calculators, Wizards,
Games, Setup, Structure Tools, Trajectory Tools, Lifetime Analysis) draws each
sub-tool's pictogram in front of its name with emtk's
`im.selectable(label, selected, icon=...)`, which gives the icon a square slot
one frame high so every label starts in one column. The icon comes from
`chisurf.emtk.plugin_icons.entry_icon(entry, *refs)`: the hub entry's own
`icon` if it names one, else the child plugin's manifest `icon`, else the
package's module-level `icon` (the main menu's resolver order, read from source
without importing the child). A sidebar sized from its labels adds
`im.selectable_icon_width()`.

Traps: typed into the label instead, a colour emoji draws wider than the one
cell the layout measured and runs into the text, and U+FE0F (in `⏱️`, `✂️`, `🏷️`)
draws as a missing-glyph box — `selectable` strips presentation modifiers. A
pictogram shared by two rows of one hub defeats the point; the 2026-10-05 pass
made Image Tools (Coloc 🔗, Drift 📌, Region MLE 🧩, PSF 💠), Structure Tools
(FPS JSON 📝, Docking ⚓) and Setup (Settings 🛠️, Acquisition 🎚️, AI 🤖,
Packages 📚) distinct.

### Where to pick this up

1. **Legacy Qt hubs** (`NavigationPanelTool`, e.g. `tttr_toolbox/gui/tool.py`)
   already show the emoji in their Qt list; nothing to port, they retire with Qt.
2. **New hub**: pass `icon=entry_icon(entry, <child entrypoint or plugin path>)`
   to `im.selectable`; a test that pins "no emoji in the list" is now wrong —
   the filetools and calculator-hub tests show the replacement assertion (emoji
   only as row icons).
3. **Re-check duplicates** when adding a child: list a hub's icons with
   `entry_icon` over its registry (one line of Python) before committing.

