# Games launcher (hub) — restyle evidence

Owner feedback 2026-10-01: "the games selection/launcher UI looks bad". Before: `launcher_before_*.png`
(stacked description cards above the game; Tetris "Coming soon", Number Quest on an old surface).
After: `launcher_after_<game>_<size>.png` (re-take with `capture_launcher.py <outdir> after`).

- Sidebar: names only, description in the tooltip; a game without a native version reads "(not available)".
- Header: name, description, "Keys: …" line (`registry.py` `keys`).
- The selected game fills the rest of the window.
- Breakout stays "(not available)": its emtk port is incomplete (audit-all row 87, draw did not terminate).
  The stream's `breakout/app.py` etc. are left uncommitted for whoever ports it; flip `registry.py` `emtk` then.
- Key routing guard: `test/test_game_keys_through_qt_host.py` (presses, releases and focus loss through
  `build_plugin_widget`, also through the launcher).
