"""The FPS card owns its declared host default without changing sibling cards."""

import json
import shutil

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.modelling.structure_tools.cards import fps_json
from chisurf.plugins.modelling.structure_tools.cards.shell import CardShell


def test_reexported_factory_adopts_the_primary_card_window(tmp_path, monkeypatch):
    """The actual standalone plugin factory uses its clean FPS card geometry owner."""
    from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    card = make_app()
    try:
        assert isinstance(card, fps_json.FpsJsonCard)
        spec = json.loads((fps_json.RES / "window.view.json").read_text())
        assert spec["window"] == {"width": 1100, "height": 720}
        assert card.window_size == (1100, 720)
    finally:
        card.close()


def test_card_reads_authored_dimensions_without_mutating_other_cards(tmp_path, monkeypatch):
    """The new declaration affects only FPS; the shared CardShell stays geometry-neutral."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    resource = tmp_path / "resources"
    shutil.copytree(fps_json.RES, resource)
    (resource / "window.view.json").write_text(
        json.dumps({"window": {"width": 1280, "height": 760}, "sections": []})
    )
    monkeypatch.setattr(fps_json, "RES", resource)
    card = fps_json.make_app()
    other = CardShell("Other card", resource, "other_geometry")
    try:
        assert card.window_size == (1280, 760)
        assert getattr(other, "window_size", None) is None
    finally:
        card.close()
        other.close()


def test_saved_fps_card_host_size_wins_over_the_new_default(tmp_path, monkeypatch):
    """Reopening through the existing host preference seam retains the user's dimensions."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("fps_card_geometry", fps_json.make_app())
    assert first.window_size == (1100, 720)
    first.window_resized(940, 640)
    first.close()
    reopened = attach_native_state("fps_card_geometry", fps_json.make_app())
    try:
        assert reopened.window_size == (940, 640)
    finally:
        reopened.close()
