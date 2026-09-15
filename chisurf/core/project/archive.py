from __future__ import annotations

import pathlib
import tempfile
from pathlib import PurePosixPath
from types import SimpleNamespace
from typing import Any

from .pto import PROJECT_SUFFIX, ProjectPtoError, read_entries, write_entries

PathLike = str | pathlib.Path

PROJECT_JSON = "project.json"
HISTORY_FILENAME = "history.jsonl"
SESSION_FILENAME = "session.jsonl"
DATA_DIR = "data"
PROJECT_ARCHIVE_SUFFIX = PROJECT_SUFFIX

# V5 MMFDB artifact layer
MMFDB_DIR = "mmfdb"
MMFDB_MANIFEST_JSON = "mmfdb/manifest.json"
MMFDB_PROVENANCE_JSONL = "mmfdb/provenance.jsonl"
MMFDB_OBJECTS_DIR = "mmfdb/objects"
EXPORT_JSON = "export.json"


class ProjectArchive:
    """In-memory view of a ptolib-backed ChiSurf project.

    Parameters
    ----------
    Entries are stored as individual PTO objects when saved.  The in-memory
    mapping keeps existing project assembly call sites independent from the
    container implementation while avoiding a ZIP-inside-PTO compatibility
    layer.
    """

    def __init__(self, compression: int | None = None) -> None:
        del compression
        self._entries: dict[str, bytes] = {}
        self._path: pathlib.Path | None = None

    @classmethod
    def open_bytes(cls, data: bytes) -> ProjectArchive:
        """Open an existing ``.cs.pto`` project from raw bytes.

        Parameters
        ----------
        data : bytes
            Raw archive bytes.

        Returns
        -------
        ProjectArchive
            Archive opened in read mode.

        Raises
        ------
        ValueError
            If the data is not a valid ZIP archive or does not contain
            ``project.json``.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / f"project{PROJECT_ARCHIVE_SUFFIX}"
            path.write_bytes(data)
            archive = cls.open(path)
        archive._path = None
        return archive

    @classmethod
    def open(cls, path: PathLike) -> ProjectArchive:
        """Open an existing ``.cs.pto`` project into memory.

        Parameters
        ----------
        path : str or pathlib.Path
            Path to the archive file.

        Returns
        -------
        ProjectArchive
            Archive opened in read mode.

        Raises
        ------
        ValueError
            If the file is not a valid ChiSurf PTO project.
        """
        archive_path = pathlib.Path(path)
        try:
            entries = read_entries(archive_path)
        except ProjectPtoError as exc:
            raise ValueError(str(exc)) from exc
        archive = cls()
        archive._entries = entries
        archive._path = archive_path
        return archive

    @classmethod
    def is_project_archive(cls, path: PathLike) -> bool:
        """Return whether a path points to a ChiSurf project archive.

        Parameters
        ----------
        path : str or pathlib.Path
            Path to test.

        Returns
        -------
        bool
            True if the path is a readable ``.cs.pto`` project with
            ``project.json``.
        """
        try:
            archive = cls.open(path)
        except Exception:
            return False
        archive.close()
        return True

    def write_text(self, name: str, text: str, overwrite: bool = False) -> None:
        """Write a UTF-8 text entry to the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.
        text : str
            Text content.
        overwrite : bool
            If True, overwrite an existing entry with the same name.

        Raises
        ------
        ValueError
            If the entry already exists (and *overwrite* is False) or the name is unsafe.
        """
        self.write_bytes(name, text.encode("utf-8"), overwrite=overwrite)

    def write_bytes(self, name: str, data: bytes | bytearray | memoryview, overwrite: bool = False) -> None:
        """Write a binary entry to the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.
        data : bytes-like
            Binary content.
        overwrite : bool
            If True, overwrite an existing entry with the same name.

        Raises
        ------
        ValueError
            If the entry already exists (and *overwrite* is False) or the name is unsafe.
        """
        archive_name = self._normalize_name(name)
        if archive_name in self._entries:
            if not overwrite:
                raise ValueError(f"Archive entry already exists: {archive_name}")
        self._entries[archive_name] = bytes(data)

    def write_file(self, name: str, path: PathLike, overwrite: bool = False) -> None:
        """Write a file from disk into the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.
        path : str or pathlib.Path
            Source file path.
        overwrite : bool
            If True, overwrite an existing entry with the same name.

        Raises
        ------
        FileNotFoundError
            If the source file does not exist.
        ValueError
            If the entry already exists (and *overwrite* is False) or the archive name is unsafe.
        """
        source_path = pathlib.Path(path)
        if not source_path.is_file():
            raise FileNotFoundError(str(source_path))

        self.write_bytes(name, source_path.read_bytes(), overwrite=overwrite)

    def save(self, path: PathLike) -> pathlib.Path:
        """Finalize the archive and write it to disk.

        Parameters
        ----------
        path : str or pathlib.Path
        Destination ``.cs.pto`` path.

        Returns
        -------
        pathlib.Path
            Destination path.
        """
        archive_path = write_entries(path, self._entries)
        self._path = archive_path
        return archive_path

    def to_bytes(self) -> bytes:
        """Finalize the archive and return its bytes.

        Returns
        -------
        bytes
        Complete ``.cs.pto`` project bytes.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / f"project{PROJECT_ARCHIVE_SUFFIX}"
            self.save(path)
            return path.read_bytes()

    def read_text(self, name: str) -> str:
        """Read a UTF-8 text entry from the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.

        Returns
        -------
        str
            Entry text.
        """
        return self.read_bytes(name).decode("utf-8")

    def read_bytes(self, name: str) -> bytes:
        """Read a binary entry from the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.

        Returns
        -------
        bytes
            Entry bytes.
        """
        return self._entries[self._normalize_name(name)]

    def has_entry(self, name: str) -> bool:
        """Return whether an entry exists in the archive.

        Parameters
        ----------
        name : str
            Archive-internal entry name.

        Returns
        -------
        bool
            True if the entry exists.
        """
        return self._normalize_name(name) in self._entries

    def getinfo(self, name: str) -> Any:
        """Return metadata for an archive entry.

        Parameters
        ----------
        name : str
            Archive-internal entry name.

        Returns
        -------
        object
            Entry metadata with ``filename`` and ``file_size`` attributes.
        """
        entry = self._normalize_name(name)
        if entry not in self._entries:
            raise KeyError(entry)
        return SimpleNamespace(filename=entry, file_size=len(self._entries[entry]))

    def list_entries(self) -> list[str]:
        """Return archive entry names.

        Returns
        -------
        list of str
            Entry names in archive order.
        """
        return list(self._entries)

    def extract_to(self, target_dir: PathLike) -> pathlib.Path:
        """Extract all entries to a directory.

        Parameters
        ----------
        target_dir : str or pathlib.Path
            Destination directory.

        Returns
        -------
        pathlib.Path
            Destination directory.
        """
        destination = pathlib.Path(target_dir)
        destination.mkdir(parents=True, exist_ok=True)
        for name in self.list_entries():
            self.extract_entry_to(name, destination)
        return destination

    def extract_to_temp(self) -> tuple[pathlib.Path, tempfile.TemporaryDirectory]:
        """Extract all entries to a temporary directory.

        Returns
        -------
        tuple of pathlib.Path and tempfile.TemporaryDirectory
            Temporary directory path and its handle. Keep the handle alive until
            the extracted files are no longer needed.
        """
        temp_dir = tempfile.TemporaryDirectory(prefix="chisurf_project_")
        self.extract_to(temp_dir.name)
        return pathlib.Path(temp_dir.name), temp_dir

    def extract_entry_to(self, name: str, target_dir: PathLike) -> pathlib.Path:
        """Extract one entry to a directory.

        Parameters
        ----------
        name : str
            Archive-internal entry name.
        target_dir : str or pathlib.Path
            Destination directory.

        Returns
        -------
        pathlib.Path
            Extracted file path.
        """
        destination = self._safe_destination(target_dir, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.read_bytes(name))
        return destination

    def close(self) -> None:
        """Release in-memory entries retained by this archive view."""

    def write_mmfdb_layer(
        self,
        manifest: dict[str, Any],
        provenance_lines: list[str],
        object_blobs: dict[str, bytes] | None = None,
        overwrite: bool = False,
    ) -> None:
        """Write the V5 MMFDB artifact layer to the archive.

        Parameters
        ----------
        manifest : dict
            Artifact registry (``mmfdb/manifest.json`` content).
        provenance_lines : list of str
            JSONL lines for ``mmfdb/provenance.jsonl``.
        object_blobs : dict, optional
            Mapping of ``{object_uuid: blob_bytes}`` to write under
            ``mmfdb/objects/``.
        overwrite : bool, default=False
            If True, overwrite existing entries.
        """
        import json as _json

        self.write_text(
            MMFDB_MANIFEST_JSON,
            _json.dumps(manifest, sort_keys=True, ensure_ascii=True, indent=2),
            overwrite=overwrite,
        )
        self.write_text(
            MMFDB_PROVENANCE_JSONL,
            "\n".join(provenance_lines) + "\n" if provenance_lines else "",
            overwrite=overwrite,
        )
        if object_blobs:
            for obj_uuid, blob in object_blobs.items():
                entry_name = f"{MMFDB_OBJECTS_DIR}/{obj_uuid}.blob"
                self.write_bytes(entry_name, blob, overwrite=overwrite)

    def __enter__(self) -> ProjectArchive:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _normalize_name(self, name: str) -> str:
        archive_name = name.replace("\\", "/")
        if archive_name.startswith("/"):
            archive_name = archive_name.lstrip("/")
        path = PurePosixPath(archive_name)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise ValueError(f"Unsafe archive entry name: {name!r}")
        if not path.parts:
            raise ValueError(f"Empty archive entry name: {name!r}")
        return path.as_posix()

    def _safe_destination(self, target_dir: PathLike, name: str) -> pathlib.Path:
        root = pathlib.Path(target_dir).resolve()
        destination = (root / self._normalize_name(name)).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(f"Unsafe archive extraction path: {name!r}")
        return destination
