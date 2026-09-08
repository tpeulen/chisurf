---
id: plugins/alex-suite
title: ALEX Suite — the legacy ALEX workflow as a ChiSurf pipeline
type: plugin
status: active
tags: [burst, smfret, alex, titration, migration]
related:
  - plugins/burst-analysis
  - subsystems/burst-companions
  - architecture/declarative-analysis-definitions
---

# ALEX Suite

## Where to pick this up

0. **Arriving converts — and it has to, because Next does not.** The step is
   declared `optional`, and the shell's `process_current_step` returns early on
   an optional panel *by design* ("walking past a step must not silently change
   the analysis"). For µs-ALEX that meant **Next skipped the conversion**, and
   the burst search then ran on files whose alternation was still in the macro
   time: gates over a micro-time of zeros, every per-detector count 0, and a
   container written *per file* out of unconverted data. Reported twice from
   real use before it was found; the give-away in the log is only four seconds
   between the detection line and the burst-search warning, where a real
   conversion is 1.5 s per file plus the container write.

   So `_autorun` detects **and converts**. Two conditions keep that safe and
   both are pinned by `tests/test_arrival_converts.py`: detection refuses below
   `MIN_CONFIDENCE`, so PIE data is left alone, and `_needs_conversion` skips a
   measurement whose micro-time is already populated — folding that would
   overwrite a real micro-time with a phase, which is the one way this step can
   destroy information. **If either half is ever changed alone the trap comes
   back**: making the step non-optional would run it on PIE data from Next;
   removing the auto-run while it stays optional restores the original bug.

0a. **Superseded: "detection runs on arrival; conversion needs the button".** Reaching
   the step with files measures the instrument straight away (armed on a
   zero-timer so the panel paints first, ~1.9 s on the cal1 file) and fills in
   the period, the channel assignment and both gates for checking — it writes
   nothing. The button converts, and reuses that detection rather than repeating
   it (`_can_reuse_detection`: the gates are deliberately excluded, since they
   shape the published setup and not the fold). **Where this is still soft:** a
   re-arrival with a *different* file set re-detects, which is right, but there
   is no cache keyed on the files, so bouncing between two selections re-measures
   each time.

0a. **The alternation gates are editable now — the remaining half is the
   *period*.** Detection writes the period and both gates into spin boxes, the
   shaded bands on the plot are the same values (drag or type, they stay in
   step), and a gate change republishes the setup without reconverting, because
   the fold uses only the period. `detect_and_convert(period=...)` accepts a
   typed period, but changing it means pressing Detect again — the containers
   were folded with the old one. **Trap if you go to make that automatic:** the
   `.pto` is already written and its micro-time *is* the old phase, so honouring
   a new period means re-running the conversion from the original vendor files,
   which the panel no longer holds after step 2 replaced them with the
   containers.

0b. **The setup step's own combo does not show the detected setup's name.** The
   *tables* are filled in correctly (step 3 writes them through
   `load_data_into_tables`), and everything downstream uses the right
   definition — but the `Setup:` combo at the top of step 1 stays blank, because
   the name lives in a store the page's own selector does not read. Same root
   cause as the next item; harmless but it looks unfinished.

0c. **Detector setups have two stores and a picker sees one of them.** The RPC
   store (`detector_setups.*`, what this workflow publishes through) writes the
   settings JSON; every `SetupSelector` reads the wizard loader, which reads
   MMFDB and never falls back to that JSON. So a setup this step saves is
   invisible in every picker. Worked around here only — the alternation step's
   own picker reads a *merge* of both (`_merged_setups`), and the step writes to
   both. **Trap when you go to fix it properly:** `save_detector_setups`
   swallows an MMFDB failure and reports success (`FOREIGN KEY constraint
   failed` on a database with no user row), so a store that is rejecting writes
   is indistinguishable from an empty one. Full entry in
   [known-issues](../references/known-issues.md).

1. **The rate-vs-count defect in `.bur` is only half fixed.** The gated stream
   columns now come in two flavours — `S {window} {detector} (kHz)` and
   `… (photons)` — and every reader that goes through
   `chisurf.core.fluorescence.burst.table.guess_columns` prefers the counts. But
   **ndX's shipped MFD equations still read the kHz columns**
   (`modules/ndxplorer/ndxplorer/settings/mfd.equations.yaml`: `Sg`, `Sr`,
   `Sg(PIE)`, `Sr(PIE)`, `Sy(PIE)`), so ndX's `Proximity ratio` and
   `Stoichiometry (PIE)` still carry the bias. **Measure it before changing
   anything**: `count_rate_khz` in `_span_features`
   (`chisurf/core/fio/fluorescence/burst.py`) divides each stream's photons by
   *that stream's own span*, so the four rates of one burst have four different
   denominators. Switching the equations to the `(photons)` columns changes every
   existing ndX session's numbers — that is why it was not done here.
   Trap: an old `.bur` has no `(photons)` column at all, so the equations cannot
   simply be swapped; they need a fallback or a re-run.
2. **Container run paths are accepted by four tools, rejected by four more.**
   A burst search over a `.pto` writes no folder — its output is
   `m000.pto/sliding_window_All 0.1500#60`, which `is_dir()` answers `False`
   for. Fixed here: `burst_browser.load_folder`, `burst_bva._set_folder`,
   `chisurf.core.fluorescence.burst.table.read_burst_table`, and the workflow
   shell's own `analysis_path()`. **Still silent:** `burst_2cde`
   (`gui/tool.py:270,299`), `burst_h2mm` (`gui/tool.py:852`),
   `burst_fcs_correlator` (`gui/tool.py:301`), `burst_fusion`
   (`gui/view_model.py:255`). The pattern is one line —
   `p.is_dir() or burst_tree.is_container_path(p)` — but each needs its own
   read path checked, because rejecting the path is not the whole bug: the
   *reader* behind it must handle a container too.
3. **The alternation step converts, it does not gate.** It refuses below
   `MIN_CONFIDENCE` (50×), which catches continuous-wave data. It does **not**
   catch a file whose donor/acceptor channels are swapped: the contrast is just
   as high, the windows come back swapped, and the analysis proceeds with *E*
   reflected about ½. The check is the plot and the donor-only population, and
   both are prose in `help.md`/`guide.json` rather than anything enforced.
4. **Not attempted:** per-population γ (the old *Populations* panel gave each
   tagged population its own γ/β). ndX plus Accurate FRET cover the common case;
   a per-population γ needs the selection to reach the calibration, which is the
   `ndxplorer/calibration_bridge.py` seam.

## What it is

The workflow of the **ALEX-Suite** program (`junk/ALEX-Suite`, enaml + a C++
`alex_tools` burst searcher), rebuilt as a ChiSurf `NavigationPanelTool`. It is a
*shell*: every step embeds a tool that already exists, and the plugin's own code
is the step order, two panels ChiSurf lacked, and one compatibility writer.

It subclasses `BurstAnalysisTool` and replaces only `PANELS`. Everything below
that — how the detector setup, the raw files and the burst folder are threaded
between steps — is the same code the PIE workflow runs, which is what makes the
**output identical**: one `.pto` per measurement with the bursts inside it and
the companions beside them ([burst companions](../subsystems/burst-companions.md)).
An analysis started here can be finished in Burst Analysis and brought back.

## The steps, and what each replaces

| step | embeds | replaces |
|---|---|---|
| 1. Setup | `DetectorWizardPage` | the channel table in *Burst Search Settings* |
| 2. Files | `BurstDataSelectionWidget` (no drop guard) | *Select Directory* + file list |
| 3. Alternation (µs-ALEX) | **new** | *Burst Search Settings → Microscope* |
| 4. Burst search | `burst_selection` | *Burst Search → APBS / DCBS* |
| 5. Background | `burst_background` | the `bkg_*` fields |
| 6. Accurate FRET | `accurate_fret` | *Accurate FRET* |
| 7. E–S histogram | ndX | *E vs S Histogram* **and** *Dataset Viewer* |

Setup first is the owner's ordering (2026-09-08: *"0. Must the Setup selection.
1. File drop."*). It also makes `_sync_channel_context` simpler than the base
class's: there the definition is inferred from whichever setup the burst search
happens to have selected, because that is the only place one is chosen; here
step 1 *is* the choice, and every other step receives it.

Step 2 runs **no drop guard**. Dropping a vendor file normally offers to embed it
in a `.pto` immediately, which here is wrong twice: a µs-ALEX measurement
converted before step 3 still has its alternation in the macro time (the
container's micro-time is empty and step 3 converts that container again), and
the embed is a synchronous 45 MB copy on the GUI thread that reads as a hang.
That is what "dropping a .sm crashes it" was.
| Burst properties | `burst_browser` | *Burst Properties* |
| Titration | **new** | *Titration* |
| BVA | `burst_bva` | the *Advanced Options* half |
| Export (ALEX-Suite CSV) | **new** | *Export* |

## The one that matters: alternation

µs-ALEX encodes the laser identity in the **macro** time; PIE encodes it in the
**micro** time. Folding the macro-time phase into the micro time
(`tttrlib.TTTR.alex_to_microtime`) makes the two the same measurement, and that
is why there is no ALEX analysis path — only a conversion at the front.

The old dialog asked for seven numbers. All seven are in the data:

- **period** — `detect_alex_period` (in `ptu_alex_creator/core`, beside
  `auto_alex_windows`): bin the *signed* donor-minus-acceptor stream, take the
  spectral peak, then finish on an integer scan of the folded modulation. The
  integer matters: one macro-time unit out, over 10⁵ cycles, walks the phase
  across a laser window.
- **laser edges** — `auto_alex_windows`. **Not** the plateaus of the folded
  intensity, which is what it used to look for and what fails on every real
  measurement: both lasers keep the sample emitting, so there is no laser-off
  gap and the intensity is flat to within a factor of two. What alternates is
  the *detector ratio* — measured on the calibration file below: the acceptor's
  share is 0.69 in one half of the period and 0.07 in the other. The split is
  made on that, with hysteresis so the rise/fall band between the two levels
  falls in neither window (a midpoint threshold absorbed it and produced a
  window that wrapped past phase 0, which cannot be written as a micro-time
  range at all).
- **channel flip** — `detect_alex_channels`. One physical fact decides it:
  **under acceptor excitation the donor detector sees essentially nothing**,
  whatever the sample's efficiency or labelling.

### Checked against a real measurement

`~/dev/tttr-data/sm/cal1/001_60g_25r_cal1_cy3b_8_18_33bp_atto647n.sm` — a 300 s,
3.77 M photon µs-ALEX file, and the one the window detection was rewritten
against. The tests in `tests/test_alternation.py` skip when it is absent.

| | detected | ALEX-Suite was configured with |
|---|---|---|
| period | 8000 units = 100.0 µs | `alex_period = 1e-4 s`, `time_resolution = 12.5e-9` |
| green gate | 616–3784 | 240–3760 |
| red gate | 4278–7762 | 4160–7680 |
| donor | channel **1** | `channel_flip = True` |

The donor is 5 % as bright under acceptor excitation, so the assignment is not a
close call. The gates are the configured ones minus the 6 % guard trimmed at each
laser edge. End to end: 7358 bursts, and the stoichiometry histogram has the
three species it should — donor-only at S ≈ 1, acceptor-only at S ≈ 0.1, the
doubly labelled population at S ≈ 0.6.

The step writes **one** `<first stem>_alex.pto` for the whole selection —
`Measurement.create` takes a list and embeds them all, which is what `.pto` means
by a measurement split across vendor files — and publishes a detector setup named
**ALEX Suite (auto)**. One container per *file* would make six analyses of one
experiment (owner, 2026-09-08: "the pto file should include all files. no
individual files for .sm files").

### The setup's names are not free

`windows = {prompt, delayed}`, `detectors = {green, red, yellow}` — the Seidel
vocabulary that ndX's MFD equations and
`chisurf.core.fluorescence.burst.table.COLUMN_HINTS` are written against.
`red` and `yellow` are the **same physical detector entered twice**, once per
window, which is what makes a two-detector ALEX measurement readable by tools
written for a three-detector MFD setup.

Naming the windows after the colours instead (`green`/`red`) produced a burst
table whose stream columns matched nothing: the E–S step came up empty with the
burst files loaded, and Accurate FRET fell back to the un-gated detector totals.

A related trap: the burst writer intersects the window with each detector's
**own** micro-time range, so the cross product still writes an all-zero
`S delayed red`. Reading I_AA from it is not a missing column — it is every burst
at S = 1. `gated_stream_columns` prefers a *second* acceptor detector for the
acceptor window for exactly this reason.

## Titration

`api/titration.py`, Qt-free. One shared set of Gaussian centres and widths across
the whole concentration series, free amplitudes per condition, solved by
**variable projection**: the amplitudes are the non-negative least-squares
solution for any trial shape, so only the 2K shape parameters are searched.

The isotherm is read from the population that **grows** with ligand. With two
complementary populations the spans are equal and "largest change" is a coin
toss — half the time it plots the free species and labels a falling curve with a
K_d.

Validated end to end against a simulated series with a planted K_d = 50 nM:
recovered 52.1 nM, Hill 1.05, populations at E = 0.212 / 0.671 (planted 0.22 /
0.68).

## Layout

```
chisurf/plugins/burst/alex_suite/
  api/         histograms.py, titration.py, convert.py, legacy_export.py  (Qt-free)
  cli/main.py  csc alex-suite {alternation, histogram, titration}
  gui/         tool.py (the shell), alternation.py, titration*.py,
               legacy_export_panel.py, help.md, guide.json
  tests/
```

## Changed outside the plugin

- `burst_features.yaml` — a `(photons)` column beside every gated `(kHz)` one.
- `burst/table.py` — `gated_stream_columns`, and container runs in
  `read_burst_table`.
- `burst_analysis/gui/tool.py` — `PANELS`/`TITLE` class attributes so the shell
  is subclassable; `burst_sources()` / `analysis_path()`; downstream context
  application driven by what is loaded rather than a hard-coded role list.
- `burst_browser`, `burst_bva` — container run paths; the browser's E/S now come
  from the shared channel conventions instead of the un-gated detector totals.
- `chisurf/gui/__init__.py` — the plugins menu goes through
  `run_plugin_from_dir`, so a manifest-only plugin's menu entry is not dead.
