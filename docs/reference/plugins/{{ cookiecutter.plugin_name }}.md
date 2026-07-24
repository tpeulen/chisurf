(plugin-{{ cookiecutter.plugin_name }})=
# {{ cookiecutter.plugin_display_name }}

{{ cookiecutter.plugin_description }}

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `{{ cookiecutter.plugin_name }}` |
| Menu path | {{ cookiecutter.plugin_category }} → **{{ cookiecutter.plugin_display_name }}** |
| Categories | {{ cookiecutter.plugin_category }} |
| Version | 1.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `{{ cookiecutter.plugin_name }}` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/cookiecutter-chisurf-plugin/{{cookiecutter.plugin_name}}/`
- Manifest: `chisurf/plugins/cookiecutter-chisurf-plugin/{{cookiecutter.plugin_name}}/manifest.json`
