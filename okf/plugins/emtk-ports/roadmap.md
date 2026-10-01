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
- Shared detector/FCS editor: table layout, range-text parsing, last-used setup (the `setup_channel_definition` blockers).
- Platform: IME/text input, accessibility, HiDPI, native + web hosts parity; docs and an emtk widget gallery with screenshots.

## Track D: retire Qt
Only after A and B: remove Qt tool entries, then host-level Qt (`ControlHost` stays as an optional host). Gate: zero plugins on the preview list and zero Qt-only manifests.
