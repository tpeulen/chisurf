---
type: Plugin Reference
title: ALEX Suite
description: 'The classic ALEX-Suite workflow, as a linear ChiSurf pipeline: files, µs-ALEX alternation, burst search, background, accurate FRET, E-S. Plus the titration/stack-plot analysis and the ALEX-Suite CSV export. Writes the same .pto container and burst companions as the PIE burst workflow.'
resource: chisurf/plugins/burst/alex_suite/
tags: [reference, plugins, alex-suite, spectroscopy, single-molecule, fret]
anchor: plugin-alex_suite
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-alex_suite)=
# ALEX Suite

The classic ALEX-Suite workflow, as a linear ChiSurf pipeline: files, µs-ALEX alternation, burst search, background, accurate FRET, E-S. Plus the titration/stack-plot analysis and the ALEX-Suite CSV export. Writes the same .pto container and burst companions as the PIE burst workflow.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `alex_suite` |
| Menu path | Spectroscopy → Single-Molecule → **ALEX Suite** |
| Categories | Spectroscopy, Single-Molecule, FRET |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `alex_suite` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Fit

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Populations | `n_populations` | int |  | 1 … 6 (step 1) | How many FRET populations the whole series is described with. Two is the usual case: free and bound. |
| Isotherm | `binding_model` | choice |  | choices: `binding_model_options` | hill fits the cooperativity too; one_site holds the Hill coefficient at 1. |
| Unit | `concentration_unit` | str |  |  | Only a label — the fit never converts. The K_d is reported in this unit. |
| Fix peak positions | `fix_peak_positions` | bool |  |  | Hold the shared centres and widths at their starting values instead of fitting them. Use it when a control measurement has already established where the populations are. |

### Burst filters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Min. photons | `min_photons` | int |  | 0 … 100000 (step 10) | Bursts with fewer photons than this are dropped, in every condition alike. |
| E bins | `bins` | int |  | 11 … 501 (step 10) | Bins of the efficiency histogram. |
| S gate from | `s_low` | float |  | -1.0 … 2.0 (step 0.05) | Only bursts inside this stoichiometry band enter the E histogram — the gate that removes donor-only and acceptor-only species. |
| S gate to | `s_high` | float |  | -1.0 … 2.0 (step 0.05) | Upper edge of the stoichiometry gate. |
| γ | `gamma` | float |  | 0.0 … 100.0 (step 0.05) | Detection/quantum-yield ratio. Take it from the Accurate FRET step. |
| β | `beta` | float |  | 0.0 … 100.0 (step 0.05) | Excitation-flux ratio, which enters the stoichiometry only. |

## Theory and workflow

- **Workflow** — [Coming from ALEX-Suite](/guides/66_alex_suite.md)

## Source

- Plugin package: `chisurf/plugins/burst/alex_suite/`
- Manifest: {src}`chisurf/plugins/burst/alex_suite/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/alex_suite/gui/titration.view.json`
