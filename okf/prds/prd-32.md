---
type: PRD
prd: "32"
title: "PRD-32: Acquisition Standard Output Folder"
description: Adds a single user-configurable standard output folder to acquisition so new measurements have a predictable save location.
status: done
phase: "cross-cutting"
resource: chisurf/plugins/core/acq
tags: [prd, acquisition]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Gives acquisition a single, user-configurable standard output folder so new measurements have a predictable save location without the user picking a directory every time. The setting is made explicit in the Setup surface, persisted in `gui.acquisition`, used to prefill the acquisition dock, and resolved as the default runtime destination (creating the folder before a run writes files). Intentionally narrow: no direct MMFDB registration, no device-format changes, no project-scoped output-tree policy.

# Status
Done. The runtime path was already implemented (the acquisition dock prefills
from `_default_acquisition_output_path()`, resolves the folder at start when the
dock field is blank, and `mkdir`s the destination before writing). The remaining
gap — the setting being read but never declared — is closed: `gui.acquisition.output_path`
is now a documented key in the default settings YAML (empty string ⇒ fall back to
`<working_path>/acquisition`), and the generic Setup settings editor renders it
with a directory picker (`SettingsDelegate._is_folder_setting` /
`_create_folder_editor` / `_browse_folder`).

# Goal

Give acquisition a single, user-configurable standard output folder so new
measurements have a predictable save location without making the user pick a
directory every time.

# Why

The current acquisition flow already has an ad-hoc output-path field in the dock,
but the setting is not defined in the central setup surface. That makes the save
location easy to miss and hard to standardize across sessions.

This PRD makes the setting explicit in the setup UI and treats it as the default
runtime destination for acquisition output.

# Scope

- Add a standard output-folder field to acquisition settings in Setup.
- Persist the setting in `gui.acquisition`.
- Prefill the acquisition dock from the saved setting.
- Resolve the output folder at acquisition start if the dock is empty.
- Create the destination folder before the run writes files.

# Non-goals

- Direct MMFDB registration.
- Changing the device-specific file formats.
- Introducing a new project-scoped output tree policy.

# Definition of Done

- [x] Acquisition settings expose a standard output-folder field.
- [x] The folder persists across restarts.
- [x] The acquisition dock defaults to the saved folder.
- [x] Acquisition start uses the saved folder when the dock field is empty.
- [x] The output folder is created before a run writes files.

# Notes

This PRD is intentionally narrow. The MMFDB alternative is a separate, more
complex PRD ([PRD-33](prd-33.md)) because it needs sample ownership and
provenance decisions first.

# Relationships
- Deliberately kept separate from [PRD-33](prd-33.md) (acquisition→MMFDB registration), which remains the more complex database path requiring sample ownership/provenance decisions first.
- Relates to acquisition/acq and the [plugin system](/architecture/plugin-system.md).
