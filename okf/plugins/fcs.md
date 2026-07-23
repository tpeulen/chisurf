---
type: Plugin Group
title: Correlation (FCS)
description: Fluorescence Correlation Spectroscopy plugins that turn TTTR photon streams into correlation curves and derive diffusion, lifetime-filtered and 2D-lifetime observables.
resource: chisurf/plugins/fcs/
tags: [plugins, fcs]
timestamp: '2026-07-05T00:00:00Z'
---

The `fcs/` group processes raw photon data into correlation curves and the quantities derived from them — diffusion coefficients, concentrations, lifetime-filtered species and exchange dynamics. Fluorescence Correlation Spectroscopy (FCS) studies molecular dynamics, diffusion and interactions from intensity fluctuations in a confocal volume.

The group presents a **single menu entry — `FCS`** (`fcs_toolbox`). It merges the
correlator workflow with the optional FCS tools behind one left-navigation rail:
the correlator steps come first (under a `Correlator` group header), then a
`Tools` group header separates the optional, independent tools (2D-FLCS,
Lifetime-FCS Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter
calculator, correlation-channel presets). Every constituent below is
`menu_hidden` and surfaced only through this window.

| Plugin dir | Role | What it does |
|---|---|---|
| `fcs_toolbox` | **FCS** (the single menu entry) | Unified FCS window on the shared `NavigationPanelTool` shell. Subclasses `FcsCorrelatorTool` to keep the correlator step wiring and appends the optional tools below a `Tools` separator. |
| `fcs_correlator` | Correlator workflow (hidden building block) | Two-pane navigation workflow whose steps are **1. Channel Definitions → 2. Files & Steps → 3. Photon/Burst Filter → 4. Correlator → 5. FCS Merger** (opens on the file-drop step). There is no separate detector-setup step: step 1 is the FCS channel-definition editor (`FCSChannelWidget`), which selects a detector setup and supplies the correlation channel pairs / logical channel map to the correlator (container type is auto-detected per file). `menu_hidden` — hosted as the first section of `FCS`. |
| `fcs_filter_calculator` | FCS Filter Calculator (tool) | Computes filtered-FCS (fFCS) lifetime filters from microtime decay patterns. |
| `flc_2d` | 2D-FLCS (tool) | Two-dimensional fluorescence lifetime correlation spectroscopy — builds 2D decay-correlation maps to resolve lifetime species and exchange dynamics (see [flc-2d memory](fluorescence-decay.md)). |
| `fcs_lfcs_sim` | Lifetime-FCS Simulator (tool) | AutoForm panel that simulates diffusing species with distinct lifetimes and optional interconversion (via the photon simulator), builds lifetime filters, and shows the species-filtered auto-/cross-correlations. Interactive companion to the Qt-free `core/fluorescence/fcs/simulate.py`. |
| `fcs_merger` | FCS-Merger (workflow step) | Merges/averages multiple FCS correlation curves to improve signal-to-noise; surfaced as the correlator's final step. |
| `fcs_calculator` | Diffusion/Volume Calculator (tool) | Confocal FCS calculator for tau, D, hydrodynamic radius, effective volume and concentration. |
| `fcs_channel_preset` | FCS Definitions (tool + `Setup`) | Defines FCS detector/correlation channels per setup. |
| `fcs_convert` | (CLI) | Click CLI converting FCS correlation files between formats (ALV, ConfoCor3, Kristine, PyCorrFit, `.sin`, CSV, YAML, …). |

Plugins are discovered via `manifest.json` (`id`, `display_name`, `categories: [Spectroscopy, Fluorescence Correlation Spectroscopy]`) by `chisurf/core/plugin/`; `fcs_toolbox`, `fcs_correlator` and `fcs_convert` are code/CLI helpers without their own manifest (discovered from the `__init__.py` `name`/`menu_hidden` metadata). They read datasets and write fits through `PluginContext` / `ChiSurfAPI`, and their GUIs are AutoForm view schemes. Conversion I/O is shared with `chisurf.core.fio.fluorescence.fcs`.

The Filter Calculator follows the fluorescence-domain objective of a
[single intensity/decay computation path](/subsystems/fluorescence-domain.md#design-objective-one-intensitydecay-computation-path): measured patterns and spectra imported from existing fits are valid inputs, but detector-resolved decay generation (including IRF, polarization, detector response, and crosstalk) should route through the shared ChiSurf model infrastructure rather than plugin-local formulas.

Its GUI uses the shared AutoForm record-table binding for editable lifetime spectra, an AutoForm options model for the Pol/AP/IRF toggles, and the ChiSurf `DockArea` for rearrangeable source, detector, filter, reconstruction, and residual panels. Detector selection and per-detector IRF live in one **Detectors table** (`DetectorIrfTableWidget`): a row per detector with a select checkbox, the name, editable synthetic-IRF Width (FWHM ns) and Skew, a **Shift** column (IRF time shift in ns), and an IRF column whose `…` button loads a measured IRF file (then becomes `✕` to unload). While a measured IRF is loaded, Width/Skew are disabled and populated with values estimated from that IRF (`irf_width_skew_ns`); the **Shift stays editable** and is applied (`_shift_irf`, sub-bin linear interpolation, positive = later) to *both* the measured and the synthetic/computed IRF so a detector's timing offset is corrected the same way regardless of source. When Pol is on, each detector splits into parallel/perpendicular rows with independent IRF settings; the per-detector state (IRF path, Width, Skew, Shift) persists in projects (`export_state`/`import_state`). The default scientific stack places weighted residuals immediately above the reconstruction/decay plot; the residuals are **masked to the selected fit range** (`_mask_to_fit_range` → NaN outside `[start, stop]`, drawn with `connect="finite"`) so only the fitted region is shown. The **fFCS filters are solved over the fit-range window** (`_ranged_filters` slices the total/species/nuisance to `[start, stop]`, runs `calc_ffcs_filters` there, and embeds the result back — filters zero outside, reconstruction == total outside so the residual is 0 there), so the excluded pre-prompt/far-tail bins cannot bias the reconstruction; the synthetic **scatter uses the detector's own IRF** (`_detector_irf`, with the auto-fit's fitted width/skew/shift) so scatter, the component convolution and the auto-fit share one IRF. Filters are therefore zeroed outside the fit range, and the range can be set **per detector** — an editable Detector/Start/Stop table in the **Info dock** overrides the global region (`_detector_fit_ranges`). Because the fFCS filters are computed over the full decay and only zeroed to the range, a **range change re-zeros from a cached copy of the un-zeroed filters and replots without a refit** (`_on_fit_range_committed`), so dragging the region — or editing a spinbox / the per-detector table — updates the filter and residual plots instantly, and narrowing then widening recovers the columns. The **Info dock** (`_build_info_panel`) gathers all state: mixed-decay source/files, bins/bin-width/µ-time binning, global fit range, per-detector IRF (width/skew/shift/measured), the component list, the last auto-fit summary, and per-result filter counts/mode. A compact emoji-led toolbar owns data/component/unmix/project actions through `QToolButton` menus; visible labels stay short while tooltips carry the complete descriptions. Plot colors are identity-stable rather than index-based: common detector names have semantic colors and other detector/component names use a deterministic digest palette, so toggling a channel or component cannot recolor survivors. The **Mixed decay** group has an explicit `📂 Load…` button and a `📡 From correlator` button that adopts the TTTR files already loaded in the sibling Correlator (Files & Steps) step as the mixed decay — reading the FCS toolbox's shared `FcsWorkflowContext.expanded_files`/`file_paths`; on first show the Filter Calculator auto-adopts those files when the user hasn't loaded a measured total. The **micro-time axis comes from the loaded data**: the TAC bin width (ns) is read from the TTTR header's `micro_time_resolution` and the channel count from `number_of_micro_time_channels`, with an **optional micro-time binning** factor (`FcsWorkflowContext.microtime_binning`, from the correlator) that coarsens the histogram and widens the bin width identically to the correlator — so the lifetime filters share the correlation's micro-time axis rather than a hardcoded `n_bins`/`bin_width`. A replaceable two-component 70/30 example is generated on first open as a reproducible 100,000-photon Poisson observation, so the filter, noisy reconstruction, and weighted-residual workflow is visible before measured data are loaded; those seeded components are tagged `example` and are **cleared automatically the moment measured data is loaded** (`_clear_example_components`), while user-added components survive. Synthetic or fit-derived reference patterns can independently opt into shot noise with an explicit photon budget and seed.

**Coupled FRET-species components.** A component can be a whole smFRET
labeling state whose channels carry *different, physically-coupled* decays
(a species does not share one decay across detectors). The core
`chisurf/core/fluorescence/fret/species_decay.py::fret_species_patterns` builds,
for states donor-only / FRET-pair (DA) / acceptor-only: **green** = donor decay
(FRET-quenched in DA), **red** = the FRET-*sensitized* acceptor (donor-decay-shaped
rise, via the reused `fret/acceptor.py::da_a0_to_ad` primitive) plus donor leakage
(α) and directly-excited acceptor (δ), **yellow** = the acceptor's own decay —
optionally split into ∥/⊥ by a per-chromophore **anisotropy spectrum** `r(t)=Σᵢ bᵢ·e^(−t/ρᵢ)+r∞` (multi-exponential rotation, edited as donor/acceptor `{amplitude, ρ}` tables; a single `r0`/`ρ` remains the fallback).
The channel **amplitudes** come from the full **excitation**
(`[laser, chromophore]`) and **emission** (`[chromophore, detector]`) matrices —
so the relative weights of donor / sensitized / directly-excited emission across
green/red/yellow are physically consistent, not approximated; the familiar
Hellenkamp α/β/γ/δ stay the user-facing knobs and induce those matrices
(`CrosstalkFactors.{excitation,emission}_matrix`). FRET is given either as a
transfer efficiency E or physically as a **distributed distance** — Gaussian
components (mean R, σ, fraction) reusing the *same* distance grid and
`distance_to_fret_rate_constant` as the TCSPC FRET fits — plus R0/κ² and a
donor-only fraction `x(D-only)`. Decays are generated **ideal (no IRF)**; each
detector's own IRF (measured or synthetic-from-width/skew) is applied at compute
time from the Detector settings and **normalized to unit sum** (`normalize_irf`).
Fractions are **not** inputs — each labeling state is one component and the fFCS
filters recover the populations. The GUI editor
(`chisurf/gui/widgets/fret_species_editor.py` + `.view.json`, opened from the
Components context menu as *🔬 Add FRET species…*, double-click to edit) uses
AutoForm tables for the donor/acceptor spectra and the distance distribution,
previews the ideal green/red/yellow (∥/⊥) decays live, and seeds α/β/γ/δ/R0 from
the selected detector-setup calibration (editable); on accept it expands to a
`patterns_by_detector` (via `fret_species_detector_patterns`, mapping each
detector's colour to its channel and applying that detector's IRF) that the
Filter Calculator consumes exactly like a fit-derived source. *Follow-up:* the
legacy hand-built TCSPC FRET-fit input widgets (`gui/widgets/models/tcspc/`
`gaussian.py`, `discrete_distance.py`, …) are not yet AutoForm, so the
distance-distribution / FRET-parameter *input UI* is not yet shared between the
fits and this editor (the core physics already is).

**Auto-fit (auto filter).** A persistent **Auto-fit** dock (registered in the
`DockArea` beside the sources panel, driven by `_build_autofit_panel`) exposes the
decomposition settings inline rather than through a transient dialog: a **Type**
selector (Lifetime species / FRET species), a **components / states** count, and
the **lifetime min/max** bounds, plus a `🎯 Fit + generate filters` button, a live
**Fit range** label, and a status line echoing the last fit (`χ²ᵣ` and the resolved
amplitude·lifetime terms). The dock controls mirror into `_auto_fit_settings`
(`_sync_autofit_settings`), and the `🎯 Auto-fit` toolbar action runs the same fit.
The fit window is chosen with a draggable `LinearRegionItem` region on the decay
plot (synced to the **Fit range** spinboxes and the dock's range label); it resets
when new mixed data is loaded. Auto-fit decomposes the measured mixed decay over
that window into `N` lifetime components (or `N` FRET states, `E` from the relative
donor quenching), appends one synthetic species per component, then auto-computes
the filters. It uses the
general, reusable core `chisurf/core/fluorescence/decay_fit.py` — `fit_lifetime_components`
(discrete multi-exponential: bounded log-space lifetimes via `scipy.least_squares`,
non-negative amplitudes by NNLS at each step, Poisson-weighted residuals, built on
the canonical `synthetic_decay` forward model) and `fit_component_amplitudes`
(the weighted non-negative unmixing step). When the selected (primary) detector has
**no measured IRF**, a synthetic Gaussian IRF is **fitted jointly** (`fit_irf`,
via `synthetic_irf`) — its **width, shift (center) and skew** are all free parameters
(not just the width) — with the fit window extended down to the prompt (`fit_lo = 0`)
so the rising edge makes them identifiable; the fitted width/skew/shift are **written
back to the detector table** (`set_width`/`set_skew`/`set_shift`, the shift being the
fitted center minus the nominal `2·FWHM`) for every selected detector that lacks a
measured IRF; each fitted lifetime's per-detector pattern is then convolved with
that detector's IRF from the prompt (`start_bin = 0`) so the deconvolved components
reconstruct the measured decay. The auto-fit also **fits the scatter and background
fractions** jointly with the lifetimes — `include_scatter` (an IRF-shaped column)
and `include_background` (a constant afterpulse column), driven by the **IRF** and
**AP** input toggles — so the lifetimes are not biased by having to absorb the
prompt/baseline; the fitted `scatter_fraction`/`background_fraction` are reported in
the status line. The **draggable fit region is the fit window** (`fit_lo = start`),
so the fit honours the user's range rather than always starting at bin 0. An
**Instrument dock** (AutoForm over `instrument_options.py`) holds the calibration
constants **α/β/γ/δ, G-factor, l₁/l₂, R₀ and the laser period**, pre-populated from
the selected setup; enabling its **periodic convolution** threads a `period` through
`fit_lifetime_components`/`_basis`/`synthetic_decay` so the previous-pulse tail wraps
into the window (removing the residual ramp), and the generated components carry
`period_ns` to stay periodic. When a measured IRF *is* loaded the fit is a robust
tail fit over the region (start past the prompt), aligned to the range start. The
draggable region item is preserved across every replot (`_clear_recon_plot` re-adds
it after `PlotWidget.clear()`, which would otherwise wipe it on the first compute).
**The auto-fit runs through a real ChiSurf `Fit`.** `_auto_fit_components` calls
`fit_lifetime_model` ([subsystems/fitting.md](/subsystems/fitting.md)), which
drives an actual `LifetimeModel`, and the Auto-fit dock renders that model's
parameters in the standard AutoForm parameter table — so the ordinary
right-click **Link…** menu can tie a fitted lifetime to a parameter of any open
fit. Three things the swap had to reconcile:

- **Amplitude convention.** `fit_lifetime_model` reports **pre-exponential**
  amplitudes; the scipy fitter it replaced reported **photon fractions**, which
  is what the species labels and relative weights mean. The seam converts with
  `f_i = a_i·τ_i / Σ a_j·τ_j` rather than relabelling one as the other.
- **Fit window.** The model is handed the *full* decay plus `start_bin`/
  `stop_bin` and masks the window itself; the previous call sliced the window
  first, which made every fitted time relative to the window start.
- **IRF write-back.** The model parameterises the prompt as a generalized normal
  with σ `iw` and shape `ik`, while `synthetic_irf` takes a FWHM and the *same*
  shape — so the width converts exactly through `FWHM_TO_SIGMA` and the skew
  transfers unchanged. The shift is read off the model's own processed IRF peak
  against the nominal `2·FWHM` centre, avoiding any dependence on the units of
  the model's internal timeshift.

The table hides convolution/acquisition plumbing (`dt`, `rep`, `start`, `stop`,
`irf_start`, `irf_stop`, `n0`, …) — the auto-fit configures those, they are not
results.

**The FRET kind fits distances, not converted lifetimes.** Selecting *FRET
species* runs `fit_fret_model`, which drives a real
`GaussianModel`: each state is a Gaussian donor–acceptor distance whose **mean,
width and species fraction are fitted parameters**, alongside the donor-only
fraction `xDOnly`, and the efficiencies follow from the fitted distances and R₀
(taken from the Instrument dock). **R₀ and τ_D0 are held fixed** — they are
calibration rather than data, and fitting them against a distance distribution
is badly conditioned, since R₀ and R trade off through the same `(R/R₀)⁶`.
`_add_fret_autofit_species` still supports the older *derived* route
(`E = 1 − τ/τ_D0`, longest fitted lifetime taken as unquenched donor) for
callers that only have lifetimes, and now documents which inference it is
making.

Afterpulsing/dark counts and scattered excitation light are the two explicit
nuisance bases, toggled by the **AP** (`fit_background`) and **IRF**
(`scatter_irf`) controls respectively: a constant microtime pattern represents
the former and the normalized IRF the latter. They participate in
reconstruction, filter orthogonalization, and non-negative unmixing, with their
fitted counts reported separately. Nuisance rows always remain visible for
diagnostics (drawn dotted and tagged "(rejected)" in the lifetime-filters plot)
but are **always** removed from the correlation-facing filter tables — only
molecular species become correlation channels. (There is no separate "reject
nuisance" toggle; rejection is unconditional, since afterpulse/scatter should
never become correlation channels.)

**Multi-detector filter modes.** With more than one detector selected the filters
are computed either **independently per detector** (default: each detector's photons
are isolated and its filters column-normalized on their own) or in a **global
(stacked)** mode (the *Global (stacked) multi-detector filters* toggle,
`_compute_filters_stacked`). Stacked mode concatenates every detector's total decay
and per-species patterns onto a single axis (`[green | red | yellow]`) and solves one
filter set jointly, then splits it back into per-detector `FilterResult` slices for
plotting/export. Because the FRET-species per-detector patterns keep their **joint
normalization** — a species' relative brightness across detectors, fixed by the
excitation/emission matrices and α/β/γ/δ crosstalk (`fret_species_patterns` normalizes
across channels, not per channel) — that inter-detector amplitude ratio constrains the
unmix in stacked mode, whereas the independent mode discards it (per-detector column
normalization). The mode persists in the project `ui_state`.

**Single decay generator.** Synthetic decays everywhere funnel through the one
canonical generator `chisurf/core/fluorescence/decay.py::synthetic_decay` /
`synthetic_component_decay` (built on the shared `calculate_fluorescence_decay`
sum-of-exponentials, the `tcspc/convolve.py` IRF kernels, and
`sample_decay_shot_noise`). The Filter Calculator's former local
`api.py::synthetic_decay` (a duplicate exponential+`np.convolve` implementation)
now re-exports the core function. That generator is also surfaced as a
full-stack plugin, `chisurf/plugins/fluorescence_decay/synthetic_decay/`
(**Spectroscopy:Fluorescence Decay:Synthetic Decay Generator**) with API / CLI
(`synth-decay generate|component`) / RPC (`synthetic_decay.compute[_component]`)
/ AutoForm GUI (editable lifetime-spectrum table + histogram/IRF/noise options +
live decay plot). The **photon-stream simulators build their per-species
`SimDecay` through the same generator**: the acquisition simulator
(`plugins/core/acq/.../simulation/core/algorithms.py::build_engine`, from its
`decay_lifetimes` + optional `irf_fwhm_ns`) and the CLSM imaging simulator
(`core/fluorescence/imaging/simulate.py::_lifetime_species`) both call
`synthetic_decay(...)` → `tttrlib.SimDecay.from_pattern`, replacing local
`np.exp`/`np.convolve` code. The TCSPC-experiment `core/experiments/tcspc/simulator.py`
keeps the lower-level `calculate_fluorescence_decay` (it may use rise terms /
zero-lifetime components the strict wrapper rejects).

**One shared decay editor.** The synthetic-decay *editing surface* is also
unified, not just the generator math. A single reusable AutoForm editor —
`chisurf/gui/widgets/synthetic_decay_editor.py::SyntheticDecayEditorModel` with
`synthetic_decay_editor.view.json` — provides the amplitude/lifetime spectrum
table, IRF (a loaded **experimental** histogram *or* a synthetic **skewed**
Gaussian — FWHM + skew, via the canonical `tcspc/irf.py::synthetic_irf`
generalized-normal helper), a periodic **colour shift** (sub-bin IRF time shift),
optional **periodic convolution** at a laser repetition **period** (the
`fconv_per` inter-pulse tail), Poisson shot-noise (photons + seed), histogram
size, a measured-pattern override, "Read from Fit", and a live decay preview.
The generator `synthetic_decay` gained `period` (periodic convolution) and
`time_shift` (a wrapped sub-bin IRF shift via the new
`tcspc/convolve.py::periodic_shift`) parameters; `synthetic_component_decay`
threads the persisted `period_ns`/`time_shift_ns` so a Filter-Calculator
reconstruction matches the editor preview. Both the FCS Filter Calculator's *Add Synthetic Decay Component*
dialog (`fcs_filter_calculator/gui_parts/main_window.py::_add_synthetic_dialog`,
which reads `editor_model.component()` for the persisted source dict) and the
acquisition simulator's *Decay settings* modal
(`plugins/core/acq/.../simulation/setup_dialog.py::DecaySettingsDialog`, which
wraps the shared editor with a per-species selector) embed this one widget, so
the two editors can no longer diverge. The Filter Calculator's former
plugin-local `SyntheticSpectrumViewModel` / `synthetic_editor.view.json` were
removed. Editable AutoForm tables now refresh the hosting form on cell edit
(mirroring value/toggle/button sections), so the preview stays live.

**TODO — auto-optimizing filter sweep (autoresearch).** Filter computation is
cheap, so a planned feature sweeps the filter-defining inputs (per-species IRF
width/skew, micro-time gating, nuisance handling, `rcond`/Tikhonov conditioning)
to **maximize the contrast between species filters** — and hence the
anti-correlation amplitude/contrast in the resulting species cross-correlation.
This is marked as an **autoresearch component**: an automated search/optimizer
(objective = species-filter separability / anti-correlation contrast) that
proposes and ranks filter settings rather than requiring manual tuning.
**Reuse candidate:** the 2D-FLCS plugin (`flc_2d`) already performs a lifetime
**decay unmixing** (MEM/Tikhonov inversion of a 2D fluorescence-decay
correlation map into lifetime species); that unmixing machinery is a strong
candidate to drive, or seed, the fFCS filter computation and the sweep's species
model. See [FCS catalogue & FLCS filters: PAM port](/references/fcs-pam-port.md).

IRF/scatter calibration is detector-resolved. Each detector may select its own
measured IRF. When that entry is empty, the calculator reuses the TCSPC
synthetic-IRF machinery and searches the detector decay's prompt position and
width while non-negatively fitting species, constant afterpulse, and IRF
scatter amplitudes. Polarization channels are fitted separately. The preloaded
example follows the same forward model: detector-distinct synthetic IRFs
convolve both molecular patterns, and the finite-count mixtures include an
IRF-shaped scatter fraction plus a constant afterpulse fraction.

Correlation curves are fitted against a catalogue of string-equation models in `chisurf/core/models/fcs/models.yaml` (parsed by `ParseFCSModel` / `ParseModel`) — a large family of 3D/2D-Gaussian diffusion and bunching/anti-correlation terms. This catalogue was extended with an **absolute-`D`, physically-parametrised family ported from PAM** (Schrimpf 2018) and A/B-verified against PAM's exact formulas: single- and two-component 3D diffusion with triplet, `tau_D` and anomalous variants, flow, background, afterpulsing, bleaching, **two-focus FCS** (absolute `D` from a known inter-focus distance), FRET-FCCS 2-state kinetics, ns-FCS antibunching, and scanning FCS. Three pre-existing broken catalogue entries (equations referencing parameters absent from their `initial:` block) were also fixed. On the FLCS side, `chisurf/core/fluorescence/fcs/filtered.py` gained pseudo-inverse conditioning (`rcond`/Tikhonov), a condition-number diagnostic, a uniform (afterpulsing) pattern helper, and a per-photon filter-weighting helper, and its legacy `calc_lifetime_filter` divide-by-zero / nonstandard-renormalisation bugs were fixed. A Qt-free lifetime-FCS **simulator** (`chisurf/core/fluorescence/fcs/simulate.py`, `simulate_lifetime_fcs`) closes the FLCS loop: it drives the photon simulator to generate confocal photon streams of several diffusing species with distinct lifetimes and an optional interconversion rate matrix, reconstructs the macro-time axis from the engine window + arrival offset and reads native micro-times (the hardware TAC encoding is bypassed, which would otherwise ill-condition the filters), and feeds `calc_ffcs_filters` + `species_filtered_correlation` so the species separate by diffusion time (static) or reveal exchange in the cross-correlation (dynamic). Worked examples: `examples/lifetime_fcs.py` (chisurf) and `examples/correlation/plot_lifetime_fcs.py` (photon-simulator gallery). Full status, the A/B methodology, and remaining gaps (correlator wiring, channel-aware par/perp weighting, scatter/IRF pattern injection, and the not-yet-ported pCF/SCCF/MIA models) are in [FCS catalogue & FLCS filters: PAM port](/references/fcs-pam-port.md) and [Two-focus FCS status and gaps](/references/two-focus-fcs.md).

Beyond the string-equation catalogue, the FCS model list also carries **non-parse** (Python-computed) `ModelCurve` models — `DyeShapeFCSWidget`, `MaxEntFCSWidget`, and the new **`MdfFCSWidget`** ("FCS MDF (Gauss--Lorentz)"), registered in `experiment_configs.yaml` alongside `ParseFCSWidget`. The MDF model closes the non-Gaussian molecule-detection-function gap: `chisurf/core/fluorescence/fcs/enderlein.py` ports Fretica's `FEnderleinMDF`/`FVeffEnderlein`/`FGdiffEnderlein` — the Gauss--Lorentz MDF `U(ρ,z)=κ(z)/w(z)²·exp(-2ρ²/w²)/norm` (with axially-varying beam width `w(z)` and pinhole collection efficiency `κ(z)`), the effective volume `Veff = π(∫κ)²/∫(κ²/w²)` (so absolute concentrations, not just relative amplitudes), and the diffusion autocorrelation obtained by convolving the MDF with the 3-D propagator. The lateral integral is analytic; the axial convolution uses **Gauss--Hermite quadrature in the difference direction** (substituting `z' = z + √(4Dτ)ξ`) so the propagator is resolved at any lag — a fixed z-grid fails once `√(4Dτ)` drops below the grid spacing. The model exposes N, D (µm²/s), `w0`/`R0` (nm) and fixed optics (λex/λem, n, pinhole, magnification), and reports `Veff`, concentration and `τ_D` as outputs. It is the accurate-`Veff` basis two-focus/dual-focus calibration wants. Headless coverage: `test/fluorescence/test_enderlein_fcs.py` (MDF shape, `Veff` scaling, `g(0)=1` normalisation and `g(0)=1/Veff` consistency, D-scaling of the decay) and `test/gui/test_fcs_models_resolve.py` (the model resolves + appears in the FCS menu as a `ModelCurve`).

The **Correlator step wires the FLCS filters into the GUI**: its `4. Correlator` panel has a lifetime-filter load/unload control (`🧬 Load filters… / ✖ Unload`, plus a `🧪 Filter Calc…` button that deep-links to the Filter Calculator tool via `NavigationPanelTool.show_panel_by_role("filter_calc")`) that reads an fFCS `FilterResult` JSON (from the Filter Calculator; nuisance filters excluded) or a `.npy`/`.npz` filter matrix and calls `CorrelatorSettingsModel.set_lifetime_filters`. While filters are loaded the panel is in *species mode*: the A/B selectors list the filter species instead of detector channels, and pressing *Correlate* computes that species pair's auto-correlation (A = B) or cross-correlation (A ≠ B) via `species_filtered_correlation` restricted to the two chosen filter rows. Unloading returns the panel to detector-channel correlation.

The FCS plugin family carries a **coherent emoji icon set** (previously a mix of
raster `icon.png`, one emoji, and blanks): the FCS umbrella tool `〰️`,
Correlator `⚛️`, diffusion Calculator `🧮`, fFCS Filter Calculator `🎚️`,
Converter `🔁`, Merger `🔀`, Lifetime-FCS Simulator `🎲`, 2D-FLCS `🌈`, and the
Channel Preset `📡`. Icons are declared in each plugin's `manifest.json` `icon`
field (or, for the manifest-less legacy plugins, a module `icon` attribute);
superseded `icon.png` assets were removed. Resolution order is manifest icon →
on-disk image → module attribute (see [GUI & AutoForm](/subsystems/gui-autoform.md)).

See also: [plugin system](/architecture/plugin-system.md), [Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md). Per-burst FCS lives in the [burst group](burst.md). Formats interoperate with established FCS/multiparameter-fluorescence suites.
