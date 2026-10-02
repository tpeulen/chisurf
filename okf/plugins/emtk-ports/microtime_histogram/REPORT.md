# emtk port report -- `microtime_histogram` (upgrade, audit-all row 76; T-20261002-EMTKUP5)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `microtime_histogram` / `chisurf/plugins/tttr/microtime_histogram` |
| Port type | A+B: the Qt `MicrotimeHistogram` wizard (Histogram tab: setup/detector combos, output, binning, dt, parallel/perpendicular, polarization, G-factor, VV/VH shifts, FWHM, Compute / Save / Transfer, two checkable path lists with Files/Folder/Database/All/None/Remove/Clear, plot; Detector Setup tab) -> the stream's hand-drawn emtk app, rebuilt on a view spec |
| Commits | baseline `4c0858201` (Qt baseline + the earlier stream's emtk state, `pre-upgrade/`); app + tests commit; evidence commit |
| Qt reference | `before_populated.png`, `before_populated_detector_setup.png` (BH_SPC132.spc, SPC-130, green detector); emtk before: `before_emtk_populated_1200x800.png` |

## 1. What was wrong (screenshots + tests)
- Options were a tall column of caption-above-field rows in a cut-off dock; plot in a corner; unsized file chooser; buttons one per row;
  the app rendered every frame (`continuous=True`); no `item_rects`, no tour targets, no real-input tests.
- The compute button resolved to the *model's* `compute` (the proxy preferred model attributes): found by the click test.
- Photon and burst list buttons shared ImGui ids (identical captions): found by the click test.
- Qt/emtk numbers differ in two places, both Qt defects (legacy, documented in guide 89): dt of an SPC file is the detector page's 50 ps default (header: 3.3 ps); a `.pto` is read with the disabled format box value SPC-130.

## 2. Now
Two dock tabs as in Qt (Inputs and options | Detector definition = the shared channel-definition editor) and the decay with the room. Spec `gui/histogram.view.json` over `HistogramFields`; Run panel (Compute / Save / Save as... / Transfer, Autosave) and FWHM always on top (800x600 keeps them in view); photon list with check boxes, All/None/Remove/Clear, context-menu remove; burst list under a fold; two-column label grid; spin shifts; sized dialogs; frames only while a job runs; help + 7-step guide with awaits; log axis default as Qt; plot toggles; empty axes; settings round trip.

## 3. Parity (hermetic, vs the Qt wizard in a subprocess on BH_SPC132.spc)
`tests/test_emtk_histogram_parity.py`: cumulative VV|VH export **equal** to the Qt wizard's for the default and for binning 4 + VV shift 3 + VH shift -2 + G 1.25; same channel lists and G-factor; FWHM in channels equal. A broken Qt host fails the fixture (never skipped).

## 4. Control -> test (tests/test_emtk_histogram_clicks.py, 35; layout 17; parity 4)
Guide/Help/Next/Prev/Close; Files... (dialog: empty Open, Cancel, x, select+Open), Folder..., Database... picker; drops (photon, burst, foreign); check box, All, None, Remove, Clear, row select, context-menu remove; burst fold, Files/Folder dialogs, Find TTTR; Detector choice (channels, G, output name), Parallel/Perpendicular typed (+ junk refused), Polarization resolved, Excitation window, TTTR format, Binning, dt typed (manual) + Manual toggle, G-factor, VV/VH shift typed/arrows/wheel, Output typed, Polarization choice, Autosave; Compute (worker; Qt sum 135967), headerless-SPC error in the window, Stop (worker told to stop), Save (VV then VH), Save as... (dialog ways out, typed name), Transfer (host receives dataset); Log counts / VV / VH / VV+2G VH toggles, wheel zoom, drag pan; Detector definition tab; settings round trip; every spec field/button has a description; guide targets drawn; real ~/.chisurf untouched; Qt-free.
Layout (both sizes): run buttons inside the dock and above 40 % of the height, every option field inside the dock, one caption column, short number fields, no overlapping texts, pictograms clear, plot >= 45 % of the width with axes and legend, idle state, sized file dialog.

## 5. Gaps
- strict xfail: tour card `Close Tour` dead where the card lies over a field (shared gap, `scripts/emtk_gaps_repro.py` #3).
- The detector tab shows the shared editor's own list of setups; the Qt wizard's *Setup:* combo on the Histogram tab is the editor's setup chooser (deliberate, `deliberate.json`); BID list has no Database... button (the picker returns photon data).
- Shared editor (not touched): see the channel_definition owner's notes.

## 6. Deliberate breakage
Round 1: 16 mutations, 15 caught; missed "stop does nothing" (test only checked the outcome) -> asserts the worker was told to stop. Round 2: 16/16 caught (actions to model, button id collision, detector keeps channels, typed dt not manual, shifts not applied, log axis, save-as path ignored, None/Remove/transfer broken, text field cap, label column, burst drop routing, stop, shift sign, 2G).

## 7. Reuse
Shared: `chisurf/emtk/channel_definition.py` (Detector definition tab; unchanged), `DatasetPicker`, `FileDialog`/`DialogWindow`, `emtk_layout` (`LabelColumn`, `layout_spec`, `button_row`), `draw_form` spec forms, help/tour. Replaced local: hand-drawn labelled fields and buttons, the unsized chooser window.

## 8. Docs
New `docs/guides/89_microtime_histogram.md` (figure from the app, headless snippet run), `docs/concepts/microtime_histogram.md`, reference page links, indexes. In-app `help.md` rewritten.

## 9. Self-check
- [x] D1 [x] D2 [x] D3 [x] D4 [x] D5 [x] D6 [x] D7 [x] D8 [x] D9 [x] D10
