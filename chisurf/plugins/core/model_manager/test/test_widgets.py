"""Model manager: the registry reading, the settings edits, and the panel.

The plugin had no tests at all, which is how an empty model list, a Save that
wrote into the installed package, and two dead entries in the shipped defaults
all survived.
"""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.core.model_manager.api.records import ModelRow, collect_model_rows
from chisurf.plugins.core.model_manager.gui.view_model import ModelManagerViewModel


class _FakeModel:
    """A model class stand-in."""

    def __init__(self, name, module="pkg.mod", qualname="Cls", doc="A model."):
        self.name = name
        self.__module__ = module
        self.__qualname__ = qualname
        self.__doc__ = doc
        self.__mro__ = (self,)


class _FakeExperiment:
    def __init__(self, label, models):
        self.name = label
        self.model_classes = models


def _registry():
    return {
        "tcspc": _FakeExperiment("TCSPC", [
            _FakeModel("Lifetime", "pkg.tcspc", "Lifetime"),
            _FakeModel("Parse-Model", "pkg.tcspc.parse", "ParseTCSPC"),
        ]),
        "fcs": _FakeExperiment("FCS", [
            _FakeModel("Parse-Model", "pkg.fcs.parse", "ParseFCS"),
        ]),
    }


# ── records ─────────────────────────────────────────────────────────────


def test_models_are_keyed_uniquely_not_by_display_name():
    """Two models called Parse-Model must both survive.

    Keying by display name meant the second overwrote the first, so selecting
    the FCS row showed the other experiment's module and docstring.
    """
    rows = collect_model_rows(_registry())
    assert len(rows) == 3
    keys = {r.key for r in rows}
    assert len(keys) == 3, "rows collapsed on a shared display name"


def test_a_shared_display_name_is_reported():
    """Disabling matches on the name, so a shared name must be visible."""
    rows = collect_model_rows(_registry())
    parse = [r for r in rows if r.name == "Parse-Model"]
    assert len(parse) == 2
    assert all(r.shares_name_with for r in parse)
    assert {r.experiment_label for r in parse} == {"TCSPC", "FCS"}
    lifetime = next(r for r in rows if r.name == "Lifetime")
    assert lifetime.shares_name_with == []


def test_disabled_is_matched_by_display_name():
    rows = collect_model_rows(_registry(), disabled=["Parse-Model"])
    assert [r.name for r in rows if r.disabled] == ["Parse-Model", "Parse-Model"]


def test_the_real_registry_is_not_empty():
    """The list used to be blank outside a GUI session.

    ``Experiment.model_classes`` is filled by whoever registers the models;
    nothing ensured that had happened, so the panel showed nothing and said
    nothing about why.
    """
    rows = collect_model_rows()
    assert len(rows) > 20, f"only {len(rows)} models reached the manager"
    assert any(r.experiment == "tcspc" for r in rows)


def test_every_model_reports_its_parameter_ui():
    for row in collect_model_rows():
        assert row.spec_text() in ("ok", "missing file", "none")
        assert isinstance(row.qt_bound, bool)


# ── the view model ──────────────────────────────────────────────────────


def test_edits_do_not_touch_live_settings_until_saved():
    """The old manager held the live list and mutated it in place."""
    live = {"disabled_models": ["Lifetime"]}
    model = ModelManagerViewModel(settings_block=live)
    model._rows = collect_model_rows(_registry(), disabled=["Lifetime"])
    model.select_row({"name": "Parse-Model", "module": "pkg.fcs.parse"})
    model.selected_disabled = True

    assert live["disabled_models"] == ["Lifetime"], "live settings changed before save"
    assert model.dirty


def test_revert_restores_the_saved_state():
    model = ModelManagerViewModel(settings_block={"disabled_models": []})
    model._rows = collect_model_rows(_registry())
    model.select_row({"name": "Lifetime", "module": "pkg.tcspc"})
    model.selected_disabled = True
    assert model.dirty
    model.revert()
    assert not model.dirty


def test_stale_entries_are_found_and_droppable():
    """The shipped defaults carried two names matching no model."""
    model = ModelManagerViewModel(
        settings_block={"disabled_models": ["Lifetime", "Et-Model free"]}
    )
    model._rows = collect_model_rows(_registry(), disabled=["Lifetime", "Et-Model free"])
    assert model.stale_entries() == ["Et-Model free"]
    assert "match no model" in model.status_text()

    assert model.drop_stale() == 1
    assert model.stale_entries() == []
    assert "Lifetime" in model._disabled, "dropping stale removed a live entry"


def test_details_warn_about_a_shared_name():
    model = ModelManagerViewModel(settings_block={})
    model._rows = collect_model_rows(_registry())
    model.select_row({"name": "Parse-Model", "module": "pkg.fcs.parse"})
    text = model.details_text()
    assert "Shared name" in text and "TCSPC" in text


def test_save_writes_the_user_settings_file(tmp_path, monkeypatch):
    """The old Save wrote into the installed package, where it was ignored."""
    import chisurf.core.settings.settings_utils as settings_utils

    written = {}

    def _fake(section, values):
        written[section] = values
        return True

    monkeypatch.setattr(settings_utils, "update_settings_section", _fake)

    live = {}
    model = ModelManagerViewModel(settings_block=live)
    model._rows = collect_model_rows(_registry())
    model.select_row({"name": "Lifetime", "module": "pkg.tcspc"})
    model.selected_disabled = True
    assert model.save()

    assert written["plugins"]["disabled_models"] == ["Lifetime"]
    assert live["disabled_models"] == ["Lifetime"]
    assert not model.dirty


# ── the panel ───────────────────────────────────────────────────────────


def test_the_view_spec_matches_the_schema():
    from chisurf.core.dataspec.schema import validate_view_spec
    from chisurf.plugins.core.model_manager.gui.view_model import _VIEW_JSON

    assert validate_view_spec(json.loads(_VIEW_JSON.read_text())) == []


def test_every_bound_attribute_exists_on_the_model():
    """A view spec naming a missing attribute renders a dead control."""
    from chisurf.plugins.core.model_manager.gui.view_model import (
        _VIEW_JSON,
        ModelManagerViewModel as VM,
    )

    model = VM(settings_block={})
    spec = json.loads(_VIEW_JSON.read_text())
    missing = []

    def walk(section):
        for key in ("attr", "source", "options_source", "selected_call"):
            target = section.get(key)
            if target and not hasattr(model, target):
                missing.append(f"{section.get('type')}.{key} -> {target}")
        for nested_key in ("source", "selected_call"):
            target = (section.get("options") or {}).get(nested_key)
            if target and not hasattr(model, target):
                missing.append(f"custom.{nested_key} -> {target}")
        for child in section.get("sections", []):
            walk(child)

    for section in spec["sections"]:
        walk(section)
    assert not missing, "view spec binds to missing attributes:\n  " + "\n  ".join(missing)


def test_model_manager_widget_creation(qapp, qtbot):
    """The panel builds and shows the registry."""
    from chisurf.plugins.core.model_manager import ModelManagerWidget

    widget = ModelManagerWidget()
    qtbot.addWidget(widget)
    assert "Model" in widget.windowTitle()
    assert widget.model.rows, "no models reached the panel"
    assert len(widget.model.model_rows()) == len(widget.model.visible_rows())
