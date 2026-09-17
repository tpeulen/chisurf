---
type: Plugin Reference
title: Accurate FRET
description: 'Accurate FRET (Hellenkamp): automatic alpha/beta/gamma/delta from the burst populations, the optics prior of a saved light path and the static FRET line, with E-S and E-lifetime views.'
resource: chisurf/plugins/burst/accurate_fret/
tags: [reference, plugins, accurate-fret, spectroscopy, fret, single-molecule]
anchor: plugin-accurate_fret
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-accurate_fret)=
# Accurate FRET

Accurate FRET (Hellenkamp): automatic alpha/beta/gamma/delta from the burst populations, the optics prior of a saved light path and the static FRET line, with E-S and E-lifetime views.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `accurate_fret` |
| Menu path | Spectroscopy → FRET → **Accurate FRET** |
| Categories | Spectroscopy, FRET, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `accurate_fret` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| setup_name | `setup_name` | setup_selector |  |  | Detector setup whose named windows (green, red, yellow, …) say which detection channels this measurement has. Picking one helps the channel columns below map themselves even when the table uses site-specific names, and it names the detectors when the optical model supplies the prior. |
| Burst table | `filename` | file |  |  | Per-burst table to calibrate: any delimited text file (.csv/.tsv/.txt/.bur) or an .npz archive, with one row per burst and one column per signal. Files can also be dropped on the window. Use the toolbar's ndX button instead to calibrate exactly the bursts currently open there. |

### Channels

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| I_DD (donor) | `column_i_dd` | choice |  | choices: `column_names` | Donor signal under donor excitation — the 'green' channel. Auto-detected from the column names; counts and count rates both work as long as every channel uses the same unit. Type to filter the list. |
| I_DA (FRET) | `column_i_da` | choice |  | choices: `column_names` | Acceptor signal under donor excitation — the 'red' FRET channel. It still contains donor leakage and directly excited acceptor; removing those is what alpha and delta do. Type to filter the list. |
| I_AA (acceptor) | `column_i_aa` | choice |  | choices: `column_names` | Acceptor signal under acceptor excitation (ALEX/PIE) — the 'yellow' channel. Optional, but without it there is no stoichiometry: donor-only and acceptor-only bursts can then not be found automatically and every burst is assumed to be doubly labelled. Type to filter the list. |
| Donor lifetime | `column_tau_f` | choice |  | choices: `column_names` | Per-burst fluorescence-averaged donor lifetime in presence of the acceptor (ns). Optional, and powerful: it puts every burst on the E-tau plot, lets the static FRET line determine gamma from a single population, and turns the off-line offset into a dynamics test. Type to filter the list. |

### Dyes (database)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Donor | `donor_dye` | choice |  | choices: `dye_names` | Donor dye, from the fluorophore database. Selecting a pair fills in the numbers that are properties of the dyes rather than of this measurement: the Förster radius computed from the stored emission and absorption spectra, both quantum yields, and the donor lifetime when it is curated. Anything the database does not have is left as you set it — the report says which is which. Type to filter the list. |
| Acceptor | `acceptor_dye` | choice |  | choices: `dye_names` | Acceptor dye. Its absorption spectrum and molar extinction coefficient are what the overlap integral — and therefore R0 — is computed from, so an acceptor without those cannot supply an R0. Type to filter the list. |
| kappa^2 | `kappa2` | float |  | 0.0 … 4.0 (step 0.01) | Orientation factor. 2/3 is the isotropic average that free dye linkers justify; it enters R0 only as its sixth root, so even a factor-of-two error moves R0 by ~12 %. |
| Refractive index | `refractive_index` | float |  | 1.0 … 2.0 (step 0.01) | Refractive index of the medium between the dyes: 1.33 for water, ~1.4 inside a protein. R0 scales as n^(-2/3). |

### Photophysics

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| tau_D(0) (ns) | `donor_lifetime` | float |  | 0.01 … 100.0 (step 0.1) | Donor-only lifetime, measured on a donor-only sample. It anchors the FRET lines: the line ends at (tau_D(0), E = 0), so an error here tilts the whole lifetime-based calibration. |
| R_0 (Å) | `forster_radius` | float |  | 1.0 … 200.0 (step 0.5) | Förster radius of the dye pair. It does not affect the efficiency at all — only the distance derived from it, and the shape of the FRET lines. |
| Linker width (Å) | `linker_sigma` | float |  | 0.0 … 30.0 (step 0.5) | Width of the donor-acceptor distance distribution caused by the dye linkers. It is what bends the static FRET line away from the straight E = 1 - tau/tau_D(0) diagonal; 6 Å is typical for common linkers. |
| Dynamic line | `show_dynamic_line` | bool |  |  | Also draw the dynamic FRET line between the two extreme populations found. Populations lying on it (rather than on the static line) exchange between two states faster than the burst duration. |

### Background

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Bg I_DD | `background_dd` | float |  |  | Background of the donor channel, in the units of the columns. Uncorrected background biases low-efficiency populations most. |
| Bg I_DA | `background_da` | float |  |  | Background of the FRET channel. |
| Bg I_AA | `background_aa` | float |  |  | Background of the acceptor-excitation channel. |

### Optics prior (light path)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Use the optics prior | `use_priors` | bool |  |  | Combine each data estimate with what the light path predicts. gamma, alpha and delta follow from computed excitation and emission probabilities; that prediction is the prior, the data moves it, and a factor the data cannot identify keeps the optical value together with the optical uncertainty. |
| Light path | `lightpath_name` | choice |  | choices: `lightpath_names` | A light path saved by the light-path simulator. Its excitation matrix (which laser excites which dye) and emission matrix (which fraction of each dye's emission reaches each detector) are turned into Gaussian priors for gamma, alpha and delta. Leave empty to calibrate from the data alone. Type to filter the list. |
| Phi_D | `quantum_yield_donor` | float |  | 0.0 … 1.0 (step 0.01) | Donor fluorescence quantum yield. Enters the predicted gamma = (g_R·Phi_A)/(g_G·Phi_D). |
| Phi_A | `quantum_yield_acceptor` | float |  | 0.0 … 1.0 (step 0.01) | Acceptor fluorescence quantum yield. |
| g_G | `detection_green` | float |  | 0.0 … 10.0 (step 0.01) | Detection efficiency of the donor (green) channel, beyond what the light path already models. |
| g_R | `detection_red` | float |  | 0.0 … 10.0 (step 0.01) | Detection efficiency of the acceptor (red) channel. |

### Procedure

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| gamma from | `gamma_source` | choice |  | choices: auto, es, lifetime, combined | Which route determines gamma. 'es' uses the 1/S versus E fit across FRET populations (needs at least two of different efficiency); 'lifetime' requires the population to lie on the static FRET line (works with a single population, and without ALEX); 'auto' takes the E-S fit and falls back to the lifetime; 'combined' averages both — their agreement is a good consistency check. |
| Max FRET populations | `max_fret_populations` | int |  | 1 … 6 | Largest number of FRET sub-populations the efficiency mixture may find. These sub-populations are what makes gamma identifiable from a single measurement. |
| Min bursts per population | `min_population` | int |  | 5 … 10000 | A population with fewer bursts is ignored rather than used for a factor. Raise it for noisy data so a handful of outliers cannot define a correction factor. |
| Bootstrap resamples | `n_bootstrap` | int |  | 0 … 2000 | Resamples used to estimate the uncertainty of each factor (0 skips it). The uncertainties matter twice: they weigh the data against the optics prior, and they propagate into the error bar of the accurate efficiency. |
| Plotted bursts | `max_points` | int |  | 200 … 200000 | Upper limit of bursts drawn in the scatter plots (the calibration always uses all of them). |

## Theory and workflow

- **Theory** — [Accurate FRET: correction factors, FRET lines, and where they come from](/concepts/accurate_fret.md)
- **Workflow** — [RCM detection calibration from dye solutions](/guides/07_rcm_calibration.md), [RCM from FRET-labelled samples (PIE/ALEX)](/guides/25_rcm_from_fret_samples.md), [Accurate FRET: automatic correction factors](/guides/41_accurate_fret.md)

## Source

- Plugin package: `chisurf/plugins/burst/accurate_fret/`
- Manifest: {src}`chisurf/plugins/burst/accurate_fret/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/accurate_fret/gui/accurate_fret.view.json`
