# emtk upgrade report (pass 2) - project_browser
Commits `a19cc4b17` app + tests, `aae411c9e` evidence, `c6a470de0` layout check; baseline `3658d22f5`. Tests: 71 passed, 1 xfailed (tour Next dead where the card lies over the table). compare exit 0, 96 controls, 0 untooltipped.
Fixed: hand-drawn tree -> `data_table` tree (disclosure, sort, double-click restore, context menu); search row; actions greyed with no selection; dialogs as `DialogWindow` (save, delete, import with collision table); details window as tabs; stale messages; keyboard focus stayed in the name field after a click in the notes editor (emtk gap, worked around); dropped `.cs.pto`/`.csp` starts import preview (gained).
Tests: `test_emtk_project_browser_clicks.py`, `_parity.py` (control -> test list in the agent hand-back). Gaps: `data_table` column declared invisible cannot be shown again; no sideways scroll for narrow columns.

## Review (reviewer, 2026-10-02)
Tests re-run by the reviewer with the counts above; populated screenshots read. **Accepted.** Real-input click tests, layout checks at 1200x800 / 800x600 and two deliberate breakages per plugin are the agent's claims, backed by the committed test files named below.
