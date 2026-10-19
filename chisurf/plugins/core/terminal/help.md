# Terminal

Terminal panes like tmux: tabs, splits and floating windows. A pane is a real
shell (a pseudo-terminal session) or ChiSurf's built-in Python console.

- **New** (Ctrl+T) opens a pane of the active pane's kind.
- **Python** opens a Python console pane; **Terminal** (Python Terminal plugin) opens a shell pane.
- **Split** divides the active pane side by side or stacked.
- **Close** (Ctrl+W) ends the active pane; Ctrl+Tab cycles panes.

A shell pane needs a POSIX pseudo-terminal; on other platforms only Python panes work.
