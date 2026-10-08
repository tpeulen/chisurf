"""Real child operations leave actions and wide photon tables usable."""

import shutil
import time
from pathlib import Path

from emtk.testing import Driver

ROOT = Path(__file__).resolve().parents[2]


def finish(tool):
    """Wait for the real worker and publish its result through the normal poll hook."""
    tool.job.future.result(timeout=30)
    tool.job.poll()


def test_completed_split_can_be_started_again_from_visible_io_action(tmp_path, monkeypatch):
    """A completed status cannot cover the Convert/Split action's pointer target."""
    from chisurf.plugins.tttr.tttr_splitter.gui.controller import SplitterController

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    source = tmp_path / "source.spc"
    shutil.copyfile(ROOT / "test/data/tttr/BH/132/BH_SPC132.spc", source)
    tool = SplitterController()
    tool._model.input_format = "SPC-130"
    tool._model.output_folder = str(tmp_path / "output")
    Path(tool._model.output_folder).mkdir()
    tool._model.photons_per_file_k = 50
    tool._model.keep_original = True
    try:
        tool.load_input(source)
        finish(tool)
        tool._run()
        finish(tool)
        assert tool.message.startswith("Complete:")
        assert len(list(Path(tool._model.output_folder).rglob("*.ptu"))) == 4
        calls = []
        original = tool.app.splitter_gui.on_run

        def run():
            """Record delivery while retaining the real scientific worker."""
            calls.append(time.monotonic())
            original()

        tool.app.splitter_gui.on_run = run
        drv = Driver(tool.app, size=(1100, 720))
        drv.draw(3)
        drv.click("run")
        assert len(calls) == 1
        if tool.job.future is not None:
            finish(tool)
        assert source.exists()
    finally:
        tool.app.close()


def test_real_burst_table_has_readable_headers_cells_and_sideways_navigation(tmp_path, monkeypatch):
    """A 66-column measured burst table keeps visible content and scrolls to later columns."""
    import numpy as np

    from chisurf.plugins.burst.bid_to_analysis import convert_bid_file
    from chisurf.plugins.burst.bid_to_analysis.test.test_container import INTERVALS, SPC
    from chisurf.plugins.core.pto_inspector.gui.app import PtoInspectorApp

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    source = tmp_path / "m000.spc"
    shutil.copyfile(SPC, source)
    bid = tmp_path / "m000.bid"
    np.savetxt(bid, INTERVALS, fmt="%d")
    convert_bid_file(bid, output_types={"pto"})
    app = PtoInspectorApp()
    try:
        app.model.set_filename(str(bid.with_suffix(".pto")))
        item = next(i for i in app.model.inspection.infos() if i.name == "bursts")
        app.model.select_uid(item.uid)
        app.refresh_payload()
        drv = Driver(app, size=(1100, 720))
        painter = drv.draw(3)
        assert "First Photon" in painter.strings
        assert any(str(value) in painter.strings for value in (100, 900, 5000))
        table = app.table.control
        assert table._hbar_box is not None
        before = table.first_column
        x, y, width, height = table._hbar_box
        drv.click((x + width * 0.9, y + height * 0.5))
        assert table.first_column > before
        assert len(app.payload["First Photon"]) == 3
    finally:
        app.close()


def test_real_split_working_stop_is_reachable_and_keeps_written_output(tmp_path, monkeypatch):
    """Stop remains usable while a real split is paused at its first progress boundary."""
    from threading import Event

    from chisurf.plugins.tttr.tttr_splitter.gui.controller import SplitterController
    from chisurf.plugins.tttr.tttr_splitter.gui.view_model import SplitterViewModel

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    source = tmp_path / "source.spc"
    shutil.copyfile(ROOT / "test/data/tttr/BH/132/BH_SPC132.spc", source)
    tool = SplitterController()
    tool._model.input_format = "SPC-130"
    tool._model.output_folder = str(tmp_path / "output")
    Path(tool._model.output_folder).mkdir()
    tool._model.photons_per_file_k = 50
    tool._model.keep_original = True
    entered, release = Event(), Event()
    original = SplitterViewModel.do_split

    def gated(model, progress_cb=None):
        """Pause only delivery timing while retaining actual output computation."""

        def progress(value):
            if progress_cb:
                progress_cb(value)
            if not entered.is_set():
                entered.set()
                assert release.wait(10)

        return original(model, progress_cb=progress)

    monkeypatch.setattr(SplitterViewModel, "do_split", gated)
    try:
        tool.load_input(source)
        finish(tool)
        tool._run()
        assert entered.wait(10)
        drv = Driver(tool.app, size=(1100, 720))
        painter = drv.draw(3)
        assert "Working…" in painter.strings
        drv.click("Stop")
        assert tool.job.cancelled.is_set()
        release.set()
        try:
            tool.job.future.result(timeout=30)
        except RuntimeError as exc:
            assert "stopped" in str(exc).lower()
        tool.job.poll()
        assert source.exists()
        assert list(Path(tool._model.output_folder).rglob("*.ptu"))
        assert "remain" in tool.message.lower()
    finally:
        release.set()
        tool.app.close()
