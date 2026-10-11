---
type: Guide
title: Saving and reopening projects
description: Save complete ChiSurf analysis sessions without requiring MMFDB.
tags: [guides, database, mmfdb]
---

# Saving and reopening projects

```{warning}
This replacement is still undergoing acceptance testing. Fresh independent
review reproduced public API guard/UID ownership gaps, attachment loss on file
resave, rejected shipped TTTR/DEER readers, forced local import authentication
and non-atomic browser export. Preserve the original raw data and existing
analysis files; do not rely on the new project snapshot as the sole copy of an
analysis until those gates and independent review pass.
```

A project saves the scientific session, not just the selected fit: imported
curves and groups, masks, fits and fit ranges, model settings, parameters and
links, supporting curves such as IRFs, and the supported window state.

## Choose the destination

MMFDB is optional. With no configured MMFDB deployment, or only the desktop's
embedded/bootstrap database, ordinary project saving uses a **`.cs.pto` file**.
You do not need to start or log into MMFDB to save and reopen that file.

When an authenticated MMFDB deployment is explicitly configured through the
remote client settings, ordinary Save stores a project version there. A
standalone service on localhost counts as a configured deployment; the
hostname alone does not distinguish it from the desktop seed. Connection,
authentication and storage errors are reported, not silently redirected to a
local file. **Save As** remains the explicit portable-file operation.

## Save a portable project

1. Use **Save Project** (`Ctrl+S`). In file mode, choose a name ending in
   `.cs.pto` the first time. Later saves reuse the current destination.
2. Use **Export Project…** (`Ctrl+Shift+S`) to save under a different portable
   destination, which becomes the project's file. This writes the current live
   analysis, not an earlier database version.
3. Reopen the `.cs.pto` with **Open Project…** (or **Recent Projects**). Confirm
   that the imported data, fit windows and parameter settings are present before
   continuing the analysis.

Saving an individual fit is a separate operation (`Ctrl+Alt+S`), not a
substitute for saving the entire project.

The project container embeds its recorded scientific arrays. Reopening does
not re-read the original measurement files or reconstruct science from their
filenames. Supported built-in reader configuration is recorded separately;
reader controllers and database connections are runtime resources, not
portable project state. Unsupported scientific state causes a visible error
instead of being omitted from an apparently successful save.

## Autosave

While a project holds data, ChiSurf writes a silent copy of it every two
minutes. The copy sits beside the saved project as `<name>.autosave.cs.pto`;
before the first save it goes to `autosave/untitled.autosave.cs.pto` in the
working folder. It is rewritten only when the analysis changed since the last
copy, it never opens a dialog, and the next explicit **Save** deletes it. An
autosave is not a save: the project still counts as unsaved, and closing it
still asks. To recover after a crash, open the `.autosave.cs.pto` file like
any project and save it under a normal name.

The interval and the switch are the `project.autosave` settings
(`interval_s`, in seconds; `enabled`, true or false). Changes apply at the next
start.

## Close, replace or reset the session

Before a nonempty project is discarded, ChiSurf offers:

- **Save:** continue only if saving explicitly succeeds.
- **Don't Save:** discard the project without saving it.
- **Cancel:** leave the current session open. This is the default selection.

Cancelling the save-file chooser or encountering a save error also keeps the
session open. The same decision protects project replacement and reset.

## In the native window

The native window (`python -m chisurf --emtk-shell`, opt-in while it replaces
the Qt window) has the same **File** menu and shortcuts: **Save Project**
(`Ctrl+S`), **Export Project…** (`Ctrl+Shift+S`, save under a new file), **Open
Project…**, **Import Project…**, **Close Project**, **Reinitialize** (`Ctrl+R`),
**Recent Projects** and **Quit** (`Ctrl+Q`); **View** has **Undo** (`Ctrl+Z`)
and **Redo** (`Ctrl+Y`). Closing the window, quitting, opening or closing a
project ask the Save / Don't Save / Cancel question once, and only when the
session has unsaved work; an empty session asks "Quit ChiSurf?" instead. The
autosave writes the same `.autosave.cs.pto` copy. A fit window's **×** asks,
then removes the fit, as in the Qt window.

**File ▸ Fits** saves and loads single fits as the Qt window does: **Current Fit**
(`Ctrl+Alt+S`), **All Fits** and **Load Fit** (see
[Saving & exporting the results](../manual/saving__exporting_the_results.md)).
**Macro ▸ Record** and **Macro ▸ Run Macro…** work as in the Qt window (see
[the console guide](59_console.md)). Undo and redo cover the session since it
was opened; the undo history is not written into the project file.

## Failures do not mean an empty project

An invalid or corrupt project is rejected before replacing the active
scientific objects. Failed restoration preserves the old project state and
identity. File saving validates a temporary candidate before publishing it;
failed validation or replacement preserves the previous valid file.

The current pre-release project schema is version 5. Old `.csp`/ZIP projects
and earlier project schemas are not supported by this replacement. Do not
rename an old archive to `.cs.pto` to try to convert it.

For architecture and verification details, see the project-persistence record
in `okf/subsystems/project-persistence.md`.

The native Project Browser starts at 1200×800. Its project, version and artifact
views use the same persisted data; a saved custom window size takes precedence.

## Theory

- [The photon container](../concepts/photon_container.md): how a measurement and its results are stored together.
- [The measurement database](../concepts/measurement_database.md): the optional provenance store a project does not require.
