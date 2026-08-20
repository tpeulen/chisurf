# Plugins

What is installed, how it is wired together, and what you can safely switch off.

## The table

One row per plugin ChiSurf discovered, from the shipped tree and from your own
plugin directory. It sorts on any column, searches from the box above it, and
starts with five columns visible; the header's right-click menu adds the rest —
**Id**, **Source**, **Optional**, **Toolbar** and **Window state**.

| Column | Means |
|---|---|
| **Plugin** | The name as it appears in the menus. |
| **Status** | `enabled`, `disabled`, `library`, `cli only`, or a maturity flag (`experimental`, `deprecated`). |
| **Category** | Top-level menu section. |
| **Version** | From the plugin's manifest. |
| **Requires** | Plugins that must load *before* this one. |
| **Required by** | Plugins that break if this one is switched off. |

## Dependencies

A plugin declares what it needs in its `manifest.json`, split by *when* the need
arises:

- **`requires`** — imported when the module is imported. The target must be
  present, and it fixes load order: ChiSurf starts the dependency first.
- **`optional_requires`** — reached only later, from a button press or a
  guarded import. Real coupling, but it constrains nothing.

The split is what keeps the dependency graph solvable. Several plugins reference
each other in opposite directions; because only one direction of each pair is a
hard import, a load order always exists.

The **Dependencies** table shows every edge touching the selected plugin in both
directions, with the version bound (`any` unless the plugin asked for more) and
whether the plugin at the other end is installed. A row reading `missing` is a
dependency that is declared but not present — that plugin will not work.

## Switching plugins off

**Disabled** removes a plugin from the menus without deleting it. Before the
change sticks you are told which *other* plugins hard-require it, because those
are what stop working. Built-in plugins can only be disabled; **Uninstall**
deletes, and works only for plugins in your own directory.

## Installing

**Install…** accepts a plugin folder or a `.zip`. Before anything is copied the
manifest is read and validated, so a malformed plugin is refused with the reason
rather than installed and then silently skipped by discovery. Archives are
checked for entries that would escape the destination.

Plugins install into `~/.chisurf/plugins`, which is already on ChiSurf's plugin
path and needs no administrator rights.

## Window state

Whether a plugin's window reopens at the size and position you left it.
**Window state (all plugins)** sets the policy for everything; a manifest can
declare its own default, which `Plugin default` respects.

## Saving

Edits live in a working copy until **Save**. **Revert** discards them, and
closing the window with unsaved changes asks first. Menu and toolbar changes
appear the next time ChiSurf starts.

## Further reading

- [Plugin architecture](docs/development/plugin_architecture.md) — the manifest
  format, including how to declare `requires` and `optional_requires`.
