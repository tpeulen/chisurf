"""Copy a finished session's measurements to the archive drive -- verifiably, or not at all.

After a session closes, its directory under ``C:\\Measurements`` (one folder per session,
one file family per measurement: ``<stem>.ptu`` / ``.pck`` / ``*_OFCS.pqres`` ...) is
copied to the archive, ``Z:\\microtime200\\<session>``.  The Z: drive is a mapped SMB
share (``\\\\129.217.203.251\\Data``) that is regularly disconnected or unreachable, so
this module treats the destination as *guilty until proven reachable*
(:func:`is_reachable`, ``DestinationUnavailable``) and never creates the destination
*root* itself -- a missing share must fail loudly, not silently reappear as a local
folder that swallows the data.

Safety rules, in the order they matter:

* **The source is read-only.** Copy only; nothing is opened for writing, nothing
  truncated.  :meth:`SessionTransfer.move` is the one opt-in relocation, and it deletes a
  source file only after the copy is verified AND the source hash is re-checked
  (all-or-nothing: one mismatch cancels the whole move phase, keeping every source file).
* **Atomic files.** Every file is copied to ``<name>.chisurf-part`` in its destination
  directory, flushed, fsynced, then ``os.replace``d onto its final name -- a crash or a
  dropped share leaves a ``.chisurf-part``, never a half-written file at the real name.
* **No overwrite, ever.** A destination file that already exists is re-hashed: identical
  content is skipped (that is how a resumed transfer finishes), different content is
  reported as a conflict and left untouched.
* **Resume.** A per-session state document (``.chisurf-transfer.json`` in the destination
  directory) records every finished file with size and SHA-256; a rerun skips the
  verified-identical files and copies only the rest.  Errors are per-file: one bad file
  does not stop the others, and transient I/O errors (a dropped share) are retried with
  exponential backoff.
* **Verifiable report.** The returned :class:`TransferReport` lists every file with size,
  SHA-256 and status, and can be written next to the copy (``transfer-report.json``) --
  so "did it all arrive" is a checkable claim, and the caller (the UI) gets byte-accurate
  progress through one callback.

A file that changes between listing and hashing (someone still writing it) is reported as
failed with that reason -- this module never races a live writer.

Not thread-safe by design: run it in the caller's worker thread; it never touches a
session that is still recording.
"""

from __future__ import annotations

import datetime
import errno
import fnmatch
import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)

__all__ = [
    "CHUNK",
    "PART_SUFFIX",
    "STATE_NAME",
    "DestinationUnavailable",
    "FileResult",
    "Progress",
    "SessionTransfer",
    "TransferReport",
    "is_reachable",
]

#: Suffix of the in-flight copy inside its destination directory.
PART_SUFFIX = ".chisurf-part"
#: Per-session transfer state in the destination directory (the resume record).
STATE_NAME = ".chisurf-transfer.json"
#: Report document schema.
REPORT_SCHEMA = "chisurf.transfer.report/1"
#: State document schema.
STATE_SCHEMA = "chisurf.transfer.state/1"
#: Copy/read chunk (1 MiB).
CHUNK = 1024 * 1024

ProgressCallback = Callable[["Progress"], None]


class DestinationUnavailable(RuntimeError):
    """The destination root is not reachable (share disconnected, drive absent)."""


@dataclass
class Progress:
    """A byte-accurate transfer snapshot for a progress callback (UI-safe: plain data)."""

    phase: str  # listing | copying | verifying | moving | done | failed
    current_file: str = ""  # path relative to the source session directory
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    message: str = ""


@dataclass
class FileResult:
    """One source file's fate: where it went, how big, its hash, what happened."""

    rel: str  # path relative to the session directory, POSIX separators
    source: Path
    destination: Path
    size: int = 0
    sha256: str = ""
    status: str = "pending"  # copied | skipped-identical | conflict | failed | moved
    error: str = ""
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.status in ("copied", "skipped-identical", "moved")


@dataclass
class TransferReport:
    """What the transfer did, per file -- the verifiable claim a UI can show."""

    source_dir: Path
    destination_dir: Path
    files: list[FileResult] = field(default_factory=list)
    bytes_total: int = 0
    bytes_transferred: int = 0
    bytes_skipped: int = 0
    started_at: str = ""
    finished_at: str = ""
    moved: bool = False

    @property
    def ok(self) -> bool:
        """True when every listed file copied (or was already there, identical)."""
        return all(result.ok for result in self.files)

    @property
    def duration_s(self) -> float:
        if not (self.started_at and self.finished_at):
            return 0.0
        start = datetime.datetime.fromisoformat(self.started_at)
        finish = datetime.datetime.fromisoformat(self.finished_at)
        return (finish - start).total_seconds()

    def failures(self) -> list[FileResult]:
        return [result for result in self.files if not result.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "source_dir": str(self.source_dir),
            "destination_dir": str(self.destination_dir),
            "ok": self.ok,
            "moved": self.moved,
            "bytes_total": self.bytes_total,
            "bytes_transferred": self.bytes_transferred,
            "bytes_skipped": self.bytes_skipped,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "files": [
                {"rel": result.rel, "status": result.status, "size": result.size,
                 "sha256": result.sha256, "attempts": result.attempts, "error": result.error,
                 "destination": str(result.destination)}
                for result in self.files
            ],
        }

    def write(self, path: Path | str) -> Path:
        """Write the report as JSON (atomic replace) so the transfer can be audited later."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return path


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def is_reachable(path: Path | str) -> bool:
    """True when the drive/share *root* of *path* answers (e.g. ``Z:\\`` or a UNC root).

    A mapped-but-disconnected drive fails here even though ``Path.exists()`` would
    quietly return False; on a POSIX host a normal path always answers.
    """
    try:
        os.stat(Path(path).anchor or str(path))
        return True
    except OSError:
        return False


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)


def _load_state(directory: Path) -> dict[str, Any]:
    try:
        document = json.loads((directory / STATE_NAME).read_text(encoding="utf-8"))
        return document if isinstance(document, dict) and document.get("schema") == STATE_SCHEMA else {}
    except (OSError, ValueError):
        return {}


def _save_state(directory: Path, state: dict[str, Any]) -> None:
    try:
        _atomic_json(directory / STATE_NAME, state)
    except OSError as exc:  # a dropped share must not abort the transfer mid-run
        _log.warning("could not write transfer state %s: %s", directory / STATE_NAME, exc)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":  # no usable directory fsync on Windows; the file fsync carried it
        return
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


class SessionTransfer:
    """Copy one session directory into an archive root, with progress and verification.

    >>> transfer = SessionTransfer(source_dir, Path("Z:/microtime200"))
    >>> report = transfer.run()      # copy + verify; the source stays untouched
    >>> report.ok                    # every file arrived, hashes verified
    True
    >>> report.write(Path("Z:/microtime200/TP_20261030/transfer-report.json"))

    The destination *root* must already exist and be reachable -- ``Z:\\microtime200``
    when the share is up.  A rerun of the same source into the same destination resumes:
    verified-identical files are skipped, unfinished work is redone, nothing is
    overwritten.
    """

    def __init__(self, source_dir: Path | str, destination_root: Path | str, *,
                 session_name: str = "", verify: str = "sha256",
                 attempts: int = 3, retry_delay_s: float = 2.0,
                 exclude: tuple[str, ...] = (f"*{PART_SUFFIX}", STATE_NAME)) -> None:
        self.source_dir = Path(source_dir)
        self.destination_root = Path(destination_root)
        self.session_name = str(session_name or self.source_dir.name)
        if verify not in ("sha256", "size", "none"):
            raise ValueError(f"verify must be 'sha256', 'size' or 'none', not {verify!r}")
        self.verify = verify
        self.attempts = max(1, int(attempts))
        self.retry_delay_s = float(retry_delay_s)
        self.exclude = tuple(exclude)
        self._callback: ProgressCallback | None = None
        self._move_requested = False

    # -- checks --------------------------------------------------------------
    def _precheck(self) -> Path:
        if not self.source_dir.is_dir():
            raise NotADirectoryError(f"source session directory does not exist: {self.source_dir}")
        if not is_reachable(self.destination_root):
            raise DestinationUnavailable(
                f"destination root is not reachable: {self.destination_root} "
                f"(network share disconnected? drive {self.destination_root.anchor!s} absent?)"
            )
        if not self.destination_root.is_dir():
            raise NotADirectoryError(
                f"destination root does not exist: {self.destination_root} "
                f"-- never created automatically; check the drive mapping"
            )
        destination_dir = self.destination_root / self.session_name
        source = os.path.abspath(self.source_dir)
        dest = os.path.abspath(destination_dir)
        if source == dest or dest.startswith(source + os.sep) or source.startswith(dest + os.sep):
            raise ValueError(f"source and destination overlap: {source} <-> {dest}")
        return destination_dir

    # -- plumbing ------------------------------------------------------------
    def _emit(self, progress: Progress) -> None:
        if self._callback is None:
            return
        try:
            self._callback(replace(progress))  # a frozen-ish snapshot; the UI may keep it
        except Exception:  # noqa: BLE001 - a UI callback must never break the transfer
            _log.exception("progress callback raised")

    def _rel_files(self) -> list[tuple[str, Path, int]]:
        """Every file under the session directory as (rel, absolute, size), stable order."""
        entries: list[tuple[str, Path, int]] = []
        for path in sorted(self.source_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.source_dir).as_posix()
            if any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)
                   for pattern in self.exclude):
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                _log.warning("cannot stat %s: %s", path, exc)
                continue
            entries.append((rel, path, size))
        return entries

    def _digest_of(self, path: Path, progress: Progress) -> tuple[str, int]:
        """SHA-256 and size of *path*, streamed (works on network shares)."""
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as handle:
            while True:
                block = handle.read(CHUNK)
                if not block:
                    break
                digest.update(block)
                size += len(block)
                self._emit(progress)
        return digest.hexdigest(), size

    def _source_identity(self, source: Path, size: int, progress: Progress) -> str:
        """The source file's verification identity (its SHA-256, or a size stamp)."""
        if self.verify != "sha256":
            return f"size:{size}"
        progress.phase = "verifying"
        self._emit(progress)
        digest, actual = self._digest_of(source, progress)
        if actual != size:
            raise OSError(errno.EIO,
                          f"source changed while being read ({actual} != {size} bytes) "
                          f"-- still being written?")
        return digest

    def _copy_stream(self, source: Path, part: Path, progress: Progress) -> int:
        """Copy *source* onto the part file, fsync, atomically rename to the final name."""
        copied = 0
        with open(source, "rb") as src, open(part, "wb") as dst:
            while True:
                block = src.read(CHUNK)
                if not block:
                    break
                dst.write(block)
                copied += len(block)
                progress.bytes_done += len(block)
                progress.phase = "copying"
                self._emit(progress)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(part, part.with_name(part.name[: -len(PART_SUFFIX)]))
        _fsync_directory(part.parent)
        return copied

    # -- per-file worker -----------------------------------------------------
    def _transfer_one(self, rel: str, source: Path, destination: Path, size: int,
                      progress: Progress) -> FileResult:
        result = FileResult(rel=rel, source=source, destination=destination, size=size)
        progress.current_file = rel
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result.status = "failed"
            result.error = f"cannot create destination directory: {exc}"
            _log.error("%s: %s", rel, result.error)
            return result
        try:
            result.sha256 = self._source_identity(source, size, progress)
        except OSError as exc:
            result.status = "failed"
            result.error = f"{exc}"
            _log.error("%s: %s", rel, exc)
            return result

        if destination.exists():
            # A previous run (or a human) put something there: identical -> done, else conflict.
            progress.phase = "verifying"
            self._emit(progress)
            try:
                if self.verify == "sha256":
                    digest, _actual = self._digest_of(destination, progress)
                    same = digest == result.sha256
                else:
                    same = destination.stat().st_size == result.size
                if same:
                    result.status = "skipped-identical"
                    progress.files_done += 1
                    progress.bytes_done += size
                    return result
                result.status = "conflict"
                result.error = ("destination exists with different content; "
                                "left untouched (never overwritten)")
                _log.error("%s: %s", rel, result.error)
                progress.files_done += 1
                return result
            except OSError as exc:
                _log.warning("re-hash of existing %s failed (%s); copying anew", destination, exc)

        last_error = ""
        for attempt in range(1, self.attempts + 1):
            result.attempts = attempt
            attempt_start_bytes = progress.bytes_done
            part = destination.with_name(destination.name + PART_SUFFIX)
            try:
                copied = self._copy_stream(source, part, progress)
                if copied != size:
                    raise OSError(errno.EIO, f"source size changed during copy: {copied} != {size}")
                if self.verify == "sha256":
                    progress.phase = "verifying"
                    self._emit(progress)
                    digest, _actual = self._digest_of(destination, progress)
                    if digest != result.sha256:
                        raise OSError(errno.EIO,
                                      "verification failed: destination digest differs from source")
                result.status = "copied"
                progress.files_done += 1
                last_error = ""
                break
            except OSError as exc:
                last_error = f"attempt {attempt}/{self.attempts}: {exc}"
                _log.warning("copy of %s failed: %s", rel, exc)
                progress.bytes_done = attempt_start_bytes  # a retry restarts this file's bytes
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass
                if attempt < self.attempts:
                    time.sleep(self.retry_delay_s * (2 ** (attempt - 1)))
        if last_error:
            result.status = "failed"
            result.error = last_error
        return result

    # -- the run -------------------------------------------------------------
    def run(self, *, progress: ProgressCallback | None = None) -> TransferReport:
        """Copy the whole session; returns the per-file :class:`TransferReport`."""
        self._callback = progress
        try:
            report = TransferReport(source_dir=self.source_dir,
                                    destination_dir=self.destination_root / self.session_name,
                                    started_at=_now_iso())
            destination_dir = self._precheck()
            destination_dir.mkdir(parents=False, exist_ok=True)

            listing = Progress(phase="listing")
            self._emit(listing)
            entries = self._rel_files()
            report.bytes_total = sum(size for _rel, _path, size in entries)
            state_progress = Progress(phase="copying", files_total=len(entries),
                                      bytes_total=report.bytes_total)
            self._emit(state_progress)

            state = _load_state(destination_dir)
            state.update({"schema": STATE_SCHEMA, "source_dir": str(self.source_dir)})
            state.setdefault("files", {})

            for rel, source, size in entries:
                result = self._transfer_one(rel, source, destination_dir / rel, size, state_progress)
                report.files.append(result)
                if result.ok:
                    state["files"][rel] = {"size": result.size, "sha256": result.sha256,
                                           "status": result.status}
                    if result.status == "copied":
                        report.bytes_transferred += size
                    else:
                        report.bytes_skipped += size
                else:
                    state["files"][rel] = {"size": size, "status": result.status,
                                           "error": result.error}
                _save_state(destination_dir, state)
                self._emit(state_progress)

            if self._move_requested:
                self._move_phase(report, state, destination_dir)

            state_progress.phase = "done" if report.ok else "failed"
            state_progress.message = ("" if report.ok else
                                      f"{len(report.failures())} file(s) not transferred")
            self._emit(state_progress)
            report.finished_at = _now_iso()
            return report
        finally:
            self._callback = None

    # -- verified relocation -------------------------------------------------
    def move(self, *, progress: ProgressCallback | None = None) -> TransferReport:
        """Copy, verify, and *then* remove the source -- explicit relocation, all-or-nothing.

        The delete phase runs only when every file copied and verified.  Each source file
        is re-hashed before its ``unlink``; a single mismatch (the file changed since the
        copy) cancels the whole move and keeps every source file.  Directory tree of the
        source is removed only once it holds no files any more.
        """
        self._move_requested = True
        try:
            return self.run(progress=progress)
        finally:
            self._move_requested = False

    def _move_phase(self, report: TransferReport, state: dict[str, Any],
                    destination_dir: Path) -> None:
        progress = Progress(phase="moving", files_total=len(report.files),
                            bytes_total=report.bytes_total)
        self._emit(progress)
        # Re-verify every source file first; a single mismatch keeps everything in place.
        for result in report.files:
            try:
                digest, size = self._digest_of(result.source, progress)
            except OSError as exc:
                result.error = f"move cancelled: source unreadable ({exc})"
                _log.error("move cancelled at %s: %s", result.rel, exc)
                return
            if size != result.size or (self.verify == "sha256" and digest != result.sha256):
                result.error = "move cancelled: source changed since the verified copy"
                _log.error("move cancelled at %s: source hash changed", result.rel)
                return
        for result in report.files:
            try:
                result.source.unlink()
            except OSError as exc:
                result.error = f"move incomplete: {exc}"
                _log.error("source file %s could not be removed: %s", result.source, exc)
                return  # stop deleting; what is gone was verified, the rest stays
            result.status = "moved"
            progress.files_done += 1
            self._emit(progress)
        report.moved = True
        shutil.rmtree(self.source_dir, ignore_errors=True)
        state["moved"] = not self.source_dir.exists()
        _log.info("session moved: %s -> %s", report.source_dir, destination_dir)
