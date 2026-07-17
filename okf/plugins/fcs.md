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

Its GUI uses the shared AutoForm record-table binding for editable lifetime spectra, an AutoForm options model for polarization/background controls, and the ChiSurf `DockArea` for rearrangeable source, detector, filter, reconstruction, and residual panels. The default scientific stack places weighted residuals immediately above the reconstruction/decay plot. A compact emoji-led toolbar owns data/component/unmix/project actions through `QToolButton` menus; visible labels stay short while tooltips carry the complete descriptions. Plot colors are identity-stable rather than index-based: common detector names have semantic colors and other detector/component names use a deterministic digest palette, so toggling a channel or component cannot recolor survivors. A replaceable two-component 70/30 example is generated on first open as a reproducible 100,000-photon Poisson observation, so the filter, noisy reconstruction, and weighted-residual workflow is visible before measured data are loaded. Synthetic or fit-derived reference patterns can independently opt into shot noise with an explicit photon budget and seed.

Afterpulsing/dark counts and scattered excitation light are explicit nuisance
bases: a constant microtime pattern represents the former and the normalized
IRF represents the latter. They participate in reconstruction, filter
orthogonalization, and non-negative unmixing, with their fitted counts reported
separately. With nuisance rejection enabled, the nuisance rows remain visible
for diagnostics but are deliberately removed from correlation-facing filter
tables; only molecular species become correlation channels.

IRF/scatter calibration is detector-resolved. Each detector may select its own
measured IRF. When that entry is empty, the calculator reuses the TCSPC
synthetic-IRF machinery and searches the detector decay's prompt position and
width while non-negatively fitting species, constant afterpulse, and IRF
scatter amplitudes. Polarization channels are fitted separately. The preloaded
example follows the same forward model: detector-distinct synthetic IRFs
convolve both molecular patterns, and the finite-count mixtures include an
IRF-shaped scatter fraction plus a constant afterpulse fraction.

Correlation curves are fitted against a catalogue of string-equation models in `chisurf/core/models/fcs/models.yaml` (parsed by `ParseFCSModel` / `ParseModel`) — a large family of 3D/2D-Gaussian diffusion and bunching/anti-correlation terms. This catalogue was extended with an **absolute-`D`, physically-parametrised family ported from PAM** (Schrimpf 2018) and A/B-verified against PAM's exact formulas: single- and two-component 3D diffusion with triplet, `tau_D` and anomalous variants, flow, background, afterpulsing, bleaching, **two-focus FCS** (absolute `D` from a known inter-focus distance), FRET-FCCS 2-state kinetics, ns-FCS antibunching, and scanning FCS. Three pre-existing broken catalogue entries (equations referencing parameters absent from their `initial:` block) were also fixed. On the FLCS side, `chisurf/core/fluorescence/fcs/filtered.py` gained pseudo-inverse conditioning (`rcond`/Tikhonov), a condition-number diagnostic, a uniform (afterpulsing) pattern helper, and a per-photon filter-weighting helper, and its legacy `calc_lifetime_filter` divide-by-zero / nonstandard-renormalisation bugs were fixed. A Qt-free lifetime-FCS **simulator** (`chisurf/core/fluorescence/fcs/simulate.py`, `simulate_lifetime_fcs`) closes the FLCS loop: it drives the photon simulator to generate confocal photon streams of several diffusing species with distinct lifetimes and an optional interconversion rate matrix, reconstructs the macro-time axis from the engine window + arrival offset and reads native micro-times (the hardware TAC encoding is bypassed, which would otherwise ill-condition the filters), and feeds `calc_ffcs_filters` + `species_filtered_correlation` so the species separate by diffusion time (static) or reveal exchange in the cross-correlation (dynamic). Worked examples: `examples/lifetime_fcs.py` (chisurf) and `examples/correlation/plot_lifetime_fcs.py` (photon-simulator gallery). Full status, the A/B methodology, and remaining gaps (correlator wiring, channel-aware par/perp weighting, scatter/IRF pattern injection, the non-Gaussian Dertinger MDF, and the not-yet-ported pCF/SCCF/MIA models) are in [FCS catalogue & FLCS filters: PAM port](/references/fcs-pam-port.md) and [Two-focus FCS status and gaps](/references/two-focus-fcs.md).

The **Correlator step wires the FLCS filters into the GUI**: its `4. Correlator` panel has a lifetime-filter load/unload control (`🧬 Load filters… / ✖ Unload`) that reads an fFCS `FilterResult` JSON (from the Filter Calculator; nuisance filters excluded) or a `.npy`/`.npz` filter matrix and calls `CorrelatorSettingsModel.set_lifetime_filters`. While filters are loaded the panel is in *species mode*: the A/B selectors list the filter species instead of detector channels, and pressing *Correlate* computes that species pair's auto-correlation (A = B) or cross-correlation (A ≠ B) via `species_filtered_correlation` restricted to the two chosen filter rows. Unloading returns the panel to detector-channel correlation.

See also: [plugin system](/architecture/plugin-system.md), [Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md). Per-burst FCS lives in the [burst group](burst.md). Formats interoperate with established FCS/multiparameter-fluorescence suites.
