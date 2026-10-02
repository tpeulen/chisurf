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

## 8. Second cycle (LEFTOVERS): every game with real input, Breakout diagnosed, fixed and enabled

**Breakout diagnosis.** The audit called its draw "not finishing within 120 s". It does finish: the cost is the
software painter used by the audit and the screenshot helpers (`PixelPainter`), not a loop. cProfile of one 1200x800
frame (11 s before): 641 rounded rectangles (every brick halo layer and body went through `fill_convex`, about 25
triangles each, 9.4 s in `fill_triangle`) plus the full-viewport background fills (about 1M px of alpha blending in
Python each). `after` ran three frames per size plus the inventory frames, so 80 s in total and a 120 s harness cap
sounded like a hang. The live Qt host and the GPU host draw it in 20 to 60 ms (the Qt host test below). Fix in
`breakout/app.py`: the brick halo is three square-cornered layers instead of six rounded ones (alpha 4/8/12 sums to
the former opacity; the corners of a halo of at most 12/255 alpha were not visible); a frame is now about 4 s in the
software painter. The registry entry is `emtk: breakout.app:make_app`, "(not available)" is gone from the list. The
stream's uncommitted Breakout files (`app.py`, `model.py`, `drawing.py`, `glyphs.json`, `translations.py`, capture
scripts, renders, manifest `emtk` entry, `__init__` lazy import, `breakout.py` Qt view over the shared model) are
committed with this cycle.

**Real input.** `test/test_games_real_input.py` (20 tests): QKeyEvent / QMouseEvent are sent to the real
`ControlHost` built by `build_plugin_widget`, the host's paint timer runs with a real wall clock, and each test asserts
that the paddle, piece, cursor or dial moved.

| Control | Test |
|---|---|
| Breakout Left/Right held, release stops, Left back | `test_breakout_paddle_follows_held_keys_and_stops_on_release` |
| Breakout A/D, two keys for one direction | `test_breakout_letter_keys_a_d_steer_and_a_key_up_keeps_the_other_held` |
| Breakout Space launch, ball moves | `test_breakout_space_launches_the_ball_and_the_ball_moves` |
| Breakout P pause (ball frozen), M mute, R reset | `test_breakout_pause_reset_and_mute_keys` |
| Breakout focus_lost | `test_breakout_focus_loss_releases_every_held_key` |
| Breakout pointer drag, stuck ball follows | `test_breakout_pointer_drag_moves_the_paddle_and_the_stuck_ball` |
| Breakout live loop paints and ends | `test_breakout_frame_terminates_and_stays_cheap_in_the_live_loop` |
| Breakout in the hub (keys, launch) | `test_breakout_in_the_hub_takes_keys_and_pointer`, registry entry `test_breakout_is_enabled_in_the_registry_and_manifest` |
| Pong Up/Down, release, W/S, P, focus_lost, pointer drag | `test_pong_*` (3) |
| Tetris Left/Right one cell per press, Up rotate, held repeat, focus_lost, Space drop, P, R | `test_tetris_*` (3) |
| Minesweeper arrows, F, Enter, held repeat, focus_lost, Q/E; left click scans, right click flags | `test_minesweeper_*` (2) |
| Number Quest Left/Right, Q/E, held repeat, focus_lost, Enter, R; click the dial; caption halves | `test_number_quest_*` (2) |
| Every hub entry receives a real Left key | `test_every_game_in_the_hub_receives_a_real_key` |

Breakage, twice: round 1 (Breakout key release no-op, Breakout pointer drag no-op, Tetris focus_lost no-op) failed 6 tests;
round 2 (Pong pointer, Number Quest dial click, Minesweeper right click, hub key routing) failed 5; restored, 20 passed.

Tests: `python -m pytest chisurf/plugins/misc/games -q` 182 passed. Screenshots read at full size:
`breakout_hub_playing_1200x800.png`, `breakout_hub_playing_800x600.png` (no clipping; the caption shrinks to fit).

**Reuse.** The hub reuses every game's own emtk app (no copy), the shared registry, `emtk.qt_host.ControlHost`.
**Docs.** New `docs/guides/95_games.md` (+ figure `docs/guides/figures/games_breakout.png`, index row); the plugin
reference pages already list all five games.
