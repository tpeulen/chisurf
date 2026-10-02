---
title: emtk ports layout polish
---

# emtk ports: layout polish pass

Owner requirement: "make sure layout of widgets is good". Scope: the traj family (shared
`chisurf/plugins/traj/emtk_tool.py`) and burst_gs, burst_fusion, burst_irf_bg, burst_bva.
Each populated app was rendered at 1200x800 and 800x600 with the plugin's own
`okf/plugins/emtk-ports/<id>/scripts/capture_populated.py` (`<id>/polish_before_*.png` before,
`<id>/polish_after_*.png` after), read at full size, fixed, re-rendered.
Evidence folder ids: potential_energy is `traj_energy_calculator`, fret_trajectory is `traj_fret`.

## Shared fixes

New `chisurf/plugins/emtk_layout.py` (spec helpers and `button_row`) and `test/gui/emtk_layout_checks.py`
(assertions over recorded draws: inside the window, texts apart, rects disjoint, one above another, short fields,
aligned label column, pictogram gap, log capped). The `*.view.json` files are untouched (the Qt AutoForm reads them).

| Defect (all plugins unless noted) | Fix |
| --- | --- |
| Pictogram glyph touching its caption (Guide, Help, Save, Run ...) | `icon_label()`: two spaces after a colour pictogram, one after a plain geometric glyph |
| Number, text and choice fields as wide as the window | `cap_widths()` declares widths (110 / 320 / 170 px) after loading the spec; paths stay full width |
| A grid gives one width to a whole column, so mixed fields were all stretched | `group_by_width()` wraps each run of same-kind fields in an untitled panel |
| Labels of separate grids and the file rows started at different x | `LabelColumn` pads every field caption to the widest and gives hand-drawn rows the same x |
| Save button above the inputs it acts on (align, join, clashes, rotate) | traj shell draws the action as its own section directly above the log |
| Log filling the rest of the window | log child capped to 9 lines (scrolls) |
| Buttons stacked one per line | `button_row()`: one row that wraps at the panel width |
| Stop live while idle | Stop enabled only while a run is in flight |

## Per plugin

### traj_rotate_translate (before `polish_before_*`, after `polish_after_*`)
Defects: save icon touched label; Stride below Save; matrix and stride stretched across the window; log took
most of the window. Fixed: matrix and translation are label/field rows in the shared label column with 110 px
cells; Stride sits with the inputs above Save; log capped. Test: `traj_rotate_translate/test/test_emtk_layout.py`.

### traj_align, traj_remove_clashes, traj_join
Defects: Save button between file rows and options; stretched atom selection / stride / distance / chunk size;
icon touching label; log filling the window. Fixed by the shared shell. Tests: `test_emtk_layout.py` in each.

### traj_save_topology
Defects: icon touching label, log filling the window. Test: `test_emtk_layout.py`.

### traj_convert
Defects: frame range, filename and format stretched; toggles unaligned between panels; log filling the window.
Test: `test_emtk_layout.py`.

### traj_energy (potential_energy, evidence `traj_energy_calculator`)
Defects: full-width Add button and potential choice; stretched cutoffs, weight, stride; "Potential", "Cutoff"
and "Stride" captions in three different columns; log filling the window. Fixed: editor specs get the same
helpers (`TrajToolApp.layout_spec`/`pad_labels`), Add is natural width. Needs `IMP.cgmol` on the path to render.

### fret_trajectory (evidence `traj_fret`)
Defects: stretched stride and parameters; stride label column differed from the file rows; log filling the window.

### burst_gs
Defects: six full-width buttons stacked; "Stop fit" shown live while idle; report text cut off at the bottom
without a scrollbar; stretched numeric fields; at 800x600 the toggles in Extras were clipped at the right edge.
Fixed: data row (Open, Add folder, MMFDB, Clear) and one action row (Fit, Stop, Export, Guide, Help) via
`button_row`; Stop enabled only while a fit runs; report in a scrolling child; capped fields; toggles at the
left edge (`toggles_join=False`). Test: `test/test_emtk_gs_layout.py`.

### burst_fusion
Defects: six stacked buttons plus Stop; Stop live while idle; TTTR file type field stretched with its label on a
separate line; Run row then Guide/Help on separate lines; summary table cut after eight rows. Fixed: source row,
run row (Run, Estimate, Demo, Stop), files row (Load, Save, Export), Guide/Help row; table height 210.
Test: `tests/test_emtk_fusion_layout.py`.

### burst_irf_bg
Defects: nine stacked buttons incl. two full-width ones; Stop live while idle; stretched fields. Fixed: data row
(incl. Channel definition) and one action row. `IrfBackgroundController.draw_inputs` overrides the shared
burst_background one, which is untouched. Test: `test/test_emtk_irf_bg_layout.py`.

### burst_bva
Defects: "Help" orphaned on its own line, a ragged second row, Stop live while idle, icons
touching labels. Fixed: three whole rows (run controls; saves; guide and help). Test: `tests/test_emtk_bva_layout.py`.

## Test changes for layout
Exact-text lookups changed because captions gained two spaces after a pictogram (`💾  Save ...`) and
trailing padding on field captions (parity tests now compare stripped strings).

## emtk-level gaps (not edited, repros)
1. Grid columns share one width per column: `draw_sections([{value, kind:int, width:110}, {value, kind:str}])`
   in one call gives both rows the wider width. Worked around by `group_by_width`.
2. No per-section label-column sharing across separate `draw_sections` calls: draw two lists, labels start at
   different x. Worked around by padding captions with trailing spaces.
3. Emoji glyph advance is wider than `calc_text_size` reports: `im.button("💾 Save")` draws the icon over the
   first character of the caption. Worked around by two spaces.
4. A toggle in a numeric grid is indented by the label column and clips in a 320 px panel
   (`toggle_width + label_w > avail`); no wrap for toggles.
5. `info`/text blocks have no scroll: long `text_wrapped` content past the window bottom is cut.

## Test results
traj: align 44, rotate_translate 46, join 49, remove_clashes 42, convert 56, save_topology 32, traj_energy 3,
potential_energy 67 (run with imp-tricks on PYTHONPATH for `IMP.cgmol`), fret_trajectory 48 passed (xfails unchanged,
new `test_emtk_layout.py` included). burst: burst_gs 76, burst_fusion 103, burst_irf_bg 62, burst_bva 73 passed.
burst_background (not touched, shares nothing changed here) has 1 failing Qt-parity test
(`test_an_estimate_gives_the_qt_widgets_rates_and_the_known_background`, "comparison failed"); not verified against a
pre-change baseline because no stash/checkout is allowed in the shared tree.
traj_tools (a different agent's combined shell, imports the shared `emtk_tool.py`) was not run or edited.
