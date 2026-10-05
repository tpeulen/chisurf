# fps_json_editor — emtk port report

**Accepted** 2026-10-05 for visual and functional parity with the Qt `FpsJsonEditorTool`; `fps_json_editor` left
`chisurf/core/plugin/emtk_preview.json`, and auto mode now opens `gui.app:make_app` (the Qt tool stays reachable with
`gui_mode="qt"`). Board `T-20261005-FPSJSON-ACCEPT`, per [PARITY_AGENT_PROMPT](../PARITY_AGENT_PROMPT.md).

## Port scope

`entrypoints.emtk` = `chisurf.plugins.modelling.fps_json_editor.gui.app:make_app`, which re-exports the Structure Tools
FPS card (`structure_tools/cards/fps_json.py` drawing the Qt-free `fps_model.FpsEditor` from three `view.json` specs with
`data_table` tables). Same card in the Structure Tools hub and as a window of its own; one implementation.

## Defects found and fixed (root causes, with tests)

| Defect | Where | Fix |
|---|---|---|
| At 800x600, with **Simulation** open, the **Advanced** panel and the last fields lay below the window (y 678-717 in a 600 px window). The wheel scrolled the toolbar away but the form never moved, and the scroll range grew without end. | emtk `begin_child` gave a scrolled child a layout `box + scroll_y` tall, so the `expand` table filled the extra room every frame | emtk `052b22a` (+ `tests/test_im_child_scroll_expand.py`) |
| A dock window lost its scroll whenever its content box moved by a pixel (status line, font metrics, toolbar wrap). | emtk `docking._draw_content` keyed the child by its position | emtk `664fff7` (+ `test_a_window_keeps_its_scroll_when_its_box_moves`) |
| Typing JSON into the JSON tab doubled every closer: `{"a": {}}` became `{"a": {}}}""`. | emtk `TextEditor._type` completed pairs but had no type-over | emtk `f08ae47` (+ 4 cases in `test_ui_text_editor.py`) |
| **Add Scoring Group** / FlexFit **+** prompts opened without keyboard focus, so typing went nowhere; Enter did nothing, although the tooltip promised it. Qt's input dialog focuses its field. | `structure_tools/cards/shell.py` `_draw_modal` | focus on open, Enter = OK (shared by every Structure Tools card) |

Found on the way and fixed (not FPS): `structure_tools/test/test_native.py` read `HydroProApp.exe_path`, which moved to
`.model` in c8449abc4 (2 tests red); `test/gui/test_emtk_port_parity.py::test_a_missing_entry_is_a_clear_error` used
`acq` as a Qt-only plugin, but `acq` has been ported. It now uses a synthetic manifest.

## Acceptance gate

1. **Functional**: `fps_json_editor/test` + `structure_tools/test` **99 passed**. Gate + registry/manifest/metadata +
   parity tool: **143 passed**. emtk suite: 2256 passed, 11 skipped; the one red test there, `test_window_appearing_front.py`,
   is another agent's untracked in-progress file and passes on rerun.
2. **Real interaction**: `fps_json_editor/test/test_emtk_real_input.py`, 12 tests. Everything goes through pointer presses
   at drawn rects, typed keys and the file dialog:
   - every position field typed at 1200x800 **and** 800x600, each one scrolled into view first;
   - Qt's ranges clamp typed values: linker −5→0, 500→200; trapped fraction keeps −1 and −0.5 and clamps −3→−1;
     a typo leaves the value unchanged;
   - Delete Row behind its question (Keep, then Remove; the distances that use the position go with it);
   - Save through the dialog, with a round trip;
   - JSON typed into the JSON tab, then **Update**;
   - distance form values and a negative clamp, Add Scoring Group by typing + Enter, Add Row;
   - FlexFit set +/−, residue and bond add/remove;
   - Browse PDB (dialog), **Compute AVs** (a real AV), **Save AV MRC** (dialog, file > 1 kB), 3D View populated;
   - combo picks: Dye model AV3, Dye preset D1-Alexa488, distance type pRDA → **Load DA Distribution...** (dialog;
     `rda`/`prda` loaded);
   - Guide Next/Prev/Close and Help open/close at both sizes.

   `structure_tools/test/test_cards.py` already covered drop, tabs, Add Row, Clear (Keep / Clear all), Guide, Load dialog.
3. **Parity inventory**: `compare.json`: `lost: []`, `untooltipped: []`, Qt-free OK. Qt 56 controls, native 284 (the
   union over the empty state, every populated tab and the opened Details panels, from `scripts/capture_emtk.py`,
   because the Qt inventory walks hidden tabs too). 11 deliberate differences are in `deliberate.json`: combo options that
   a closed combo does not draw, `PDB (File/ID)`→`Structure`/`PDB file or ID`, the two `Remove selected` buttons, the
   per-row `Details...` dialog → inline Dye dimensions / Simulation / Advanced panels, and the JSON caret read-out.
4. **Visual**: PNGs read at 1200x800 and 800x600: empty (`after_*`), every populated tab
   (`after_populated_<tab>_<size>.png`), and `after_populated_positions_details_scrolled_800x600.png` (both folded panels
   opened by clicks, wheeled to the end; the last field at y 577 of 600, scrollbar thumb at the bottom). No clipped rows;
   tables elide long cells (full text in the tooltip).
5. **Deltas documented**: `deliberate.json` plus the one below.

## The 3D View is ChiMOL (2026-10-05, owner: "should display cartoon, fix usage of chimol")

The first acceptance drew the 3D tab with `implot3d` point clouds; Qt embeds the ChiMOL viewer. The card now embeds
ChiMOL through the shared `chisurf/emtk/chimol_view.py` (`ChimolView`: chimol's offscreen renderer in a region of any
emtk window, input read from the emtk context, a fixed aspect when scaled below 760x420). It makes the calls the Qt
editor makes on its viewer:
- every structure a position uses, as cartoon;
- each computed AV as a translucent surface (`add_surface_overlay`, Qt's parameters) with its mean position as a sphere;
- one distance line per restraint, in the first label's colour.

An atom clicked in the viewer becomes the selected position's chain, residue and atom (`FpsEditor.pick_atom`), as in
Qt. Unlike Qt, both structures (protein and DNA) are shown at once: Qt's `set_structure` kept only the last loaded one.
The `implot3d` view is kept only for when ChiMOL cannot start (no WebGPU adapter); it says why.

Tests (`test_emtk_real_input.py`): the scene holds the two structures, 11 AV surfaces, 11 means and 20 lines, and hiding
a position removes its volume; a drag rotates and the wheel zooms (the frame changes); clicking a protein atom attaches
`p51_E194C` to it. Passed 3 of 3 repeats. Evidence: `after_populated_3dview_{1200x800,800x600}.png`, guide figure
`23_fps_editor_3d.png`.

The same `ChimolView` replaces the `implot3d` CA/P trace in the `fret_docking` Structure tab (`cards/docking.py`); its
click suite passes unchanged.

## Docs

Guide 23 (*The FPS JSON Editor*) rewritten for the native window. Its figures (`23_fps_editor.png`, `_distances.png`, new
`_3d.png`) are regenerated from the emtk app by `docs/guides/screenshots/guides_15_25.py _grab_23_fps_editor`. Guide 88
already described the native card. `docs/reference/plugins/fps_json_editor.md` was regenerated (surfaces: emtk; window
is an EMTK app). Only that page was kept: the generator rewrites every page, and the other pages carry other streams'
manifest changes.

## Re-derive

```
O=okf/plugins/emtk-ports/fps_json_editor
python -m test.gui.emtk_port_parity before fps_json_editor --out $O    # Qt, empty state (populated: scripts/capture_qt.py)
python -m test.gui.emtk_port_parity after  fps_json_editor --out $O
python $O/scripts/capture_emtk.py $O                                    # populated tabs + union inventory (overwrites after.json)
python -m test.gui.emtk_port_parity compare fps_json_editor --out $O
```

Trap: run `capture_emtk.py` **after** `after`, because `after` writes the single-frame inventory, which undercounts. A
wheel over the table scrolls the table, not the window, so wheel over the form.

## HEAD caveat (checked in a clean `git archive HEAD` tree, 2026-10-05)

The committed tree passes everything here except three tests, and each depends on another stream's **uncommitted** work:

- `test_guide_and_help_buttons[*]` (2) needs the tour-topmost fix in `chisurf/emtk/help_guide.py` (the tour card gets
  its own window so its Prev / Close answer). That fix was made in the `fret_docking` acceptance (2026-10-04, not
  committed). With that one file added to the clean tree, both pass.
- `structure_tools/test/test_native.py::test_structure_ribbon_entries_resolve_native` needs
  `registry.select_gui_entrypoint`, part of the owner's uncommitted emtk-entrypoint migration (see
  [settings-audit](../settings-audit.md)). This failure predates this change.

Whoever commits those two lands them with their tests; nothing here needs changing.
