"""File links: how a project points at measurement files it does not copy.

A photon stream (or any dataset whose data stays in a file) enters a project as a **link** — the
file's address, size and sha256, plus its path relative to the project when the project is saved —
so a ``.cs.pto`` stays slim and never duplicates a measurement (owner directive 2026-10-26,
``okf/specs/data-workspace.md``). Hashing happens once, when the link is made; opening a project
checks the size only, and :func:`verify` checks the hash on demand — an autosave never re-hashes.

A link resolves, in order, to the recorded path relative to the project's folder, then the recorded
absolute path, then a file of the same name beside the project. A file that is missing or no longer
matches is reported (:class:`Resolution`), never silently replaced by a different one.

**Two backends, one record.** The link record lives in the project JSON (the session state);
the project container also carries it as a ptolib link object (``pto.link.*`` tags) — or, once
embedded, the target's bytes with a ``pto.packed.*`` record — so ptolib's tools and readers see the
same thing (``pto verify``, ``pto locate``, a ``project.cs.pto/<object>`` address). Where the
installed tttrlib exposes ptolib's links (:func:`ptolib_links`), hashing (``sha256_file``) and the
candidate search (``PtoFile.find_link_candidates``) use them; an older tttrlib falls back to the
Python implementations here. The semantics are ptolib's either way: the recorded path (relative to
the project's folder), then the same name beside the project; size on every open, sha256 on
demand; a mismatch is reported, never silently replaced.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chisurf.core.fio.address import join_address, split_address

__all__ = [
    "EMBED_AVAILABLE",
    "LINK_SCHEME",
    "Candidate",
    "LinkError",
    "LinkReport",
    "Resolution",
    "add_link",
    "embed",
    "file_digest",
    "find_candidates",
    "is_embedded",
    "object_tags",
    "ptolib_links",
    "relativize",
    "relink",
    "report",
    "resolve",
    "unembed",
    "use_remote_copy",
    "verify",
]

#: The record format written into the project JSON by this backend (a local file, a container
#: member, or an MMFDB object ``mmfdb://artifact/<id>`` -- :mod:`chisurf.core.project.remote_links`).
LINK_SCHEME = "chisurf.file-link.v1"

#: Whether :func:`embed` can store a link's target inside the project (written by the project
#: writer with the container's streaming ``add_file``; every supported tttrlib has it).
EMBED_AVAILABLE = True

_CHUNK = 1 << 20


class LinkError(ValueError):
    """A link operation refused: the file is missing, or not the file that was linked."""


def _tttrlib():
    try:
        import tttrlib
    except ImportError:  # pragma: no cover - tttrlib is a hard dependency of the app
        return None
    return tttrlib


def ptolib_links() -> bool:
    """Whether the installed tttrlib exposes ptolib's first-class file links.

    tttrlib >= the one carrying ptolib 67451c3 (``PtoFile.add_link`` … ``find_link_candidates``,
    ``sha256_file``). Older builds use this module's Python fallbacks; the records are the same.
    """
    tttrlib = _tttrlib()
    return bool(
        tttrlib is not None
        and hasattr(getattr(tttrlib, "PtoFile", None), "add_link")
        and hasattr(tttrlib, "sha256_file")
    )


def file_digest(path: str | os.PathLike, progress=None) -> tuple[int, str]:
    """Return ``(size_bytes, sha256 hex)`` of *path*, streamed in 1 MiB chunks.

    *progress*, when given, is called with the bytes read so far after each chunk. Without it,
    ptolib's ``sha256_file`` does the reading where the installed tttrlib has it.
    """
    if progress is None and ptolib_links():
        sha256 = str(_tttrlib().sha256_file(str(path)))
        if sha256:
            return Path(path).stat().st_size, sha256
    # FALLBACK (2026-10-26): the Python digest for a tttrlib without ptolib links; delete with the
    # relock that pins a tttrlib exposing them (known-issues "Code ahead of the pins").
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
            if progress is not None:
                progress(size)
    return size, digest.hexdigest()


def _container_and_member(address: str) -> tuple[Path, str]:
    container, member = split_address(address)
    if container is None:
        raise FileNotFoundError(f"no file at {address!r}")
    return Path(container).resolve(), member or ""


def add_link(
    address: str | os.PathLike,
    progress=None,
    *,
    size: int | None = None,
    sha256: str | None = None,
) -> dict[str, Any]:
    """Make the link record of *address* (a file, a member of a container file, or an MMFDB object).

    The size and sha256 are those of the file on disk (the container, for a member), computed once
    (ptolib's ``sha256_file`` where available, :func:`file_digest`). An ``mmfdb://`` address cannot
    be hashed here: its *size* and *sha256* come from the artifact's metadata
    (:mod:`chisurf.core.project.remote_links`).
    """
    from chisurf.core.project import remote_links

    if remote_links.is_remote(str(address)):
        if size is None or sha256 is None:
            raise LinkError(f"{address}: an MMFDB link needs the object's size and sha256")
        return remote_links.link_for(str(address), size=size, sha256=sha256)
    container, member = _container_and_member(str(address))
    size, sha256 = file_digest(container, progress)
    return {
        "scheme": LINK_SCHEME,
        "container": str(container),
        "member": member,
        "size": size,
        "sha256": sha256,
        "mtime": container.stat().st_mtime,
        "companions": _companions(container),
    }


def _companions(primary: Path) -> list[dict[str, Any]]:
    """The files a primary is not readable without (an ``.spc``'s ``.set``), as found beside it."""
    from chisurf.core.fio.pto import COMPANION_SUFFIXES

    out = []
    for suffix in COMPANION_SUFFIXES.get(primary.suffix.lower(), ()):
        for candidate in (primary.with_suffix(suffix), primary.with_suffix(suffix.upper())):
            if candidate.is_file():
                size, sha256 = file_digest(candidate)
                out.append({"name": candidate.name, "size": size, "sha256": sha256})
                break
    return out


def relativize(link: dict[str, Any], project_dir: str | os.PathLike) -> dict[str, Any]:
    """Return *link* with its target's path relative to *project_dir* (where the project is saved).

    No hashing. A target on another volume (no relative path exists) keeps only its absolute path;
    an MMFDB object (no local file) has none.
    """
    updated = dict(link)
    if not link.get("container"):
        return updated
    try:
        updated["relative"] = os.path.relpath(
            Path(link["container"]).resolve(), Path(project_dir).resolve()
        )
    except (ValueError, KeyError):
        updated.pop("relative", None)
    return updated


@dataclass(frozen=True)
class Resolution:
    """Where a link points now: the address to read, or why there is none."""

    #: ``"ok"``, ``"missing"``, ``"size changed"`` or ``"hash changed"``.
    status: str
    #: The address to open (container path + member); ``None`` unless the status is ``"ok"``.
    address: str | None
    #: The file that was found (also for a mismatch), else ``None``.
    found: Path | None
    #: A sentence for the user.
    reason: str = ""

    @property
    def ok(self) -> bool:
        """Whether the link resolved to a matching file."""
        return self.status == "ok"


def _candidates(link: dict[str, Any], project_dir: Path | None) -> list[Path]:
    recorded = Path(str(link.get("container", "")))
    out: list[Path] = []
    if project_dir is not None and link.get("relative"):
        out.append((project_dir / str(link["relative"])).resolve())
    if str(recorded):
        out.append(recorded)
    if project_dir is not None and recorded.name:
        out.append(project_dir / recorded.name)
    seen: list[Path] = []
    for path in out:
        if path not in seen:
            seen.append(path)
    return seen


def resolve(
    link: dict[str, Any],
    project_dir: str | os.PathLike | None = None,
    *,
    check_hash: bool = False,
    project_path: str | os.PathLike | None = None,
) -> Resolution:
    """Find the file *link* points at and check it is the same file.

    The size is always compared; the sha256 only with *check_hash* (it reads the whole file). An
    embedded target saved in *project_path* resolves to its address inside the project.
    """
    if is_embedded(link) and project_path is not None and link.get("object"):
        container = Path(project_path)
        if container.is_file():
            return Resolution("ok", join_address(container, str(link["object"])), container)
    from chisurf.core.project import remote_links

    if remote_links.is_remote(link) and not link.get("container"):
        return remote_links.resolve_remote(link, check_hash=check_hash)
    if project_dir is None and project_path is not None:
        project_dir = Path(project_path).parent
    base = Path(project_dir).resolve() if project_dir is not None else None
    for candidate in _candidates(link, base):
        if not candidate.is_file():
            continue
        size = candidate.stat().st_size
        if int(link.get("size", -1)) != size:
            return Resolution(
                "size changed",
                None,
                candidate,
                f"{candidate.name} is {size} bytes, the linked file was {link.get('size')} bytes",
            )
        if check_hash:
            _, sha256 = file_digest(candidate)
            if sha256 != link.get("sha256"):
                return Resolution(
                    "hash changed",
                    None,
                    candidate,
                    f"{candidate.name} has the same size but different content (sha256)",
                )
        for companion in link.get("companions") or ():
            beside = candidate.with_name(str(companion.get("name", "")))
            if not beside.is_file():
                return Resolution(
                    "missing",
                    None,
                    candidate,
                    f"{beside.name}, which {candidate.name} is not readable without, is missing",
                )
            if beside.stat().st_size != int(companion.get("size", -1)):
                return Resolution(
                    "size changed",
                    None,
                    candidate,
                    f"{beside.name} changed size since it was linked",
                )
            if check_hash and file_digest(beside)[1] != companion.get("sha256"):
                return Resolution(
                    "hash changed", None, candidate, f"{beside.name} changed since it was linked"
                )
        address = join_address(candidate, link["member"]) if link.get("member") else str(candidate)
        return Resolution("ok", address, candidate)
    if remote_links.is_remote(link):
        # The local file is gone, but the link knows an MMFDB copy (Locate's "Use MMFDB copy").
        return remote_links.resolve_remote(link, check_hash=check_hash)
    name = Path(str(link.get("container", ""))).name or "the linked file"
    return Resolution("missing", None, None, f"{name} was not found where it was linked")


def verify(
    link: dict[str, Any],
    project_dir: str | os.PathLike | None = None,
    *,
    project_path: str | os.PathLike | None = None,
) -> Resolution:
    """Resolve *link* and compare the sha256 too: the full check, on demand."""
    return resolve(link, project_dir, check_hash=True, project_path=project_path)


def is_embedded(link: dict[str, Any]) -> bool:
    """Whether *link*'s target is stored inside the project (rather than linked)."""
    return bool(link.get("embedded"))


def embed(link: dict[str, Any], project_dir: str | os.PathLike | None = None) -> dict[str, Any]:
    """Return *link* marked to be stored inside the project at the next save.

    Like ptolib's ``pack``: the target must resolve and match its recorded sha256 (checked here,
    once). The project writer then streams the bytes into the container; until that save the data
    is still read from the file.
    """
    if is_embedded(link):
        return dict(link)
    resolution = verify(link, project_dir)
    if not resolution.ok:
        raise LinkError(f"Cannot embed: {resolution.reason}")
    updated = dict(link)
    updated["embedded"] = True
    return updated


def unembed(
    link: dict[str, Any],
    project_path: str | os.PathLike,
    target: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """Write an embedded target back out of *project_path* and return the link to it.

    *target* defaults to the recorded location (relative to the project's folder, else the
    original absolute path). A file already there must be the same bytes (size and sha256) and is
    kept; otherwise the bytes are extracted from the project and checked.
    """
    if not is_embedded(link):
        return dict(link)
    project_path = Path(project_path)
    obj = str(link.get("object") or "")
    if not obj:
        raise LinkError("The embedded dataset has no object in the project (save it first).")
    if target is None:
        relative = link.get("relative")
        target = project_path.parent / str(relative) if relative else Path(str(link["container"]))
    target = Path(target)
    if target.is_file():
        size, sha256 = file_digest(target)
        if size != int(link.get("size", -1)) or sha256 != link.get("sha256"):
            raise LinkError(
                f"{target} exists and is a different file; choose another place to unembed to."
            )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _extract_object(project_path, obj, target)
        size, sha256 = file_digest(target)
        if size != int(link.get("size", -1)) or sha256 != link.get("sha256"):
            target.unlink(missing_ok=True)
            raise LinkError(f"The bytes of {obj} in the project do not match the link record.")
    for companion in link.get("companions") or ():
        name = str(companion.get("name", ""))
        beside = target.with_name(Path(target.name).stem + Path(name).suffix)
        if not beside.is_file():
            _extract_object(project_path, Path(obj).stem + Path(name).suffix, beside)
        if file_digest(beside) != (int(companion.get("size", -1)), companion.get("sha256")):
            raise LinkError(f"{beside.name} is not the companion that was embedded.")
    updated = {k: v for k, v in link.items() if k != "embedded"}
    updated["container"] = str(target.resolve())
    return relativize(updated, project_path.parent)


def _extract_object(container: Path, name: str, target: Path) -> None:
    """Stream the object *name* of the PTO *container* to *target*."""
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    if not handle.open(str(container)):
        raise LinkError(f"Could not open {container}: {handle.error()}")
    try:
        uid = next((obj.uid for obj in handle.objects() if obj.name == name), None)
        if uid is None:
            raise LinkError(f"{container.name} holds no object {name!r}")
        if not handle.extract(uid, str(target)):
            raise LinkError(f"Could not extract {name!r}: {handle.error()}")
    finally:
        handle.close()


def relink(link: dict[str, Any], path: str | os.PathLike, *, force: bool = False) -> dict[str, Any]:
    """Point *link* at *path* — a moved or renamed original — and return the new record.

    The file must have the recorded size and sha256 (ptolib's ``relink`` rule); a different file is
    refused with :class:`LinkError` unless *force*, which records the new file's size and hash.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise LinkError(f"{path} is not a file")
    size, sha256 = file_digest(path)
    same = size == int(link.get("size", -1)) and sha256 == link.get("sha256")
    if not same and not force:
        what = "size" if size != int(link.get("size", -1)) else "content (sha256)"
        raise LinkError(f"{path.name} is a different file: its {what} does not match the link")
    updated = dict(link)
    updated.update(
        container=str(path),
        size=size,
        sha256=sha256,
        mtime=path.stat().st_mtime,
        companions=_companions(path),
    )
    updated.pop("relative", None)
    return updated


@dataclass(frozen=True)
class Candidate:
    """A file that may be a link's moved target (found by name; confirmed by :func:`relink`)."""

    path: Path
    size: int
    size_matches: bool


def find_candidates(
    link: dict[str, Any],
    root: str | os.PathLike,
    *,
    project_path: str | os.PathLike | None = None,
) -> list[Candidate]:
    """Files under *root* named like *link*'s target, those with the recorded size first.

    Nothing is hashed (a candidate is confirmed by :func:`relink`). With ptolib links and a saved
    *project_path* holding the link object, ptolib's ``find_link_candidates`` walks; otherwise the
    Python walk here does the same.
    """
    name = Path(str(link.get("container", ""))).name
    if not name:
        return []
    obj = str(link.get("object") or "")
    if ptolib_links() and project_path is not None and obj and Path(project_path).is_file():
        found = _ptolib_candidates(Path(project_path), obj, Path(root))
        if found is not None:
            return found
    # FALLBACK (2026-10-26): the Python walk for a tttrlib without ptolib links; delete at the relock.
    recorded = int(link.get("size", -1))
    out: list[Candidate] = []
    for directory, _dirs, files in os.walk(root, onerror=lambda _e: None):
        if name in files:
            candidate = Path(directory) / name
            try:
                size = candidate.stat().st_size
            except OSError:
                continue
            out.append(Candidate(candidate, size, size == recorded))
    out.sort(key=lambda c: (not c.size_matches, str(c.path)))
    return out


def _ptolib_candidates(project_path: Path, obj: str, root: Path) -> list[Candidate] | None:
    tttrlib = _tttrlib()
    handle = tttrlib.PtoFile()
    if not handle.open(str(project_path)):
        return None
    try:
        uid = next((o.uid for o in handle.objects() if o.name == obj), None)
        if uid is None or not handle.is_link(uid):
            return None
        return [
            Candidate(Path(c.path), int(c.size), bool(c.size_matches))
            for c in handle.find_link_candidates(uid, str(root))
        ]
    finally:
        handle.close()


def object_tags(link: dict[str, Any], project_dir: str | os.PathLike) -> list[tuple[str, str, Any]]:
    """The ptolib record of *link* as ``(tag name, type, value)``: ``pto.link.*`` while linked,
    ``pto.packed.*`` once embedded (so ``pto unembed`` can restore the link). Types are ptolib's:
    ``"text"``, ``"uint"``, ``"int"``."""
    prefix = "pto.packed." if is_embedded(link) else "pto.link."
    container = Path(str(link.get("container", "")))
    if not link.get("container") and link.get("uri"):
        path = str(link["uri"])  # an MMFDB object: ptolib resolves the URI through its registry
    else:
        try:
            path = os.path.relpath(container.resolve(), Path(project_dir).resolve())
        except ValueError:
            path = str(container)
    tags: list[tuple[str, str, Any]] = [
        (prefix + "path", "text", path),
        (prefix + "size", "uint", int(link.get("size", 0))),
        (prefix + "sha256", "text", str(link.get("sha256", ""))),
    ]
    if link.get("mtime"):
        tags.append((prefix + "mtime", "int", int(float(link["mtime"]))))
    if link.get("container") and link.get("uri"):
        # A local file that also knows where it came from: ptolib's fallback source.
        tags.append((prefix + "uri", "text", str(link["uri"])))
    return tags


def use_remote_copy(link: dict[str, Any], uri: str) -> dict[str, Any]:
    """Return *link* with *uri* (an MMFDB object with the same sha256) as its source.

    Locate missing data's "Use MMFDB copy": the recorded local path stays (a file that reappears
    there is used first), and the object is fetched from MMFDB otherwise. The size and sha256 are
    the link's own: the object must match them.
    """
    from chisurf.core.project import remote_links

    if not remote_links.is_remote(uri):
        raise LinkError(f"not an MMFDB address: {uri!r}")
    updated = dict(link)
    updated["uri"] = str(uri)
    return updated


@dataclass(frozen=True)
class LinkReport:
    """One linked dataset of a project, checked: what the self-contained and export checks list."""

    uid: str
    name: str
    status: str
    reason: str
    embedded: bool
    location: str

    @property
    def ok(self) -> bool:
        """Whether the dataset's data is found (embedded, or a matching linked file)."""
        return self.status == "ok"


def report(
    records: Any,
    project_dir: str | os.PathLike | None = None,
    *,
    check_hash: bool = False,
    project_path: str | os.PathLike | None = None,
) -> list[LinkReport]:
    """Check every linked dataset in *records* (project dataset records, or linked datasets).

    An embedded dataset is ``ok`` (its bytes are in the project); a linked one is resolved — size
    only unless *check_hash*.
    """
    out: list[LinkReport] = []
    items = records.values() if isinstance(records, dict) else records
    for item in items:
        if isinstance(item, dict):
            if item.get("kind") != "linked" or not isinstance(item.get("link"), dict):
                continue
            uid, name, link = str(item.get("uid", "")), str(item.get("name", "")), item["link"]
        elif hasattr(item, "link") and isinstance(getattr(item, "link", None), dict):
            uid = str(getattr(item, "unique_identifier", ""))
            name, link = str(getattr(item, "name", "")), item.link
        else:
            continue
        location = str(link.get("container", "") or link.get("uri", ""))
        if is_embedded(link):
            out.append(LinkReport(uid, name, "ok", "", True, location))
            continue
        resolution = resolve(link, project_dir, check_hash=check_hash, project_path=project_path)
        if resolution.found is not None:
            location = str(resolution.found)
        out.append(LinkReport(uid, name, resolution.status, resolution.reason, False, location))
    return out
