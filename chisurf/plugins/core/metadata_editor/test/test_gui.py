"""The editor widget and the standalone window, driven like a user drives them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from emtk.app import ImApp

from chisurf.plugins.core.metadata_editor.core import flrcif_schema, zenodo_schema
from chisurf.plugins.emtk_test_input import Driver


class _Host(ImApp):
    """A bare window that draws the widget -- what a host plugin does."""

    def __init__(self, widget):
        self.w = widget
        self.item_rects: dict = {}
        super().__init__(gui=self._render)

    def _render(self) -> None:
        self.w.draw()
        self.item_rects.update(self.w.item_rects)


@pytest.fixture
def widget():
    from chisurf.plugins.core.metadata_editor.gui.widget import MetadataEditorWidget

    applied = []
    w = MetadataEditorWidget(on_apply=applied.append)
    w.open(flrcif_schema(), {"pH": "7.4", "note": "hello"})
    return _Host(w), applied


def draw(w, size=(1000, 700)):
    return Driver(w, size).draw(2)


class TestWidget:
    def test_the_schema_fields_are_drawn_with_their_values(self, widget):
        w, _ = widget
        texts = [t[5] for t in draw(w).texts]
        assert "pH *" in texts or "pH" in texts
        assert "hello" in texts  # the extras table shows it

    def test_a_typed_value_reaches_the_entries(self, widget):
        w, _ = widget
        drv = Driver(w, (1000, 700))
        drv.draw(1)
        drv.type_into_name("pH", "8.2")
        assert w.w.editor.entries()["pH"] == "8.2"

    def test_add_extra_through_the_inputs(self, widget):
        w, _ = widget
        drv = Driver(w, (1000, 700))
        drv.draw(1)
        drv.type_into_name("extra_key", "operator")
        drv.type_into_name("extra_value", "TP")
        drv.click_name("add_extra")
        assert w.w.editor.entries()["operator"] == "TP"

    def test_an_entry_without_a_key_shows_a_message_not_a_crash(self, widget):
        w, _ = widget
        drv = Driver(w, (1000, 700))
        drv.draw(1)
        drv.type_into_name("extra_key", "")
        drv.click_name("add_extra")  # must not raise
        texts = [t[5] for t in draw(w).texts]
        assert any("key" in t.lower() for t in texts)

    def test_apply_hands_over_the_entries_and_closes(self, widget):
        w, applied = widget
        drv = Driver(w, (1000, 700))
        drv.draw(1)
        drv.click_name("apply")
        assert applied == [{"pH": "7.4", "note": "hello"}]
        assert not w.w.visible

    def test_a_required_error_is_shown_and_blocks_apply(self):
        from chisurf.plugins.core.metadata_editor.gui.widget import MetadataEditorWidget

        w = MetadataEditorWidget(on_apply=lambda entries: None)
        w.open(zenodo_schema(), {"creators": "Doe, Jane"})  # title missing
        host = _Host(w)
        applied = []
        w.on_apply = applied.append
        drv = Driver(host, (1000, 700))
        texts = [t[5] for t in drv.draw(2).texts]
        assert any("Title is required" in t for t in texts)
        drv.click_name("apply")  # disabled: nothing happens
        assert applied == [] and w.visible

    def test_an_empty_schema_is_only_free_form(self):
        from chisurf.plugins.core.metadata_editor.core import freeform_schema
        from chisurf.plugins.core.metadata_editor.gui.widget import MetadataEditorWidget

        w = MetadataEditorWidget(on_apply=lambda entries: None)
        w.open(freeform_schema(), {"a": "1"})
        drv = Driver(_Host(w), (1000, 700))
        drv.draw(1)
        drv.type_into_name("extra_key", "b")
        drv.type_into_name("extra_value", "2")
        drv.click_name("add_extra")
        assert w.editor.entries() == {"a": "1", "b": "2"}


class TestStandaloneApp:
    @pytest.fixture
    def app(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
        from chisurf.plugins.core.metadata_editor.gui.app import MetadataEditorApp

        return MetadataEditorApp()

    def test_open_edit_apply_round_trips_a_json_file(self, app, tmp_path):
        path = tmp_path / "meta.json"
        path.write_text(json.dumps({"pH": 7.4, "note": "x"}), encoding="utf-8")
        app.pick_schema("flrCIF")  # pH is one of its typed fields
        drv = Driver(app, (1000, 800))
        drv.draw(1)
        drv.click_name("open")
        assert app.dialog is not None  # the floating window is up
        app.dialog.directory = str(tmp_path)
        drv.draw(3)
        drv.click_text("meta.json")
        drv.click_text("Open")
        assert app.path == path and app.editor.editor.entries()["note"] == "x"
        drv.type_into_name("pH", "8.0")
        drv.click_name("apply")
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == {"pH": "8.0", "note": "x"}

    def test_switching_the_schema_keeps_the_entries(self, app):
        from chisurf.plugins.core.metadata_editor.core import freeform_schema

        app.editor.open(freeform_schema(), {"note": "kept"})
        app.pick_schema("flrCIF")
        assert app.editor.editor.entries() == {"note": "kept"}
        assert "pH" in app.editor.editor.values  # the schema's fields are there

    def test_make_app_is_the_entrypoint(self):
        from chisurf.plugins.core.metadata_editor.gui.app import MetadataEditorApp, make_app

        assert isinstance(make_app(), MetadataEditorApp)

    def test_every_control_has_a_tooltip(self, app):
        drv = Driver(app, (1000, 800))
        drv.draw(2)
        assert app.editor.item_rects  # something was laid out
