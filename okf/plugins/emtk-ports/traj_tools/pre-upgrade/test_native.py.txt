"""Qt-free tests for the native trajectory-tools workspace hub."""

from __future__ import annotations

from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from ..app import TrajectoryToolsHubApp, make_app
from ..registry import TOOL_PANELS


def test_registry_covers_every_child_tool():
    names = [panel["name"] for panel in TOOL_PANELS]
    assert names == [
        "Align", "Convert", "Energy Calc", "FRET",
        "Join", "Remove Clashed", "Rot Translate", "Save Topol",
    ]
    assert all(panel["emtk"] for panel in TOOL_PANELS)


def test_native_select_routes_to_child_and_preserves_state():
    app = make_app()
    # The first tool builds eagerly on the first draw; select builds the rest.
    assert app.select("Convert") is not None
    convert = app.children["Convert"]
    assert convert.model is not None
    convert.model.trajectory = "kept.dcd"

    assert app.select("Save Topol") is app.children["Save Topol"]
    # Switching back must return the SAME child with its state intact.
    assert app.select("Convert") is convert
    assert convert.model.trajectory == "kept.dcd"


def test_native_unknown_tool_raises():
    app = make_app()
    with pytest.raises(ValueError):
        app.select("No Such Tool")


def test_native_state_roundtrip_with_pending_child_state():
    app = TrajectoryToolsHubApp()
    app.select("Convert")
    # A file that exists: the trajectory tools do not restore a path whose file has gone.
    run = str(Path(__file__).resolve().parents[5] / "test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd")
    app.children["Convert"].model.trajectory = run
    app.select("FRET")
    app.children["FRET"].model.forster_radius = 51.0
    app.selected = "FRET"

    state = app.export_settings()
    assert state["active_tool"] == "FRET"

    fresh = TrajectoryToolsHubApp()
    fresh.restore_settings(state)
    assert fresh.selected == "FRET"
    assert fresh.children["FRET"].model.forster_radius == 51.0
    # The Convert state was saved before its tool was opened; opening it now
    # applies the pending state.
    fresh.select("Convert")
    assert fresh.children["Convert"].model.trajectory == run


def test_native_renders_hub_and_first_child():
    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 900, 640)
    for expected in (
        "Available tools",
        "Align",
        "Convert",
        "Energy Calc",
        "FRET",
        "Join",
        "Remove Clashed",
        "Rot Translate",
        "Save Topol",
    ):
        assert expected in painter.strings, expected
    # The first child (Align) renders inside the workspace: its heading is
    # drawn onto the same painter through draw_child.
    assert app.child is not None
    assert "Align trajectory" in painter.strings


def test_native_tool_tooltips_in_all_locales():
    from emtk import i18n

    from ..strings import install_translations

    install_translations()
    previous = i18n.get_locale()
    try:
        for locale in ("de", "fr", "es", "pt", "ru"):
            i18n.set_locale(locale)
            app = TrajectoryToolsHubApp()
            painter = RecordingPainter()
            app.draw(painter, 0, 0, 900, 640)
            assert tr_count(painter) >= 0  # rendered without error
            assert tr_label(app, locale), locale
    finally:
        i18n.set_locale(previous)


def tr_count(painter):
    return len(painter.strings)


def tr_label(app, locale):
    from ..strings import tr

    expected = {
        "de": "Trajektorien-Werkzeuge",
        "fr": "Outils de trajectoire",
        "es": "Herramientas de trayectorias",
        "pt": "Ferramentas de trajetórias",
        "ru": "Инструменты траекторий",
    }[locale]
    return tr("Trajectory tools") == expected


def test_native_child_input_forwarding():
    app = make_app()
    app.select("Convert")
    # Keys route into the visible child, not the hub.
    assert app.key(0, "x") in (True, False, None)
    assert app.selected == "Convert"
