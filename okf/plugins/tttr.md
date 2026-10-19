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

**No TTTR hub (2026-10-19).** The former `tttr_toolbox` meta plugin ("TTTR Tools")
was removed: in the emtk shell every tool is its own dock, so a window listing
five tools added nothing. ALEX Creator, Audifier, Count Rate Analysis,
Microtime Shifter and Photon Table are plain buttons of **Tools › Photon data**
(alphabetical, like every other group). The one thing the hub owned was a
shared **0. Setup** step for Count Rate Analysis and Audifier; both always
embedded their own `ChannelDefinitionWidget` when not hosted, and a setup saved
there by name lands in the setup library every tool reads, so nothing was lost.
The hub's help text (the two clocks, "keep the originals", "re-check the IRF")
lives in the concept `docs/concepts/tttr_stream_tools.md` and guide
`docs/guides/101_photon_data_tools.md`; each tool keeps its own `?` and Guide.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `ptu_alex_creator` | Tools:Photon data:ALEX Creator | Converts macro-time ALEX modulation into micro-time / PIE-style files; supports single, batch, and merged output plus histogram inspection. |
| `tttr_microtime_shifter` | Tools:Photon data:Microtime Shifter | Applies global and per-channel micro-time shifts to TTTR files with replayable transform metadata. |
| `tttr_header_edit` | File:Data:TTTR Header editor | Views/edits header tags of any tttrlib-readable container (PTU/HT3/SPC/HDF5, auto-detected) through a declarative view; saves the edited header as PTU (the only container that persists arbitrary tags losslessly), copying the source photon events. |
| `tttr_time_windows` | File:Data:TTTR→Time-Window BIDs | Splits TTTR files into fixed-duration Burst-ID windows. Own window in File › Data; keeps its options between sessions. |
| `trace_browser` | Spectroscopy:Single-Molecule:Trace Browser | Browses folders of PTU/TTTR intensity traces, stores ratings/annotations, previews traces, and exports selections. |
| `tttr_image_browser` | Imaging:Tools:Image Browser | Browses TTTR files in a folder and previews the per-detector-window intensity mosaic. GUI is the shared `image_browser` AutoForm section over a Qt-free view-model (file list with star ratings + size, mosaic canvas with per-tile labels, editable annotations, rating filter, drag-drop) on the existing Qt-free core + RPC; exports TIFF/DOCX. |
| `tttr_count_rate_analysis` | Tools:Photon data:Count Rate Analysis | Computes per-channel count rates across many TTTR files; carries its own detector editor. |
| `tttr_lut_tools` | Tools:TTTR:LUT Tools | Builds micro-time lookup tables and channel-LUT settings. |
| `microtime_histogram` | Spectroscopy:Fluorescence decay:Histogram-Microtime | Creates and inspects TTTR micro-time histograms. |
| `audifier` | Tools:Photon data:Audifier | Converts photon streams to audio with a live micro-time/lifetime waterfall preview; carries its own detector editor. |
| `photon_table` | Tools:Photon data:Photon Table | Lists the records of a TTTR file (routing channel, micro time, macro time) with a channel filter. |

Several tools expose CLI and service entrypoints in `manifest.json`, especially
the file-transforming workflows (`alex.*`, `microtime_shift.*`,
`tttr_time_windows.*`, trace/image-browser APIs). GUI state is increasingly
data-driven through AutoForm `*.view.json` files and shared toolbox shells.

See also [compiled modules](/subsystems/compiled-modules.md), [fluorescence domain](/subsystems/fluorescence-domain.md),
and [plugin system](/architecture/plugin-system.md).

## Hub icons

Every emtk hub (Image Tools, Calculators, Wizards, Games, Setup,
Trajectory Tools) draws each
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

1. Open: **New hub**: pass `icon=entry_icon(entry, <child entrypoint or plugin path>)`
   to `im.selectable`; a test that pins "no emoji in the list" is now wrong —
   the calculator-hub tests show the replacement assertion (emoji
   only as row icons).
2. Open: **Re-check duplicates** when adding a child: list a hub's icons with
   `entry_icon` over its registry (one line of Python) before committing.

## Where to pick this up — cancellable native trace fitting (2026-10-07)

HMM/BIC workers now propagate a cooperative callback through GaussianHMM
EM/SQUAREM maps and the state-count scan; CancelledError is never converted
to a failed-fit NaN. The real toolbar Cancel was clicked through Driver with
the 10,001-bin demo loaded. Previous completed outputs are retained and a
cancelled fit does not export. Before/busy-after/cancelled PNGs were inspected;
EM/SQUAREM parameters/states and likelihood/BIC match the captured baseline.
47 targeted regressions plus the legacy numerical oracle pass. The two old
pointer cases require the matching rebuilt IMP.bff FitResidualFunction provider
to recover dwell-fit tau labels; this is a provider-root issue, not cancellation.
Continue PRD-154's guarded e2e acceptance after that provider is installed.


## Native microtime histogram retirement — 2026-10-07

The public CLI/manifest and remaining lifetime panel now use the existing native AutoForm histogram app; wizard.py/UI and its old Qt reference are retired. Immutable measured arrays/fullsettings replace recomputing the deleted legacy widget. Five print-only scripts retire while the independent fortune assertion remains unchanged. The saved BID setup publisher synchronizes the editor before replacing the completed model; switching polarization merges/splits the current ordered routes and retains explicit timing/G/shifts/manual channels. Scientific model and package initializer bytes/modes remain unchanged.

The plugin supplies a synthetic PTU Demo (3000VV/1500VH,32ps micro/25ns macro clocks,4-bin/.128ns FWHM) and real Guide awaits Demo then Compute. Current native defaults/scientific outputs preserve provider timing; the headerless BH3.2958984375ps is not independent instrument calibration and explicit25ps is validation only. Three polarized measured exports match the legacy bytes. Unpolarized output corrects the extra-all-source-VH bug:135967selected/4096rows rather than319624/8192. All17 final images were inspected, including legacy-host and complete detector controls; paired docs and3realfigures accompany the source.

Parent112 targeted cases pass in three isolated normal-exit groups; scoped Ruff14/mypy6 are clean. The actual policy guard identified one stale Qt GUI allowance after entrypoint retirement; removing only that line makes all285 policy cases pass/16expectedskips, with other available guard files already green. No allowance or skip added. [Acceptance](../validation/release-readiness-w1/microtime-retirement/acceptance.json). W1 next is ordered Burst13, then Channel14 and shared Designer helper cleanup.

## ALEX Creator automatic excitation regions — 2026-10-09

Loading detects all resolved phase candidates at the configured instrument
period using every routing channel. Three-color and higher phase counts are
supported; candidates retain neutral names, editable circular bounds, detector
grouping and explicit transition/heterogeneity warnings. Review and overlays do
not filter photons or assign laser identities. Histogram and export remain usable
when detection is inconclusive. Generic unknown-period inference remains absent.

TTTRlib `c783fe00a` fixes integer `(macro - shift) % period` across uint64
macro times and signed shifts, and preserves high bits in the bulk getter.
Both test and arm64 providers rebuilt; 33 independent native regressions pass.
Single/batch/merge preserve the conversion contract and reject output phase
truncation before writing. A copied output header keeps loaded metadata intact.
[Scientific assumptions](../../docs/concepts/us_alex.md) and
[workflow](../../docs/guides/100_alex_creator.md) describe multiple phases and
record capacity. [Current integration state](../validation/release-readiness-w6g/current-job.md).

## Photon Table lists every record, markers by kind (2026-10-13)

`photon_table` lists **every** record of a TTTR file, not only photons: each row
carries a *kind* (photon, pixel, line start, line stop, frame, other marker),
the marker kinds coloured in the Kind cell, with a Kind filter beside Channel
and a per-kind count line in the summary. The kinds are tttrlib's answer
(`CLSMImage.get_record_kinds`, tttrlib `54422de06`): a file whose header
describes an image scan (`CLSMImageInfo.from_header(...).is_valid()` or a
`BH_SPC_ReadingRoutine` tag) is classified by a pixel-less `CLSMImage`, so a
record is a line marker exactly when image reconstruction treats it as one;
any other file has unnamed markers (`classify_records_events` with empty
settings → *other*). Names, codes and colours are declared once in
`photon_table/core/record_kinds.yaml`; a colour is a category of the shell's
vocabulary (`chisurf/emtk/task_colors.yaml`, same fill in both themes, ink
picked for contrast by the emtk table's `background` column map, filled in by
`gui/app.py:kind_backgrounds`). There is no overflow kind: tttrlib folds
overflow records into the macro times. Docs: guide 108, `gui/help.md`.

### Where to pick this up

1. Open: **tttrlib rebuild is required for names.** Until the env's tttrlib is at or
   past `54422de06`, `classify_records` warns (`RuntimeWarning` naming the
   missing `CLSMImage.classify_records_events`) and lists every marker as
   *other*; the scan tests skip. Measure: `python -c "import tttrlib;
   print(hasattr(tttrlib.CLSMImage,'get_record_kinds'))"`. Trap: the arm64
   env imports tttrlib through an editable `ScikitBuildRedirectingFinder`, so
   `PYTHONPATH=<scratch build>` does **not** override it — drop that finder from
   `sys.meta_path` first (what the session's dev-build runs did).
2. Open: **Header semantics, not routine guesses.** Leica SP5 PTU
   (`test/data/clsm/Leica_SP5.ptu`): the header names frame 4, line 1/2, so the
   210 records on channel 6 (the SP5 routine's second frame channel) are
   *other marker*. Only an explicit `reading_routine='SP5'` would call them
   frames; the table deliberately has no routine picker. Add one only if a user
   needs SP5 conventions on a header that lacks them.
3. Open: **Narrow windows.** Six columns at 500 px scroll sideways (Macro time has
   `min_width` 84 so its value never elides). `Record` declares
   `collapse_order: 1`; it drops first once the installed emtk carries the
   column-collapse work (emtk 9bdd67a) — re-render at 500×500 after the arm64
   emtk sync.
4. Measure: parity baseline: BH_SPC132 (no markers) still matches the recorded Qt tool
   word for word except the deliberate renames listed in the parity test's
   docstring (`Record`, `First record`, `records 0–200`, the Kind column/filter).
