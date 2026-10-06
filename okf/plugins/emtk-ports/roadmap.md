# Roadmap: every plugin on emtk, emtk as the GUI toolkit (owner objective, 2026-10-01)

Measured 2026-10-01: 123 plugins declare a GUI, 109 declare `entrypoints.emtk`, 14 are Qt-only. A declared emtk entry is not a swap: the readiness
gate (`chisurf/core/plugin/emtk_preview.json`) keeps the Qt tool the default until the four checks pass (looks good, parity, works, tested).
Preview list now (2026-10-05): `code_editor` only.

## Where to pick this up (2026-10-05)

0. **Ribbon entries that still open Qt** (measured 2026-10-05 with `select_gui_entrypoint(manifest, "auto")` over every
   manifest with a `gui` / `emtk` / `script` entry). The preview gate and `audit_emtk_overflow` only see manifests
   that declare *both* `gui` and `emtk`, so **script-entry plugins that build a Qt window were invisible**. That is how
   "FCS opens the Qt tool" went unnoticed. FCS (`fcs_toolbox` + `fcs_correlator`) is done
   ([report](fcs_toolbox/REPORT.md)). Still Qt, by size:
   - `gui` only: `burst_analysis`, `burst_selection`, `mmfdb_admin`, `quenching_estimator`, and `code_editor` (gated);
   - `script`, opening Qt: `screenshot`; `tttr_correlate` and `tttr_histogram` are menu-hidden (and so is
     `quenching_estimator`, replaced by the Structure Tools QuEst card). `intensity_trace` done 2026-10-05
     ([report](intensity_trace/REPORT.md)). `burst_analysis` is blocked (burst-survey B2/B3: other streams' uncommitted
     work and the owner's yes needed).
   Re-measure: the loop in this file's history, or `select_gui_entrypoint` over all manifests, flagging `script`
   entries whose file calls `.show()`. Template for a rail tool: `chisurf/emtk/tool_hub.py` + a Qt-free workflow
   (`fcs_correlator/workflow.py`).

1. **`code_editor`**, the last id on the preview list. `code_editor/REPORT.md` + `REPORT_input.md`: 29 Qt controls
   lost (Back/Fwd, Def/Hint, Symbols and Kernel panels, project-tree columns and context menu, LSP status, view toggles,
   shipped notebooks). Re-measure with `emtk_port_parity before|after|compare` against `window:CodeEditorWindow`
   (`code_editor/scripts/qt_before_entry.py`): the manifest's `gui` is a Qt host around the emtk app, so a plain
   `before` measures emtk against emtk. Several modules carry another stream's edits; settle ownership first.
2. **ChiMOL in emtk cards: done 2026-10-05.** `chisurf/emtk/chimol_view.py` is the shared view; the FPS 3D View and the
   `fret_docking` Structure tab use it. Next users: any card still drawing a structure with `implot3d` (grep
   `implot3d` under `chisurf/plugins/modelling`). Open: `chisurf/plugins/chimol/app.py` (the whole-window host) still
   embeds chimol in its own code, and still stretches the picture below 760x420; port it onto `ChimolView`.
3. **Re-audit every accepted port for the scroll defect class.** Until emtk `052b22a`, any dock window with an `expand`
   table (or plot) above more content had an unreachable bottom and an unbounded scroll. The single-frame
   `audit_emtk_overflow` cannot see it: it shows only with populated data, open folded panels, and the window wheeled
   to its end. Method: `fps_json_editor/scripts/capture_emtk.py` (open the panels, wheel *over the form, not the
   table*, then assert the last field's rect is inside the window).
3b. **FPS editor interactivity: done 2026-10-06** ([report](fps_json_editor/REPORT.md), "Placing dyes
   interactively"). Open: the white attachment marker sits inside its own (opaque-ish) volume and is barely seen --
   chimol has no "draw on top" sphere; the overlay labels of `add_sphere` do not render in the native host. Both
   are chimol work. The other `ChimolView` user (`fret_docking` Structure tab) has none of the new interactions yet.
   **Pushed 2026-10-06**: emtk `main` at `d94a5a9`, chimol `development` at `5df67ff`. **`pixi.lock` still pins emtk
   `42859fc`** (no `tab_rect`, `DockWindow.tooltip`, `TableColumn.min_width`): re-lock once the other stream's large
   uncommitted `pixi.lock` / `pixi.toml` edits are settled; until then a pixi env built from the lock breaks the FPS
   editor. chisurf commits are local (project rule: never push).
4. **Fixed views where Qt had movable docks** (owner, 2026-10-05: "in the old one, i could move the docks around, in
   the current all is fixed"). FPS JSON editor done: one dock window per view under a fixed toolbar strip
   (`CardShell.toolbar_height` / `draw_toolbar`), [report](fps_json_editor/REPORT.md). Same defect, not yet ported:
   the `fret_docking` card's Results / Score / Structure tabs and the QuEst card's Quenching Chemistry / Project JSON
   tabs (`structure_tools/cards/docking.py`, `quest.py`). Find more: grep card and app code for a hand-drawn tab strip
   (`_tab_strip`, `begin_tab_bar` inside a single dock window) where the Qt tool used `QDockWidget`s. Pattern:
   `FpsJsonCard.build_docks` + the `tab` property + `tab_<title>` rects from `DockManager.tab_rect`; keep a test that
   drags a tab with real input (`_drag_tab_to_right_pad` in `fps_json_editor/test/test_emtk_real_input.py`). TTTR Tools
   moved onto `tool_hub.py` in another session (fcb2f06b3).
   **Needs emtk `bf6b5fe`** (`DockManager.tab_rect`, `DockWindow.tooltip`): local, unpushed; `pixi.lock` still pins
   `42859fc`, so a pixi env built from the lock fails with `AttributeError: tab_rect`. Push emtk and re-lock.
5. **ChiSurf Settings rows** (owner, 2026-10-05: label above field "wastes vertical space"): now key | field on one
   row, the full name in the tooltip. About 12 → 25 settings visible at 1200x800, 16 at 800x600
   (`setup/settings-rows/before_*.png` / `after_*.png`, `capture.py`). **Uncommitted**: it sits on the uncommitted
   scroll / typed-number work in `setup/gui/app.py` and the untracked `test_emtk_setup_settings_scroll.py` (owner
   unclear); commit together once that is settled. Setup suite: 384 passed with it.
6. Tracks C-F below are unchanged.

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
