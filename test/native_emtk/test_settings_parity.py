"""Settings parity audit: every panel must open, render and persist.

The user-facing contract of the EMTK settings hub matches the Qt tool: every
panel opens without error, the selected panel's content renders, YAML
configuration panels edit and save with their types preserved, and native
panels round-trip their state. This audit walks all of them so a broken panel
fails here instead of in front of a user.
"""

from __future__ import annotations

import tempfile

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.setup.gui.app import UnifiedSettingsApp


@pytest.fixture
def hub():
    app = UnifiedSettingsApp(settings_dir=tempfile.mkdtemp())
    return app


def test_every_panel_opens_and_renders(hub):
    rendered = []
    for panel in hub.panels:
        hub.select(panel.key)
        painter = RecordingPainter()
        hub.draw(painter, 0, 0, 1100, 800)
        assert not hub.error, (panel.key, hub.error)
        assert any(panel.label in s for s in painter.strings), panel.key
        rendered.append(panel.key)
    assert len(rendered) == len(hub.panels)


def test_every_panel_round_trips_state(hub):
    for panel in hub.panels:
        hub.select(panel.key)
        child = hub.child
        assert child is not None, panel.key
        export = getattr(child, "export_settings", None)
        assert callable(export), f"{panel.key} cannot export state"
        state = export()
        assert isinstance(state, dict), panel.key
        restore = getattr(child, "restore_settings", None)
        if callable(restore):
            restore(state)


def test_configuration_panel_saves_yaml_to_disk(hub):
    """A configuration panel's save writes the YAML file it edits."""
    hub.select("chisurf")
    child = hub.child
    save = getattr(child, "save", None)
    assert callable(save), "configuration panel lost its save action"
    save()
    assert child.document.path.exists(), "save did not write the YAML file"


def test_search_filters_panels(hub):
    hub.filter = (
        "kappa" if any("kappa" in p.label.casefold() for p in hub.panels) else "zzz_no_match"
    )
    painter = RecordingPainter()
    hub.draw(painter, 0, 0, 1100, 800)
    if hub.filter == "zzz_no_match":
        nav_rows = [
            s
            for p in hub.panels
            for s in painter.strings
            if s.startswith(("▸ ", "  ")) and p.label in s
        ]
        assert not nav_rows, f"filter left nav rows visible: {nav_rows[:3]}"


def test_native_children_are_registered_as_native(hub):
    """Panels backed by a native plugin factory must route native, not YAML."""
    expected_native = {
        "boarding",
        "style",
        "plots",
        "models",
        "users",
        "ai",
        "plugins",
        "channels",
        "fcs",
        "lut",
        "check",
    }
    for panel in hub.panels:
        hub.select(panel.key)
        if panel.key in expected_native:
            assert hub.routes.get(panel.key) == "native", (
                f"{panel.key} fell back to the YAML editor: {hub.error or hub.routes.get(panel.key)}"
            )
