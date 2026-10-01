# emtk port report — `burst_irf_bg` (upgrade, audit-all row 31)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `burst_irf_bg` / `chisurf/plugins/burst/burst_irf_bg` |
| Port type | B (run port): the Qt `BurstIrfBackgroundTool` draws `BurstIrfBackgroundApp` in a `ControlHost`, computes synchronously and hands the MLE patterns to the burst-analysis shell; the emtk app computes with the stream's `IrfBackgroundController` (a `BackgroundController` subclass) and an `mle_receiver` |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `43336be5a` baseline; `b3652dca8` core fix (background window); `f5cec2e6a` emtk app at parity with the Qt tool; evidence commit "burst_irf_bg: evidence and report". Docs corrected because of the core fixes: `b1b23fd18` (guide 15), `8e272e832` (guide 57) |
| Board | `T-20261001-EMTK1B` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `gui/app.py`, `gui/view_model.py` (cancel check, `tttr_provider`), `manifest.json`;
untracked `gui/controller.py`, `test/test_native.py`. All committed with the app.

## 2. Science: the background rate (core, `b3652dca8`)

On the demo measurement (the same non-burst stream on both detectors) both hosts reported 0.69 / 0.15 kHz; an exact tail
estimate of the same photons is 1.83 / 1.84. `extract_irf_background` fitted the tail above 80 % of the longest gap — a few
mostly empty bins. burst_background's quantile-seeded window moved to core (`background.seed_tail_window`) and serves both tools:
2.04 / 2.05 kHz. Everything downstream of `extract_irf_background` moved with it: the MFD reader's background on guide 57's
simulated folder (no dark counts) went from 0.335 kHz to 0.001 kHz; guide 15's numbers (from the earlier stalled tail fit,
`8e2c1f892`) were re-measured on their BH file against a direct truncated-exponential MLE and corrected, figures regenerated.

## 3. Parity checklist (Qt → emtk; `before_populated.png` vs `before_emtk_populated_*` → `after_*`)

| Qt tool | Stream's emtk | Now |
|---|---|---|
| detectors from the AutoForm detector page | emtk channel editor (inherited) | same |
| files pushed by the shell | own file inputs, MMFDB (inherited, gained) | same; folder drop skips the `.pto` container (burst_background fix) |
| Compute synchronous, error dialog | worker | worker; errors in the window; 10 Hz frames while running |
| Send to MLE → shell's `apply_irf_background_to_mle`; "Compute the IRF and background first."; "Sent IRF + background to MLE for N detector(s)." | `mle_receiver`, same messages | same |
| — | Export MLE patterns (`.npz`, gained) — dialog without the sized window the base now draws in | sized window; refused before a result |
| status line | drawn twice | once |

Shared drawing, fixed: results-table headers overlapped in a narrow pane (fixed widths). Guide: only the plot target existed;
`irf_bg_channels`, `files`, `min_photons`, `irf_bg_run`, `irf_bg_results` are recorded now and the Extract step waits for Compute.

## 4. Automated evidence

```
after: 34 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/burst_irf_bg
compare: exit=0   (lost [] / stale [] / untooltipped [];  the Qt side inventories 0 controls: one canvas)
```

## 5. Deliberate differences

None in `compare.json`. Behaviour: compute on a worker; errors in the window instead of a dialog; the gained inputs/export.

## 6. Tests

```
$ python -m pytest chisurf/plugins/burst/burst_irf_bg -q -p no:cacheprovider
16 passed in 30.10s
```

`test/demo_data.py`: SPC-130, 4096 micro-time channels, scatter IRF at 2.0 ns + flat background between 300 bursts (τ 4 ns).
`test_emtk_irf_bg_parity.py` (11): results equal the Qt tool's (subprocess) and the known IRF peak, equal rates on both
detectors; Send to MLE with and without a receiver, as the Qt tool; pattern export; errors; status once and frames while
computing; every guide target drawn and the Extract await released by a pointer press; folder drop; draws with fitting headers;
Qt-free; tooltips. Core guard: `test/plugins/burst/test_irf_background_window.py`.

Deliberate breakage, round 1: controller status copy restored → status-once test failed; export guard removed → export test
failed. Round 2: results rect not remembered → guide test failed; Compute press not tracked → await test failed. All restored.
Trap met again: the await test first read the button rect from a `RecordingPainter` frame and pressed in pixel frames — draw a
`PixelPainter` frame before reading rects you press.

## 7. Screenshots read

`before_populated.png` (Qt HEAD), `before_emtk_populated_{1200x800,800x600}.png`, `after_populated_{1200x800,800x600}.png`,
`after_*`.

## 9. Persistence, guide, help, docs

Detector setups through the shared setup store; window geometry host's. Guide content unchanged, now walkable. Docs: guides 15
and 57 corrected for the core fixes (above).

## 10. Blocked / open

* The IRF plot shows the floor-subtracted, normalised histogram on a log axis; its near-zero floor bins draw as a solid band
  that hides the second detector (both hosts). Plotting the raw non-burst histogram (where the flat floor *is* the background
  the help describes) would read better — a display choice left for the plugin owner.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10
