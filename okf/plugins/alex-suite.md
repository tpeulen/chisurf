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
| 1. Files | `BurstDataSelectionWidget` | *Select Directory* + file list |
| 2. Alternation (µs-ALEX) | **new** | *Burst Search Settings → Microscope* |
| 3. Burst search | `burst_selection` | *Burst Search → APBS / DCBS* |
| 4. Background | `burst_background` | the `bkg_*` fields |
| 5. Accurate FRET | `accurate_fret` | *Accurate FRET* |
| 6. E–S histogram | ndX | *E vs S Histogram* **and** *Dataset Viewer* |
| Burst properties | `burst_browser` | *Burst Properties* |
| Titration | **new** | *Titration* |
| BVA, Trace viewer | `burst_bva`, `trace_browser` | the *Advanced Options* half |
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
- **laser edges** — `auto_alex_windows`, the two plateaus of the folded phase.
- **channel flip** — which plateau the donor detector is brighter in.

The step then writes `<stem>_alex.pto` per file and publishes a detector setup
named **ALEX Suite (auto)**.

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
