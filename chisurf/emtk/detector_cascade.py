"""Native reader settings sections for photon-stream readers: the detector cascade and the ICS ROI.

The TCSPC-TTTR, PCH and image-correlation readers declare a ``custom`` section
(``tcspc_tttr_detector``, ``pch_detector``, ``ics_detector``) that the Qt
editor fills with a hand-built widget: *Setup* → *Detector* picks a named
detector of a saved setup, which writes the routing channels, the micro-time
window and the setup's LUTs onto the reader; *Routine* is the TTTR container
type and *Routing chs* the channels typed by hand. The image-correlation reader
adds ``ics_roi``, the pixel rectangle of each frame.

Here the same sections are emtk view specs (choices and value fields) drawn by
:func:`emtk.view_form.draw_sections` over a small model, registered on the
reader settings form by :func:`register`. The writes are the Qt widgets' own:
the reader object is the client-side configuration a later ``dataset.load``
reads with, so nothing here touches the session.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from emtk.view_form import FormState, draw_sections

from chisurf.core.support.i18n import tr

#: The custom section keys :func:`register` draws natively.
DETECTOR_KEYS = ("tcspc_tttr_detector", "pch_detector", "ics_detector")
ROI_KEY = "ics_roi"


def detector_setups() -> dict:
    """The saved detector setups by name (the one store every picker reads)."""
    try:
        from chisurf.core.data_io.detector_setups import load_detector_setups

        data = load_detector_setups()
    except Exception:  # noqa: BLE001 - no store: no setups, channels are typed by hand
        return {}
    setups = data.get("setups", {}) if isinstance(data, dict) else {}
    return setups if isinstance(setups, dict) else {}


def last_used_setup() -> str:
    """The name of the detector setup used last, ``""`` when none is recorded."""
    try:
        from chisurf.core.data_io.detector_setups import load_detector_setups

        data = load_detector_setups()
    except Exception:  # noqa: BLE001 - no store: nothing was used
        return ""
    return str(data.get("last_used", "") or "") if isinstance(data, dict) else ""


def routines() -> list[str]:
    """The TTTR container types tttrlib reads."""
    try:
        import tttrlib

        names = list(tttrlib.TTTR.get_supported_container_names())
        if names:
            return [str(n) for n in names]
    except Exception:  # noqa: BLE001
        pass
    from chisurf.core.fio.staging import supported_container_types

    return [str(n) for n in supported_container_types()]


def _channels(text: str) -> list[int]:
    out = []
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out or [0]


class DetectorCascade:
    """Setup → Detector → Routine + routing channels, written onto a reader.

    Parameters
    ----------
    reader : object
        The TTTR / PCH / ICS reader.
    setups : dict, optional
        Named detector setups; read from the store when omitted.
    """

    SPEC = {
        "sections": [
            {
                "type": "choice",
                "attr": "setup",
                "label": "Setup",
                "options_source": "setup_names",
                "description": "A saved detector setup: its detectors, LUTs and file type.",
            },
            {
                "type": "choice",
                "attr": "detector",
                "label": "Detector",
                "options_source": "detector_names",
                "description": "The detector of the setup whose routing channels are read.",
            },
            {
                "type": "choice",
                "attr": "routine",
                "label": "Routine",
                "options_source": "routine_names",
                "description": "The TTTR container type of the file.",
            },
            {
                "type": "value",
                "attr": "channels",
                "kind": "str",
                "label": "Routing chs",
                "placeholder": "e.g. 0,3 or from detector setup",
                "description": "Routing channels used for the histogram; populated from the detector "
                "setup or entered manually (comma-separated).",
            },
        ]
    }

    def __init__(self, reader: Any, setups: dict | None = None) -> None:
        self.reader = reader
        self.setups = detector_setups() if setups is None else dict(setups)
        self._routines = routines()
        self.form = FormState()
        chosen = str(getattr(reader, "detector_setup", "") or "")
        names = self.setup_names()
        self._setup = chosen if chosen in names else (names[0] if names else "")
        dets = self.detector_names()
        chosen = str(getattr(reader, "detector_name", "") or "")
        self._detector = chosen if chosen in dets else (dets[0] if dets else "")
        if self._setup and not getattr(reader, "detector_setup", ""):
            self._apply_routine()
            self._apply()

    # -- options ------------------------------------------------------------ #
    def setup_names(self) -> list[str]:
        return sorted(str(n) for n in self.setups)

    def detector_names(self) -> list[str]:
        setup = self.setups.get(self._setup) or {}
        return sorted(str(n) for n in (setup.get("detectors") or {}))

    def routine_names(self) -> list[str]:
        current = str(getattr(self.reader, "reading_routine", "") or "")
        names = list(self._routines)
        return names if not current or current in names else [current, *names]

    # -- the bound values ------------------------------------------------------ #
    @property
    def setup(self) -> str:
        return self._setup

    @setup.setter
    def setup(self, name: str) -> None:
        self._setup = str(name)
        dets = self.detector_names()
        self._detector = dets[0] if dets else ""
        self._apply_routine()
        self._apply()

    def _apply_routine(self) -> None:
        """The setup's file type is the reading routine, when it names one."""
        setup = self.setups.get(self._setup) or {}
        reading = setup.get("tttr_reading") or {}
        routine = reading.get("file_type") if isinstance(reading, dict) else None
        if isinstance(routine, str) and routine:
            self.reader.reading_routine = routine

    @property
    def detector(self) -> str:
        return self._detector

    @detector.setter
    def detector(self, name: str) -> None:
        self._detector = str(name)
        self._apply()

    @property
    def routine(self) -> str:
        return str(getattr(self.reader, "reading_routine", "") or "")

    @routine.setter
    def routine(self, name: str) -> None:
        self.reader.reading_routine = str(name)

    @property
    def channels(self) -> str:
        numbers = getattr(self.reader, "channel_numbers", None)
        if numbers is None:
            numbers = [getattr(self.reader, "channel", 0)]
        try:
            return ", ".join(str(int(c)) for c in list(numbers))
        except TypeError:
            return str(numbers)

    @channels.setter
    def channels(self, text: str) -> None:
        self._write_channels(_channels(text))

    # -- writing the reader ------------------------------------------------------ #
    def _write_channels(self, channels: list[int]) -> None:
        reader = self.reader
        if isinstance(getattr(type(reader), "channel_numbers_str", None), property):
            reader.channel_numbers_str = ", ".join(str(c) for c in channels)
        else:
            reader.channel_numbers = np.array(channels, dtype=np.int8)
            reader.channel = int(channels[0])

    def _apply(self) -> None:
        """The chosen detector's channels, window and the setup's LUTs, onto the reader."""
        reader = self.reader
        setup = self.setups.get(self._setup) or {}
        info = (setup.get("detectors") or {}).get(self._detector)
        if isinstance(info, dict):
            self._write_channels([int(c) for c in info.get("chs", [])] or [0])
            windows = info.get("micro_time_ranges")
            if hasattr(reader, "micro_time_ranges"):
                reader.micro_time_ranges = windows
            elif (
                hasattr(reader, "micro_time_range")
                and isinstance(windows, (list, tuple))
                and windows
            ):
                first = windows[0]
                if isinstance(first, dict):
                    first = first.get("range", first.get("values", first))
                if isinstance(first, (list, tuple)) and len(first) >= 2:
                    reader.micro_time_range = (int(first[0]), int(first[1]))
        reader.detector_setup = self._setup
        reader.detector_name = self._detector
        reader.channel_luts = {int(k): v for k, v in (setup.get("channel_luts") or {}).items()}
        reader.channel_shifts = {
            int(k): int(v) for k, v in (setup.get("channel_shifts") or {}).items()
        }
        reader.apply_lut = bool(setup.get("apply_lut", False))

    def draw(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The cascade as two lines of fields, as the Qt widget's 2 × 2 grid."""
        if not self.setups:
            from emtk import im

            im.text_disabled(tr("No saved detector setup: type the routing channels."))
        draw_sections(self.SPEC["sections"], self, self.form, n_col=2)
        for name, rect in self.form.rects.items():
            state.rects[f"{section.get('key')}.{name}"] = rect


class IcsRoi:
    """The image-correlation reader's pixel rectangle (``x_range`` / ``y_range``); −1: to the edge."""

    SPEC = {
        "sections": [
            {
                "type": "value",
                "attr": "x0",
                "kind": "int",
                "label": "X range",
                "minimum": 0,
                "description": "First column of each frame that enters the correlation.",
            },
            {
                "type": "value",
                "attr": "x1",
                "kind": "int",
                "label": "to",
                "minimum": -1,
                "description": "Last column (−1: the last of the frame).",
            },
            {
                "type": "value",
                "attr": "y0",
                "kind": "int",
                "label": "Y range",
                "minimum": 0,
                "description": "First row of each frame that enters the correlation.",
            },
            {
                "type": "value",
                "attr": "y1",
                "kind": "int",
                "label": "to",
                "minimum": -1,
                "description": "Last row (−1: the last of the frame).",
            },
        ]
    }

    def __init__(self, reader: Any) -> None:
        self.reader = reader
        self.form = FormState()

    def _range(self, axis: str) -> tuple[int, int]:
        value = getattr(self.reader, f"{axis}_range", None) or (0, -1)
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError, IndexError):
            return 0, -1

    def _set(self, axis: str, index: int, value: Any) -> None:
        pair = list(self._range(axis))
        pair[index] = int(value)
        setattr(self.reader, f"{axis}_range", (pair[0], pair[1]))

    x0 = property(lambda self: self._range("x")[0], lambda self, v: self._set("x", 0, v))
    x1 = property(lambda self: self._range("x")[1], lambda self, v: self._set("x", 1, v))
    y0 = property(lambda self: self._range("y")[0], lambda self, v: self._set("y", 0, v))
    y1 = property(lambda self: self._range("y")[1], lambda self, v: self._set("y", 1, v))

    def draw(self, section: dict, model: Any, state: FormState, width: float) -> None:
        draw_sections(self.SPEC["sections"], self, self.form, n_col=2)
        for name, rect in self.form.rects.items():
            state.rects[f"{ROI_KEY}.{name}"] = rect


def register(reader: Any, form: FormState, setups: dict | None = None) -> None:
    """Draw the photon-stream sections a reader's spec declares natively on *form*."""
    cascade: DetectorCascade | None = None

    def detector(section, model, state, width) -> None:
        nonlocal cascade
        if cascade is None:
            cascade = DetectorCascade(reader, setups)
        cascade.draw(section, model, state, width)

    for key in DETECTOR_KEYS:
        form.custom.setdefault(key, detector)
    roi = IcsRoi(reader)
    form.custom.setdefault(ROI_KEY, roi.draw)


__all__ = [
    "DETECTOR_KEYS",
    "DetectorCascade",
    "IcsRoi",
    "ROI_KEY",
    "detector_setups",
    "last_used_setup",
    "register",
]
