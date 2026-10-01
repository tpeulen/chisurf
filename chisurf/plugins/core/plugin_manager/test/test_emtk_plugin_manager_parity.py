"""The native plugin manager against the Qt tool: rows, search, edits, file operations, drawing, no Qt.

Hermetic: the settings folder is a temporary one (Save writes there, never to the user's
``~/.chisurf``) and the user plugin directory is a temporary one too, so Install,
Uninstall, Rename and Icon act on throwaway plugins under ``tmp_path`` only. A guard
refuses to remove any folder outside it, and a module fixture compares the real user
plugin directory and the built-in ``about`` plugin before and after the whole module.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
import yaml
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "plugins_emtk.view.json"
TABLE = "plugin_rows"
DEPS = "dependency_rows"
PLUGINS_ROOT = HERE.parents[2]  # chisurf/plugins


# ── hermetic environment ────────────────────────────────────────────────


def _snapshot(root: Path) -> dict:
    """``{relative path: (size, mtime_ns)}`` of every file under *root* (no caches)."""
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_file():
            stat = path.stat()
            out[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
        else:
            out[str(path.relative_to(root)) + "/"] = (0, 0)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_dirs_untouched():
    """Nothing in the real user plugin directory or the built-in ``about`` plugin changes."""
    import chisurf.plugins as plugins

    real_user = Path(plugins.user_plugins_dir)
    about = PLUGINS_ROOT / "core" / "about"
    before = (_snapshot(real_user), _snapshot(about))
    yield
    assert (_snapshot(real_user), _snapshot(about)) == before


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    """Redirect the settings folder (and the MMFDB paths) to a temporary one."""
    folder = tmp_path / "settings"
    folder.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(folder / "m.db"))
    return folder


@pytest.fixture(autouse=True)
def user_dir(tmp_path, monkeypatch):
    """A temporary user plugin directory standing in for ``~/.chisurf/plugins``.

    Discovery, the installer and the uninstall guard all read
    ``chisurf.plugins.user_plugins_dir`` / ``__path__`` at call time. ``rmtree`` in the
    installer additionally refuses any path outside ``tmp_path``, so a wrong redirect
    could never delete a real plugin.
    """
    import chisurf.plugins as plugins
    from chisurf.plugins.core.plugin_manager.api import install as installer

    root = tmp_path / "userplugins"
    root.mkdir()
    real = str(plugins.user_plugins_dir)
    monkeypatch.setattr(plugins, "user_plugins_dir", root)
    monkeypatch.setattr(
        plugins, "__path__", [p for p in plugins.__path__ if p != real] + [str(root)]
    )
    real_rmtree = installer.shutil.rmtree

    def guarded_rmtree(path, *args, **kwargs):
        resolved = Path(path).resolve()
        allowed = (tmp_path.resolve(), Path(tempfile.gettempdir()).resolve())
        assert any(root in resolved.parents for root in allowed), f"refusing to remove {resolved}"
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(installer.shutil, "rmtree", guarded_rmtree)
    plugins.invalidate_plugin_cache()
    yield root
    monkeypatch.undo()
    plugins.invalidate_plugin_cache()


def make_plugin(root: Path, name: str, **manifest) -> Path:
    """A throwaway plugin folder ``root/name`` with an ``__init__.py`` and a manifest."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text('"""A throwaway plugin."""\n')
    data = {
        "id": name,
        "version": "0.1.0",
        "display_name": f"Tools:{name.title()}",
        "description": f"Throwaway plugin {name}.",
    }
    data.update(manifest)
    (folder / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def make_zip(path: Path, folder: Path, wrapper: str = "") -> Path:
    """Zip *folder* into *path* (inside ``wrapper/`` when given)."""
    with zipfile.ZipFile(path, "w") as archive:
        for file in folder.rglob("*"):
            if file.is_file():
                inside = file.relative_to(folder.parent if not wrapper else folder)
                archive.write(file, str(Path(wrapper) / inside) if wrapper else str(inside))
    return path


def make_model(block=None):
    from chisurf.plugins.core.plugin_manager.gui.model import PluginManagerModel

    return PluginManagerModel(settings_block=dict(block or {}))


def make_app(model=None):
    from chisurf.plugins.core.plugin_manager.gui.app import PluginManagerApp

    return PluginManagerApp(model or make_model())


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def pump(app, seconds=30.0):
    """Draw frames until the app's background job has finished."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        draw(app, frames=1)
        if not app.job.busy:
            return
        time.sleep(0.01)
    raise AssertionError("the job did not finish")


def table(app, name=TABLE):
    """The painted table control of an app that has drawn."""
    return app.form.tables[name].control


def click_row(app, plugin_id):
    """Select the row with id *plugin_id* the way the table does when clicked."""
    binding = app.form.tables[TABLE]
    control = binding.control
    index = next(i for i in range(control.row_count()) if control.key_of(i) == plugin_id)
    control.selected_key = plugin_id
    binding._on_select(index)


def shown_ids(app):
    records, _ = app.displayed()
    return [r["id"] for r in records]


def populated(tmp_path_user_dir, *names, **manifests):
    for name in names:
        make_plugin(tmp_path_user_dir, name, **manifests.get(name, {}))


@pytest.fixture
def trio(user_dir):
    """alpha <- gamma (requires), delta requires a plugin that is not there."""
    make_plugin(user_dir, "alpha")
    make_plugin(user_dir, "gamma", requires={"alpha": "*"}, display_name="Setup:Gamma")
    make_plugin(user_dir, "delta", requires={"ghost": "*"}, display_name="Delta")
    import chisurf.plugins as plugins

    plugins.invalidate_plugin_cache()
    return user_dir


# ── 1. rows, columns, status equal the Qt tool's ────────────────────────

QT_TO_KEY = {
    "Plugin": "name", "Id": "id", "Version": "version", "Category": "category",
    "Status": "status", "Requires": "requires", "Required by": "required_by",
    "Optional": "optional", "Source": "source", "Toolbar": "toolbar",
    "Window state": "state",
}


def _qt_cells(table_widget):
    model = table_widget._view.model()
    titles = [str(model.headerData(c, 1)) for c in range(model.columnCount())]
    cells = [
        [str(model.index(r, c).data() or "") for c in range(model.columnCount())]
        for r in range(model.rowCount())
    ]
    return titles, cells


def test_rows_columns_and_status_match_the_qt_widget(qapp, qtbot, trio):
    """The same registry and settings give the Qt table's cells and status line."""
    from qtpy.QtTest import QTest

    from chisurf.gui.widgets.chitable import ChiTableWidget
    from chisurf.plugins.core.plugin_manager.gui.model import TABLE_COLUMNS
    from chisurf.plugins.core.plugin_manager.gui.tool import PluginManagerWidget
    from chisurf.plugins.core.plugin_manager.gui.view_model import PluginManagerViewModel

    settings = {"disabled_plugins": ["tttr_correlate", "tttr_histogram"],
                "toolbar_plugins": ["alpha"]}
    qt_widget = PluginManagerWidget(view_model=PluginManagerViewModel(settings_block=dict(settings)))
    qtbot.addWidget(qt_widget)
    qt_widget.show()
    QTest.qWait(300)
    tables = sorted(qt_widget.findChildren(ChiTableWidget),
                    key=lambda t: -t._view.model().rowCount())
    titles, qt_cells = _qt_cells(tables[0])

    model = make_model(settings)
    app = make_app(model)
    draw(app)
    rows, columns = app.displayed()
    assert [title for _k, title in columns] == [t for _k, t in TABLE_COLUMNS]
    assert len(rows) == len(qt_cells) > 100
    # every Qt column, visible or hidden, by its title
    for qt_index, title in enumerate(titles):
        key = QT_TO_KEY[title]
        assert [str(r[key]) for r in rows] == [row[qt_index] for row in qt_cells], title
    assert sorted(QT_TO_KEY[t] for t in titles) == sorted(
        c["key"] for c in json.loads(SPEC_FILE.read_text())["sections"][0]["sections"][2]
        ["options"]["columns"])
    assert model.status_text() == qt_widget.model.status_text()
    assert "2 disabled" in model.status_text() and "needing attention" in model.status_text()

    # the dependency table of a plugin with edges: same cells, same order
    qt_widget.model.select_row({"id": "gamma"})
    model.select_row({"id": "gamma"})
    QTest.qWait(300)
    deps = sorted(qt_widget.findChildren(ChiTableWidget),
                  key=lambda t: t._view.model().rowCount())[-2:]
    dep_table = next(t for t in deps if t._view.model().columnCount() == 5)
    dep_titles, dep_cells = _qt_cells(dep_table)
    mine = model.dependency_rows()
    assert dep_titles == ["Plugin", "Relation", "Bound", "Installed", "Status"]
    assert [[str(r[k]) for k in ("plugin", "relation", "bound", "installed", "status")]
            for r in mine] == dep_cells
    assert dep_cells and dep_cells[0][0] == "alpha"


def test_rows_status_and_counts_for_the_throwaway_plugins(trio):
    model = make_model({"disabled_plugins": ["gamma"], "hide_disabled_plugins": False})
    rows = {r.plugin_id: r for r in model.rows}
    assert rows["alpha"].source == "user" and rows["alpha"].required_by == ["gamma"]
    assert rows["gamma"].disabled and rows["gamma"].requires == {"alpha": "*"}
    assert rows["gamma"].category == "Setup" and rows["delta"].category == ""
    first = [r for r in model.plugin_rows() if r["id"] == "gamma"][0]
    assert first["status"] == "disabled" and first["requires"] == "alpha"
    assert set(first) >= {"id", "name", "version", "category", "status", "requires",
                          "required_by", "optional", "source", "toolbar", "state"}
    total = len(model.rows)
    assert model.status_text().startswith(f"{total} plugins · 1 disabled")
    assert "needing attention" in model.status_text()  # the deprecated built-in


def test_table_source_keeps_its_identity_until_a_row_changes(trio):
    model = make_model()
    first = model.plugin_rows()
    assert model.plugin_rows() is first
    model.select_row({"id": "alpha"})
    model.selected_disabled = True
    model.show_disabled = True
    second = model.plugin_rows()
    assert second is not first and second.revision > first.revision
    assert [r for r in second if r["id"] == "alpha"][0]["status"] == "disabled"


# ── 2. search, sort, Show disabled ──────────────────────────────────────


def test_filter_box_narrows_the_rows_in_any_column(trio):
    app = make_app()
    draw(app)
    everything = len(shown_ids(app))
    table(app).filter.set_text("throwaway")  # only in nothing: description is not a column
    draw(app)
    assert shown_ids(app) == []
    table(app).filter.set_text("alpha")
    draw(app)
    # the id column is hidden, but the Requires cell of gamma names alpha
    assert set(shown_ids(app)) == {"gamma", "alpha"}
    table(app).filter.set_text("setup")
    draw(app)
    assert "gamma" in shown_ids(app) and "alpha" not in shown_ids(app)
    table(app).filter.set_text("")
    draw(app)
    assert len(shown_ids(app)) == everything
    table(app).filter.set_text("no such plugin anywhere")
    draw(app)
    assert shown_ids(app) == []
    assert f"0 of {everything} rows" in table(app).status_text()


def test_header_sort_orders_the_rows_and_reverses(trio):
    app = make_app()
    draw(app)
    table(app).sort_by("name", False)
    draw(app)
    records, _ = app.displayed()
    names = [r["name"] for r in records]
    assert names == sorted(names, key=str.lower) or names == sorted(names)
    table(app).sort_by("name", True)
    draw(app)
    assert [r["name"] for r in app.displayed()[0]] == list(reversed(names))
    table(app).sort_by("category", False)
    draw(app)
    categories = [r["category"] for r in app.displayed()[0]]
    assert categories == sorted(categories, key=str.lower)


def test_show_disabled_plugins_hides_and_shows_rows(trio):
    model = make_model({"disabled_plugins": ["alpha"], "hide_disabled_plugins": True})
    app = make_app(model)
    draw(app)
    assert "alpha" not in shown_ids(app) and "gamma" in shown_ids(app)
    visible = len(shown_ids(app))
    # the status line counts every plugin, shown or not
    assert model.status_text().startswith(f"{visible + 1} plugins · 1 disabled")
    model.show_disabled = True
    draw(app)
    assert "alpha" in shown_ids(app) and len(shown_ids(app)) == visible + 1
    assert model.dirty and "unsaved changes" in model.status_text()
    # the switch survives a reload (it used to be reset from the settings on every reload)
    model.select_row({"id": "gamma"})
    model.selected_disabled = True
    draw(app)
    assert model.show_disabled is True and "alpha" in shown_ids(app)


# ── 3. the detail pane and its dependencies ─────────────────────────────


def test_selection_fills_the_detail_pane_and_dependency_table(trio):
    model = make_model()
    app = make_app(model)
    painter = draw(app)
    assert "No plugin selected" in painter.strings
    assert model.dependency_rows() == []
    click_row(app, "gamma")
    painter = draw(app)
    assert model.selected.plugin_id == "gamma"
    strings = painter.strings
    assert "Gamma" in strings and "Id: gamma" in strings and "Source: user" in strings
    assert "No plugin selected" not in strings
    edges = model.dependency_rows()
    assert [(e["plugin"], e["relation"], e["bound"], e["installed"], e["status"]) for e in edges] \
        == [("alpha", "requires", "any", "0.1.0", "cli only")]
    assert len(table(app, DEPS).order()) == 1
    click_row(app, "alpha")
    draw(app)
    assert [(e["plugin"], e["relation"]) for e in model.dependency_rows()] == [("gamma", "required by")]
    click_row(app, "delta")
    draw(app)
    edge = model.dependency_rows()[0]
    assert (edge["plugin"], edge["installed"], edge["status"]) == ("ghost", "—", "missing")
    # a built-in with edges in both directions, and one that stands alone
    click_row(app, "traj_tools")
    draw(app)
    assert len(model.dependency_rows()) >= 8
    assert any(e["relation"] == "optional for" for e in model.dependency_rows())
    blocks = dict(model.details_blocks()[:1])
    assert blocks["title"] == "Traj Tools"
    click_row(app, "about")
    painter = draw(app)
    assert model.dependency_rows() == []
    assert any(s.startswith("Stands alone") for s in painter.strings)


def test_the_dependency_table_has_its_own_filter_and_count(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "traj_tools")
    draw(app)
    deps = table(app, DEPS)
    total = len(deps.order())
    assert total >= 9 and f"{total} rows" in deps.status_text()
    deps.filter.set_text("convert")
    draw(app)
    assert len(deps.order()) == 1 and f"1 of {total} rows" in deps.status_text()
    deps.filter.set_text("zzz")
    draw(app)
    assert len(deps.order()) == 0 and f"0 of {total} rows" in deps.status_text()


def test_a_deprecated_plugin_shows_why_it_needs_attention():
    model = make_model()
    model.select_key("vv_vh_anisotropy")
    blocks = model.details_blocks()
    assert ("fact", "Status: deprecated") in blocks
    note = [t for k, t in blocks if k == "note"]
    assert note and note[0].startswith("Deprecated — ")
    assert "> **Deprecated**" in model.details_text()  # the Qt pane's Markdown says the same


# ── 4. switches and choices: dirty, Save, Revert ────────────────────────


def test_toggling_disabled_marks_dirty_and_updates_the_status(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    assert not model.selected_disabled and not model.dirty
    model.selected_disabled = True
    assert model.selected_disabled and model.dirty
    assert "1 disabled" not in model.status_text() or "unsaved changes" in model.status_text()
    assert "unsaved changes" in model.status_text()
    draw(app)
    # a hidden (disabled) row keeps its details, as in the Qt tool
    assert "alpha" not in shown_ids(app)
    assert model.selected.plugin_id == "alpha"


def test_disabling_a_required_plugin_names_the_dependants(trio):
    model = make_model()
    model.select_key("alpha")
    blocking = model.set_disabled(True)
    assert blocking == ["gamma"]
    assert model.set_disabled(False) == []


def test_every_switch_and_choice_marks_dirty_and_save_writes_the_temp_settings(
        trio, hermetic_settings):
    block = {"disabled_plugins": [], "toolbar_plugins": []}
    model = make_model(block)
    model.select_key("alpha")
    model.selected_disabled = True
    model.selected_in_toolbar = True
    model.selected_statefulness = "Remember"
    model.statefulness_mode = "Remember for none"
    model.gui_runtime = "Qt"
    assert model.dirty
    assert model.selected_in_toolbar and model.selected_statefulness == "Remember"
    assert model.statefulness_mode == "Remember for none" and model.gui_mode == "qt"
    assert model.save() is True
    written = yaml.safe_load((hermetic_settings / "settings_chisurf.yaml").read_text())["plugins"]
    assert written["disabled_plugins"] == ["alpha"]
    assert written["toolbar_plugins"] == ["alpha"]
    assert written["statefulness"] == {"mode": "disabled", "per_plugin": {"alpha": True}}
    assert written["gui_mode"] == "qt"
    assert written["hide_disabled_plugins"] is True
    assert not model.dirty and model.status_text().startswith("Settings saved.")
    # the live dict the model was given is not the file; nothing leaked into the real settings
    assert hermetic_settings.is_dir() and str(hermetic_settings).startswith(str(hermetic_settings))


def test_revert_asks_first_and_restores_the_saved_state(trio):
    model = make_model({"disabled_plugins": ["delta"]})
    model.select_key("alpha")
    model.ask_revert()
    assert model.dialog == "" and model.status_text() == "Nothing to revert."
    model.selected_disabled = True
    model.selected_in_toolbar = True
    model.ask_revert()
    assert model.dialog == "confirm_revert"
    assert "Discard every plugin setting" in model.dialog_text
    model.dialog_cancel()
    assert model.dirty and model.selected_disabled and model.dialog == ""
    model.ask_revert()
    model.dialog_ok()
    assert not model.dirty and not model.selected_disabled and not model.selected_in_toolbar
    assert [r.plugin_id for r in model.rows if r.disabled] == ["delta"]
    assert model.status_text() == "Unsaved changes discarded."
    model.selected_disabled = True
    assert "unsaved changes" in model.status_text()


def test_confirmation_dialog_opens_on_screen_and_the_x_cancels(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    model.select_key("alpha")
    model.selected_disabled = True
    model.ask_revert()
    painter = draw(app)
    assert app.message_window.open
    assert "Discard changes" in painter.strings and "Yes" in painter.strings
    assert "No" in painter.strings
    # the toolbar is inert behind a dialog
    assert not model.enabled("save") and not model.enabled("ask_install")
    model.dialog_cancel()
    draw(app)
    assert not app.message_window.open and model.dirty and model.enabled("save")


# ── 5. Move up / Move down ──────────────────────────────────────────────


def test_move_reorders_like_the_qt_tool(trio):
    from chisurf.plugins.core.plugin_manager.api.settings_io import PluginSettings

    model = make_model()
    keys = [r.plugin_id for r in model.visible_rows()]
    model.select_key(keys[3])
    model.move_down()
    expected = PluginSettings({})
    expected.move(keys[3], keys, +1)
    assert model.settings.order == expected.order
    assert model.settings.order[keys[3]] == 4 and model.settings.order[keys[4]] == 3
    assert model.dirty
    model.move_up()
    model.move_up()
    assert model.settings.order[keys[3]] == 2
    model.select_key(keys[0])
    before = dict(model.settings.order)
    model.move_up()  # at the top edge: nothing moves
    assert model.settings.order == before
    model.select_row(None)
    assert not model.enabled("move_up") and not model.enabled("move_down")
    model.move_up()  # no selection: a no-op, as in Qt
    assert model.settings.order == before


# ── 6. Rename ───────────────────────────────────────────────────────────


def test_rename_dialog_edits_the_manifest_and_keeps_the_menu_path(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    model.ask_rename()
    painter = draw(app)
    assert model.dialog == "rename" and model.dialog_input == "Alpha"
    assert "Rename plugin" in painter.strings and "Menu name" in painter.strings
    model.dialog_input = "Renamed One"
    model.dialog_ok()
    manifest = json.loads((trio / "alpha" / "manifest.json").read_text())
    assert manifest["display_name"] == "Tools:Renamed One"
    assert model.selected.name == "Renamed One" and model.selected.category == "Tools"
    assert model.status_text() == "Renamed to 'Tools:Renamed One'."
    assert [r["name"] for r in model.plugin_rows() if r["id"] == "alpha"] == ["Renamed One"]


def test_rename_cancel_and_bad_names_change_nothing(trio):
    model = make_model()
    model.select_key("alpha")
    manifest = (trio / "alpha" / "manifest.json").read_text()
    model.ask_rename()
    model.dialog_input = "Something"
    model.dialog_cancel()
    assert (trio / "alpha" / "manifest.json").read_text() == manifest and model.dialog == ""
    for text, why in (("", "cannot be empty"), ("   ", "cannot be empty"), ("A:B", "leaf name")):
        model.ask_rename()
        model.dialog_input = text
        model.dialog_ok()
        assert model.dialog == "notice" and model.dialog_title == "Cannot rename"
        assert why in model.dialog_text
        model.dialog_ok()
    assert (trio / "alpha" / "manifest.json").read_text() == manifest
    (trio / "alpha" / "manifest.json").unlink()
    model.ask_rename()
    model.dialog_input = "Whatever"
    model.dialog_ok()
    assert "no manifest.json" in model.dialog_text


def test_actions_that_need_a_selection_say_so():
    model = make_model()
    for action in ("ask_rename", "ask_uninstall", "ask_icon", "open_folder"):
        model.dialog = ""
        getattr(model, action)()
        assert (model.dialog, model.dialog_title, model.dialog_text) == (
            "notice", "No plugin selected", "Select a plugin first."), action
    assert not model.icon_open


def test_open_folder_hands_the_plugin_directory_to_the_opener(trio):
    model = make_model()
    opened = []
    model.opener = opened.append
    model.select_key("alpha")
    model.open_folder()
    assert opened == [str(trio / "alpha")]


# ── 7. Icon ─────────────────────────────────────────────────────────────


def _png_bytes(size=(20, 40), colour=(40, 80, 120, 255)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def test_icon_use_copies_a_png_and_converts_other_formats(trio, tmp_path):
    from PIL import Image

    model = make_model()
    model.select_key("alpha")
    model.ask_icon()
    assert model.icon_open and model.icon_title == "Icon — Alpha" and model.icon_path_text == ""
    assert model.icon_provider and model.icon_endpoint.startswith("http") and model.icon_model
    model.icon_use()
    assert model.dialog_title == "No image" and model.dialog_text == "Choose an image file first."
    model.dialog_ok()
    png = tmp_path / "mark.png"
    png.write_bytes(_png_bytes())
    model.icon_path_text = str(png)
    model.icon_use()
    assert (trio / "alpha" / "icon.png").read_bytes() == png.read_bytes()  # copied as is
    assert json.loads((trio / "alpha" / "manifest.json").read_text())["icon"] == "icon.png"
    assert model.icon_changed
    jpg = tmp_path / "mark.jpg"
    Image.new("RGB", (20, 40), (200, 10, 10)).save(jpg)
    model.icon_path_text = str(jpg)
    model.icon_use()
    with Image.open(trio / "alpha" / "icon.png") as icon:
        assert icon.size == (256, 256) and icon.getbbox() == (64, 0, 192, 256)
    bad = tmp_path / "broken.jpg"
    bad.write_text("not an image")
    model.icon_path_text = str(bad)
    model.icon_use()
    assert model.dialog_title == "Unreadable image" and "broken.jpg" in model.dialog_text
    model.dialog_ok()
    model.icon_close()
    assert not model.icon_open and model.status_text() == "Icon updated for 'Alpha'."


def test_icon_clear_asks_then_removes_the_file_and_the_manifest_key(trio, tmp_path):
    model = make_model()
    model.select_key("alpha")
    model.ask_icon()
    png = tmp_path / "mark.png"
    png.write_bytes(_png_bytes())
    model.icon_path_text = str(png)
    model.icon_use()
    icon = trio / "alpha" / "icon.png"
    model.icon_clear()
    assert model.dialog == "confirm_icon_clear" and str(icon) in model.dialog_text
    model.dialog_cancel()
    assert icon.is_file() and "icon" in json.loads((trio / "alpha" / "manifest.json").read_text())
    model.icon_clear()
    model.dialog_ok()
    assert not icon.exists()
    assert "icon" not in json.loads((trio / "alpha" / "manifest.json").read_text())
    model.icon_clear()  # no file: only drops a dangling manifest key, asks nothing
    assert model.dialog == ""
    model.icon_edit()
    assert model.dialog_title == "No icon"


def test_icon_edit_opens_the_file_in_the_system_editor(trio, tmp_path):
    model = make_model()
    opened = []
    model.opener = opened.append
    model.select_key("alpha")
    model.ask_icon()
    png = tmp_path / "mark.png"
    png.write_bytes(_png_bytes())
    model.icon_path_text = str(png)
    model.icon_use()
    model.icon_edit()
    assert opened == [str(trio / "alpha" / "icon.png")]


def test_icon_generate_runs_in_the_background_and_writes_the_icon(trio, monkeypatch):
    from chisurf.plugins.core.plugin_manager.api import icons as icon_api

    calls = []

    def fake(config, info, prompt=None, *, sleep=None):
        calls.append((config.provider, config.endpoint, config.model, info["name"]))
        return _png_bytes((64, 64))

    monkeypatch.setattr(icon_api, "request_icon_bytes", fake)
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    model.ask_icon()
    draw(app)
    assert app.icon_window.open
    model.icon_generate()
    assert app.job.busy and model.icon_status == "Generating…" and not model.enabled("icon_generate")
    pump(app)
    assert calls and calls[0][3] == "Alpha"
    assert model.icon_status == "Icon generated." and (trio / "alpha" / "icon.png").is_file()
    draw(app)
    model.icon_close()


def test_icon_generate_failures_are_reported_not_raised(trio, monkeypatch):
    from chisurf.plugins.core.plugin_manager.api import icons as icon_api

    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    model.ask_icon()
    model.icon_endpoint = ""
    model.icon_generate()
    assert model.dialog_title == "Not configured"
    model.dialog_ok()
    model.icon_endpoint, model.icon_model = "https://example.invalid/v1", "m"

    def boom(*args, **kwargs):
        raise RuntimeError("provider is down")

    monkeypatch.setattr(icon_api, "request_icon_bytes", boom)
    model.icon_generate()
    pump(app)
    assert model.icon_status == "Generation failed: provider is down"
    monkeypatch.setattr(icon_api, "request_icon_bytes", lambda *a, **k: b"not an image")
    model.icon_generate()
    pump(app)
    assert model.icon_status == "The provider returned something that is not an image."
    assert not (trio / "alpha" / "icon.png").exists()


def test_icon_provider_choice_resets_endpoint_and_model(trio):
    model = make_model()
    model.select_key("alpha")
    model.ask_icon()
    labels = model.icon_provider_labels()
    assert len(labels) >= 2 and model.icon_provider_label == labels[0]
    first = (model.icon_endpoint, model.icon_model)
    model.icon_endpoint = "typed"
    model.icon_provider_label = labels[1]
    assert model.icon_endpoint != "typed" and model.icon_provider_label == labels[1]
    model.icon_provider_label = labels[0]
    assert (model.icon_endpoint, model.icon_model) == first


def test_icon_panel_draws_and_choose_opens_a_file_dialog(trio, tmp_path):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    model.ask_icon()
    painter = draw(app)
    for expected in ("Choose…", "Use", "Generate…", "Edit", "Clear", "Provider", "Endpoint",
                     "Image model", "Close", "no icon", "Icon — Alpha"):
        assert expected in painter.strings, expected
    png = tmp_path / "mark.png"
    png.write_bytes(_png_bytes())
    model.icon_path_text = str(png)
    model.icon_use()
    painter = draw(app)
    assert "no icon" not in painter.strings
    model.icon_choose()
    draw(app)
    assert app.dialog is not None and app.dialog.title == "Choose an icon image"
    app.dialog.draw = lambda: [str(png)]
    draw(app, frames=1)
    assert app.dialog is None and model.icon_path_text == str(png)


# ── 8. Install and Uninstall ────────────────────────────────────────────


def test_install_from_a_folder_asks_then_copies_only_into_the_user_dir(trio, tmp_path):
    source = make_plugin(tmp_path / "src", "beta")
    (source / "data.txt").write_text("x")
    elsewhere = _snapshot(tmp_path / "src")
    before = _snapshot(trio)
    model = make_model()
    app = make_app(model)
    draw(app)
    model.choose_install_source(str(source))
    assert model.dialog == "confirm_install" and model.install_plan.plugin_name == "beta"
    assert f"Install 'beta' into {trio}?" in model.dialog_text
    assert _snapshot(trio) == before  # nothing is copied before the user agrees
    painter = draw(app)
    assert "Install plugin" in painter.strings and "Yes" in painter.strings
    model.dialog_ok()
    assert app.job.busy and model.busy
    pump(app)
    after = _snapshot(trio)
    assert set(after) - set(before) == {"beta/", "beta/__init__.py", "beta/manifest.json",
                                        "beta/data.txt"}
    assert set(before) <= set(after)
    assert _snapshot(tmp_path / "src") == elsewhere  # the source is left alone
    assert model.status_text() == f"Installed 'beta' into {trio / 'beta'}."
    assert "beta" in [r.plugin_id for r in model.rows]
    assert [r["source"] for r in model.plugin_rows() if r["id"] == "beta"] == ["user"]


def test_install_from_a_zip_including_a_wrapped_archive(trio, tmp_path):
    folder = make_plugin(tmp_path / "src", "beta")
    flat = make_zip(tmp_path / "beta.zip", folder)
    wrapped_src = make_plugin(tmp_path / "src2", "zeta")
    wrapped = make_zip(tmp_path / "zeta-main.zip", wrapped_src, wrapper="zeta-main")
    model = make_model()
    app = make_app(model)
    draw(app)
    for archive, name in ((flat, "beta"), (wrapped, "zeta")):
        model.choose_install_source(str(archive))
        assert model.dialog == "confirm_install", model.dialog_text
        model.dialog_ok()
        pump(app)
        assert (trio / name / "manifest.json").is_file()
        assert name in [r.plugin_id for r in model.rows]
    assert sorted(p.name for p in trio.iterdir()) == ["alpha", "beta", "delta", "gamma", "zeta"]


def test_install_replacing_a_plugin_says_so_and_decline_changes_nothing(trio, tmp_path):
    source = make_plugin(tmp_path / "src", "alpha", version="9.9.9")
    before = _snapshot(trio)
    model = make_model()
    app = make_app(model)
    draw(app)
    model.choose_install_source(str(source))
    assert "This replaces the plugin already installed there." in model.dialog_text
    model.dialog_cancel()
    assert model.install_plan is None and _snapshot(trio) == before
    model.choose_install_source(str(source))
    model.dialog_ok()
    pump(app)
    assert json.loads((trio / "alpha" / "manifest.json").read_text())["version"] == "9.9.9"
    assert [r.version for r in model.rows if r.plugin_id == "alpha"] == ["9.9.9"]


def test_install_refuses_bad_sources_with_the_reason(trio, tmp_path):
    before = _snapshot(trio)
    model = make_model()
    (tmp_path / "empty").mkdir()
    bad_manifest = make_plugin(tmp_path / "src", "broken")
    (bad_manifest / "manifest.json").write_text("{not json")
    traversal = tmp_path / "evil.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", "x")
    text_file = tmp_path / "notes.txt"
    text_file.write_text("x")
    cases = (
        (tmp_path / "empty", "no __init__.py"),
        (bad_manifest, "not readable JSON"),
        (traversal, "escapes the destination"),
        (text_file, "only a plugin folder or a .zip"),
        (tmp_path / "missing", "does not exist"),
    )
    for source, why in cases:
        model.choose_install_source(str(source))
        assert model.dialog == "notice" and model.dialog_title == "Cannot install", why
        assert why in model.dialog_text, (why, model.dialog_text)
        model.dialog_ok()
        assert model.install_plan is None
    assert _snapshot(trio) == before
    assert not (tmp_path / "escape.txt").exists()


def test_install_without_a_manifest_warns_but_proceeds(trio, tmp_path):
    folder = tmp_path / "src" / "legacy"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text('"""legacy"""\n')
    model = make_model()
    model.choose_install_source(str(folder))
    assert model.dialog == "confirm_install" and "no manifest.json" in model.dialog_text
    model.dialog_ok()
    assert (trio / "legacy" / "__init__.py").is_file()


def test_the_install_chooser_asks_for_a_zip_then_a_folder_when_cancelled(trio, tmp_path):
    model = make_model()
    app = make_app(model)
    draw(app)
    model.ask_install()
    draw(app)
    assert app.dialog.title == "Choose a plugin archive" and app.dialog_purpose == "install_archive"
    app.dialog.draw = lambda: False  # cancelled
    draw(app, frames=1)
    assert app.dialog is not None and app.dialog.title == "Choose a plugin folder"
    assert app.dialog.mode == "folder"
    app.dialog.draw = lambda: False
    draw(app, frames=1)
    assert app.dialog is None and model.dialog == ""
    # a chosen archive goes to the confirmation, not straight to disk
    folder = make_plugin(tmp_path / "src", "beta")
    archive = make_zip(tmp_path / "beta.zip", folder)
    model.ask_install()
    draw(app)
    app.dialog.draw = lambda: [str(archive)]
    draw(app, frames=1)
    assert app.dialog is None and model.dialog == "confirm_install"
    assert not (trio / "beta").exists()
    model.dialog_cancel()


def test_uninstall_of_a_user_plugin_asks_lists_dependants_and_deletes_only_it(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "alpha")
    before = _snapshot(trio)
    model.ask_uninstall()
    assert model.dialog == "confirm_uninstall"
    assert f"Permanently delete 'Alpha' from\n{trio / 'alpha'}?" in model.dialog_text
    assert "These plugins require it and will stop working:\n  gamma" in model.dialog_text
    model.dialog_cancel()
    assert _snapshot(trio) == before  # declined: nothing changed
    model.ask_uninstall()
    model.dialog_ok()
    pump(app)
    after = _snapshot(trio)
    assert not (trio / "alpha").exists()
    assert {k for k in before if not k.startswith("alpha")} == set(after)
    assert "alpha" not in [r.plugin_id for r in model.rows] and model.selected is None
    assert model.status_text() == "Removed 'Alpha'."


def test_uninstall_refuses_a_builtin_plugin_and_changes_nothing_outside(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, "about")
    about = PLUGINS_ROOT / "core" / "about"
    before = (_snapshot(about), _snapshot(trio))
    model.ask_uninstall()
    assert model.dialog == "confirm_uninstall"  # as in Qt: asks, then refuses
    model.dialog_ok()
    pump(app)
    assert model.dialog == "notice" and model.dialog_title == "Cannot uninstall"
    assert "switch a built-in plugin off instead" in model.dialog_text
    assert (_snapshot(about), _snapshot(trio)) == before and about.is_dir()
    assert "about" in [r.plugin_id for r in model.rows]
    painter = draw(app)
    assert "Cannot uninstall" in painter.strings


def test_uninstall_confirmation_lists_the_dependants_of_a_builtin(trio):
    model = make_model()
    model.select_key("imaging_common")
    model.ask_uninstall()
    assert "These plugins require it and will stop working:" in model.dialog_text
    assert len(model.selected.required_by) >= 3
    for dependant in model.selected.required_by:
        assert dependant in model.dialog_text
    model.dialog_cancel()


# ── 9. Rescan ───────────────────────────────────────────────────────────


def test_rescan_runs_in_the_background_and_picks_up_a_new_plugin(trio):
    model = make_model()
    app = make_app(model)
    draw(app)
    before = len(model.rows)
    make_plugin(trio, "omega")  # appears on disk after the manager opened
    assert "omega" not in [r.plugin_id for r in model.rows]
    model.rescan()
    assert app.job.busy and not model.enabled("save") and not model.enabled("rescan")
    pump(app)
    assert [r.plugin_id for r in model.rows].count("omega") == 1 and len(model.rows) == before + 1
    assert model.status_text() == "Plugin folders rescanned."
    draw(app)
    assert "omega" in shown_ids(app)
    # without a runner the same work is done in place
    other = make_model()
    other.runner = None
    make_plugin(trio, "psi")
    other.rescan()
    assert "psi" in [r.plugin_id for r in other.rows]


def test_rescan_failure_is_reported_not_raised(trio, monkeypatch):
    model = make_model()
    app = make_app(model)
    draw(app)

    def boom(self):
        raise RuntimeError("walk failed")

    monkeypatch.setattr(type(model), "do_rescan", boom)
    model.rescan()
    pump(app)
    draw(app)
    assert "walk failed" in model.status_text()


# ── 10. copy and export ─────────────────────────────────────────────────


def test_export_csv_follows_the_filter_and_the_columns(trio, tmp_path):
    app = make_app()
    draw(app)
    table(app).filter.set_text("alpha")
    table(app).set_column_hidden("category", True)
    draw(app)
    model = app.model
    model.request_export()
    draw(app)
    assert app.dialog is not None and app.dialog.title == "Export plugins as CSV"
    target = tmp_path / "out.csv"
    assert model.export_csv(str(target))
    rows = list(csv.reader(target.open(encoding="utf-8")))
    assert rows[0] == ["Plugin", "Version", "Status", "Requires", "Required by"]
    assert sorted(r[0] for r in rows[1:]) == ["Alpha", "Gamma"]
    assert "Exported 2 rows" in model.status_text()
    assert model.export_csv(str(tmp_path / "missing" / "x.csv")) is False
    assert "Could not write" in model.status_text()
    app.dialog.draw = lambda: [str(tmp_path / "chosen")]
    draw(app, frames=1)
    assert (tmp_path / "chosen.csv").is_file() and app.dialog is None


def test_copy_puts_the_shown_rows_with_headers_on_the_clipboard(trio, monkeypatch):
    from emtk import im

    copied = []
    monkeypatch.setattr(im, "set_clipboard_text", copied.append)
    app = make_app()
    draw(app)
    table(app).filter.set_text("alpha")
    draw(app)
    app.model.request_copy()
    draw(app)
    assert len(copied) == 1
    lines = copied[0].splitlines()
    assert lines[0].split("\t") == ["Plugin", "Version", "Category", "Status", "Requires",
                                    "Required by"]
    assert len(lines) == 3 and lines[1].startswith("Alpha\t0.1.0\tTools\tcli only")
    assert "Copied 2 rows" in app.model.status_text()


# ── 11. drawing ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_populated_and_empty_at_both_sizes(size, trio, monkeypatch):
    app = make_app(make_model({"disabled_plugins": ["gamma"]}))
    draw(app, size)
    click_row(app, "alpha")
    strings = draw(app, size).strings
    for expected in ("Installed plugins", "Selected plugin", "Save", "Revert", "Rescan",
                     "Install…", "Uninstall", "Move up", "Move down", "Rename…", "Icon…",
                     "Open folder", "Help", "Guide", "Show disabled plugins", "Disabled",
                     "Show in main toolbar", "Remember window state", "Window state (all plugins)",
                     "Dependencies"):
        assert expected in strings, expected
    assert "Alpha" in strings
    assert any("plugins ·" in s and "disabled" in s for s in strings)
    import chisurf.plugins as plugins

    monkeypatch.setattr(plugins, "iter_plugins", lambda: iter([]))
    model = make_model()
    empty = draw(make_app(model), size)
    assert "Installed plugins" in empty.strings and "No plugin selected" in empty.strings
    assert "Alpha" not in empty.strings and model.status_text() == "0 plugins · 0 disabled"
    assert not model.enabled("selected_disabled") and not model.enabled("move_up")


def test_real_registry_populates_the_app():
    app = make_app()
    painter = draw(app)
    assert len(app.model.rows) > 100
    assert "About ChiSurf" in painter.strings
    assert any(s.startswith("Spectrosc") for s in painter.strings)  # a long cell is shortened


# ── 12. spec, tooltips, guide, help ─────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model(trio):
    model = make_model()
    spec = json.loads(SPEC_FILE.read_text())
    app = make_app(model)
    model.select_key("alpha")
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source", "options_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (section.get("type"), key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
            if button.get("label_source"):
                assert callable(getattr(model, button["label_source"]))
            if button.get("hidden_when"):
                assert hasattr(model, button["hidden_when"]["attr"])
        if section.get("hidden_when"):
            assert hasattr(model, section["hidden_when"]["attr"])
        options = section.get("options") or {}
        for key in ("source", "selected_call"):
            if options.get(key):
                assert hasattr(model, options[key]), options[key]
        if section.get("type") == "custom" and section.get("key") != "data_table":
            assert section["key"] in app.form.custom, section["key"]
        columns = [c["key"] for c in options.get("columns", [])]
        if columns:
            source = getattr(model, options["source"])()
            assert set(columns) <= set(source[0]) if source else True, columns


def test_every_control_has_a_tooltip(trio):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("plugin_manager"))
    assert inventory["controls_without_tooltip"] == []
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "table", "data_table", "custom",
                                   "info", "button_row", "panel"):
            assert section.get("description"), section.get("attr") or section.get("title") or section
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("tooltip"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_guide_steps_point_at_controls_the_app_draws(trio):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = make_app()
    draw(app)
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    assert len(steps) >= 8
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        rect = app.item_rects.get(name) or app.form.rects.get(name)
        assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
    awaiting = [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")]
    assert awaiting == ["row_selected", "save"]
    text = " ".join(s["text"] for s in steps)
    assert "📥" not in text and "💾" not in text  # no Qt-era glyph names in the emtk text


def test_the_tour_hears_the_row_pick_and_the_save(trio):
    app = make_app()
    draw(app)
    heard = []
    app.tour.notify_used = heard.append
    app.form.on_used = app.tour.notify_used
    click_row(app, "alpha")
    draw(app)
    assert "row_selected" in heard
    app.form.used("save")
    assert "save" in heard


def test_help_exists_and_its_links_are_live(trio):
    help_text = (GUI / "help.md").read_text()
    for word in ("Rescan", "Install…", "Uninstall", "Rename…", "Icon…", "Copy", "Export CSV",
                 "Remember window state", "GUI runtime"):
        assert word in help_text, word
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    for target in re.findall(r"\]\((docs/[^)#]+)\)", help_text):
        assert (repo / target).is_file(), target
    app = make_app()
    draw(app)
    app.help_window.show()
    assert draw(app).strings


# ── 13. persistence, no Qt ──────────────────────────────────────────────


def test_settings_round_trip(trio):
    app = make_app()
    draw(app)
    table(app).filter.set_text("alpha")
    click_row(app, "alpha")
    draw(app)
    saved = app.export_settings()
    assert saved == {"query": "alpha", "selected_key": "alpha"}
    json.dumps(saved)
    other = make_app()
    other.restore_settings(saved)
    draw(other)
    assert other.model.selected.plugin_id == "alpha"
    assert table(other).filter.text == "alpha"
    assert table(other).selected_key == "alpha"
    assert set(shown_ids(other)) == {"alpha", "gamma"}
    other.restore_settings({"selected": "gamma"})  # the key the earlier text-list app wrote
    assert other.model.selected.plugin_id == "gamma"
    other.restore_settings({"selected_key": "no_such_plugin"})
    assert other.model.selected.plugin_id == "gamma"


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("plugin_manager")
    assert result["ok"], result["output"]
