"""Video source and recording primitives for acquisition.

The frame contract is independent of a particular camera or capture card.  A source
returns RGB uint8 frames and a monotonic timestamp; adapters may implement this
contract for USB cameras, capture cards, files, or other transports.  The optional
OpenCV adapter does not enumerate by opening arbitrary devices: the caller chooses
the device identifier or file to open explicitly.  Recording to a multi-page TIFF
(:class:`TiffRecorder`) goes through the image I/O seam (the TTTR library's
libtiff), so a capture card with its own adapter (Matrix Vision) records with no
OpenCV installed.
"""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

MAX_RECORDING_GAP_S = 30.0


def _validated_rgb(image) -> np.ndarray:
    """A contiguous RGB uint8 frame, or ``ValueError`` (recorders share the check)."""
    image = np.asarray(image)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Video frames must be three-channel uint8 RGB images.")
    if not image.shape[0] or not image.shape[1]:
        raise ValueError("Video frames must not be empty.")
    return np.ascontiguousarray(image)


def _checked_timestamp(previous: float | None, timestamp: float) -> None:
    """Timestamps are finite and move forward, and a gap stays bounded."""
    if not np.isfinite(timestamp):
        raise ValueError("Video frame timestamp must be finite.")
    if previous is not None:
        if timestamp < previous:
            raise ValueError("Video frame timestamps must not move backwards.")
        if timestamp - previous > MAX_RECORDING_GAP_S:
            raise ValueError(f"Video capture gap exceeds {MAX_RECORDING_GAP_S:.0f} seconds; "
                             "recording stopped.")


@dataclass(frozen=True)
class VideoFrame:
    """An RGB image and its host monotonic capture time, in seconds."""

    image: np.ndarray
    timestamp_s: float


class VideoSource(Protocol):
    """An explicitly opened video source; reading returns ``None`` at end of stream."""

    def open(self) -> None: ...

    def read(self) -> VideoFrame | None: ...

    def close(self) -> None: ...


def _opencv():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Video capture requires the optional OpenCV Python package.") from exc
    return cv2


class MatrixVisionSource:
    """Capture monochrome frames through an installed mvIMPACT Acquire driver.

    The SDK owns the buffers until the request is unlocked, so each frame is
    copied before returning. The adapter is selected as ``mv:0``, ``mv:1``, etc.
    """

    def __init__(self, index: int = 0, *, library=None):
        self.index = int(index)
        self._library = library
        self._device = ctypes.c_int(-1)
        self._driver = ctypes.c_int(-1)
        self._initialized = False
        self._opened = False
        self.frame_interval_s = 0.0

    def _call(self, name, *args):
        result = getattr(self._library, name)(*args)
        if result != 0:
            raise RuntimeError(f"Matrix Vision {name} failed ({result}).")

    def open(self):
        if self._initialized:
            raise RuntimeError("Video source is already open.")
        if self._library is None:
            if sys.platform != "win32":
                raise RuntimeError("Matrix Vision capture requires its Windows SDK.")
            try:
                self._library = ctypes.WinDLL("mvDeviceManager.dll")
            except OSError as exc:
                raise RuntimeError("Matrix Vision mvIMPACT Acquire driver is unavailable.") from exc
        try:
            manager = ctypes.c_int()
            self._call("DMR_Init", ctypes.byref(manager))
            self._initialized = True
            count = ctypes.c_uint()
            self._call("DMR_GetDeviceCount", ctypes.byref(count))
            if self.index < 0 or self.index >= count.value:
                raise RuntimeError(f"Matrix Vision device {self.index} is unavailable ({count.value} found).")
            self._call("DMR_GetDevice", ctypes.byref(self._device), 1, ctypes.c_char_p(b"*"),
                       self.index, ctypes.c_char(b"*"))
            self._call("DMR_OpenDevice", self._device, ctypes.byref(self._driver))
            self._opened = True
        except Exception:
            self.close()
            raise

    def read(self):
        if not self._opened:
            raise RuntimeError("Video source is not open.")
        request = ctypes.c_int(-1)
        self._call("DMR_ImageRequestSingle", self._driver, 0, None)
        self._call("DMR_ImageRequestWaitFor", self._driver, 2000, 0, ctypes.byref(request))
        try:
            result = (ctypes.c_int * 2)()
            self._call("DMR_GetImageRequestResultEx", self._driver, request, result,
                       ctypes.c_size_t(ctypes.sizeof(result)), 0, 0)
            if result[0] != 0:
                raise RuntimeError(f"Matrix Vision capture failed ({result[0]}).")
            bpp, channels, height, width, size, fmt = (ctypes.c_int() for _ in range(6))
            pointer = ctypes.c_void_p()
            self._call("DMR_GetImageRequestBufferData", self._driver, request,
                       ctypes.byref(bpp), ctypes.byref(channels), ctypes.byref(height),
                       ctypes.byref(width), ctypes.byref(size), ctypes.byref(fmt),
                       ctypes.byref(pointer))
            if (fmt.value != 1 or bpp.value != 1 or channels.value != 1
                    or width.value <= 0 or height.value <= 0
                    or size.value != width.value * height.value or not pointer.value):
                raise RuntimeError("Matrix Vision source returned an unsupported image format.")
            pixels = np.frombuffer(ctypes.string_at(pointer, size.value), dtype=np.uint8)
            image = np.repeat(pixels.reshape(height.value, width.value, 1), 3, axis=2)
            return VideoFrame(image, time.monotonic())
        finally:
            self._call("DMR_ImageRequestUnlock", self._driver, request)

    def close(self):
        if self._opened:
            self._library.DMR_CloseDevice(self._driver, self._device)
            self._opened = False
        if self._initialized:
            self._library.DMR_Close()
            self._initialized = False


def _matrix_vision(rest: str) -> VideoSource:
    if not rest.isdecimal():
        raise ValueError("Use mv: followed by a Matrix Vision device number.")
    return MatrixVisionSource(int(rest))


#: Capture-card SDK adapters by the address prefix that selects them (``mv:0`` is
#: the first Matrix Vision SDK device). Another card -- Matrox, for example -- is
#: one :class:`VideoSource` adapter class plus one entry here; the panel, the
#: preview and the recorders stay untouched. Addresses without a known prefix are
#: camera indices, files or URLs, so a drive letter or ``https://`` is never
#: caught by this table.
SDK_ADAPTERS: dict[str, Callable[[str], VideoSource]] = {"mv": _matrix_vision}


def source_for(address: str) -> VideoSource:
    """The video source an address names: an SDK capture card for a registered
    ``prefix:`` address, else a camera index, video file or stream URL through
    OpenCV."""
    prefix, sep, rest = address.partition(":")
    factory = SDK_ADAPTERS.get(prefix.lower()) if sep else None
    if factory is not None:
        return factory(rest)
    return OpenCVSource(int(address) if address.isdecimal() else address)


class OpenCVSource:
    """A selected camera index, capture device, video file, or network stream.

    ``backend`` is an optional OpenCV backend identifier, useful when a device
    requires DirectShow, Media Foundation, V4L2, or AVFoundation. No device is
    opened until :meth:`open` is called.
    """

    def __init__(self, address: int | str, *, backend: int | None = None):
        self.address = address
        self.backend = backend
        self._capture = None
        self.frame_interval_s = 0.0

    def open(self) -> None:
        if self._capture is not None:
            raise RuntimeError("Video source is already open.")
        cv2 = _opencv()
        cap = (cv2.VideoCapture(self.address) if self.backend is None
               else cv2.VideoCapture(self.address, self.backend))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Could not open video source {self.address!r}.")
        self._capture = cap
        if isinstance(self.address, str) and Path(self.address).is_file():
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if np.isfinite(fps) and fps > 0:
                self.frame_interval_s = 1.0 / fps

    def read(self) -> VideoFrame | None:
        if self._capture is None:
            raise RuntimeError("Video source is not open.")
        ok, image = self._capture.read()
        if not ok or image is None:
            return None
        image = np.asarray(image)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Video source must provide three-channel uint8 frames.")
        return VideoFrame(np.ascontiguousarray(image[:, :, ::-1]), time.monotonic())

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


class OpenCVRecorder:
    """Write RGB frames to a new video file at a specified constant frame rate.

    Frames are resampled by capture time: early frames are dropped and the
    preceding frame is repeated across missing output slots. :meth:`write`
    returns each emitted frame's original capture time for a timing sidecar.
    The output must not already exist.
    """

    def __init__(self, path: str | Path, *, fps: float, codec: str = "MJPG"):
        if fps <= 0 or len(codec) != 4:
            raise ValueError("Video recording needs a positive frame rate and four-character codec.")
        self.path = Path(path)
        self.fps = float(fps)
        self.codec = codec
        self._writer = None
        self._shape = None
        self._first_time = None
        self._previous_image = None
        self._previous_time = None
        self._output_index = -1

    def write(self, frame: VideoFrame) -> list[float]:
        image = _validated_rgb(frame.image)
        if self._writer is None:
            if self.path.exists():
                raise FileExistsError(self.path)
            cv2 = _opencv()
            writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*self.codec),
                                     self.fps, (image.shape[1], image.shape[0]))
            if not writer.isOpened():
                writer.release()
                raise RuntimeError(f"Could not create video recording {self.path}.")
            self._writer, self._shape = writer, image.shape
        if image.shape != self._shape:
            raise ValueError("Video frame dimensions changed during recording.")
        timestamp = float(frame.timestamp_s)
        _checked_timestamp(self._previous_time, timestamp)
        bgr = np.ascontiguousarray(image[:, :, ::-1])
        if self._first_time is None:
            self._first_time = timestamp
        index = int((timestamp - self._first_time) * self.fps + 0.5)
        emitted = []
        if self._previous_image is None:
            self._writer.write(bgr)
            emitted.append(timestamp)
            self._output_index = 0
        elif index > self._output_index:
            while self._output_index + 1 < index:
                self._writer.write(self._previous_image)
                emitted.append(self._previous_time)
                self._output_index += 1
            self._writer.write(bgr)
            emitted.append(timestamp)
            self._output_index += 1
        self._previous_image = bgr
        self._previous_time = timestamp
        return emitted

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None


class TiffRecorder:
    """Write every captured RGB frame as one page of a new multi-page TIFF.

    TIFF pages carry no playback rate, so no frame is dropped or repeated: each
    captured frame becomes one page and :meth:`write` returns its capture time
    for the timing sidecar. Pages are appended as they arrive through the image
    I/O seam (the TTTR library's libtiff), so recording needs no OpenCV and the
    writer's memory stays one frame however long the recording runs. The output
    must not already exist.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._closed = False
        self._shape = None
        self._previous_time = None

    def write(self, frame: VideoFrame) -> list[float]:
        image = _validated_rgb(frame.image)
        timestamp = float(frame.timestamp_s)
        _checked_timestamp(self._previous_time, timestamp)
        if self._closed:
            raise RuntimeError("Video recording is already closed.")
        if self._shape is None and self.path.exists():
            raise FileExistsError(self.path)
        if self._shape is not None and image.shape != self._shape:
            raise ValueError("Video frame dimensions changed during recording.")
        from chisurf.core.fio.image import append

        append(self.path, image)
        self._shape = image.shape
        self._previous_time = timestamp
        return [timestamp]

    def close(self) -> None:
        self._closed = True

