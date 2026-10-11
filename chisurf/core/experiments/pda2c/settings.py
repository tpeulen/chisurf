"""The PDA reader's settings as a form binds them: detector rows, time windows, the file list.

:class:`PdaReaderSettings` is the object a settings form reads and writes. It
owns no state of its own that matters: every write lands on the reader at once
(``channels``, ``micro_time_ranges``, ``reading_routine``, ``tw_configs``,
``minimum_time_window_length``, ``files``, ...), so a form rebuilt after a
colour-count change, or a second form over the same reader, shows what the
reader will read with. The Qt panel and the emtk form both bind it; neither
holds the logic.

Row fields are named by position -- ``detector_0``, ``channels_0``,
``window_0``, ... -- because how many rows exist is the colour-count setting:
two detectors with a photon-selection window each, or three detectors and the
two excitation periods of the PIE cycle.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Mapping
from typing import Any

from chisurf.core.experiments.pda2c import inputs

#: How many detector rows a form can show (three colours).
MAX_ROWS = 3


def _saved_setups() -> tuple[dict, str]:
    """The saved detector setups by name and the last one used (the one store every picker reads)."""
    try:
        from chisurf.core.data_io.detector_setups import load_detector_setups

        data = load_detector_setups()
    except Exception:  # noqa: BLE001 - no store: no setups, channels are typed by hand
        return {}, ""
    setups = data.get("setups", {}) if isinstance(data, dict) else {}
    last = data.get("last_used", "") if isinstance(data, dict) else ""
    return (dict(setups) if isinstance(setups, dict) else {}), str(last or "")


def _routines() -> list[str]:
    """The TTTR container types tttrlib reads."""
    try:
        import tttrlib

        names = [str(n) for n in tttrlib.TTTR.get_supported_container_names()]
        if names:
            return names
    except Exception:  # noqa: BLE001
        pass
    from chisurf.core.fio.staging import supported_container_types

    return [str(n) for n in supported_container_types()]


#: Shown as the only setup when none is saved; choosing it changes nothing.
NO_SETUP = "No setups available"


class _Rows(list):
    """Table rows with a ``revision``: a table re-reads them when it changes, not every frame."""

    revision = 0


def _row_property(kind: str, row: int) -> property:
    """``detector_<row>`` / ``channels_<row>`` / ``window_<row>``: one field of one row, by name."""
    getter = {
        "detector": PdaReaderSettings.detector,
        "channels": PdaReaderSettings.channels_text,
        "window": PdaReaderSettings.window_text,
    }[kind]
    setter = {
        "detector": PdaReaderSettings.set_detector,
        "channels": PdaReaderSettings.set_channels_text,
        "window": PdaReaderSettings.set_window_text,
    }[kind]
    return property(
        lambda self: getter(self, row),
        lambda self, value: setter(self, row, value),
        doc=f"The {kind} field of row {row}.",
    )


class PdaReaderSettings:
    """Bind a settings form to a :class:`~chisurf.core.experiments.pda2c.Pda2cReader`.

    Parameters
    ----------
    reader : Pda2cReader
        The reader every write lands on.
    setups : mapping, optional
        Saved detector setups by name; read from the store when omitted.
    last_used : str, optional
        The setup chosen when the reader has none yet.
    routines : list of str, optional
        TTTR container types; tttrlib's when omitted.
    """

    def __init__(
        self,
        reader: Any,
        setups: Mapping | None = None,
        last_used: str | None = None,
        routines: list[str] | None = None,
    ) -> None:
        self.reader = reader
        if setups is None:
            setups, saved_last = _saved_setups()
            last_used = saved_last if last_used is None else last_used
        self.setups = dict(setups)
        self._routines = list(routines) if routines is not None else _routines()
        self._accepted = inputs.accepted_extensions()
        if getattr(reader, "files", None) is None:
            reader.files = []
        if getattr(reader, "auto_load", None) is None:
            reader.auto_load = True
        if getattr(reader, "tw_configs", None) is None:
            # A form starts with the usual time windows; a reader used without
            # one reads its single nPh min / time window.
            reader.tw_configs = list(inputs.DEFAULT_TW_CONFIGS)
        self._tw_rows = _Rows()
        self._file_rows = _Rows()
        names = list(self.setups)
        chosen = str(getattr(reader, "detector_setup", "") or "")
        if chosen in names:
            self._seen_colors = self.n_colors
            return
        start = last_used if last_used in names else (names[0] if names else "")
        self._seen_colors = self.n_colors
        if start:
            self.setup = start

    # -- colours ------------------------------------------------------------- #
    @property
    def n_colors(self) -> int:
        """The reader's colour count, 2 or 3."""
        return inputs.colour_count(getattr(self.reader, "n_colors", 2))

    @property
    def three_colours(self) -> bool:
        """Whether the rows are three detectors and two excitation periods."""
        return self.n_colors == 3

    def row_labels(self) -> tuple[str, ...]:
        """The colour of each detector row (``Green``, ``Red`` / ``Blue``, ``Green``, ``Red``)."""
        return inputs.COLOUR_LABELS[self.n_colors]

    def sync(self) -> bool:
        """Re-derive the detector rows after the colour count changed under the form.

        The reader rolls its channel groups when its colour count changes; the
        rows then take the setup's detectors named after the new colours.

        Returns
        -------
        bool
            Whether the count had changed.
        """
        if self.n_colors == self._seen_colors:
            return False
        self._seen_colors = self.n_colors
        detectors = self._detectors()
        if detectors:
            self.reader.detector_names = inputs.preferred_detectors(detectors, self.n_colors)
            self._apply_detectors()
        return True

    # -- setup, routine, detectors ------------------------------------------- #
    def setup_names(self) -> list[str]:
        """The saved setups, or the one placeholder that says there are none."""
        return list(self.setups) or [NO_SETUP]

    @property
    def setup(self) -> str:
        """The chosen detector setup; choosing one assigns its detectors to the rows."""
        name = str(getattr(self.reader, "detector_setup", "") or "")
        return name if name in self.setups else (NO_SETUP if not self.setups else name)

    @setup.setter
    def setup(self, name: str) -> None:
        name = str(name)
        if name not in self.setups:
            return
        self.reader.detector_setup = name
        self.reader.detector_names = inputs.preferred_detectors(self._detectors(), self.n_colors)
        reading = self.setups[name].get("tttr_reading") or {}
        routine = reading.get("file_type") if isinstance(reading, dict) else None
        if isinstance(routine, str) and routine in self._routines:
            self.reader.reading_routine = routine
        self._apply_detectors()

    def _detectors(self) -> dict:
        setup = self.setups.get(str(getattr(self.reader, "detector_setup", "") or "")) or {}
        detectors = setup.get("detectors") or {}
        return dict(detectors) if isinstance(detectors, Mapping) else {}

    def detector_names(self) -> list[str]:
        """The detectors of the chosen setup, each row's options."""
        return [str(n) for n in self._detectors()]

    def routine_names(self) -> list[str]:
        """The TTTR container types, the reader's own first when tttrlib does not list it."""
        current = self.routine
        names = list(self._routines)
        return names if not current or current in names else [current, *names]

    @property
    def routine(self) -> str:
        """The TTTR container type of the files."""
        return str(getattr(self.reader, "reading_routine", "") or "")

    @routine.setter
    def routine(self, name: str) -> None:
        self.reader.reading_routine = str(name)

    def detector(self, row: int) -> str:
        """The detector chosen for *row*."""
        names = list(getattr(self.reader, "detector_names", None) or [])
        return str(names[row]) if row < len(names) else ""

    def set_detector(self, row: int, name: str) -> None:
        """Choose *name* for *row*: its routing channels, and at two colours its window, fill the row."""
        names = list(getattr(self.reader, "detector_names", None) or [])
        names += [""] * (self.n_colors - len(names))
        names[row] = str(name)
        self.reader.detector_names = names
        self._apply_detectors()

    def _apply_detectors(self) -> None:
        """Copy the chosen detectors' channels (and at two colours windows) onto the reader.

        The windows follow a detector only at two colours, where each detector
        has its own photon-selection window; at three they are the excitation
        periods of the PIE cycle and belong to no detector. Without detectors
        nothing is written: a hand-typed channel list is not blanked.
        """
        detectors = self._detectors()
        if not detectors:
            return
        n = self.n_colors
        channels = self._groups("channels", n)
        windows = list(getattr(self.reader, "micro_time_ranges", None) or [])
        for row in range(n):
            info = detectors.get(self.detector(row))
            if not isinstance(info, Mapping):
                continue
            channels[row] = [int(c) for c in info.get("chs", [])]
            if n == 2:
                while len(windows) <= row:
                    windows.append([])
                windows[row] = inputs.parse_micro_time_ranges(
                    inputs.format_micro_time_ranges(info.get("micro_time_ranges", []))
                )
        self.reader.channels = channels
        if n == 2:
            self.reader.micro_time_ranges = windows

    # -- rows as text --------------------------------------------------------- #
    def _groups(self, attr: str, n: int) -> list:
        groups = [
            list(g) if g is not None else [] for g in (getattr(self.reader, attr, None) or [])
        ]
        return (groups + [[] for _ in range(n)])[:n]

    def channels_text(self, row: int) -> str:
        """Routing channels of *row* as ``"0, 3"``."""
        groups = list(getattr(self.reader, "channels", None) or [])
        return inputs.format_channels(groups[row]) if row < len(groups) else ""

    def set_channels_text(self, row: int, text: str) -> None:
        """Set the routing channels of *row* from ``"0, 3"``."""
        groups = self._groups("channels", self.n_colors)
        groups[row] = inputs.parse_channels(text)
        self.reader.channels = groups

    def window_text(self, index: int) -> str:
        """Micro-time window *index* as ``"start-end;start-end"``.

        A detector's photon selection at two colours; an excitation period of
        the PIE cycle at three.
        """
        windows = list(getattr(self.reader, "micro_time_ranges", None) or [])
        return inputs.format_micro_time_ranges(windows[index]) if index < len(windows) else ""

    def set_window_text(self, index: int, text: str) -> None:
        """Set micro-time window *index* from ``"start-end;start-end"``.

        A two-colour window is a detector's photon selection and may list
        several ranges, so it stays a list of them. A three-colour window is
        one excitation period and is a single ``[start, stop]`` pair, which is
        what :meth:`~chisurf.core.experiments.pda2c.Pda2cReader.detection_windows`
        pairs with the detectors that see that pulse.
        """
        windows = list(getattr(self.reader, "micro_time_ranges", None) or [])
        windows = (windows + [[], []])[: max(2, len(windows))]
        parsed = inputs.parse_micro_time_ranges(text)
        windows[index] = (parsed[0] if parsed else []) if self.three_colours else parsed
        self.reader.micro_time_ranges = windows

    # -- time windows --------------------------------------------------------- #
    @property
    def tw_ms(self) -> float:
        """The time window an added entry gets, in ms (the reader keeps seconds)."""
        return float(getattr(self.reader, "minimum_time_window_length", 0.0) or 0.0) * 1e3

    @tw_ms.setter
    def tw_ms(self, value: float) -> None:
        value = float(value)
        if value > 0.0:
            self.reader.minimum_time_window_length = value / 1e3

    def tw_configs(self) -> list[tuple[int, float]]:
        """The ``(photons, seconds)`` time windows the reader reads, one dataset each."""
        return inputs.valid_tw_configs(getattr(self.reader, "tw_configs", None))

    def tw_rows(self) -> list[dict]:
        """One record per time window, for a list or table (the same list until one changes)."""
        rows = [
            {"window": inputs.tw_label(n, s), "n_ph": n, "tw_s": s} for n, s in self.tw_configs()
        ]
        return self._refreshed(self._tw_rows, rows)

    @staticmethod
    def _refreshed(cache: _Rows, rows: list[dict]) -> _Rows:
        if list(cache) != rows:
            cache[:] = rows
            cache.revision += 1
        return cache

    def add_tw(self) -> None:
        """Add the current ``nPh min`` and time window as an entry (a duplicate is not added)."""
        n_ph = int(getattr(self.reader, "minimum_number_of_photons", 0) or 0)
        self.reader.tw_configs = inputs.add_tw_config(self.tw_configs(), n_ph, self.tw_ms / 1e3)

    def remove_tw(self, record: Any) -> None:
        """Remove the time window *record* (a row of :meth:`tw_rows`, or an index)."""
        configs = self.tw_configs()
        if isinstance(record, int):
            if 0 <= record < len(configs):
                del configs[record]
        elif isinstance(record, Mapping):
            entry = (int(record.get("n_ph", 0)), float(record.get("tw_s", 0.0)))
            configs = [c for c in configs if c != entry]
        self.reader.tw_configs = configs

    def clear_tw(self, *_record: Any) -> None:
        """Remove every time window: the reader then reads one, ``nPh min`` at the current window."""
        self.reader.tw_configs = []

    # -- files ---------------------------------------------------------------- #
    @property
    def auto_load(self) -> bool:
        """Read files as soon as they are dropped, and empty the list after a read."""
        return bool(getattr(self.reader, "auto_load", True))

    @auto_load.setter
    def auto_load(self, value: bool) -> None:
        self.reader.auto_load = bool(value)

    def file_rows(self) -> list[dict]:
        """The file list, one record per file or folder (copies; edit through the methods).

        ``use`` and ``path`` are the entry; ``name`` and ``folder`` split the
        path for a list too narrow to show it whole.
        """
        rows = []
        for entry in self.reader.files:
            path = pathlib.Path(str(entry["path"]))
            rows.append(
                {
                    "use": bool(entry.get("use", True)),
                    "name": path.name or str(path),
                    "folder": str(path.parent),
                    "path": str(path),
                }
            )
        return self._refreshed(self._file_rows, rows)

    def file_edited(self, record: Any, key: str, value: Any) -> None:
        """A table cell of the file list changed: the *Use* tick is the only editable one."""
        if key == "use" and isinstance(record, Mapping):
            self.set_use(str(record.get("path", "")), bool(value))

    def add_paths(self, paths: Iterable[str]) -> int:
        """Add TTTR files, burst tables and folders; anything else and duplicates are skipped.

        Returns
        -------
        int
            How many entries were added.
        """
        present = {row["path"] for row in self.reader.files}
        added = 0
        for path in paths or ():
            text = str(path)
            if text in present or not inputs.accepts_path(text, self._accepted):
                continue
            self.reader.files.append({"use": True, "path": text})
            present.add(text)
            added += 1
        return added

    def set_use(self, path: str, use: bool) -> None:
        """Tick or untick *path*: only ticked entries are read."""
        for row in self.reader.files:
            if row["path"] == str(path):
                row["use"] = bool(use)

    def remove_paths(self, paths: Iterable[str]) -> None:
        """Remove *paths* from the list."""
        gone = {str(p) for p in paths}
        self.reader.files[:] = [row for row in self.reader.files if row["path"] not in gone]

    def remove_file(self, record: Any) -> None:
        """Remove one entry (a row of :meth:`file_rows`)."""
        if isinstance(record, Mapping):
            self.remove_paths([record.get("path", "")])

    def clear_files(self, *_record: Any) -> None:
        """Empty the list."""
        self.reader.files[:] = []

    def checked_paths(self) -> list[str]:
        """The ticked entries, in list order: what a read takes."""
        return [row["path"] for row in self.reader.files if row.get("use", True)]

    def load_filename(self) -> str:
        """The ticked entries as the ``|``-joined filename a read takes; empty when none."""
        return "|".join(self.checked_paths())


for _row in range(MAX_ROWS):
    setattr(PdaReaderSettings, f"detector_{_row}", _row_property("detector", _row))
    setattr(PdaReaderSettings, f"channels_{_row}", _row_property("channels", _row))
for _row in range(2):
    setattr(PdaReaderSettings, f"window_{_row}", _row_property("window", _row))
del _row


__all__ = ["MAX_ROWS", "NO_SETUP", "PdaReaderSettings"]
