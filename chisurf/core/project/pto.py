"""The ptolib-backed ``.cs.pto`` transport for a ChiSurf project.

This module intentionally owns only the container profile.  ``Project`` owns
the scientific schema, while BFF owns native graph serialisation.  Keeping the
three concerns separate makes a project file inspectable with a generic PTO
reader without creating a second project-state implementation.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from collections.abc import Mapping
from typing import Any

PROJECT_SUFFIX = ".cs.pto"
PROFILE = "ChiSurf.Project"
PROFILE_VERSION = 1

_PROJECT_KIND = "chisurf.project"
_PROJECT_ENCODING = "json"
_PROJECT_NAME = "project"
_SESSION_KIND = "chisurf.graph-session"
_SESSION_ENCODING = "jsonl"
_SESSION_NAME = "session"
_ARCHIVE_ENTRY_KIND = "chisurf.project-entry"


class ProjectPtoError(RuntimeError):
    """A PTO file cannot be used as a complete ChiSurf project."""


def _tttrlib():
    try:
        import tttrlib
    except ImportError as exc:  # pragma: no cover - dependency error is environment-specific
        raise ProjectPtoError("Saving a .cs.pto project requires tttrlib/ptolib") from exc
    return tttrlib


def _object_uid(handle: Any, kind: str, name: str) -> int:
    matches = [obj.uid for obj in handle.objects() if obj.kind == kind and obj.name == name]
    if len(matches) != 1:
        raise ProjectPtoError(
            f"Expected exactly one {kind!r} object named {name!r}; found {len(matches)}"
        )
    return int(matches[0])


def _problems(handle: Any) -> list[str]:
    try:
        return [str(problem) for problem in handle.verify()]
    except Exception as exc:
        raise ProjectPtoError(f"Could not validate PTO container: {exc}") from exc


def _tag_text(tttrlib: Any, handle: Any, name: str, value: str) -> None:
    tag = tttrlib.PtoTag()
    tag.name = name
    tag.type = tttrlib.PtoType_Text
    tag.target = 0
    tag.text = value
    handle.add_tag(tag)


def _payload_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectPtoError(f"Project state is not valid JSON: {exc}") from exc


def _temporary_path(destination: pathlib.Path) -> pathlib.Path:
    fd, value = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    path = pathlib.Path(value)
    path.unlink()
    return path


def write_project(
    path: str | pathlib.Path,
    payload: Mapping[str, Any],
    *,
    session_bytes: bytes | None = None,
) -> pathlib.Path:
    """Write one validated PTO project, then atomically publish it.

    PTO's in-place update API is deliberately not used: a project save must
    retain the prior valid file until the new container has been committed,
    closed and reopened successfully.
    """
    target = pathlib.Path(path)
    if target.suffixes[-2:] != [".cs", ".pto"]:
        raise ProjectPtoError(f"ChiSurf project paths must end in {PROJECT_SUFFIX}: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target)
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    try:
        if not handle.create(
            str(temporary), str(payload.get("meta", {}).get("name") or target.stem)
        ):
            raise ProjectPtoError(f"Could not create {temporary}: {handle.error()}")
        handle.set_writing_app("ChiSurf")
        _tag_text(tttrlib, handle, "chisurf.profile", PROFILE)
        _tag_text(tttrlib, handle, "chisurf.profile_version", str(PROFILE_VERSION))
        if not handle.add(_PROJECT_KIND, _PROJECT_ENCODING, _PROJECT_NAME, _payload_bytes(payload)):
            raise ProjectPtoError(f"Could not add project state: {handle.error()}")
        if session_bytes is not None:
            if not handle.add(_SESSION_KIND, _SESSION_ENCODING, _SESSION_NAME, session_bytes):
                raise ProjectPtoError(f"Could not add native graph session: {handle.error()}")
        if not handle.commit():
            raise ProjectPtoError(f"Could not commit {temporary}: {handle.error()}")
        handle.close()
        handle = None
        # Reopen before replacement: index publication alone is not a complete
        # save guarantee, and a damaged temporary must never replace the last save.
        read_project(temporary)
        os.replace(temporary, target)
        return target
    except Exception:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        raise
    finally:
        if temporary.exists():
            temporary.unlink()


def read_project(path: str | pathlib.Path) -> tuple[dict[str, Any], bytes | None]:
    """Read and validate the portable project payload and optional BFF session."""
    source = pathlib.Path(path)
    if not source.is_file():
        raise ProjectPtoError(f"Project file does not exist: {source}")
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    if not handle.open(str(source)):
        raise ProjectPtoError(f"Could not open {source}: {handle.error()}")
    try:
        problems = _problems(handle)
        if problems:
            raise ProjectPtoError(f"PTO validation failed for {source}: {'; '.join(problems)}")
        profile = next(
            (tag.text for tag in handle.tags_for(0) if tag.name == "chisurf.profile"), ""
        )
        version = next(
            (tag.text for tag in handle.tags_for(0) if tag.name == "chisurf.profile_version"), ""
        )
        if profile != PROFILE or version != str(PROFILE_VERSION):
            raise ProjectPtoError(
                f"Unsupported ChiSurf PTO profile {profile!r} version {version!r}"
            )
        raw = bytes(handle.read(_object_uid(handle, _PROJECT_KIND, _PROJECT_NAME)))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectPtoError(f"Invalid project JSON in {source}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProjectPtoError("Project payload must be a JSON object")
        session = None
        matches = [
            obj.uid
            for obj in handle.objects()
            if obj.kind == _SESSION_KIND and obj.name == _SESSION_NAME
        ]
        if len(matches) > 1:
            raise ProjectPtoError("Project contains more than one native graph session")
        if matches:
            session = bytes(handle.read(matches[0]))
        return payload, session
    finally:
        handle.close()


def write_entries(path: str | pathlib.Path, entries: Mapping[str, bytes]) -> pathlib.Path:
    """Write named project payloads to a validated ``.cs.pto`` file.

    This is the adapter used by existing project callers that still assemble
    project, history and embedded-data entries independently.  Each entry is
    a first-class PTO object, never a ZIP embedded inside PTO.
    """
    if "project.json" not in entries:
        raise ProjectPtoError("A ChiSurf project must include project.json")
    target = pathlib.Path(path)
    if target.suffixes[-2:] != [".cs", ".pto"]:
        raise ProjectPtoError(f"ChiSurf project paths must end in {PROJECT_SUFFIX}: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target)
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    try:
        if not handle.create(str(temporary), target.stem):
            raise ProjectPtoError(f"Could not create {temporary}: {handle.error()}")
        handle.set_writing_app("ChiSurf")
        _tag_text(tttrlib, handle, "chisurf.profile", PROFILE)
        _tag_text(tttrlib, handle, "chisurf.profile_version", str(PROFILE_VERSION))
        for name, data in entries.items():
            if not name or name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
                raise ProjectPtoError(f"Unsafe project entry name: {name!r}")
            if not handle.add(_ARCHIVE_ENTRY_KIND, "raw", name, bytes(data)):
                raise ProjectPtoError(f"Could not add {name!r}: {handle.error()}")
        if not handle.commit():
            raise ProjectPtoError(f"Could not commit {temporary}: {handle.error()}")
        handle.close()
        handle = None
        read_entries(temporary)
        os.replace(temporary, target)
        return target
    except Exception:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        raise
    finally:
        if temporary.exists():
            temporary.unlink()


def read_entries(path: str | pathlib.Path) -> dict[str, bytes]:
    """Read the named payload objects of a validated ``.cs.pto`` project."""
    source = pathlib.Path(path)
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    if not handle.open(str(source)):
        raise ProjectPtoError(f"Could not open {source}: {handle.error()}")
    try:
        problems = _problems(handle)
        if problems:
            raise ProjectPtoError(f"PTO validation failed for {source}: {'; '.join(problems)}")
        profile = next(
            (tag.text for tag in handle.tags_for(0) if tag.name == "chisurf.profile"), ""
        )
        version = next(
            (tag.text for tag in handle.tags_for(0) if tag.name == "chisurf.profile_version"), ""
        )
        if profile != PROFILE or version != str(PROFILE_VERSION):
            raise ProjectPtoError(
                f"Unsupported ChiSurf PTO profile {profile!r} version {version!r}"
            )
        entries: dict[str, bytes] = {}
        for obj in handle.objects():
            if obj.kind != _ARCHIVE_ENTRY_KIND:
                continue
            if obj.name in entries:
                raise ProjectPtoError(f"Project contains duplicate entry {obj.name!r}")
            entries[obj.name] = bytes(handle.read(obj.uid))
        if "project.json" not in entries:
            raise ProjectPtoError("Project does not contain project.json")
        return entries
    finally:
        handle.close()
