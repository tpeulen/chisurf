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
