# emtk port report — `tetris` (swap-candidate, audit-all row 12)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `tetris` / `chisurf/plugins/misc/games/tetris` |
| Port type | A (view port): the committed Qt `Tetris` (chigame canvas + Sound) held the rules in `tetris.py:TetrisGame`; the stream moved them into `model.TetrisModel` (the Qt game subclasses it) and drew the view with emtk |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `909dd054f` baseline; `ef03b24c5` emtk app at parity with the Qt tool; evidence commit "tetris: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `README.md`, `__init__.py`, `manifest.json`, `test/test_game.py`, `tetris.py`; untracked `app.py`, `drawing.py`, `glyphs.json`,
`model.py`, `spectrum.py`, `translations.py`, `test/capture_*.py`, `test/renders/`, `test/test_legacy_adapter.py`,
`test/test_native.py` (`pre-upgrade/`). All committed. `test_game.py` was ported to the model; its Qt render test
(`test_it_renders`, a GPU capture of the legacy game) was dropped by the stream.

## 2. Play-compare checklist

| Qt (committed) | emtk | Present? |
|---|---|---|
| Rules (gravity, rotation, wall kicks, line clears, scoring/level) | `model.TetrisModel`; diff against HEAD `TetrisGame` (`rules_diff_vs_head.txt`): action names, `__init__` host default, draw helpers moved to the view | yes |
| ←/→ A/D move, ↓ S soft, ↑ W rotate, Space hard drop, P pause, R reset | same (`test_bindings_match_the_qt_game`, `test_keys_drive_the_game_like_the_qt_controller`) | yes |
| Picture: well, spectral packets, COUNTS / LINES / GAIN, HELD, footer | same (`before_populated.png` vs `before_emtk_populated_*.png`) | yes |
| Sound (music "town", effects) | greyed, tooltip "no audio output"; takes a backend via `make_app(audio=...)` | gap (emtk), known issue |

## 4. Automated evidence

```
after: 1 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/tetris
compare: exit=0
```

## 6. Tests

```
$ python -m pytest chisurf/plugins/misc/games/tetris -q -p no:cacheprovider
30 passed in 14.68s
```

`test_emtk_tetris_parity.py` (9): Qt model identity and bindings (subprocess), pause and hard drop by key, Sound greyed without
audio and wired with a stub backend (switch, sfx, close), draws at three sizes, Qt-free, tooltips. Deliberate breakage: Space mapped
to rotate → bindings and key tests failed (`assert 0 == 4`); `set_enabled` dropped → sound test failed. Restored.

## 7. Screenshots read

`before.png`, `before_populated.png`, `before_emtk_populated_*`, `after_populated_*`: same well and labels; nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings` (stream's): game state and sound flag. Guide/help: allow-listed games. Docs: none.

## 10. Blocked / open

Audio output for emtk (known issue "emtk games have no sound"). The legacy Qt render test is gone with the stream's test port.

## 11. Self-check

- [x] D1 · [x] D2 (sound: emtk gap) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [ ] D7 n/a · [x] D8 · [x] D9 · [x] D10
