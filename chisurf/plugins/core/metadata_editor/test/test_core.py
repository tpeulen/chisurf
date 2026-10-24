"""The shared metadata editor: schemas, validation, and the model behind the widget."""

import pytest

from chisurf.plugins.core.metadata_editor import (
    EditorModel,
    Field,
    Schema,
    flrcif_schema,
    freeform_schema,
    zenodo_schema,
)


class TestSchema:
    def test_a_field_needs_a_key(self):
        with pytest.raises(ValueError):
            Field("")

    def test_a_choice_needs_options(self):
        with pytest.raises(ValueError):
            Field("x", kind="choice")

    def test_duplicate_keys_are_refused(self):
        with pytest.raises(ValueError, match="duplicate"):
            Schema([Field("a"), Field("a")])

    def test_the_display_label_falls_back_to_the_key(self):
        assert Field("buffer_composition").display_label == "Buffer composition"
        assert Field("pH", label="pH").display_label == "pH"

    def test_the_presets_are_schemas(self):
        for schema in (freeform_schema(), flrcif_schema(), zenodo_schema()):
            assert isinstance(schema, Schema)
        assert freeform_schema().keys == []
        assert "title" in zenodo_schema().keys
        assert "pH" in flrcif_schema().keys
        # extra keys join as plain fields
        assert "custom_pdbx_key" in flrcif_schema(["custom_pdbx_key"]).keys


class TestEditorModel:
    def test_values_come_from_the_schema_extras_from_beyond(self):
        model = EditorModel(flrcif_schema(), {"pH": 7.4, "note": "hello"})
        assert model.values["pH"] == "7.4"
        assert model.values["temperature"] == ""
        assert model.extras == [["note", "hello"]]

    def test_lists_become_joined_text(self):
        model = EditorModel(
            zenodo_schema(),
            {"keywords": ["fret", "bursts"], "creators": [{"name": "Doe, Jane"}]},
        )
        assert model.values["keywords"] == "fret; bursts"
        assert "Doe, Jane" in model.values["creators"]

    def test_add_extra_writes_schema_values_and_new_rows(self):
        model = EditorModel(flrcif_schema(), {})
        model.extra_key, model.extra_value = "pH", "8.0"
        model.add_extra()
        assert model.values["pH"] == "8.0" and model.extras == []
        model.extra_key, model.extra_value = "note", "x"
        model.add_extra()
        assert model.extras == [["note", "x"]]
        # same key twice edits in place
        model.extra_key, model.extra_value = "note", "y"
        model.add_extra()
        assert model.extras == [["note", "y"]]
        with pytest.raises(ValueError):
            model.extra_key, model.extra_value = "", "z"
            model.add_extra()

    def test_remove_extra_drops_rows_and_clears_schema_values(self):
        model = EditorModel(flrcif_schema(), {"pH": 7.4, "note": "x"})
        model.remove_extra({"key": "note"})
        model.remove_extra({"key": "pH"})
        assert model.extras == [] and model.values["pH"] == ""

    def test_errors_of_required_and_kinds(self):
        model = EditorModel(zenodo_schema(), {"title": "", "publication_date": "2026"})
        problems = model.errors()
        assert problems["title"] == "Title is required."
        assert "YYYY-MM-DD" in problems["publication_date"]
        model2 = EditorModel(flrcif_schema(), {"pH": "not a number"})
        assert "number" in model2.errors()["pH"]
        assert EditorModel(
            zenodo_schema(), {"title": "t", "creators": "Doe, Jane"}
        ).errors() == {}

    def test_entries_merge_schema_and_extras_extras_win(self):
        model = EditorModel(flrcif_schema(), {"pH": 7.4, "note": "x"})
        assert model.entries() == {"pH": "7.4", "note": "x"}
        model.values["pH"] = "  "
        model.extras.append(["pH", "8.1"])
        assert model.entries() == {"note": "x", "pH": "8.1"}

    def test_rows_preview_multiline_values(self):
        model = EditorModel(freeform_schema(), {"desc": "line1\nline2"})
        assert model.rows() == [{"key": "desc", "value": "line1; line2"}]
