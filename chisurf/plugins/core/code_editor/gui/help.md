# Code Editor

Edit Python files and notebooks, run them, lint them with Ruff and ask the
assistant. Ctrl is Command on a Mac.

## Keyboard shortcuts

Every shortcut calls what the matching button or menu item calls; tooltips name them.

| Shortcut | Action | Button |
|---|---|---|
| Ctrl+S / Ctrl+Shift+S | Save / Save As | File menu |
| Ctrl+O / Ctrl+N / Ctrl+W | Open / New / Close the document | File menu |
| Ctrl+F | Show the find bar | Edit > Find |
| F3 | Select the next match (wraps) | Next |
| Shift+F3 | Select the previous match (wraps) | Prev |
| Esc | Hide the find bar | Close find |
| F12 | Go to the Python definition (needs the Python LSP) | Def / Navigate > Go to definition |
| Ctrl+Space | Ask for completions (needs the Python LSP) | Hint / Edit > Hint |
| Alt+Left / Alt+Right | Back / forward through caret positions | Back / Fwd |

On a Mac, Option+arrow moves by word, so Back and Forward are Cmd+[ and Cmd+].

## Navigation history

A jump records where the caret was and where it landed: Go to definition, a
find match on another line, an outline or diagnostic entry, and a click ten or
more lines from the previous caret. Back returns to the earlier position and
Forward goes on again; a new jump after going back drops the forward positions.

## Menus and docks

- **File**: New, Open…, **Folder…** (the project folder the Project dock shows), Save, Save As…,
  **Reload** (the file from disk), **Open Notebook…** (the example notebooks ChiSurf ships, by
  group), Close.
- **Edit**: Find, Find next / previous, Hint. The find bar matches case, whole words or a
  **Regex** (Python syntax; the replacement is inserted as typed).
- **Settings**: Settings…, Show Line Numbers, Show Whitespace (also the **¶** toggle on the
  toolbar), Enable Python LSP (Def, Hint and the status line's LSP state need it).
- **Navigate**: Back, Forward, Go to definition.
- **View**: show or hide each dock: Project, Symbols, Diagnostics, Output, Kernel, Agent.
- **Run**: Run Script (Stop while it runs), Lint (Ruff check), Ruff Fix.

The **Project** dock is a table of the project folder (Name, Size, Kind, Date Modified; in a
narrow pane the last three give way to the name, and a row's tooltip lists them): click a file
to open it, expand a folder with its triangle, right-click a row to copy its path or name or
make it the project root. **Symbols** lists the classes, functions and methods of the active
Python document; click one to jump to it. **Kernel** is the terminal of the active notebook's
shell, with **Restart**; it says so when no notebook is open.

The **Agent** (AI Assistant) dock offers **Things to ask** (shipped example prompts that fill
the input) and **Wiki** (browse the LLM Wiki the assistant reads, or populate it from the
codebase).
