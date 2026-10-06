---
type: Plugin Reference
title: VV/VH G-Factor Calculator
description: Calculate detector G-factors using tail-matching on VV/VH format files.
resource: chisurf/plugins/vv_vh_g_factor/
tags: [reference, plugins, vv-vh-g-factor, spectroscopy, fluorescence-decay]
anchor: plugin-vv_vh_g_factor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-vv_vh_g_factor)=
# VV/VH G-Factor Calculator

Calculate detector G-factors using tail-matching on VV/VH format files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `vv_vh_g_factor` |
| Menu path | Spectroscopy → Fluorescence decay → **VV/VH G-Factor Calculator** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `vv_vh_g_factor` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Channels

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Flip VV/VH | `flip` | bool |  |  | The file has VV and VH swapped: exchange the parallel and perpendicular channels consistently across the calculation and the plots. |
| Background correction | `background` | bool |  |  | Subtract separate channel means of the background region before matching the tails. |

### Tail matching

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Tail start (bin) | `tail_start` | float |  | 0.0 … 1000000.0 (step 1.0) | First TAC bin of the tail region used to match the reference dye channels. |
| Tail stop (bin) | `tail_stop` | float |  | 0.0 … 1000000.0 (step 1.0) | Last TAC bin of the tail region. |
| Background start (bin) | `background_start` | float |  | 0.0 … 1000000.0 (step 1.0) | First TAC bin of the signal-free region used for each channel's background (needs Background correction). |
| Background stop (bin) | `background_stop` | float |  | 0.0 … 1000000.0 (step 1.0) | Last TAC bin of the background region (needs Background correction). |
| VH shift (bins) | `shift` | float |  | -1000.0 … 1000.0 (step 0.1) | Shift the VH time axis by this many TAC bins, fractional bins included (the Qt tool's 'Shift Perpendicular Decay'). |

### Manual G

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Manual G | `manual_g` | bool |  |  | Use the G-factor typed below instead of the calculated one (the Qt tool does this when its G field is edited). |
| G used | `g_override` | float |  | 0.001 … 100.0 (step 0.01) | Positive detector sensitivity ratio used for the corrected anisotropy. |

### Slow-reference mixing

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| dt (ns/bin) | `fp_dt_ns` | float |  | 0.0001 … 1000.0 (step 0.01) | Nanoseconds per slow-reference bin. |
| rho (ns) | `fp_rho_ns` | float |  | 0.001 … 100000.0 (step 1.0) | Rotational correlation time used in the Perrin relation. |
| r0 | `fp_r0` | float |  | -0.2 … 0.4 (step 0.01) | Limiting (fundamental) anisotropy of the reference fluorophore. |
| Manual lifetime | `manual_tau` | bool |  |  | Override the intensity first-moment lifetime of the slow reference. |
| tau (ns) | `tau_override` | float |  | 0.0 … 100000.0 (step 0.1) | Lifetime used in place of the estimate. |
| Manual target rS | `manual_rs` | bool |  |  | Override the Perrin steady-state anisotropy target. |
| Target rS | `rs_override` | float |  | -0.2 … 0.4 (step 0.01) | Steady-state anisotropy the slow reference should have. |
| Manual l1 = l2 | `manual_l` | bool |  |  | Override the single linked polarization-mixing parameter. |
| l1 = l2 | `l_override` | float |  | 0.0 … 0.5 (step 0.01) | Linked mixing parameter applied to l1 and l2. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `vv_vh_g_factor.calculate` | no | Calculate G-factor based on tail matching for VV/VH decays. |
| `vv_vh_g_factor.perrin_steady_state` | no | Perrin steady-state anisotropy for a sphere. |
| `vv_vh_g_factor.solve_linked_l` | no | Solve for the linked l1=l2 mixing parameter. |
| `vv_vh_g_factor.archive_g_factor` | no | Register reference decay and archive G-factor calibration in MMFDB. |

## Theory and workflow

- **Theory** — [Time-resolved fluorescence anisotropy](/concepts/anisotropy.md)
- **Workflow** — [Fluorescence lifetime and anisotropy decay fitting](/guides/10_lifetime_anisotropy_fitting.md)

## Source

- Plugin package: `chisurf/plugins/vv_vh_g_factor/`
- Manifest: {src}`chisurf/plugins/vv_vh_g_factor/manifest.json`
- UI spec: {src}`chisurf/plugins/vv_vh_g_factor/gui/gfactor_emtk.view.json`
