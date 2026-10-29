---
type: Subsystem
title: Excitation windows (PIE / µs-ALEX) detected from the data and checked everywhere
description: One Qt-free detection of the excitation pulses (micro time) and the µs-ALEX alternation (macro time), one check of a setup's windows against it, and the places that call it -- the Excitation Windows plugin, the setup editor's Auto-detect, Record during a run, burst selection before a search.
resource: chisurf/core/fluorescence/excitation/
tags: [smfret, pie, alex, setup, record, burst, windows]
timestamp: '2026-10-29T00:00:00Z'
---

# Where to pick this up

1. **Wire the remaining window consumers to the pre-flight.** Done: Record (live), the setup
   editor (Auto-detect), burst selection (preview + every searched file's `warnings`), fret_check
   (its own detection, via the shared `rising_edges`), the ALEX Creator / ALEX Suite (their
   detection *is* `excitation.alex`). Not yet: `burst_fusion` (`core/fusion.py` reads
   `windows`), `bid_to_analysis`, `tttr_count_rate_analysis`, `tttr_image_browser`, `img_frc`,
   `mfd_prepare` and the PDA input path (`core/experiments/pda2c/inputs.py`). Each needs only
   `windows_message(windows_preflight(tttr, windows, detectors=..., tttr_reading=...))` added to
   its warnings -- the measurement is open there already. 2CDE/BVA consume burst tables, not
   windows: they inherit the burst selection's warning.
2. **µs-ALEX in Record.** The live check reads the analyzer's micro-time decays only; for the
   `alex` preset it is skipped (the alternation is in the macro time, which the snapshot does not
   carry). A per-phase count histogram from the analyzer would let `detect_alex_windows` run live.
3. **Unit inconsistency in `from_setup`** (tttrlib `modules/streaming/include/Streaming.i:367` and
   the stand-in `acq/live/analyzer.py`): `tttr_reading.micro_time_resolution` is multiplied by
   1e-9 (ns) while the setup editor writes it in **ps**. Harmless in Record (it passes the
   resolution explicitly), wrong for any caller that relies on the setup -- recorded in
   [known issues](../references/known-issues.md).
4. **Detector micro-time ranges** (`detectors.*.micro_time_ranges`) are channel numbers of the
   same kind and are neither converted nor checked yet; `convert_setup_windows` is the place.

Measurements to re-derive: `pytest test/fluorescence/test_excitation_windows.py` (synthetic PIE at
8–49 ps, 1024–6250 channels, a pulse straddling the range end, donor-only, noise, the MT200 case,
tttrlib-simulated PIE/MFD, the `.sm` µs-ALEX stream); `csc windows check <demo.ptu> --setup <SPC-130
setup>` exits 1. Trap: `detect_alex_period` on a stream that does not alternate used to scan
hundreds of aliases (minutes on 5 s of cw data) -- `min_confidence` stops it after the spectrum,
and `detect_alex_windows` searches only 2 µs–2 ms periods because slow burst/diffusion drift gives
cw data a spectral "line" of contrast > 2000 at ~90 ms.

# What it is

`chisurf/core/fluorescence/excitation/` (Qt-free):

* `pie.py` -- `detect_pie_windows(histograms, resolution_s)`: rising edges per detector and in
  their sum on ~256 circular coarse bins (≥ 15 % of the range, held two bins, 5 Poisson σ),
  refined at full resolution; windows tile the period from 0.3 ns before each rise; roles from
  which detectors are dark (< 15 %) under each pulse; `pie` / `single` / `unclear`.
* `alex.py` -- moved from `ptu_alex_creator/core` (period, channels, windows, regions, masks);
  the plugin re-exports it.
* `measure.py` -- `detect_windows(tttr|path)` (PIE, else µs-ALEX), `check_setup`,
  `histograms_from_tttr`, `setup_window_resolution_s`.
* `check.py` -- `check_windows`: resolution mismatch (converted), outside range, no windows,
  pulse uncovered, boundary cuts a pulse, window mixes pulses, swapped, empty; severity and a
  proposal, never applied.
* `preflight.py` -- `windows_preflight` / `windows_message`: what an analysis calls.
* `result.py` -- `ExcitationWindows` (one shape for both schemes, `rescaled`, `windows_ns`,
  `setup_patch`), `WindowCheck`, `rescale_windows`.

Callers: plugin `chisurf/plugins/core/excitation_windows/` (API, RPC `excitation_windows.detect`
/ `.check`, `csc windows`, emtk tool); the shared review panel
`chisurf/emtk/excitation_windows.py` + `.view.json` (tool, setup editor, Record's *From a
measurement…*); Record `acq/live/window_check.py` + `acq/gui/record_windows.py`;
`burst_selection` `api/selection.py` and `gui/model.py`; `fret_check/detect.py` (edge search).

# Root cause it fixed

Record on an MT200 (HydraHarp, 32 ps, 3125 channels per 100 ns) with an SPC-130 setup (50 ps,
prompt 0–2048 / delayed 2048–4095): (1) the setup's raw channel numbers were applied unconverted
-- now `convert_setup_windows` maps them through `tttr_reading.micro_time_resolution`; (2) the
Decays dock plotted its 1024-bin decay against **bin index** while windows are in **channels**
(off by `n_micro / 1024`) -- now the x axis is channels; (3) nothing compared windows and pulses
-- now the live check does.

Docs: [concept](../../docs/concepts/excitation_windows.md),
[guide](../../docs/guides/115_excitation_windows.md).
