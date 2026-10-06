# emtk port report — `burst_analysis` (DONE 2026-10-06)

Burst Analysis opens as a native emtk hub: `chisurf/plugins/burst/burst_analysis/gui/native.py`
on `chisurf/emtk/tool_hub.py` (`ToolHubApp`), manifest `entrypoints.emtk`. All 17 steps are
native apps and open and draw in a Qt-blocked process. With it, no ribbon button opens Qt.
(Written by the coordinator from the porting agent's hand-back; subagents may not write
report files.)

## Commits

- 21920bc3a — snapshot of the uncommitted 2026-10-03 files (`pre-upgrade/`).
- 966163d53 — setup step (shared `ChannelDefinitionWidget`) and Qt-free data step (BA4, BA3);
  MMFDB registration is one function, `import_raw_file`.
- ee14af4bd, 9c39340c4 — Burst Selection: Qt-free `diagnostics.py`, then the Qt-free model (BS0).
- ddd07e123 — native Burst Selection app (BS1–BS6; its manifest has `entrypoints.emtk`).
- a5981e47c — H2MM-state split in the Qt-free MLE engine (`tests/test_engine_state_split.py`).
- 77337cfd6 — the native hub (BA0–BA2): `workflow_context.py` (Qt-free context and "which
  bursts do the later steps read", used by the Qt shell too), BVA channel rule in
  `BvaViewModel`, manifest entry, `test_hub_membership.py` reads the native `STEPS`.
- f6a98f22d — 11 hub tests; 2CDE gets the setup's channels; shared `fret_detectors` in
  `core/fluorescence/burst/table.py`.
- 77ffe8b95 — two failures red on the parent too, fixed (QApplication garbage-collected in the
  burst_selection smoke test; MLE histogram series in worker order).
- 6eca22141 — burst FCS and GS get the setup's pairs/channels; Accurate FRET maps photon counts
  (`Number of Photons (<detector>)`; it used `First Photon (green)` for I_DD, in Qt too).
- 351987e61 — guide.json (Next / >>), help.md, guide 27 rewritten with a figure from the hub
  (10 files, 1130 bursts), plugin reference page; PRD mentions out of four burst files.
- d81e0e53d — OKF evidence (`after_*.png`, `after.json`, `compare.json`, `deliberate.json`),
  burst-survey resume section, ribbon item 1 closed, known issues, log, board.

## Walk-through (asserted by a test)

Copies of `bh_spc132_sm_dna/m000.spc,m001.spc`, setup `probe`: pick the setup, Next, drop the
files, Next twice → Burst Selection finds **198 bursts**, the Qt tool's number; every later
step receives its input.

## Parity

`compare`: exit 0, nothing lost, every control tooltipped, Qt-free. Deliberate differences
(`deliberate.json`): 14 "lost" items are data of the Qt before-image (the `probe` setup's
rows; present in `after_setup_1200x800.png`); the rail cannot collapse and clips
"7. Burst segmentation (H2MM)" at 800 px; the `[opt]` badge is gone (the name says
optional); labels `Next`, `>>`, `Help` + `Tool help`; the status bar shows a live summary;
the header shows the rail badge; the setup is no longer published to the RPC store; the MLE
step's own file-drop docks stay visible.

## Screenshots read

Empty hub at 1200×800 and 800×600; setup, data, selection at both sizes; fusion, BVA, 2CDE,
both MLE steps, H2MM, browser, accurate FRET, burst FCS, GS, background, IRF & background;
MLE at 800×600; the guide-27 figure. Fixes they led to: status line after the drop, Next's
tooltip over the plots, status text under Back/Next at 800 px, 2CDE/FCS/GS on default
channels, Accurate FRET column choice.

## Tests

burst_analysis 49, alex_suite 46, burst_bva 73, burst_2cde 32 (+1 skip), accurate_fret 58,
burst_selection 275 (+1 xfail), burst_mle_analysis 109; hub_membership 7, ribbon_layout 12,
plugin_menu_tabs 4, plugin_registry 23, ribbon_layout_build 1, emtk_preview_gate 7,
emtk_port_parity 13. Red at HEAD too (other lanes' files): burst_gs clicks (3),
burst_fcs_correlator clicks (2), test_guided_tour (cookiecutter help link).

## Where to pick this up

1. **ALEX Suite shell (AS4)** still subclasses the Qt shell; build `AlexHubApp` on the hub with
   ALEX's own steps, then point its `test_hub_membership.py` extractor at it.
2. Two `ToolHubApp` limits (fixed rail, badge in the header) need an additive change in
   `tool_hub.py` (owned by the emtk-port session).
3. The five red burst_gs / burst_fcs_correlator click tests.
4. Retire the Qt shells (`gui/tool.py`, `gui/app.py`, the Qt Burst Selection and its three
   recorded defects) once AS4 lands.
