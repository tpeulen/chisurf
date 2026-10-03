# emtk port report - `imaging_tools` (audit-all row 79, hub; upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-03, T-20261002-LEFTOVERS, UPGRADE_BRIEF. Type A hub: the Qt `ImagingToolsTool` (a `NavigationPanelTool` over 16 panels) against the stream's emtk hub that hosts the children's own native apps. The children are not touched (each has its own accepted report). Verdict: **accept**.

Commits: `16ecc190d` Qt baseline + stream state; the app/tests commit and the evidence/docs commit follow (hashes on the board).

## 1. State at start
Uncommitted: modified `gui/client.py`, `manifest.json`; untracked `gui/app.py` (501 lines, copied to `pre-upgrade/app.py.txt`), `gui/help.md`, `test/` (test_native: 4 tests + 16 parametrised child draws; its children test failed until `region_mle.make_app` accepted the coordinator). Defects of the stream's hub (`before_emtk_populated_*.png`): every list entry led by an emoji that the canvas font draws as a stray glyph, the Search field's caption to the right of a field that ran under the list, Previous/Next that walked a pipeline order different from the Qt shell's, no Back/Run-all stepper, no guide, a header that did not grow with a long description or an error (it overlapped the child), the Qt descriptions replaced by short ones.

## 2. Qt checklist (`before.png`, `before_populated_*.png`, `qt_facts.json`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | nav list: 16 panels in Qt order, a rule before CLSM Draw, icons, tooltips | same 16 in the same order with the Qt descriptions word for word, the rule before CLSM Draw; no emoji | yes (icons dropped) |
| 2 | Search field | hint `Search...`, name + description match, "No tool matches" line | yes |
| 3 | Back / Next (list order, greyed at the ends) | same | yes |
| 4 | fast-forward (queue to the separator, one step after the other, again = stop) | `Run all` / `Stop` | yes |
| 5 | Guide, ? | Guide, Help (real page) | yes |
| 6 | status bar (background compute progress, Ready) | status line under the buttons (opened tool / fast-forward) | yes (no pre-compute: below) |
| 7 | shared Setup / pipeline / calibration propagation, deep copies, MMFDB binding | unchanged (stream code, tested) | yes |
| 8 | panels built lazily; a broken one reports and the rest works | same, error in the header | yes |
| 9 | up/down keys in the list | same unless the open tool takes the key | yes |
Deliberate: the Qt hub pre-computes all analysis steps in a background pool as soon as a new source is set; the native hub computes a step when it is opened (autorun) or by **Run all**, each step on its own `SnapshotJob`. Next/Previous from inside a tool (`advance_from`) keep the Qt pipeline order (the order excludes Flow, as Qt's does).

## 3. Reuse
`calculator/hub/gui/app.py` `CalculatorHubApp` (event forwarding to the child, arrow keys, frame requests, layouts) is now the base, as `lifetime_analysis` and `calculator/hub` are; the hub's own list/header/stepper is drawn here because it carries the pipeline context; `chisurf/emtk/help_guide.py`; `imaging_emtk.testing.Driver`; the layout checker of `project_browser`. The children are the accepted native apps, constructed from their manifests (no copy). A duplicated event-forwarding block (pointer, wheel, key, drop) of the stream's app is gone.

## 4. Evidence
`after: 63 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [], untooltipped [], 127 explained: the embedded Qt Setup wizard's text and the lazy-load placeholders; stale_explanations 0). Real children, real photon file copy: `click_1..8_*.png`, `after_populated_{1200x800,800x600}.png`.

## 5. Layout
1200x800 and 800x600 read at full size. Asserted on the hub's own texts (the child's are its own report): no overlap, nothing cut, and the header grows with a long description or an error so it never covers the child (`test_a_long_description_and_an_error_grow_the_header...`). The list is capped at 300 px; Back / Next / Run all and Help / Guide sit in two rows under it.

## 6. Tests
```
$ python -m pytest chisurf/plugins/microscopy/imaging_tools -q -p no:cacheprovider
91 passed in 88.15s
```
Parity vs the live Qt tool: list names/roles/order/descriptions, the separator, `PIPELINE_ORDER`, `ANALYSIS_ROLES`, the stepper order. Context duties (setup/pipeline/calibration deep copies, lazy build, snapshot and restore, autorun only for analysis steps with a source and no result, failing factory, pending tool), 16 real children drawn Qt-free at both sizes, the five pipeline children receiving setup/source/HDF5/calibration, six locales.
Control -> test (real pointer/keys/wheel/drop via `Driver`): list entry click `test_a_click_on_a_list_entry...`; search `test_the_search_field_keeps...`; Back/Next `test_back_and_next_buttons_walk_the_list...`; Run all / Stop `test_fast_forward_*`; pending tool `test_a_tool_marked_pending...`; pointer into the child in its coordinates `test_the_embedded_tool_gets_pointer_events...`; wheel `test_the_wheel_over_the_tool...`; keys and drop `test_keys_go_to_the_open_tool...`, `test_a_tool_without_a_drop_handler...`; arrow keys `test_the_arrow_keys_step_the_list_selection...`; source banner `test_the_source_and_hdf5_lines_follow...`; Help/Guide/tour with awaits and card placement `test_help_button...`, `test_the_tour_is_walked...`, `test_every_guide_target...`; small window `test_the_whole_flow_works_in_the_small_window_too`. Guard: module fixture fails on any change in the real `~/.chisurf` except `logs/`; tests run on temp settings and HOME.
Breakage twice (the stepper skips one tool; the tour/status notifications removed): 1 and 3 failures (the stepper skipping a tool: back/next, small-window flow, stepper order; the removed tour notification: tour walk), restored.

## 7. Docs
New `docs/guides/98_imaging_tools.md` (+ index entries) with a figure from the emtk hub on a real photon file, `docs/reference/plugins/imaging_tools.md` (surface, native window, guide link), `help.md` rewritten, `guide.json` (7 steps, 3 awaits). The allow-list line for this plugin struck.

## 8. Findings
Real: the stream's Next/Previous disagreed with the Qt shell (list order vs pipeline order); the fast-forward queue was missing; a long description or error overlapped the embedded tool. Gaps in the hosted tools are reported in their own reports.
