"""Drive the emtk app headlessly: settle frames, click a label, read a file."""

from __future__ import annotations

import time
from typing import Any

from emtk.testing import RecordingPainter

LEFT = 1


def frame(app: Any, size: tuple[int, int] = (1200, 800)) -> RecordingPainter:
    """Draw one frame with a recording painter and return it."""
    painter = RecordingPainter()
    app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def settle(app: Any, size: tuple[int, int] = (1200, 800), frames: int = 3) -> RecordingPainter:
    """Draw a few frames so windows open and layout settles; return the last painter."""
    painter = frame(app, size)
    for _ in range(frames - 1):
        painter = frame(app, size)
    return painter


def find_text(painter: RecordingPainter, label: str, nth: int = 0) -> tuple[float, float] | None:
    """Centre of the *nth* drawn string equal to *label*."""
    hits = [t for t in painter.texts if t[5] == label]
    if len(hits) <= nth:
        return None
    x, y, w, h = hits[nth][:4]
    return x + w / 2.0, y + h / 2.0


def click_text(app: Any, label: str, size: tuple[int, int] = (1200, 800), nth: int = 0) -> bool:
    """Press and release the pointer on the *nth* drawn *label*; False when it is not on screen."""
    where = find_text(settle(app, size, 2), label, nth)
    if where is None:
        return False
    x, y = where
    app.pointer_move(x, y)
    frame(app, size)
    app.pointer_press(x, y, LEFT)
    frame(app, size)
    app.pointer_release(x, y, LEFT)
    settle(app, size, 2)
    return True


def finish_read(app: Any, timeout: float = 60.0) -> None:
    """Wait for the background read of the editor to finish."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.page.poll()
        if app.page._future is None:
            return
        time.sleep(0.05)
    raise TimeoutError("the TTTR read did not finish")


def populate(app: Any, path: Any) -> None:
    """Read the measurement *path* as the Read button does, and wait for it."""
    app.page.read(str(path))
    finish_read(app)


DATA = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[0, 2048]], "g_factor": 1.25, "l1": 0.01, "l2": 0.02},
    },
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 13.5, "micro_time_resolution": 3.25, "micro_time_binning": 2},
    "polarization_resolved": True,
}
STAMP = "2026-09-01T10:00:00"
CAL = {"green": (1.7, 0.1, 0.2), "red": (0.9, 0.3, 0.4)}


def norm(setup):
    """The fields both implementations store, in one comparable shape."""
    reading = setup.get("tttr_reading", {})
    return {
        "windows": {k: [int(a) for a in v] for k, v in sorted(setup.get("windows", {}).items())},
        "detectors": {
            n: {
                "chs": [int(c) for c in d.get("chs", [])],
                "micro_time_ranges": [[int(a) for a in r] for r in d.get("micro_time_ranges", [])],
                "g_factor": float(d.get("g_factor", 1.0)),
                "l1": float(d.get("l1", 0.0)),
                "l2": float(d.get("l2", 0.0)),
            }
            for n, d in sorted(setup.get("detectors", {}).items())
        },
        "reading": {k: reading.get(k) for k in ("file_type", "macro_time_resolution", "micro_time_resolution", "micro_time_binning")},
        "polarization_resolved": bool(setup.get("polarization_resolved", True)),
        "apply_lut": bool(setup.get("apply_lut", False)),
    }


