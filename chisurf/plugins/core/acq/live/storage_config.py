"""Explicit local and archive directories in an acquisition JSON profile.

A missing archive is not silently substituted: the caller can keep local data and
report that transfers are not configured. Windows path strings remain verbatim
when reading profiles on other operating systems.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class StorageConfigError(ValueError):
    """The profile does not provide valid storage settings."""


@dataclass(frozen=True)
class StorageConfig:
    """Configured local measurement and archive root paths."""

    local_directory: str
    archive_directory: str

    @classmethod
    def from_document(cls, document: object) -> StorageConfig:
        """Read path settings without touching either directory."""
        section = document.get("storage") if isinstance(document, dict) else None
        if not isinstance(section, dict):
            raise StorageConfigError("storage: missing object")
        for key in ("local_directory", "archive_directory"):
            value = section.get(key)
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise StorageConfigError(f"storage.{key}: expected a nonempty path string")
        return cls(section["local_directory"], section["archive_directory"])

    @classmethod
    def from_file(cls, path: str | Path) -> StorageConfig:
        """Read the selected JSON profile without creating files or directories."""
        try:
            with Path(path).open(encoding="utf-8") as stream:
                document = json.load(stream)
        except (OSError, ValueError) as exc:
            raise StorageConfigError(f"cannot read storage settings: {exc}") from exc
        return cls.from_document(document)
