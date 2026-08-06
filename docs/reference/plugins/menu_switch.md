(plugin-menu_switch)=
# Menu Switch

Menu Switch

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `menu_switch` |
| Menu path | Setup → **Menu Switch** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/menu_switch/`
- Manifest: `chisurf/plugins/core/menu_switch/manifest.json`
