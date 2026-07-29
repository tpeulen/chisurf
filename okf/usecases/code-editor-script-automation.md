---
type: Reference
title: Use case — scripting an analysis in the Code Editor
description: The workflow that turns a one-off click-through into something repeatable — open the Code Editor, write or open a ChiSurf script, lint it, run it, read its output.
tags: [usecase, scripting, code-editor, automation, ruff, lsp, gui]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: scripting an analysis in the Code Editor

**Goal.** Stop clicking. Every workflow recorded in this folder is a sequence of
GUI actions; the moment a user has to repeat one over a second sample, they want
it as a script. The **Code Editor** (`Tools ▸ Miscellaneous ▸ Code Editor`,
plugin `code_editor`, 📝) is ChiSurf's answer: a tabbed editor with a project
browser, a symbol outline, Ruff diagnostics, an optional Python LSP, an AI agent
side panel, and a **Run** button with three declared execution endpoints —
*Console* (`exec()` in-process, with `cs` in scope), *Process* (a separate
subprocess) and *IPython* (`%run -i` into the ChiSurf console). The first and
third are the interesting ones: they are the only way a script can reach the
**live session** — the loaded datasets, the open fits, the plots.

**Data.** No measurement file needed. Driven against the shipped example
`examples/scripts/protein_unfolding_fret_line.py` (139 lines, carries a
`# !chisurf: process` shebang) plus small probe scripts written to a scratch
directory.

## Steps

1. Open `Tools ▸ Miscellaneous ▸ Code Editor`. The window comes up with an empty
   *Untitled* tab, a **Project** dock on the left (tabbed with **Symbols**), a
   **Diagnostics**/**Output** dock at the bottom, a hidden **Agent** dock on the
   right, and a toolbar carrying *New · Open · Folder · Save · Back · Fwd · Def ·
   Hint · **▶ Run** · ⏹ Stop · endpoint dropdown · Lint · ¶ · Settings · Agent*.
2. Look in the **Project** dock for something to start from.
3. `File ▸ Open` the shipped example
   `examples/scripts/protein_unfolding_fret_line.py`. It opens in a second tab;
   the status bar shows its path, `Ln 1, Col 0` and `LSP idle`.
4. Raise the **Symbols** dock to see the file's outline.
5. Press **Lint** (Ruff) and raise the **Diagnostics** dock to read the findings.
6. Double-click a diagnostic to jump to the offending line.
7. Pick the execution endpoint in the toolbar dropdown — **Console**, so the
   script runs in-process and can touch `cs` (the tooltip states
   *"Console — exec() in-process (cs in scope)"*).
8. Press **▶ Run** and watch the **Output** dock.
9. Write a second script of your own in a new tab, type an edit into an already
   open file, and press **▶ Run** again.
10. Press **⏹ Stop** while a long script is running.
11. Open `Settings ▸ Editor settings` and change the colour scheme / behaviour.
12. Toggle the **Agent** dock to ask the assistant about the open file.

## Expected

- Step 2: the shipped example scripts, or *some* starting point, reachable in
  the project tree.
- Step 3: the file's text fully visible from column 1, syntax-highlighted
  legibly.
- Step 5: a list of Ruff findings; step 6 moves the caret to that line.
- Step 7–8: with **Console** selected, the script executes **inside the ChiSurf
  process** and `cs` resolves to the live session; its `print()` output lands in
  the Output dock.
- Step 9: pressing Run on a buffer with unsaved edits either runs the buffer
  without touching the file, or saves it and says so — not both halves of that
  at once.
- Step 10: the process stops and the Output dock says why.

## Observed (last run: 2026-07-29)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) by instantiating
`CodeEditorWindow` at 1400×900 and exercising the real toolbar/menu actions;
twelve screenshots read and inspected.

**What works.** The window builds in **0.95 s** from a cold `import` and lays out
cleanly — docks, tabs, toolbar, status bar all sensible and uncrowded
(`01_open.png`). The **Process** endpoint is genuinely good: `▶ Running: <path>`,
then live streaming of the subprocess's stdout (first `tick` at t = 1.5 s, one
per 0.5 s thereafter — not a batch dump at the end), merged stderr, so a
`ValueError` arrives as a full traceback, and a closing
`⏹ Process finished with exit code 1`. **⏹ Stop** kills a running script and
reports it (`exit code 9`). **Ruff** works and is fast: 5 findings on the shipped
example (`I001`, `F401`, 3 × `E702`), rendered with path:line:column, and the
status bar summarises `Ruff: 5 issue(s)` — green *"Ruff: no issues found"* when
clean, red *"Ruff failed: …"* when not. The **Symbols** outline resolves
`fit_decay | 4` from a def. The **Agent** dock is well laid out (provider combo,
mode combo, *Things to ask*, *Restart*, *Wiki*, Send/Cancel). The
**Editor Settings** dialog is tidy and readable (`16_settings.png`). The
shebang parser (`# !chisurf: console`) does move the endpoint combo on open.

**What does not.**

*The endpoint dropdown does nothing.* Selecting **Console** and pressing Run
executes the script in a **subprocess** anyway: a different pid from the GUI
(15952 vs 15849), `cs` not in scope, and the process-path header
`▶ Running:` rather than the console path's `▶ Running (console):`. The
`# !chisurf: console` shebang moves the combo and changes nothing else. The
setting is silently discarded on the way to disk — `run_endpoint` is absent from
both `EDITOR_SETTINGS_KEYS` and `default_editor_settings()`, so
`_set_run_endpoint`'s `save_editor_settings` filters it out and `run_macro`'s
`settings.get("run_endpoint", "process")` always falls through to the default.
The consequence is the whole point of the workflow: **a script cannot reach the
live ChiSurf session from the GUI.** Neither the in-process `exec()` (which the
tooltip advertises as having `cs` in scope) nor the `%run -i` into the ChiSurf
IPython console is reachable; every script gets a cold interpreter that has to
re-`import chisurf` and cannot see a single loaded dataset or open fit.
**RF-1008.**

*Every file opens with its first characters hidden.* The line-number gutter and
the text viewport overlap. Measured on open: gutter widget 26 px vs viewport
`x = 19 px` for a 13-block file, and 34 px vs 19 px for a 151-block one — i.e.
one character swallowed at ≥ 10 lines, two at ≥ 100. On the shipped example this
renders `import pathlib` as `mport pathlib`, `TAU_D0` as `AU_D0`,
`FRACS = np.linspace(...)` as `RACS = …` and `from chisurf.core.data import
DataCurve` as `rom chisurf…` (`02_opened_example.png`, `10_300lines_crop.png`).
Pressing Return anywhere — any line-count change — snaps the viewport to 35 px
and the text becomes whole, so the margin is simply never re-applied after the
document is loaded. **RF-1009.**

*The default colour scheme is unreadable.* The token palette is hard-coded VS
Code **Dark+** (`#B5CEA8` numbers, `#DCDCAA` functions, `#4EC9B0` classes,
`#CE9178` strings, `#6A9955` comments, `#569CD6` keywords) while the shipped
`ChiSurf` scheme paints them on a light-grey `#cfcfcf` paper. Contrast ratios:
numbers **1.09:1**, functions **1.10:1**, classes 1.31:1, strings 1.70:1,
keywords 1.89:1, comments 2.14:1 — against 4.5:1 for readable body text and 3:1
for the most lenient non-text threshold. `y = 123` renders as `y = ` plus a
ghost; `np.linspace(0, 1, 21)` shows as `np.linspace( ,  ,   )` at 100 % zoom
(`05_crop.png`). Switching the scheme to **Dark** makes everything legible
(`12_dark.png`), which is the diagnosis: the palette and the paper come from
different themes. **RF-1010.**

*Run writes over the file on disk while still claiming the buffer is unsaved.*
Typing `# typed by the user` into an opened file and pressing **▶ Run** — no
Save, no prompt — leaves the disk file changed from `print('ORIGINAL')` to
`# typed by the user\nprint('ORIGINAL')`, while the tab still reads `ow.py *`
and the status bar still says `Modified`. So a user who tweaks a shipped example
to try something has already modified it in the repository, and a user who then
closes the tab and answers *Discard* believes the edit is gone when it is on
disk. **RF-1011.**

*Numbers are re-coloured inside comments and strings.* The number rule is added
last and `highlightBlock` applies rules in order, so `# donor lifetime 0.91 ns`
comes out comment-green with a number-green `0.91` embedded in it, and
`"abc 42"` comes out string-orange with a number-green `42`. The pattern is also
`\b[0-9]+\b`, so `4.0` colours the `4` and leaves `.0` at default. **RF-1012.**

*Two colour settings in the dialog are inert.* The gutter is painted with a
hard-coded `QColor('green')`, so **Margin color** and **Marker color** — offered
in the Editor Settings dialog, persisted to the user YAML, and part of every
colour scheme — change nothing. The gutter is the same saturated green under the
`ChiSurf` scheme and under `Dark` (`01_open.png` vs `12_dark.png`), where it is
the brightest thing in an otherwise dark window. **RF-1013.**

*The Diagnostics list is not clickable.* Each item stores its diagnostic dict —
`{'code': 'E702', 'line': 26, 'column': 3, …}` — in `Qt.UserRole`, but nothing is
connected to `itemActivated`/`itemDoubleClicked`. Activating the item leaves the
caret on line 1. With the full absolute path printed on every row, the list is
read-only text. **RF-1014.**

*The project tree is empty on first open.* The default root resolves to
`<repo>/scripts`, which does not exist in the tree, so it falls back to
`~/.chisurf/scripts` — which the call **creates**, empty, ignoring
`CHISURF_SETTINGS_DIR`. A new user therefore opens the Code Editor to a **Project
dock with zero rows** (`01_open.png`), while the shipped example scripts sit in
`examples/scripts/` where nothing points at them. **RF-1015.**

*Timings.* Window construction 0.95 s; opening a 139-line file ≈ 0.2 s; Ruff on
it ≈ 1 s; subprocess start-up ≈ 1.0–1.4 s before the first line of script output.

## UX / UI suggestions

- **Say what the endpoint means at the point of use.** Even once the dropdown
  works, "Console / Process / IPython" is jargon for a fluorescence
  spectroscopist. The two things a user actually chooses between are *"run
  inside ChiSurf (can see my data and fits)"* and *"run in a clean interpreter"*.
  Label them that way and put the current choice in the Output header
  (`▶ Running in ChiSurf (console): …`) so the Output pane records which one
  produced the result.
- **Make the Project dock useful on first open.** Point it at
  `examples/scripts/` when the user has no scripts directory yet, or show a
  one-line placeholder (*"No project folder — use 📁 Folder, or open an example
  from examples/scripts/"*) instead of an empty tree with a lone *Name* header.
- **Give Def / Hint a visible answer.** With `python-lsp-server` absent (it is a
  declared plugin dependency but is not in this machine's environment) pressing
  **Def** or **Hint** does nothing at all — the only trace is a status-bar label
  changing from `LSP idle` to `LSP stopped`, which is 90 px wide at the far right
  of a 1400 px window. Show it where the user is looking, and say what is
  missing and how to install it.
- **Shorten the diagnostics rows.** Every row repeats the full absolute path,
  eating ~55 % of the width for a file the user already has open. Show
  `line:col code — message` and reserve the path for cross-file diagnostics.
- **Highlight docstrings.** The triple-quoted module docstring of the shipped
  example is rendered in plain default black — the highlighter has no multi-line
  string rule — so the largest block in the file is the one block with no
  colour at all.
- **Do not call a user-requested Stop an error.** After **⏹ Stop** the Output
  reads `⏹ Process finished with exit code 9`; say `⏹ Stopped by the user`.
- **`print` is not a keyword.** It sits in the Python-2-era keyword list, so
  `print(...)` is drawn bold-blue like `import` and `return`.
- **The Apply button reads `Apply _Save`.** The ampersand mnemonic in
  *"Apply & Save"* renders literally as an underscore in the settings dialog.

## Bugs filed

- RF-1008 — the Run-endpoint dropdown is inert; Console/IPython unreachable, so
  a script can never touch the live session.
- RF-1009 — the first 1–2 characters of every line are hidden under the
  line-number gutter until the line count changes.
- RF-1010 — the shipped `ChiSurf` colour scheme paints a dark-theme token
  palette on a light paper (1.09–2.14:1 contrast).
- RF-1011 — **Run** overwrites the file on disk without a Save while the buffer
  still shows *Modified*.
- RF-1012 — digits inside comments and strings are re-coloured as numbers; the
  number pattern misses float fractions and exponents.
- RF-1013 — the gutter background is hard-coded green; *Margin color* and
  *Marker color* do nothing.
- RF-1014 — the Diagnostics list carries line/column but is not activatable.
- RF-1015 — the project tree opens empty; the default root does not exist and
  the shipped example scripts are unreachable from it.
