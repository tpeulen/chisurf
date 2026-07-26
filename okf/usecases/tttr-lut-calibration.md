---
type: Reference
title: Use case — TAC linearization (micro-time LUT calibration)
description: Compute a per-routing-channel TAC-linearization LUT from a flat-light measurement in the Channel Definition editor's LUT Tools, add it to the detector setup, and have every later TTTR read linearized at the staging seam.
tags: [usecase, tttr, lut, tac, calibration, detector-setup, dnl, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: TAC linearization (micro-time LUT calibration)

**Goal:** the instrument-calibration step that sits *underneath* every
micro-time-based analysis. Some TCSPC hardware (notably Becker & Hickl SPC-130)
digitises the photon arrival time on a TAC whose channels are not exactly equal
in width — **differential non-linearity (DNL)**. Left uncorrected, the distortion
propagates into every lifetime fit, every filtered-FCS filter and every PDA
micro-time gate. The user therefore measures **uniform (flat) illumination** once,
computes a **look-up table per routing channel** from it, stores the LUTs in the
detector setup, and from then on every TTTR read is linearized automatically.

This is the "Correlation / TTTR tools" coverage entry for **LUT calibration**. The
theory and the intended flow are in
`docs/guides/37_tttr_microtime_lut.md`.

**Data:** `test/data/tttr/BH/132/BH_SPC132.spc` — the repo's Becker & Hickl
SPC-130 stream, 183 657 photons, 3664 used micro-time bins at 3.2959 ps, routing
channels 0 (56 499 photons), 1 (23 038), 8 (79 468), 9 (24 652). **Caveat: this is
a fluorescence-decay measurement, not a flat-light one** — the repo ships no
uniform-illumination file. That turned out to be the most informative part of the
run (see *Observed*): it is exactly the mistake a user makes, and the tool never
says a word about it.

**Tools:** `chisurf.plugins.core.setup_channel_definition`
(*Setup:Channel Definition*, wrapping `DetectorWizardPage`) and
`chisurf.plugins.tttr.tttr_lut_tools` (*Tools:TTTR:LUT Tools*,
`TTRLutToolsWidget`). Both are `menu_hidden: true`; the editor is the entry point
and LUT Tools is opened from inside it. Reading seam:
`chisurf/core/fio/staging.py::open_tttr`; the process-global correction context is
`chisurf/core/fio/lut_context.py`.

## Steps

1. Open the **Channel Definition** editor. Pick the setup in *Setup:* (`BS`
   ships). The *TTTR Reading routine* box shows *File Type* `SPC-130`,
   *Macrotime res.* 13.5 ns, *Microtime res.* 3.2958984375 ps; the *Detectors*
   table lists `green` = `8, 0, 3`, `red` = `9, 1, 2` (µT 0:2048), `yellow` =
   `9, 1, 2` (µT 2048:4095), with *Polarization resolved* ticked.
2. Press **Read** in the *TTTR Reading routine* row and choose the calibration
   file. This is what fills the macro/micro-time resolutions from the file header
   and remembers the file for the decay preview and the shift tool.
3. Expand the **LUT handling (TAC linearization)** box at the bottom. It shows the
   master gate *Apply TAC linearization (LUT) when reading*, one row per used
   routing channel (`Channel | LUT | Shift`, LUT reading `— none —`), and three
   buttons: **📥 Assign LUT…**, **Configure LUTs…**, **Adjust shifts…**.
4. Press **Configure LUTs…** → the modal **TTTR LUT Tools** window, two docked
   tabs: **① Compute LUT** (the tool) and **② settings.tttr.json (optional)**.
   The header carries the flow text and the bold **➡ Add all channels to setup**
   button.
5. In ① drop the uniform-illumination file(s) onto *Uniform-illumination TTTR
   file(s)* (or **+ Files**). The panel loads the photons, fills *Preview channel*
   with the routing channels found, histograms the selected one into the **Raw TAC
   histogram** and shows the **After linearization (corrected preview)** below.
6. Check the orange region (the "linear plateau") on the raw histogram — drag it,
   type into *Linear start* / *Linear stop*, or press **🎯 Auto-detect region**.
   The status line under the plots reports
   `ch N | Range [start, stop) | width=… | f=… | n_mean=…`.
7. Step through every entry of *Preview channel* and repeat step 6 — TAC DNL is
   per routing channel, so each channel gets its own region and its own LUT.
8. Press **➡ Add all channels to setup**. A LUT is computed for *every* routing
   channel in the file (each with its own auto-detected region, except the
   currently selected one, which keeps its hand-tuned region) and handed to the
   editor. Saving a `.npy` LUT or a `settings.tttr.json` in tab ② is optional.
9. Close the window. The editor's LUT box now names a LUT per channel (hover for a
   thumbnail plot of it) and **Apply TAC linearization (LUT) when reading** is
   ticked automatically.
10. Optionally press **Adjust shifts…** to align the per-channel micro-time
    histograms on the LUT-corrected axis, then **💾 Save** the setup so the LUTs
    travel with it.
11. From then on every read that goes through `staging.open_tttr` — decay
    histograms, correlation, burst analysis, PDA — is linearized. Untick the gate
    to get the raw axis back.

Headless equivalent (documented in guide 37):

```bash
chisurf lut-tools compute uniform.spc -o green.npy --routine SPC-130 --channel 0
chisurf lut-tools settings --lut 0=green.npy --shift 0=3 -o settings.tttr.json
```

## Expected

- Step 5: the raw TAC histogram of a *flat-light* measurement is flat up to shot
  noise; the auto-detected plateau covers most of the illuminated axis.
- Step 6: `f` (the corrected/raw axis scale, `ntac_required / Σ widths`) is close
  to 1 and comparable across channels; `n_mean` is the plateau's mean counts/bin.
- Step 8: one LUT per routing channel, monotonically increasing from 0 to
  `ntac_required`.
- Step 9: the gate is on, every used routing channel has a LUT, and the user is
  told about any channel that will still be read raw.
- Step 11: reading the file twice gives identical micro-times (fixed dither
  seed), and the corrected decay keeps its shape — a linearization must remove
  hardware ripple, not the fluorescence decay.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real
widgets: `SetupChannelDefinitionWidget` → `read_tttr_button.click()` →
`_box_lut.set_expanded(True)` → `TTRLutToolsWidget` → the AutoForm `path_list`
widget → `bridge_btn.click()` → `_pull_luts_from_panel` → `staging.open_tttr`.
Screenshots at every step were read and compared.

**The mechanics work.** No crash anywhere in the flow. LUT Tools builds in
~0.04 s, loading the 183 657-photon file into ① takes 0.04 s, the raw and
corrected plots render with axis labels and units, per-channel LUTs are monotone
0 → 3664, LUT tooltips render a base64 thumbnail plot, `➡ Add all channels to
setup` with nothing loaded politely explains itself instead of failing, the
`get_settings` → `_load_data` round trip restores the four LUT arrays bit-exactly
and re-ticks the gate, loading a LUT-free setup clears both the LUTs and the
gate, the gate really gates (`apply_lut=False` returns the raw micro-times), two
reads of the same file are identical, and the `lut-tools` CLI group
(`compute` / `apply` / `settings`) works with the names the docs use.

**What a user actually sees is another matter.** The single most important number
in this workflow — the linear plateau — is a fabrication on 3 of the 4 routing
channels of the repo's own sample file:

- `autodetect_linear_region` **raises** for channels 0, 1 and 9 (`plateau too
  short (18 < 32)`, `(5 < 32)`, `(6 < 32)`). `LutComputeViewModel._select_channel`
  catches that and substitutes `_fallback_region()` — the middle 20 % of the
  non-empty axis — and the panel then displays `ch 0 | Range [1749, 2387) |
  width=638 | f=0.526734 | n_mean=8.12` in exactly the same way it would display
  a real detection. The shown region equals the fallback output bin-for-bin on
  all three channels. The same api call through the CLI (`lut-tools compute
  --channel 0`) **exits 1** with the error, so the GUI and the CLI disagree about
  the same file (RF-291).
- Pressing **🎯 Auto-detect region** is indistinguishable from a dead button: on
  this file it always fails, and the failure is swallowed into a `logger.info`
  with no dialog, no status change and no region change (RF-292).
- The detector's per-bin criterion (`|counts / rolling_mean − 1| ≤ 0.10`) is
  shot-noise-blind. On *perfectly flat* synthetic Poisson data it needs ~100
  counts/bin: 8 counts/bin fails, 30 counts/bin fails, and even 200 counts/bin
  returns only a 42-bin run out of 3664. It therefore only ever "succeeds" in the
  brightest part of the histogram — on channel 8 it returned `(788, 828)`, a
  40-bin window sitting **on the decay peak** (`n_mean = 353` against 5–8
  elsewhere), giving `f = 16.29` against 0.53–0.84 for the other channels
  (RF-293).
- Nothing validates the result before it goes live. `➡ Add all channels to setup`
  assigned all four LUTs without a single dialog, `_enable_apply_lut` then ticked
  the master gate with `blockSignals(True)` — bypassing the *Missing LUTs*
  question that the same checkbox raises when a human ticks it — and every later
  read is corrected. Measured through `staging.open_tttr`: channel 0's decay peak
  moves from bin 775 to bin 2843 and the bins above half maximum go from 95 to
  1362. The decay is gone, and no warning was raised at any point (RF-294).
  Channels 2 and 3 (used by the `red`/`yellow` detectors but absent from the
  calibration file) stay raw, silently, in the same polarization pair (RF-295).
- The one piece of feedback the panel *does* give is a tautology: the "After
  linearization" plot is flat **by construction** — the LUT is built to flatten
  the histogram it came from — so a perfect-looking corrected preview is exactly
  what a completely wrong LUT produces. In screenshot `Q1_ch8_selected.png` the
  orange plateau is a 40-bin sliver on the peak of a decay and the preview below
  is beautifully flat.

Two more concrete dead ends and two layout problems:

- Tab ② is unreachable from the normal flow. After `➡ Add all channels to setup`
  the *Channels* list is empty, *Shift* is disabled and **Save JSON** is greyed
  out even though `channel_luts` holds `[0, 1, 8, 9]` — `receive_computed_lut`
  fills `channel_luts`/`loaded_luts` but never `channel_list`, and the save
  button is only enabled by loading TTTR files *into tab ②*. The advertised
  "optional" export therefore cannot be reached after computing (RF-296).
- Tab ②'s buttons render as fragments at 1148 × 776: `+ ...es`, `...er`, `...se`,
  `— ...ve`, `...ar` for Files/Folder/Database/Remove/Clear, and `Sho...SON` for
  Show JSON (RF-297).
- The editor's LUT table is capped at 160 px (4 whole 30 px rows in a 134 px
  viewport), so with the default setup's 6 routing channels the rows for channels
  8 and 9 are clipped behind a scrollbar — while the *Detectors* table directly
  above keeps ~120 px of blank space (RF-298).
- The docs' headless example omits `--channel`, and without it `lut-tools
  compute` pools **all** routing channels into one LUT (region `[769, 877)`) —
  the very thing the same page says is wrong, since DNL is per channel (RF-299).

Smaller things seen while driving: pressing **Read** on a 183 657-photon file
changed nothing visible in the panel (the resolutions already matched the stored
setup) and produced no confirmation at all — while the page's own help text
promises "*Use 'Read from file…' to load a dataset: the preview below shows the
micro-time decay*", a button labelled *Read* and a preview that lives behind the
separate **📊 Plot** button. `Adjust shifts…` opens and plots all four channels on
the corrected axis, but with flattening LUTs active all four traces are flat, so
the rising edges it exists to align are not there. Tab ②'s empty plot shows
invented axes (0.2 – 0.8, "Counts (log)" 2 – 9) before any file is loaded.

Screenshots: `01_channel_definition_editor.png`, `02_after_read_calibration.png`,
`03_lut_box_expanded.png`, `05_lut_tools_loaded.png`, `Q1_ch8_selected.png`,
`Q2_tab2.png`, `Q4_editor_lut_box.png`, `R1_roundtrip.png`,
`R5_shift_dialog.png` (session scratch, not committed).

## UX / UI suggestions

- **Say when the region is a guess.** The status line should distinguish
  "detected" from "fallback (no plateau found)", and colour the region marker
  differently. Right now a fabricated region and a measured one look identical.
- **Replace the tautological preview with a validity read-out.** Useful numbers:
  plateau width as a fraction of the illuminated axis, `f` per channel with an
  outlier flag, and a flatness/χ² statistic of the *reference* histogram against
  a constant. A one-line verdict ("this file is not flat — 40 of 3664 bins used")
  would have caught everything seen in this run.
- **Rename *Preview channel* to *Routing channel*** (guide 37 already calls it
  that). It is not a preview-only control: the selected channel is the one whose
  hand-tuned region survives `Add all channels to setup`.
- **Label the marker lines.** The red vertical (Noffset) and green horizontal
  (low-count threshold) lines in the raw plot carry no legend or label.
- **Let *Noffset* reach Auto-detect.** `autodetect_linear_region` takes a
  `noffset_guess` and the `lut.autodetect_region` RPC exposes it, but all three
  GUI call sites omit it, so raising *Noffset* to skip the early axis leaves the
  detected region unchanged.
- **Give the LUT box a way to remove a LUT.** The only actions are *Assign LUT…*,
  *Configure LUTs…* and *Adjust shifts…*; once a channel has a LUT the user can
  only switch the global gate off.
- **One wording for the bridge button.** The button says "➡ Add all channels to
  setup"; the status bar, the panel tooltip and guide 37 say "➡ Add to Detector
  setup".
- **Confirm the calibration read.** *Read* should report what it loaded (photons,
  channels, bins) and show the decay inline, or the help text should stop
  promising a preview that is behind another button.
- **Show raw *and* corrected in *Adjust shifts…*** so the alignment edges remain
  visible when a flattening LUT is active.
- **Stop embedding LUTs as JSON float lists.** One setup with four 3664-entry
  LUTs serialises to 361 kB of JSON; store them rounded, compressed, or as
  referenced artifacts.

## Bugs filed

- RF-291 — a failed plateau detection is silently replaced by a geometric guess
  and presented as a detection (GUI ≠ CLI on the same file).
- RF-292 — **🎯 Auto-detect region** does nothing and says nothing on failure.
- RF-293 — the plateau criterion is shot-noise-blind, so it rejects real flat
  data and "detects" plateaus on decay peaks.
- RF-294 — `Add all channels to setup` + auto-enabled gate put an unvalidated
  correction on every subsequent read, with no plausibility check and no warning.
- RF-295 — auto-enabling the gate bypasses the *Missing LUTs* warning, so
  channels that stay raw are never mentioned.
- RF-296 — after the normal flow tab ② shows no channels and a disabled
  *Save JSON*, making the advertised settings export unreachable.
- RF-297 — tab ②'s file-list and JSON buttons render as elided fragments.
- RF-298 — the editor's LUT table clips rows while the table above it has empty
  space.
- RF-299 — the documented headless example omits `--channel` and produces a
  channel-pooled LUT.

## See also

- `docs/guides/37_tttr_microtime_lut.md` — TAC linearization: microtime LUTs.
- [TTTR micro-time histogram](/usecases/tttr-microtime-histogram.md) — the first
  consumer of a linearized axis.
- [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) — the fit the correction
  is ultimately for.
- [TTTR subsystem](/plugins/tttr.md)
