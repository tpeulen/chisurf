(plugin-quenching_estimator)=
# QuEst

Structure-based simulation of dynamic PET quenching and FRET for dyes tethered to proteins by flexible linkers. The science lives in the `quest` package; this plugin is the ChiSurf-side shell.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `quenching_estimator` |
| Menu path | Structure → Computation → **QuEst** |
| Categories | Structure, Computation |
| Version | 19.8.13 |
| Surfaces | cli, gui, services |
| State namespace | `quenching_estimator` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `quest.template` | no | Return a minimal valid project, optionally with FRET. |
| `quest.validate` | no | Check a project and report why it is malformed. |
| `quest.simulate` | yes | Run one simulation and return the decay and derived metrics. |
| `quest.scan` | yes | Simulate a set of labeling sites and return one record each. |
| `quest.parameter_catalog` | no | Return the parameter catalog (labels, units, help), optionally translated. |
| `quest.dyes.list` | no | Return the dye presets. |
| `quest.dyes.save` | no | Add or replace a dye preset. |
| `quest.quenching_defaults` | no | Return the residue-type PET chemistry defaults. |
| `quest.structure.metadata` | no | Return the chains, residues and atoms of a structure file. |
| `quest.runs.list` | no | Return run-artefact summaries, newest first. |
| `quest.runs.get` | no | Return a finished run's result. |
| `quest.locales` | no | List the languages QuEst's labels and help text are available in. |
| `quest.contract.describe` | no | Return the contract: methods, schemas, error codes and where serialization happens. |
| `quest.jobs.list` | no | Return the running and recent operations. |
| `quest.jobs.get` | no | Return one operation's status and progress. |
| `quest.jobs.cancel` | no | Ask a running operation to stop at its next checkpoint. |

## Source

- Plugin package: `chisurf/plugins/quenching_estimator/`
- Manifest: `chisurf/plugins/quenching_estimator/manifest.json`
