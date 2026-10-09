"""Real TTTR conversion, provenance, native actions and lifecycle."""

import numpy as np
from emtk.testing import RecordingPainter

from ..gui.app import create_app
from .test_container import INTERVALS, SPC


def selection(tmp_path):
    (tmp_path / "m000.spc").write_bytes(SPC.read_bytes())
    path = tmp_path / "m000.bid"
    np.savetxt(path, INTERVALS, fmt="%d")
    return path


def test_native_conversion_outputs_and_original_provenance(tmp_path, caplog):
    from chisurf.core.datastore import row_count
    from chisurf.core.fio.pto import Measurement

    path = selection(tmp_path)
    raw = path.with_suffix(".spc").read_bytes()
    app = create_app()
    try:
        app.on_paths_dropped([path, path])
        assert len(app.rows) == 1
        app.output_types = {"pto", "bur", "sl5", "hdf5"}
        app.process()
        app.future.result(timeout=30)
        app.poll()
        assert app.rows[0]["status"] == "Done"
        folder = tmp_path / "m000"
        assert (folder / "bi4_bur" / "m000.bur").exists()
        assert list((folder / "sl5").glob("*.gz")) and list((folder / "hdf5").iterdir())
        with Measurement.open(path.with_suffix(".pto")) as measurement:
            assert row_count(measurement.get_store("bursts")) == len(INTERVALS)
            assert measurement.get_blob("m000.bid") == path.read_bytes()
            assert measurement.parents(measurement._resolve("bursts")) == [
                measurement._resolve("m000.bid")
            ]
        assert path.with_suffix(".spc").read_bytes() == raw
        for width, height in ((1200, 800), (800, 600)):
            app.draw(RecordingPainter(), 0, 0, width, height)
        assert not [record for record in caplog.records if record.levelno >= 40]
    finally:
        app.close()


def test_native_errors_dialogs_preferences_and_help(tmp_path):
    path = tmp_path / "missing.bid"
    np.savetxt(path, INTERVALS, fmt="%d")
    app = create_app()
    try:
        app.add_files([tmp_path])
        assert app.rows[0]["status"] == "Missing TTTR"
        app.process()
        app.future.result(timeout=10)
        app.poll()
        assert app.rows[0]["status"].startswith("Error:")
        for mode in ("files", "folder", "output"):
            app.browse(mode)
            assert app.dialog is not None
        app.dialog = None
        app.analysis_folder = str(tmp_path / "output")
        app.unique_folder = True
        app.output_types = {"bur", "pto"}
        preferences = app.export_settings()
        restored = create_app()
        try:
            restored.restore_settings(preferences)
            assert restored.export_settings() == preferences
        finally:
            restored.close()
        app.io.wall_clock = False
        app.io.delta_time = 0.01
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 800, 600)
        button = next(text for text in painter.texts if text[5] == "Process")
        app.hover(button[0] + button[2] / 2, button[1] + button[3] / 2)
        hovered = RecordingPainter()
        app.draw(hovered, 0, 0, 800, 600)
        app.io.delta_time = 0.6
        app.draw(hovered, 0, 0, 800, 600)
        assert "Convert each selection" in " ".join(hovered.strings)
        app.clear()
        assert not app.rows and not app.messages
    finally:
        app.close()


def test_output_destination_and_batch_backend(tmp_path):
    from .. import convert_bid_file, convert_many

    path = selection(tmp_path)
    output = tmp_path / "explicit"
    assert (
        convert_bid_file(path, analysis_folder=output, output_types={"bur"})
        == output / "bi4_bur" / "m000.bur"
    )
    results = convert_many([path], analysis_folder=tmp_path / "batch", output_types={"bur"})
    assert len(results) == 1 and results[0].exists()


def test_cancel_finishes_current_conversion_and_skips_remaining(tmp_path, monkeypatch):
    import threading

    from ..gui import app as module

    path = selection(tmp_path)
    second = tmp_path / "m000_second.bid"
    second.write_bytes(path.read_bytes())
    ready, release = threading.Event(), threading.Event()
    original = module.convert_bid_file

    def convert(*args, **kwargs):
        ready.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "convert_bid_file", convert)
    app = create_app()
    try:
        app.add_files([path, second])
        app.process()
        assert ready.wait(5)
        app.cancel.set()
        release.set()
        app.future.result(timeout=20)
        app.poll()
        assert [row["status"] for row in app.rows] == ["Done", "Cancelled"]
    finally:
        release.set()
        app.close()


def test_real_populated_native_conversion_without_qt(tmp_path):
    import os
    import subprocess
    import sys
    import textwrap

    path = selection(tmp_path)
    script = textwrap.dedent("""
        import importlib.abc,sys
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'}:raise ImportError(fullname)
        sys.meta_path.insert(0,Block())
        from chisurf.plugins.burst.bid_to_analysis.gui.app import create_app
        from emtk.testing import RecordingPainter
        app=create_app()
        try:
            app.add_files([sys.argv[1]]);app.process();app.future.result(timeout=20);app.poll()
            assert app.rows[0]['status']=='Done'
            for width,height in ((1200,800),(800,600)):
                painter=RecordingPainter();app.draw(painter,0,0,width,height)
                assert 'Done' in painter.strings
        finally:app.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(path)],
        capture_output=True,
        text=True,
        timeout=35,
        env=dict(
            os.environ,
            MPLCONFIGDIR="/private/tmp/chisurf-mpl",
            CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
