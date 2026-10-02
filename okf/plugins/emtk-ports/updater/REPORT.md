# emtk port report - updater (card U1 done, card U2 not started)

Agent (Sonnet), 2026-10-02. Safety: every test and evidence script runs on fakes (`chisurf/plugins/core/updater/test/fakes.py`): no update, install, removal, env change or network (subprocess and urllib are blocked; asserted after each test).

## U1 (Updater tab)
Qt-free `gui/model.py` (`UpdaterModel`), spec `gui/updater.view.json`, `gui/app.py`, `guide.json` (7 steps, 2 await), `help.md`; package `__init__` made lazy (Qt widgets moved to `qt_widget.py`). Manifest NOT switched (after U2).
Tests: 85 passed, 1 xfailed (parity 28, real-input 40 incl. xfail wheel over the version list, layout 13, Qt widget tests 4). compare exit 0, lost [] (22 U2 controls in deliberate.json as "card U2"), 0 untooltipped, Qt-free yes. Command lines asserted: remote .tar.bz2 and .conda install line, standard install line, development vs master channel, declined = nothing run.
## Findings
- Qt PackageManagerWidget: `_on_operation_finished` body duplicated (two error boxes) - fixed + test; QThread destroyed while running aborted the process - fixed (`_ALIVE`) + test.
- `PackageManager.search` returns conda's dict, the Qt table only reads lists: Qt search shows 0 results with a real solver (baseline `pm_search_rows` 0). NOT yet fixed (U2).
- Changelog for the latest version uses the previous listed version, not the installed one, contradicting the caption (kept for parity; belongs in known-issues).
- Real runner ends with sys.exit inside the worker: model catches SystemExit and the app calls exit_hook.
- emtk gaps: wheel over a choice does not step it; tour card does not block controls under it (Next dead where it covers a field/child; changelog capped at 640 px so the card has room at >=1100 px wide).
## Reuse / Docs
Reused: data of ChiSurfUpdater, SnapshotJob, spec forms, DialogWindow, help/tour, emtk_layout. Duplicate flagged: dialog mixin vs plugin_manager's. Docs: new docs/guides/90_updater.md + index + figure updater_checked.png; reference page not regenerated.
## Open
U2 (package manager), manifest switch, search normalisation fix, quenching_estimator (not started), deliberate breakage x2, log.md hunk.
