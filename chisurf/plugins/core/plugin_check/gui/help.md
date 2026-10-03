# Plugin Check

Find out which plugins fail to start, and why.

## What a check does

A check builds the plugin's native window in a separate process, on throw-away settings, draws it at two window sizes and closes it. pass means that worked without an error; fail means it raised, logged an error or did not finish in time (30 s, 5 s in a safe sweep). A check says the window opens, not that the analysis behind it is right. Nothing a check does reaches your own settings or your home folder.

## The table

One row per discovered plugin, built-in and your own. It sorts on any column (click a header, again to reverse), filters from the box above it and lets the header's right-click menu choose the columns.

- Plugin: the plugin's menu path.
- Status: pass, fail, skipped (blacklisted), Qt only (no native window yet), no GUI, or pending (no sweep has reached it yet).
- Source: built-in, or user for a plugin in your own plugin directory.
- Depends on: plugins that must load first; optional ones are counted.
- Error: the first line of the startup error.

Select a row to read the plugin's details on the right: module, version, dependencies and any dependency problem, the description, and for a failed check the whole error and traceback, which you can select with the mouse and copy.

## The buttons

Test all plugins checks every plugin; Test safe plugins only the first ten, with a short timeout. Stop ends the sweep and terminates the plugin being checked. Refresh rescans the plugin folders and clears the results. Clear blacklist takes every plugin off the blacklist.

Delay between plugins is the pause between two checks (0 to 5 s). Skip blacklisted leaves out the plugins that failed five checks in a row.

## Further reading

- [Plugin Check guide](docs/guides/96_plugin_check.md)
- [Plugin reference: Plugin-Check](docs/reference/plugins/plugin_check.md)
