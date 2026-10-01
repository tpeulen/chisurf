# Wave 3 plan — splitting the larger plugins into agent-sized ports

Companion to [`PRD-153`](../../prds/prd-153.md). Waves 0–2 (`pch`, `region_mle`, `flc-2d`) showed
what the procedure can carry: a Type B port with a spec, a model, two or three plots and a few
dialogs, in about 20–25 minutes of agent time. The plugins below are bigger, so each is cut into
**task cards**: one card = one PRD-153 port cycle (claim, baseline, model, spec, app, tests,
evidence, report, three commits), with its own acceptance and its own `okf/plugins/emtk-ports/<id>/`
folder section. A card never changes the plugin's science, backend or RPC surface.

Rules that apply to every card (in addition to PRD-153):

* **The manifest switch comes once per plugin**, after the last card of that plugin is accepted.
  Until then the cards share one `gui/app.py` that grows card by card, and the Qt tool stays the
  default. The evidence tool therefore compares each card against the **same** `before.json`; a
  control owned by a later card goes into `deliberate.json` with the reason `"card <n>"` and is
  removed from it when that card lands (`stale_explanations` must be empty at the end).
* **Checking a card before the manifest switch:** `$PY -m test.gui.emtk_port_parity after <id> --out <dir> --entry
  chisurf.plugins.<group>.<id>.gui.app:make_app` builds the app from the named factory instead of the manifest (the
  Qt-free proof uses it too), so a card can be evidenced while `entrypoints.emtk` is still absent.
* **One working-tree state per card.** Before a card starts: `git status --short -- <plugin dir>`
  must be empty and the board must show no live claim; otherwise pick another card.
* A card is **not started** until its predecessor's report is accepted by the reviewer.

## `updater` (`core/updater`, 4.6k Qt lines, hidden plugin)

Facts (measured 2026-10-01): the logic is already Qt-free in `updater.py` — `ChiSurfUpdater`
(`check_for_updates`, `update_to_version`, `update`, `_list_available_versions`, `_build_changelog`,
`_run_command`, `_schedule_restart`, ...) and `PackageManager` (`list_installed`, `search`,
`install`, `remove`, `update`, `list_envs`, `create_env`, `get_channels`, ...). The Qt side is two
files: `__init__.py` (`UpdaterWidget`, 836 lines, about 12 controls) and `package_widget.py`
(`PackageManagerWidget` in a thin `PackageManagerDialog`, 746 lines, four tabs and about 20 controls), with `QThread` workers
(`UpdaterWorker`, `PackageWorker`). `conda_manager.py` (1.3k lines) is backend.

**Safety rule for both cards (hard):** tests and evidence runs must **never** execute a real
update, install, remove or environment change and must not reach the network. Replace
`ChiSurfUpdater._run_command`, `_run_with_elevation`, `_run_update_in_separate_process`,
`_schedule_restart`, `_list_remote_versions` and `PackageManager._popen` with fakes in a fixture, and
assert in a test that the fake saw the command line that the real code would have run. A card that
cannot be tested that way stops and asks.

| Card | Scope | Acceptance beyond PRD-153 |
|---|---|---|
| **U1 Updater tab** | `UpdaterWidget`: current version, status label, "Development" toggle + branch label, the two startup toggles (`check on startup`, `ignore updates`; they persist through the existing `_load_startup_settings` / `_save_startup_settings`), version drop-down, Check for Updates, Update Now, changelog text (HTML from `_format_changelog_html` → `im.markdown`), and the **Package Manager button, which in the emtk app opens the U2 window** (until U2 lands the button is drawn disabled with a tooltip saying so; record it in `deliberate.json`). Work on a `SnapshotJob`. | The fake runner receives the same command list the Qt path builds for `update_chisurf`, for stable and development channel; the changelog test feeds a fixed fake release list and compares to `_build_changelog`. |
| **U2 Package manager** | `PackageManagerWidget` (the dialog only adds Close): tabs *Installed* (filter, 3-column table, Update/Update All/Remove), *Search & Install* (query, results table, Install), *Environments* (list; Create, Clone, Remove, Export, Import with `FileDialog`), *Channels* (list; Add, Remove), the operation log and Refresh All. Tables are `data_table` sections; selection goes through `selected_call`. | Each button's call reaches the fake `PackageManager._popen` with the expected arguments (one test per button); destructive actions (Remove, Remove environment) ask for confirmation in the app, as the Qt dialog does. |

Order: U1 → accept → U2 → accept → manifest switch (a third, tiny commit by the U2 agent).

## `fret_docking` (`modelling/fret`, hidden)

Facts: the form is a pure spec (`gui/fret_dock.view.json`: 3 panels, 11 values, 3 choices, 4
toggles). The Qt tool (`gui/dock_tool.py`, 831 lines) adds a PDB path list, a results table (sortable
numeric items, "best trial" highlight), a score plot (`chiplot`), a **structure viewer** (the
`chimol` AutoForm section), a progress dialog, project save/load, and workers that run docking in a
subprocess (`multiprocessing`) with a stop flag. Backend lives in `api/` and `core/` and is unchanged.

| Card | Scope | Notes |
|---|---|---|
| **F1 Form, actions, jobs** | the spec form, FPS/output pickers with `FileDialog`, PDB list, Run/Stop with a progress line, project load/save, status. The docking run stays a **subprocess** (the existing `_Worker._run_in_subprocess` logic moved into the model); the app polls it. | Tests use the plugin's own small example and a stub `ops` module for the subprocess path; never start a long docking in tests. |
| **F2 Results** | results `data_table` (numeric sort, best-trial highlight, row selection), score plot with `implot`, CSV/stat file reading (`_stat_files`, `_fill_table`). | Numbers equal the Qt tool's for a recorded result folder. |
| **F3 Structure view** | the `chimol` viewer for the selected trial / PDB. **Not an agent card yet.** `chisurf/plugins/chimol` already has an emtk app; the open design question is whether `fret_docking` draws it as a child (`ImApp.draw_child`, as the `filetools` hub does) or links to the Chimol window. Reviewer decides first; until then F3's controls are listed in `deliberate.json` as `"card F3"`. | |

## Burst tools — survey first, no ports yet

`burst_selection` (7.7k Qt lines), `burst_mle_analysis` (6.4k), `burst_analysis` (2.6k),
`burst_h2mm` (2.0k) and `trace_browser` (2.8k) are too large to cut well from the outside. **Card S**
(read-only, same method as the Type C audit, output
`okf/plugins/emtk-ports/burst-survey.md`): for each plugin list the pipeline **stages or tabs** the
user walks through, for each the controls, the Qt LOC, where the Qt-free logic already lives, which
emtk app or helper already covers it (several already have an emtk `gui/app.py` that is hosted by a Qt
tool), the tests, and a proposed cut into cards of at most one stage each with the dependency order.
The reviewer turns the survey into cards; no code changes.

Not planned here (own design needed): `acq` (7.6k, device and acquisition), `mmfdb_admin` (11.7k),
`fps_json_editor` (3.7k), the FCS hub (`fcs_toolbox` / `fcs_correlator` / `intensity_trace`,
blocked on the Type C decision for `tttr_correlate`), `quenching_estimator` (backend broken).

## Wave 1 reminder

`mfd_prepare`, `burst_ebfret`, `alex_suite` are Type A and small but had uncommitted edits to
`gui/app.py` from another stream on 2026-09-30; on 2026-10-01 the owner chose to skip them until those
edits are committed or dropped.
