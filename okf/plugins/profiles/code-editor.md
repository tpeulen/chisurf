---
type: Plugin Profile
title: Code Editor plugin
description: OKF profile for the shared code/text editor plugin.
resource: chisurf/plugins/core/code_editor/
tags: [plugins, editor, rpc, tooling]
timestamp: '2026-07-05T00:00:00Z'
---

# Identity

| Field | Value |
| --- | --- |
| Plugin id | `code_editor` |
| Display name | `Tools:Miscellaneous:Code Editor` |
| Categories | `Tools`, `Miscellaneous` |
| Version | `2.1.0` |
| State namespace | `code_editor` |
| Local README | Missing |

The manifest describes a shared multi-document editor with project navigation,
symbols, diagnostics, and optional Python LSP integration.

# Architecture Evidence

| Layer | Evidence |
| --- | --- |
| GUI/editor | `window.py`, `editor.py`, `text_editor.py`, `agent_panel.py`. |
| Notebooks | `notebook_editor.py` — `.ipynb` tabs: a one-row toolbar over a stack of `NotebookCell` widgets (code/markdown/raw) run in a single in-process `Shell`. Every surface is sized to its content; the `[n]` prompt lives in a left gutter, not a header row. |
| Panels | Every dock of `CodeEditorWindow` is a `ChisurfDock` (`chisurf/gui/widgets/tools/chisurf_dock.py`): Project, Symbols, Diagnostics, Output, **Kernel**, Agent. The Kernel dock holds the *current* notebook tab's `Chinsole`, which shares that notebook's shell. |
| Tooling | `lsp_client.py`, `ruff_runner.py`, `symbols.py`, `validation.py`. |
| State/docs | `document_store.py`, `context_retriever.py`, `wiki_indexer.py`, `settings.py`. |
| Backend services | `backend/services.py`. |
| Tests | Agent runtime, document store, RPC, ruff runner, services, widgets, `test/test_notebook_editor.py`. |

Manifest RPC methods include document list/get/set/apply-edits plus `ruff_check`
and `ruff_fix`.

# Data And Provenance Impact

This plugin can mutate open documents and optionally run code-assistance or lint-fix
flows. It is not an MMFDB plugin, but it is high-impact because file edits and agent
integration need a clear execution and safety model.

# Verification Surface

Focused test command:

```bash
PYTHONPATH="modules/chinet:modules/imp-tricks/src:." python3 -m pytest chisurf/plugins/core/code_editor/test
```

# Documentation Work

- Add `chisurf/plugins/core/code_editor/README.md`.
- Document document-store semantics, edit application, and ruff fix behavior.
- State whether file writes happen immediately or through editor buffers.
- Document optional LSP/agent features separately from the core editor contract.

# Where to Pick This Up

State as of 2026-08-10 (`notebook_editor.py`):

- **Done (function):** markdown cells render on run (`render_markdown`, Ctrl+Enter / Shift+Enter routed through `run_cell`); double-click-to-edit via a `_MarkdownView` subclass (this Qt build's `QTextBrowser` has no `doubleClicked` signal); cells are added/removed/inserted by **rebuilding** the stack from `self._cells` (`_rebuild_stack`), with a hairline `＋` gap strip between every pair of cells; shell `stdout`/`stderr` are echoed into the attached `Chinsole`, and `run_cell` wraps the run in `pump.begin_cell()`/`end_cell()`.
- **Done (layout, the 2026-08-10 pass).** The measurement is the height of `notebook.container` for the demo notebook the grabber writes: **1091px → 929px**, no scrollbar anywhere it is not needed. What that came from:
  - **Everything is content-sized.** `CellOutput.fit_to_content` lays the document out against the viewport width and sets a fixed height (capped at `MAX_HEIGHT = 360`, above which it scrolls); `NotebookCell._update_height` sizes the source editor to `blockCount * lineSpacing` and turns its vertical scrollbar *off* while it fits; `_update_render_height` does the same for rendered markdown. Before this, a one-line result occupied a fixed ~95px block.
  - **The per-cell header row is gone** — run/delete buttons and the `[n]` prompt sit in a 40px left gutter (`NotebookCell.GUTTER_WIDTH`), which is also what makes markdown text align with code. The gutter stays visible for a *rendered* markdown cell, which previously could not be deleted at all.
  - **One toolbar** (`_build_toolbar`): run all, `restart_kernel`, `clear_all_outputs`, and a terminal toggle that gives the terminal's ~150px back to the cells.
  - **Plot placement**: a figure is scaled to the output panel's width (`CellOutput._image_format`, re-applied on resize by `_relayout_images`), and it is painted in **one** place — `_on_display` routes to the active cell *or* the terminal, never both.
- **Two defects only a screenshot showed:**
  1. A **ghost cell** painting over the top of the notebook: `_clear_cells`/`remove_cell` called `deleteLater()` without `setParent(None)`, and a widget that is out of the layout but still a child keeps painting at its last geometry until the deferred delete runs.
  2. **ANSI escapes printed verbatim** (`[91m--->`) in every traceback — `CellOutput.append_text` now feeds `chisurf.core.console.ansi.AnsiParser` and resolves colours against the `chisurf-light` theme, because the output panel is a light surface while the console is dark.
- **Shell-side fix that belongs to this pass:** `Shell.record_output` skips the execute_result for a matplotlib `Figure`/`Axes` while the inline hook is registered (`_is_pending_inline_figure`). A cell ending in `fig` used to print `<Figure size 420x260 with 1 Axes>` immediately before the inline backend flushed the same figure as an image — two outputs for one plot.
- **The terminal is a window panel, not a pane under the cells (2026-08-10).** `NotebookEditor.take_terminal()` hands the `Chinsole` to the host; `CodeEditorWindow` puts it in a **Kernel** `ChisurfDock` tabbed with Diagnostics and Output, backed by a `QStackedWidget` that follows the active tab (one shell per notebook, so one terminal per notebook). The toolbar's terminal button then emits `terminalVisibilityRequested` instead of resizing a splitter, and a standalone `NotebookEditor` still shows the terminal inline. Fixed on the way: `CodeEditorWindow.__init__` forwarded **all** `**kwargs` to both `QMainWindow` and `CodeEditor`, so `CodeEditorWindow(can_load=False)` raised `TypeError` — editor options are now split out via `_EDITOR_KWARGS`.
- **Grab under the app's real stylesheet or the grab is a lie.** `grab_notebook_editor.py --style` applies `chisurf/gui/styles/<name>.qss` the way `chisurf.gui.setup_style` does, defaulting to `dark.qss`. Under the bare Qt palette the insert `＋` looked like a hairline; under the real theme (`QToolButton { background-color: #694545; border: 1px solid #000 }`) a full-width one between every pair of cells was a **thick maroon separator bar**, and `CellOutput`'s hardcoded `#1a1a1a` text was unreadable on the dark background. Chrome buttons now set `background: transparent` explicitly, the insert button is 26×11 and centred rather than full-width, and the output panel takes `theme_from_settings()`.
- **How to re-measure:** `QT_QPA_PLATFORM=offscreen python -m build_tools.dev_utils.grab_notebook_editor` writes `_window` (the whole window with its docks), `_host`, `_widget`, `_cells`, `_states` (traceback, clamped output, markdown in edit mode, terminal hidden) and `_narrow` PNGs. Read the images; a construction test cannot see a clipped output panel, and neither can a grab taken without the theme.
- **Open front:**
  1. There is no keyboard route to *insert* a cell (Jupyter's `a`/`b`) or to move one up/down; the gap strips and the toolbar are mouse-only.
  2. `restart_kernel` does not re-run `console_init`, so a restarted kernel has `np`/`cs` from `_make_shell`'s `user_ns` but not whatever the app console preloads.
  3. Running a markdown cell intentionally does **not** mark the notebook dirty (source is unchanged); if a later pass wants "ran → dirty", move `_mark_modified()` into that branch of `run_cell` and update the test.
- **Traps:**
  - `QApplication.processEvents()` does not reliably flush `QToolButton.deleteLater()` — tests must use `QApplication.sendPostedEvents(None, QEvent.DeferredDelete)` before counting gap buttons.
  - Stream text ends in `\n`, so the output document always carries a trailing empty block. Its height must be subtracted using `documentLayout().blockBoundingRect(last)`, not `fontMetrics().lineSpacing()` (a block holding an image is not one line tall) — and because that block is still *inside* the document, the panel must be made unscrollable while it fits, or the view slides onto it and clips the last real line.
  - A stylesheet border on a bare `QWidget` is never painted without `setAttribute(Qt.WA_StyledBackground, True)`.
