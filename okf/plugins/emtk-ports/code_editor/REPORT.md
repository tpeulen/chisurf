# emtk port report — `code_editor`: NOT a swap-candidate (stopped, reclassified as upgrade)

Session EMTK-1, claude implementing agent, 2026-10-01, board `T-20261001-EMTK1`. Audit-all row 2 listed `code_editor` as a
swap-candidate with "Qt side is a single canvas (0 controls)". That measurement was of the wrong window, so the plugin was
stopped after the baseline (PRD-153 "When to stop and ask": effort far beyond a swap, files with another stream's changes).
No plugin code was changed.

## Why the audit was wrong

The earlier migration stream repointed the manifest (uncommitted, `git_status_at_start.txt`):

```
HEAD:      "gui": "chisurf.plugins.core.code_editor.window:CodeEditorWindow"
working:   "gui": "chisurf.plugins.core.code_editor.gui.tool:CodeEditorEmtkTool",   "emtk": "...gui.editor_app:make_editor_app"
```

`CodeEditorEmtkTool` is a Qt `ControlHost` around the same emtk app, so the audit's "before" was the emtk app and the Qt
editor is no longer reachable through the manifest (no Qt fallback). The real Qt baseline (`before.png`, `before.json`) was
captured from `window:CodeEditorWindow` with `scripts/qt_before_entry.py` (the parity tool's `qt_before` with an explicit
entrypoint): 37 controls. Against it the current emtk app (`before_emtk_*.png`, `before_emtk.json`, 85 controls, 0 without
tooltip, Qt-free) loses 29 (`compare_current.json`).

## Gaps (Qt `CodeEditorWindow` → current emtk `CodeEditorApp`)

| Qt control | emtk | Gap |
|---|---|---|
| Toolbar Back / Fwd (navigation history) | none | missing |
| Toolbar Def (go to definition), Hint (signature/hover) | LSP actions exist only inside the completion popup (`definition`, `hover`) | no toolbar/menu route |
| Toolbar Stop (enabled while running) | Run menu Stop, toolbar Stop button | present |
| Run target combo "In ChiSurf" (default) | "Separate process" default | default differs; check targets |
| Lint | Check / Fix (Ruff) | rename, parity |
| ¶ whitespace toggle, line-number toggle | none | missing |
| Settings | Settings | present |
| Folder (open project folder) | Project tree "Parent" only | missing open-folder |
| Edit menu (Find, Completion) | no Edit menu | missing Find |
| Navigate menu | none | missing |
| View menu: dock toggles (Project, Symbols, Output, Diagnostics, Kernel, Agent) | font size only | missing |
| Symbols tab (Symbol / Kind / Line table) | none | missing |
| Kernel tab (notebook kernel terminal, Restart, "Open a notebook to get a kernel terminal.") | Notebook menu Restart shell | partial |
| Agent / AI assistant (Send, "Things to ask", Wiki) | "AI Assistant" tab | to verify |
| Shipped notebooks submenu | none | missing |
| Project tree columns (Name, Size, Kind, Date Modified), context menu Copy Path / Copy File Name | flat list, no columns, no context menu | missing |
| Status: file name, "Ln 1, Col 0", "LSP idle" | "Untitled · Ln 1, Col 1 · UTF-8 · Unsaved" | LSP status missing; column 0 vs 1 |
| Default look | custom `WINDOW_BG` palette, emoji/icon prefixes on buttons | PRD-153 rules 5 and 6 |

## What a real cycle needs

An upgrade cycle (UPGRADE_BRIEF, not a swap): restore `entrypoints.gui` to `window:CodeEditorWindow` (the Qt fallback),
populated Qt captures (a file open, Symbols filled, a run), then port navigation history, Find, the view toggles, Symbols and
Kernel panels, project-tree columns and context menu, LSP status, and remove the custom palette and emoji. Tracked modules
`editor.py`, `agent_panel.py`, `document_store.py`, `rpc_server.py`, `wizard.py`, `__init__.py`, `__main__.py` carry another
stream's uncommitted edits (see `git_status_at_start.txt`); whoever runs the cycle must settle their ownership first.

## Evidence in this folder

`before.png`, `before.json` (Qt `CodeEditorWindow`, empty state), `before_emtk_{1200x800,800x600}.png`, `before_emtk.json`
(current emtk app), `compare_current.json` (29 lost), `scripts/qt_before_entry.py`, `git_status_at_start.txt`.
