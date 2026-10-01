# emtk port report — `help` (swap-candidate upgrade, audit-all row 3)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `help` / `chisurf/plugins/core/help` |
| Port type | A (adapter/upgrade): the earlier stream's `gui/help_app.py` (emtk docs browser, uncommitted) existed; the work was parity |
| Agent / date | claude implementing agent, session EMTK-1, 2026-10-01 |
| Effort (hours) | ~1.5 |
| Commits | `4a846cfb7` help: Qt baseline and current emtk state; `aa3050fe6` help: emtk app at parity with the Qt tool; evidence commit "help: evidence and report" |
| Board | `T-20261001-EMTK1` |

## 1. State at start

```
 M chisurf/plugins/core/help/__init__.py
 M chisurf/plugins/core/help/api/render.py
 M chisurf/plugins/core/help/api/rst.py
 M chisurf/plugins/core/help/api/toc.py
 M chisurf/plugins/core/help/api/xref.py
 M chisurf/plugins/core/help/gui/__init__.py
 M chisurf/plugins/core/help/gui/tool.py
 M chisurf/plugins/core/help/manifest.json
 M chisurf/plugins/core/help/test/test_doc_registers.py
 M chisurf/plugins/core/help/test/test_manual_snippets.py
?? chisurf/plugins/core/help/gui/help_app.py
?? chisurf/plugins/core/help/test/test_emtk_help.py
```

Copies in `pre-upgrade/`. Committed with the app: `help_app.py`, `test_emtk_help.py`, `gui/__init__.py`, `__init__.py`,
`gui/tool.py` (adds `HelpEmtkTool`, the Qt host of the emtk app, which `chisurf/gui/main.py` and `chisurf/emtk/doc_links.py`
look up), `manifest.json`. **Not committed**: `api/render.py`, `api/rst.py`, `api/toc.py`, `api/xref.py`,
`test/test_doc_registers.py`, `test/test_manual_snippets.py`: the docs rst→md migration stream's edits (the emtk literature-link
test relies on the uncommitted `xref.py` cite resolution).

**Audit correction:** the audit measured the Qt side as "a single canvas" because the stream had rewritten `gui/tool.py` to host
emtk and pointed `entrypoints.gui` at `HelpEmtkTool`. The Qt baseline here is `HelpWidget` **as committed** (HEAD), captured with
`scripts/qt_before_head.py` (loads the HEAD source as a sibling module and runs the parity tool's `qt_before` on it): 30 controls.

## 2. Control checklist (Qt `HelpWidget` → emtk)

| # | Qt control | emtk | Present? |
|---|---|---|---|
| 1 | ⌂ Home, ◀ / ▶ history | Home, Back, Fwd (disabled when empty) | yes |
| 2 | Search box (Ctrl+F) | search above the tree | yes |
| 3 | Online docs (opens `chisurf.core.info.help_url`) | Online docs (was "Docs" opening another URL) | fixed |
| 4 | Videos | Videos | yes |
| 5 | Ask toggle + "Ask the docs" panel, example questions | "Ask Docs" tab with quick questions | yes (deliberate: tab) |
| 6 | ✎ authoring toggle | Authoring tools checkbox | yes |
| 7 | Authoring: Edit, Save, Mark reviewed, AI-reviewed, Show: filter (All/Unreviewed/AI/Reviewed/Stale), Developer docs, review summary | Source/Read, Save, Mark human reviewed, Mark AI reviewed, Clear review, filter combo, Developer docs, summary | Developer docs added; rest present |
| 8 | ✕ close | dock close | yes |
| 9 | Address field ("Address:") | address field with hint + Go + suggestions | yes |
| 10 | Tree of sections, expanded to the open page | tree; opens to the open page once | fixed |
| 11 | Breadcrumb "Concepts — the theory › Core methods" | same breadcrumb above the page | added |
| 12 | Start page: intro, Start here (4 pages), the parts (sections with summaries and first six children) | generated from the TOC, same links | fixed (was a hard-coded welcome page) |
| 13 | Rendered page with math, figures, links | markdown reader, math textures, link chips | yes |
| 14 | Zoom (Ctrl +/−/wheel) | A−, Reset zoom, A+, Ctrl+wheel | yes |

Screenshots: `before.png`, `before_populated.png` (Qt on `docs/concepts/fret.md`), `before_emtk_{home,page}_*.png`.

## 3. Files

| File | Change |
|---|---|
| `gui/help_app.py` | generated start page (`_build_home_content`, `START_HERE`), `breadcrumb()`, tree reveal (`_ancestors_of_current`, reveal once), `set_include_development` + Developer docs checkbox, Online docs → `help_url`, labels without pictograms, `begin_disabled` instead of button recolouring |
| `test/test_emtk_help.py` | stream's file; three assertions updated to the new labels (`Home`/`Back`/..., chips without `↗`) |
| `test/test_emtk_help_parity.py` | new, 10 tests |
| `manifest.json` | stream's `emtk` entry committed; `gui` restored to `tool:HelpWidget` (Qt fallback) |

## 4. Automated evidence

```
$ python -m test.gui.emtk_port_parity after help --out okf/plugins/emtk-ports/help
after: 61 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/help
$ python -m test.gui.emtk_port_parity compare help --out okf/plugins/emtk-ports/help; echo "exit=$?"
exit=0      (lost [] / stale_explanations [] / untooltipped [])
```

`qt_free`: `{'ok': True, 'output': 'QT-FREE OK\n'}`.

## 5. Deliberate differences (`deliberate.json`, 18 entries)

| Item | Why / where |
|---|---|
| `1`–`5` | rows of the hidden popup list of the Qt review-filter combo (inventory artefact) |
| `address`, `show` | Qt labels beside a field/combo; emtk uses hint text and tooltips |
| `ask`, `askthedocs` | the question panel is the "Ask Docs" tab |
| `edit`, `save`, `markreviewed`, `ai-reviewed`, `allpages`, `unreviewed`, `reviewed`, `stale`, `developerdocs` | present in the authoring state / edit mode (`after_authoring_1200x800.png`); the inventory records the default state |

## 6. Tests

```
$ python -m pytest chisurf/plugins/core/help -q -p no:cacheprovider
5 failed, 945 passed, 2 skipped in 103.93s
$ python -m pytest test/core/test_emtk_preview_gate.py test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
20 passed
```

| Required | Test | Asserts |
|---|---|---|
| 1 | `test_start_page_matches_the_qt_start_page`, `test_breadcrumb_matches_the_qt_window` | links/titles of the start page and the breadcrumb equal the Qt HelpWidget's |
| 2 | `test_tree_opens_to_the_open_page`, `test_navigation_actions`, `test_developer_docs_toggle_lists_development_pages` | reveal once, history, bad address never raises, Developer docs rebuilds the tree |
| 3 | (no spec: hand-drawn reader) | — |
| 4 | `test_draws_home_and_page_without_pictograms[1200x800, 800x600]` | home and page drawn, no pictogram in any string |
| 5 | covered by 1/2 (open page → tree + breadcrumb) | |
| 6 | `test_port_is_qt_free` | |
| 7 | `test_every_control_has_a_tooltip` | inventory empty; Online docs, Videos, Home, Back, Fwd present |
| 8 | `test_settings_round_trip` | font size survives export/restore |

Deliberate breakage: reveal disabled → `test_tree_opens_to_the_open_page` failed (`assert 'The orientation factor κ² and what it
costs' in [...]`; the first version of the test passed while broken, because the page title is also the page heading, and was
strengthened to check a sibling); `breadcrumb()` returning `[]` → `test_breadcrumb_matches_the_qt_window` failed. Restored.

Pre-existing failures (docs tree state, not the app): `test_doc_registers.py` (images not registered; stale registers
figures.md, tables.md, code.md), `test_docs_crosslinks.py` (3: unlinked concept pages, `64_notebooks.md`,
`review_mmfdb_implementation.md` → `chisurf/plugins/sample_database`).

## 7. Screenshots read

| File | Observation |
|---|---|
| `after_home_1200x800.png`, `_800x600` | generated start page; links drawn as chips under each item (reader design) |
| `after_page_1200x800.png`, `_800x600` | tree opened to Core methods, breadcrumb, page; **R₀ and R⁶ draw as empty boxes** (font, see 10) |
| `after_authoring_1200x800.png` | filter combo, review colours, Developer docs, sign-off buttons |
| `after_1200x800.png`, `after_800x600.png` | tool's empty state |

No clipped label, no overlap, no empty panel.

## 9. Persistence, guide, help, docs

* `export_settings()` = `{"font_size"}`; the Qt `HelpWidget` persisted nothing (no QSettings, no export/restore; its theme follows the Qt palette). The emtk app keeps more than Qt did.
* Guide/help: the help browser has no `?`/Guide of its own, in Qt either (allow-listed `chisurf/plugins/core/help/gui`): not added.
* Docs: no user-visible workflow change needing a guide edit.

## 10. Blocked / open

* **emtk font gap**: the sans-serif font has no glyphs for Unicode sub/superscript digits (U+2070–U+209F), so `format_inline_math`
  output such as `R₀`, `1/R⁶` draws as boxes. Repro: `im.text("R₀ R⁶")` under `im.push_font("sans-serif")`, screenshot.
* **emtk**: `im.set_next_item_open(True)` is ignored by `tree_node`/`collapsing_header` (it stores `("next_open",)` state that
  `collapsing_header` never reads). Worked around with `collapsing_header(label, True)` + `indent()`. Repro: `set_next_item_open(True);
  assert im.tree_node("x")` fails on the first frame.
* The shared help window (`chisurf/emtk/help_guide.py`) draws markdown `**`/backticks literally (seen in chimol's help).
* Uncommitted `api/*` docs-migration edits (section 1) must land with their stream.

## 11. Self-check

- [x] D1 · [x] D2 · [x] D3 · [x] D4 · [x] D5 · [x] D6 · [x] D7 n/a (none in Qt) · [x] D8 · [ ] D9 (5 pre-existing docs failures) · [x] D10

## 12. Reviewer quick check

```bash
cd ~/dev/chisurf && export QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD:$HOME/dev/emtk"
PY=~/mambaforge/envs/arm64/bin/python
$PY -m test.gui.emtk_port_parity compare help --out okf/plugins/emtk-ports/help; echo "exit=$?"
$PY -m pytest chisurf/plugins/core/help/test/test_emtk_help_parity.py chisurf/plugins/core/help/test/test_emtk_help.py -q -p no:cacheprovider
```
