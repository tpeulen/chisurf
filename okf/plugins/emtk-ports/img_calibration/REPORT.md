# emtk port report — `img_calibration` (upgrade, audit-all row 47)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `img_calibration` / `chisurf/plugins/microscopy/img_calibration` |
| Port type | A+B: the Qt `ImgCalibrationTool` (AutoForm over `calibration.view.json`: Calibration panel and Decay & IRF tab) over `CalibrationViewModel`; the stream's emtk `gui/app.py` over the same model, with its own hand-drawn controls |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `23cdf6e6d` baseline; `5ae07011d` emtk app at parity + two model defects; evidence commit "img_calibration: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json`; untracked `gui/app.py`, `gui/help.md`, `gui/locales.py`,
`gui/translations.json`, `test/` (test_native, two capture scripts). All committed with the app.

## 2. Model defects, fixed for both hosts

- **Apply published a shallow copy** (`dict(self.calibration)`): the per-detector rows stayed shared, so an edit after Apply
  changed the calibration Phasor and the pixel-wise MLE had received. Now a deep copy (the stream's tests pinned this).
- **Apply published empty windows and negative backgrounds unchecked.** `check()` refuses them ("Not applied: green: range
  start must be smaller than stop"); the stream's app had the check, it now lives in the model.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| info text, Detector, IRF files list (Files / Database / Remove / Clear), Conv/IRF start-stop, Background VV/VH, Shift VV/VH, Apply → | hand-drawn: "Fit start" etc., no Database | the spec's Calibration panel via view_form (the spec's labels and descriptions), the IRF list as its `path_list` section with Files / Database / Remove / Clear |
| Decay & IRF tab: decay + IRFs, draggable regions | plot dock, peaks clipped | plot dock, y range holds the peaks (ALWAYS on change, ONCE after) |
| — | Help / Open TTTR / Refresh among the inputs | 📖 Guide / ❓ Help / 📂 Open TTTR… / 🔄 Refresh, wrapping in a narrow dock |
| no guide | none | `guide.json` (8 steps; Open TTTR and Apply await presses) |
| binning off the UI thread | worker | worker; a refusal stays visible while re-binning (it was wiped by the next binning) |
| — | no `close()` | `close()` |

## 4. Automated evidence

```
after: 34 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/img_calibration
compare: exit=0   ("1": a list row number, deliberate.json)
```

## 5. Tests

```
$ python -m pytest chisurf/plugins/microscopy/img_calibration -q -p no:cacheprovider
17 passed
```

`test_emtk_calibration_parity.py` (12): the Qt tool in a subprocess on real photons (the micro-time shifter's demo SPC as
source and IRF; detector channels 0 ∥ and 8 ⊥) — decay, IRF, windows, backgrounds and the published snapshot equal the
emtk app's, and the backgrounds equal the mean counts of a histogram made from the photons in the test; Apply's status in
the Qt words, a snapshot that later edits do not reach, a refused empty window shown in the window; spec fields with
descriptions and the spec's labels; IRF list add (multi-select dialog), remove, drop, clear and its "raw data" hint; the
plot's drawn y range holds the peak; frames requested while binning; guide targets drawn, Open TTTR and Apply awaits
released by presses (the Apply press applies); draws empty and populated with every toolbar and IRF-list button inside the
dock and at its natural width; settings round trip; help; Qt-free; tooltips.

Deliberate breakage, two rounds of 12 faults (shallow publish, no range check, background from the wrong region, plot clips
the peaks, spec not drawn, single-file IRF dialog, no-IRF hint missing, refusal hidden while binning, toolbar never wraps,
Open not told to the tour, tour never drawn, not animating while binning): "toolbar never wraps" passed in both — item
rects are clipped to the dock, so an overflowing button reported an in-dock rect; the test now measures against the dock's
own box (remembered as `controls`), caught. Also found by the screenshots: the IRF list's four buttons overflowed at
800 px (one wrapping helper now serves both rows).

## 6. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_guide_{1200x800,800x600}.png`.

## 7. Persistence, guide, help, docs

Detectors, calibration, display detector and source via `export_settings` (stream). Help (stream's) and guide new; off the
help/guide allow-list. Docs: no page describes this step on its own.

## 8. Blocked / open

none for this plugin.

## 9. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10

## 10. Upgrade 2 (2026-10-03, T-20261002-LEFTOVERS): real-input coverage, layout, host drop, glyphs, docs

Commit: see the board status line. The earlier pass closed the app at parity with 17 tests; this pass adds the owner's real-input, layout and docs rules.

**Defects found and fixed.** (1) **A file dropped on the window never arrived**: the app defined `on_files_dropped`, but the hosts (and `ControlSurface`) call `files_dropped`, so the drop went nowhere (found by the first drop test: the window did not add the IRF). The app now has both (`files_dropped` for hosts, `on_files_dropped` returning whether the files were taken, for the hub). (2) The toolbar, IRF-list buttons and the tour hint carried emoji (Guide, Help, Open TTTR, Refresh, Files, Database, Remove, Clear) that the canvas font draws as boxes: removed.

**Reuse.** `emtk.view_form` over the spec the Qt tool renders, the shared `chisurf/emtk/dataset_picker.py`, `help_guide.py`, `imaging_emtk.testing.Driver`, the layout checker of `project_browser`; the IRF list is the spec's `path_list` section drawn here (the shared AutoForm section has no emtk renderer of its own: a duplicate of the path-list idea lives in `imaging_emtk/path_list.py`; replacing this list by it is a follow-up, since it would change the Remove/Clear semantics the Qt-parity test pins).

**Tests.** `pytest chisurf/plugins/microscopy/img_calibration -q`: **47 passed** (17 earlier + 30 new in `test_emtk_calibration_clicks.py`, on real photons: the micro-time shifter's demo SPC). Control -> test (real pointer/keys/wheel/drop via `Driver`): Open TTTR chooser, cancel, a chosen file becomes the source `test_open_tttr_chooser...`; Refresh `test_refresh_bins_the_histograms_again`; Help window and its buttons `test_help_button...`; tour walk with awaits and card placement `test_the_tour_is_walked...`, `test_every_guide_target...`; Files chooser (multi-select), row click / Remove / Clear, Database picker, host drop, drop before a detector `test_files_button_opens...`, `test_a_click_on_a_row_selects_it...`, `test_database_button...`, `test_a_file_dropped...`, `test_a_file_dropped_before_a_detector_is_chosen_says_so`; the four window fields, the four background/shift fields typed, bad text, clamping, arrows `test_window_fields_take_typed_integers[4]`, `test_background_and_shift_fields...[4]`, `test_typed_text_that_is_no_number...`, `test_the_arrows_step...`; detector choice `test_the_detector_choice...`; Apply publishes a deep snapshot / refuses an empty window with the reason in the window `test_apply_*`; Next with a coordinator `test_next_applies_and_advances...`; plot boundary drag and axes `test_dragging_a_window_boundary...`, `test_the_plot_is_drawn_with_its_axes_and_legend`; layout at 1200x800 and 800x600 (controls dock: no overlap, nothing cut) `test_draws_empty_and_populated...[2]`; no emoji; small window flow. A module guard fails on any change in the real `~/.chisurf` except `logs/` (tests run on temporary settings and HOME). Breakage twice (Remove no longer removes: 1 failure; `add_irfs` no longer stores the files: 3 failures), restored. Strict xfails: none.

**Evidence.** `after: 34 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0. `click_1..6_*.png` and `after_populated_*` read at full size (real photons).

**Docs.** There was no page for this step: new `docs/guides/99_img_calibration.md` (theory + application, figure `img_calibration.png` from the emtk app), index entries, the reference page lists the emtk surface and the guide.
