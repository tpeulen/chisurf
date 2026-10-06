---
type: Plugin Reference
title: Microtime Shifter
description: Apply global and per-channel micro-time shifts to TTTR files.
resource: chisurf/plugins/tttr/tttr_microtime_shifter/
tags: [reference, plugins, microtime-shifter, tools, tttr, editor]
anchor: plugin-microtime_shifter
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-microtime_shifter)=
# Microtime Shifter

Apply global and per-channel micro-time shifts to TTTR files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `microtime_shifter` |
| Menu path | Tools → TTTR → **Microtime Shifter** |
| Categories | Tools, TTTR, Editor |
| Version | 2.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `microtime_shifter` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Sample

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Sample name | `name` | text |  |  | Sample identity recorded with the shifted files' provenance. |
| Description | `description` | text |  |  | Free-text description of the sample and the experiment. |
| Buffer | `buffer_description` | text |  |  | Buffer composition recorded with the sample. |

### Entity

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Entity name | `entity_name` | text |  |  | Name of the labelled molecule. |
| Entity type | `entity_type` | text |  |  | Kind of molecule (protein, DNA, RNA ...). |
| Construct sequence | `sequence` | text |  |  | Sequence of the measured construct; compared with the reference to document mutations. |
| UniProt accession | `uniprot_accession` | text |  |  | UniProt entry the reference sequence is fetched from. |
| PDB ID | `pdb_id` | text |  |  | PDB entry of the structure. |
| PDB chain | `pdb_chain_id` | text |  |  | Chain of the PDB entry. |
| Organism | `organism` | text |  |  | Source organism. |
| Reference sequence | `reference_sequence` | text |  |  | Reference (wild-type) sequence, fetched from UniProt or typed. |

### Probes

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Donor dye | `donor` | text |  |  | Name of the donor probe on the first entity. |
| Acceptor dye | `acceptor` | text |  |  | Name of the acceptor probe on the first entity. |

### Alignment

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show trigger lines | `show_trigger` | bool |  |  | Display the draggable count threshold (yellow) and target bin (green) on the histogram. |
| Log Y | `log_y` | bool |  |  | Display histogram photon counts on a logarithmic axis. |
| Trigger level | `trigger_level` | int |  | 1 … | Count threshold: auto-align finds, per detector, the first bin up to the peak at or above this level (the rising edge). |
| Target bin | `trigger_position` | int |  | 0 … | Auto-align shifts each detector's rising edge to this micro-time bin. |

### Shifts

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Global shift | `global_shift` | int |  |  | Added to every routing channel's shift; the micro-times wrap modulo the bin count. |

### Save

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Batch folder | `output_folder` | text |  |  | Directory for a batch of shifted files; the inputs stay unchanged. |

### MMFDB

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Sample ID | `sample_id` | text |  |  | The MMFDB sample that owns the registered shifted files; choose one from the list or enter its identifier. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `microtime_shift.apply` | no | Apply micro-time shifts to TTTR files. |
| `microtime_shift.load_metadata` | no | Return routing channels and n_mt for a file. |
| `microtime_shift.identify` | no | Look up a file in the MMFDB object store. |
| `microtime_shift.contract.describe` | no | Return the Micro-time Shifter workflow contract. |

## Theory and workflow

- **Theory** — [Micro-time shift: putting detectors on one time axis](/concepts/microtime_shift.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_microtime_shifter/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_microtime_shifter/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_microtime_shifter/gui/sample.view.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_microtime_shifter/gui/shifter.view.json`
