"""Burst IRF/background host geometry preserves actual photon extraction."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native preferences, detector setups and synthetic photons in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_default_reaches_app_before_field_loader(tmp_path, monkeypatch):
    """The real app consumes initial geometry before control and result specs are adapted."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui import app as owner

    path = Path(owner.__file__).with_name("irf_bg.view.json")
    original = path.read_bytes()
    app = attach_native_state("burst_irf_primary", owner.create_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"toolAction_run", "send_to_mle", "patterns"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_primary_dimensions_reach_constructor(tmp_path, monkeypatch):
    """A copied raw declaration changes the true constructor's host dimensions."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui import app as owner

    primary = json.loads(Path(owner.__file__).with_name("irf_bg.view.json").read_text())
    primary["window"] = {"width": 960, "height": 640}
    (tmp_path / "irf_bg.view.json").write_text(json.dumps(primary))
    # The results spec is an independent resource consumed by the same GUI.
    (tmp_path / "irf_bg_results_emtk.view.json").write_bytes(
        Path(owner.__file__).with_name("irf_bg_results_emtk.view.json").read_bytes()
    )
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_missing_primary_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """Control-only specs remain usable through the bounded family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui import app as owner

    primary = json.loads(Path(owner.__file__).with_name("irf_bg.view.json").read_text())
    primary.pop("window")
    (tmp_path / "irf_bg.view.json").write_text(json.dumps(primary))
    (tmp_path / "irf_bg_results_emtk.view.json").write_bytes(
        Path(owner.__file__).with_name("irf_bg_results_emtk.view.json").read_bytes()
    )
    monkeypatch.setattr(owner, "__file__", str(tmp_path / "app.py"))
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_native_dimensions_win_without_claiming_analysis_snapshot(tmp_path, monkeypatch):
    """Custom native geometry/docks reopen while photon inputs and extraction are rebuilt explicitly."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app

    first = attach_native_state("burst_irf_saved", create_app())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("burst_irf_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert not other.model.has_results()
        assert not other.model.files
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


def test_real_known_irf_worker_patterns_and_handoff_survive_all_views(tmp_path, monkeypatch):
    """The real worker extracts known photons; all host views retain arrays, gates and physical clocks."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app
    from chisurf.plugins.burst.burst_irf_bg.test.demo_data import build

    path = build(tmp_path / "measurement", seed=4)
    received = []
    app = create_app(
        mle_receiver=lambda patterns: received.append(copy.deepcopy(patterns)) or len(patterns)
    )
    try:
        clean = {
            "detectors": {
                "green": {"chs": [0], "micro_time_ranges": []},
                "red": {"chs": [1], "micro_time_ranges": []},
            },
            "windows": {},
            "tttr_reading": {
                "file_type": "SPC-130",
                "override_timing": False,
                "micro_time_binning": 1,
            },
            "apply_lut": False,
            "channel_luts": {},
            "channel_shifts": {},
        }
        app.controller.channel_definition.load_definition(clean)
        assert app.files_dropped([str(path)])
        app.controller.run()
        app.controller._future.result(timeout=120)
        app.controller.poll()
        assert app.model.has_results(), app.controller.status
        Driver(app, size=(1100, 720)).draw(3)
        patterns = copy.deepcopy(app.model.mle_patterns())
        rows = copy.deepcopy(app.model.results_rows())
        definition = copy.deepcopy(app.controller.channel_definition.model.get_settings())
        for size in ((1100, 720), (900, 650)):
            driver = Driver(app, size=size)
            for name in ("controls", "channels", "plot", "results"):
                app.irf_gui.docks.focus(name)
                driver.draw(3)
            assert app.model.results_rows() == rows
            assert app.controller.channel_definition.model.get_settings() == definition
            for name, values in patterns.items():
                for key, array in values.items():
                    np.testing.assert_array_equal(app.model.mle_patterns()[name][key], array)
            assert not app.controller.running
        assert app.controller.send_to_mle()
        for name, values in patterns.items():
            for key, array in values.items():
                np.testing.assert_array_equal(received[-1][name][key], array)
        app.controller.export_patterns(tmp_path / "patterns.npz")
        with np.load(tmp_path / "patterns.npz") as exported:
            for name, values in patterns.items():
                for key, array in values.items():
                    np.testing.assert_array_equal(exported[f"{name}/{key}"], array)
    finally:
        app.close()


def test_custom_callback_without_native_controller_draws_and_closes(tmp_path, monkeypatch):
    """External hosts retain their callback and guide rectangles without a native controller."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app

    calls = []
    app = create_app(on_compute=lambda: calls.append("compute"))
    try:
        assert app.controller is None
        Driver(app, size=(900, 650)).draw(3)
        assert "toolAction_run" in app.item_rects
        assert "patterns" not in app.item_rects
        app.irf_gui.on_compute()
        assert calls == ["compute"]
        assert not app.files_dropped(["measurement.spc"])
    finally:
        app.close()
