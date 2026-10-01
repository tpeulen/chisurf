"""Qt-free view model of the Photon Table emtk app.

Wraps :class:`~..core.model.PhotonTableModel` (the photons of one TTTR file,
paged and channel-filtered) with what the window edits: the first photon shown,
the page size, the channel filter, the status line and the requests of the
Open and Copy buttons. The numbers come from the core model, unchanged, so the
Qt tool and this app show the same rows for the same file.
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable

from ..core.model import PhotonTableModel

#: The "All channels" sentinel of the channel filter (the core model's too).
CHANNEL_ANY = -1
#: Largest page, as the core model clamps it.
MAX_ROWS = 20_000
#: The container formats the Open dialog offers (the Qt tool's filter).
TTTR_FILTERS = "TTTR files (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r);;All files (*)"


class _Rows(list):
    """The rows of the table, with a ``revision`` the table notices a change by."""

    revision = 0


class PhotonTableViewModel:
    """State and actions of the photon table window."""

    def __init__(self, table: PhotonTableModel | None = None) -> None:
        self.table = table or PhotonTableModel()
        self.first_index = 0
        self.rows_per_page = 200
        self.channel_filter = CHANNEL_ANY
        #: The status line: what was loaded, what failed, what was copied.
        self.notice = ""
        #: ``"open"`` or ``"copy"`` while the app has to act on a button.
        self.request = ""
        #: The last file opened successfully (the Open dialog starts in its folder).
        self.input_file = ""
        self.busy = False
        self._observers: list[Callable[[str], None]] = []
        self._rows = _Rows()
        self._rows_key: tuple | None = None
        self._revision = 0

    # ── observers (the SnapshotJob listens) ───────────────────────────
    def notify(self, event: str = "updated") -> None:
        """Tell the observers that something changed."""
        for observer in list(self._observers):
            observer(event)

    @property
    def status_text(self) -> str:
        """The status line."""
        return self.notice

    # ── state read by the spec ────────────────────────────────────────
    @property
    def loaded(self) -> bool:
        return self.table.n_photons > 0

    @property
    def not_loaded(self) -> bool:
        return not self.loaded

    @property
    def file_name(self) -> str:
        return self.table.filename

    @property
    def summary_text(self) -> str:
        """Photon count, acquisition time and micro-time channels, as the Qt tool shows them."""
        t = self.table
        text = f"{t.n_photons:,} photons"
        acq = t.acquisition_time_s()
        if acq > 0:
            text += f", {acq:.3g} s"
        if t.n_micro_channels:
            text += f", {t.n_micro_channels} µ-channels"
        return text

    @property
    def channels_text(self) -> str:
        channels = self.table.used_channels
        return f"Routing channels: {', '.join(str(c) for c in channels) or '—'}"

    @property
    def count(self) -> int:
        """How many photons the channel filter lets through."""
        return self.table.filtered_count(self.channel_filter)

    @property
    def range_text(self) -> str:
        count = self.count
        if not count:
            return "no photons"
        return f"photons {self.first_index:,}–{min(count, self.first_index + self.rows_per_page):,}"

    def channel_labels(self) -> list[list]:
        """``[value, label]`` of the channel choice: All channels, then each used channel."""
        return [[CHANNEL_ANY, "All channels"]] + [[c, str(c)] for c in self.table.used_channels]

    @property
    def rows(self) -> list[dict]:
        """The visible page as table records (rebuilt only when the page changes)."""
        key = (id(self.table), self.first_index, self.rows_per_page, self.channel_filter)
        if key != self._rows_key:
            self._revision += 1
            rows = _Rows(self.table.page(self.first_index, self.rows_per_page, self.channel_filter))
            rows.revision = self._revision
            self._rows, self._rows_key = rows, key
        return self._rows

    def enabled(self, name: str) -> bool:
        """Which buttons can be pressed now."""
        if name in ("request_open",):
            return not self.busy
        if name in ("go_first", "go_prev", "go_next", "go_last", "request_copy"):
            return self.loaded and not self.busy
        return True

    def bounds(self, name: str):
        """Dynamic limits of the page fields."""
        if name == "first_index":
            return (0, max(self.count - 1, 0))
        return None

    # ── loading ───────────────────────────────────────────────────────
    def load_path(self, path: str) -> bool:
        """Open a TTTR file and show its photons from the first page.

        A failed load leaves the table that was shown and says why in the status line.
        """
        path = str(path)
        if not pathlib.Path(path).is_file():
            self.notice = f"Could not open {path}: file does not exist"
            return False
        table = PhotonTableModel()
        try:
            table.load_file(path)
        except Exception as exc:  # noqa: BLE001 - tttrlib raises RuntimeError and others
            self.notice = f"Could not open {path}: {exc}"
            return False
        self.table = table
        self.first_index = 0
        self.channel_filter = CHANNEL_ANY
        self.input_file = path
        self.notice = f"{table.n_photons:,} photons from {path}"
        self.notify("loaded")
        return True

    def drop_directory(self) -> str:
        """The folder the Open dialog starts in."""
        if self.input_file:
            parent = pathlib.Path(self.input_file).parent
            if parent.is_dir():
                return str(parent)
        return ""

    # ── buttons ───────────────────────────────────────────────────────
    def request_open(self) -> None:
        self.request = "open"

    def request_copy(self) -> None:
        self.request = "copy"

    def copy_text(self) -> str:
        """The visible rows as tab-separated text (the Qt tool's 'Copy visible')."""
        return self.table.page_tsv(self.first_index, self.rows_per_page, self.channel_filter)

    def go_first(self) -> None:
        self.first_index = 0

    def go_prev(self) -> None:
        self.first_index = self._clamp(self.first_index - self.rows_per_page)

    def go_next(self) -> None:
        self.first_index = self._clamp(self.first_index + self.rows_per_page)

    def go_last(self) -> None:
        self.first_index = self._clamp(max(self.count - self.rows_per_page, 0))

    # ── fields ────────────────────────────────────────────────────────
    def _clamp(self, first: int) -> int:
        return self.table.clamp_first(first, self.rows_per_page, self.channel_filter)

    def set_first(self, value: Any) -> None:
        """The first photon typed into the field, clamped into the filtered range."""
        self.first_index = self._clamp(_to_int(value, self.first_index))

    def set_rows(self, value: Any) -> None:
        """The page size typed into the field (1 to 20000), keeping the page inside the data."""
        self.rows_per_page = max(1, min(_to_int(value, self.rows_per_page), MAX_ROWS))
        self.first_index = self._clamp(self.first_index)

    def set_channel(self, value: Any) -> None:
        """The routing channel to show (-1: all); the table goes back to the top."""
        value = _to_int(value, CHANNEL_ANY)
        valid = [CHANNEL_ANY] + self.table.used_channels
        self.channel_filter = value if value in valid else CHANNEL_ANY
        self.first_index = self._clamp(0)

    # ── persistence ───────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the page size and the last file."""
        return {"rows_per_page": int(self.rows_per_page), "input_file": self.input_file}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; the file is not reopened."""
        if "rows_per_page" in settings:
            self.rows_per_page = max(1, min(_to_int(settings["rows_per_page"], 200), MAX_ROWS))
        self.input_file = str(settings.get("input_file", "") or "")


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
