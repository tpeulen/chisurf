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
| F12 | Go to the Python definition (needs the Python LSP) | Go to definition |
| Ctrl+Space | Ask for completions (needs the Python LSP) | Complete |
| Alt+Left / Alt+Right | Back / forward through caret positions | Back / Forward |

On a Mac, Option+arrow moves by word, so Back and Forward are Cmd+[ and Cmd+].

## Navigation history

A jump records where the caret was and where it landed: Go to definition, a
find match on another line, an outline or diagnostic entry, and a click ten or
more lines from the previous caret. Back returns to the earlier position and
Forward goes on again; a new jump after going back drops the forward positions.
