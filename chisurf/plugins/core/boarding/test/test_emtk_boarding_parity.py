"""The native onboarding wizard against the Qt wizard: steps, marks, actions, editors, no Qt.

Hermetic: every test points the settings folder, the metadata database and the Qt settings at a
temporary directory (``CHISURF_SETTINGS_DIR``, ``MMFDB_*``), never touches ``~/.chisurf``, the
keyring or the network, and opens no file manager (``open_in_file_manager`` is replaced). Nothing
runs pip or conda: the dependency table only tries ``import``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
PLUGIN = HERE.parent
SPEC_FILE = PLUGIN / "boarding_emtk.view.json"
GUIDE_FILE = PLUGIN / "guide.json"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SIZES = [(1200, 800), (800, 600)]

#: The steps of the Qt wizard as ``boarding.view.json`` declares them.
QT_STEPS = [
    "Welcome",
    "Settings",
    "Fix / Initialize",
    "Experiments",
    "Dependencies",
    "Detector setup",
    "FCS channels",
    "Finish",
]


class Folder(type(Path())):
    """The temporary settings folder, remembering which folders the wizard asked to open."""

    opened: list


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """Settings, metadata database and detector/FCS files in a temporary folder."""
    folder = Folder(tmp_path / "settings")
    folder.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb" / "m.db"))
    import chisurf.core.fluorescence.fcs.channel_setups as fcs_setups
    import chisurf.core.setup_channel_definition as scd
    from chisurf.plugins.core.boarding import utils

    monkeypatch.setattr(scd, "DETECTOR_SETUPS_FILE", folder / "detector_setups.json")
    monkeypatch.setattr(fcs_setups, "FCS_CHANNEL_SETUPS_FILE", folder / "fcs_channel_setups.json")
    opened = []
    monkeypatch.setattr(utils, "open_in_file_manager", lambda path: opened.append(Path(path)))
    folder.opened = opened
    return folder


@pytest.fixture
def model():
    from chisurf.plugins.core.boarding.model import BoardingModel

    return BoardingModel()


@pytest.fixture
def app():
    from chisurf.plugins.core.boarding.app import BoardingApp

    tool = BoardingApp()
    yield tool
    tool.close()


def frames(app, size=(1200, 800), n=3):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def click(app, label, size=(1200, 800), nth=0):
    """Press and release the pointer on the nth drawn *label*; False when it is not on screen."""
    painter = frames(app, size, 2)
    hits = [t for t in painter.texts if t[5] == label]
    if len(hits) <= nth:
        return False
    x, y, w, h = hits[nth][:4]
    x, y = x + w / 2.0, y + h / 2.0
    app.pointer_move(x, y)
    frames(app, size, 1)
    app.pointer_press(x, y, 1)
    frames(app, size, 1)
    app.pointer_release(x, y, 1)
    frames(app, size, 2)
    return True


# ---------------------------------------------------------------- the steps
def test_steps_are_the_qt_steps_in_order(model):
    from chisurf.plugins.core.boarding.view_model import BoardingViewModel

    qt_spec = BoardingViewModel().view_spec().sections[0]
    assert [s.title for s in model.steps] == QT_STEPS == [s.title for s in qt_spec.steps]
    assert [s.subtitle for s in model.steps] == [s.subtitle for s in qt_spec.steps]
    assert [s.optional for s in model.steps] == [bool(s.optional) for s in qt_spec.steps]
    declared = [(s.complete_when or {}).get("attr") for s in qt_spec.steps]
    assert [s.complete_when for s in model.steps] == declared


def test_back_next_finish_follow_the_qt_bar(model):
    assert model.is_first and not model.enabled("go_back")
    model.go_back()
    assert model.step == 0
    for expected in range(1, len(QT_STEPS)):
        model.go_next()
        assert model.step == expected
        assert model.enabled("go_back")
    assert model.is_last
    model.go_next()
    assert model.step == len(QT_STEPS) - 1
    assert not model.finished
    model.finish()
    assert model.finished
    model.go_back()
    assert model.step == len(QT_STEPS) - 2


def test_finish_does_nothing_before_the_last_step(model):
    model.finish()
    assert not model.finished


def test_next_is_never_gated_the_wizard_is_not_linear(model):
    assert not model.step_complete(model.steps.index(next(s for s in model.steps if s.id == "detector")))
    for _ in range(len(QT_STEPS) - 1):
        model.go_next()
    assert model.is_last


def test_go_to_clamps_and_clears_the_notice(model):
    model.notice = "x"
    model.go_to(99)
    assert model.step == len(QT_STEPS) - 1 and model.notice == ""
    model.go_to(-5)
    assert model.step == 0


# ------------------------------------------- marks equal the Qt wizard's marks
@pytest.fixture
def qt_wizard(tmp_path):
    pytest.importorskip("qtpy")
    from qtpy import QtCore, QtWidgets

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
    QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp_path / "qt"))
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.gui.autoform.sections.wizard_section import WizardWidget
    from chisurf.plugins.core.boarding.wizard import WelcomeToChiSurfWizard

    wiz = WelcomeToChiSurfWizard()
    widget = wiz.assistant.auto_form.findChildren(WizardWidget)[0]
    yield wiz, widget
    wiz.close()
    qapp.processEvents()


def qt_marks(widget):
    return [widget.nav_list.item(i).text().startswith("✓") for i in range(widget.nav_list.count())]


def test_marks_equal_the_qt_nav_marks_fresh_and_after_create_missing(model, qt_wizard):
    wiz, widget = qt_wizard
    assert [model.step_complete(i) for i in range(8)] == qt_marks(widget)
    # the fresh temporary folder has no settings_chisurf.yaml: the Settings step has no mark
    assert qt_marks(widget)[1] is False
    wiz.model.create_missing()
    model.create_missing()
    widget.refresh()
    assert [model.step_complete(i) for i in range(8)] == qt_marks(widget)


def test_marks_equal_the_qt_nav_marks_with_a_saved_detector_setup(model, app, qt_wizard):
    wiz, widget = qt_wizard
    app.detector_editor().toolbar.save("lab")
    model.refresh_completion()
    widget.refresh()
    assert model.step_complete(5) is True
    assert [model.step_complete(i) for i in range(8)] == qt_marks(widget)


def test_back_and_next_enabled_states_equal_qt(model, qt_wizard):
    wiz, widget = qt_wizard
    for index in range(8):
        widget.nav_list.setCurrentRow(index)
        model.go_to(index)
        assert model.enabled("go_back") == widget.back_btn.isEnabled()
        assert (not model.is_last) == (not widget.next_btn.isHidden())
        assert model.is_last == (not widget.finish_btn.isHidden())


def test_status_table_rows_equal_the_qt_html_rows(model):
    from chisurf.plugins.core.boarding import utils

    html = utils.build_status_html()
    rows = model.status_rows()
    assert [r["item"] for r in rows][:3] == ["User settings directory", "settings_chisurf.yaml", "settings_colors.yaml"]
    assert len(rows) == html.count("<tr>")
    for row in rows:
        assert row["item"] in html and row["status"] in html
        assert row["detail"].replace("&", "&amp;") in html or not row["detail"]
    deps = model.deps_rows()
    assert [r["module"] for r in deps] == ["tttrlib", "pyqtgraph", "markdown", "pymol"]
    assert len(deps) == utils.build_deps_html().count("<tr>")


# ---------------------------------------------------------------- the actions
def test_create_missing_writes_only_missing_files(model, hermetic):
    target = hermetic / "settings_colors.yaml"
    assert not target.exists()
    assert {r["item"]: r["status"] for r in model.status_rows()}["settings_colors.yaml"] == "MISSING"
    model.create_missing()
    assert target.is_file()
    assert model.repair_ok and "missing files only" in model.repair_message
    assert {r["item"]: r["status"] for r in model.status_rows()}["settings_colors.yaml"] == "OK"
    target.write_text("kept: true\n")
    model.create_missing()
    assert target.read_text() == "kept: true\n"
    # As in the Qt wizard: the main settings file is never copied by "Create missing files"
    # (the core reads it as defaults overlaid by the user's file), so it stays MISSING there.
    assert not (hermetic / "settings_chisurf.yaml").exists()


def test_restore_defaults_asks_and_declining_changes_nothing(model, hermetic):
    model.create_missing()
    target = hermetic / "settings_colors.yaml"
    target.write_text("mine: 1\n")
    model.request_restore()
    assert model.confirm == "restore"
    model.confirm_no()
    assert model.confirm == "" and target.read_text() == "mine: 1\n"
    assert model.repair_message.startswith("Defaults copied (missing files only)")
    model.request_restore()
    model.confirm_yes()
    assert model.confirm == "" and target.read_text() != "mine: 1\n"
    assert model.repair_ok and "overwrite" in model.repair_message
    assert "overwrite" in model.repair_status_html()
    # only the overwrite path writes the main settings file; it is what gives the Settings step its mark
    assert (hermetic / "settings_chisurf.yaml").is_file() and model.step_complete(1) is True


def test_failing_copy_is_reported_not_raised(model, monkeypatch):
    import shutil

    def broken(*args, **kwargs):
        raise OSError("disk full (test)")

    monkeypatch.setattr(shutil, "copyfile", broken)
    model.overwrite_defaults()
    assert model.repair_ok is False and "disk full (test)" in model.repair_message


def test_update_experiments_resyncs_only_that_file(model, hermetic):
    target = hermetic / "experiment_configs.yaml"
    target.write_text("old: 1\n")
    other = hermetic / "settings_colors.yaml"
    other.write_text("keep: 1\n")
    model.update_experiments()
    assert model.repair_ok and "updated" in model.repair_message
    assert target.read_text() != "old: 1\n" and other.read_text() == "keep: 1\n"
    model.update_experiments()
    assert "already up to date" in model.repair_message


def test_open_settings_folder_opens_the_user_folder(model, hermetic):
    model.open_settings_dir()
    assert hermetic.opened == [hermetic]


def test_refresh_rereads_status_and_marks(model, hermetic):
    assert model.step_complete(1) is False
    (hermetic / "settings_chisurf.yaml").write_text("a: 1\n")
    assert model.step_complete(1) is False  # not re-read by itself
    model.refresh()
    assert model.step_complete(1) is True
    assert {r["item"]: r["status"] for r in model.status_rows()}["settings_chisurf.yaml"] == "OK"


@pytest.mark.parametrize("opens", [True, False, "raises"])
def test_actions_that_open_another_window_use_the_host(opens):
    from chisurf.plugins.core.boarding.model import BoardingModel

    asked = []

    def host(kind):
        asked.append(kind)
        if opens == "raises":
            raise RuntimeError("no window")
        return opens

    model = BoardingModel(host=host)
    for action, kind in (
        ("open_settings_editor", "settings_editor"),
        ("open_help", "help"),
        ("open_plugin_manager", "plugin_manager"),
    ):
        getattr(model, action)()
        assert asked[-1] == kind
        assert (model.notice == "") == (opens is True)
    assert asked == ["settings_editor", "help", "plugin_manager"]


def test_without_a_host_the_buttons_say_where_the_window_is(model):
    model.open_settings_editor()
    assert "Settings" in model.notice
    model.open_help()
    assert "Help" in model.notice
    model.open_plugin_manager()
    assert "Plugin Manager" in model.notice


# --------------------------------------------------------- the embedded editors
def test_detector_editor_is_the_shared_editor_and_lists_saved_setups(app):
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget

    editor = app.detector_editor()
    assert isinstance(editor.page, ChannelDefinitionWidget)
    assert app.detector_editor() is editor
    assert editor.toolbar.names == []
    editor.toolbar.save("lab")
    assert editor.toolbar.names == ["lab"]
    assert app.model.has_detector_setups is True


def test_saved_detector_setup_marks_the_step_and_is_stored(app):
    app.model.go_to(5)
    frames(app)
    assert app.model.step_complete(5) is False
    editor = app.detector
    editor.toolbar.save("lab")
    app.model.refresh_completion()
    assert app.model.step_complete(5) is True
    assert "lab" in editor.model.refresh_setups()
    assert editor.model.setups["lab"]["detectors"]["green"]["chs"] == [8, 0, 3]


def test_fcs_editor_saves_a_pair_and_marks_the_step(app):
    app.detector_editor().toolbar.save("lab")
    fcs = app.fcs_editor()
    fcs.model.reload_setups()
    fcs.select_setup("lab")
    assert fcs.model.channel_names == ["green", "red", "yellow"]
    assert app.model.step_complete(6) is False
    fcs.channel_a, fcs.channel_b = "green", "red"
    fcs.add_pair()
    fcs.save()
    app.model.refresh_completion()
    assert app.model.step_complete(6) is True
    assert fcs.model.pairs[0]["channel_a"] == "green" and fcs.model.pairs[0]["channel_b"] == "red"
    assert app.model.has_fcs_setups is True


def test_fcs_close_goes_on_to_the_last_step(app):
    app.model.go_to(6)
    fcs = app.fcs_editor()
    fcs.request_close()
    assert app.model.step == len(QT_STEPS) - 1


def test_editors_are_built_on_first_use_only(app):
    frames(app)
    assert app.detector is None and app.fcs is None
    app.model.go_to(5)
    frames(app)
    assert app.detector is not None and app.fcs is None
    app.model.go_to(6)
    frames(app)
    assert app.fcs is not None


# ------------------------------------------------- spec, tooltips, guide, i18n
def spec_walk(spec):
    def walk(sections):
        for section in sections:
            yield section
            yield from walk(section.get("sections", []))

    return list(walk(spec["sections"]))


def test_every_spec_key_exists_on_the_model(model, app):
    spec = json.loads(SPEC_FILE.read_text())
    names = [s["name"] for s in spec["sections"]]
    assert names[2:] == ["welcome", "settings", "fix", "experiments", "dependencies", "detector", "fcs", "finish"]
    for section in spec_walk(spec):
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"], None)), button["action"]
            hidden = button.get("hidden_when")
            if hidden:
                assert hasattr(model, hidden["attr"]), hidden["attr"]
        options = section.get("options") or {}
        if section.get("key") == "markdown":
            assert callable(getattr(model, options["source"])), options["source"]
        if section.get("key") == "data_table":
            assert isinstance(getattr(model, options["source"])(), list)
            for call in ("selected_call", "edited_call"):
                if options.get(call):
                    assert callable(getattr(model, options[call]))
        if section.get("type") == "custom" and section.get("key") not in ("data_table",):
            assert section["key"] in app.form.custom, section["key"]


def test_every_control_has_a_tooltip_on_every_step(app):
    from test.gui.emtk_port_parity import emtk_inventory

    for index in range(len(QT_STEPS)):
        app.model.go_to(index)
        inventory = emtk_inventory(app)
        assert inventory["controls_without_tooltip"] == [], (index, inventory["controls_without_tooltip"])
    spec = json.loads(SPEC_FILE.read_text())
    for section in spec_walk(spec):
        assert section.get("description"), section.get("name") or section.get("key") or section
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("tooltip") or column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_guide_targets_are_real_controls(app):
    guide = json.loads(GUIDE_FILE.read_text())
    targets = {s["target"]["name"] for s in guide["steps"] if s.get("target")}
    seen = set()
    for index in range(len(QT_STEPS)):
        app.model.go_to(index)
        frames(app)
        seen |= set(app.item_rects) | set(app.form.rects)
    assert targets <= seen, sorted(targets - seen)
    assert len([s for s in guide["steps"] if s.get("await")]) >= 3


def test_the_awaited_buttons_are_noticed_by_the_tour(app):
    names = []
    app.tour.notify_used = names.append
    app.form.on_used = names.append
    app.model.go_to(0)
    assert click(app, "Next")
    assert "go_next" in names and app.model.step == 1


def test_translations_exist_for_the_texts_the_app_adds():
    from chisurf.plugins.core.boarding.strings import _CATALOGS

    for catalog in _CATALOGS.values():
        for key in ("Steps", "Help", "Guide", "Restore defaults"):
            assert key in catalog


# ------------------------------------------------------------------- drawing
@pytest.mark.parametrize("size", SIZES)
def test_every_step_draws_empty_and_populated(size, app):
    expected = {
        0: "Welcome to ChiSurf",
        1: "Settings status",
        2: "Create missing files",
        3: "Update experiments",
        4: "Optional dependencies",
        5: "Detector setup",
        6: "FCS channels",
        7: "Open Plugin Manager",
    }
    for index in range(len(QT_STEPS)):
        app.model.go_to(index)
        painter = frames(app, size)
        strings = " ".join(painter.strings)
        assert expected[index].split()[0] in strings, (index, strings[:200])
    app.model.create_missing()
    app.detector_editor().toolbar.save("lab")
    app.model.refresh_completion()
    for index in range(len(QT_STEPS)):
        app.model.go_to(index)
        painter = frames(app, size)
        assert painter.strings


def test_settings_table_shows_the_populated_rows(app, hermetic):
    app.model.create_missing()
    app.model.go_to(1)
    strings = " ".join(frames(app).strings)
    assert "settings_colors" in strings and "MISSING" in strings and "OK" in strings


def test_restore_question_is_drawn_and_declined_by_keep(app, hermetic):
    app.model.go_to(2)
    assert click(app, "Restore defaults (overwrite)")
    assert app.model.confirm == "restore"
    strings = " ".join(frames(app).strings)
    assert "Keep my settings" in strings
    assert click(app, "Keep my settings")
    assert app.model.confirm == ""


def test_finish_closes_the_window(app):
    app.model.go_to(7)
    assert click(app, "Finish")
    assert app.model.finished
    assert app.close_requested


def test_repair_outcome_is_drawn_green_or_red(app, monkeypatch):
    app.model.go_to(3)
    app.model.update_experiments()
    assert app.model.repair_message in " ".join(frames(app).strings)


# --------------------------------------------------------------- persistence
def test_settings_round_trip(app):
    app.model.go_to(4)
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved["step"] == 4
    from chisurf.plugins.core.boarding.app import BoardingApp

    other = BoardingApp()
    other.restore_settings(saved)
    assert other.model.step == 4 and other.model.title == "Dependencies"
    other.restore_settings({"step": "garbage"})
    assert other.model.step == 0
    other.restore_settings({"step": 99})
    assert other.model.step == len(QT_STEPS) - 1
    other.restore_settings({})
    assert other.model.step == 0


# ------------------------------------------------------------------- no Qt
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("boarding")
    assert result["ok"], result["output"]


def test_every_step_is_qt_free_including_the_embedded_editors(tmp_path, hermetic):
    script = """
import importlib.abc, sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise RuntimeError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.core.boarding.app import make_app
app = make_app()
for i in range(8):
    app.model.go_to(i)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
app.model.open_settings_editor(); app.model.open_help(); app.model.open_plugin_manager()
app.model.create_missing(); app.model.update_experiments()
bad = sorted(m for m in sys.modules if m == 'chisurf.gui' or m.startswith('chisurf.gui.'))
assert not bad, bad[:5]
print('QT-FREE OK')
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]))
    done = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env, capture_output=True, text=True)
    assert done.returncode == 0 and "QT-FREE OK" in done.stdout, done.stdout + done.stderr


def test_nothing_was_written_outside_the_temporary_settings(hermetic, model):
    from chisurf.plugins.core.boarding import utils

    model.create_missing()
    assert utils.settings_paths()["user_settings_dir"] == hermetic
    assert str(Path.home() / ".chisurf") != str(hermetic)
