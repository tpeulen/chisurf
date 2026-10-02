# microtime_shifter: layout, real-input and docs upgrade (T-20261002-EMTKUP5)

Builds on REPORT.md (parity, EMTK-1C). Qt baseline: `before_populated.png` (unchanged tool). Emtk before this pass:
`before_layout_{1200x800,800x600}.png`; after: `layout_*.png` (idle, loaded, populated, save/folder/sample dialogs, guide, help, both sizes; script `scripts/capture_layout.py`). All read at full size.

## Defects found by screenshots and tests, fixed
- Field captions of the three panels started at three x; trigger fields stretched across the dock -> one `LabelColumn`, capped spin fields (spec `style: spin`: Level/Pos/Global shift now have the Qt spin arrows).
- At 800x600 the Save panel's buttons sat in the label grid and ran off the dock ("Save batch" lost) -> each run of fields is its own panel, buttons start at the left edge; path field no longer capped past the dock; placeholder shortened.
- Channel rows used a raw `im.input_int`, which in emtk takes no keyboard on a click (repro below) -> spec rows (`draw_sections`, spin field + fixed-width reset), keys `shift_<ch>`, `reset_<ch>`; label "Channel N" (Qt: "Ch0").
- New-sample dialog: hand-drawn fields with captions on the right and ragged widths -> `sample.view.json` over a `SampleFields` proxy of the definition JSON, one label column, JSON under a collapsing "Advanced" header, Create/Cancel under the form.
- Dock titles / buttons with a pictogram touching the caption -> `icon_label` (two spaces). Idle plot had unit axes 0..1 -> 0..4096 / 0..100.

## Control -> test (tests/test_emtk_shifter_clicks.py, 35; test_emtk_shifter_layout.py, 16 cases)
Guide/Help/Next/Prev/Close; Files... dialog (Open empty, Cancel, x, select+Open, double click); Folder... dialog; Database... picker open/close; drop of file, folder, foreign file; list select (reload, shifts reset); Remove; context-menu remove; Clear; Auto align (shifts = demo's known 3904/3504); typed Level/Target + Enter (re-align, clamp, junk); spin arrows and wheel; Show trigger lines; Log Y (decades); drag of green line (target moves, aligns on release); drag of yellow line; wheel zoom on the histogram; channel typed/arrows/reset; global shift typed/arrows/bounded; Save shifted... (cancel, typed name, written file = (micro+shift) mod N per photon); Batch folder typed, Browse... cancel, Save batch; MMFDB fold, New sample..., Cancel sample; Alignment fold; Status tab; tour not covering. Layout: every control inside its dock and window at both sizes, one caption column, short number fields, no overlapping texts, Save panel complete, plot area >= half the window with axes, idle state, sample dialog aligned.
Numeric parity vs the Qt tool stays in test_emtk_shifter_parity.py (Qt subprocess on the same file).

## Gaps
- strict xfail: tour card `Close Tour` dead on step 7 (card over a field; shared gap, emtk_gaps_repro.py #3).
- emtk repro (5 lines, `scratchpad` -> okf scripts not committed): `ImApp` drawing only `im.input_int("##v", 5, step=1)` in a window; click it at 70% width; `app.io.want_capture_keyboard` stays False and typed keys change nothing, whereas `im.input_text` takes the click. (It works after any input_text was clicked once.)

## Deliberate breakage (14 mutations, two rounds)
Round 1: 12 of 14 caught. Missed: "channel shift not clamped" (equivalent: the spec's bounds clamp first), "log_y ignored" (test gap: added the decades-only assertion). Round 2 (13 mutations, the equivalent one dropped): 13/13 caught. A test asserts a full session leaves the real ~/.chisurf (pwd home) untouched.

## Reuse
LabelColumn / layout_spec / icon_label (chisurf/plugins/emtk_layout.py), draw_form + draw_sections spec forms (channel rows, sample dialog), FileDialog, DatasetPicker, help/tour. Replaced local: hand-drawn sample form, hand-drawn channel rows.

## Docs
New docs/guides/88_microtime_shifter.md (figure figures/88_microtime_shifter.png from the app; CLI and Python verified), docs/concepts/microtime_shift.md, registered in guides/index.md and concepts/index.rst, reference page microtime_shifter.md links both.
