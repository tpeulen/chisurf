(plugin-tttr_splitter)=
# Split/Convert

TTTR Split / Convert plugin.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_splitter` |
| Menu path | TTTR → Editor → **Split/Convert** |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Input / Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Input format | `input_format` | choice |  | choices: `input_format_options` | Force an input container type, or Auto to detect it from the file. |
| Output format | `output_format` | choice |  | choices: `output_format_options` | Container format written to disk; differs from input ⇒ transcode. |

### Split options

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Photons/file | `photons_per_file_k` | int |  | 100 … 999999999 (step 100) | Photons per output file (×1000) when 'Split into files' is on. |
| µ-time binning | `microtime_binning` | choice |  | choices: 1, 2, 4, 8, 16 | Micro-time binning factor (clamped to ≥8 for SPC containers). |

### Batch

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| batch_files | `batch_files` | path_list |  |  |  |
| Use file's parent as output folder | `batch_use_parent` | bool |  |  |  |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_splitter/`
- Manifest: `chisurf/plugins/tttr/tttr_splitter/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_splitter/gui/splitter.view.json`
