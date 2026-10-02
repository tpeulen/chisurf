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
