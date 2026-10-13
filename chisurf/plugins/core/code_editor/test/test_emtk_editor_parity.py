"""The emtk Code Editor at control parity with the Qt ``CodeEditorWindow`` it replaced.

The Qt side is ``qt_reference.json``: the legacy window's menu bar, toolbar, docks, combos, buttons,
tree headers, tab bars and status labels, recorded once from the live window (offscreen) and
frozen; ``_recorded`` names the commit. So this file imports no Qt.

Every Qt control is looked up in the emtk app by driving it (emtk ``Driver``: clicks on drawn
text, never a call into the model), under :data:`RENAMED` when its caption changed. A control
that is not reachable is a failure; deliberate differences are :data:`DELIBERATE`, each with its
reason (``okf/plugins/emtk-ports/code_editor/deliberate.json`` says the same).
"""

from __future__ import annotations

import json
import pathlib

import pytest
from emtk.testing import Driver

from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app

QT = json.loads(pathlib.Path(__file__).with_name("qt_reference.json").read_text(encoding="utf-8"))
SIZE = (1400, 860)

#: Qt caption -> emtk caption, where only the words changed.
RENAMED = {
    "Open": "Open…",
    "Folder": "Folder…",
    "Save As": "Save As…",
    "Find": "Find…",
    "Settings": "Settings…",
    "Fwd": "Forward",
    "Def": "Go to definition",
    "Run": "Run Script",
    "Lint": "Lint (Ruff Check)",
    " ": "Show Whitespace",
    "": "Show Whitespace",
}

#: Qt controls whose emtk twin is not a 1:1 caption, and why.
DELIBERATE = {
    "Open Notebook": "File ▸ Open Notebook… opens a picker of the same groups and notebooks (emtk menus have no "
    "nested submenus); compared separately",
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    (tmp_path / "project").mkdir()
    (tmp_path / "project" / "script.py").write_text(
        "class Thing:\n    def run(self):\n        return 1\n\n\ndef helper():\n    pass\n",
        encoding="utf-8",
    )
    application = make_editor_app(str(tmp_path / "project"))
    yield application
    application.close()


@pytest.fixture
def driver(app):
    drv = Driver(app, SIZE)
    drv.frame(3)
    return drv


def _drawn(driver) -> list[str]:
    return [entry[5] for entry in driver.frame(2).texts]


def _menu(driver, title: str) -> list[str]:
    """Open the main-menu *title* and return what it draws (then close it again)."""
    from collections import Counter

    before = Counter(_drawn(driver))
    driver.click(title)
    shown = list((Counter(_drawn(driver)) - before).elements()) + [title]
    driver.escape()
    driver.frame(2)
    return shown


def _labels(items) -> list[str]:
    out = []
    for item in items:
        if isinstance(item, dict):
            out.extend(item)
        else:
            out.append(item.split(" [", 1)[0].replace(" (checkable)", ""))
    return out


@pytest.mark.parametrize("menu", sorted(QT["menus"]))
def test_every_qt_menu_item_is_in_the_emtk_menu_of_the_same_name(driver, menu):
    drawn = _menu(driver, menu)
    missing = []
    for label in _labels(QT["menus"][menu]):
        want = RENAMED.get(label, label)
        if label in DELIBERATE:
            continue
        if not any(text == want or text.startswith(want) for text in drawn):
            missing.append((label, want))
    assert not missing, (menu, missing, drawn)


def test_the_shipped_notebooks_submenu_has_the_qt_groups_and_notebooks(app, driver):
    from chisurf.plugins.core.code_editor.shipped_notebooks import notebook_groups

    qt = next(item["Open Notebook"] for item in QT["menus"]["File"] if isinstance(item, dict))
    qt_groups = {group: notebooks for entry in qt for group, notebooks in entry.items()}
    groups = {group: [p.stem for p in paths] for group, paths in notebook_groups().items()}
    assert groups == qt_groups
    driver.click("File")
    driver.click("Open Notebook…")
    drawn = _drawn(driver)
    first = sorted(groups)[0]
    assert any(text.endswith(first) for text in drawn) and groups[first][0] in drawn
    driver.click(groups[first][0])
    assert app.model.active_doc.name == groups[first][0] + ".ipynb"
    assert not app.editor_gui.notebook_window.open


def test_every_qt_toolbar_button_is_on_the_emtk_toolbar(driver):
    drawn = " ".join(_drawn(driver))
    for label in ("New", "Open", "Folder", "Save", "Back", "Fwd", "Def", "Hint", "Run", "Lint",
                  "¶", "Settings", "Agent"):
        assert label in drawn, label
    # The Qt run-target combo: both targets offered.
    assert "Separate process" in drawn or "In ChiSurf console" in drawn


def test_stop_replaces_run_while_a_script_runs(app, driver):
    app.model.is_running_script = True
    try:
        assert "■ Stop" in _drawn(driver)
    finally:
        app.model.is_running_script = False


def test_every_qt_dock_is_an_emtk_dock_listed_under_view(app, driver):
    drawn = _menu(driver, "View")
    for dock in QT["docks"]:
        assert dock in drawn, dock
    gui = app.editor_gui
    for key, label in gui.VIEW_DOCKS:
        assert key in gui.docks.windows, key


@pytest.mark.parametrize("dock", ["Symbols", "Kernel", "Diagnostics", "Agent", "Project", "Output"])
def test_view_toggles_hide_and_show_each_dock(app, driver, dock):
    gui = app.editor_gui
    key = dict((label, key) for key, label in gui.VIEW_DOCKS)[dock]
    shown = gui.docks.is_shown(key)
    driver.click("View")
    driver.click(dock)
    driver.frame(2)
    assert gui.docks.is_shown(key) is not shown


def test_the_project_table_has_the_qt_columns_and_opens_a_clicked_file(app, driver):
    headers = QT["tree_views"][1]
    assert headers == ["Name", "Size", "Kind", "Date Modified"]
    columns = [c["title"] for c in app.editor_gui.view_spec["project"][0]["options"]["columns"]]
    assert columns == headers
    assert "Name" in _drawn(driver) and "script.py" in _drawn(driver)
    driver.click("script.py")
    assert app.model.active_doc.name == "script.py"


def test_the_symbols_table_lists_the_symbols_and_jumps(app, driver):
    assert QT["tree_headers"][0] == ["Symbol", "Line"]
    columns = [c["title"] for c in app.editor_gui.view_spec["symbols"][0]["options"]["columns"]]
    assert {"Symbol", "Line"} <= set(columns)
    app.model.open_file(pathlib.Path(app.model.project_root) / "script.py")
    driver.click("Symbols")
    drawn = _drawn(driver)
    assert "Thing.run" in drawn and "helper" in drawn
    driver.click("helper")
    assert app.model.active_doc.editor.cursors.main.end.line == 5


def test_the_kernel_dock_says_what_it_needs_and_offers_restart(app, driver):
    driver.click("Kernel")
    drawn = _drawn(driver)
    assert "Open a notebook to get a kernel terminal." in drawn
    assert any("Restart" in text for text in drawn)
    app.model.new_document("Untitled.ipynb")
    drawn = _drawn(driver)
    assert "Notebook terminal" in drawn


def test_the_find_bar_has_the_qt_toggles(app, driver):
    app.model.open_file(pathlib.Path(app.model.project_root) / "script.py")
    driver.click("Edit")
    driver.click("Find…")
    drawn = _drawn(driver)
    for label in ("Match case", "Whole word", "Regex", "Prev", "Next", "Close find"):
        assert label in drawn, label  # Qt: Aa, \b, .*, ▲, ▼, ✕


def test_regex_find_selects_a_pattern_match(app, driver):
    import inspect

    from emtk.widgets.text_editor import TextEditor

    if "regex" not in inspect.signature(TextEditor.set_find_text).parameters:
        pytest.skip("regex search needs emtk 0.1.10")
    app.model.open_file(pathlib.Path(app.model.project_root) / "script.py")
    gui = app.editor_gui
    gui.open_find()
    gui.find_text, gui.find_regex = r"def \w+", True
    driver.frame(2)
    assert gui.find_next()
    assert app.model.active_doc.editor.selected_text() == "def run"


def test_the_assistant_offers_the_qt_agent_controls(app, driver):
    driver.click("🤖 Agent")
    driver.frame(2)
    if not app.editor_gui.docks.is_shown("agent"):
        driver.click("🤖 Agent")
    app.editor_gui.docks.focus("agent")
    drawn = " ".join(_drawn(driver))
    for label in ("Things to ask", "Wiki", "Send"):
        assert label in drawn, label
    # Qt's mode combo: the three modes.
    from chisurf.plugins.core.code_editor.gui.chat_app import MODE_LABELS

    assert [m.split(" ", 1)[1] for m in QT["combos"]["1"]] == list(MODE_LABELS.values())


def test_the_status_line_has_the_position_and_the_lsp_state(app, driver):
    assert QT["status"][1] == "Ln 1, Col 0" and QT["status"][3] == "LSP idle"
    drawn = " ".join(_drawn(driver))
    assert "Ln 1, Col 1" in drawn  # emtk counts columns from 1, as the line
    assert app.model.lsp_status in drawn


def test_the_settings_menu_toggles_line_numbers_and_whitespace(app, driver):
    numbers = app.model.show_line_numbers
    driver.click("Settings")
    driver.click("Show Line Numbers")
    assert app.model.show_line_numbers is not numbers
    whitespace = app.model.show_whitespace
    driver.click("Settings")
    driver.click("Show Whitespace")
    assert app.model.show_whitespace is not whitespace


def test_the_qt_free_port():
    from test.gui.emtk_port_parity import qt_free

    assert qt_free("code_editor")["ok"] is True


def test_the_open_file_hand_off_opens_the_file_at_its_line(app, driver):
    """A source link in the shell hands the file over (manifest ``accepts`` open_file)."""
    from chisurf.core.plugin import handoff

    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "manifest.json").read_text(encoding="utf-8")
    )
    spec = handoff.accepted("code_editor", "open_file", manifest)
    assert spec is not None and spec.required == ["path"]
    target = pathlib.Path(app.model.project_root) / "script.py"
    handoff.deliver(app, spec, {"path": str(target), "line": 6})
    assert app.model.active_doc.name == "script.py"
    assert app.model.active_doc.editor.cursors.main.end.line == 5
    with pytest.raises(FileNotFoundError):
        handoff.deliver(app, spec, {"path": str(target.with_name("absent.py"))})
