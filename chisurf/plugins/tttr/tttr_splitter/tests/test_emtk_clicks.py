"""Convert / Split and Start batch pressed with the pointer on a real TTTR file."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from emtk.testing import Driver

ROOT = Path(__file__).resolve().parents[5]
PTU = ROOT / "test" / "data" / "clsm" / "Leica_SP5.ptu"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="sample PTU not available")


def _finish(tool):
    tool.job.future.result(timeout=120)
    tool.job.poll()


def _tool(tmp_path, monkeypatch):
    import tttrlib

    from chisurf.plugins.tttr.tttr_splitter.gui.controller import SplitterController

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    source = tmp_path / "in" / "sample.ptu"
    source.parent.mkdir()
    shutil.copyfile(PTU, source)
    n = len(tttrlib.TTTR(str(source)))
    tool = SplitterController()
    out = tmp_path / "out"
    out.mkdir()
    tool._model.output_folder = str(out)
    tool._model.output_format = "PTU"
    # at least 100 k photons per file (the bound of the Qt spec), about three chunks
    tool._model.photons_per_file_k = max(100, n // 3000)
    return tool, source, out, n


def test_convert_split_button_writes_chunks_that_keep_every_photon(tmp_path, monkeypatch):
    import tttrlib

    tool, source, out, n = _tool(tmp_path, monkeypatch)
    try:
        tool.load_input(source)
        _finish(tool)
        drv = Driver(tool.app, size=(1100, 720))
        drv.draw(3)
        drv.click("run")
        _finish(tool)
        drv.draw(2)
        assert tool.message.startswith("Complete:"), tool.message
        files = sorted(out.rglob("*.ptu"))
        assert len(files) >= 2
        assert sum(len(tttrlib.TTTR(str(f))) for f in files) == n
    finally:
        tool.app.close()


def test_start_batch_button_splits_every_queued_file(tmp_path, monkeypatch):
    tool, source, out, n = _tool(tmp_path, monkeypatch)
    try:
        tool._queue_batch_paths([source])
        assert tool._model.batch_files == [str(source)]
        tool._model.batch_use_parent = False
        drv = Driver(tool.app, size=(1100, 720))
        drv.draw(3)
        drv.click("batch_run")
        _finish(tool)
        drv.draw(2)
        assert tool.message == "Processed 1 file(s).", tool.message
        assert len(sorted(out.rglob("*.ptu"))) >= 2
    finally:
        tool.app.close()


def test_photons_per_file_minus_button_stops_at_the_100k_minimum(tmp_path, monkeypatch):
    """The Qt spin box minimum (100 k) bounds the step buttons: pressing minus past it stays at it."""
    tool, _source, _out, _n = _tool(tmp_path, monkeypatch)
    try:
        tool._model.photons_per_file_k = 300
        drv = Driver(tool.app, size=(1100, 720))
        drv.draw(3)
        x, y, w, h = next(t[:4] for t in drv.painter.texts if t[5] == "Photons per file [k]")
        seen = []
        for _ in range(4):
            drv.click((x - 454.0, y + h / 2))  # the minus button, left of the field
            seen.append(tool._model.photons_per_file_k)
        assert seen == [200, 100, 100, 100]
    finally:
        tool.app.close()
