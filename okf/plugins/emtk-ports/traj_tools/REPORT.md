# emtk port report - `traj_tools` (audit-all row 72, hub; upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-03, T-20261003-LEFTOVERS2. Type A hub: the Qt `TrajectoryToolsTool` (dock tabs of the eight trajectory tools, status bar, Guide/?, drop routing) against the stream's emtk hub that hosts the accepted `traj_*` child apps. Verdict: **accept**.

Commits: baseline + stream state (message "traj_tools: Qt baseline ..."), the app/tests commit ("traj_tools: emtk workspace at parity ..."), then the evidence/docs commit.

## 1. State at start
Stream hub (`before_emtk_populated_*.png`): list + description + child; no Help/Guide, no status line, a drop reached the child without any word on what happened, its own `Tool unavailable` window, 7 tests (hub only). The stream's `test/renders/` captures and `capture_native.py` are kept in the baseline commit.

## 2. Qt checklist (`before.png`, `before_populated_{1..8}_*.png`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | eight dock tabs in order Align, Convert, Energy Calc, FRET, Join, Remove Clashed, Rot Translate, Save Topol | list with the same names/order (asserted vs the Qt widget), tooltip = description | yes |
| 2 | tab close buttons | none: a closed Qt tab could not be reopened | deliberate |
| 3 | status bar `Active tool: X` | status line, same text (asserted vs the Qt status bar) | yes |
| 4 | drop on the window: first path into the panel's `trajectory_filename`, message `X takes no dropped file ...` | the drop goes to the open tool's own drop handler (it routes by file type, a superset); the line says `X: file` or that nothing took it | yes (superset; wording differs) |
| 5 | Guide, ? | Guide (tour, 1 await), Help | yes |
| 6 | window geometry, panel state | active tool + the opened tools' settings (pending state for tools not yet opened) | yes |
| 7 | panels built eagerly | built on first selection (state kept); a failing tool is reported, the rest works | deliberate (faster) |
Hosted tools are the accepted native apps; their controls are reported in their own REPORT.md.

## 3. Reuse
Subclass of `calculator/hub/gui/app.py` `CalculatorHubApp`; the eight native `traj_*` apps from `registry.py`; `chisurf/emtk/help_guide.py`; `emtk_test_input.Driver`, `project_browser` layout checker, `emtk_hermetic`. No fork; the stream's hand-copied event forwarding is gone.

## 4. Evidence
`after: ... 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [] after `deliberate.json`: the Qt capture lists every tab, the hub shows one tool). Screenshots `after_populated_{1_align,2_fret}_*`, `after_help_*`, `after_tour_*` at both sizes.

## 5. Layout
Both sizes read: no overlap/clipping on any of the eight tools (asserted, `layout_problems` + `clipped_texts` over every tool), the list 130-180 px, the status line at the bottom, tour cards clear of their targets. Defect found in the baseline script: its trajectory path was wrong by one directory (a nonexistent file); fixed in the scripts.

## 6. Tests
`pytest chisurf/plugins/traj/traj_tools`: **34 passed** (7 stream hub tests kept, 2 Qt construction tests, 10 parity, 14 real-input). Parity vs the live Qt window: tool list/order, status text, a dropped DCD fills the same field. Real-input: each entry click, state kept, arrow keys, pointer + typing into the open tool in its own coordinates (stride typed and committed), drop and unrecognised drop, wheel in a short window, Help/Guide, tour walked at both sizes with the awaited entry, card drag. Breakage twice (status text, drop routing): 5 failures, restored. Guard: real `~/.chisurf` unchanged (note: other agents' processes write `~/.chisurf/emtk` concurrently, which can trip the guard on a busy machine).
Qt test note: the Qt workspace is built once per module under a temporary HOME and kept alive (destroying it bus-errors at fixture teardown).

## 7. Docs
`docs/guides/81_trajectory_tools.md` (Open the tools section for the list/status/drop behaviour, hub figure `traj_tools_hub.png`), `docs/reference/plugins/traj_tools.md` (native window), `gui/help.md`, `gui/guide.json` (6 steps, 1 await). The per-tool figures remain those tools' own.

## 8. Findings
No behaviour regression found in the hub itself; the child apps are untouched. Not touched: `chisurf/emtk/*`, emtk, preview gate.
