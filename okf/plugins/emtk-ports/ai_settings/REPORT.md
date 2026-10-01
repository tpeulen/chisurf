# emtk port report — `ai_settings` (settings plugin upgrade)

## 0. Header

| Field | Value |
|---|---|
| Plugin id / path | `ai_settings` / `chisurf/plugins/ai_settings` |
| Port type and why | Upgrade of the earlier stream's emtk app (type B in effect: the Qt tool is AutoForm over the Qt-free `AISettingsModel`; the app was one flat hand-drawn column). New spec + app over the same model. |
| Agent / date | implementing agent (Sonnet), 2026-10-01 |
| Effort spent (hours) | not measured (one session) |
| Commits | `5c305f086` ai_settings: Qt baseline for the emtk upgrade (with `pre-upgrade/`); `a4f1be362` ai_settings: emtk app at parity with the Qt tool; the evidence and report commit (this file) |
| Agent-board entry | `T-20261001-AI` |

## 1. State at start

```
 M chisurf/plugins/ai_settings/__init__.py
 M chisurf/plugins/ai_settings/gui/model.py
 M chisurf/plugins/ai_settings/manifest.json
 M chisurf/plugins/ai_settings/test/test_widgets.py
?? chisurf/plugins/ai_settings/gui/app.py
```

The earlier stream's uncommitted state was the intended starting point (precondition waived for this folder). Preserved before any change in `pre-upgrade/` (`app.py.txt`, diffs of `__init__.py`, `gui/model.py`, `manifest.json`, `test/test_widgets.py`) and committed with the Qt baseline. Their `__init__.py` (lazy `AISettingsWidget` export) and `manifest.json` (`entrypoints.emtk`) changes are committed in `a4f1be362`.

Files I did **not** write but touched: none. Seen but not mine and left alone: `chisurf/core/settings/ai_settings.py` and `settings_chisurf.yaml` carry another stream's uncommitted edits (the ACP provider's `command` / `acp_backend_provider` keys); the committed core would drop those two keys on Save, so that file must land with this plugin.

## 2. What the Qt tool offered — control checklist

| # | Qt control (as shown) | emtk equivalent | Present? |
|---|---|---|---|
| 1 | Title "AI Settings" | window title of the settings window | yes |
| 2 | Sentence "Configure one endpoint per provider, ..." | spec `info` at the top | yes |
| 3 | `?` (help) and Guide | Help and Guide buttons (hand-drawn, tooltips), `help.md`, 6-step `guide.json` | yes (Help is the `?`) |
| 4 | Section API Configuration (open) | `panel` collapsible, `collapsed: false` | yes |
| 5 | Provider combo (6 entries: Mistral (EU), Local, OpenAI, OpenRouter, ACP Agent (stdio), Custom) | `choice` from `available_providers`; `call: set_provider` loads that provider's saved settings, drops fetched models, hides the key | yes |
| 6 | Sign in via browser | `button_row` -> `sign_in` (opens the provider's key page; message when none) | yes |
| 7 | Base URL | `value` str, placeholder, trimmed, blank falls back to the provider default on Save | yes |
| 8 | API Key, masked, placeholder | `value` `kind: password` (masked by emtk), `call: apply_token` (Enter/click-away saves and tests) | yes |
| 9 | Eye toggle (show/hide key) | `toggle` "Show key" swapping to a clear-text field on the same attribute; session only, reset on provider change and close | yes |
| 10 | Section Models (open) | `panel` | yes |
| 11 | Text model editable combo | `value` text field (any id) + `choice` "Fetched text models" (shown after Fetch) | yes, deliberate (see 5) |
| 12 | Image model editable combo | `value` text field + `choice` "Fetched image models" | yes, deliberate |
| 13 | Fetch models | `button_row` -> `fetch_models` on a `SnapshotJob`; greyed while a request runs | yes |
| 14 | Section Generation Settings (folded) | `panel`, `collapsed: true` | yes |
| 15 | Temperature 0..2 step 0.1, 2 decimals | `value` float, `style: spin`, same range/step/decimals | yes |
| 16 | Top-p 0..1 step 0.05 | same | yes |
| 17 | Max tokens 1..1000000 | `value` int spin | yes |
| 18 | Test connection | `button_row` -> `test_connection` on a `SnapshotJob` | yes |
| 19 | Save | `save` -> settings file | yes |
| 20 | Reset (not saved) | `reset` | yes |
| 21 | Result/log area | `info` bound to `status_text` under the buttons (own window) | yes |
| 22 | Tooltips on every control | `description` on every spec section and button, `set_item_tooltip` on Help/Guide | yes (`controls_without_tooltip` = []) |
| 23 | (not in Qt) ACP command and "In-tree server API" | kept from the earlier stream, shown only for the ACP provider | gained |

Screenshots (Qt): `before.png`, `before_populated_expanded_key_hidden.png`, `..._key_shown.png`, `..._models_fetched.png`, `..._connection_ok.png`, `..._connection_failed.png`, `..._validation_empty_url.png`, `..._reset.png`. Current emtk before: `before_emtk_*.png`.

## 3. Files

| File | New / changed | Purpose |
|---|---|---|
| `gui/model.py` | changed | emtk-facing members (`show_key`, `status_text`, pick lists, `enabled`, `busy`), `describe_error`, key redaction in status, epoch guard against stale answers, `BackgroundCall` job target; Qt behaviour unchanged |
| `gui/ai_settings_emtk.view.json` | new | the form (panels `settings`, `actions`) |
| `gui/app.py` | rewritten | `AISettingsApp` (two docked windows, Help/Guide, job polling); factories `make_ai_settings_app` and `make_app` |
| `gui/guide.json` | changed | emtk target `name` beside the Qt `attr`/`action`; texts name the emtk controls |
| `gui/help.md` | changed | Show key, pick lists, Save/Reset |
| `test/test_emtk_ai_settings_parity.py` | new | 40 tests |
| `test/test_widgets.py` | changed | six tests of the removed `AISettingsGui` class dropped (superseded) |
| `manifest.json`, `__init__.py` | changed (earlier stream's, committed) | `entrypoints.emtk` kept next to `entrypoints.gui`; lazy Qt export |

Qt files untouched: `gui/tool.py`, `gui/ai_settings.view.json`. `chisurf/core/plugin/emtk_preview.json` untouched (the reviewer removes `ai_settings`).

## 4. Automated evidence

`compare` (exit 0):

```
{
  "lost": [],
  "untooltipped": []
}
qt-free: True
exit=0          (compare.json: stale_explanations [], explained 15)
```

`after`:

```
after: 24 controls, 0 without tooltip, qt-free=yes -> okf/plugins/emtk-ports/ai_settings
```

`qt_free`: `{'ok': True, 'output': 'QT-FREE OK\n'}`. `controls_without_tooltip`: `[]`.
`grep qtpy|PyQt|PySide|chisurf.gui` over `gui/app.py`, `gui/model.py`: no output.

## 5. Deliberate differences

| Lost/changed item | Why | Where it went |
|---|---|---|
| `1`..`6` | inventory artefacts of the Qt capture (list/spin row numbers) | not controls |
| `?` | Qt title-row help button | Help button (`help`, in "gained") |
| `openai(chatgpt)`, `openrouter`, `local(...)`, `custom(...)`, `acpagent(stdio)` | entries of the Provider drop-down; emtk draws the list only while open | test asserts the emtk list equals the Qt combo's entries; each is selected in `test_changing_the_provider_loads_its_defaults` |
| `temperature`, `top-p`, `maxtokens` | inside Generation Settings, folded at start as in Qt | drawn once opened (`after_populated_expanded_*`, `test_generation_settings_are_folded_until_opened`) |
| Editable combos (Text/Image model) | emtk `choice` is not editable (known gap, no patch) | text field for any id + pick list of fetched ids (current custom id listed first) |
| Eye toggle | Qt tool-button | "Show key" check box; swaps masked and clear-text fields |
| Spin boxes | Qt spin buttons | emtk `style: spin` fields, same ranges |
| Status | Qt coloured HTML label | plain-text result line (the error text is the same; colour is not drawn) |
| Window | one scrolling column | settings window + a "Test / Save / Reset" window with the result below it, so the buttons and the answer are never scrolled out |
| Model changes visible in Qt too | a timeout reads "timed out: the endpoint did not answer within 15 s"; an empty exception message falls back to the class name; the API key is replaced by `[redacted]` in a status text (a server may echo it); a second request while one runs says so | `describe_error`, `_redact` in `gui/model.py` |

## 6. Tests

```
$PY -m pytest chisurf/plugins/ai_settings -q -p no:cacheprovider
81 passed in 28.57s            (15 existing + 66 in test_emtk_ai_settings_parity.py, 40 test functions parametrised)

$PY -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed in 30.88s

$PY -m pytest test/test_plugin_help_guide_seam.py -q -k ai_settings
3 passed, 228 deselected
```

| Required test | Test name(s) | What it asserts |
|---|---|---|
| 1 model reference | `test_provider_options_and_defaults_equal_the_qt_tool`, `test_numeric_ranges_equal_the_qt_spec`, `test_fetch_models_fills_the_pick_lists_through_the_job` | provider list = the Qt combo's, a fresh model = the Qt widget's, ranges/steps = Qt spec, fetched split = `split_models_by_capability` |
| 2 actions and errors | `test_network_failures_give_a_readable_status_and_never_raise` (12 cases: 500, bad JSON, timeout x2, refused, empty message, for both buttons), `test_an_empty_base_url_is_refused_with_the_qt_messages`, `test_save_failure_is_reported_not_raised`, `test_numbers_are_clamped_to_the_qt_ranges_and_typos_are_ignored` | readable status, no exception, no request for an empty URL |
| 3 spec keys | `test_every_spec_key_exists_on_the_model` | attr/call/options_source/source/hidden_when/actions exist |
| 4 draws | `test_the_app_draws_empty_and_populated_at_both_sizes` (1200x800, 800x600, 480x700, text + pixel painter) | labels, result, no key |
| 5 main action | `test_fetch_models_...`, `test_test_connection_ok_and_failed`, `test_the_window_stays_responsive_while_a_request_runs`, `test_an_answer_for_a_provider_that_was_left_is_dropped` | job, responsiveness, stale answer |
| 6 Qt-free | `test_port_is_qt_free` | `qt_free("ai_settings")` ok |
| 7 tooltips | `test_every_control_has_a_tooltip` | inventory + spec walk |
| 8 persistence | `test_save_persists_to_the_temporary_settings_file_and_a_fresh_model_reads_it`, `test_reset_restores_the_defaults_without_saving`, `test_folds_round_trip_through_the_remembered_state` | temp file 0600, fresh model, Reset not saved, folds |
| key | `test_the_key_is_never_drawn_in_clear_by_default`, `test_show_key_toggle_reveals_and_hides_the_key`, `test_the_key_is_not_in_tooltips_status_or_remembered_state` | the fake key is absent from every drawn string unless the toggle is on |

Hermetic: temp `CHISURF_SETTINGS_DIR`/`MMFDB_*`, the module's path function pointed into `tmp_path`, provider key env vars removed, `http.get` and `webbrowser.open` replaced for the whole module; fake key `sk-test-0000` only. `~/.chisurf/ai_api_settings.json` was not modified (mtime 2026-09-28).

Deliberate-breakage check:

| Test | What I broke | Result when broken |
|---|---|---|
| `test_a_provider_change_and_close_hide_the_key_again` | removed `self.show_key = False` from `set_provider` | `assert True is False` (`show_key`) |
| `test_fetch_models_fills_the_pick_lists_through_the_job` | assigned the text list to the image models | `assert [...] == [...]  Left contains one more item: 'pixtral-large-latest'` |

Both restored; plugin folder 81 passed again.

Pre-existing failures I did not cause: `test/test_prd_mentions.py::test_prd_mention_allowlist_has_no_stale_entries` (stale allow-list entries `chisurf/plugins/calculator/kappa2_dist/gui/tool.py`, `chisurf/plugins/tttr/tttr_time_windows/tests/test_construction_smoke.py`; not this plugin).

## 7. Screenshots I looked at

| File | Observation | Fix applied |
|---|---|---|
| `after_1200x800.png`, `after_populated_default_1200x800.png` | three sections, Generation Settings folded, labels beside fields | first draft had stretched full-width buttons (button rows share a grid with a labelled field): each wrapped in its own container, weight 0 |
| `after_800x600.png`, `after_populated_expanded_key_hidden_800x600.png` | nothing clipped | none |
| `after_populated_expanded_key_hidden_1200x800.png`, `..._narrow_480x700.png` | key as stars; fits at 480 wide | none |
| `after_populated_expanded_key_shown_1200x800.png` | `sk-test-0000` in clear, check box ticked | none |
| `after_populated_models_fetched_1200x800.png`, `..._800x600.png` | pick lists appear, "Found 4 text and 3 image models." | none |
| `after_populated_connection_ok_*.png`, `after_populated_connection_failed_1200x800.png` | result line "Connection successful!" / `Connection failed: API error 401: {"message":"Unauthorized"}` | none |
| `after_populated_validation_empty_url_1200x800.png` | "Enter a base URL first." | none |
| `after_populated_acp_1200x800.png` | ACP command and In-tree server API under the key row | moved into their own container (first draft interleaved them with Show key) |
| `after_populated_reset_1200x800.png` | "Fields reset to defaults. Press Save to keep them." | none |

For each: no clipped label, no text past its box, no overlapping windows, no empty panel, no oversized status box. The first capture attempts also showed a stray tooltip from the pointer left on a title bar: the capture script now parks the pointer in blank space. The settings window is mostly blank below the folded content at 1200x800, as the Qt tool's window is.

## 8. Workflow walk-through

1. Open: Mistral (EU), Base URL and models filled, key masked, Generation folded (`make_app()`).
2. Choose a provider (`set_provider`): its saved base URL, models, key.
3. Paste a key, Enter: saved and checked on the job (`apply_token`); stars unless Show key.
4. Fetch models (`fetch_models`, job): pick lists appear; "Found N text and M image models."
5. Pick a model or type an id: saved as you edit.
6. Open Generation Settings: temperature, top-p, max tokens, clamped to the Qt ranges.
7. Test connection (job): "Connection successful!" or a readable failure.
8. Save: "Settings saved." to the settings file; Reset: defaults, not saved.
Data: none needed; the transport is stubbed (`FakeHTTP` in the test file, `capture_*` scripts).

## 9. Persistence, guide, help, docs

* `export_settings()` = `{"folds": {...}}`; the Qt tool remembered only window geometry (`persist_plugin_state`); provider settings and the key live in `ai_api_settings.json` (not a keyring) via the model and are never part of a window's state (asserted).
* Guide: 6 steps (provider, key, Fetch models [await], text model, Test connection [await], Reset), targets by `name` (emtk) with the Qt `attr`/`action` kept; `test_the_tour_waits_for_the_real_buttons` clicks the real buttons and checks the tour does not skip or press for the user.
* Help links: `test_the_help_window_opens_and_its_links_exist` and `test/test_plugin_help_guide_seam.py -k ai_settings` (3 passed).
* Docs: no `docs/guides` page for this plugin exists (docs gap); `gui/help.md` updated.

## 10. Blocked / open questions

none blocking. emtk gaps used around (not patched): `choice` is not editable; `info` cannot colour text; the combo list is not in the closed-state inventory. Open: `chisurf/core/settings/ai_settings.py` (ACP keys) is another stream's uncommitted change this plugin depends on; core capability inference lists `mistral-embed` as an image model (Qt shows the same).

## 11. Self-check against the Definition of Done

- [x] D1 `entrypoints.emtk` -> Qt-free `make_ai_settings_app()` (section 4)
- [x] D2 every Qt control present or explained (sections 2, 5)
- [x] D3 no untooltipped control (section 4)
- [x] D4 screenshots read, nothing clipped (section 7)
- [x] D5 workflow tested (sections 6, 8)
- [x] D6 persistence (section 9)
- [x] D7 guide + help (section 9)
- [ ] D8 docs: no guide page exists (gap listed)
- [x] D9 plugin tests green (section 6)
- [x] D10 report, evidence, board

## 12. Reviewer quick check

As in `_TEMPLATE.md` with `<id>` = `ai_settings`, `<group>/<id>` = `ai_settings`; run with `CHISURF_SETTINGS_DIR`/`MMFDB_SETTINGS_DIR`/`MMFDB_DATABASE_PATH` on a temp folder and the provider key variables unset.
