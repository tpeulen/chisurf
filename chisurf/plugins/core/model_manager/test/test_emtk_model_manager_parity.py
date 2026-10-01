"""The native model manager against the Qt tool: rows, filter, sort, edits, drawing, no Qt.

Hermetic: every test points the settings folder at a temporary directory, so
Save writes there and never to the user's ``~/.chisurf``.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pytest
import yaml
from emtk.testing import RecordingPainter

from chisurf.plugins.core.model_manager.api.records import ModelRow, collect_model_rows

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "models_emtk.view.json"
TABLE = "model_rows"


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    """Redirect the settings folder (and the MMFDB paths) to a temporary one."""
    folder = tmp_path / "settings"
    folder.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(folder / "m.db"))
    return folder


# ── a deterministic registry ────────────────────────────────────────────


class _Cls:
    def __init__(self, name, module, qualname, doc="A model."):
        self.name = name
        self.__module__ = module
        self.__qualname__ = qualname
        self.__doc__ = doc
        self.__mro__ = (self,)


class _Exp:
    def __init__(self, label, models):
        self.name = label
        self.model_classes = models


def _fake_registry():
    return {
        "tcspc": _Exp(
            "TCSPC",
            [
                _Cls("Lifetime", "pkg.tcspc", "Lifetime", "Single exponential lifetime."),
                _Cls("Parse-Model", "pkg.tcspc.parse", "ParseTCSPC"),
                _Cls("FRET: discrete", "pkg.tcspc.fret", "FretDiscrete"),
            ],
        ),
        "fcs": _Exp(
            "FCS",
            [_Cls("Parse-Model", "pkg.fcs.parse", "ParseFCS"), _Cls("FCS kinetics", "pkg.fcs", "K")],
        ),
        "pda": _Exp("PDA", [_Cls("PDA2c", "pkg.pda", "Pda2c")]),
    }


@pytest.fixture
def fake_registry(monkeypatch):
    """Make the view model read the fake registry instead of the real one."""
    from chisurf.plugins.core.model_manager.gui import view_model

    def fake(experiments=None, *, disabled=None, ensure_registered=True):
        return collect_model_rows(_fake_registry(), disabled=disabled, ensure_registered=False)

    monkeypatch.setattr(view_model, "collect_model_rows", fake)


def make_model(disabled=None):
    from chisurf.plugins.core.model_manager.gui.model import ModelManagerModel

    return ModelManagerModel(settings_block={"disabled_models": list(disabled or [])})


def make_app(model=None):
    from chisurf.plugins.core.model_manager.gui.app import ModelManagerApp

    return ModelManagerApp(model or make_model())


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


def table(app):
    """The painted table control of an app that has drawn."""
    return app.form.tables[TABLE].control


def click_row(app, key):
    """Select the row with record ``key`` the way the table does when clicked."""
    binding = app.form.tables[TABLE]
    control = binding.control
    index = next(i for i in range(control.row_count()) if control.key_of(i) == key)
    control.selected_key = key
    binding._on_select(index)


def key_of(model, name, experiment=None):
    return next(
        r.key
        for r in model.rows
        if r.name == name and (experiment is None or r.experiment_label == experiment)
    )


def shown_names(app):
    records, _ = app.displayed()
    return [(r["name"], r["experiment"]) for r in records]


# ── 1. rows and status counts equal the Qt tool's ───────────────────────


def test_rows_and_status_match_the_qt_widget(qapp, qtbot):
    """The same registry and settings give the Qt table's cells and status line."""
    from chisurf.gui.widgets.chitable import ChiTableWidget
    from chisurf.plugins.core.model_manager.gui.model import TABLE_COLUMNS
    from chisurf.plugins.core.model_manager.gui.tool import ModelManagerWidget
    from chisurf.plugins.core.model_manager.gui.view_model import ModelManagerViewModel

    settings = {"disabled_models": ["Lifetime", "Et-Model free"]}
    qt_widget = ModelManagerWidget(view_model=ModelManagerViewModel(settings_block=dict(settings)))
    qtbot.addWidget(qt_widget)
    qt_table = qt_widget.findChildren(ChiTableWidget)[0]
    qt_model = qt_table._view.model()
    titles = [str(qt_model.headerData(c, 1)) for c in range(qt_model.columnCount())]
    qt_cells = [
        [str(qt_model.index(r, c).data() or "") for c in range(qt_model.columnCount())]
        for r in range(qt_model.rowCount())
    ]

    model = make_model(settings["disabled_models"])
    app = make_app(model)
    draw(app)
    rows, columns = app.displayed()
    assert [title for _k, title in columns] == [t for _k, t in TABLE_COLUMNS]
    emtk_cells = [[str(r[key]) for key, _t in columns] for r in rows]

    assert len(emtk_cells) == len(qt_cells) > 20
    shared = [c for c in titles if c in [t for _k, t in TABLE_COLUMNS]]
    assert shared == [t for _k, t in TABLE_COLUMNS]
    qt_cells_by_title = [[row[titles.index(t)] for t in shared] for row in qt_cells]
    assert emtk_cells == qt_cells_by_title
    assert model.status_text() == qt_widget.model.status_text()
    assert "2 disabled name(s) match no model" in model.status_text() or (
        "1 disabled name(s) match no model" in model.status_text()
    )


def test_rows_status_and_counts_for_a_known_registry(fake_registry):
    model = make_model(["Parse-Model", "Gone"])
    assert len(model.rows) == 6
    # a disabled display name switches off every model of that name
    assert [r.experiment_label for r in model.rows if r.disabled] == ["TCSPC", "FCS"]
    assert model.status_text() == "6 models · 2 disabled · 1 disabled name(s) match no model"
    first = model.model_rows()[0]
    assert set(first) >= {"key", "name", "experiment", "status", "spec", "ui", "shared"}
    shared = [r["shared"] for r in model.model_rows() if r["name"] == "Parse-Model"]
    assert sorted(shared) == ["FCS", "TCSPC"]


def test_table_source_keeps_its_identity_until_a_row_changes(fake_registry):
    model = make_model()
    first = model.model_rows()
    assert model.model_rows() is first
    model.select_row(first[0])
    model.selected_disabled = True
    second = model.model_rows()
    assert second is not first and second.revision > first.revision
    assert second[0]["status"] == "disabled"


# ── 2. search, sort, Show disabled ──────────────────────────────────────


def test_filter_box_narrows_the_rows_in_any_column(fake_registry):
    app = make_app()
    draw(app)
    assert len(shown_names(app)) == 6
    table(app).filter.set_text("FCS")
    draw(app)
    # any column matches: the TCSPC Parse-Model row names FCS in its Shared cell
    assert shown_names(app) == [
        ("Parse-Model", "TCSPC"), ("Parse-Model", "FCS"), ("FCS kinetics", "FCS")]
    table(app).filter.set_text("pda2c")
    draw(app)
    assert shown_names(app) == [("PDA2c", "PDA")]
    table(app).filter.set_text("no such model")
    draw(app)
    assert shown_names(app) == []
    assert "0 of 6 rows" in table(app).status_text()


def test_header_sort_orders_the_rows_and_reverses(fake_registry):
    app = make_app()
    draw(app)
    table(app).sort_by("name", False)
    draw(app)
    names = [n for n, _e in shown_names(app)]
    assert names == sorted(names, key=str.lower) or names == sorted(names)
    table(app).sort_by("name", True)
    draw(app)
    assert [n for n, _e in shown_names(app)] == list(reversed(names))
    table(app).sort_by("experiment", False)
    draw(app)
    assert [e for _n, e in shown_names(app)] == sorted(e for _n, e in shown_names(app))


def test_show_disabled_models_hides_and_shows_rows(fake_registry):
    model = make_model(["Lifetime"])
    app = make_app(model)
    draw(app)
    assert len(shown_names(app)) == 6
    model.show_disabled = False
    draw(app)
    assert ("Lifetime", "TCSPC") not in shown_names(app)
    assert len(shown_names(app)) == 5
    # the status line counts every model, shown or not
    assert model.status_text().startswith("6 models · 1 disabled")
    model.show_disabled = True
    draw(app)
    assert ("Lifetime", "TCSPC") in shown_names(app)


# ── 3. the Disabled flag, Save, Revert, Rescan, Drop stale ──────────────


def test_toggling_disabled_marks_the_model_dirty_and_the_status(fake_registry):
    model = make_model()
    app = make_app(model)
    draw(app)
    click_row(app, key_of(model, "Lifetime"))
    assert model.selected.name == "Lifetime" and not model.selected_disabled
    model.selected_disabled = True
    assert model.selected_disabled and model.dirty
    assert "1 disabled" in model.status_text() and "unsaved changes" in model.status_text()
    draw(app)
    assert ("Lifetime", "TCSPC") in shown_names(app)
    assert [r for r in model.model_rows() if r["name"] == "Lifetime"][0]["status"] == "disabled"


def test_a_stale_message_does_not_hide_unsaved_changes(fake_registry):
    """Revert's "Unsaved changes discarded." used to stay on the status line forever."""
    model = make_model(["Lifetime"])
    model.select_key(key_of(model, "Lifetime"))
    model.selected_disabled = False
    model.revert()
    assert model.status_text() == "Unsaved changes discarded."
    model.selected_disabled = False
    assert "unsaved changes" in model.status_text()


def test_save_writes_the_temporary_settings_file(fake_registry, hermetic_settings):
    model = make_model()
    model.select_key(key_of(model, "FCS kinetics"))
    model.selected_disabled = True
    assert model.dirty
    assert model.save() is True
    written = yaml.safe_load((hermetic_settings / "settings_chisurf.yaml").read_text())
    assert written["plugins"]["disabled_models"] == ["FCS kinetics"]
    assert not model.dirty
    assert model.status_text().startswith("Saved.")


def test_revert_asks_first_and_restores_the_saved_state(fake_registry):
    model = make_model(["Lifetime"])
    model.select_key(key_of(model, "PDA2c"))
    model.ask_revert()
    assert model.confirm == "" and model.status_text() == "Nothing to revert."
    model.selected_disabled = True
    model.ask_revert()
    assert model.confirm == "revert" and "Discard every model setting" in model.confirm_text
    model.confirm_no()
    assert model.dirty and model.selected_disabled and model.confirm == ""
    model.ask_revert()
    model.confirm_yes()
    assert not model.dirty and not model.selected_disabled
    assert [r.name for r in model.rows if r.disabled] == ["Lifetime"]


def test_drop_stale_lists_the_names_and_removes_only_them(fake_registry):
    model = make_model(["Lifetime", "Et-Model free", "Dye-diffusion"])
    assert model.stale_entries() == ["Dye-diffusion", "Et-Model free"]
    model.ask_drop_stale()
    assert model.confirm == "drop_stale"
    assert "Et-Model free" in model.confirm_text and "Dye-diffusion" in model.confirm_text
    assert "Lifetime" not in model.confirm_text
    model.confirm_no()
    assert len(model.stale_entries()) == 2
    model.ask_drop_stale()
    model.confirm_yes()
    assert model.stale_entries() == []
    assert [r.name for r in model.rows if r.disabled] == ["Lifetime"]
    assert model.dirty
    model.ask_drop_stale()
    assert model.confirm == "" and "No stale entries" in model.status_text()


def test_confirmation_dialog_opens_on_screen_and_cancel_leaves_state(fake_registry):
    model = make_model(["Gone"])
    app = make_app(model)
    draw(app)
    model.ask_drop_stale()
    painter = draw(app)
    assert app.confirm_window.open
    assert "Drop stale entries" in painter.strings and "Cancel" in painter.strings
    assert any("Gone" in s for s in painter.strings)
    model.confirm_no()
    draw(app)
    assert not app.confirm_window.open and model.stale_entries() == ["Gone"]


def test_rescan_runs_in_the_background_and_reports(fake_registry):
    model = make_model()
    app = make_app(model)
    draw(app)
    before = len(model.rows)
    model.rescan()
    assert app.job.busy and not model.enabled("save") and not model.enabled("rescan")
    pump(app)
    assert model.status_text() == "Model registry re-read."
    assert len(model.rows) == before
    # without a runner the same work is done in place
    other = make_model()
    other.runner = None
    other.rescan()
    assert other.status_text() == "Model registry re-read."


def test_rescan_failure_is_reported_not_raised(fake_registry, monkeypatch):
    model = make_model()
    app = make_app(model)
    draw(app)

    def boom(self):
        raise RuntimeError("registry broke")

    monkeypatch.setattr(type(model), "scan", boom)
    model.rescan()
    pump(app)
    draw(app)
    assert "registry broke" in model.status_text()


# ── 4. the detail pane ──────────────────────────────────────────────────


def test_detail_pane_for_several_models(fake_registry):
    model = make_model(["Lifetime"])
    app = make_app(model)
    painter = draw(app)
    assert "No model selected" in painter.strings
    assert any("Pick a row" in s for s in painter.strings)

    click_row(app, key_of(model, "Lifetime"))
    painter = draw(app)
    text = model.details_text()
    assert "### Lifetime" in text and "Single exponential lifetime." in text
    assert "**Status:** disabled" in text and "Shared name" not in text
    assert "Lifetime" in painter.strings and "No model selected" not in painter.strings

    click_row(app, key_of(model, "Parse-Model", "FCS"))
    painter = draw(app)
    text = model.details_text()
    assert "pkg.fcs.parse.ParseFCS" in text and "Experiment:** FCS" in text
    assert "Shared name" in text and "TCSPC" in text
    assert any("Shared name" in s for s in painter.strings)

    click_row(app, key_of(model, "PDA2c"))
    text = model.details_text()
    assert "PDA" in text and "pkg.pda.Pda2c" in text and "**Status:** enabled" in text


def test_detail_pane_reports_a_missing_view_spec(fake_registry):
    model = make_model()
    model._rows = [
        ModelRow("a", "Spec model", "e", "E", "m", "A", "", view_spec="x.json", view_spec_ok=False),
        ModelRow("b", "Qt model", "e", "E", "m", "B", "", qt_bound=True),
    ]
    model.select_row({"key": "a"})
    assert "declared but not found" in model.details_text()
    model.select_row({"key": "b"})
    assert "a Qt class" in model.details_text() and "none declared" in model.details_text()


def test_disabled_switch_follows_the_selection(fake_registry):
    model = make_model()
    assert not model.enabled("selected_disabled")
    model.selected_disabled = True  # nothing selected: a no-op, not an error
    assert not model.dirty
    model.select_key(key_of(model, "PDA2c"))
    assert model.enabled("selected_disabled")


def test_selection_restored_into_the_table(fake_registry):
    model = make_model()
    app = make_app(model)
    draw(app)
    model.select_key(key_of(model, "PDA2c"))
    draw(app)
    assert table(app).selected_key == key_of(model, "PDA2c")


# ── 5. empty state ──────────────────────────────────────────────────────


def test_empty_registry_draws_a_message_not_invented_rows(monkeypatch):
    from chisurf.plugins.core.model_manager.gui import view_model

    monkeypatch.setattr(view_model, "collect_model_rows", lambda *a, **k: [])
    model = make_model()
    app = make_app(model)
    painter = draw(app)
    assert model.status_text() == "0 models · 0 disabled"
    assert "No model selected" in painter.strings
    assert shown_names(app) == []
    assert not model.enabled("selected_disabled")


# ── 6. drawing ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_populated_and_empty_at_both_sizes(size, fake_registry, monkeypatch):
    app = make_app(make_model(["Lifetime"]))
    painter = draw(app, size)
    strings = painter.strings
    for expected in ("Registered models", "Selected model", "Save", "Revert", "Rescan",
                     "Drop stale", "Export CSV", "Help", "Guide", "Show disabled models"):
        assert expected in strings, expected
    assert "Parse-Model" in strings and "Lifetime" in strings
    assert any("6 models" in s for s in strings)
    from chisurf.plugins.core.model_manager.gui import view_model

    monkeypatch.setattr(view_model, "collect_model_rows", lambda *a, **k: [])
    empty = draw(make_app(make_model()), size)
    assert "Registered models" in empty.strings and "No model selected" in empty.strings
    assert "Parse-Model" not in empty.strings


def test_real_registry_populates_the_app(qapp):
    """The registry the Qt tool shows: the app draws its models too."""
    app = make_app(__import__(
        "chisurf.plugins.core.model_manager.gui.model", fromlist=["x"]).ModelManagerModel())
    painter = draw(app)
    assert len(app.model.rows) > 20
    assert "Lifetime" in painter.strings and "TCSPC" in painter.strings


# ── 7. copy and export ──────────────────────────────────────────────────


def test_export_csv_follows_the_filter_and_the_columns(fake_registry, tmp_path):
    app = make_app()
    draw(app)
    table(app).filter.set_text("FCS")
    table(app).set_column_hidden("ui", True)
    draw(app)
    model = app.model
    model.request_export()
    draw(app)
    assert app.dialog is not None and app.dialog.title == "Export models as CSV"
    target = tmp_path / "out.csv"
    assert model.export_csv(str(target))
    rows = list(csv.reader(target.open(encoding="utf-8")))
    assert rows[0] == ["Model", "Experiment", "Status", "Spec", "Shared"]
    assert [r[0] for r in rows[1:]] == ["Parse-Model", "Parse-Model", "FCS kinetics"]
    assert "Exported 3 rows" in model.status_text()
    bad = model.export_csv(str(tmp_path / "missing" / "x.csv"))
    assert bad is False and "Could not write" in model.status_text()


def test_copy_puts_the_shown_rows_with_headers_on_the_clipboard(fake_registry, monkeypatch):
    from emtk import im

    copied = []
    monkeypatch.setattr(im, "set_clipboard_text", copied.append)
    app = make_app()
    draw(app)
    table(app).filter.set_text("PDA")
    draw(app)
    app.model.request_copy()
    draw(app)
    assert len(copied) == 1
    lines = copied[0].splitlines()
    assert lines[0].split("\t") == ["Model", "Experiment", "Status", "Spec", "Parameter UI", "Shared"]
    assert len(lines) == 2 and lines[1].startswith("PDA2c\tPDA\tenabled")
    assert "Copied 1 rows" in app.model.status_text()


# ── 8. spec, tooltips, guide, help ──────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model(fake_registry):
    model = make_model()
    spec = json.loads(SPEC_FILE.read_text())
    app = make_app(model)
    options_keys = ("source", "selected_call", "edited_call")
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source"):
            if section.get(key):
                assert hasattr(model, section[key]), (section.get("type"), key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options") or {}
        for key in options_keys:
            if options.get(key):
                assert hasattr(model, options[key]), options[key]
        if section.get("type") == "custom" and section.get("key") != "data_table":
            assert section["key"] in app.form.custom, section["key"]
        columns = [c["key"] for c in options.get("columns", [])]
        if columns:
            assert set(columns) <= set(model.model_rows()[0]), columns


def test_every_control_has_a_tooltip(fake_registry):
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("model_manager"))
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


def test_guide_steps_point_at_controls_the_app_draws(fake_registry):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = make_app()
    draw(app)
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    assert len(steps) >= 6
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        rect = app.item_rects.get(name) or app.form.rects.get(name)
        assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
    awaiting = [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")]
    assert awaiting == ["row_selected", "save"]


def test_the_tour_hears_the_row_pick_and_the_save(fake_registry):
    app = make_app()
    draw(app)
    heard = []
    app.tour.notify_used = heard.append
    app.form.on_used = app.tour.notify_used
    click_row(app, key_of(app.model, "Lifetime"))
    draw(app)
    assert "row_selected" in heard
    app.form.used("save")
    assert "save" in heard


def test_help_exists_and_its_links_are_live():
    help_text = (GUI / "help.md").read_text()
    assert "Export CSV" in help_text and "Rescan" in help_text
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    import re

    for target in re.findall(r"\]\((docs/[^)#]+)\)", help_text):
        assert (repo / target).is_file(), target
    app = make_app()
    draw(app)
    app.help_window.show()
    assert draw(app).strings


# ── 9. persistence, no Qt ───────────────────────────────────────────────


def test_settings_round_trip(fake_registry):
    model = make_model()
    app = make_app(model)
    draw(app)
    model.show_disabled = False
    click_row(app, key_of(model, "PDA2c"))
    saved = app.export_settings()
    assert saved == {"show_disabled": False, "selected_key": key_of(model, "PDA2c")}
    json.dumps(saved)
    other = make_app(make_model())
    other.restore_settings(saved)
    draw(other)
    assert other.model.show_disabled is False
    assert other.model.selected.name == "PDA2c"
    assert table(other).selected_key == key_of(model, "PDA2c")
    other.restore_settings({})
    assert other.model.show_disabled is True


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("model_manager")
    assert result["ok"], result["output"]
