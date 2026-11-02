---
type: Subsystem
title: Excitation windows (PIE / µs-ALEX) detected from the data and checked everywhere
description: One Qt-free detection of the excitation pulses (micro time) and the µs-ALEX alternation (macro time), one check of a setup's windows against it, and the places that call it -- the Excitation Windows plugin, the setup editor's Auto-detect, Record during a run, burst selection before a search.
resource: chisurf/core/fluorescence/excitation/
tags: [smfret, pie, alex, setup, record, burst, windows]
timestamp: '2026-10-29T12:00:00Z'
---

# Where to pick this up

Layering (owner: "respect the software dependency chain"): **tttrlib** reads a detector setup
(`ext/python/ChannelSetup.py`: `setup_detectors`, `setup_gates`, `setup_windows`,
`setup_micro_time_resolution` (ps, or `micro_time_resolution_unit`), `setup_macro_time_resolution`,
`setup_channel_map`, `rescale_micro_time_ranges`, `ranges_to_inclusive` / `ranges_from_inclusive`,
`micro_time_mask`, `polarization_channels`) and its `from_setup` uses it; `TTTRMask.select_microtime_ranges`
is half-open now (it dropped the first channel of every range). **chisurf core** (`excitation/`)
keeps what only ChiSurf uses: PIE pulse detection, ALEX detection, the check, the pre-flight and its
mixin, `gate_check` / `remembered_gate_check`, `merge_gates`, `format_ranges`; the PIE demo is
`core/fluorescence/simulation/pie_demo.py`. ndXplorer reads `.bur` columns, never setups or photons'
windows -- nothing to move for it. Pulse/ALEX detection stays in chisurf core because neither tttrlib
nor ndXplorer needs it; it moves to tttrlib C++ the day one of them does.

Open front:

1. **The arm64 env runs tttrlib 2634e77b7 + 0fe7061ef** (installed with `pip install --no-deps
   --no-build-isolation .`, `CMAKE_ARGS=-DTTTRLIB_LTO=OFF`; a pythoncode-only change needs
   `touch ext/python/tttrlib.i` or the cached `build/cp312-*` skips SWIG). chisurf now *requires*
   these tttrlib symbols; `pixi.lock` must move with the next tttrlib pin (see the "code ahead of
   the pins" known issue).
2. **Tools apply windows as raw channels, ignoring the setup's channel width.** Only Record converts
   (`convert_setup_windows`). Making the others convert is a behaviour change -- decide, then do it
   once (a `tttrlib` "setup in data channels" helper). [known issues](../references/known-issues.md).
3. **Not equivalent, so not merged:** `fret_check._find_alternation` (64 coarse bins, donor-dark rule,
   folded µsALEX without an acceptor rise) vs `detect_pie_windows`; `alex_suite.detect_and_convert`
   (user period/channels, folded TTTR for the plot, its own refusal message) vs `detect_alex_windows`;
   fusion `_detector_definition` vs mfd_prepare `_recorded_windows` (different source choice/raise).
4. **`NamedWorkspaceInput` lives in `plugins/tttr/workspace_io`** and is imported across plugins; the
   review panel now builds its input from the core contract (`chisurf.emtk.excitation_windows.WorkspaceInputSection`).
   The other plugins should move to it and the tttr helper be deleted.
5. **2CDE's window passes empty ranges** (ALEX-2CDE cannot separate excitations on PIE data); the
   `burst_background` plugin does not pass `warnings=`; PDA's two-colour form shows windows it never
   applies; the image browser keeps an ungated detector as a blank tile (`ungated_means_all`).
6. **Live µs-ALEX** checks the first 2 M photons only.

Measurements to re-derive: `pytest test/fluorescence/test_excitation_windows.py` plus every
`*/test_window_preflight.py` (`find chisurf test -name test_window_preflight.py -o -name
'test_*_window_preflight.py'`); `csc windows check <demo.ptu> --setup <SPC-130 setup>` exits 1.
Traps: `detect_alex_period` on a stream that does not alternate used to scan hundreds of aliases
(minutes) -- `min_confidence` stops it, and `detect_alex_windows` searches 2 µs–2 ms only because
cw burst drift gives a spectral "line" of contrast > 2000 at ~90 ms. The gate rule is "a gate that
holds **none** of the pulses its detector sees" -- the stricter "misses any pulse" flagged BVA's
prompt-gated acceptor and the `R|G`/`R|R` split (tried, reverted 2026-10-29). A tttrlib built in
`build/dev` is shadowed by the editable finder in the arm64 env: drop it from `sys.meta_path` to
test the build.

# What it is

`chisurf/core/fluorescence/excitation/` (Qt-free):

* `pie.py` -- `detect_pie_windows(histograms, resolution_s)`: rising edges per detector and in
  their sum on ~256 circular coarse bins (≥ 15 % of the range, held two bins, 5 Poisson σ),
  refined at full resolution; windows tile the period from 0.3 ns before each rise; roles from
  which detectors are dark (< 15 %) under each pulse; `pie` / `single` / `unclear`.
* `alex.py` -- moved from `ptu_alex_creator/core` (period, channels, windows, regions, masks);
  every caller imports it from core.
* `measure.py` -- `detect_windows(tttr|path)` (PIE, else µs-ALEX), `check_setup`,
  `histograms_from_tttr`; setup reading is tttrlib's.
* `setup.py` -- `gate_setup`, `gate_check`, `remembered_gate_check`, `GATE_CODES`, `merge_gates`,
  `format_ranges`.
* `check.py` -- `check_windows`: resolution mismatch (converted), outside range, no windows,
  pulse uncovered, boundary cuts a pulse, window mixes pulses, swapped, empty, ALEX period;
  detector gates (beyond the data, holding none of the detector's pulses, nearly empty; sibling
  detectors on one channel understood); severity and a proposal (windows + gates), never applied.
* `preflight.py` -- `windows_preflight` / `windows_message` / `apply_check` and
  `WindowsPreflightMixin`: what an analysis or a tool model calls.
* `result.py` -- `ExcitationWindows` (one shape for both schemes, `rescaled`, `windows_ns`,
  `setup_patch`), `WindowCheck`.
* `core/fluorescence/burst/streams.py` -- the burst engines' streams as a setup and their pre-flight
  (BVA, 2CDE, H2MM, workflow, background, MFD prepare).

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
