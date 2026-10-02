# emtk port report — `traj_convert` (upgrade, audit-all row 43)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `traj_convert` / `chisurf/plugins/traj/traj_convert` |
| Port type | A+B: the Qt `MDConverter` widget (AutoForm over `convert_structures.view.json`: *Input* panel with the custom `traj_convert_io` rows (topology, trajectory — a folder when the toggle is on —, target folder), the folder toggle and the frame range; *Output* panel with name, format, split and the custom `traj_convert_run` ▶ Convert; info log) over `MDConverterViewModel`; the stream's hand-drawn emtk `app.py` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `e0ac97b3f` baseline; `826e3fe66` emtk app at parity + one frame selection for every mode (guide 81, known-issues); evidence commit "traj_convert: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `__init__.py`, `manifest.json`, `view_model.py` (`log_text()`); untracked
`app.py`, `strings.py`. Tracked edits committed with the app; `app.py` rewritten, `strings.py` dropped.

## 2. The conversion, fixed for both hosts

**Measured at baseline** (frames 10 to 50 at stride 10 into one DCD): both hosts wrote **4** frames (10–40), not 5 — the
range was `slice(first, last, stride)`. Guide 81 also listed split mode ignoring the stride and crashing on a range (it
called `iterload` without the stride, and with `chunk=None` when a range was set) and folder mode reading the folder path
itself. `convert()` now takes one `frame_selection(n)` (first to last **inclusive**, −1 = the end) for both outputs, reads a
folder's `*.pdb` in name order as consecutive frames (`trajectory_data.join`), names split files by their source frame,
refuses an empty selection ("The frame range selects no frames.") and a missing target folder (it used to write into the
working directory). Multi-frame PDB output already worked (append mode and MODEL records are in core): that defect was
stale. New known issue: `trajectory_data.load` reads a multi-model PDB as its first model, so ChiSurf cannot read back a
multi-frame PDB it wrote (guide 81 *Known defects* says so).

## 3. The shared app grew four things (`chisurf/plugins/traj/emtk_tool.py`)

Rows that take a folder (always, or when `folder(model)` says so — the converter's toggle); specs of several panels kept as
titled, folding panels (single-panel tools unchanged); an action drawn in a custom section of its own (`action_key`) that
runs without a save dialog (`dialog_title=None`); a `done` notice after a successful run (the Qt confirmation box). The
status is drawn once (a first version drew it beside the rows too — caught by the breakage round).

## 4. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt widget | Stream's emtk | Now |
|---|---|---|
| Topology / Trajectory / Target folder rows, `…` (file, or folder per the toggle; target always a folder) | free-text fields | read-only rows, file or folder dialogs per the toggle, drops (a dropped folder goes to the folder row) |
| folder toggle, First/Last frame, Stride | toggles and int steppers | the spec's fields, descriptions as tooltips |
| Filename, Format (.dcd/.pdb), Split | text, combo, toggle | the spec's fields |
| ▶ Convert; "Choose a trajectory first.", "Conversion done!", "Conversion failed" boxes | button | same button in the Output panel; same texts in the window; also "Choose a target folder first." |
| collapsible Input / Output panels | flat | folding panels |
| log | log lines | scrolling, wrapping log |
| synchronous | synchronous | worker thread |

## 5. Automated evidence

```
after: 26 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/traj_convert
compare: exit=0   (lost: the Qt Format combo's internals, in deliberate.json)
```

## 6. Deliberate differences

`deliberate.json`: ".pdb" and "2" are the Qt Format combo's second item and its popup's row number. Behaviour changed for
both hosts by §2; a missing target folder is refused.

## 7. Tests

```
$ python -m pytest chisurf/plugins/traj/traj_convert -q -p no:cacheprovider
29 passed
```

`test_emtk_convert_parity.py` (16): the Qt widget in a subprocess (nothing chosen, a range, an empty range) — the emtk file
equals the Qt file and `source[[10, 20, 30, 40, 50]]`; −1 reaches the end; split writes `frames_00000000.pdb` … `_400`
at stride 100, each equal to its source frame; a multi-frame PDB holds three MODELs whose coordinates, read from the PDB
columns, equal the source (the loader cannot be the reference, see §2); a folder of three PDBs becomes three frames, the
browse dialog a folder dialog; same answers and captions as Qt, a missing target refused, the failure drawn once; spec
fields with descriptions, panels fold; busy state with exactly one run for two presses; drops fill all three rows; guide
awaits; draws (log lines drawn); settings round trip; help; Qt-free; tooltips. The stream's (uncommitted) Traj Tools hub
test restored a non-existent `run.dcd`; the shared app does not restore a missing path, so that test now uses the hgbp1
file — edited in place, left uncommitted for the hub's port (board note).

Deliberate breakage, round 1 (12: last frame exclusive again, split ignores the selection, split numbered by position,
folder mode reads the folder, no target check, done not said, failure caption, browse ignores the toggle, target row takes
files, panels do not fold, empty range not refused, nested log not hosted): all caught. Round 2 (9 applicable shared-app
faults): "busy guard removed" (no run count), "log not drawn" (no log assertion) and "status not drawn" (the duplicate
drawing hid it) passed at first; run count and log assertion added, the duplicate removed and the failure asserted drawn
once — all caught.

## 8. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_dialog_1200x800.png` (the target-folder dialog: an action without a save
dialog shows a row's browse dialog), `after_guide_800x600.png`.

## 9. Persistence, guide, help, docs

Paths (if still present), toggles, range, name, format, split via `export_settings`. Help and guide new; off the allow-list.
README corrected. Guide 81: Convert paragraph rewritten, four Known defects replaced by the multi-model read-back one;
known-issues item 7 marks the convert defects fixed and a new entry records the read-back gap.

## 10. Blocked / open

- Multi-model PDB read-back (known issue, core).
- The hub test edit (above) waits for the Traj Tools port to commit it.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
