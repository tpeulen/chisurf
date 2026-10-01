# emtk port report — `minesweeper` (swap-candidate, audit-all row 15)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `minesweeper` / `chisurf/plugins/misc/games/minesweeper` |
| Port type | A (view port): Qt `MinesweeperWidget` = chigame canvas + Sound; rules in `core/game.py` (shared); the stream drew the view with emtk (`gui/app.py`) |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `86b2e0ec3` baseline; `26a21d4b1` emtk app at parity with the Qt tool; evidence commit "minesweeper: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

Modified `gui/__init__.py`, `manifest.json`; untracked `README.md`, `gui/app.py`, `gui/glyphs.json`, `gui/translations.py`,
`test/capture_native.py`, `test/renders/`, `test/test_native.py` (`pre-upgrade/`). All committed.

## 2. Play-compare checklist

| Qt | emtk | Present? |
|---|---|---|
| Board, hot-pixel counter, preset name, numbers in spectral colours, flag, cursor ring, footer | same (`before_populated.png` vs `before_emtk_populated_*.png`); flag glow smaller | yes |
| ↑↓←→ / WASD cursor, Enter/Space scan, F flag, R reset, Q/E preset (recentred cursor) | same (`test_bindings_match_the_qt_view`) | yes |
| Finished board ignores scan/flag, result message stays | **was not**: emtk replaced it with "Start a new game to play again." and played the effect → fixed | fixed |
| Held direction auto-repeat (0.28 s / 0.045 s, chigame timer) | OS key repeat delivered by the host | deliberate |
| Sound (music "underworld", effects) | greyed, shared tooltip; `make_app(audio_callback=...)` | gap (emtk), known issue |
| — | mouse: left click scans, right click flags, click the preset name | added by the stream |

## 4. Automated evidence

```
after: 1 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/minesweeper
compare: exit=0
```

## 6. Tests

```
$ python -m pytest chisurf/plugins/misc/games/minesweeper -q -p no:cacheprovider
33 passed in 17.01s
```

`test_emtk_minesweeper_parity.py` (8): a scripted game (scan, flag, scan a mine, two presses after the loss) equals the Qt view's
messages, status and revealed/flagged counts (subprocess, stub host); bindings; Sound greyed without a backend and playing the 620 Hz
scan effect with one; draws at three sizes; Qt-free; tooltips. Deliberate breakage: post-game guard removed → scripted test failed;
Q/E swapped → bindings test failed (`AssertionError: q`). Restored.

## 7. Screenshots read

`before.png`, `before_populated.png`, `before_emtk_populated_*`, `after_populated_*`. Same board; nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings` (stream's): board, mines, preset, cursor, sound flag. Guide/help: allow-listed games. Docs: none.

## 10. Blocked / open

Audio output for emtk (known issue "emtk games have no sound").

## 11. Self-check

- [x] D1 · [x] D2 (sound: emtk gap; key repeat by the OS) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [ ] D7 n/a · [x] D8 · [x] D9 · [x] D10
