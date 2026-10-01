# emtk port report — `pong` (swap-candidate, audit-all row 11)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `pong` / `chisurf/plugins/misc/games/pong` |
| Port type | A (view port): the committed Qt `Pong` (chigame GPU canvas + Sound button) holds the rules in `pong.py:PongGame`; the earlier stream moved them into `model.PongModel` (the Qt `PongGame` now subclasses it) and drew the view with emtk (`app.py`) |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `839fb2943` baseline; `59731c87f` emtk app at parity with the Qt tool; evidence commit "pong: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `README.md`, `__init__.py`, `manifest.json`, `pong.py`; untracked `app.py`, `drawing.py`, `glyphs.json`, `model.py`,
`translations.py`, `test/capture_*.py`, `test/renders/`, `test/test_emtk_app.py` (`pre-upgrade/`). All committed. Baseline from
HEAD `pong.py` (`scripts/qt_head.py`).

## 2. Play-compare checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Rules (serve, CPU, bounce, score to 7, particles) | `model.PongModel`; method diff against HEAD `PongGame` (`rules_diff_vs_head.txt`): only `__init__` (host argument), `_sfx` (host guard), `update` (action names as strings) | yes |
| P1 ↑/↓, Enter/Space confirm, P pause, R reset, M mode, N mute; P2 W/S | same (`test_bindings_match_the_qt_game`, `test_keys_drive_the_game_like_the_qt_controller`) | yes |
| Picture: scores, transfers, field, paddles, ball, HELD, footer captions | same (`before_populated.png` vs `before_emtk_populated_*.png`); ball glow smaller | yes |
| Sound button (music "battle", effects) | no audio output in emtk: greyed, tooltip says so | gap (emtk), known issue "emtk games have no sound" |
| — | drag a paddle with the mouse, clickable captions; 1/120 s sub-steps against tunnelling | added by the stream |

## 4. Automated evidence

```
after: 1 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/pong
compare: exit=0
```

## 5. Deliberate differences

none in `compare.json`. Behaviour: no sound (emtk gap), mouse control and sub-stepping added.

## 6. Tests

```
$ python -m pytest chisurf/plugins/misc/games/pong -q -p no:cacheprovider
35 passed in 15.16s
```

`test_emtk_pong_parity.py` (9): Qt game is a `PongModel` and its P1/P2 bindings equal the emtk keys (subprocess); pause / mode / reset
by key; Sound greyed without audio, working with a stub backend; draws at three sizes; Qt-free; tooltips. Deliberate breakage:
swapped M/N → bindings and key tests failed (`AssertionError: m`); Sound toggling without audio → sound test failed. Restored.

## 7. Screenshots read

`before.png`, `before_populated.png`, `before_emtk_populated_*`, `after_populated_*`. A downscaled read suggested "Up/Down optio"
at 820×640; the full-size crop shows "optic" complete (no defect).

## 9. Persistence, guide, help, docs

`export_settings`: game fields and sound flag (stream's). Guide/help: allow-listed games, none in Qt. Docs: none.

## 10. Blocked / open

Audio output for emtk (known issue).

## 11. Self-check

- [x] D1 · [x] D2 (sound: emtk gap) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [ ] D7 n/a · [x] D8 · [x] D9 · [x] D10
