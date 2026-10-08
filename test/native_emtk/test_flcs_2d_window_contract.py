"""The real 2D-FLCS factory consumes its declared geometry and saved host size."""

import json
import shutil

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.fcs.flc_2d.gui import app as flcs


def test_real_factory_uses_the_primary_window_declaration(tmp_path, monkeypatch):
    """The shipped tool uses its own 1100×720 declaration before host construction."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    tool = flcs.make_app()
    try:
        assert tool.spec["window"] == {"width": 1100, "height": 720}
        assert tool.window_size == (1100, 720)
    finally:
        tool.close()


def test_factory_reads_authored_dimensions(tmp_path, monkeypatch):
    """A changed primary declaration reaches the actual factory without a literal override."""
    resource = tmp_path / "gui"
    shutil.copytree(flcs.HERE, resource)
    path = resource / "flc_2d_emtk.view.json"
    spec = json.loads(path.read_text())
    spec["window"] = {"width": 1280, "height": 760}
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(flcs, "HERE", resource)
    tool = flcs.make_app()
    try:
        assert tool.window_size == (1280, 760)
    finally:
        tool.close()


def test_saved_resize_wins_when_reopening_real_factory(tmp_path, monkeypatch):
    """The existing host preference seam retains the user's resize over the default."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("flcs_2d_geometry", flcs.make_app())
    assert first.window_size == (1100, 720)
    first.window_resized(940, 640)
    first.close()
    reopened = attach_native_state("flcs_2d_geometry", flcs.make_app())
    try:
        assert reopened.window_size == (940, 640)
    finally:
        reopened.close()
