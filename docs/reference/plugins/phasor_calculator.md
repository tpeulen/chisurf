---
type: Plugin Reference
title: Phasor-Calculator
description: 'Interactive phasor plot: universal semicircle with reference-lifetime grid/ticks, a FRET trajectory and a two-component mixing line. Declarative AutoForm view.'
resource: chisurf/plugins/calculator/phasor_calculator/
tags: [reference, plugins, phasor-calculator, main, tools, phasor-flim]
anchor: plugin-phasor_calculator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-phasor_calculator)=
# Phasor-Calculator

Interactive phasor plot: universal semicircle with reference-lifetime grid/ticks, a FRET trajectory and a two-component mixing line. Declarative AutoForm view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `phasor_calculator` |
| Menu path | Main → Tools → **Phasor-Calculator** |
| Categories | Main, Tools, Phasor-FLIM |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `phasor_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Frequency | `frequency` | float |  | 0.001 … 10000.0 (step 1.0) | Modulation frequency used to map lifetimes onto the phasor plot. |
| Harmonic | `harmonic` | int |  | 1 … 16 | Harmonic number; the effective frequency is frequency x harmonic. |
| Lifetimes (ns) | `taus` | str |  |  | Comma-separated reference lifetimes (ns) drawn as the iso-lifetime grid and semicircle ticks. |
| Iso-lifetime grid | `show_grid` | bool |  |  | Draw iso-phase and iso-modulation lines for the reference lifetimes. |
| Lifetime ticks | `show_ticks` | bool |  |  | Mark the reference lifetimes on the universal semicircle. |
| Polar grid | `show_polar_grid` | bool |  |  | Draw a polar coordinate grid (concentric circles + angular spokes) for reading phase and modulation. |
| FRET trajectory | `show_fret` | bool |  |  | Draw the quenched-donor FRET trajectory for the donor-only lifetime below. |
| Donor tau0 | `tau_d0` | float |  | 0.001 … 1000.0 | Donor-only lifetime for the FRET trajectory (tau_DA = tau_D0 * (1 - E)). |
| Two-component line | `show_component` | bool |  |  | Draw a mixing line between the two component phasors below. |
| g1 | `g1` | float |  | -0.1 … 1.1 (step 0.01) | Component 1 g. |
| s1 | `s1` | float |  | -0.1 … 0.7 (step 0.01) | Component 1 s. |
| g2 | `g2` | float |  | -0.1 … 1.1 (step 0.01) | Component 2 g. |
| s2 | `s2` | float |  | -0.1 … 0.7 (step 0.01) | Component 2 s. |
| Mixing region | `show_mixing` | bool |  |  | Draw the two-component mixing geometry and the fraction-weighted mixture point (uses g1/s1, g2/s2 as the components). |
| Fraction c1 | `frac1` | float |  | 0.0 … 1.0 (step 0.05) | Fractional intensity of component 1 (component 2 gets the remainder); sets the mixture point. |
| Cursor | `show_cursor` | bool |  |  | Draw a circular gating-cursor outline at the position below. |
| Cursor g | `cursor_g` | float |  | -0.1 … 1.1 (step 0.01) | Cursor centre g. |
| Cursor s | `cursor_s` | float |  | -0.1 … 0.7 (step 0.01) | Cursor centre s. |
| Cursor radius | `cursor_radius` | float |  | 0.001 … 0.5 (step 0.01) | Radius of the circular gating cursor. |

## Theory and workflow

- **Theory** — [FLIM and the phasor approach](/concepts/imaging_flim_phasor.md)

## Source

- Plugin package: `chisurf/plugins/calculator/phasor_calculator/`
- Manifest: {src}`chisurf/plugins/calculator/phasor_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/phasor_calculator/gui/phasor.view.json`
