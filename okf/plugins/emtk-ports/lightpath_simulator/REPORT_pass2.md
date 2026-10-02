# emtk upgrade report (pass 2) - lightpath_simulator
Commits `315d7b396` baseline, `7149e6fae` app + tests, `6815abf53` evidence. Tests: 133 passed, 1 xfailed (Enter on an emptied field does not commit: emtk gap). compare exit 0, 169 controls, 0 untooltipped.
Qt baseline: HEAD's `gui/tool.py` offscreen on a generated spectra catalogue (7 probes, `tests/catalog.py`); numbers (signals + three matrices) equal Qt.
Fixed: floating windows over graph/results (now docked), right-click menus never opened, Rename raised, Reset built the Easy graph not the Qt default path, dropped graph files never delivered (`files_dropped`), Delete on links raised, hand-drawn tables -> `data_table`, Stop shown while idle, stretched Easy form inputs, wrapped status line, Foerster node over sample node.
Tests: `test_emtk_lightpath_parity.py`, `test_emtk_lightpath_clicks.py` (control -> test list in the agent hand-back: toolbar, palette, calculate/stop, result tabs, Easy Mode, graph drag/wheel/minimap/delete, drops, right-click menus, guide/help).
Reuse: embeds shared `chisurf.emtk.optical_configuration.OpticalConfigurationWidget` (broken table borders under "Foerster radius", slider fields: shared widget, not edited). Open: docs reference page still says custom Qt widgets; no numbered guide.

## Review (reviewer, 2026-10-02)
Tests re-run by the reviewer with the counts above; populated screenshots read. **Accepted.** Real-input click tests, layout checks at 1200x800 / 800x600 and two deliberate breakages per plugin are the agent's claims, backed by the committed test files named below.
