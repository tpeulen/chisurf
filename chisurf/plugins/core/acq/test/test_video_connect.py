"""Connecting the camera on a machine without OpenCV: the capture-card rescue.

The MT200 carries a Matrix Vision PCI frame grabber but no OpenCV, and its
saved panel state can still name an OpenCV camera index ("0") and an .avi
output from an older deploy -- both unusable there, and both invisible to a
simple-mode session that had no Connect button at all. These tests pin the
recovery: pressing Connect on a camera index falls back to the first
registered SDK capture card (updates the address and says so), a saved file or
URL is still refused without OpenCV, a video-file recording is refused with
the .tif remedy before it can kill the capture, and the simple-mode view
exposes Connect/Disconnect.

Everything here runs with ``import cv2`` made to fail, exactly the MT200's
condition: no test may depend on OpenCV being installed.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui import video_panel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
from chisurf.plugins.core.acq.live import video as video_module
from chisurf.plugins.core.acq.live.video import (
    OpenCVSource,
    OpenCVUnavailable,
    VideoFrame,
    _opencv,
    source_for,
)

HERE = Path(__file__).resolve().parent.parent


class CardSource:
    """A fake SDK capture-card source that delivers frames when opened."""

    def __init__(self, device: int):
        self.device = device
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True

    def read(self):
        time.sleep(0.01)
        return VideoFrame(np.zeros((8, 10, 3), dtype=np.uint8), time.monotonic())

    def close(self):
        self.closed = True


@pytest.fixture
def no_opencv(monkeypatch):
    """Make ``import cv2`` fail, as on the MT200."""
    monkeypatch.setitem(sys.modules, "cv2", None)


@pytest.fixture
def card_adapter(monkeypatch):
    """One registered SDK capture-card adapter, standing in for ``mv``."""
    monkeypatch.setattr(video_module, "SDK_ADAPTERS",
                        {"card": lambda rest: CardSource(int(rest))})


def _wait_connected(panel, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not panel._connected and time.monotonic() < deadline:
        time.sleep(0.01)
    return panel._connected


def test_camera_index_does_not_fall_back_to_a_different_card(no_opencv, card_adapter):
    panel = VideoPanel()
    panel.address = "0"
    panel.connect()
    panel._thread.join(3)
    assert not panel._connected
    assert "OpenCV" in panel.status and "unavailable" in panel.status.lower()
    assert panel.address == "0"
    assert isinstance(panel._source, OpenCVSource)


def test_connect_without_a_card_still_names_the_missing_package(no_opencv, monkeypatch):
    """No registered card: the honest OpenCV error, address untouched."""
    monkeypatch.setattr(video_module, "SDK_ADAPTERS", {})
    panel = VideoPanel()
    panel.address = "0"
    panel.connect()
    panel._thread.join(3)
    assert not panel._thread.is_alive()
    assert not panel._connected
    assert "OpenCV" in panel.status
    assert panel.address == "0"


def test_connect_keeps_files_and_urls_on_opencv(no_opencv):
    """A file or URL asked for OpenCV by name: no card is substituted."""
    address = "https://example.org/stream.m3u8"
    panel = VideoPanel()
    panel.address = address
    panel.connect()
    panel._thread.join(3)
    assert "OpenCV" in panel.status
    assert panel.address == address
    assert not panel._connected



def test_record_refuses_video_files_without_opencv_and_keeps_capture(
        no_opencv, card_adapter, tmp_path):
    panel = VideoPanel()
    panel.address = "card:0"
    panel.output = str(tmp_path / "capture.avi")
    panel.connect()
    try:
        assert _wait_connected(panel)
        panel.record()
        assert panel._recorder is None
        assert ".tif" in panel.status and "OpenCV" in panel.status
        assert panel._connected and panel._thread.is_alive()
        assert not list(tmp_path.iterdir())
    finally:
        panel.close()
        panel._thread.join(3)


def test_opencv_unavailable_is_a_distinct_but_catchable_error(no_opencv):
    """The rescue (and every existing handler) can tell the failure apart
    while old ``except RuntimeError`` code keeps working."""
    with pytest.raises(OpenCVUnavailable):
        _opencv()
    with pytest.raises(RuntimeError):
        _opencv()


def test_a_failing_recorder_ends_the_recording_and_keeps_the_preview(monkeypatch, tmp_path):
    """A writer that cannot keep going (the MT200's tttrlib predating imappend,
    a full disk) must end the recording with a clear status -- never kill the
    live capture the user is watching."""
    from chisurf.plugins.core.acq.gui import video_panel as panel_module

    class FragileRecorder:
        def __init__(self):
            self.path = Path(panel_output)
            self.calls = 0
            self.closed = False

        def write(self, frame):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("this writer's wheel is too old")
            return [frame.timestamp_s]

        def close(self):
            self.closed = True

    class Source:
        def __init__(self, address):
            pass

        def open(self):
            pass

        def read(self):
            time.sleep(0.01)
            return VideoFrame(np.full((8, 10, 3), 7, dtype=np.uint8), time.monotonic())

        def close(self):
            pass

    monkeypatch.setattr(panel_module, "source_for", lambda address: Source(address))
    panel_output = str(tmp_path / "acceptance.tif")
    monkeypatch.setattr(panel_module, "recorder_for",
                        lambda path, fps: FragileRecorder())
    panel = VideoPanel()
    panel.output = panel_output
    panel.connect()
    try:
        assert _wait_connected(panel)
        panel.record()
        deadline = time.monotonic() + 3
        while "failed" not in panel.status and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "failed" in panel.status
        assert "this writer's wheel is too old" in panel.status
        assert panel._recorder is None          # recording ended, sidecar closed
        assert panel._connected and panel._thread.is_alive()
        first = panel.frame
        deadline = time.monotonic() + 3
        while panel.frame is first and time.monotonic() < deadline:
            time.sleep(0.01)
        assert panel.frame is not first         # frames keep arriving
    finally:
        panel.close()
        panel._thread.join(3)


def test_simple_mode_exposes_connect_and_disconnect():
    """The saved MT200 session runs simple mode; the tour tells the user to
    press Connect, so the simple view must carry the connect buttons -- and
    every simple action must resolve on the panel."""
    spec = json.loads((HERE / "gui" / "video.view.json").read_text(encoding="utf-8"))
    actions = [button["action"] for section in spec["simple_sections"]
               for button in section.get("buttons", [])]
    assert not {"connect", "disconnect", "record", "stop_recording"} & set(actions)
    panel = VideoPanel()
    for action in actions:
        assert callable(getattr(panel, action)), action
