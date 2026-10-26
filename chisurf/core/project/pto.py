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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
#: The archive-entry name of the live bff graph session.  Written as the
#: typed ``chisurf.graph-session`` object on both save routes (``write_project``
#: and ``write_entries``) so every reader sees one identity.
SESSION_FILENAME = "session.jsonl"
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


@dataclass(frozen=True)
class ProjectFile:
    """One linked or embedded data file of a project, as its container carries it.

    A linked file is a zero-size object with ptolib's ``pto.link.*`` record; an embedded one holds
    the bytes, streamed from *source* (a file path, or the address of an object in another
    container -- the previous save of the project), with a ``pto.packed.*`` record.
    """

    name: str
    kind: str
    encoding: str
    tags: tuple[tuple[str, str, Any], ...] = ()
    source: str | None = None
    size: int = 0
    #: The object this one is a companion of (an ``.spc``'s ``.set``): ptolib's ``pto.sidecar_of``.
    sidecar_of: str | None = None

    @property
    def embedded(self) -> bool:
        """Whether the bytes go into the container."""
        return self.source is not None


def _typed_tag(tttrlib: Any, uid: int, name: str, kind: str, value: Any) -> Any:
    tag = tttrlib.PtoTag()
    tag.name, tag.target = name, uid
    if kind == "uint":
        tag.type, tag.u = tttrlib.PtoType_UInt, int(value)
    elif kind == "int":
        tag.type, tag.i = tttrlib.PtoType_Int, int(value)
    else:
        tag.type, tag.text = tttrlib.PtoType_Text, str(value)
    return tag


def _local_source(source: str, scratch: pathlib.Path) -> pathlib.Path:
    """A file path for *source*: itself, or an object of a container extracted into *scratch*."""
    from chisurf.core.fio.address import split_address

    container, member = split_address(source)
    if container is None:
        raise ProjectPtoError(f"The data to embed is not available: {source}")
    if not member:
        return pathlib.Path(container)
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    if not handle.open(str(container)):
        raise ProjectPtoError(f"Could not open {container}: {handle.error()}")
    try:
        uid = next((obj.uid for obj in handle.objects() if obj.name == member), None)
        if uid is None:
            raise ProjectPtoError(f"{pathlib.Path(container).name} holds no {member!r}")
        out = scratch / pathlib.PurePosixPath(member).name
        if not handle.extract(uid, str(out)):
            raise ProjectPtoError(f"Could not extract {member!r}: {handle.error()}")
        return out
    finally:
        handle.close()


def _add_project_files(
    tttrlib: Any, handle: Any, files: Sequence[ProjectFile], target: pathlib.Path
) -> None:
    """Add *files* to the open container *handle* (written beside *target*)."""
    if not files:
        return
    names = [f.name for f in files]
    if len(set(names)) != len(names):
        raise ProjectPtoError("Two data files of the project have the same object name")
    scratch = pathlib.Path(tempfile.mkdtemp(prefix=".chisurf-embed-", dir=target.parent))
    uids: dict[str, int] = {}
    try:
        for item in files:
            if item.embedded:
                path = _local_source(str(item.source), scratch)
                add_file = getattr(handle, "add_file", None)
                if callable(add_file):
                    uid = add_file(item.kind, item.encoding, item.name, str(path))
                else:  # pragma: no cover - every supported tttrlib streams
                    uid = handle.add(item.kind, item.encoding, item.name, path.read_bytes())
            else:
                uid = handle.add(item.kind, item.encoding, item.name, b"")
            if not uid:
                raise ProjectPtoError(f"Could not add {item.name!r}: {handle.error()}")
            uids[item.name] = uid
            for name, kind, value in item.tags:
                handle.add_tag(_typed_tag(tttrlib, uid, name, kind, value))
            if item.sidecar_of and item.sidecar_of in uids:
                tag = tttrlib.PtoTag()
                tag.name, tag.target = "pto.sidecar_of", uid
                tag.type, tag.u = tttrlib.PtoType_UID, uids[item.sidecar_of]
                handle.add_tag(tag)
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def _check_project_files(handle: Any, files: Sequence[ProjectFile]) -> None:
    """Every data file is in the reopened container, an embedded one with all its bytes."""
    present = {obj.name: obj for obj in handle.objects()}
    for item in files:
        obj = present.get(item.name)
        if obj is None:
            raise ProjectPtoError(f"Candidate PTO project lost {item.name!r}")
        if item.embedded and item.size and int(obj.size) != int(item.size):
            raise ProjectPtoError(
                f"Candidate PTO project holds {obj.size} bytes of {item.name!r}, not {item.size}"
            )


def _payload_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectPtoError(f"Project state is not valid JSON: {exc}") from exc


def _validate_project_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every scientific snapshot, independent of optional metadata."""
    from .project import Project

    normalized = dict(payload)
    project = Project.from_dict(normalized)
    codec = project.metadata.get("session_codec")
    if codec is not None and codec != "detached-v2":
        raise ProjectPtoError(f"Unsupported project session codec: {codec!r}")

    from .history import validate_history_state
    from .session import restore_session

    restore_session(project)
    validate_history_state(project)
    return normalized


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


def publish_project_bytes(path: str | pathlib.Path, data: bytes) -> pathlib.Path:
    """Validate and atomically publish an exact native PTO container.

    Exported containers can carry native sessions and resource objects beyond
    the scientific snapshot. Keep every byte rather than serializing the
    snapshot again. The existing destination is untouched until the sibling
    stage has been written, flushed, fsynced, read back and scientifically
    validated. Any pre-publication failure removes that stage.
    """
    target = pathlib.Path(path)
    if target.suffixes[-2:] != [".cs", ".pto"]:
        raise ProjectPtoError(f"ChiSurf project paths must end in {PROJECT_SUFFIX}: {target}")
    if not isinstance(data, bytes) or not data:
        raise ProjectPtoError("Exported project content must be nonempty native PTO bytes")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target)
    try:
        with temporary.open("wb") as stream:
            if stream.write(data) != len(data):
                raise ProjectPtoError("Candidate PTO project write was incomplete")
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.read_bytes() != data:
            raise ProjectPtoError("Candidate PTO project did not read back exactly")
        payload, _session = read_project(temporary)
        _validate_project_payload(payload)
        # Read all archive resources too, including MMFDB attachments. This
        # validates the complete container without rebuilding or losing them.
        entries = read_entries(temporary)
        for name in entries:
            if not name or name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
                raise ProjectPtoError(f"Unsafe project entry name: {name!r}")
        os.replace(temporary, target)
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


def write_project(
    path: str | pathlib.Path,
    payload: Mapping[str, Any],
    *,
    session_bytes: bytes | None = None,
    files: Sequence[ProjectFile] = (),
) -> pathlib.Path:
    """Write one validated PTO project, then atomically publish it.

    *files* are the project's linked and embedded data files (:class:`ProjectFile`).

    PTO's in-place update API is deliberately not used: a project save must
    retain the prior valid file until the new container has been committed,
    closed and reopened successfully.
    """
    target = pathlib.Path(path)
    if target.suffixes[-2:] != [".cs", ".pto"]:
        raise ProjectPtoError(f"ChiSurf project paths must end in {PROJECT_SUFFIX}: {target}")
    validated_payload = _validate_project_payload(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target)
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    try:
        if not handle.create(
            str(temporary), str(validated_payload.get("meta", {}).get("name") or target.stem)
        ):
            raise ProjectPtoError(f"Could not create {temporary}: {handle.error()}")
        handle.set_writing_app("ChiSurf")
        _tag_text(tttrlib, handle, "chisurf.profile", PROFILE)
        _tag_text(tttrlib, handle, "chisurf.profile_version", str(PROFILE_VERSION))
        if not handle.add(
            _PROJECT_KIND,
            _PROJECT_ENCODING,
            _PROJECT_NAME,
            _payload_bytes(validated_payload),
        ):
            raise ProjectPtoError(f"Could not add project state: {handle.error()}")
        if session_bytes is not None:
            if not handle.add(_SESSION_KIND, _SESSION_ENCODING, _SESSION_NAME, session_bytes):
                raise ProjectPtoError(f"Could not add native graph session: {handle.error()}")
        _add_project_files(tttrlib, handle, files, target)
        if not handle.commit():
            raise ProjectPtoError(f"Could not commit {temporary}: {handle.error()}")
        handle.close()
        handle = None
        # Reopen and compare before replacement: index publication alone is not
        # a complete save guarantee, and a damaged temporary must never replace
        # the last save.
        _verify_project_files(temporary, files)
        actual, actual_session = read_project(temporary)
        _validate_project_payload(actual)
        if actual != validated_payload or actual_session != session_bytes:
            raise ProjectPtoError("Candidate PTO project did not read back exactly")
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


def _verify_project_files(path: pathlib.Path, files: Sequence[ProjectFile]) -> None:
    if not files:
        return
    handle = _tttrlib().PtoFile()
    if not handle.open(str(path)):
        raise ProjectPtoError(f"Could not reopen {path}: {handle.error()}")
    try:
        _check_project_files(handle, files)
    finally:
        handle.close()


def write_entries(
    path: str | pathlib.Path,
    entries: Mapping[str, bytes],
    files: Sequence[ProjectFile] = (),
) -> pathlib.Path:
    """Write named project payloads to a validated ``.cs.pto`` file.

    This is the adapter used by existing project callers that still assemble
    project, history and embedded-data entries independently.  ``project.json``
    is always the typed ``chisurf.project`` object; remaining entries are
    first-class PTO resource objects, never a ZIP embedded inside PTO.
    """
    if "project.json" not in entries:
        raise ProjectPtoError("A ChiSurf project must include project.json")
    target = pathlib.Path(path)
    if target.suffixes[-2:] != [".cs", ".pto"]:
        raise ProjectPtoError(f"ChiSurf project paths must end in {PROJECT_SUFFIX}: {target}")
    try:
        project_payload = json.loads(bytes(entries["project.json"]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectPtoError(f"project.json is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(project_payload, dict):
        raise ProjectPtoError("project.json must contain a JSON object")
    project_payload = _validate_project_payload(project_payload)
    resources = {name: bytes(data) for name, data in entries.items() if name != "project.json"}
    # The graph session is a first-class typed object, not a raw entry.
    session_data = resources.pop(SESSION_FILENAME, None)
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
        if not handle.add(
            _PROJECT_KIND,
            _PROJECT_ENCODING,
            _PROJECT_NAME,
            _payload_bytes(project_payload),
        ):
            raise ProjectPtoError(f"Could not add project state: {handle.error()}")
        for name, data in resources.items():
            if not name or name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
                raise ProjectPtoError(f"Unsafe project entry name: {name!r}")
            if not handle.add(_ARCHIVE_ENTRY_KIND, "raw", name, bytes(data)):
                raise ProjectPtoError(f"Could not add {name!r}: {handle.error()}")
        if session_data is not None:
            if not handle.add(_SESSION_KIND, _SESSION_ENCODING, _SESSION_NAME, session_data):
                raise ProjectPtoError(f"Could not add native graph session: {handle.error()}")
        _add_project_files(tttrlib, handle, files, target)
        if not handle.commit():
            raise ProjectPtoError(f"Could not commit {temporary}: {handle.error()}")
        handle.close()
        handle = None
        _verify_project_files(temporary, files)
        actual = read_entries(temporary)
        actual_project = json.loads(actual.pop("project.json").decode("utf-8"))
        _validate_project_payload(actual_project)
        actual_session = actual.pop(SESSION_FILENAME, None)
        if (
            actual_project != project_payload
            or actual != resources
            or actual_session != session_data
        ):
            raise ProjectPtoError("Candidate PTO project did not read back exactly")
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
        project_matches = [
            obj.uid
            for obj in handle.objects()
            if obj.kind == _PROJECT_KIND and obj.name == _PROJECT_NAME
        ]
        if len(project_matches) != 1:
            raise ProjectPtoError("Project must contain exactly one typed project object")
        entries["project.json"] = bytes(handle.read(project_matches[0]))
        for obj in handle.objects():
            if obj.kind != _ARCHIVE_ENTRY_KIND:
                continue
            if obj.name in entries:
                raise ProjectPtoError(f"Project contains duplicate entry {obj.name!r}")
            entries[obj.name] = bytes(handle.read(obj.uid))
        session_matches = [
            obj.uid
            for obj in handle.objects()
            if obj.kind == _SESSION_KIND and obj.name == _SESSION_NAME
        ]
        if len(session_matches) > 1:
            raise ProjectPtoError("Project contains more than one native graph session")
        if session_matches:
            entries[SESSION_FILENAME] = bytes(handle.read(session_matches[0]))
        return entries
    finally:
        handle.close()
