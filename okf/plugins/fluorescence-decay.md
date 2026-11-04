---
type: Plugin Group
title: Fluorescence decay
description: TCSPC fluorescence-lifetime plugins for decay analysis, blind IRF estimation, maximum-entropy lifetime/distance distributions and time-resolved anisotropy.
resource: chisurf/plugins/fluorescence_decay/
tags: [plugins, tcspc]
timestamp: '2026-07-05T00:00:00Z'
---

## Where to pick this up

**Burst MLE's IRF "for dummies" and the tuned IRF coming back (2026-11-04).** Owner: "by default
use the irf extraction tool. when click irf tool, computed irf must be feed back. rm ctrl from
IRF in MLE, just leave selector" and "extract irf from ref dyes by default". Burst MLE's IRF tab is
one radio selector **IRF from** (Auto / IRF measurement / Reference dye / Outside the bursts /
Estimate from the data, plus "IRF tool (tuned)" once one came back), greyed per source by emtk
0.1.44's `enabled_source` / `descriptions_source`; a one-word status (details in its tooltip), the
plot, **IRF tool**. Gone from MLE: Measured IRF input (pipeline: the IRF/BG files tab is hidden;
standalone keeps it), IRF model, VH shift, IRF start/stop, background levels, Use the estimate, the
IRF-range drag lines (the fit still subtracts 0.02 and Opt still searches the shifts). Engine:
`MleSession.irf_choice` / `irf_candidates` / `apply_irf_choice` / `choose_irf` / `take_tuned_irf` /
`irf_options`; Auto follows the tool's `extraction.AUTO_ORDER` (reference dye, scatter, non-burst,
blind; `best_irf` ranks by it). Round trip: the payload carries `reply`; the tool sends every
estimate the user makes (not the one on opening) back, MLE takes it on its next frame
(`_take_tuned`), refits, and picking another source asks once (`irf_confirm`). The IRF tool opens
Simple (Source + Estimate), **Advanced** button for every setting. Test:
`test_irf_from_the_irf_tool.py::test_an_irf_tuned_in_the_irf_tool_comes_back_and_is_fitted`.

**IRF time shift calibrated against a reference dye (2026-11-04).** Owner: "before fitting, optimize
the time shifts; a reference dye at single-molecule conditions is the reference, otherwise the
reference dyes; lifetimes of ref dyes ideally known." `extraction.calibrate_shifts` fits the dye's
decay with the IRF (polarised kernel, amplitude + flat background per polarisation, Poisson
deviance, quarter-bin grid + golden section), shifts VV/VH free, lifetime fixed (fitted when
unknown). `MleSession.calibrate_shift` runs after every IRF choice (`apply_irf_choice`), prefers
records with `single_molecule()` (1 ms bins: median < 0.2 x p99.5) because SPAD timing moves with
the count rate (owner; stated as the instrument's behaviour, no citation at hand), records the
reference's and the bursts' count rates (`burst_count_rate_khz`) and warns (status ⚠, tooltip,
report `warning`) for a bulk reference above 3x the bursts' rate; sets the detector's `shift_sp`
/ `shift_ss`; Opt refines them within +-0.5 bin; the IRF tool's Advanced Shift VV/VH go back as
`shift_override`. Lifetimes: MMFDB `reference_diffusion.json` gained `tau_ns` / `tau_solvent` /
`tau_sources` (mmfdb ea052d6, stored as probe property `tau_fl`), recopied into
`chisurf/core/fluorescence/reference_diffusion.json`; `reference_dyes.yaml` lost its own tau
column, `reference_files.dye_lifetime` reads the database. Report: `calibration_report.build_report(
irf_shift=...)` (hub `_update_report`, MLE `on_calibrated`). Measured: injected 1.25 / -2.5 bins
recovered within 0.06 bins (tau fixed), 0.05 with tau fitted (3.98 for 4.0); demo scatter vs Rh110
within 0.4 bins of 0. Open: (a) Data Selection has no "single-molecule" tag for a reference row --
the flag is inferred from the photon stream only; (b) Cy5, Alexa 488, Rh B have no lifetime in the
database yet (no source at hand) -- they are fitted; (c) the integer VH shift (`shift`, data and IRF
together) is not calibrated, only the IRF's sub-bin shifts against the dye.

**One IRF extraction tool (2026-11-04).** Owner: "IRF extraction not good. Use the logic of the IRF
extraction tool. Do not duplicate: a single IRF extraction tool/plugin that is used." `irf_estimator`
is that tool: `core/extraction.py` holds every IRF source -- scatter (`irf_from_scatter`), reference
dye (`irf_from_reference`: Richardson-Lucy with the polarised kernel (1+2r)e^-t/tau | (1-r)e^-t/tau,
tau from the tail of VV+2VH, rho from the two polarisations (`reference_rotation`), triangle-binned
kernel, stop at chi2r <= 1 or stagnation, significance gate, area = floor-free counts x (1-e^-dt/tau)),
non-burst prompt (`irf_from_prompt`, `gaussian_prompt` moved here), blind (`irf_from_decay`) and
`best_irf`. Deleted duplicates: `tcspc/irf.py` scatter/reference/tail functions, `burst/irf_bg.gaussian_prompt`,
the MLE engine's own reconvolution and blind code. Callers: Burst MLE (`irf_pattern`, `blind_irf`,
non-burst via `extract_mle_irf_background`, which only selects/histograms), Burst IRF & Background
(display = the MLE pattern), `mfd/fit.py`. The window: **Source** (Blind / Reference dye / Scatter /
Non-burst), VV | VH halves, lifetime / listed / rho; hand-off `irf_source` (`receive_irf_source`),
reached from Burst MLE's **IRF tool** button with `MleSession.irf_inputs`. Measured (scratch
prototype `20261104_05_before_after.py` pattern, docs/concepts/irf_extraction.md): simulated Rh110,
realistic IRF, 80 ps: TV 0.16 -> 0.03, a 2.5 ns sample 2.63 -> 2.50 ns (VV); Burst Analysis demo
(narrow Gaussian, 64 ps): VH 0.26 -> 0.07, VV 0.05 -> 0.10 (the exact difference's best case).
DNA13bp_3 G|G with Rh110: smooth IRF, 2I* 20.93 -> 20.91, chi2r 29.1 -> 27.9. Open: (a) a narrow
(~3-bin) IRF still comes out ~30 ps late/wide from a reference -- the stopped deconvolution; a
Tikhonov/positivity solver or more iterations with a sharper stop could close it; (b) the blind
mode of the window still runs the tttrlib engine with its own parameters, not `irf_from_decay`'s
trim; (c) done 2026-11-04: the round trip back is wired (see above).

1. Measure: **the Anisotropy Wizard's example** — Load example → Load / reload data → Create fits → Fit, untouched:
   χ²ᵣ 0.99, τ 3.997 ns, ρ 1.999 ns, r0 0.381 (truth 4 / 2 / 0.38). Each fit uses its IRF only over the pulse's
   channels (*IRF start/stop*, `core/irf.py` `response_window`). Trap: the model clips the background-subtracted
   IRF at zero, so any IRF used over a noisy tail adds a constant offset under the decay — un-clipping the wizard's
   subtraction does not help (the model clips again). Tried and reverted: unclipped `correct_irfs` (no effect).
   Open: the window threshold (5 σ, 0.1 % of peak) cuts an IRF reflection below 0.1 % of the peak; the user can
   widen *IRF stop* in the model editor.
2. Measure: **the VV/VH G-factor demo** — Load example: G 1.239 ± 0.132 (simulated 1.2), linked l1 = l2 0.014
   (simulated 0), batch r∞ 0.047 (ρ 8 ns) / 0.230 (ρ 30 ns). Guide 91 is walkable; its figures
   (`gfactor_native_primary_window.png`, `vv_vh_g_factor_native_*.png`) still come from the screenshot scripts'
   own references and could be regenerated from the demo.
3. Measure: **LLTF VV/VH mode** (2026-10-14) — Load example → Fit: 3.982 / 0.968 ns (0.705 / 0.295),
   ρ 1.501 ns, r0 0.351, χ²ᵣ 1.007 (truth 4 / 1 ns, 0.7 / 0.3, ρ 1.5, r0 0.35, G 1.2). Re-derive with
   `lltf/test/test_polarized.py` (seeds 1–3, plus mixing, two rotations, r∞, the Wizard cross-check: LLTF
   3.999 / 1.997 / 0.380 vs ChiSurf's linked fit 3.997 / 2.007 / 0.381). Code: `lltf/core/polarized.py`
   reuses `calculcate_spectrum` (made Schaffer for l1/l2 the same day, RF-954). Open:
   (a) [closed] r0 +0.002…+0.004 on demo seeds 1–5 was chance: over 30 seeds 0.3503 ± 0.0004 (sd 0.0020),
   noise-free counts give 0.3500; fixing the backgrounds at 0 or Neyman changed nothing (scratch probe:
   simulate 30 seeds, mean r0 — do not judge a bias from five); (b) G is held fixed — a tail-matching G
   could be fitted when r(t) has decayed inside the window; (c) [closed] the VV/VH summary is five lines and
   fits 800×600; (d) an associated anisotropy (one r(t) per lifetime) is outside the model.
   Traps: the IRF must be windowed by its baseline noise, not by a fraction of its peak (0.1 % cut the
   example IRF's real tail and moved 1 ns to 1.05 ns; no window left a pedestal, χ²ᵣ 3.8); the magic-angle
   pre-fit that seeds the lifetimes stops off (5.0 / 2.78 ns), so the joint fit runs from two starts.

The `fluorescence_decay/` group analyses Time-Correlated Single Photon Counting (TCSPC) microtime histograms: fitting lifetime decays, recovering the instrument response function (IRF), extracting lifetime or FRET-distance distributions, and resolving rotational anisotropy. These tools depend on a correct IRF and instrument corrections, so estimation and calibration steps sit alongside the fitting steps.

| Plugin dir | Display name | What it does |
|---|---|---|
| `irf_estimator` | IRF Estimation | The one IRF extraction: blind (truncated exponential + Richardson-Lucy), reference dye, scatter, non-burst photons (`core/extraction.py`); Burst MLE, Burst IRF & Background and the MFD fit call it. |
| `maxent_decay` | MaxEnt MEM | Maximum-entropy analysis of TCSPC decays for lifetime and FRET-distance distributions. |
| `lltf` | Lazy Lifetime Analysis | Fast/low-setup lifetime estimation for TCSPC decay data; in VV/VH mode a joint fit of a polarized pair (lifetimes, rotational correlation times, r0; `csc lltf fit-vvvh`). |
| `tr_anisotropy` | Anisotropy-Wizard | Guided setup of a linked VV/VH global time-resolved anisotropy fit: loads polarised decays, background-corrects IRFs, sets instrument corrections and defines lifetime/rotation spectra. |
| `vv_vh_g_factor` | VV/VH G-Factor Calculator | Calculates detector G-factors from VV/VH-format decay files and can archive calibration provenance through backend services. |
| `vv_vh_anisotropy` | VV/VH Anisotropy Decay | Computes anisotropy decays from VV/VH-format VV/VH data, including batch processing. |
| `tttr/microtime_histogram` | Histogram-Microtime | Creates TTTR micro-time histograms for decay inspection before model fitting. |

Each plugin is discovered through its `manifest.json` (`id`, `display_name`, `categories: [Spectroscopy, Fluorescence decay]`) by the infrastructure in `chisurf/core/plugin/`. They obtain decay datasets and register fits through `PluginContext` / `ChiSurfAPI` rather than the legacy globals, and their GUIs (including the `tr_anisotropy` wizard) are rendered from AutoForm view schemes. The integrated `lifetime_analysis` window builds on the shared `NavigationPanelTool` shell and reuses the standalone plugins as panels.

See also: [plugin system](/architecture/plugin-system.md), [Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md). Lifetime filters derived from these decays feed the [FCS group](fcs.md) (fFCS, 2D-FLCS) and per-burst lifetime estimation in the [burst group](burst.md).


## Native microtime histogram retirement — 2026-10-07

The public CLI/manifest and remaining lifetime panel now use the existing native AutoForm histogram app; wizard.py/UI and its old Qt reference are retired. Immutable measured arrays/fullsettings replace recomputing the deleted legacy widget. Five print-only scripts retire while the independent fortune assertion remains unchanged. The saved BID setup publisher synchronizes the editor before replacing the completed model; switching polarization merges/splits the current ordered routes and retains explicit timing/G/shifts/manual channels. Scientific model and package initializer bytes/modes remain unchanged.

The plugin supplies a synthetic PTU Demo (3000VV/1500VH,32ps micro/25ns macro clocks,4-bin/.128ns FWHM) and real Guide awaits Demo then Compute. Current native defaults/scientific outputs preserve provider timing; the headerless BH3.2958984375ps is not independent instrument calibration and explicit25ps is validation only. Three polarized measured exports match the legacy bytes. Unpolarized output corrects the extra-all-source-VH bug:135967selected/4096rows rather than319624/8192. All17 final images were inspected, including legacy-host and complete detector controls; paired docs and3realfigures accompany the source.

Parent112 targeted cases pass in three isolated normal-exit groups; scoped Ruff14/mypy6 are clean. The actual policy guard identified one stale Qt GUI allowance after entrypoint retirement; removing only that line makes all285 policy cases pass/16expectedskips, with other available guard files already green. No allowance or skip added. W1 next is ordered Burst13, then Channel14 and shared Designer helper cleanup.

## Native G-factor contract — 2026-10-09

The calculator consumes an authored1100×720 default and retains saved geometry.
Tail matching's G=VV/VH corrects VH in anisotropy and linked mixing; knownG2
therefore produces zero fast-reference anisotropy. Batch columns keep readable
minimum widths and scroll horizontally. Existing preferences reload reference
files/settings and recompute, rather than storing their arrays. Scientific and
layout regressions pass; acceptance
and onefinalarchive retain bounded visual evidence. Verifiedsource remains
uncommitted; broader convention/shift audits are queued separately.

The direct deprecated VV/VH anisotropy host also consumes authored1100×720
metadata and preserves saved geometry. Its existing known ratio/shift/background/
batch/exports and preference reload remain exact. Three bounded captures verify
baseline/default/narrow; acceptance
records the singlearchive and source status. This sizing change does not remove
or redesign the deprecated entry point.

The native anisotropy wizard's actualpanel specification now owns its1100×720
default, while legacy stepmetadata remains unchanged. NormalizedIRFs andshared
VV/VH/globalfit links retain their configuredvalues; componentpanels adapt at
narrowwidth. Creationis notanoptimizationquality claim. Threeboundedcaptures,
targetedchecks andguardsonceatfreeze are recorded in
acceptance
andonefinalarchive.
