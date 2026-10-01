# Models

Which fitting models the model drop-down offers, and how each one's parameter
panel is described.

## The table

One row per model **class** registered by an experiment. Click a column header to
sort (again to reverse), type in the filter box above the rows to keep the rows
that contain the text in any column, and right click the header to choose which
columns are shown.

| Column | Means |
|---|---|
| **Model** | The name shown in the model drop-down. |
| **Experiment** | Which experiment offers it — TCSPC, FCS, PDA and so on. |
| **Status** | `enabled` or `disabled`. |
| **Spec** | `ok` when the model declares a view spec that resolves, `missing file` when it declares one that is not there, `none` when it declares none. |
| **Parameter UI** | `spec-driven` when the parameter panel is built from that spec, `Qt class` when the model still carries its own widget code. |
| **Shared** | Other experiments offering a model of the same name. |

Under the table, **Show disabled models** hides or shows the switched-off rows,
and the status line counts the models, the disabled ones and the disabled names
that match no model. **Copy** puts the rows the table shows (with their headers)
on the clipboard and **Export CSV** writes them to a file; both follow the filter,
the sort and the chosen columns.

## Disabling a model

**Disabled** keeps a model out of the drop-down offered for a dataset. Nothing
is removed and no code changes; the model can still be built by a macro or
restored from a project.

**Disabling matches on the display name.** That matters when the *Shared* column
is not empty: `Parse-Model` exists under TCSPC, FCS and PCF, so switching one
off switches off all three. The details pane says so for any model in that
position.

## Stale entries

A disabled entry naming a model that no longer exists sits in your settings
doing nothing, and there was previously no way to see it — the shipped defaults
themselves carried two such names for years. The status line counts them and
**Drop stale** removes them after asking. **Rescan** reads the experiment
registry again.

## Saving

Changes live in a working copy until **Save**, which writes
`plugins.disabled_models` into *your* settings file. **Revert** discards them,
after asking. The status line says *unsaved changes* until you save. The drop-down picks the change up
the next time you select a dataset — no restart needed.

## Further reading

- [Settings reference](docs/reference/settings.md)
