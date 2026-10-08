"""The molecular host reads declared viewer geometry without altering renderer dimensions."""

import json
from pathlib import Path

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep viewer and native settings in scratch directories."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("CHIMOL_SETTINGS_DIR", str(tmp_path / "chimol"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_host_primary_declares_viewer_geometry(tmp_path, monkeypatch):
    """The true factory consumes a host-only declaration before any lazy renderer exists."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.chimol import app as owner

    app = owner.make_app()
    try:
        spec = json.loads(Path(owner.__file__).with_name("window.view.json").read_text())
        assert spec["window"] == {"width": 1200, "height": 800}
        assert app.window_size == (1200, 800)
        assert app._chimol_size == (900, 620)
        assert app._chimol is None
    finally:
        app.close()


def test_saved_host_size_wins_without_constructing_renderer(tmp_path, monkeypatch):
    """Native geometry restores while the scientific viewer remains lazily constructed."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.chimol.app import make_app

    first = attach_native_state("chimol_geometry", make_app())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("chimol_geometry", make_app())
    try:
        assert other.window_size == (1330, 870)
        assert other._chimol is None
        assert other._chimol_size == (900, 620)
    finally:
        other.close()


def test_declared_reader_honors_primary_values(tmp_path, monkeypatch):
    """The constructor reaches the shared reader with the loaded declaration."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.chimol import app as owner

    seen = []
    original = owner.window_size

    def declared(spec, default):
        """Record the actual primary and return independently chosen host dimensions."""
        seen.append(spec["window"])
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(owner, "window_size", declared)
    app = owner.make_app()
    try:
        assert seen == [{"width": 1200, "height": 800}]
        assert app.window_size == (1234, 789)
        assert app._chimol_size == (900, 620)
    finally:
        app.close()
