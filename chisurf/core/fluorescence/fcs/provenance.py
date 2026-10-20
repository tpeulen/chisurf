"""The settings file beside every computed correlation: what reproduces it from the raw photons, Qt-free.

A correlation written as ``<name>.cor`` is accompanied by ``<name>.cor.json``. The record names every raw photon file
by path, size and SHA-256, the photons used from each (its time regions), how the files were read, the photon filter,
the correlator settings and which correlated pieces the merge averaged — everything
:func:`chisurf.plugins.fcs.fcs_correlator.provenance.reproduce` needs to compute the same curve again. A ``.cor`` merged
from correlation files rather than from photons names those files instead (``"source": "correlations"``): it can be
re-merged, not re-correlated.

The record is plain JSON so it can be read without ChiSurf; ``kind`` and ``version`` say what it is.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
from typing import Any

#: The ``kind`` of a correlation settings record, and the version of its layout.
KIND = "chisurf.fcs.correlation"
VERSION = 1


def settings_path(cor_path) -> pathlib.Path:
    """The settings file of *cor_path*: ``<name>.cor`` → ``<name>.cor.json``."""
    cor_path = pathlib.Path(cor_path)
    return cor_path.with_name(cor_path.name + ".json")


def sha256(path, chunk: int = 1 << 22) -> str:
    """Hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def file_entry(path, **extra) -> dict[str, Any]:
    """``{path, name, size, sha256, **extra}`` of a file the result was computed from."""
    path = pathlib.Path(path).resolve()
    return {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256(path),
        **extra,
    }


def complete_inputs(record: dict) -> dict:
    """*record* with the name, size and SHA-256 of every input file that lacks them (checksums are taken when a
    result is written, off the drawing thread)."""
    inputs = []
    for entry in record.get("inputs", []):
        entry = dict(entry)
        path = pathlib.Path(entry.get("path", ""))
        if "sha256" not in entry and path.is_file():
            entry.update(name=path.name, size=path.stat().st_size, sha256=sha256(path))
        inputs.append(entry)
    return {**record, "inputs": inputs}


def software_versions() -> dict[str, str]:
    """The versions of ChiSurf and tttrlib that computed the result."""
    versions: dict[str, str] = {}
    try:
        import chisurf

        versions["chisurf"] = str(getattr(chisurf, "__version__", "") or "")
    except Exception:  # noqa: BLE001 - a record without the version is still a record
        pass
    try:
        import tttrlib

        versions["tttrlib"] = str(getattr(tttrlib, "__version__", "") or "")
    except Exception:  # noqa: BLE001
        pass
    return versions


def new_record(source: str, **fields) -> dict[str, Any]:
    """A record of *source* (``"photons"`` or ``"correlations"``) with its header filled in."""
    return {
        "kind": KIND,
        "version": VERSION,
        "source": source,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "software": software_versions(),
        **fields,
    }


def write_settings(cor_path, record: dict) -> pathlib.Path:
    """Write *record* beside *cor_path*, with the output's own name and checksum added; its path."""
    cor_path = pathlib.Path(cor_path)
    record = dict(record)
    record["output"] = {"file": cor_path.name, "sha256": sha256(cor_path)}
    target = settings_path(cor_path)
    target.write_text(json.dumps(record, indent=2, default=_jsonable) + "\n", encoding="utf-8")
    return target


def read_settings(path) -> dict:
    """The record in *path* (a settings file, or the ``.cor`` it belongs to)."""
    path = pathlib.Path(path)
    if path.suffix.lower() == ".cor":
        path = settings_path(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("kind") != KIND:
        raise ValueError(f"{path} is not a correlation settings file (kind {record.get('kind')!r}).")
    if int(record.get("version", 0)) > VERSION:
        raise ValueError(f"{path} has layout version {record['version']}; this ChiSurf reads up to {VERSION}.")
    return record


def _jsonable(value):
    """JSON form of the values settings carry besides the JSON types (paths, numpy scalars and arrays)."""
    if isinstance(value, pathlib.Path):
        return str(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return str(value)


__all__ = [
    "KIND",
    "VERSION",
    "complete_inputs",
    "file_entry",
    "new_record",
    "read_settings",
    "settings_path",
    "sha256",
    "software_versions",
    "write_settings",
]
