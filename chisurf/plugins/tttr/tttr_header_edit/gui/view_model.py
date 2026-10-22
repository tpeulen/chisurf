"""Qt-free view-model backing the TTTR Inspector tool.

:class:`HeaderEditorViewModel` holds the parsed header tags of any
:mod:`tttrlib`-readable time-tagged file (PicoQuant PTU/HT3, Becker&Hickl SPC,
PicoQuant/HDF5 …), converts values by tag type and writes the edited header back
out. Because ``tttrlib`` normalises every container into the same
``{name, type, value, idx}`` tag list, reading is format-agnostic; only the
*write* side is container-specific — arbitrary edited tags round-trip losslessly
only through the PTU container, so saving always produces a PTU file (the photon
data of the source is copied verbatim).

The editable tag table lives in the custom ``header_table`` section; the
read-only JSON view binds to :attr:`json_text`. Free of Qt so it is unit-testable
headlessly.
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
import tempfile

import tttrlib

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "header.view.json"

#: File-dialog filter listing the containers :mod:`tttrlib` can auto-detect.
OPEN_FILTER = (
    "TTTR files (*.pto *.ptu *.ht3 *.spc *.hdf5 *.h5);;"
    "PicoQuant PTU (*.ptu);;PicoQuant HT3 (*.ht3);;"
    "Becker&Hickl SPC (*.spc);;Photon-HDF5 (*.hdf5 *.h5);;"
    "All files (*)"
)

#: Sample header used when the tool opens without a file.
SAMPLE_JSON = json.dumps(
    {
        "tags": [
            {
                "name": "File_GUID",
                "type": 1073872895,
                "value": "{D3D2D9C0-5B48-4D94-98CE-A5E2EA3558E6}",
            },
            {"name": "File_CreatingTime", "type": 553648136, "value": "1539705731.9470003"},
            {"name": "Measurement_SubMode", "type": 268435464, "value": "1"},
            {"name": "User_Author", "type": 2000000001, "value": "John Doe"},
            {"name": "File_Version", "type": 1000000002, "value": "1.0.0"},
            {
                "name": "File_Description",
                "type": 2000000003,
                "value": "This is a sample file description.",
            },
        ]
    }
)


class HeaderEditorViewModel:
    """State + logic for the TTTR Header Editor (no Qt)."""

    TYPE_MAPPING = {
        0xFFFF0008: "Empty",
        0x00000008: "Bool",
        0x10000008: "Int8",
        0x11000008: "BitSet64",
        0x12000008: "Color8",
        0x20000008: "Float8",
        0x21000008: "DateTime",
        0x2001FFFF: "Float8Array",
        0x4001FFFF: "AnsiString",
        0x4002FFFF: "WideString",
        0xFFFFFFFF: "BinaryBlob",
    }
    REVERSE_TYPE_MAPPING = {v: k for k, v in TYPE_MAPPING.items()}

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``header.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    #: Events listed in the photon preview table.
    _PHOTON_ROWS = 400

    def __init__(self) -> None:
        self.opened_path: str | None = None
        #: Canonical container name of the opened file (e.g. ``"ptu"``/``"ht3"``).
        self.source_container: str = ""
        self._parsed: dict = {}
        self.json_text: str = ""
        #: Read-only photon preview of the opened file (first ``_PHOTON_ROWS``
        #: events) and a one-line summary -- the Photons dock of the inspector.
        self.photon_rows: list[dict] = []
        self.photon_summary: str = ""
        self._observers: list = []
        self.load_json(SAMPLE_JSON)

    # ── source description ─────────────────────────────────────────────
    @property
    def source_summary(self) -> str:
        """Human-readable one-liner describing the loaded file, for the UI."""
        if not self.opened_path:
            return "No file loaded — showing a sample header."
        name = pathlib.Path(self.opened_path).name
        fmt = self.source_container.upper() or "TTTR"
        return f"{name}  ·  {fmt}  ·  {len(self.tags)} tags  →  saves as PTU"

    # ── observer hook ──────────────────────────────────────────────────
    def add_observer(self, cb) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("header observer failed", exc_info=True)

    def update(self) -> None:
        """AutoForm hook after a bound field changes (no-op; table drives state)."""

    # ── value conversion ───────────────────────────────────────────────
    def convert_value_by_type(self, value_str: str, type_str: str):
        """Convert *value_str* to the Python type implied by the tag *type_str*."""
        try:
            if type_str in ("Int8", "BitSet64", "Color8"):
                return int(value_str, 0) if value_str.lower().startswith("0x") else int(value_str)
            if type_str in ("Float8", "DateTime"):
                value = float(value_str)
                if not math.isfinite(value):
                    raise ValueError("Nonfinite numeric value")
                return value
            if type_str == "Float8Array":
                values = json.loads(value_str)
                if not isinstance(values, list) or not all(
                    isinstance(value, (int, float)) and math.isfinite(value) for value in values
                ):
                    raise ValueError("Expected a JSON array of finite numbers")
                return values
            if type_str == "Bool":
                if value_str.lower() not in ("true", "false", "1", "0"):
                    raise ValueError("Expected true, false, 1 or 0")
                return value_str.lower() in ("true", "1")
        except ValueError:
            raise ValueError(f"Invalid {type_str} value: {value_str}") from None
        return value_str

    # ── tags ───────────────────────────────────────────────────────────
    @property
    def tags(self) -> list[dict]:
        """The current header tags (``name`` / ``type`` int / ``value`` / ``idx``)."""
        return self._parsed.get("tags", [])

    def load_json(self, json_str: str) -> None:
        """Parse a header JSON string and refresh the table/JSON view."""
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("tags", []), list):
            raise ValueError("Expected a header object with a tags list.")
        self._parsed = parsed
        self._parsed.setdefault("tags", [])
        self._refresh_json_text()
        self.notify("loaded")

    def load_file(self, path: str) -> None:
        """Load the header tags from any :mod:`tttrlib`-readable file at *path*.

        The container type is auto-detected. PTU, HT3, SPC and Photon-HDF5 all
        expose the same tag list through ``tttrlib``.
        """
        tttr = tttrlib.TTTR(path)
        self.opened_path = path
        self.source_container = self._detect_container(path, tttr)
        self.load_json(tttr.header.json)
        self._photon_preview(tttr)

    def _photon_preview(self, tttr) -> None:
        """First events + a summary line for the Photons dock (never raises)."""
        try:
            mt, ut, rch = tttr.macro_times, tttr.micro_times, tttr.routing_channels
            n = int(tttr.n_valid_events) or int(tttr.n_records_in_file)
            k = min(n, self._PHOTON_ROWS)
            self.photon_rows = [
                {"i": i + 1, "rch": str(int(rch[i])),
                 "macro": f"{int(mt[i]):,}", "micro": str(int(ut[i]))}
                for i in range(k)
            ]
            used = sorted(int(c) for c in tttr.get_used_routing_channels())
            self.photon_summary = (
                f"{n:,} events · {tttr.acquisition_time:.1f} s · "
                f"record type {tttr.get_tttr_record_type()} · routing channels {used}"
            )
        except Exception:
            logger.debug("photon preview failed", exc_info=True)
            self.photon_rows, self.photon_summary = [], ""

    #: Backwards-compatible alias for :meth:`load_file`.
    load_ptu = load_file

    @staticmethod
    def _detect_container(path: str, tttr) -> str:
        """Best-effort canonical container name of the opened *tttr* file."""
        try:
            ct = tttrlib.inferTTTRContainerTypeFromExtension(pathlib.Path(path).suffix)
            name = tttrlib.tttrContainerCanonicalExtension(ct)
            if name:
                return name
        except Exception:
            logger.debug("container detection failed", exc_info=True)
        return pathlib.Path(path).suffix.lstrip(".").lower()

    def set_tags(self, rows: list[dict]) -> None:
        """Replace the tag list (each row: name, type-name str, value-str, idx).

        Rows arrive from the table widget with string types/values; they are
        normalised to the numeric tag type and Python value here.
        """
        tags = []
        for row in rows:
            type_str = row.get("type", "")
            type_code = self.REVERSE_TYPE_MAPPING.get(type_str)
            if type_code is None:
                type_code = row.get("raw_type")
                if type_code is None:
                    raise ValueError(f"Unknown tag type: {type_str}")
            if not str(row.get("name", "")).strip():
                raise ValueError("Tag name must not be empty.")
            try:
                idx = int(row.get("idx", -1))
            except (TypeError, ValueError):
                raise ValueError("Tag index must be an integer.") from None
            if idx < -1:
                raise ValueError("Tag index must be -1 or nonnegative.")
            tags.append(
                {
                    "name": row.get("name", ""),
                    "type": type_code,
                    "value": row.get("raw_value", row.get("value", ""))
                    if type_str not in self.REVERSE_TYPE_MAPPING
                    else self.convert_value_by_type(str(row.get("value", "")), type_str),
                    "idx": idx,
                }
            )
        self._parsed["tags"] = tags
        self._refresh_json_text()
        self.notify("json")

    def _refresh_json_text(self) -> None:
        self.json_text = json.dumps(self._parsed, indent=4)

    # ── save ───────────────────────────────────────────────────────────
    def can_save(self) -> str | None:
        """Return ``None`` when a save can run, else a human-readable reason."""
        if not self.opened_path:
            return "Open a TTTR file first (its photon data is copied into the new PTU)."
        return None

    def save(self, path: str) -> None:
        """Write a PTU at *path* with the source events and the edited tags.

        Output is always a PTU container: it is the only ``tttrlib`` container
        that persists arbitrary edited header tags without loss. HT3/SPC writers
        regenerate a fixed binary header and would drop custom tags, so a header
        edited from any source format is saved as PTU.
        """
        if not self.opened_path:
            raise ValueError("No source TTTR file is open.")
        path = str(path)
        if not path.lower().endswith(".ptu"):
            path += ".ptu"
        if pathlib.Path(path).resolve() == pathlib.Path(self.opened_path).resolve():
            raise ValueError("Choose a new file; saving over the source is not allowed.")
        src = tttrlib.TTTR(self.opened_path)
        out = tttrlib.TTTR()
        header_dict = json.loads(src.header.json)
        header_dict["tags"] = self._parsed.get("tags", [])
        out.header.set_json(json.dumps(header_dict))
        out.append_events(
            macro_times=src.macro_times,
            micro_times=src.micro_times,
            routing_channels=src.routing_channels,
            event_types=src.event_types,
        )
        destination = pathlib.Path(path)
        fd, temporary = tempfile.mkstemp(prefix=".header-", suffix=".ptu", dir=destination.parent)
        os.close(fd)
        try:
            result = out.write(temporary)
            if result is False or pathlib.Path(temporary).stat().st_size == 0:
                raise OSError("TTTR writer did not produce a PTU file.")
            os.replace(temporary, destination)
        finally:
            pathlib.Path(temporary).unlink(missing_ok=True)


__all__ = ["HeaderEditorViewModel"]
