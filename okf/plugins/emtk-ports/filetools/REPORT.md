# emtk port report — `filetools` (upgrade, audit-all row 46)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `filetools` / `chisurf/plugins/tttr/filetools` |
| Port type | A+B hub: the Qt `FileToolsTool` (NavigationPanelTool over `panels.json`: navigation list, lazily built panels, ◀ Back / ⏩ / Next ▶ stepper, Guide and ? in the toolbar) embedding six Qt tools; the stream's emtk `gui/app.py` hosting the six children's own emtk apps |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-02 |
| Commits | `f29652d4e` baseline; `1b31cbd5c` emtk hub at parity; evidence commit "filetools: evidence and report" |
| Board | `T-20261002-EMTK1C` |

## 1. State at start

`pre-upgrade/git_status_at_start.txt`: modified `manifest.json` (emtk entrypoint); untracked `gui/app.py`,
`gui/translations.json`, `test/test_native.py`. Committed with the app. The children (tttr_splitter, tttr_to_pto,
pto_inspector, tttr_header_edit, tttr_time_windows, bid_to_analysis) were **not touched** — tttr_to_pto and pto_inspector
are off-limits (T-20261001-SWAP4), tttr_time_windows is SWAP4B's. The hub keeps its stream code that reads the splitter's
and time-window tool's state, because those two children have no `export_settings` and are not mine to change.

## 2. Parity checklist (`before_populated.png` (Qt) vs `before_emtk_populated_*` → `after_*`)

| Qt hub | Stream's emtk | Now |
|---|---|---|
| navigation list (6 tools, icons) | selectables; icons' U+FE0F drawn as stray glyphs | same list, captions without the selector |
| lazy panels; a failing tool shows an error panel | lazy children from the manifests' emtk entrypoints; pending/error panel with Retry | same |
| — | filter field (gained) | filter with a hint |
| Guide / ? (toolbar) | Help / Guide; guide without targets | 📖 Guide / ❓ Help; guide on the list entries, description strip and panel box, the converter step waits for a converter to open |
| ◀ Back / ⏩ / Next ▶ | — | not reproduced (deliberate) |
| — | rendered every frame | frames only while the open child or the hub's tour/help needs them |
| drops and keys go to the open panel | same | same |

## 3. Automated evidence

```
after: 40 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/filetools
compare: exit=0   (Qt internals in deliberate.json)
```

## 4. Deliberate differences

`deliberate.json`: the Qt list's row numbers and its "Select … to load." placeholders (the emtk hub builds a child when it
is selected), the status bar's "Ready", "?" → ❓ Help, and the stepper — it runs the open panel's Run action and moves to the
next panel, which suits a pipeline hub (Burst Analysis), not six independent file tools.

## 5. Tests

```
$ python -m pytest chisurf/plugins/tttr/filetools -q -p no:cacheprovider
34 passed
```

`test_emtk_filetools_parity.py` (12): the Qt hub's rows (subprocess) are the emtk hub's tools in order; every panel opens
its child's emtk app without error; a child that cannot open breaks only its panel (pending text, Retry; the rest opens); a
pointer press on a list entry opens that tool; captions carry no U+FE0F; the filter hides what does not match; frames
follow the open child (at rest with pto_inspector, the one child that renders on demand); drops and keys reach the open
child; guide targets drawn, the converter step released only by opening a converter; draws at both sizes; help; Qt-free;
tooltips. The stream's drop test patched `on_paths_dropped` while tttr_to_pto now has the rich `files_dropped` the hub
prefers; it patches that hook now.

Deliberate breakage, two rounds of the same 11 faults (back to continuous, child animation ignored, child frame request
ignored, selection not told to the tour, list rects not remembered, stray glyphs back, filter ignored, drops not routed,
keys not routed, help missing, pending panel without Retry): all caught both times.

## 6. Screenshots read

`before.png`, `before_populated.png` (Qt), `before_emtk_populated_{1200x800,800x600}.png`, `after_{1200x800,800x600}.png`,
`after_populated_{1200x800,800x600}.png`, `after_guide_{1200x800,800x600}.png`.

## 7. Persistence, guide, help, docs

Selected tool, filter and the children's states via `export_settings` (stream code). Help unchanged (shared with the Qt hub);
guide rebuilt. Docs: none changed.

## 8. Blocked / open — for other owners, not fixed here

- Five of the six children render continuously (`continuous=True`), so the hub keeps drawing while one of them is open.
- The TTTR header child's tag table is cramped at 800 px (Value and Idx overlap); 🏷 has no glyph in the canvas font.
- tttr_splitter and tttr_time_windows have no `export_settings`; the hub reads their internals instead.

## 9. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 · [x] D8 · [x] D9 · [x] D10

## 10. Upgrade 2 (2026-10-03, T-20261002-LEFTOVERS): real-input coverage, layout, docs, glyphs

Commit: see the board status line. The earlier pass (sections 0-9) closed the hub at parity but drove it only with a few presses; this pass adds the owner's real-input and layout rules.

**Changes to the app.** The Guide and Help buttons and the list captions no longer carry emoji (`caption()` is the name; the Qt list's pictograms are not drawn): the earlier deliberate difference note about the stray variation selectors is now moot. The tour text and `deliberate.json` are unchanged.

**Reuse.** Hosts the accepted native children from their manifests (no copy); `imaging_emtk.testing.Driver`, the layout checker of `project_browser`, `chisurf/emtk/help_guide.py`. Not forked. The hub keeps its own list/strip/forwarding code (it predates `CalculatorHubApp`; its child-state handling for the splitter and time-window tools has no equivalent there, and those two children have no `export_settings`); folding it onto the shared base is a follow-up (hub family: imaging_tools, lifetime_analysis, calculators already use it).

**Tests.** `pytest chisurf/plugins/tttr/filetools -q`: **50 passed** (34 earlier + 16 new in `test_emtk_filetools_clicks.py`). Control -> test (real pointer/keys/wheel/drop via `Driver`, recording children): list entry click selects, builds and shows the description `test_every_tool_is_listed_and_a_click_on_its_entry...`; filter `test_the_search_field_keeps_the_tools_matching...`; pointer into the child in its coordinates and not from the list `test_the_embedded_tool_gets_pointer_events...`; wheel `test_the_wheel_over_the_tool...`; keys after a press inside, host drop `test_keys_go_to_the_open_tool...`; broken tool / Retry / pending `test_a_tool_that_cannot_open...`, `test_a_tool_without_a_native_declaration...`; Help window and its buttons `test_help_button...`; tour walk with the await and card placement `test_the_tour_is_walked...`, `test_every_guide_target...`; layout of the hub at 1200x800 and 800x600 and every description above the tool `test_the_hub_draws_without_clipped...`, `test_every_description_fits_above_the_tool...`; no emoji `test_the_buttons_and_captions_carry_no_emoji`; small window `test_the_whole_flow_works_in_the_small_window_too`. Guard: a module fixture fails on any change in the real `~/.chisurf` except `logs/`; tests run on temporary settings and HOME. Breakage twice (child pointer coordinates shifted by 3 px; the host-drop route disabled): one failure each, restored.

**Evidence.** `after: 40 controls, 0 without tooltip, qt-free=yes`; `compare` exit 0. Real children: `click_1..9_*.png`, `after_populated_{1200x800,800x600}.png` (read at full size).

**Docs.** `docs/guides/74_intensity_traces_and_file_tools.md` figures regenerated from the emtk hub (`file_tools.png`: Time Windows with an Olympus HT3 queued and its trace previewed; `file_tools_split.png`: Split / Convert with the SPC loaded) and their captions corrected; no reference-page change.

**For the child owners (not touched).** At 800x600 `bid_to_analysis` overlaps text (the *Detectors / Polarization resolved* row and the table header *Output / remote* over *Status*); the splitter child's window titles carry colour pictograms the canvas font draws as boxes.
