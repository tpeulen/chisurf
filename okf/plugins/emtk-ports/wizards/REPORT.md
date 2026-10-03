# emtk port report - `wizards` (audit-all row 55, hub; upgrade to verified parity)

Agent: claude (Sonnet), 2026-10-03, T-20261003-LEFTOVERS2. Type A hub (the Qt `WizardHub`: list left, selected wizard embedded right). Verdict: **accept**.

Commits: baseline + stream state (message "wizards: Qt baseline ..."), `c1eaa778b` app + tests, then the evidence/docs commit.

## 1. State at start
Stream hub: the list on top with emoji glyphs the canvas drew as stray marks, the wizard under it, the Batch analysis entry `emtk=None` (it showed "native wizard surface pending"), no Help/Guide (`before_emtk_populated_*.png`). 2 smoke tests.

## 2. Qt checklist (`before.png`, `before_populated_{1,2}_*.png`)
| # | Qt control | emtk | |
|---|---|---|---|
| 1 | list: Anisotropy, Batch analysis, tooltip = description, first selected | same ids/order/tooltips (asserted vs the Qt widget) | yes (icons dropped) |
| 2 | title + subtitle above the page, "No wizard selected" placeholder | header (label + description, grows with a long text or error), empty-list hint | yes |
| 3 | wizard built lazily, kept | same; failing factory reported in the header, rest works | yes |
| 4 | embedded wizard | the wizards' own native apps (`batch_analysis` now registered) | yes |
| 5 | selection + geometry persisted | selection + the opened wizards' settings | yes |
| 6 | arrow keys on the list | same unless the child takes them | yes |
Gained: Help, Guide (tour with await), pointer/wheel/key/drop forwarding into the child.

## 3. Reuse
Subclass of `calculator/hub/gui/app.py` `CalculatorHubApp` (child lifetime, event forwarding, persistence); `chisurf/emtk/help_guide.py`; `batch_analysis` native app (accepted in this stream); `emtk_test_input.Driver`, `project_browser` layout checker, `emtk_hermetic`. Only the window, catalogue and texts are local.

## 4. Evidence
`after: ... 0 without tooltip, qt-free=yes`; `compare` exit 0 (lost [] after `deliberate.json`: the Qt capture lists every page of the hosted Anisotropy wizard; those controls belong to the child reports). Screenshots `after_populated_{1,2}_*_{1200x800,800x600}.png`, `after_help_*`, `after_tour_*`.

## 5. Layout
Both sizes read; asserted no overlap and nothing outside the window for each wizard. The list is 15 percent of the width (120-190 px) so the child keeps room. Finding (hosted child, not edited): the tr_anisotropy dock title `Anisotropy workflow` needs 133 px and is cut at 800 px even with the narrow list; the test ignores that one string explicitly.

## 6. Tests
`pytest chisurf/plugins/core/wizards`: **25 passed**. Parity vs the live Qt hub: entries/order/tooltips/title/subtitle. Real-input: entry click builds the wizard, arrow keys, pointer and wheel into the embedded Batch wizard in its own coordinates (step list click, file table scroll), a file drop reaches the child, a whole batch run through the hub, Help/Guide windows, tour walked with the awaited list at both sizes (card clear of target), card drag. Breakage twice (child not kept, restore filter inverted): 3 failures, restored. Guard: real `~/.chisurf` unchanged.

## 7. Docs
`docs/guides/78_model_comparison_and_batch.md` (hub figure `wizards_hub.png`), `docs/reference/plugins/wizards.md` (native window), `gui/help.md`, `gui/guide.json` (4 steps, 1 await).

## 8. Findings
`WizardEntry.emtk` for Batch analysis was None: set to the native app. Not touched: `chisurf/emtk/*`, emtk, preview gate.
