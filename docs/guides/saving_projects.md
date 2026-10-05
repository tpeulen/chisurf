---
type: Guide
title: Saving and reopening projects
description: Save complete ChiSurf analysis sessions without requiring MMFDB.
tags: [guides, project, persistence, mmfdb]
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
2. Use **Save Project As** (`Ctrl+Shift+S`) to choose a different portable
   destination. This writes the current live analysis, not an earlier database
   version.
3. Reopen the `.cs.pto` through the project-opening action. Confirm that the
   imported data, fit windows and parameter settings are present before
   continuing the analysis.

Saving an individual fit is a separate operation (`Ctrl+Alt+S`), not a
substitute for saving the entire project.

The project container embeds its recorded scientific arrays. Reopening does
not re-read the original measurement files or reconstruct science from their
filenames. Supported built-in reader configuration is recorded separately;
reader controllers and database connections are runtime resources, not
portable project state. Unsupported scientific state causes a visible error
instead of being omitted from an apparently successful save.

## Close, replace or reset the session

Before a nonempty project is discarded, ChiSurf offers:

- **Save:** continue only if saving explicitly succeeds.
- **Don't Save:** discard the project without saving it.
- **Cancel:** leave the current session open. This is the default selection.

Cancelling the save-file chooser or encountering a save error also keeps the
session open. The same decision protects project replacement and reset.

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
