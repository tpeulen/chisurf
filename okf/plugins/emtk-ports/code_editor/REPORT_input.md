# code_editor: native editor verified with real input (continuation of REPORT.md)

Agent: claude (Sonnet), 2026-10-03, board `T-20261003-EMTKUP7`. Verdict: **editing behaviour accepted, plugin NOT accepted for the swap**: the control gaps listed in `REPORT.md` (Qt Back/Fwd navigation, Def/Hint, Symbols and Kernel panels, project-tree columns and context menu, LSP status, view toggles, shipped notebooks) are still open (`compare.json`: 29 Qt controls lost, 0 untooltipped, Qt-free yes; no `deliberate.json` is written because nothing was explained away). The emoji-prefixed button captions and the custom dark palette also remain.

Commits: `8c2a38316` the earlier stream's native editor (gui package state, `acp_client.py` and `document_store.py` it needs, the manifest entrypoint; pre-upgrade copies in `pre-upgrade/`), then the code+tests commit and the evidence commit. Not committed, other stream's and not covered by my tests: `editor.py`, `agent_panel.py`, `rpc_server.py`, `wizard.py`, `__init__.py`, `__main__.py`, `test/test_notebook_editor.py`, `test/test_acp_client.py`, `test/test_notebook_shortcuts.py`, `test/test_emtk_editor.py`.

## What was checked (test -> behaviour), `test/test_emtk_editor_input.py`, 52 tests (51 pass, 1 strict xfail)
Hermetic: temp HOME / CHISURF_SETTINGS_DIR / MMFDB_*, temp project folder, in-memory clipboard hook (the system clipboard is never touched), real-`~/.chisurf` snapshot for editor files; only pointer, wheel and key events with modifier bits.

| Area | Tests |
|---|---|
| typing, Enter, Backspace, Delete, arrows, Home/End, Page keys, Ctrl+Home/End, click places caret, status line "Ln, Col, Modified" | test_typed_characters..., test_enter_splits..., test_the_arrow_home_and_end_keys..., test_page_keys..., test_a_click_places_the_caret |
| Tab / bracket closing / indent, deindent, comment toggle on a selection | test_tab_inserts..., test_a_selection_is_indented... |
| selection: Shift+arrows replaced by typing, Shift+End, Ctrl+A, drag, double click | test_shift_arrows..., test_shift_end..., test_a_mouse_drag..., test_double_click_selects_a_word |
| clipboard copy, cut, paste (multi line) | test_copy_cut_and_paste... |
| undo / redo | test_undo_and_redo..., test_undo_reverts... |
| syntax colouring by token kind, plain text, keyword while typing | test_python_is_coloured..., test_a_document_without_a_language..., test_a_keyword_changes_colour... |
| wheel (3 lines per notch, however large the delta), caret scrolls into view | test_the_wheel_scrolls..., test_the_caret_scrolls_into_view |
| files: Open dialog list/pick/cancel, project tree click, edit + Save, Save As typed name, overwrite question, close with unsaved changes (Cancel / Discard), New | test_open_button..., test_the_open_dialog_cancel..., test_a_file_of_the_project_tree..., test_editing_and_saving..., test_save_as..., test_save_over_an_existing_file..., test_closing_a_modified_document..., test_new_and_close... |
| find bar: Ctrl+F, Edit menu, Enter/Next with wrap, Match case, Whole word, All, Not found, Replace, Replace all, undo, Close find, Escape | the find tests |
| shortcuts Ctrl+S / Shift+S / O / N / W; typed letters never trigger them; Alt+Up; a second tab keeps its own text | the shortcut tests |
| focus: typing in the project filter or the find field does not edit the document | test_typing_into_the_project_filter..., test_ctrl_f_opens_the_find_bar... |
| layout at 1200x800, 800x600, 640x480 | test_the_toolbar_wraps... |

## Gaps found and fixed in the app (gui/editor_app.py)
* **No Find** (the Qt editor had one, with case / word / regex toggles) and **no file shortcuts** (Ctrl+S/O/N/W/F did nothing): a Find / Replace bar (Edit → Find…, Ctrl+F) and the shortcuts, queued from the host key event and run inside the editor window as the buttons run them (running `new_document` outside a frame raised "no current im context"). Regex search is not implemented (open).
* One wheel notch scrolled twice or more (emtk keeps an unconsumed wheel across frames): the app clears it at the end of the frame.
* At 800 px the toolbar ran off the window (Fix, Notebook, Settings unreachable) and the status line was clipped: the toolbar wraps, the status path is elided from the left.

## emtk gaps (not touched; repro)
1. `im.text_editor` calls `editor.press(px, py, *box, 0, clicks)` with modifiers 0 and clicks at most 2: a triple click (select line), Shift+click (extend) and Alt+click (add a caret) never reach `TextEditor.press` (strict xfail `test_triple_click_selects_a_line_and_shift_click_extends`; fix: pass `_current_modifiers(io)` and a click count >= 3).
2. An unconsumed `io.mouse_wheel` repeats on every later frame (`app.wheel(x, y, 1.0)` then two `app.draw`: the editor scrolls twice).
3. The clipboard falls back to `pbpaste`/`pbcopy` unless a hook is set: tests must install `emtk.clipboard.set_hook`.

## Evidence
`after_script_{1200x800,800x600}.png`, `after_selection_1200x800.png`, `after_find_1200x800.png` (read at full size; the 800 px toolbar wraps), `after.json`, `compare.json`, `scripts/capture_input_states.py`. Other folder results: the whole `code_editor/test` folder 212 passed / 2 failed before the last layout change; the two failures (`test_acp_client`'s stdio round trip, `test_emtk_editor`'s Qt-free check hitting `AISettingsApp._render`) are another stream's in-flight work and untouched. Breakage twice (Ctrl+S letter compare, find case flag inverted): 3 failed, restored.
