# emtk port report - updater (cards U1 and U2)

Agent (Sonnet), 2026-10-02. Verdict: both cards done, `entrypoints.emtk` switched. SAFETY: every test and evidence script runs on fakes (`chisurf/plugins/core/updater/test/fakes.py`): no update, install, removal, environment change or network; subprocess and urllib are blocked and an autouse fixture asserts after each test that no process started and `_run_command`, `_run_with_elevation`, `_schedule_restart` were never reached. HOME, CHISURF_SETTINGS_DIR, MMFDB_* are temporary (`test_nothing_in_the_real_home_is_touched`).

Commits: `1daac6f0d` baseline, `cf7a8ab04` U1, `31bd9f7b2` known-issue + log (U1), `70d055987` U2 code, then the U2 click/layout/evidence/docs/manifest commit.

## Result
`151 passed, 2 xfailed in 38.58s` (parity 28 + 22, real-input 40 + 30, layout 13 + 13, Qt widget guardrails 5; xfails: wheel over a choice, tour Next over the table). compare exit 0, lost [], deliberate.json empty, 0 untooltipped, Qt-free yes (both `make_app` and `make_package_app`). Command lines asserted: update (remote .tar.bz2, .conda, standard, development vs master), and one test per package-manager button (install, update selected, update all, remove, create, clone by path and by name, remove env, export, import, add/remove channel, refreshes read-only, failure path).

## Deliberate differences
- One selected row per table (Qt allowed several for install/update/remove); `data_table` has no Ctrl/Shift multi-select (same gap as image browser, `scripts/gap_table_multiselect.py` there). Install/remove one package at a time.
- Update Selected and Remove Channel ask nothing (as Qt); buttons that need a selection are greyed (Qt returned silently).
- Changelog drawn as plain text blocks, links open in the browser (Qt: HTML, link inert); the start-up check waits 0.6 s after the first frame so a drawn-only window never reaches the network.

## Defects found and fixed
Qt package widget: completion handler body duplicated (two error boxes); a QThread destroyed with its widget aborted the process (module-level keep-alive); lambda connections to deleted buttons; failure text of (ok, output) results lost (empty error box). Backend: `PackageManager.search` returned conda's dict / micromamba's nested payload while the table read lists: a real solver showed 0 results (`normalize_search_results`, guardrail test). Known issue (not fixed): changelog range vs caption (known-issues.md).

## emtk gaps
Wheel over a choice does not step it; the tour card does not block what is under it (Next dead where it covers the full-width table, so `test_the_tour_cards_next_button_answers_over_the_table` is a strict xfail; U1 works because the changelog is capped at 640 px); Enter in a just-emptied text field does not commit (click away does); markdown has no escape for `_`/`*` (changelog is plain text); an input inside a window is greyed by the model's `enabled` unless listed (my bug, fixed).

## Real-input coverage (control -> test)
U1: Check for Updates (check_for_updates_press..., second press, failing server, raising check), version list (picking, wheel xfail, greyed), Update Now (greyed, question, No/x/Escape, Yes + command, progress, failed start), Package Manager (opens window, x closes), Development (inert), startup switches (toggle, caption press, saved), changelog (wheel scroll, link, literal characters), notice OK, tooltips, Help, Guide (await steps, drag card, targets), dialog drag. U2: tabs (4), Refresh List/All, filter typed and cleared, header sort, row select, Update Selected/All, Remove (No, x, Escape, Yes, failure), Search by Enter and button, Install (No/Yes), Create/Clone/Remove env (typed names, Cancel, empty), Export (save dialog Cancel/typed name), Import (open dialog then name), Add/Remove channel, log wheel/follow, table wheel, tooltips, Help, Guide. Drops: none apply (the Qt dialogs took none).

## Reuse
Used: `ChiSurfUpdater`/`PackageManager` unchanged as the only system boundary, `SnapshotJob`, spec forms with `draw_sections`, `data_table` (4 tables), `FileDialog`, `DialogWindow`, help/tour, `emtk_layout.layout_spec`, the imaging `Driver` for tests. New shared piece: `gui/dialog_model.py` (in-app confirm/entry dialog) duplicates plugin_manager's dialog model - flagged for unification (other plugin, not touched). The Qt widgets `UpdaterWidget` now delegate changelog formatting and startup settings to the Qt-free module (no copy).

## Docs
New `docs/guides/90_updater.md` (U1 figure and three package-manager figures regenerated from the emtk app), `docs/guides/index.md`, `docs/reference/plugins/updater.md` (edited by hand; the generator was not run), `gui/help.md`, `gui/packages_help.md`. No concept page: the updater has no method to explain.

## Open
Multi-select in `data_table`; the embedding of the native updater/package panels into the emtk Settings app (it still lists the panels from the Qt tool); tour card modality in emtk.
