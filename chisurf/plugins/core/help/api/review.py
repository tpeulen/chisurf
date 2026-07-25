"""Review-status tracking for documentation pages.

Large parts of the user manual were drafted by a language model. Such a page is
useful for orientation but must not reach a release before a human has read it,
so every tracked page carries one of three states:

``reviewed``
    A human signed the page off *and* the file still has the content they saw.
``stale``
    The page was signed off, but has been edited since. The sign-off no longer
    applies and the page counts as unreviewed for gating purposes.
``unreviewed``
    Never signed off (the default for anything absent from the registry).

The distinction between ``reviewed`` and ``stale`` is why the registry stores a
content hash: without it a page could be approved once and then silently
rewritten, which is exactly the failure this module exists to prevent.

Status lives in a per-directory sidecar ``review_status.json`` rather than in the
pages themselves, so the manual's reStructuredText stays clean and the whole
review state of a directory can be read, diffed and gated as one file.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import pathlib

#: Status values.
STATUS_REVIEWED = "reviewed"
STATUS_STALE = "stale"
STATUS_UNREVIEWED = "unreviewed"

#: Name of the per-directory sidecar registry.
REGISTRY_NAME = "review_status.json"

#: Documentation directories under ``docs/`` whose pages require sign-off.
#: Add a directory here to bring it under review gating.
TRACKED_DIRS: tuple[str, ...] = ("manual",)

#: File suffixes treated as documentation pages.
PAGE_SUFFIXES: tuple[str, ...] = (".rst", ".md")


@dataclasses.dataclass
class ReviewRecord:
    """Sign-off recorded for a single page."""

    status: str = STATUS_UNREVIEWED
    reviewer: str = ""
    date: str = ""
    sha256: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return the record as a plain JSON-serialisable dict."""
        return {
            "status": self.status,
            "reviewer": self.reviewer,
            "date": self.date,
            "sha256": self.sha256,
        }


@dataclasses.dataclass
class PageStatus:
    """Effective status of one page, after comparing hashes."""

    path: str
    rel_path: str
    status: str
    reviewer: str = ""
    date: str = ""

    @property
    def is_blocking(self) -> bool:
        """Whether this page would block a release."""
        return self.status != STATUS_REVIEWED


@dataclasses.dataclass
class ReviewReport:
    """Aggregate review state across every tracked directory."""

    pages: list[PageStatus] = dataclasses.field(default_factory=list)

    @property
    def reviewed(self) -> list[PageStatus]:
        """Pages signed off and unchanged since."""
        return [p for p in self.pages if p.status == STATUS_REVIEWED]

    @property
    def stale(self) -> list[PageStatus]:
        """Pages edited after sign-off."""
        return [p for p in self.pages if p.status == STATUS_STALE]

    @property
    def unreviewed(self) -> list[PageStatus]:
        """Pages never signed off."""
        return [p for p in self.pages if p.status == STATUS_UNREVIEWED]

    @property
    def blocking(self) -> list[PageStatus]:
        """Every page that is not cleanly reviewed."""
        return [p for p in self.pages if p.is_blocking]

    @property
    def ok(self) -> bool:
        """Whether every tracked page is cleanly reviewed."""
        return not self.blocking

    def summary(self) -> str:
        """Return a one-line human-readable tally."""
        return (
            f"{len(self.reviewed)} reviewed, "
            f"{len(self.stale)} stale, "
            f"{len(self.unreviewed)} unreviewed "
            f"({len(self.pages)} tracked)"
        )


def content_hash(text: str) -> str:
    """Return the SHA-256 of *text*, insensitive to line-ending style.

    Parameters
    ----------
    text : str
        File contents.

    Returns
    -------
    str
        Hex digest.

    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def docs_root() -> pathlib.Path | None:
    """Return the repository ``docs/`` directory, or *None* when unavailable.

    Returns
    -------
    pathlib.Path or None
        The documentation root; *None* for installations without a source tree.

    """
    import chisurf as cs

    root = pathlib.Path(cs.__file__).resolve().parent.parent / "docs"
    return root if root.is_dir() else None


def tracked_dirs() -> list[pathlib.Path]:
    """Return every existing tracked documentation directory.

    Returns
    -------
    list of pathlib.Path
        Directories under ``docs/`` listed in :data:`TRACKED_DIRS`.

    """
    root = docs_root()
    if root is None:
        return []
    return [root / name for name in TRACKED_DIRS if (root / name).is_dir()]


def is_tracked(path) -> bool:
    """Whether *path* lies in a tracked directory and is a documentation page.

    Parameters
    ----------
    path : str or pathlib.Path
        Candidate file.

    Returns
    -------
    bool
        *True* when the page is subject to review gating.

    """
    p = pathlib.Path(path).resolve()
    if p.suffix.lower() not in PAGE_SUFFIXES:
        return False
    return any(_is_within(p, d) for d in tracked_dirs())


def registry_path(directory) -> pathlib.Path:
    """Return the sidecar registry path for *directory*.

    Parameters
    ----------
    directory : str or pathlib.Path
        A tracked documentation directory.

    Returns
    -------
    pathlib.Path
        Path of the ``review_status.json`` sidecar.

    """
    return pathlib.Path(directory) / REGISTRY_NAME


def load_registry(directory) -> dict[str, ReviewRecord]:
    """Load the sign-off registry of *directory*.

    Parameters
    ----------
    directory : str or pathlib.Path
        A tracked documentation directory.

    Returns
    -------
    dict
        Mapping of directory-relative page name to :class:`ReviewRecord`. Empty
        when the registry is missing or unreadable.

    """
    path = registry_path(directory)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, ReviewRecord] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            out[key] = ReviewRecord(
                status=str(value.get("status", STATUS_UNREVIEWED)),
                reviewer=str(value.get("reviewer", "")),
                date=str(value.get("date", "")),
                sha256=str(value.get("sha256", "")),
            )
    return out


def save_registry(directory, records: dict[str, ReviewRecord]) -> bool:
    """Write *records* to the sidecar registry of *directory*.

    Parameters
    ----------
    directory : str or pathlib.Path
        A tracked documentation directory.
    records : dict
        Mapping of page name to :class:`ReviewRecord`.

    Returns
    -------
    bool
        *True* on success.

    """
    payload = {key: records[key].as_dict() for key in sorted(records)}
    try:
        registry_path(directory).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return True
    except Exception:
        return False


def status_of(path) -> PageStatus:
    """Return the effective review status of a single page.

    A page recorded as reviewed whose content hash no longer matches is reported
    as :data:`STATUS_STALE`.

    Parameters
    ----------
    path : str or pathlib.Path
        Documentation page.

    Returns
    -------
    PageStatus
        Effective status. Untracked pages report :data:`STATUS_REVIEWED` so they
        never block a build.

    """
    p = pathlib.Path(path).resolve()
    directory = _tracked_parent(p)
    if directory is None:
        return PageStatus(path=str(p), rel_path=p.name, status=STATUS_REVIEWED)

    rel = p.relative_to(directory).as_posix()
    record = load_registry(directory).get(rel)
    if record is None or record.status != STATUS_REVIEWED:
        return PageStatus(path=str(p), rel_path=rel, status=STATUS_UNREVIEWED)

    try:
        current = content_hash(p.read_text(encoding="utf-8"))
    except Exception:
        current = ""
    status = STATUS_REVIEWED if current and current == record.sha256 else STATUS_STALE
    return PageStatus(
        path=str(p),
        rel_path=rel,
        status=status,
        reviewer=record.reviewer,
        date=record.date,
    )


def set_status(path, status: str, reviewer: str = "") -> bool:
    """Record *status* for a page and persist the registry.

    Marking a page reviewed stores the hash of its current content, so any later
    edit turns the page stale automatically.

    Parameters
    ----------
    path : str or pathlib.Path
        Documentation page.
    status : str
        :data:`STATUS_REVIEWED` or :data:`STATUS_UNREVIEWED`.
    reviewer : str, optional
        Name recorded alongside the sign-off.

    Returns
    -------
    bool
        *True* on success; *False* when the page is untracked or unreadable.

    """
    p = pathlib.Path(path).resolve()
    directory = _tracked_parent(p)
    if directory is None:
        return False

    rel = p.relative_to(directory).as_posix()
    records = load_registry(directory)

    if status == STATUS_REVIEWED:
        try:
            digest = content_hash(p.read_text(encoding="utf-8"))
        except Exception:
            return False
        records[rel] = ReviewRecord(
            status=STATUS_REVIEWED,
            reviewer=reviewer,
            date=datetime.date.today().isoformat(),
            sha256=digest,
        )
    else:
        records.pop(rel, None)

    return save_registry(directory, records)


def scan() -> ReviewReport:
    """Return the review status of every tracked page.

    Returns
    -------
    ReviewReport
        Per-page statuses across all tracked directories.

    """
    pages: list[PageStatus] = []
    for directory in tracked_dirs():
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in PAGE_SUFFIXES or not path.is_file():
                continue
            pages.append(status_of(path))
    return ReviewReport(pages=pages)


# ── helpers ─────────────────────────────────────────────────────────


def _is_within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _tracked_parent(path: pathlib.Path) -> pathlib.Path | None:
    for directory in tracked_dirs():
        if _is_within(path, directory):
            return directory
    return None
