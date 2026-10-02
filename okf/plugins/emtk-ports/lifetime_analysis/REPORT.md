# emtk port report - `lifetime_analysis` (upgrade to verified parity, audit-all row 62)

Agent: claude (Sonnet), 2026-10-02, per `UPGRADE_BRIEF.md`, claim `T-20261002-UPG6`. This plugin is a hub: the five hosted tools (IRF estimator, MaxEnt, LLTF, microtime histogram, G-factor) are separate plugins with their own ports and reports; this report covers what the hub owns. Verdict: **accept** with the open items in section 6.
Commits: baseline + earlier-stream files (`pre-upgrade/`), then the upgrade commit and the evidence commit.

## 0. Hermetic first
The plugin's own files write nothing under the user's home (grep before running), but the hosted tools do (MaxEnt reads/writes its settings folder, the Qt shell QSettings). New `test/conftest.py` (autouse) points HOME, the chisurf/MMFDB folders, `chisurf_settings_path` and QSettings at a temp folder; `test_zzz_the_real_chisurf_folder_was_not_touched` compares the real `~/.chisurf` before and after (chisurf's own `logs/` excluded: that logger ignores `CHISURF_SETTINGS_DIR`). Qt baseline captures ran on temp HOME/QSettings.

## 1. Defects found in the earlier-stream hub
* The search box drew no field (a label "Search tools" overlapped the description header), the header was a fixed 70 px (a banner and a description overlapped the tool), the list carried the Qt pictograms as emoji (the font drew garbage glyphs), the experimental warning was a plain line.
* **Guide step 3 targeted `MaxEnt`, which no list entry is called** (`MaxEnt MEM`): that step never highlighted anything. Fixed in `guide.json`; test `every_tour_target_is_drawn` covers all of them.
* The settings of the hosted tools were not saved with the window (only the selection); a hosted tool built later never received pending settings; hosted tools were not given the frame-request callback (a worker thread of a child could not wake the host).
* No Back / Next (the Qt shell has them), no "no match" message, the list too narrow at 800 px.
* Found while listing the hosted tools (not mine, reported): `irf_estimator`, `lltf` and `microtime_histogram` still draw emoji in button labels (`📊  Load from Dataset`, `❓  Help`, `⏹  Stop` ...).

## 2. Qt checklist -> emtk -> test
| Qt control | emtk | Test |
|---|---|---|
| search box | typed field with hint, filters name and purpose | `typing_in_the_search_box...`, `no_match...`, `search_matches_descriptions_too` |
| list of five tools with icons, experimental mark | list `1. ...`, ` *` mark, tooltips | `each_entry_is_clicked...`, `names_descriptions_order_and_maturity_equal_the_qt_shell` |
| experimental banner above the tool | red banner in the header, header grows | `only_the_experimental_tool_carries_the_banner...`, `header_grows...` |
| Guide, ? | Guide, Help | `help_opens...`, `tour_waits...`, `every_tour_target_is_drawn` |
| Back, Next (process-and-advance), fast-forward | Back, Next (selection only; the hosted tools process through their own buttons) | `back_and_next_walk...`, `up_and_down_keys_step...` |
| status bar message | status line under the list | `tool_that_cannot_be_built_is_reported...` |
| hosted panel (lazy, kept alive) | built on first selection, kept | `selected_tool_is_kept_alive...`, `click_in_the_hosted_tool_is_translated...`, `typing_into_a_hosted_field...`, `wheel_over_a_hosted_plot...`, `dropped_file_goes_to_the_selected_tool` |
| window state | selection + every built tool's settings | `settings_round_trip...` |

## 3. Tests
```
$ python -m pytest chisurf/plugins/fluorescence_decay/lifetime_analysis -q -p no:cacheprovider
31 passed in 72.34s     (23 new in test_emtk_lifetime_analysis_parity.py + the existing native test and the 5 Qt shell tests)
```
Deliberate breakage (restored): header height fixed again + children's settings not exported -> 2 failed; Back/Next always forward + search by name only -> 1 failed (`back_and_next...`).
`compare`: exit 0 (lost 0, explained 9, stale 0, untooltipped 0), qt-free yes; `after.json` is the union over the five hosted tools (their own tooltip audits are in their reports; `hosted_tools_without_tooltip` is empty here).

## 4. Layout and evidence
`before_populated_*` (Qt, every panel + search), `before_emtk_*` (earlier app), `after_populated_{g_factor,maxent}_{1200x800,800x600}.png` (hub with the G-factor tool populated and MaxEnt after a run). List 24 % of the width (at least 215 px), no text past the list edge at 800x600 (test), header grows with the banner.

## 5. Reuse and docs
Reuse: `CalculatorHubApp` (the shared hub: child building, event routing, drops, frame requests) and `chisurf.emtk.plugins.load_plugin`; `emtk_layout` not needed (no forms); `chisurf/plugins/emtk_test_input.py`. The hub's own render stays (search, banner, Back/Next differ from the calculator hub).
Docs: `docs/guides/76_decay_analysis_tools.md` (hub figure replaced by the emtk window, text now names Back/Next, search, Help, Guide, `*`, event forwarding), `docs/reference/plugins/lifetime_analysis.md` (native window paragraph, surfaces), `help.md` unchanged (links verified by test), `guide.json` target fixed.

## 6. Open
* Back/Next do not "process the loaded files of the step" as the Qt shell's stepper does (the hosted native tools have no such hook): deliberate, listed in `deliberate.json`.
* The hosted tools' own parity (IRF estimator, LLTF, microtime histogram: emoji labels; MaxEnt and G-factor are done) belongs to their reports.
* `emtk_preview.json` untouched.
