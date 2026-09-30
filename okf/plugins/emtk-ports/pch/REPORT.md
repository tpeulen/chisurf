# emtk port report — `pch` (Wave 0 pilot)

Author of the port and of sections 0–11: the implementing agent (Sonnet), 2026-09-30. The
agent could not write this file, so the reviewer saved its hand-over text here, corrected
where the evidence tool was at fault (section 4) and appended section 12 (review).

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `pch` / `chisurf/plugins/pch` |
| Port type | **B** — only a Qt `ChisurfDockTool` (`gui/tool.py`, 679 lines); the logic sat in the Qt class |
| Agent / date | implementing agent, 2026-09-30 |
| Effort | not measured (one session, about 25 minutes of agent time) |
| Commits | `b2496542f` Qt baseline, `138ceeeaa` native emtk app, `ec41fc2f8` evidence/docs/log; reviewer: this report + `deliberate.json` + re-run `compare.json` |
| Agent-board entry | `T-20260930-02` in `okf/agent-board.md` |

## 1. State at start

`git status --short -- chisurf/plugins/pch` printed nothing (clean); no live claim on the board.
Files edited that the agent did not write: `gui/__init__.py` (lazy export of the Qt `PCHApp`, so
`gui.app` imports without Qt), `README.md`, `test/plugin_help_guide_allowlist.txt` (one line
struck). `gui/tool.py` and the other Qt files are untouched.

## 2. Control checklist

| # | Qt control | emtk equivalent | Present |
|---|---|---|---|
| 1 | Load TTTR | `button_row` action `load` + `FileDialog` | yes |
| 2 | Compute PCH | action `compute`, `enabled()` | yes |
| 3 | Fit Model | action `fit` | yes |
| 4 | Save Results | action `save` + `FileDialog` | yes |
| 5 | Help | hand-drawn Help button, `EmTkHelpWindow` on `help.md` | yes |
| 6 | File (read-only) | `value` attr `filename` | yes |
| 7 | Channels | `value` attr `channels` | yes |
| 8 | Bin Time (μs) | `value` attr `bin_time_us`, suffix ` μs` | yes |
| 9 | Micro Time from / to | `value` attrs `micro_time_min`, `micro_time_max` | yes |
| 10 | Components (1–10) | `value` attr `n_components`, spin, `call: set_n_components` | yes |
| 11 | ε i, ⟨N⟩ i stacked spin boxes | one editable `table` section | yes (table) |
| 12 | Fit Results text | panel "Fit results", `info` source `results_text` | yes |
| 13 | Intensity trace | `implot` line (decimated to ~4000 points for display) | yes |
| 14 | Histogram (log y, points + fit) | `implot` scatter + line, log10 y | yes |
| 15 | Region selector | two `implot.drag_line_x` lines → `model.set_region` | yes (lines, no band) |
| 16 | Status bar | `info` source `status_line` | yes |
| 17 | Window drop of a TTTR file | `on_paths_dropped` / `files_dropped` | yes |
| 18 | Open / save dialogs | `emtk.file_dialog.FileDialog` | yes |
| 19 | Save writes npz/csv/txt + 2 PNG grabs | npz/csv/txt written; PNGs not | partly |
| 20 | Guide | none in the Qt tool | gained |

Screenshots of the Qt tool: `before.png`, `before_populated.png` (Leica_SP8.ptu, channel 1, 100 µs),
`before_populated_2comp.png`, `before_populated_computed.png`.

## 3. Files

`gui/model.py` (new, `PchModel`, Qt-free; results text and save code cut from `tool.py`, same
`PCHClient`), `gui/pch.view.json` (new), `gui/app.py` (new, `PchApp`, two plots, dialogs, help,
tour, job polling, `make_app()`), `gui/guide.json` (9 steps, 3 with `await`), `gui/help.md`,
`gui/__init__.py` (lazy export), `test/test_emtk_pch.py` (11 tests), `manifest.json` (added
`entrypoints.emtk`, `entrypoints.gui` kept), `README.md`, `docs/guides/04_fida_pch.md`,
`docs/guides/figures/04_pch_tool.png`, `test/plugin_help_guide_allowlist.txt` (line struck).

## 4. Automated evidence

The implementing agent's `compare` exited 1 because of two defects **in the evidence tool**, not
in the port: (1) emoji glued to a word (`📥loadtttr`) was never stripped, giving five false
"lost" entries; (2) there was no way to record a deliberate difference. The reviewer fixed both
in `test/gui/emtk_port_parity.py` (normalisation of both halves; `deliberate.json`), with tests,
and re-ran:

```
$ python -m test.gui.emtk_port_parity compare pch --out okf/plugins/emtk-ports/pch
{ "lost": [], "untooltipped": [] }
qt-free: True
exit=0
```

`after`: `48 controls, 0 without tooltip, qt-free=yes`. `compare.json` → `explained`: `ε1` and `⟨n⟩1`
(the stacked rows, now table columns); `stale_explanations: []`.

## 5. Deliberate differences

| Item | Why | Replacement |
|---|---|---|
| `ε 1`, `⟨N⟩ 1` | two stacked rows per species became one table | columns `ε`, `⟨N⟩`, `#` |
| two PNG grabs on Save | emtk has no plot/window grab outside `emtk.testing` | not ported (feature request); npz/csv/txt still written |
| drop guard `tttr_to_pto` | that is a Qt dialog in `chisurf.gui` | a dropped file opens directly; backend `open_tttr` resolves containers |
| accepted suffixes | `.spc` and `.pto` could not be chosen in the Qt tool | filter `TTTR (*.ptu *.ht3 *.t2r *.t3r *.pto *.spc);;All files (*)` |
| trace of 1.3 M bins | too slow to draw per frame | min/max decimation to ~4000 points, display only; saved npz keeps all bins |
| load on the GUI thread | froze the window ~0.6 s | load, compute and fit run on a `SnapshotJob`; buttons grey while it runs |
| region band | `implot` has drag lines, not a band | two vertical drag lines |
| declared status-bar messages | `Msg` is Qt | one status line; error text wins, same wording |
| live `pch --help` in the help dialog | needs runtime click output | static "Command line" section in `help.md` |
| Guide button | added | `guide.json` |

## 6. Tests

```
$ python -m pytest chisurf/plugins/pch -q -p no:cacheprovider
48 passed in 19.82s            (re-run by the reviewer; the agent reported 19.48 s)
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
10 passed
```

`test_emtk_pch.py`: test 1 (`test_model_produces_the_reference_result`, `test_model_matches_the_qt_tool` —
BH_SPC132, channels 0,8, 50 µs: 1246577 bins, 25 k-values, 2 components ε=[8.28226, 0.058043],
⟨N⟩=[0.0219635, 8.75014], χ²=1018.399, dof 21; the second test runs the Qt `PCHApp` side by side),
test 2 (actions, errors, enabled states, save writes 3 files), test 3 (spec keys exist on the model),
test 4 (draws empty and populated at 1200×800 and 800×600), test 5 (Load→Compute→Fit→Save through the
app's job), test 6 (Qt-free), test 7 (tooltips), test 8 (settings round trip), plus a guide/await test.

Deliberate breakage (each broke, failed, restored): test 1 (`bin_time_us * 2.0` → `623289 == 1246577`),
test 2 (no-file error removed → message mismatch), test 5 (`start_job` no-op → file never loaded).

Pre-existing failures not caused by this port: `test/test_plugin_help_guide_seam.py` has 22 failures
in other plugins' guides (14 `guide_is_a_tour`, 5 `guide_steps_point_at_real_widgets`, 1 `help_is_substantive`,
1 `every_gui_plugin_has_help_and_guide`, 1 stale allow-list); `test/test_prd_mentions.py` stale entries for
`kappa2_dist/gui/tool.py` and `tttr_time_windows/tests/test_construction_smoke.py`.
(`test_shipped_help_is_drawn` was red for 26 plugins because the guard did not know `EmTkHelpWindow`;
the reviewer fixed the guard, it passes.)

## 7. Screenshots looked at

`after_1200x800.png` (empty plots with axes, four buttons, form, species table, status; legend moved to
north-east), `after_800x600.png` (buttons wrap to two lines, all whole), `after_populated_1200x800.png`
(Leica_SP8, channel 1, 100 µs, 1 component: trace, histogram with fit, ε 66.2864, ⟨N⟩ 0.2162, χ² 7445.30,
red. 64.742, dof 115 — equal to `before_populated.png`), `after_populated_800x600.png`,
`after_populated_2comp_1200x800.png`, `after_dialog_1200x800.png`. No clipped label, overrun text,
overlapping windows, empty panel, axis-less plot or oversized status box is visible. `⟨N⟩` reads as `(N)`:
Menlo's angle brackets are shallow at the default size (not an emtk bug). The fit-range lines sit on the
plot border at first (range 0 to max k, as in Qt).

## 8. Workflow

Data: `test/data/tttr/BH/132/BH_SPC132.spc` (tests, docs figure), `test/data/clsm/Leica_SP8.ptu`
(before/after pair). Load (button or drop) → set Channels `0,8`, Bin time `50` → Compute PCH
(1,246,577 bins, 25 k-values) → Components 2 → Fit Model (ε 8.2823 / 0.0580, ⟨N⟩ 0.0220 / 8.7501,
χ² 1018.40) → Save Results (npz, csv, txt).

## 9. Persistence, guide, help, docs

Persistence: the Qt tool stored nothing of its own; the emtk app exports `folder`, `channels`,
`bin_time_us`, `micro_time_min`, `micro_time_max`, `n_components`, `epsilons`, `ns`; bad values are
ignored (test 8). Guide: 9 steps, awaits on `file_loaded`, `computed`, `fitted` (released by outcome, not
by the button press). Help links pass the seam guardrail. Docs: guide 04 text and figure, README. The
"Known defects" sentence in guide 04 ("a two-component fit did not return within 5 minutes") was replaced
by the measured result (about 1 s, χ²ᵣ = 48.5 = 1018.40/21) — consistent with the test numbers.

## 10. Blocked / open questions (for the reviewer)

1. Evidence tool: fixed (section 4).
2. `⟨N⟩` renders as `(N)`: font property, no action.
3. emtk has no supported PNG export of a window/plot: feature request (open).
4. PRD gaps found by the pilot: lazy `gui/__init__.py`; allow-lists must be struck in the same change;
   the help-drawn guard; the recorder does not see table columns or spec-section contents; repo-root
   path in the test template; subagents cannot write REPORT.md. All folded into the PRD.
5. `okf/plugins/emtk-migration-inventory.md` is untracked (another stream), so no note was added there.
6. `chisurf/emtk/help_guide.py` hard-codes accent colours for the tour/help buttons (shared code, not
   changed): open.

## 11. Definition of Done

D1–D10 met (D2 via `deliberate.json`; `compare` exit 0 after the tool fix).

## 12. Review (reviewer, 2026-09-30)

Verified by the reviewer, not taken from the hand-over: commits touch only pch files, its docs, the
allow-list line and the agent's own log hunk; `pytest chisurf/plugins/pch` 48 passed; a fresh
`after` run gives the same 48 controls as the committed `after.json`; `grep` for Qt imports in
`gui/app.py` and `gui/model.py` prints nothing; `gui/tool.py` untouched; before and after populated
screenshots read side by side with equal numbers. **Accepted.** Follow-ups: the PNG-export feature request
for emtk, the hard-coded colours in `chisurf/emtk/help_guide.py`, and the 22 unrelated guide failures.
