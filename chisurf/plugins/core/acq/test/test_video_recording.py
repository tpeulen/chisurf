"""Recording without OpenCV: the multi-page TIFF writer, adapter-independent sources,
and Record's Camera dock.

Everything here runs with OpenCV absent (it is optional, and not installed on the
MT200): a capture card with its own adapter records to TIFF, and the preview and
the dock do not touch it.
"""

import sys
import time

import numpy as np
import pytest
from PIL import Image

from chisurf.plugins.core.acq.gui.video_panel import TIFF_SUFFIXES, recorder_for
from chisurf.plugins.core.acq.live.video import (
    MatrixVisionSource,
    OpenCVRecorder,
    OpenCVSource,
    TiffRecorder,
    VideoFrame,
    source_for,
)


def _read_tiff_pages(path):
    """Every page of a multi-page TIFF as an array, through Pillow."""
    image = Image.open(path)
    pages = []
    while True:
        pages.append(np.asarray(image).copy())
        try:
            image.seek(len(pages))
        except EOFError:
            return pages


def test_tiff_round_trip_keeps_every_frame(tmp_path):
    path = tmp_path / "capture.tif"
    recorder = TiffRecorder(path)
    emitted = []
    for index, t in enumerate((1.0, 1.02, 1.31)):  # an irregular capture rate
        image = np.zeros((32, 40, 3), dtype=np.uint8)
        image[:, :, index % 3] = 40 * (index + 1)
        emitted.extend(recorder.write(VideoFrame(image, t)))
    recorder.close()
    assert emitted == [1.0, 1.02, 1.31]  # no frame dropped, none repeated
    pages = _read_tiff_pages(path)
    assert len(pages) == 3
    for index, page in enumerate(pages):
        assert page.shape == (32, 40, 3)
        assert page.dtype == np.uint8
        assert page[:, :, index % 3].mean() > 30
        assert page[:, :, (index + 1) % 3].mean() == 0


def test_tiff_recorder_never_overwrites_and_rejects_size_change(tmp_path):
    path = tmp_path / "capture.tif"
    recorder = TiffRecorder(path)
    recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 1.0))
    with pytest.raises(ValueError, match="dimensions changed"):
        recorder.write(VideoFrame(np.zeros((20, 40, 3), dtype=np.uint8), 2.0))
    recorder.close()
    with pytest.raises(FileExistsError):
        TiffRecorder(path).write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 3.0))
    assert len(_read_tiff_pages(path)) == 1  # unchanged


def test_tiff_recorder_refuses_backwards_time_and_unbounded_gap(tmp_path):
    recorder = TiffRecorder(tmp_path / "capture.tif")
    recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 1.0))
    with pytest.raises(ValueError, match="backwards"):
        recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 0.5))
    with pytest.raises(ValueError, match="gap exceeds 30 seconds"):
        recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 60.0))
    recorder.close()


def test_tiff_writes_after_close_are_refused(tmp_path):
    path = tmp_path / "capture.tif"
    recorder = TiffRecorder(path)
    recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 1.0))
    recorder.close()
    with pytest.raises(RuntimeError, match="already closed"):
        recorder.write(VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), 2.0))


def test_recorder_for_selects_by_suffix():
    from pathlib import Path

    assert isinstance(recorder_for(Path("capture.tif"), 30.0), TiffRecorder)
    assert isinstance(recorder_for(Path("capture.TIFF"), 30.0), TiffRecorder)
    assert isinstance(recorder_for(Path("capture.avi"), 30.0), OpenCVRecorder)
    assert TIFF_SUFFIXES == (".tif", ".tiff")


def test_panel_records_tiff_without_opencv(tmp_path, monkeypatch):
    """A full panel recording to TIFF, with ``import cv2`` made to fail."""
    from chisurf.plugins.core.acq.gui import video_panel

    class Source:
        def __init__(self, address):
            pass

        def open(self):
            pass

        def read(self):
            time.sleep(0.01)
            return VideoFrame(np.zeros((32, 40, 3), dtype=np.uint8), time.monotonic())

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "cv2", None)  # ``import cv2`` raises ImportError
    monkeypatch.setattr(video_panel, "source_for", lambda address: Source(address))
    panel = video_panel.VideoPanel()
    panel.output = str(tmp_path / "capture.tif")
    panel.connect()
    deadline = time.monotonic() + 3
    while not panel._connected and time.monotonic() < deadline:
        time.sleep(0.01)
    panel.record()
    deadline = time.monotonic() + 3
    while panel._count < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    panel.stop_recording()
    deadline = time.monotonic() + 3
    while panel._recorder is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    panel.close()
    panel._thread.join(3)
    assert panel._count >= 3
    assert len(_read_tiff_pages(tmp_path / "capture.tif")) == panel._count
    rows = (tmp_path / "capture.tif.timestamps.csv").read_text().splitlines()
    assert rows[0] == "frame,monotonic_seconds"
    assert len(rows) == panel._count + 4


def test_source_for_resolves_adapters_and_urls():
    assert isinstance(source_for("mv:0"), MatrixVisionSource)
    with pytest.raises(ValueError, match="mv:"):
        source_for("mv:first")
    # a camera index, a file, a URL: through OpenCV, and never opened here
    assert source_for("0").address == 0
    assert source_for("C:\\videos\\a.avi").address == "C:\\videos\\a.avi"
    assert source_for("https://example.org/stream.m3u8").address == \
        "https://example.org/stream.m3u8"
    assert isinstance(source_for("1"), OpenCVSource)


def test_source_for_takes_a_new_sdk_adapter_without_touching_the_panel():
    """Another capture card (Matrox, say) is one adapter plus one registry entry."""
    import inspect

    from chisurf.plugins.core.acq.gui import video_panel
    from chisurf.plugins.core.acq.live.video import SDK_ADAPTERS, VideoSource

    class MatroxSource:
        def __init__(self, device: int):
            self.device = device

        def open(self):
            pass

        def read(self):
            return None

        def close(self):
            pass

    def matrox(rest: str) -> VideoSource:
        if not rest.isdecimal():
            raise ValueError("Use matrox: followed by a device number.")
        return MatroxSource(int(rest))

    SDK_ADAPTERS["matrox"] = matrox
    try:
        source = source_for("matrox:2")
        assert isinstance(source, MatroxSource) and source.device == 2
        with pytest.raises(ValueError, match="matrox:"):
            source_for("matrox:dig")
    finally:
        del SDK_ADAPTERS["matrox"]
    # the panel stays adapter-agnostic: it resolves addresses, names no card
    assert "matrox" not in inspect.getsource(video_panel).lower()


def test_camera_dock_is_available_in_every_mode(tmp_path):
    """Record shows the Camera dock -- a dock, not a folded panel -- with the
    preview, whatever the photon source (the simulator here). Simple mode shows
    the video, the record buttons and the status; the settings are Advanced."""
    from chisurf.plugins.core.acq.gui.record_app import DOCKS, RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    assert ("video", "Camera", "main") in DOCKS
    app = RecordApp(RecordModel(output_dir=tmp_path, realtime=False))
    try:
        assert app.model.source_kind == "simulator"
        assert not app.model.advanced
        app.video.frame = VideoFrame(np.full((32, 40, 3), 100, dtype=np.uint8), 1.0)
        ui = Driver(app, (1500, 950))
        ui.draw(3)
        assert {"record", "stop_recording"} <= set(app.video_form.rects)
        assert "address" not in app.video_form.rects          # settings are Advanced
        assert app.form.rects.get("video_panel") is not None
        assert app.docks.windows["video"].visible
        assert app._video_texture is not None
        texture = app._video_texture
        app.video.frame = VideoFrame(np.full((32, 40, 3), 120, dtype=np.uint8), 2.0)
        ui.draw(1)
        assert app._video_texture is texture and texture.revision > 0
        app.model.advanced = True
        ui.draw(2)
        assert {"address", "connect", "output", "fps", "record", "stop_recording"} <= set(
            app.video_form.rects
        )
        # image mode keeps the camera
        app.model.mode = "image"
        ui.draw(2)
        assert app.docks.windows["video"].visible
    finally:
        app.close()
