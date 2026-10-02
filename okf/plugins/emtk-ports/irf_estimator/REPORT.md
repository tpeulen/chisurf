# emtk port report — `irf_estimator` (upgrade, audit-all row 49)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `irf_estimator` / `chisurf/plugins/fluorescence_decay/irf_estimator` |
| Port type | A+B: the Qt `IRFEstimatorTool` (toolbar, parameter group, chiplot decay/IRF/forward-model plot with range region and crosshair, results group, status bar) → the stream's emtk `gui/app.py` + `view_model.py`, rebuilt on a view spec |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `e1013ad4a` baseline; `1601e495d` emtk app at parity; evidence commit "irf_estimator: evidence and report" |
| Board | `T-20261002-EMTK1D` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py` (lazy Qt import), `manifest.json` (emtk entrypoint),
`backend/services.py` (VV/VH split read; IRF written with its bin width; refuses empty or non-finite IRFs),
`gui/tool.py` (loads through the service; estimates from the uncorrected counts); untracked `gui/app.py`,
`gui/view_model.py`, `test/test_native.py`, `test/renders/`. All but the stale render committed with the app.
Measured on a real decay (`test/data/tcspc/Jordi_FRETsens/Donor/D0_14_TAC1024_DexDem.dat`, RL 100, range on), the stream's
numbers already equalled the Qt tool's. Its plot did not cut the scaled IRF at one count, so the log axis ran to 1e-54
(`before_emtk_populated_*`).

## 2. Parity checklist (`before_populated.png` (Qt) vs `after_populated_*.png`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| toolbar: 📂 Load Decay, 📊 Load from Dataset, 💾 Save IRF, 🚀 Transfer to ChiSurf, data label, Guide, ? | buttons two per row, no data label | spec button rows with the Qt captions; data label ("No data loaded" / path / "Dataset: exp - name" / "Error: …") |
| Save / Transfer enabled only with an IRF, Estimate only with data | always enabled | same as Qt; all but Help/Guide disabled while an estimate runs |
| Time/Channel (ns) (disabled, from data) | editable | editable (gain: rescales lifetime/rate, keeps the per-channel IRF) |
| SG Window Length 5–500, SG Poly Order 1–10, RL Iterations 5–2000, Regularization 1–51, Manual Background 0–1e5 | sliders | spec fields with the Qt ranges and steps |
| 📍 Use Range Selection, 🔄 Auto-Update IRF | plain checkboxes | toggles with the Qt captions; range also as first/last channel fields |
| 🔮 Estimate IRF | button | button; worker thread, one at a time |
| plot: measured (blue), BG corrected (cyan dash), IRF scaled ≥ 1 count (green), forward model (orange dash), log y, legend, crosshair + tooltip, range region | IRF not cut; default colours (forward model green on the green region) | Qt cut and pens; crosshair, "Time: x ns, Intensity: y" |
| results group: τ, k, A, C with Qt formats, N/A before | `.6g` text | Qt formats and N/A |
| status bar: Ready / Estimating IRF... / completed / failed; permanent time-axis label | one status line | status line, red error line, time-axis line (wraps) |
| error / success modals | status text | red error line / status text (deliberate: no modals in emtk) |
| dataset selector dialog | combo | combo + Load selected |
| docks: params left, plot right, results under the plot | results under the settings | Qt layout |
| — | drops | a dropped file loads |

## 3. Automated evidence

```
after: 51 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/irf_estimator
compare: exit=0   (deliberate.json: "?" -> ❓ Help)
```

## 4. Deliberate differences

`deliberate.json`: "?" is ❓ Help. Not in the inventory: the Qt dock context menu and QSettings geometry (the emtk dock
layout is the host's `native_layouts`), and the success modals (the status line says it instead).

## 5. Tests

```
$ python -m pytest chisurf/plugins/fluorescence_decay/irf_estimator -q -p no:cacheprovider
29 passed
```

`test_emtk_irf_estimator_parity.py` (17). The Qt widget runs in a subprocess on the measured decay. The emtk app is
driven by pointer presses on the spec's buttons; its control states before load, after load and after the estimate
equal the Qt widget's. The tests also check:
- data label, time-axis label, file background, results texts, IRF samples (rtol 1e-6) and status;
- the background a file with a nonzero tail sets, against the Qt widget;
- disabled buttons do nothing;
- a bad file shows a red error and an "Error:" label, and a drop loads the first path;
- a failed estimate leaves no result and keeps save disabled;
- one estimate at a time, with frames only while it runs and the controls disabled meanwhile;
- auto-update re-estimates with 50 iterations on a background change, and switching it on does not estimate;
- range fields order themselves, and the plot series carry the Qt names and the IRF cut;
- the four curves get the Qt pens, dashed where Qt dashes;
- save writes the IRF (6 decimals), and an unwritable path is an error;
- transfer registers a two-channel dataset;
- the dataset combo, and the error when no datasets are open;
- every guide target is drawn; the load step waits for a loaded decay and the estimate step for the button;
- draws empty and populated at both sizes, with every control inside its dock;
- help opens, Qt-free, tooltips (inventory and a walk over the spec).

The stream's `test_native.py`: the pointer text now has the Qt tooltip wording ("Intensity:").

## 6. Breakage check (14 faults, run twice: 14/14 caught both times)

The first run missed two faults, and a test was added for each:
- **file background not set:** the measured file's tail is empty, so Qt and emtk both give 0. The new test is
  `test_a_file_sets_the_qt_background_estimate`.
- **plot pens dropped:** the new test is `test_the_curves_carry_the_qt_pens`.

The other faults:
- IRF not cut;
- save enabled without an IRF;
- the dialog opening releases the load step;
- auto-update never fires;
- the error line not drawn;
- a second estimate starts;
- the time-axis and amplitude formats;
- no frames while running;
- the load error label kept;
- the range not ordered;
- controls live while busy.

## 7. Screenshots read

- `before.png`, `before_populated.png` (Qt);
- `before_emtk_populated_{1200x800,800x600}` (stream: axis to 1e-54, clipped toggle);
- `after_{1200x800,800x600}` (empty: Save/Transfer/Estimate/Time disabled, "No data loaded", N/A);
- `after_populated_*` (Qt numbers, the IRF cut, orange dashed forward model to 1024 ns);
- `after_guide_*` (step 2 spotlights 📂 Load Decay).

Fixed on the way:
- "Auto-Update IRF" and "Use Range Selection" were clipped in the field column;
- the Estimate button was clipped at 800 px;
- the time-axis line was cut off.
