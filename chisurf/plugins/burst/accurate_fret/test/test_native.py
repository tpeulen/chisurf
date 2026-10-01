"""Native calibration, full scientific views and setup/session handoffs."""

import numpy as np
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.accurate_fret.gui.app import create_app

from .test_accurate_fret_plugin import ALPHA, BETA, DELTA, GAMMA, TAU_D0, _simulate


def columns():
    dd, da, aa, tau = _simulate(n=100)
    return {
        "Green Count Rate (KHz)": dd,
        "Red Count Rate (KHz)": da,
        "S delayed yellow (kHz)": aa,
        "Tau (green)": tau,
    }


def test_native_source_calibration_numerics_views_and_export(tmp_path, caplog):
    class Source:
        def __init__(self):
            self.calibration = None

        def get_burst_columns(self):
            return columns()

        def apply_fret_calibration(self, calibration):
            self.calibration = calibration

    source = Source()
    app = create_app(ndx_source=source)
    app.model.n_bootstrap = 0
    app.model.donor_lifetime = TAU_D0
    try:
        app.controller.from_ndx()
        assert app.model.can_run() is None
        app.controller.run()
        app.controller._future.result(timeout=20)
        app.controller.poll()
        assert app.model.result is not None
        import pytest

        assert app.model.result.factors["gamma"] == pytest.approx(GAMMA, rel=0.15)
        assert app.model.result.factors["alpha"] == pytest.approx(ALPHA, rel=0.2)
        assert (
            app.model.es_series() and app.model.e_tau_series() and app.model.efficiency_histogram()
        )
        assert "static FRET line" in [entry["name"] for entry in app.model.e_tau_series()]
        app.controller.to_ndx()
        assert source.calibration is app.model.result.calibration.calibration
        app.controller.register()
        output = tmp_path / "accurate.csv"
        app.controller.export(output)
        assert output.exists() and "gamma" in output.read_text()
        for key in ("es", "tau", "hist"):
            app.accurate_gui.docks.focus(key)
            app.draw(RecordingPainter(), 0.0, 0.0, 1200.0, 800.0)
        assert not [record for record in caplog.records if record.levelno >= 40]
        assert app.model.factor_rows() and app.model.population_rows()
    finally:
        app.close()


def test_native_setup_store_and_reopen_preserves_calibration(tmp_path):
    from chisurf.core.fluorescence.fret.calibration import SETUP_CALIBRATION_FIELD
    from chisurf.core.setup_channel_definition import ChannelDefinition

    setup = ChannelDefinition(
        {
            "detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}, "yellow": {"chs": [2]}},
            "windows": {},
        },
        file_path=tmp_path / "setups.json",
    )
    setup.save_setup("Instrument")

    class Source:
        def get_burst_columns(self):
            return columns()

    source = Source()
    app = create_app(ndx_source=source, setup_model=setup)
    app.model.n_bootstrap = 0
    try:
        app.controller.apply_setup(setup.get_settings())
        assert app.model.setup_name == "Instrument"
        app.controller.from_ndx()
        app.controller.run()
        app.controller._future.result(timeout=20)
        app.controller.poll()
        app.controller.store_setup()
        reopened = ChannelDefinition(file_path=tmp_path / "setups.json")
        reopened.refresh_setups()
        reopened.select_setup("Instrument")
        stored = reopened.data[SETUP_CALIBRATION_FIELD]
        assert np.isclose(stored["values"]["gamma"], app.model.result.factors["gamma"])
        assert reopened.data["detectors"]["green"]["chs"] == [0]
    finally:
        app.close()


def test_native_discovery_registry_is_weak_and_ndx_capable():
    import gc
    import weakref

    from chisurf.emtk.session_sources import register_source, sources, unregister_source

    class Source:
        def get_burst_columns(self):
            return columns()

    source = Source()
    register_source("ndx", source)
    app = create_app()
    try:
        app.controller.from_ndx()
        assert app.model._columns
        unregister_source("ndx", source)
        assert source not in sources("ndx")
        register_source("temporary", source)
        reference = weakref.ref(source)
        del source
        gc.collect()
        assert reference() is None and sources("temporary") == []
    finally:
        app.close()


def test_native_cancel_keeps_previous_result(monkeypatch):
    import threading
    from concurrent.futures import CancelledError

    from chisurf.plugins.burst.accurate_fret.gui.view_model import AccurateFretViewModel

    app = create_app()
    app.model._columns = columns()
    app.model._map_columns()
    marker = object()
    app.model._result = marker
    ready, release = threading.Event(), threading.Event()

    def compute(snapshot, progress=None):
        ready.set()
        assert release.wait(5)
        progress(1.0, "Done")
        return True

    monkeypatch.setattr(AccurateFretViewModel, "compute", compute)
    try:
        app.controller.run()
        assert ready.wait(5)
        app.controller.stop()
        release.set()
        try:
            app.controller._future.result(timeout=5)
        except CancelledError:
            pass
        app.controller.poll()
        assert app.model.result is marker and not app.controller.running
    finally:
        release.set()
        app.close()


def test_native_file_drop_load_calibrate_and_preferences(tmp_path):
    source = tmp_path / "bursts.npz"
    np.savez(source, **columns())
    app = create_app()
    app.model.n_bootstrap = 0
    try:
        app.on_paths_dropped([str(source)])
        app.controller._future.result(timeout=20)
        app.controller.poll()
        assert app.model.filename == str(source) and app.model.can_run() is None
        app.controller.run()
        app.controller._future.result(timeout=20)
        app.controller.poll()
        assert app.model.result is not None
        app.model.setup_name = "Saved instrument"
        settings = app.export_settings()
        restored = create_app()
        try:
            restored.restore_settings(settings)
            assert restored.model.n_bootstrap == 0
            assert restored.controller.channel_definition.model.current_name == "Saved instrument"
        finally:
            restored.close()
    finally:
        app.close()


def test_populated_native_workflow_with_qt_imports_blocked(tmp_path):
    import os
    import subprocess
    import sys
    import textwrap

    source = tmp_path / "bursts.npz"
    np.savez(source, **columns())
    script = textwrap.dedent("""
        import importlib.abc,sys
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'}:
                    raise ImportError(fullname)
        sys.meta_path.insert(0,Block())
        from chisurf.plugins.burst.accurate_fret.gui.app import create_app
        from emtk.testing import RecordingPainter
        app=create_app();app.model.n_bootstrap=0
        try:
            app.controller.load(sys.argv[1])
            app.controller._future.result(timeout=20);app.controller.poll()
            app.controller.run()
            app.controller._future.result(timeout=20);app.controller.poll()
            assert app.model.result is not None
            for key in ('es','tau','hist'):
                app.accurate_gui.docks.focus(key)
                for width,height in ((1200,800),(800,600)):
                    painter=RecordingPainter();app.draw(painter,0,0,width,height)
                    assert painter.strings
            assert not any(name.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'} for name in sys.modules)
        finally:app.close()
    """)
    completed = subprocess.run(
        [sys.executable, "-c", script, str(source)],
        capture_output=True,
        text=True,
        timeout=40,
        env=dict(
            os.environ,
            MPLCONFIGDIR="/private/tmp/chisurf-mpl",
            CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        ),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_native_catalogues_use_real_optical_database(tmp_path):
    from chisurf.plugins.core.lightpath_simulator.core.workflow import save_lightpath
    from chisurf.plugins.core.lightpath_simulator.tests.test_headless import (
        _build_probe_db,
        _dye_detector_graph,
    )

    database = tmp_path / "optics.db"
    dye, detector = _build_probe_db(database, "absorption")
    graph = _dye_detector_graph(dye, detector)
    save_lightpath(graph, name="Accurate prior", db_path=str(database))
    app = create_app(db_path=database)
    try:
        app.controller._start("dyes")
        app.controller._future.result(timeout=20)
        app.controller.poll()
        assert app.model._dyes and len(app.model.dye_names()) > 1
        app.controller._start("lightpaths")
        app.controller._future.result(timeout=20)
        app.controller.poll()
        assert "Accurate prior" in app.model.lightpath_names()
    finally:
        app.close()


def test_native_calibration_action_has_hover_help():
    app = create_app()
    try:
        app.io.wall_clock = False
        app.io.delta_time = 0.01
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 800, 600)
        button = next(text for text in painter.texts if text[5] == "Calibrate")
        app.hover(button[0] + button[2] / 2, button[1] + button[3] / 2)
        hovered = RecordingPainter()
        app.draw(hovered, 0, 0, 800, 600)
        app.io.delta_time = 0.6
        app.draw(hovered, 0, 0, 800, 600)
        assert "Find burst classes and correction factors" in " ".join(hovered.strings)
    finally:
        app.close()
