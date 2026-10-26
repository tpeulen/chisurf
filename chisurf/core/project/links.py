"""File links: how a project points at measurement files it does not copy.

A photon stream (or any dataset whose data stays in a file) enters a project as a **link** — the
file's address, size and sha256, plus its path relative to the project when the project is saved —
so a ``.cs.pto`` stays slim and never duplicates a measurement (owner directive 2026-10-26,
``okf/specs/data-workspace.md``). Hashing happens once, when the link is made; opening a project
checks the size only, and :func:`verify` checks the hash on demand — an autosave never re-hashes.

A link resolves, in order, to the recorded path relative to the project's folder, then the recorded
absolute path, then a file of the same name beside the project. A file that is missing or no longer
matches is reported (:class:`Resolution`), never silently replaced by a different one.

**Switch point.** This first implementation keeps the link record in the project JSON. ptolib now
carries first-class links (relative path + size + sha256, followed by reads, ``verify_links``,
``relink``, ``pack``/``unpack``); once the installed tttrlib exposes them (``tttrlib.PtoFile.add_link``
…), the bodies of :func:`add_link`, :func:`resolve`, :func:`verify`, :func:`embed` and
:func:`unembed` move onto them and nothing outside this module changes (marked ``SWITCH POINT``).
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
    "Resolution",
    "add_link",
    "embed",
    "file_digest",
    "relativize",
    "resolve",
    "unembed",
    "verify",
]

#: The record format written into the project JSON by this backend.
LINK_SCHEME = "chisurf.file-link.v1"

#: Whether :func:`embed` can copy a link's target into the project yet (ptolib backend).
EMBED_AVAILABLE = False

_CHUNK = 1 << 20


def file_digest(path: str | os.PathLike, progress=None) -> tuple[int, str]:
    """Return ``(size_bytes, sha256 hex)`` of *path*, streamed in 1 MiB chunks.

    *progress*, when given, is called with the bytes read so far after each chunk.
    """
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


def add_link(address: str | os.PathLike, progress=None) -> dict[str, Any]:
    """Make the link record of *address* (a file, or a member of a container file).

    The size and sha256 are those of the file on disk (the container, for a member), computed once.
    SWITCH POINT: ptolib's ``File.add_link`` once tttrlib exposes it.
    """
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

    No hashing. A target on another volume (no relative path exists) keeps only its absolute path.
    """
    updated = dict(link)
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
) -> Resolution:
    """Find the file *link* points at and check it is the same file.

    The size is always compared; the sha256 only with *check_hash* (it reads the whole file).
    """
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
    name = Path(str(link.get("container", ""))).name or "the linked file"
    return Resolution("missing", None, None, f"{name} was not found where it was linked")


def verify(link: dict[str, Any], project_dir: str | os.PathLike | None = None) -> Resolution:
    """Resolve *link* and compare the sha256 too: the full check, on demand."""
    return resolve(link, project_dir, check_hash=True)


def embed(link: dict[str, Any], project_path: str | os.PathLike) -> dict[str, Any]:
    """Copy *link*'s target into the project (not available until the ptolib backend lands)."""
    raise NotImplementedError(
        "Embedding a file in the project is not available yet: the dataset stays linked."
    )


def unembed(link: dict[str, Any], project_path: str | os.PathLike, target: str | os.PathLike):
    """Write an embedded file back out and link it again (not available until the ptolib backend)."""
    raise NotImplementedError("Unembedding is not available yet: nothing is embedded.")
