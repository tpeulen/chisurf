---
type: Plugin Group
title: Fluorescence decay
description: TCSPC fluorescence-lifetime plugins for decay analysis, blind IRF estimation, maximum-entropy lifetime/distance distributions and time-resolved anisotropy.
resource: chisurf/plugins/fluorescence_decay/
tags: [plugins, tcspc]
timestamp: '2026-07-05T00:00:00Z'
---

## Where to pick this up

1. Open: **the Anisotropy Wizard's global fit does not fit its own simulated example** (χ²ᵣ 4.2 with the reader's
   auto range, 27.6 over bins 20–780; r0 0.347 against 0.38). Measure: `NativeAnisotropyModel().load_example()`,
   `load_data()`, `create_fits()`, run the global fit, compare model and data where the data are ~0 (bin 25:
   0 vs 25.3). Trap: the plugin test checks parameters only, never χ². Moving the IRF background region does not
   help. Known issue "Anisotropy Wizard's global fit misses its own simulated example" (2026-10-11).
2. Open: **the VV/VH G-factor tool has no demo**, so guide 91 cannot be walked without user files; the synthetic
   references the guide figures use live only in the screenshot scripts.
3. Done 2026-10-11: the wizard's fits are created with a runnable range (`initialise_fit_range` in
   `build_fit_group`); guide walk method and the rest in known issue "QA walk of the FCS, lifetime, …".

The `fluorescence_decay/` group analyses Time-Correlated Single Photon Counting (TCSPC) microtime histograms: fitting lifetime decays, recovering the instrument response function (IRF), extracting lifetime or FRET-distance distributions, and resolving rotational anisotropy. These tools depend on a correct IRF and instrument corrections, so estimation and calibration steps sit alongside the fitting steps.

| Plugin dir | Display name | What it does |
|---|---|---|
| `lifetime_analysis` | Decay Analysis | Integrated lifetime-analysis window bundling IRF estimation, MaxEnt MEM, Lazy Lifetime Analysis, microtime histograms and VV/VH G-factor calibration. |
| `irf_estimator` | IRF Estimation | Blind IRF estimation from decay data via truncated-exponential fitting and Richardson-Lucy deconvolution. |
| `maxent_decay` | MaxEnt MEM | Maximum-entropy analysis of TCSPC decays for lifetime and FRET-distance distributions. |
| `lltf` | Lazy Lifetime Analysis | Fast/low-setup lifetime estimation for TCSPC decay data. |
| `tr_anisotropy` | Anisotropy-Wizard | Guided setup of a linked VV/VH global time-resolved anisotropy fit: loads polarised decays, background-corrects IRFs, sets instrument corrections and defines lifetime/rotation spectra. |
| `vv_vh_g_factor` | VV/VH G-Factor Calculator | Calculates detector G-factors from VV/VH-format decay files and can archive calibration provenance through backend services. |
| `vv_vh_anisotropy` | VV/VH Anisotropy Decay | Computes anisotropy decays from VV/VH-format VV/VH data, including batch processing. |
| `tttr/microtime_histogram` | Histogram-Microtime | Creates TTTR micro-time histograms for decay inspection before model fitting. |

Each plugin is discovered through its `manifest.json` (`id`, `display_name`, `categories: [Spectroscopy, Fluorescence decay]`) by the infrastructure in `chisurf/core/plugin/`. They obtain decay datasets and register fits through `PluginContext` / `ChiSurfAPI` rather than the legacy globals, and their GUIs (including the `tr_anisotropy` wizard) are rendered from AutoForm view schemes. The integrated `lifetime_analysis` window builds on the shared `NavigationPanelTool` shell and reuses the standalone plugins as panels.

See also: [plugin system](/architecture/plugin-system.md), [Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md). Lifetime filters derived from these decays feed the [FCS group](fcs.md) (fFCS, 2D-FLCS) and per-burst lifetime estimation in the [burst group](burst.md).


## Native microtime histogram retirement — 2026-10-07

The public CLI/manifest and remaining lifetime panel now use the existing native AutoForm histogram app; wizard.py/UI and its old Qt reference are retired. Immutable measured arrays/fullsettings replace recomputing the deleted legacy widget. Five print-only scripts retire while the independent fortune assertion remains unchanged. The saved BID setup publisher synchronizes the editor before replacing the completed model; switching polarization merges/splits the current ordered routes and retains explicit timing/G/shifts/manual channels. Scientific model and package initializer bytes/modes remain unchanged.

The plugin supplies a synthetic PTU Demo (3000VV/1500VH,32ps micro/25ns macro clocks,4-bin/.128ns FWHM) and real Guide awaits Demo then Compute. Current native defaults/scientific outputs preserve provider timing; the headerless BH3.2958984375ps is not independent instrument calibration and explicit25ps is validation only. Three polarized measured exports match the legacy bytes. Unpolarized output corrects the extra-all-source-VH bug:135967selected/4096rows rather than319624/8192. All17 final images were inspected, including legacy-host and complete detector controls; paired docs and3realfigures accompany the source.

Parent112 targeted cases pass in three isolated normal-exit groups; scoped Ruff14/mypy6 are clean. The actual policy guard identified one stale Qt GUI allowance after entrypoint retirement; removing only that line makes all285 policy cases pass/16expectedskips, with other available guard files already green. No allowance or skip added. [Acceptance](../validation/release-readiness-w1/microtime-retirement/acceptance.json). W1 next is ordered Burst13, then Channel14 and shared Designer helper cleanup.

## Native G-factor contract — 2026-10-09

The calculator consumes an authored1100×720 default and retains saved geometry.
Tail matching's G=VV/VH corrects VH in anisotropy and linked mixing; knownG2
therefore produces zero fast-reference anisotropy. Batch columns keep readable
minimum widths and scroll horizontally. Existing preferences reload reference
files/settings and recompute, rather than storing their arrays. Scientific and
layout regressions pass; [acceptance](../validation/release-readiness-w6g/gfactor-window-acceptance.json)
and onefinalarchive retain bounded visual evidence. Verifiedsource remains
uncommitted; broader convention/shift audits are queued separately.

The direct deprecated VV/VH anisotropy host also consumes authored1100×720
metadata and preserves saved geometry. Its existing known ratio/shift/background/
batch/exports and preference reload remain exact. Three bounded captures verify
baseline/default/narrow; [acceptance](../validation/release-readiness-w6g/vv-vh-window-acceptance.json)
records the singlearchive and source status. This sizing change does not remove
or redesign the deprecated entry point.

The native anisotropy wizard's actualpanel specification now owns its1100×720
default, while legacy stepmetadata remains unchanged. NormalizedIRFs andshared
VV/VH/globalfit links retain their configuredvalues; componentpanels adapt at
narrowwidth. Creationis notanoptimizationquality claim. Threeboundedcaptures,
targetedchecks andguardsonceatfreeze are recorded in
[acceptance](../validation/release-readiness-w6g/anis-wizard-window-acceptance.json)
andonefinalarchive.
