# emtk port report — `microtime_shifter` (upgrade, audit-all row 42)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `microtime_shifter` / `chisurf/plugins/tttr/tttr_microtime_shifter` |
| Port type | A+B: the Qt `MicrotimeShifterTool` (DockArea: Files (`PathListWidget`), Micro-time Shift (per-channel spin rows + reset), Histogram (chiplot, draggable trigger lines), Status; toolbar Save / Show Trigger / Log Y / Level / Pos / Auto Align; save asks DB-or-file) over `MicrotimeShifterClient`; the stream's emtk `gui/app.py` (883 lines) over the same client |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `dadca9336` baseline (+ `tests/demo_data.py`); `a6a00ed3f` emtk app at parity with the Qt tool; evidence commit "microtime_shifter: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `api/shift.py` (a re-export `test_shift.py` imports), `backend/services.py`
(same-named inputs written to separate subfolders), `manifest.json` (emtk entrypoint); untracked `gui/app.py`,
`gui/guide.json`, `gui/help.md`, `tests/test_native.py` — untouched since 2026-09-29, no claim on the board: the migration
stream's settled work, committed with the app. Qt `gui/tool.py` and `gui/client.py` unchanged (= HEAD).

## 2. Demo with a known answer (`tests/demo_data.py`)

Two routing channels (0, 8) with the same sharp peak (0.3 ns decay) whose rising edges sit at bins 600 and 1000 of 4096, on a
flat background. With the tool's default trigger (20 % of the highest bin = 124, target 10 % of the bins = 409) the edges are
found at 601 and 1001, so auto-align must give 0 → (409 − 601) mod 4096 = 3904 and 8 → 3504. Both the committed Qt tool and
the stream's app did (`before_*`).

## 3. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| Files: PathListWidget (Files / Folder / Database / Remove / Clear, drop) | Files…, Folder…, Database…, Clear, right-click remove, drop | same + **➖ Remove** button; the buttons wrap in a narrow dock (Clear ran off at 800 px) |
| toolbar Show Trigger, Log Y, Level, Pos, Auto Align | checkboxes + int fields + button, hand-drawn | spec `shifter.view.json` panel *Alignment*: Show trigger lines, Log Y, Trigger level, Target bin (edits re-align through the spec's `call`, bounded by the bin count), ⚡ Auto align |
| per-channel spin rows + reset (global shift has no Qt control) | Global shift + channel rows with Reset | panel *Shifts*: Global shift (spec) + custom `channel_shifts` rows (↺ Reset on the label line — it clipped beside the field) |
| Save…: DB-or-file choice; one file → name, several → folder | Save shifted…, batch folder, Register in MMFDB, sample id/list, New sample… | panels *Save* and *MMFDB* (folded) from the spec; same actions |
| histogram with draggable level/position lines, legend | implot stairs + drag lines, align on release | same |
| Status tab | Status dock | same |
| no guide; help via toolbar? none | help + 3-slide guide (no waits), at the bottom of the panel (cut off at 800×600) | 📖 Guide / ❓ Help head the Files dock; help rewritten; guide of 9 steps on real controls, Files…/Auto align/Save await presses; panels unfold for their step |
| — | file dialog in an unsized window; rendered every frame | sized dialog windows (file, new sample); frames only while a job runs or a line is dragged |

## 4. Automated evidence

```
after: 39 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/microtime_shifter
compare: exit=0   (lost [] after deliberate.json / stale [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json`: "Histogram" (the Qt dock header → the histogram dock), "Level" → Trigger level, "Pos" → Target bin,
"Show Trigger" → Show trigger lines — renames. "Remove" was first reported lost (the stream had it only as a right-click
item); a button was added. Save asks nothing up front: file save and MMFDB registration are separate buttons instead of the
Qt DB-or-file question.

## 6. Tests

```
$ python -m pytest chisurf/plugins/tttr/tttr_microtime_shifter/tests -q -p no:cacheprovider
57 passed, 2 skipped   (the 2 need test/data/clsm/Leica_SP5.ptu, absent here)
```

`test_emtk_shifter_parity.py` (17): the Qt tool in a subprocess on the demo — default trigger, auto-align shifts, backend
preview and saved file equal the emtk app's; the rising edges found here from the photons lie within 3 bins of the
generator's, the shifts land them on the target, and the saved file holds every photon at `(micro + shift) % N` with macro
times and routing unchanged; actions say what is missing (no files, no folder, no sample, unsupported file); a mixed
bin-count queue is refused in the window; frames requested while loading; a dropped folder queues its file; Remove takes
the selected file off the queue (not the disk); every spec field and button carries its description; a target-bin edit
re-aligns; channel rows reset; guide targets drawn (folded panels unfold), awaits released by presses; draws empty and
populated at both sizes with every button inside the window and the file buttons inside their dock; settings round trip
(files reload, shifts restored); help page; Qt-free; tooltips.

Deliberate breakage, round 1 (16: align on the peak, preview shift sign, global shift not exported, target edit no
re-align, target unbounded, save enabled without files, not animating, dialog never drawn, Files… not told to the tour,
reset row missing, file buttons never wrap, help missing, folded panel never revealed, drop ignores folders, bin-count check
removed, preferences not restored): 14 caught; "never wrap" passed (the clip check measured the window, not the dock) and
"help missing" passed (no help test) — both checks added, both caught. Round 2 (all 16): all caught.

## 7. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png`, `after_guide_800x600.png`, `after_help_1200x800.png`.
They caught: the emoji variation selector (U+FE0F) drawn as "¤" in dock titles and labels, "ℹ"/"📋" without a glyph, the
clipped Reset buttons, Clear off the dock edge, a clipped empty-state hint.

## 9. Persistence, guide, help, docs

Files, current file, shifts, trigger, display toggles and batch folder via `export_settings` (restored after the files
reload). Help and guide; off the help/guide allow-list. Docs: the tool has no concept or guide page of its own (guide 12
names it in passing) — open item below.

## 10. Blocked / open

- **No docs page** for the shifter (concept: cyclic micro-time shift, rising-edge alignment; guide: the workflow above with
  the demo). Not written in this port; recorded here and in the PRD-153 resume point.
- **Legacy Qt display defect** (not fixed, Qt is legacy): after a load the toolbar Level/Pos boxes show 0 and the trigger
  lines are not drawn (`before_populated.png`), while the tool's state holds 124/409.
- **Test-package shadowing** (known-issues entry with this commit): importing the tttr plugin package moves
  `modules/ndxplorer` to the front of `sys.path`, and its own `test` package then shadows the repo's — a script that imports
  `test.gui` after the plugin fails with `No module named 'test.gui'`. Workaround: import `test.gui` first (the capture
  script and the parity test do).
- The emtk help window's raw markdown (known issue `32c73e41b`) applies here too.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
