(plugin-tttr_header_edit)=
# TTTR Header editor

TTTR Header Editor plugin.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_header_edit` |
| Menu path | TTTR → Editor → **TTTR Header editor** |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| json_text | `json_text` | text |  |  | Live JSON view of the full TTTR header with the edited tags. |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_header_edit/`
- Manifest: `chisurf/plugins/tttr/tttr_header_edit/manifest.json`
- UI spec: `chisurf/plugins/tttr/tttr_header_edit/gui/header.view.json`
