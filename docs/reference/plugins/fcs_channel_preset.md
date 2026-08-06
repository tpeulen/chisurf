(plugin-fcs_channel_preset)=
# FCS Definitions

FCS channel definition plugin per detector setup

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_channel_preset` |
| Menu path | Setup → **FCS Definitions** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector setup | `current_setup` | choice |  | choices: `setup_names` | Detector setup whose logical channels are paired for correlation. Detector setups are managed in the channel-definition wizard. |
| Public | `is_public` | bool |  |  | When checked, this setup is visible to all users in the MMFDB. Only the owner can change this setting. |

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_channel_preset/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_channel_preset/manifest.json`
- UI spec: {src}`chisurf/plugins/fcs/fcs_channel_preset/gui/fcs_channel_preset.view.json`
