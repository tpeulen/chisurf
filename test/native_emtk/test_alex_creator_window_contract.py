"""ALEX primary geometry retains saved host dimensions and existing scientific state."""

import copy
import json
from pathlib import Path

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Use scratch preferences and metadata for every factory call."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_reaches_the_real_factory(tmp_path, monkeypatch):
    """The raw spec declares geometry before locale/layout preparation."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.ptu_alex_creator.gui import app as owner

    original = Path(owner.__file__).with_name("alex_emtk.view.json").read_bytes()
    app = attach_native_state("alex_primary", owner.make_app(state_path=tmp_path / "state.json"))
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert Path(owner.__file__).with_name("alex_emtk.view.json").read_bytes() == original
    finally:
        app.close()


def test_saved_dimensions_and_conversion_settings_win(tmp_path, monkeypatch):
    """Native host restore and the existing state file preserve conversion parameters."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.ptu_alex_creator.gui.app import make_app

    state_path = tmp_path / "state.json"
    first = attach_native_state("alex_saved", make_app(state_path=state_path))
    first.model.alex_period = 4000
    first.model.period_shift = 23
    state = copy.deepcopy(first.get_state())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("alex_saved", make_app(state_path=state_path))
    try:
        assert other.window_size == (1330, 870)
        assert other.get_state() == state
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
        assert other.get_state() == state
    finally:
        other.close()


def test_workflow_controls_remain_reachable(tmp_path, monkeypatch):
    """The genuine conversion and preview controls are present at the initial host size."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.ptu_alex_creator.gui.app import make_app

    app = attach_native_state("alex_controls", make_app(state_path=tmp_path / "state.json"))
    try:
        driver = Driver(app, size=(1100, 720))
        driver.draw(3)
        assert {"alex_period", "period_shift", "load_input"} <= app.item_rects.keys()
    finally:
        app.close()
