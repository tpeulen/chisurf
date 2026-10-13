# ChiSurf Plugin Template

A [cookiecutter](https://github.com/cookiecutter/cookiecutter) template for a new ChiSurf plugin. The
plugin it generates follows the plugin standard: its window is an **emtk app declared by an AutoForm
`view.json`** (no Qt), its numbers come from **backend services** reached through a client, and it
ships a `?` help page and a guided tour.

## Requirements

- [cookiecutter](https://github.com/cookiecutter/cookiecutter)
- a ChiSurf environment (`pixi`), which provides emtk

## Usage

```bash
cookiecutter path/to/cookiecutter-chisurf-plugin
```

Answer the prompts:

- `plugin_name`: the package and plugin id (lowercase, no spaces)
- `plugin_display_name`: the name in the menus
- `plugin_category`: the menu it appears in (e.g. Tools, Structure, Analysis)
- `plugin_description`: one sentence on what it does
- `author_name`, `author_email`
- `class_prefix`: the prefix of the generated classes (`<prefix>App`, `<prefix>ViewModel`, `<prefix>Client`)

Copy the generated directory into `chisurf/plugins/` (or `~/.chisurf/plugins/`) and open it with
`python -m chisurf.plugins.<plugin_name>`, or from either ChiSurf shell's menu.

## What you get

- `manifest.json`: id, menu path, icon, the `emtk` entry (`gui.app:make_app`), the CLI and the
  backend services with their `rpc_methods`.
- `gui/<plugin_name>.view.json`: the window. Every control is a section: `value` edits a view-model
  attribute, `button_row` calls a view-model method, `info` shows what a method returns, `table` /
  `data_table` show rows. Each carries a `description` (tooltip and generated docs).
- `gui/view_model.py`: the window's state, toolkit-free; it reaches the backend only through
  `gui/client.py`.
- `gui/app.py`: draws the spec with emtk; hand-write draw code here only for what a spec cannot
  express (plots, images).
- `gui/help.md` and `gui/guide.json`: the `?` page and the guided tour; replace both.
- `backend/services.py`, `core/`, `api/`: the RPC handlers, the pure computation and its DTOs.
- `tests/`: the manifest, the client, and the window drawn headlessly (no Qt imported).

## License

This template is licensed under the same license as ChiSurf.
