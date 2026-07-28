---
type: Reference
title: Use case — Save, version, export and restore a ChiSurf project
description: Persist a whole analysis session as a versioned MMFDB project, export it as a .csp archive, import it back, and restore it into a fresh ChiSurf.
tags: [usecase, project, persistence, mmfdb, versioning, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: save, version, export and restore a project

**Goal:** the workflow that surrounds every other one — a user has spent an hour
loading data and optimising a fit, and wants to *stop*, come back tomorrow, and
find the session as they left it: the same datasets, the same fits, the same
parameter values. Along the way they want a version history ("the fit I had
before I added the second lifetime"), and a single file they can hand to a
colleague or attach to a manuscript.

ChiSurf stores projects in **MMFDB**, not in a flat file: each *Save* writes a new
immutable **version** (an MMFDB `project` operation) whose datasets are decomposed
into content-addressed object-store blobs (the raw source file *and* a derived
processed-data JSON), with a provenance DAG linking them. `.csp` is the export
container for that version.

**Data:** `test/data/tcspc/ibh_sample/Decay_577D.txt` (decay) and `Prompt.txt`
(IRF) — any loaded dataset works; the project is the subject, not the science.

## Steps

1. Start ChiSurf and build a session worth keeping: **Read data** dock →
   **Experiment** `TCSPC`, **File type** `TXT/CSV`, load `Decay_577D.txt` and
   `Prompt.txt`, select the decay in the **Data** tab, pick `Lifetime ` in the
   model combo, click **Add fit**, assign `Prompt.txt` as the IRF in the
   *Convolve* section, and click **Fit**.
2. Open the project browser: **File → Open Project…** (or the *Tools → Open
   Project* plugin). A separate window opens with a toolbar —
   **Open / Restore · Save Current Project · Export .csp · Import Project ·
   Delete Version · Refresh** — a search box, a *Show public* check box, and a
   two-level tree (project → its versions).
3. Click **Save Current Project**. A modal asks for **Project name**,
   **Visibility** (Private / Public) and free-text **Notes**; type a name and a
   note describing the state, and confirm. The tree gains a project row.
4. Change the analysis — e.g. click the green **add** button in *Lifetimes* to
   add a second component and **Fit** again — then click **Save Current Project**
   a second time. The dialog now reads *Save New Version*, the name field is
   greyed out (you are versioning the same project, not creating a new one), and
   only the notes are editable. The tree's version count increases.
5. Expand the project row and read the version history: `v1`, `v2`, … with owner,
   status, dataset and fit counts, creation time and the note you typed.
6. Select one version row and click **Export .csp**; choose a path. The archive
   is written (~100–200 kB for this session: the source text files plus the
   derived JSON and the fit records).
7. Click **Import Project** and pick a `.csp`. ChiSurf previews the archive
   first: if any of its IDs already exist in the database a *Collision Warning*
   dialog lists them and offers to remap; otherwise a plain confirmation states
   how many operations / artifacts / objects will be imported.
8. Quit ChiSurf and start it again (or use a colleague's machine after importing
   the `.csp`). Open the project browser, select the project (or one specific
   version row) and click **Open / Restore**.
9. Confirm the session is back: the datasets are in the **Data** tab with their
   original names, the fit sub-window reopens with its model and χ²ᵣ, and the
   window is bound to that project so the next **Save** appends a version.
10. Housekeeping: type in the search box to filter projects by name, toggle
    *Show public* to hide other users' shared projects, and select an obsolete
    version row and click **Delete Version** (soft-delete, with a confirmation).

## Expected

- Step 3 creates **exactly one** version; step 4 creates exactly one more.
- Step 6 writes a `.csp` that round-trips: step 7 re-creates an independent copy
  with its own project id and its own version numbering.
- Step 8/9 restore the *whole* session — every dataset with its full x/y arrays,
  its original name and its reader settings, and every fit with its model,
  parameter values and fit range — so that clicking **Fit** immediately
  reproduces the χ²ᵣ that was saved.
- Any part that cannot be restored is reported to the user, not just logged.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, isolated
`CHISURF_SETTINGS_DIR`/`MMFDB_SETTINGS_DIR` so the user's real database was never
touched) through the real main window and the real `ProjectBrowserTool`:
toolbar buttons `.click()`-ed, the modal `SaveProjectDialog` filled in and
accepted, the file dialogs redirected, the tree selection driven, screenshots
taken and read at each step.

**The storage layer is good; the round-trip is not.** Saving works and is fast
(~0.8 s per version); the object store deduplicates correctly across versions
(the second save logged five `Deduplicated object … refcount++` lines and stored
nothing new); export produced a 116–201 kB `.csp` in ~0.8 s; the version tree,
search, *Show public*, soft-delete with confirmation and the "nothing selected"
guards on Open / Export / Delete all behave. Saving with an empty name is
refused with *"Project name is missing."*

**Restoring a saved project loses all of the data and all of the fits.** In a
fresh session, restoring the newest version of a project that held 3 datasets and
1 fit produced three datasets named `ds001`, `ds002` and `Global Dataset`, each
with **zero points** — the file names, the reader settings and the 4 094-channel
arrays were all dropped — and **zero fits**. The cause is a save/restore schema
asymmetry: the archiver decomposes each dataset into the MMFDB derived-data
schema (`{schema_version, data_type, curves: [{name, x, y, ex, ey}],
reader_settings, source_object_uuids}`) but the restore hands that storage form
straight back as the project payload, while `load_project_payload` expects
ChiSurf's flat `{name, filename, x, y, data_reader, experiment_name}` shape. The
arrays *are* in the database — reading the version's blob shows the base64 x/y —
they are simply never re-composed. The fit then cannot be rebuilt on empty data
(`Convolve.__init__` → `dt = data.dx[0]` → `IndexError`), and that failure is a
`log.warning` only: the browser closes itself and reports nothing, so the user
sees an apparently successful "Open Project" that silently yields an empty
workspace. This affects **File → Save Project / Open Project** too — they call
the same client. See RF-616.

**Every toolbar button fires its handler twice.** `_add_toolbar_button` connects
`clicked` to the slot and `_connect_signals` connects the same six buttons again;
`_save_btn.receivers(clicked)` is **2**. A/B-tested on a clean database: one
`.click()` on *Save Current Project* → **two** versions (v1 and v2, identical
notes, same second); one direct `_on_save()` call → one version. So a user who
clicks Save twice during a session ends up with a four-entry history, and the
*Exported* / *Saved* confirmation appears twice. Screenshot
`20_browser_fresh_session.png` shows the artefact plainly: v1/v2 at 01:12:02 and
v3/v4 at 01:12:05 for two clicks. See RF-617.

**Restoring a project that contains a fit segfaults the application** — three
runs out of three, in both a wiped session and a brand-new one, a few hundred ms
after `_on_open` returns, inside Qt event processing with no Python frame on the
stack. Restoring a *fit-free* project of the same database survives, which points
at the deferred `restore_gui_from_fits(fit_uids)` running for a fit that
`add_fit` never created. See RF-618.

**Re-importing an archive into the database it came from does not produce an
independent copy.** Importing `qa4.csp` (exported from project
`proj_a757ffc303c5` v1) reported *"New project ID: proj_a757ffc303c5 — Version:
v1"* — the same project id — and the tree then showed that project with **two
rows both labelled `v1`**, one of them with the malformed id `ver__3756e9b2714f`
(double underscore). Confirmed in the database: two `project` operations with
`project_id = proj_a757ffc303c5` and `version_number = 1`. The collision dialog
had listed the operation and artifacts and promised to remap them; the version
*number* and the project id were not remapped. See RF-619.

**The "Remap & Import" button reads "Remap _Import".** The ampersand is consumed
as a Qt mnemonic (screenshot `30_collision_dialog.png`). See RF-620.

Screenshots inspected: `02_browser_empty.png`, `04_browser_expanded.png`,
`20_browser_fresh_session.png`, `30_collision_dialog.png`, `31_after_import.png`,
`01_main_after_fit.png`.

## UX / UI suggestions

- **The tree header clips descenders.** At the default row height the header
  reads "Proiect / Version" and "Visibilitv" — the `j` and `y` are cut off in
  every screenshot. Give the header a couple of pixels of extra height.
- **Columns are sized while the project rows are collapsed**, so nothing in a
  version row is measured: *Status* is permanently truncated to `succeed…` and
  *Notes* to `two-expone…` while two thirds of the window is empty space.
  Re-run `resizeColumnToContents` after `expandAll`, or size on the child rows.
- **The empty state is a blank rectangle.** A first-time user opening *File →
  Open Project…* sees a tree with headers and nothing else, and no hint that
  *Save Current Project* is what fills it. Put a placeholder line in the
  viewport ("No projects yet — use *Save Current Project* to store this
  session").
- **The version-control features have no UI.** The manifest exposes
  `create_branch`, `list_branches` and `version_graph` over RPC, but the window
  has no branch column, no branch button and no way to see the version DAG — so
  a project that *has* branches renders as an undifferentiated flat list of
  versions. Either surface a Branch column plus a graph view, or drop the claim
  of "version control" from the plugin description.
- **The Save dialog does not say what it is about to do.** On the second save it
  is titled *Save New Version* with the name greyed out, but it never shows
  *which* version number will be created, nor the parent version it descends
  from, nor offers "Save as a new project" for a user who wants to fork rather
  than version.
- **The collision dialog speaks in internal ids.** It lists
  `dataset:ver_befcb515646f:ds000` and `src_b98fdcbe-fe9` — nothing a user can
  act on. Show the project name, version number and dataset names, and say what
  "remap" will do to them. Its fixed 500×300 minimum also clips the last
  category ("objects (3):" is cut off at the bottom edge).
- **Restore gives no progress and no summary.** It takes ~3 s with the window
  frozen, then the browser simply closes. A short summary — "restored 3
  datasets, 1 fit; 1 fit could not be rebuilt" — would have surfaced RF-616 to
  the user instead of hiding it in the log.
- **Version rows leave *Visibility* blank** even though the value is per-project
  and known; either fill it in or drop the column from the child rows.

## Bugs filed

- RF-616 — project restore returns datasets in the MMFDB storage schema, so every
  restored dataset is empty and every fit is silently dropped.
- RF-617 — every Project Browser toolbar button is connected twice, so one *Save*
  click writes two versions.
- RF-618 — restoring a project that contains a fit segfaults ChiSurf.
- RF-619 — importing a `.csp` back into its source database creates a duplicate
  version number in the same project instead of an independent copy.
- RF-620 — the collision dialog's "Remap & Import" button renders as
  "Remap _Import".
