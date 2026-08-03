(plugin-burst_state_mle)=
# MLE per State

Burst- and state-wise maximum-likelihood lifetime fitting of an H2MM analysis: one decay per (burst, state, colour), written as per-state .b?4 folders.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_state_mle` |
| Menu path | Spectroscopy → Single-Molecule → **MLE per State** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| State namespace | `burst_state_mle` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/burst/burst_state_mle/`
- Manifest: `chisurf/plugins/burst/burst_state_mle/manifest.json`
