---
type: Plugin Documentation Standard
title: Plugin documentation standard
description: Required format for documenting individual ChiSurf plugins.
resource: chisurf/plugins/
tags: [plugins, documentation, manifest]
timestamp: '2026-07-05T00:00:00Z'
---

# Purpose

Each first-class plugin should have a local `README.md` that explains what the plugin
does, how users run it, and how maintainers verify or extend it. Group-level OKF pages
summarize domains; the plugin README is the source closest to the code.

# A guide and a `?` are the default, not an extra

Every plugin with a GUI ships **both**, and a plugin without them is unfinished
in the same way one without a `manifest.json` is.

They answer different questions and neither substitutes for the other. The `?`
modal says what a control *means*; the guide says which control to touch
**first**. A dense panel of well-documented settings is still unusable without
that second answer, which is why "the tooltips explain everything" is not a
reason to skip the tour.

The tour must **point at the real widgets and wait** (`"await"`), never press
them on the user's behalf: someone who watched a button being pressed has not
learned where it is. Where a tool needs data to demonstrate on, ship a demo the
plugin can generate itself rather than a tour that cannot be walked without the
user's own files. Any tool already calling `add_toolbar_help` picks the
**Guide** button up the moment `gui/guide.json` exists — there is no code to
write. Format and behaviour:
`chisurf/gui/widgets/tools/guided_tour.py`; worked example:
`chisurf/plugins/microscopy/img_flow/gui/guide.json`.

Help links are live. The modal routes a documentation page to the ChiSurf
documentation browser and a URL or DOI to the system browser, so a *Further
reading* list of bare backticked paths is a wasted cross-reference — write
`[title](docs/concepts/x.md)` and `[10.xxxx/yyy](https://doi.org/10.xxxx/yyy)`.

## Why this is written down

An audit of `chisurf/plugins/calculator/` on 2026-08-03 found **one plugin of
seven** with a guide and **two of seven** with a `?`. The rule existed and was
being missed silently, because nothing failed when a plugin shipped without
them. A gap that is already systemic is not fixed by adding the missing files to
the next plugin: it needs a guard that fails when a manifest declares a GUI
entrypoint and no `gui/guide.json` sits beside its `view.json`, seeded with the
current offenders as a **shrinking** allow-list. That is the shape that has
actually been driving the chiplot migration to completion
(`test/pyqtgraph_import_allowlist.txt`), rather than letting it stall.


# Required files

| File | Required when | Purpose |
| --- | --- | --- |
| `manifest.json` | Every discoverable plugin | Machine-readable identity, menu placement, entrypoints, RPC methods, state namespace, dependencies. |
| `README.md` | Every discoverable plugin | Human-readable plugin contract and workflow. |
| `gui/guide.json` | Every plugin with a GUI | A guided tour: ordered steps, each pointing at one real widget. |
| `help` section | Every plugin with a GUI | Long-form help behind the `?` modal, with live links to concepts and DOIs. |
| `docs/` | Complex plugins only | Detailed guides, contracts, screenshots, API/CLI references, migration notes. |
| `docs/STATUS.md` | Long-lived migrations/workflows | Current state, known gaps, verification evidence. |
| `docs/CONTRACT.md` | Plugins with API/RPC/CLI surfaces | Stable request/result/event contract. |

# README Format

Use this section order for every plugin README:

```markdown
# <Plugin Display Name>

Short one-paragraph summary: what the plugin does and who uses it.

## Status

| Field | Value |
| --- | --- |
| Plugin id | `<manifest id>` |
| Menu path | `<manifest display_name>` |
| Category | `<manifest categories>` |
| Maturity | `stable` / `active` / `experimental` / `deprecated` |
| Architecture | `legacy-qt` / `layered` / `client-server` / `declarative-ui` |
| MMFDB | `none` / `reads` / `writes` / `full provenance` |

## User Workflows

1. Primary workflow.
2. Secondary workflow.
3. Batch/headless workflow, if present.

## Inputs And Outputs

| Kind | Formats | Notes |
| --- | --- | --- |
| Input | `.ptu`, `.spc`, `.csv`, ... | Required assumptions. |
| Output | `.bur`, `.h5`, MMFDB artifact, ... | Where results are written. |

## UI Surface

Where it appears, key panels/actions, drag-drop behavior, and settings that persist.

## API, CLI, And RPC

| Surface | Entry point / method | Purpose |
| --- | --- | --- |
| Python API | `...` | Pure call or DTO contract. |
| CLI | `...` | Command and main options. |
| RPC | `plugin.method` | JSON-safe service call. |

## Architecture

Map the plugin's layers:
- `api/`: DTOs, serialization, public contract.
- `core/`: pure computation and IO helpers without Qt/server imports.
- `backend/`, `server/`, or `rpc/`: JSON-RPC adapters and service registration.
- `cli/`: command-line wrapper.
- `gui/`: Qt or AutoForm view only.
- `tests/` or `test/`: behavior and smoke tests.

State any known rule breaks explicitly.

## MMFDB And Provenance

Say whether the plugin reads/writes MMFDB, which artifact kinds it creates, which
operation type it records, and whether registration is best-effort or fail-loud.

## Verification

List the focused tests and any manual checks:

```bash
PYTHONPATH="modules/chinet:modules/imp-tricks/src:." python3 -m pytest <tests>
```

## Limitations And Open Work

Short bullets only. Link PRDs or TODOs instead of writing long plans inline.

## Related Files

- `manifest.json`
- `api/...`
- `backend/...`
- `gui/...`
- `tests/...`
```

# Optional docs folder format

Use `docs/` when a README would become too long. Keep filenames predictable:

| File | Contents |
| --- | --- |
| `docs/CONTRACT.md` | DTOs, JSON schemas, RPC methods, events, state patches. |
| `docs/CLI.md` | Commands, examples, exit behavior. |
| `docs/API.md` | Python API or service API reference. |
| `docs/WORKFLOWS.md` | User workflows with input/output examples. |
| `docs/STATUS.md` | Completed work, remaining gaps, verification. |
| `docs/MIGRATION.md` | Legacy-to-standard migration notes. |

# Documentation maturity labels

| Label | Meaning |
| --- | --- |
| `none` | No README and no docs folder. |
| `stub` | README exists but only gives a short feature list or launch note. |
| `usable` | README covers workflows, inputs/outputs, and tests. |
| `contracted` | README plus API/RPC/CLI contract docs for nontrivial surfaces. |
| `reference` | Complete docs plus current status and migration/extension guidance. |

# Minimum Acceptance

A plugin documentation update is complete when:

- `README.md` follows the required section order.
- The README matches `manifest.json` id, display name, entrypoints, and RPC method names.
- Inputs, outputs, and persistence side effects are explicit.
- Tests or manual verification commands are listed.
- Known gaps are stated without claiming completion.
