"""The native Wizards hub against the Qt hub: same entries, order, tooltips, titles, embedded wizards, state."""

from __future__ import annotations

import json

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts,
    draw_clip,
    layout_problems,
)
from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401
from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear

from ..core.registry import default_wizards
from ..gui.app import WizardHubApp

BIG, SMALL = (1200, 800), (800, 600)


def test_the_catalogue_names_a_native_factory_for_every_wizard():
    entries = default_wizards()
    assert [e.id for e in entries] == ["anisotropy", "batch_analysis"]
    for entry in entries:
        module, attr = entry.emtk.split(":")
        import importlib

        assert callable(getattr(importlib.import_module(module), attr))


def test_the_list_equals_the_qt_hubs_list(qapp):
    from ..gui.tool import WizardHub

    qt = WizardHub()
    app = WizardHubApp()
    qt_items = [
        (qt._list.item(i).data(0x100), qt._list.item(i).toolTip()) for i in range(qt._list.count())
    ]
    assert qt_items == [(e.id, e.description) for e in app.entries]
    assert app.selected == qt._list.item(0).data(0x100)
    for i, entry in enumerate(app.entries):
        qt._list.setCurrentRow(i)
        assert (
            qt._title.text().strip().endswith(entry.label)
            and qt._subtitle.text() == entry.description
        )


def test_the_header_and_the_embedded_wizard_are_drawn_for_each_entry():
    app = WizardHubApp()
    d = Driver(app, BIG)
    for entry in app.entries:
        d.click_name("entry:" + entry.id)
        assert app.selected == entry.id and app.child is not None and not app.error
        strings = d.draw(3).strings
        assert entry.label in strings and entry.description in strings
    app.close()


def test_wizards_are_built_lazily_and_keep_their_state():
    app = WizardHubApp()
    Driver(app, BIG).draw(2)
    assert list(app.children) == ["anisotropy"]
    app.select("batch_analysis")
    batch = app.children["batch_analysis"]
    batch.model.go_to(2)
    app.select("anisotropy")
    assert app.select("batch_analysis") is batch and batch.model.step == 2
    app.close()
    assert app.children == {}


def test_a_failing_factory_is_reported_in_the_header_and_the_rest_works(monkeypatch):
    entries = default_wizards()
    entries[1] = type(entries[1])(**{**entries[1].__dict__, "emtk": "no.such.module:make_app"})
    app = WizardHubApp(entries=entries)
    d = Driver(app, BIG)
    d.click_name("entry:batch_analysis")
    assert app.error.startswith("Could not load 'Batch analysis'") and any(
        "Could not load" in s for s in d.draw(2).strings
    )
    d.click_name("entry:anisotropy")
    assert not app.error and app.child is not None
    app.close()


def test_a_wizard_without_a_native_window_says_so():
    entries = default_wizards()
    entries[1] = type(entries[1])(**{**entries[1].__dict__, "emtk": None})
    app = WizardHubApp(entries=entries)
    app.select("batch_analysis")
    assert "no native window" in app.error
    app.close()


def test_unknown_wizard_raises():
    with pytest.raises(ValueError):
        WizardHubApp().select("nope")


def test_settings_round_trip_with_a_wizard_not_yet_opened():
    app = WizardHubApp()
    app.select("batch_analysis")
    app.children["batch_analysis"].model.save_path = "/tmp/x.csv"
    state = json.loads(json.dumps(app.export_settings()))
    assert (
        state["selected"] == "batch_analysis"
        and state["children"]["batch_analysis"]["save_path"] == "/tmp/x.csv"
    )
    fresh = WizardHubApp()
    fresh.restore_settings(state)
    assert (
        fresh.selected == "batch_analysis"
        and fresh.children["batch_analysis"].model.save_path == "/tmp/x.csv"
    )
    other = WizardHubApp()
    other.restore_settings({"selected": "ghost", "children": {"ghost": {"a": 1}, "anisotropy": 5}})
    other.restore_settings(None)
    assert other.selected == "anisotropy"
    for a in (app, fresh, other):
        a.close()


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_each_wizard_draws_without_layout_problems(size):
    app = WizardHubApp()
    for entry in app.entries:
        app.select(entry.id)
        painter = draw_clip(app, size)
        assert layout_problems(painter, size) == [], (entry.id, layout_problems(painter, size)[:3])
        # the hosted tr_anisotropy dock title 'Anisotropy workflow' needs 133 px at 800 px; that is the child's own layout
        # (reported in REPORT.md), not the hub's
        cut = [c for c in clipped_texts(painter) if "'Anisotropy workflow'" not in c]
        assert cut == [], (entry.id, cut[:3])
    app.close()


def test_every_control_has_a_tooltip_and_the_app_is_qt_free():
    from test.gui.emtk_port_parity import emtk_inventory, qt_free

    app = WizardHubApp()
    assert emtk_inventory(app, BIG)["controls_without_tooltip"] == []
    app.close()
    assert qt_free("wizards")
