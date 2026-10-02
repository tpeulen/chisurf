# emtk port report — `lltf` (upgrade, audit-all row 44)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `lltf` / `chisurf/plugins/fluorescence_decay/lltf` |
| Port type | A+B: the Qt `LLTFGUIWizard` (Input Files group with Load…/Edit…/Select…, Fitting Options, tabs Information / Analysis Output (subprocess log, Stop/Clear) / Results (HTML table + matplotlib), Fit, menus, help toolbar) running the LLTF CLI in a subprocess; the stream's emtk `gui/app.py` over `gui/model.py` running the same CLI |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `91bb344dc` baseline; `006817d06` emtk app at parity + two CLI defects fixed (guide 76, known issue); evidence commit "lltf: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json` (emtk entrypoint); untracked `gui/` (app, model),
`test/test_native.py`, `test/renders/` (the stream's captures, left untracked). Untouched since 2026-09-27, no claim.
Plugin-root `help.md` / `guide.json` (tracked, shared with the Qt wizard) kept; the emtk app remembers the Qt tour's names.

## 2. Two command-line defects, fixed for both hosts

- **`-n` was ignored** whenever the configuration had `find_optimal: true` — the shipped example does. Baseline: both hosts
  asked for 2 lifetimes and got 3 (a search). An explicit `-n` now switches the file's `find_optimal` off; `-f` turns it on;
  with neither the file decides (default count 1).
- **Figures on screen.** The CLI turned off only `plot_resulting_fit`; the search's probability and residual figures and an
  unconditional decay figure still called `plt.show()`. From the Qt wizard (no `MPLBACKEND`) the fit opened windows and
  waited for them; headless it hung (measured: 0 % CPU after 18 s, killed). All three are off (the PNG is still written),
  the decay figure is gated on the screen-figure switches, and the wizard's subprocess also runs under `MPLBACKEND=Agg`.
- **Not fixed — known issue:** the fitter draws starting values from an unseeded `random`, so runs differ (3.9659 vs 3.9673
  ns at baseline). Guide 76 *Known defects* and known-issues record it.

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt wizard | Stream's emtk | Now |
|---|---|---|
| Decay/IRF Load…, Config Edit… (+ editable path), Output Select… | editable text + Browse rows (labels right of fields, paths cut) | spec custom `lltf_files`: read-only paths (config editable), Load…/Edit…/Select…; drops route data / YAML / folder |
| Number of Lifetimes, Find Optimal Number…, Max, Threshold, Verbose; greyed by the toggle | sliders, greyed | spec fields with descriptions, `enabled()` greys as Qt; "Find Optimal" (renamed: cut at 800 px) |
| Fit (needs both files), Stop/Clear in Analysis Output | Fit, Stop, Help, Guide at the bottom | ▶ Fit (greyed without files) / ⏹ Stop under the options; 📖 Guide / ❓ Help on top; Clear output in the tab |
| Results: HTML table Component/Amplitude/Lifetime + χ², χ²ᵣ, time range, n | text lines | the spec's `table` + the same summary lines; Export result JSON |
| matplotlib decay + residuals | implot tabs | same (stream) |
| Edit… opens the Qt SettingsEditor | YAML editor window | same (stream) |
| menus File / Settings / Analysis | — | their actions are the buttons (deliberate) |

## 4. Automated evidence

```
after: 32 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/lltf
compare: exit=0   (four renames / hidden-tab entries in deliberate.json)
```

## 5. Deliberate differences

`deliberate.json`: "?" → ❓ Help; "Clear Output" lives in the Analysis Output tab (the inventory sees only the open tab);
"Find Optimal Number of Lifetimes" → "Find Optimal"; "Stop Process" → ⏹ Stop. The Qt menus are not reproduced: every menu
action is a button on the panel.

## 6. Tests

```
$ python -m pytest chisurf/plugins/fluorescence_decay/lltf -q -p no:cacheprovider
48 passed
```

`test_emtk_lltf_parity.py` (18): the Qt wizard in a subprocess with `Popen` recorded — its fixed-count and search commands
equal the model's (config path aside: the emtk app runs the edited buffer) and carry `MPLBACKEND=Agg`; the "load first"
warning; one real fit of the example: 2 lifetimes (τ 3.90 ns, the other 0.6–1.0), fractions sum to 1, χ²ᵣ 1.2–1.6, JSON and
PNG written, residual mean ≈ 0 and spread = √χ²ᵣ; the Results tab draws the spec table with the fit's numbers; the CLI
without Agg finishes a search; errors (no files, a non-mapping YAML) in the window; Fit cannot be pressed without files;
greying as Qt; drops; config editor; spec fields with descriptions; guide targets drawn, Load… and Fit awaits released by
presses; draws at both sizes with the file buttons, Fit and the toggle inside the inputs dock; settings round trip; help;
Qt-free; tooltips.

Deliberate breakage, round 1 (14: -n ignored, search figures shown, decay figure ungated, Qt subprocess without Agg,
greying inverted, rows swapped, summary without χ²ᵣ, button id collides with the field, tab tooltips only when open,
toggle label too long, dropped YAML taken as data, Find Optimal alias missing, dock too narrow, Fit enabled without
files): 11 caught; "rows swapped" passed (the test compared the table with its own source), "dock too narrow" passed (a
fixed 40 % threshold), "Fit enabled without files" passed (no press) — the tests now compare with the fit result, measure
against the details dock's edge and press Fit; caught. Round 2 (12 of them; the two figure faults hang to the CLI test's
180 s timeout and were caught in round 1): all caught.

Found by the press test, not by the screenshots: the file-row buttons shared their path field's id (`##decay_file`), so the
field took every click — Load… never opened a dialog.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_config_1200x800.png`, `after_guide_800x600.png`, `after_help_1200x800.png`.

## 9. Persistence, guide, help, docs

Paths, options and the YAML buffer via `export_settings`. Help and guide shared with the Qt wizard (unchanged). README
requirements corrected. Guide 76: the `find_optimal` advice, the Agg note and the plot-window defect updated, the
reproducibility defect added.

## 10. Blocked / open

- Unseeded random starting values (known issue).
- The emtk help window's raw markdown (known issue `32c73e41b`).

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
