# emtk upgrade report - `tttr_audifier` (audit-all row 77)

Agent: claude (Sonnet), 2026-10-02, board entry `T-20261002-EMTKUP5`. Verdict: **accept** (one emtk gap, one shared-editor note).
Commits: `67750f85a` (Qt baseline + earlier stream state, `pre-upgrade/`), then app/tests and evidence/docs commits.

## 1. Baseline and what was wrong
Qt baseline populated (BH SPC-132, 183,657 photons, `before_populated_{microtime,lifetime}_<tab>.png`; the Qt waterfall plot stays empty offscreen, a limit of the Qt capture). The earlier emtk app, populated (`before_emtk_*.png`), showed: hand-drawn number fields stretched over the whole window with captions above them and no arrows; the waterfall as a bare image with a text line instead of axes; detector colours as three integer boxes; channel notes as one long column per channel; no tour targets (the guide had no targets or awaits); no item rectangles; a file chooser in a bare window; an `.spc` file failed with a message the Qt tool never needed (see 3).

## 2. Checklist of the Qt controls
| Qt control | emtk |
|---|---|
| Load TTTR, file name | Load TTTR (dialog, drop), file name |
| Update channels | Update channels |
| Setup page (shared) | the shared detector editor, embedded |
| Mixer: detector checkbox + Color button; channel checkbox, Chord, Pitch, Gain | Detector colours table (Show, typed #rrggbb), Channel notes table (On, Pitch, Gain, Micro first/last) + Chord choice of the selected row |
| Audio: bin width, envelope, sample rate, master gain, env floor/scale, attack, release | spec form with spin arrows and the spec limits |
| Waterfall params: mode, micro-time group, lifetime group | spec form (radio, folds) |
| Waterfall plot with axes, Update, Play, Pause, Stop, Revert, WAV, time label | plot with axes (wheel/drag), transport row, state line; Pause/Stop/Revert greyed unless playing |
| (new) Range start/end, Guide, Help | spec fields, Guide, Help |

## 3. Defects and differences
1. `.spc` read with File Type Auto: emtk loader raises "Select the SPC subtype in TTTR reading before loading" (the Qt tool read it with its default reader). The message is the answer; the populated flow chooses SPC-130 first. Documented in help and guide.
2. Waterfall orientation: macro-time horizontal, micro-time/lifetime increasing upward (the Qt plot had them swapped); deliberate.
3. Channel notes keep the micro-time gate fields the Qt mixer did not have.

## 4. Layout
Read at 1200x800 and 800x600 (`after_populated_*`): fields grouped with captions beside them, number fields capped, buttons wrap, detector table and plot get the space, no clipped text. The shared detector editor's table headers (G-Factor, Micro Time Ranges) overprint at the narrow left panel (a recording check); not mine, excluded from the layout test.

## 5. Reuse
`ChannelDefinitionWidget` (shared detector editor, one-page), `emtk_layout` (`layout_spec`, `button_row`), spec forms + `data_table`, `FileDialog` + `DialogWindow`, `EmTkHelpWindow` / `EmTkGuidedTour` with `TourTarget`, `BackgroundJob` of tttr_splitter, `traj_save_topology/test/real_input.Ui`, the Qt tool's `audifier.view.json` (read, descriptions added).

## 6. Tests
`pytest chisurf/plugins/tttr/audifier`: **32 passed, 1 xfailed** (15 earlier + 17 new). Parity: payloads equal `AudifierViewModel` for micro-time and lifetime, defaults equal the Qt model's. Real input: drop and Load dialog (Cancel, close, pick), range fields (typed, clamped, garbage, arrows), four audio fields typed with limits, mode radio and checkbox clicks, detector Show box and typed colour (good and bad), channel On/Gain/chord by cell clicks and typed values, Play/Pause/Resume/Revert/Stop/Save WAV with a fake audio process, tour walked with awaits, Help, no-data message, real BH file load + waterfall, layout at both sizes, settings round trip and a guard that HOME stays untouched. Strict xfail: **emtk gap, wheel over the waterfall plot does not zoom** (implot inside a DockManager window; repro: draw the app with a computed waterfall, `app.wheel` over `item_rects["waterfall_plot"]`, the axis ticks do not change).
Deliberate breakage (restored): colour parse divisor changed -> `test_detector_table_show_box_and_typed_colour` fails; Pause bound to stop -> `test_transport_buttons_...` fails.
`after`: 62 controls, 0 untooltipped, qt-free yes; `compare` exit 0 (`deliberate.json`).

## 7. Docs
New `docs/guides/94_tttr_audifier.md` (registered), figure `docs/guides/figures/94_audifier_waterfall.png`; `gui/help.md` and `gui/guide.json` rewritten (7 steps, 3 awaits). No concept page for the audifier existed; plugin reference not regenerated.
