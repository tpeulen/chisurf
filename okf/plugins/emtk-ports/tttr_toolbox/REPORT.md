# emtk port report - `tttr_toolbox` (audit-all row 66, upgrade)

Agent: claude (Sonnet), 2026-10-03, board `T-20261003-EMTKUP7`. Verdict: **accept** (hub; sub-tool controls are verified in each child's report). Partial gap: no `before_emtk` capture of the pre-upgrade app was taken (the baseline commit holds its source in `pre-upgrade/`).

Commits: `5564b843f` Qt baseline + earlier stream's manifest/app/translations/test; the app+tests commit; the evidence commit.

## Qt checklist (NavigationPanelTool, `before.png`)
| Qt control | emtk | Test |
|---|---|---|
| Search field | `search` field, filter by name/description/id, "No matching tools." | test_the_search_field_is_typed_into..., test_the_search_matches... |
| nav list of 6 tools + separators | selectable rows (`nav.<role>`), child built on selection and kept alive | test_clicking_each_navigation_row..., test_a_selected_tool_is_kept_alive... |
| Guide, ? | Guide, Help, plus Tool help | test_help_and_tool_help_open_and_close, tour tests |
| Back / Next stepper | Back / Next buttons (grey at the ends) navigate the list | test_back_and_next_walk... |
| ⏩ fast-forward, Next "process files" | deliberate: no hosted tool has a run step, so Next only navigates and fast-forward has nothing to run | - |
| status line "Ready" | status line | test_the_status_line_says_ready |
| panel area, drops | child area with pointer/wheel/key/drop forwarding | test_pointer_wheel_and_keys..., test_files_dropped... |
| error panel | reason + Retry | test_a_tool_that_cannot_open... |

`deliberate.json`: compare exit 0, lost [], stale []. The Qt baseline had the ALEX Creator panel open: its controls are in the hosted child (see the ptu_alex_creator report).

## Bugs found and fixed
* The guide's awaited steps were released at once: the tour selected the panel itself on step change (`_tour_step`), then `select()` notified the await. Now a step with `await` waits for the user; the notification also uses the step's key ("Count Rate" vs the name "Count Rate Analysis" never matched before).
* The tour had no target rectangles (the card could cover the row it names): targets resolve to the navigation rows (`_target_rect`); tests assert the card is clear and draggable.
* Rows drew a pictogram glyph over the name (not in emtk's font): rows are the names; the header window shrank from 95 to 62 px.
* No Back/Next/status (Qt had them): added with six-language texts.

## Tests
`python -m pytest chisurf/plugins/tttr/tttr_toolbox`: 28 passed (22 new real-input, hermetic with real-`~/.chisurf` guard, layout at 1200x800 and 800x600, tooltips, five locales, Qt-free). Breakage twice (Back/Next direction, drop forwarding): 3 failed, restored.

## Reuse / Docs
Reuse: `chisurf.emtk.help_guide`, hosted children via `draw_child`, `emtk_test_input.Driver`; no duplicate. Docs: new `docs/guides/101_tttr_toolbox.md` (+ figure `tttr_toolbox.png`, index), `docs/reference/plugins/tttr_toolbox.md`.
