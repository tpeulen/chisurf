---
type: Concept
title: 'Code Editor: scripts and notebooks inside the analysis session'
description: What the shared Code Editor is for, how it relates to the console and the macro layer, and which editing, linting and navigation features it provides.
tags: [concepts, code, editor]
anchor: concept-code-editor
---

(concept-code-editor)=
# Code Editor: scripts and notebooks inside the analysis session

ChiSurf analyses are scriptable: the headless commands, the Python API and macros drive the same objects as the windows. The
Code Editor (**Tools → System → Code Editor**, `chisurf/plugins/core/code_editor/`) is the place where such scripts are written. It is a shared
multi-document editor, not a fitting tool; it measures nothing.

## What it provides

- Python files and notebooks (`.ipynb`) in tabs, with project navigation and a symbol outline.
- Running a script and showing its output, including HTML output.
- Diagnostics from Ruff, listed and jumpable.
- Optional Python language-server features (go to definition, completion) when a server is available; without one the
  editor still edits and lints.
- Caret navigation history (Back/Forward) that records jumps, not every keystroke.
- A chat panel for the assistant ([AI assistant](../guides/40_ai_assistant.md)).

Shortcuts call what the matching button or menu item calls; Ctrl is Command on a Mac. The table is in the tool's **?**
help.

## Where it fits

A script written here talks to ChiSurf through the same facade as the [console](../guides/59_console.md) and
[notebooks](../guides/64_notebooks.md): use the editor for a file you keep, the console for a one-off command.
