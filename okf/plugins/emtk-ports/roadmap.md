# Roadmap: every plugin on emtk, emtk as the GUI toolkit (owner objective, 2026-10-01)

Measured 2026-10-01: 123 plugins declare a GUI, 109 declare `entrypoints.emtk`, 14 are Qt-only. A declared emtk entry is not a swap: the readiness
gate (`chisurf/core/plugin/emtk_preview.json`) keeps the Qt tool the default until the four checks pass (looks good, parity, works, tested).
Preview list now: `setup`, `setup_channel_definition`, `switch_user`.

## Track A: finish the swaps (settings and small plugins)
1. `switch_user` (agent running), then `setup_channel_definition` (blocked on shared-editor gaps, see Track C), then the hub `setup` (adopts accepted panels).
2. Audit the other ~100 declared emtk entries for the same four checks (the ports before the PRD-153 procedure were never checked against Qt). Method: `emtk_port_parity` before/after/compare per id; list in `settings-audit.md` style; swap or upgrade.

## Track B: the 14 Qt-only plugins, by size (non-test Python lines)
`quenching_estimator` 329 (backend broken, fix first), `mfd_prepare` 749, `alex_suite` 4.3k, `updater` 4.7k (cards U1/U2), `fps_json_editor` 4.8k, `burst_analysis` 6.7k,
`burst_mle_analysis` 7.6k, `fret_docking` 7.8k (F1-F3), `burst_h2mm` 7.8k, `burst_ebfret` 8.9k, `acq` 11k, `burst_selection` 13k, `mmfdb_admin` 14.5k.
Cards per `wave3-plan.md`; `mfd_prepare`, `burst_ebfret`, `alex_suite` wait for the other stream's uncommitted edits.

## Track C: emtk as a toolkit (found by the ports; each needs tests in `~/dev/emtk`)
- `begin_child` clip fix (uncommitted in `im_core.py`), Markdown underscores and bold, `choice` editable, `DialogWindow` position.
- `DataTable`: Ctrl/Shift multi-select, column resize/reorder, per-column filters, cell editors.
- Docking: tab-strip overflow; public draw API for shared editors (the boarding wizard calls private `_draw_window`/`_draw_prompt`).
- `ImageCanvas`: more colormaps (cividis, plasma, turbo), PNG export, whole-body region drag in `implot.drag_rect`.
- Shared detector editor: DONE 2026-10-02 (one page, tables, Qt range text, last-used setup; `channel_editor/REPORT.md`). Left for emtk: a `data_table` action column and single-click cell editing (`_ButtonCells` in the editor works around the first), typed `input_int`.
- Platform: IME/text input, accessibility, HiDPI, native + web hosts parity; docs and an emtk widget gallery with screenshots.

## Track D: retire Qt
Only after A and B: remove Qt tool entries, then host-level Qt (`ControlHost` stays as an optional host). Gate: zero plugins on the preview list and zero Qt-only manifests.

## Track E: reuse audit (owner rule, 2026-10-02)
Maximize reuse across all plugins, Qt and emtk. Find duplicated UI: grep for re-implemented detector setup, dataset pickers, file choosers, image
panels, tables and plot panels across `chisurf/plugins/*`; list them with the shared component that should replace each; replace in the owning plugin's
next cycle, or extend the shared component first (detector editor: done 2026-10-02, but `burst_analysis/gui/setup_selection_app.py` still duplicates it; dataset picker buttons id bug).

## Track F: docs catch-up (owner rule, 2026-10-02)
Every accepted emtk port needs its docs updated with the UI: guide text and figures from the emtk app, reference page regenerated. Known gaps from
reports: no guide for `photon_table`, `boarding`, `switch_user`, `calculators`, `fret_calculator`, `kappa2_dist`, `accurate_fret`; guide 37 (`tttr_lut_tools`)
and the lightpath reference page still describe Qt. Method: per plugin, regenerate figures with the capture scripts under `okf/plugins/emtk-ports/<id>/scripts`.
