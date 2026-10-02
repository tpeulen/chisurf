# emtk port report — `games` (upgrade, audit-all row 48)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `games` / `chisurf/plugins/misc/games` |
| Port type | A+B hub: the Qt games hub (NavigationPanelTool: navigation list, lazily built panels, ◀ Back / ⏩ / Next ▶ stepper, status bar) → the emtk launcher (`registry.py` + sidebar/header app) hosting each game's own emtk app |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `d3b8d9750` keys land; `fff4ca45c` launcher restyle (the parity work); evidence commit "games: evidence and report" |
| Board | `T-20261002-EMTK1D` |

## 1. State at start

The launcher had already been brought to parity by the two owner-feedback commits above (keys through the Qt host,
restyle). This row adds the missing evidence and one test. The stream's uncommitted Breakout port
(`breakout/app.py`, `model.py`, `drawing.py`, …, `test/capture_hub.py`, `test/renders/`) is **not mine** and is left
untouched; it is audit-all row 87.

## 2. Parity checklist (`before.png` (Qt) vs `after_*.png`, `launcher_after_<game>_*.png`)

| Qt hub | Now |
|---|---|
| navigation list: Number Quest, Minesweeper, Tetris, Pong, Breakout (emoji icons) | sidebar with the same five, names only, description in the tooltip; Breakout reads "(not available)" |
| Sound toggle above the game | Sound button above the game |
| panel built when selected ("Select … to load.") | the game is built when selected and fills the area below a header (name, description, "Keys: …") |
| ◀ Back / ⏩ / Next ▶ stepper, "Ready" status | not reproduced (deliberate) |
| keys, releases, focus loss reach the game | same, also through the Qt host (`test_game_keys_through_qt_host.py`) |
| — | frames only while the open game animates (`test_launcher_frames.py`) |

## 3. Automated evidence

```
after: 9 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/games
compare: exit=0   (Qt internals in deliberate.json)
```

## 4. Deliberate differences

`deliberate.json`: the Qt list's row numbers 1–5, the stepper (it runs a panel's Run action and moves on, which means
nothing for games), the status bar's "Ready", the "Select … to load." placeholders, and "breakout", which shows as
"Breakout (not available)" until its own port lands.

## 5. Tests

```
$ python -m pytest chisurf/plugins/misc/games -q -p no:cacheprovider
161 passed
```

New: `test/test_launcher_frames.py`. The launcher's `animating()` follows the open game. Without this test,
a launcher that ignored the child's animation went unnoticed.

## 6. Breakage check (run twice, 6 faults, 6/6 caught both times after the new test)

| Fault | Caught by |
|---|---|
| keys not routed to the child | `test_keys_reach_the_game_selected_in_the_launcher` |
| releases not routed | same |
| focus loss not routed | same |
| child animation ignored | `test_frames_follow_the_open_game` (missed both times before it existed) |
| "(not available)" label lost | `test_render_pending_and_populated_child_with_tooltips` |
| "Keys:" line lost | same |

## 7. Screenshots read

`before.png` (Qt: list, Sound, empty panel, stepper, "Ready"), `after_800x600.png` (sidebar, header with keys line,
Number Quest filling the area, Breakout "(not available)"), and the restyle's `launcher_after_<game>_*.png` set.
