# trace_browser, card T5: host adapter for the HMM / time-window / ndX hand-offs

Implementing agent (Sonnet), 2026-10-01; the agent could not write this file, so the reviewer saved the essentials and appended the
review. Closes open item 1 of `REPORT.md`. Commits `7554500f5` (adapter, tests, docs) and `3a6058109` (evidence, log).

## What each hand-off opens

The model records a request; the app delivers it once from the draw thread to `on_request(name, payload)`. `gui/host.py` (Qt allowed,
imported lazily) is that callback in ChiSurf; each window is shown, raised, activated and kept in `host.WINDOWS` until its close event.

| Button / request | Opens | Qt tool reference |
|---|---|---|
| HMM / `open_intensity_trace` | a new `IntensityTrace` window titled `Intensity Trace Analysis - <file>`, file loaded and plotted (6233 bins at 10 ms for `BH_SPC132.spc`), bin window and detector setup passed | `_on_transfer_to_analysis` |
| TW / `open_time_window` | a new `TTTRTimeWindowTool` with the file and the bin window, titled `Time Window BID Generation: <file>` | `_on_transfer_to_tw` |
| NDX / `open_ndxplorer` | ChiSurf's `NdxWindow` on the burst folder the model wrote (`<stem>_TW_10ms`) | `_on_open_in_ndxplorer` |

Failures raise; the app shows "The host could not open <name>: ..." and keeps drawing.

## Wiring (registry.py untouched)

`gui/host_lookup.py` (Qt-free) returns the adapter only if `sys.modules["qtpy.QtWidgets"]` is already loaded and a `QApplication`
exists, without importing Qt; `make_app(on_request=None)` uses it when no explicit `on_request` is given, and the registry's
`factory()` call therefore gets the adapter inside ChiSurf. With Qt blocked, or loaded without an application, the buttons stay greyed
("Needs the ChiSurf main window"). The emtk app and model stay Qt-free.

## Findings about the Qt reference

The Qt HMM handler computed the channels but only logged them (the window gets none, as before); the Qt `widget.py` TW handler drives
widgets of an old wizard that `TTTRTimeWindowTool` no longer has and raises `AttributeError` today: the emtk hand-off works where the
Qt one is broken.

## Tests and evidence

```
185 passed (167 + 18 new)        compare: exit 0, lost [], stale_explanations [], untooltipped [], qt-free
```

18 new tests (real `BH_SPC132.spc` copies, offscreen `QApplication`, hermetic ndX settings): window classes, titles, files, bin windows,
loaded data, kept alive and dropped on close, failing handlers, explicit `on_request` wins, no application -> greyed, two Qt-free
subprocess proofs. Deliberate breakage (window list not kept; wrong TW class) failed 8 and 3 tests. Screenshots: hosted app with the
three buttons enabled, and a grab of each opened window.

## Review (reviewer, 2026-10-01)

Verified, not taken from the hand-over: 185 tests pass; compare exit 0; the real MMFDB file is untouched by the run; no Qt imports in
`gui/app.py`, `gui/model.py` or `gui/host_lookup.py` (only a `sys.modules` lookup). The agent had only tested with the draw loop called
directly, so the reviewer also drove the app **inside a real `ControlHost`** (offscreen) with real mouse presses on the three buttons:
HMM opened an `IntensityTrace`, TW a `TTTRTimeWindowTool`, NDX an `NdxWindow` (3 windows kept, 0 after closing them); the status line
said so each time. **Accepted.** Caveat: not exercised in the full ChiSurf main window; if a hand-off misbehaves there, defer the call
with `QTimer.singleShot(0, ...)`. The agent also reported two throwaway scripts that touched the real `~/.chisurf` session logs and the
sqlite WAL before the tests were hermetic (no database content changed).
