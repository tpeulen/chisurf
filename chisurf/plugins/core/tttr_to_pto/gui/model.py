"""Qt-free model of the TTTR <-> .pto conversion tool.

Holds the history of conversions the user asked for and runs them one at a
time on a worker: the drop decides the direction (a vendor file is packed, a
``.pto`` is unpacked), vendor files of one drop are packed into one container
in file-name order, and nothing the user dropped is ever deleted. The calls
are :func:`~chisurf.plugins.core.tttr_to_pto.api.convert` and
:func:`~chisurf.plugins.core.tttr_to_pto.api.extract`, the same ones the Qt
drop tool uses.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from pathlib import Path

from chisurf.core.fio import staging
from chisurf.core.fio.pto import SIDECAR_ONLY_EXTENSIONS, Measurement, is_measurement
from chisurf.core.fio.pto import SUFFIX as PTO_SUFFIX
from chisurf.plugins.core.tttr_to_pto import api
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

#: The filter the Add files dialog offers.
FILE_FILTERS = (
    "Photon files and .pto containers (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r *.spc *.sptw *.pto)"
    ";;All files (*)"
)

STATUS_LABELS = {
    "queued": "Queued",
    "running": "Converting...",
    "verified": "Verified",
    "error": "Failed",
    "rejected": "Rejected",
    "interrupted": "Not completed",
}
ACTION_LABELS = {"pack": "Pack", "unpack": "Unpack", "reject": "-"}


class TttrToPtoModel:
    """The conversion history and its serial worker."""

    def __init__(self, converter=None, extractor=None) -> None:
        self.converter = converter or api.convert
        self.extractor = extractor or api.extract
        self.rows: list[dict] = []
        self.pending: deque = deque()
        self.job = BackgroundJob()
        self.closed = False
        #: ``"add"`` while the app has to open the file dialog.
        self.request = ""
        #: The folder of the last file chosen (the dialog starts there).
        self.last_dir = ""
        self._next_id = 0
        self._records: list[dict] = []
        self._records_key: tuple | None = None

    # ── what the spec reads ───────────────────────────────────────────
    @staticmethod
    def accepts(path) -> bool:
        """An existing vendor photon file or ``.pto`` container (never a lone sidecar)."""
        path = Path(path)
        suffix = path.suffix.lower()
        return path.is_file() and (
            suffix == PTO_SUFFIX
            or (
                suffix not in SIDECAR_ONLY_EXTENSIONS
                and (suffix in staging.VENDOR_EXTENSIONS or is_measurement(path))
            )
        )

    @property
    def records(self) -> list[dict]:
        """One table record per history row (rebuilt only when a row changed)."""
        key = tuple(
            (row["id"], row["status"], tuple(row["outputs"]), row["error"]) for row in self.rows
        )
        if key != self._records_key:
            self._records = [self._record(row) for row in self.rows]
            self._records_key = key
        return self._records

    @staticmethod
    def _record(row: dict) -> dict:
        names = ", ".join(Path(p).name for p in row["paths"])
        if row["outputs"]:
            result = ", ".join(Path(p).name for p in row["outputs"])
        else:
            result = row["error"]
        detail = "\n".join(row["paths"])
        if row["outputs"]:
            detail += "\n->\n" + "\n".join(row["outputs"])
        if row["error"]:
            detail += "\n" + row["error"]
        return {
            "id": row["id"],
            "status": STATUS_LABELS[row["status"]],
            "action": ACTION_LABELS[row["action"]],
            "files": names,
            "result": result,
            "detail": detail,
        }

    @property
    def running(self) -> bool:
        return self.job.running

    @property
    def status_text(self) -> str:
        """One line: nothing yet, converting, or the counts."""
        if not self.rows:
            return "No conversions yet. Drop files on this window or press Add files."
        counts = {key: 0 for key in STATUS_LABELS}
        for row in self.rows:
            counts[row["status"]] += 1
        parts = [f"{counts[k]} {STATUS_LABELS[k].lower().rstrip('.')}" for k in STATUS_LABELS if counts[k]]
        n = len(self.rows)
        return f"{n} {'entry' if n == 1 else 'entries'}: " + ", ".join(parts)

    def enabled(self, name: str) -> bool:
        if name == "clear_history":
            return any(row["status"] not in {"queued", "running"} for row in self.rows)
        return True

    # ── actions ───────────────────────────────────────────────────────
    def request_add(self) -> None:
        self.request = "add"

    def add_paths(self, paths) -> bool:
        """Unpack each container; pack all vendor files of this call together.

        Returns whether anything was accepted. A rejected path (a lone sidecar,
        a missing file, an unknown type) is listed as such and never touched.
        """
        if self.closed:
            return False
        vendors: list[str] = []
        accepted = False
        for value in dict.fromkeys(str(Path(p).expanduser().resolve()) for p in paths):
            path = Path(value)
            if not self.accepts(path):
                sidecar = path.suffix.lower() in SIDECAR_ONLY_EXTENSIONS
                self._append(
                    [value],
                    "reject",
                    "rejected",
                    error="Sidecars need their .spc file."
                    if sidecar
                    else "Choose existing vendor photon files or PTO containers.",
                )
                continue
            accepted = True
            self.last_dir = str(path.parent)
            if path.suffix.lower() == PTO_SUFFIX or is_measurement(path):
                self.enqueue("unpack", [value])
            else:
                vendors.append(value)
        if vendors:
            self.enqueue("pack", sorted(vendors, key=lambda p: Path(p).name))
        self.start_next()
        return accepted

    def _append(self, paths, action, status, error="") -> dict:
        self._next_id += 1
        row = {
            "id": str(self._next_id),
            "paths": paths,
            "action": action,
            "status": status,
            "outputs": [],
            "error": error,
        }
        self.rows.append(row)
        return row

    def enqueue(self, action: str, paths: list) -> None:
        self.pending.append(self._append(paths, action, "queued"))

    def start_next(self) -> None:
        """Start the next queued conversion when no write is running."""
        if self.closed or self.job.running or not self.pending:
            return
        row = self.pending.popleft()
        row["status"] = "running"

        def work():
            if row["action"] == "pack":
                target = self.converter(row["paths"], keep_original=True)
                # The explicit tool verifies every write, even when keeping the sources.
                with Measurement.open(target, writable=False) as check:
                    problems = check.verify()
                if problems:
                    raise ValueError("; ".join(problems))
                return [str(target)]
            return [str(p) for p in self.extractor(row["paths"][0])]

        def publish(outputs):
            row.update(status="verified", outputs=outputs)

        def error(exc):
            row.update(status="error", error=str(exc))

        self.job.start(work, publish, error)

    def poll(self) -> None:
        """Publish a finished conversion (frame thread) and start the next one."""
        self.job.poll()
        self.start_next()

    def clear_history(self) -> None:
        """Forget the finished entries; the files on disk stay as they are."""
        self.rows[:] = [row for row in self.rows if row["status"] in {"queued", "running"}]

    # ── persistence ───────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """The history (documentary) and the last folder."""
        return {"history": deepcopy(self.rows), "last_dir": self.last_dir}

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`; unfinished rows are marked, never replayed."""
        if self.job.running:
            raise RuntimeError("Cannot restore conversion history while a write is active.")
        self.pending.clear()
        self.rows = deepcopy(state.get("history", []))
        for index, row in enumerate(self.rows):
            row.setdefault("id", str(index + 1))
            if row.get("status") in {"queued", "running"}:
                row["status"] = "interrupted"
        self._next_id = max([int(r["id"]) for r in self.rows if str(r["id"]).isdigit()] + [0])
        self.last_dir = str(state.get("last_dir", "") or "")

    def close(self) -> None:
        """Stop queued work; a write in progress finishes safely."""
        self.closed = True
        for row in self.pending:
            row["status"] = "interrupted"
        self.pending.clear()
        self.job.close()
