# emtk port report — `number_quest` (swap-candidate, audit-all row 9)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `number_quest` / `chisurf/plugins/misc/games/number_quest` |
| Port type | A (view port): Qt `NumberQuestWidget` = chigame GPU canvas + Qt Sound button; the earlier stream drew the same view with emtk (`app.py`); the rules (`core/game.py`) are shared |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `96a2042f1` baseline; `bdf892ca5` emtk app at parity with the Qt tool; evidence commit "number_quest: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/__init__.py`, `manifest.json`; untracked `README.md`, `app.py`, `drawing.py`,
`glyphs.json`, `gui/app.py`, `gui/translations.py`, `translations.py`, `test/capture_*.py`, `test/renders/`, `test/test_emtk_app.py`,
`test/test_native.py`. All committed with the app.

## 2. Play-compare checklist (Qt chigame view → emtk)

| Qt | emtk | Present? |
|---|---|---|
| Picture: title, turns/score, decay of the estimate with past guesses dotted, τ readout, message, two control captions | same (`before_populated.png` vs `before_emtk_populated_*.png`: same layout and glyphs) | yes |
| Keys: ←/→ and A/D fine, Q/E ±10, Enter/Space confirm, R new round, held-key auto-repeat 0.28 s / 0.045 s | same (`test_bindings_match_the_qt_game`; repeat constants equal) | yes |
| Messages: Longer/Shorter lifetime, found it, out of turns | identical (`test_rounds_match_the_qt_game`, 5 rounds, also turns/score/status) | yes |
| Sound button (music + "guess" effect via chigame audio) | **no audio output in emtk**: greyed, tooltip says so | gap (emtk), known issue "emtk games have no sound" |
| Mute when the window is not in front | `focus_lost` disables audio | yes |
| — | extra: click the plot to dial, click captions to submit / restart | added by the stream |

## 4. Automated evidence

```
after: 1 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/number_quest
compare: exit=0   (before ['sound'], after ['sound'])
```

## 5. Deliberate differences

none in `compare.json`. Behaviour: no sound (emtk gap, above); mouse dialling added.

## 6. Tests

```
$ python -m pytest chisurf/plugins/misc/games/number_quest -q -p no:cacheprovider
35 passed in 15.03s
```

`test_emtk_number_quest_parity.py` (8): rounds and bindings vs the Qt game driven with a stub host in a subprocess, Sound greyed
without audio and working with a stub backend (switch + 880 Hz "guess" effect on a win), draws at 1200×800 / 800×600 / 560×420,
Qt-free, tooltips. Settings round trip: the stream's `test_native.py`. Deliberate breakage: changed the "won" message → rounds test
failed (`AssertionError: [37]`); swapped Q/E → bindings test failed (`AssertionError: q`). Restored. Pre-existing failures: none.

## 7. Screenshots read

`before.png` (tool grab of the GPU canvas), `before_populated.png`, `before_emtk_populated_{1200x800,800x600,560x420}.png`,
`after_populated_*` (Sound greyed). Nothing clipped.

## 9. Persistence, guide, help, docs

`export_settings`: target, history, estimate, sound flag (stream's); the Qt widget kept window geometry only. Guide/help: games are
allow-listed (`chisurf/plugins/misc/games/number_quest/gui`), none in Qt either. Docs: none.

## 10. Blocked / open

Audio output for emtk (known issue). 

## 11. Self-check

- [x] D1 · [x] D2 (sound: emtk gap, declared) · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [ ] D7 n/a (allow-listed) · [x] D8 · [x] D9 · [x] D10
