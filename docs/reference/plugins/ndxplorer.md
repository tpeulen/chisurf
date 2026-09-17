---
type: Plugin Reference
title: ndX
description: Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data.
resource: chisurf/plugins/ndxplorer/
tags: [reference, plugins, ndxplorer, main, tools]
anchor: plugin-ndxplorer
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-ndxplorer)=
# ndX

Multidimensional fluorescence data analysis and visualization tool. Supports burst analysis, multiparameter fluorescence detection (MFD), FRET calculations, and interactive selection/filtering of burst events for both single-molecule and image spectroscopy data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `ndxplorer` |
| Menu path | Main → Tools → **ndX** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `ndxplorer` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Determine

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| α leakage | `fit_alpha` | bool |  |  | Donor emission detected in the acceptor channel. Taken from the donor-only population, so it needs one. |
| δ direct excitation | `fit_delta` | bool |  |  | Acceptor excited by the donor laser. Taken from the acceptor-only population, so it needs one. |
| γ detection / QY | `fit_gamma` | bool |  |  | Detection efficiency times quantum-yield ratio. From the 1/S = Ω + Σ·E fit across FRET sub-populations, or from the donor lifetime. Turn this off to keep a γ you determined on a reference sample. |
| β excitation flux | `fit_beta` | bool |  |  | Ratio of the two lasers' excitation flux and cross-sections. Comes from the same E-S fit as γ. |
| R₀ Förster radius | `fit_r0` | bool |  |  | Not a correction factor — it converts efficiency to distance. Off by default: it belongs to the dye pair and its environment, not to this measurement. |

### Background

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Take from | `background` | choice |  | choices: fit, measurement, constants, none | 'fit' determines them from the reference populations themselves — an acceptor-only burst has no donor, so what appears in the donor channel is background; a donor-only burst has no acceptor, so what appears under acceptor excitation is background; and the leakage line I_DA = α·I_DD + bg_da gives the third as its intercept. Use this when the background is not known, which is most of the time. It costs a second calibration pass: the populations have to exist before they can be read, and once the background is subtracted the classification is made again.  'measurement' uses the rates the Background step stored in this measurement's container, multiplied by each burst's duration — so a 4 ms burst carries four times the background of a 1 ms one, which a single number cannot express. Falls back to the window's constants if the container has no stored estimate.  'constants' uses the window's Bg / Br / By as they stand. 'none' sets them to zero.  This is the correction whose error is hardest to see: it moves the dim bursts and leaves the bright ones, which looks exactly like a real sub-population. |
| Min. reference bursts | `min_population` | int |  | 3 … 100000 (step 10) | Smallest donor-only / acceptor-only population accepted when fitting a background. Below it that channel is left at whatever it had rather than guessed from a handful of bursts. |

### How

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| γ from | `gamma_source` | choice |  | choices: auto, es, lifetime, combined | 'es' is the 1/S = Ω + Σ·E fit and needs at least two FRET sub-populations; 'lifetime' uses the static FRET line and works on a single population, but needs a per-burst donor lifetime and a trustworthy τ_D(0); 'combined' is the precision-weighted mean; 'auto' takes the E-S fit and falls back to the lifetime. The two routes are independent, so their disagreement is itself a diagnostic. |
| Use light-path priors | `use_priors` | bool |  |  | Combine the data estimates with the optical model's excitation/emission probabilities, so the result is a posterior: data where the data speaks, optics where it does not. |
| Bootstrap resamples | `n_bootstrap` | int |  | 0 … 2000 (step 10) | Resamples used for the factor uncertainties, with the population assignment held fixed. 0 skips them. It is cheap — the classification, not the resampling, is what costs. |
| τ_D(0) (ns) | `donor_lifetime` | float |  | 0.01 … 100.0 (step 0.1) | Donor-only lifetime, which anchors the static FRET line. Only used by the lifetime route; a wrong value there shows up as γ disagreeing between the two routes. |
| Linker σ (Å) | `linker_sigma` | float |  | 0.0 … 30.0 (step 0.5) | Width of the dye-linker distance distribution, which sets the curvature of the static FRET line. |
| Add accurate E / S / R_DA columns | `inject_columns` | bool |  |  | Write the corrected per-burst columns under new names. Not redundant with applying the constants: ndX's own efficiency equation has no direct-excitation term, so constants alone cannot make its native column accurate. Its own columns are left untouched. |

### When it finishes

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Store the calibration in the measurement | `save_when_done` | bool |  |  | Writes the factors, their uncertainties and the report into the .pto container the bursts came from. Each save is kept as its own object, so an earlier calibration is still there afterwards. With no container, the report window offers a file instead. |

## Theory and workflow

- **Theory** — [Density-based clustering](/concepts/density_clustering.md), [Interactive multidimensional exploration](/concepts/multidimensional_exploration.md)
- **Workflow** — [Exploring & fitting multidimensional data (ndX)](/guides/46_ndxplorer.md), [From a selection to a fit: the ndX analysis bridges](/guides/47_ndxplorer_bridges.md)

## Source

- Plugin package: `chisurf/plugins/ndxplorer/`
- Manifest: {src}`chisurf/plugins/ndxplorer/manifest.json`
- UI spec: {src}`chisurf/plugins/ndxplorer/calibration_options.view.json`
