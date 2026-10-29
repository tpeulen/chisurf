"""Video preview and recording controller for Record's optional video panel."""

from __future__ import annotations

import csv
import subprocess
import sys
import threading
import time
from pathlib import Path

from chisurf.plugins.core.acq.live.video import (
    OpenCVRecorder,
    TiffRecorder,
    source_for,
)

#: File suffixes recorded as multi-page TIFF; every other suffix is a video file
#: written through OpenCV.
TIFF_SUFFIXES = (".tif", ".tiff")


def recorder_for(path: Path, fps: float):
    """A recorder for *path*: a multi-page TIFF needs no image library, anything
    else is a constant-rate video file through the optional OpenCV package."""
    if path.suffix.lower() in TIFF_SUFFIXES:
        return TiffRecorder(path)
    return OpenCVRecorder(path, fps=fps)


class VideoPanel:
    """Read a selected source on a worker thread, optionally recording its frames.

    The panel knows no particular camera or capture card: :func:`source_for`
    resolves the address to an adapter (Matrix Vision, OpenCV, ...), and the
    recorders take the adapter's frames.
    """

    def __init__(self):
        self.address = "0"
        self.output = "capture.tif"
        self.fps = 30.0
        self.display_gain = 1.0
        self.status = "Video disconnected."
        self.frame = None
        self._source = None
        self._thread = None
        self._finalizer = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._recorder = None
        self._timestamps = None
        self._csv = None
        self._count = 0
        self.photon_context = lambda: ""
        self._photon_path = ""
        self._connected = False
        self.discovered = "No discovery performed."

    def discover(self):
        """List OS-reported video devices without opening any of them."""
        def work():
            try:
                if sys.platform == "win32":
                    command = ["powershell", "-NoProfile", "-Command",
                               "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in "
                               "@('Camera','Image','FrameGrabber') } | Select-Object -ExpandProperty FriendlyName"]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=10,
                                            check=True).stdout.strip()
                elif sys.platform == "darwin":
                    result = subprocess.run(["system_profiler", "SPCameraDataType"],
                                            capture_output=True, text=True, timeout=10,
                                            check=True).stdout.strip()
                else:
                    result = ", ".join(str(p) for p in sorted(Path("/dev").glob("video*")))
                self.discovered = result or "No camera devices reported by the operating system."
                if "MATRIX VISION" in result.upper():
                    self.discovered += "\nMatrix Vision: enter mv:0 for the first SDK device."
            except (OSError, subprocess.SubprocessError) as exc:
                self.discovered = f"Device discovery failed: {exc}"

        self.discovered = "Looking for video devices…"
        threading.Thread(target=work, daemon=True, name="video-discovery").start()

    def connect(self):
        if self._thread is not None and self._thread.is_alive():
            return
        address = self.address.strip()
        if not address:
            self.status = "Choose a video source."
            return
        try:
            self._source = source_for(address)
        except ValueError as exc:
            self.status = f"Video: {exc}"
            return
        self._stop.clear()
        self.status = "Connecting video…"
        self._thread = threading.Thread(target=self._run, daemon=True, name="video-capture")
        self._thread.start()

    def use_matrix_vision(self):
        """Select the first Matrix Vision SDK source without opening it."""
        if not self._connected:
            self.address = "mv:0"
            self.status = "Matrix Vision selected; choose Connect."

    def _run(self):
        try:
            self._source.open()
            if self._stop.is_set():
                return
            self._connected = True
            self.status = "Video connected."
            next_frame = time.monotonic()
            while not self._stop.is_set():
                interval = getattr(self._source, "frame_interval_s", 0.0)
                if interval and self._stop.wait(max(0.0, next_frame - time.monotonic())):
                    break
                frame = self._source.read()
                if frame is None:
                    self.status = "Video source ended or stopped delivering frames."
                    break
                if interval:
                    next_frame = max(next_frame + interval, time.monotonic())
                with self._lock:
                    self.frame = frame
                    if self._recorder is not None:
                        emitted = self._recorder.write(frame)
                        if emitted and self._timestamps is None:
                            self._open_timestamps()
                        if emitted:
                            current_photon_path = self.photon_context()
                            if current_photon_path != self._photon_path:
                                self._csv.writerow((f"photon_run_at_frame_{self._count}",
                                                    current_photon_path))
                                self._photon_path = current_photon_path
                            for timestamp in emitted:
                                self._csv.writerow((self._count, f"{timestamp:.9f}"))
                                self._count += 1
        except Exception as exc:
            self.status = f"Video: {exc}"
        finally:
            self._connected = False
            with self._lock:
                self._end_recording()
            self._source.close()
            if self._stop.is_set():
                self.frame = None
                self.status = "Video disconnected."

    def record(self):
        if not self._connected:
            self.status = "Connect a video source before recording."
            return
        if not self._lock.acquire(blocking=False):
            self.status = "Video is busy; try recording again."
            return
        try:
            if self._recorder is not None:
                return
            path = Path(self.output).expanduser()
            sidecar = path.with_name(path.name + ".timestamps.csv")
            try:
                if path.exists():
                    raise FileExistsError(path)
                if sidecar.exists():
                    raise FileExistsError(sidecar)
                recorder = recorder_for(path, float(self.fps))
            except Exception as exc:
                self.status = f"Video recording: {exc}"
                return
            self._recorder = recorder
            self._photon_path = self.photon_context()
            self._count = 0
            self.status = f"Waiting for first video frame for {path}."
        finally:
            self._lock.release()

    def _open_timestamps(self):
        path = self._recorder.path
        sidecar = path.with_name(path.name + ".timestamps.csv")
        stamps = sidecar.open("x", encoding="utf-8", newline="")
        writer = csv.writer(stamps)
        writer.writerow(("frame", "monotonic_seconds"))
        writer.writerow(("clock_anchor_unix_seconds", f"{time.time():.9f}"))
        writer.writerow(("clock_anchor_monotonic_seconds", f"{time.monotonic():.9f}"))
        writer.writerow(("associated_photon_ptu", self._photon_path))
        self._timestamps, self._csv = stamps, writer
        self.status = f"Recording video to {path}."

    def _end_recording(self):
        if self._recorder is not None:
            self._recorder.close()
            if self._timestamps is not None:
                self._timestamps.close()
            self._recorder = self._timestamps = self._csv = None

    def stop_recording(self):
        if self._recorder is not None and (self._finalizer is None or not self._finalizer.is_alive()):
            self.status = "Stopping video recording…"
            def finish():
                with self._lock:
                    self._end_recording()
                    self.status = f"Video recording stopped ({self._count} frames)."

            self._finalizer = threading.Thread(target=finish, daemon=True, name="video-finalize")
            self._finalizer.start()

    def disconnect(self):
        self._stop.set()
        self.stop_recording()
        if self._thread is not None and self._thread.is_alive():
            self.status = "Disconnecting video…"
        else:
            self.frame = None
            self.status = "Video disconnected."

    def close(self):
        """Disconnect and allow a bounded time for the recording to finalize."""
        self.disconnect()
        if self._finalizer is not None:
            self._finalizer.join(timeout=2.0)
            if self._finalizer.is_alive():
                self.status = "Video finalization is still pending; output may be incomplete."
