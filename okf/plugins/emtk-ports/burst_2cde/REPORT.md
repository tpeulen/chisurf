# emtk port report — `burst_2cde` (swap-candidate, audit-all row 23)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_2cde` / `chisurf/plugins/burst/burst_2cde` |
| Port type | B (run port): the Qt `BurstTwoCdeTool` already draws `BurstTwoCdeApp` in a `ControlHost` and owns the run (ChiSurfProgress worker, result cache, stamp, showEvent run); the emtk app runs the same drawing with the stream's toolkit-free `TwoCdeController` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Commits | `38f1913c5` baseline; `d7261b221` emtk app at parity with the Qt tool; evidence commit "burst_2cde: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `core/computation.py` (import of the shared burst reader), `gui/app.py` (window
end fix, disabled settings while running, tooltips, emtk help/guide), `manifest.json` (emtk entrypoint); untracked
`gui/controller.py`, `tests/test_emtk_controller.py`. All committed with the app.

## 2. Parity checklist (Qt run → emtk run)

| Qt `BurstTwoCdeTool` | Stream's controller | Now |
|---|---|---|
| Run / Restart: `allow()` then run (an explicit run forgets a Stop) | never forgot | same as Qt |
| showEvent: run a set folder unless that exact run was stopped ("Stopped earlier — press Run to compute 2CDE") | nothing | first frame does the same |
| Unchanged skip: "Unchanged — kept the previous 2CDE result (🔁 Restart recomputes it)" + Restart flagged | other words, no flag | Qt words (no emoji), Restart drawn orange |
| ChiSurfProgress dialog: "Reading burst data …", "Computing 2CDE …" with a burst count | status text only | progress bar with the same captions, fraction from compute_2cde's `set_value` |
| Stop: cancel, abandon, nothing written | same | same |
| 2c4 write failure: logged, result kept | raised: result lost, "Error: …" | result kept, status says why nothing was written |
| Read/compute failure: "Error: …", result cleared | same, result not cleared | same as Qt |
| Drop: first folder adopted and run; else "2CDE reads a burst-analysis folder; {name} is not one." | controller method, **never reached** (the app had no drop hook, the host ignored drops) | `files_dropped` → Qt behaviour and text |
| Folder: QFileDialog | FileDialog in a full-viewport window | FileDialog in a sized window (`after_folder_dialog_1200x800.png`) |
| frames: Qt events | continuous rendering | 10 Hz while running, idle otherwise |
| window geometry (manifest) | host's | host's |

Shared drawing (both hosts), fixed: the 2CDE axis auto-fit put the extreme bursts on the plot edge, half clipped
(`before_populated.png`, `before_emtk_populated_*`: the top burst at ~66 and the lowest ones); now fitted with margin once per
result (`COND_ONCE`, re-applied when the range changes, so a zoom holds). The action row cut off Help in a narrow pane (the Qt
grab shows "? H" at 1200 px); it now wraps (`after_populated_800x600.png`).

## 4. Automated evidence

```
after: 40 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_2cde
compare: exit=0   (lost [] after deliberate.json / stale_explanations [] / untooltipped [])
```

## 5. Deliberate differences

`deliberate.json`: `?` — the help button of the Qt toolbar the tool hides (`toolbar.setVisible(False)`); both hosts draw
"❓ Help". Behaviour: progress bar instead of a modal progress dialog; a failed companion write is stated in the status.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_2cde -q -p no:cacheprovider
32 passed, 1 skipped in 23.27s      (skip: "the engine is present, which is the normal case")
```

`tests/demo_folder.py` writes a real burstwise folder: SPC-130 file (12.5 ns ticks set before writing — without it tttrlib
writes 1.68 ms ticks and every τ gives 2CDE = 110) one level above `burstwise/bi4_bur/m000.bur` (zero-interleaved: without
the separator rows the reader keeps every other burst), green/red counts for the E axis. Static bursts read ~10.5, dynamic ~44.5.

`test_emtk_2cde_parity.py` (13): a run through the controller equals the Qt tool's `_analysis_worker` on the same folder
(subprocess; values, fingerprint parameters, companion files) and the known answer; unchanged skip + Restart; Stop → nothing
written → shown again says "Stopped earlier" → explicit Run computes; first-frame run; drop of a file and of a folder;
progress caption and fraction while running and frames requested; errors (missing folder, write failure keeps the result,
read failure); every guide target drawn; draws empty and populated at 1200×800 / 800×600 with every button inside the pane;
the axis request covers every burst and is stable across frames; Qt-free; tooltips. The stream's `test_emtk_controller.py`
follows the Qt drop message.

Deliberate breakage, round 1: first-frame auto-run removed → its test failed; drop hook removed → drop test failed. Round 2:
write failure no longer caught → errors test failed; axis fit removed → axis test failed; row wrap disabled → draws test failed
("help"). All restored.

## 7. Screenshots read

`before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_running_1200x800.png` (progress bar, Stop red, settings disabled), `after_folder_dialog_1200x800.png`, `after_*`.

## 9. Persistence, guide, help, docs

Window geometry only on the Qt side (host's in emtk); settings are not persisted by either. Guide/help: the shared
`guide.json` / `help.md`, all targets drawn. Docs: behaviour of the analysis unchanged, none edited.

## 10. Blocked / open

* The burst_analysis Qt workflow shell (`burst_analysis/gui/tool.py:_burst_2cde`) embeds the Qt `BurstTwoCdeTool`; it keeps
  the Qt run until that shell moves to emtk.
* Systemic (known issue "emtk apps opened from ChiSurf's menu are never closed"): `close()` stops the worker only when a host
  calls it.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
