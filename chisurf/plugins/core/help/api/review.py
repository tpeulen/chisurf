"""Review-status tracking for documentation pages.

Large parts of the user manual were drafted by a language model. Such a page is
useful for orientation but must not reach a release before a human has read it.
Between "nobody has looked at this" and "a human vouches for it" there is a
third, real state — **an agent has read the page end to end, corrected what it
could verify against the source code, and left nothing it knows to be wrong** —
and collapsing that into "unreviewed" throws away the only signal that says
which pages still need the *first* pass. So a tracked page carries one of four
states:

``reviewed``
    A human signed the page off *and* the file still has the content they saw.
``ai-reviewed``
    An agent read and corrected it. Worth more than nothing and less than a
    human: it cannot open the application, so it cannot tell whether a
    screenshot still matches the interface or a procedure still works. **Does
    not clear the release gate.**
``stale``
    The page was signed off at some level, but has been edited since. The
    sign-off no longer applies and the page counts as unreviewed for gating.
``unreviewed``
    Never signed off (the default for anything absent from the registry).

The distinction between a signed state and ``stale`` is why the registry stores
a content hash: without it a page could be approved once and then silently
rewritten, which is exactly the failure this module exists to prevent.

The levels form a ladder. A human sign-off replaces an agent's; an agent's never
replaces a human's, because an automated pass must not be able to quietly
downgrade what somebody actually checked.

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
STATUS_AI_REVIEWED = "ai-reviewed"
STATUS_STALE = "stale"
STATUS_UNREVIEWED = "unreviewed"

#: The sign-off ladder, weakest first. A page may only be moved *up* it by an
#: automated reviewer; a human may set any level.
REVIEW_LEVELS: tuple[str, ...] = (STATUS_UNREVIEWED, STATUS_AI_REVIEWED, STATUS_REVIEWED)

#: Statuses that record a sign-off (as opposed to its absence or expiry).
SIGNED_STATUSES: tuple[str, ...] = (STATUS_AI_REVIEWED, STATUS_REVIEWED)

#: Name of the per-directory sidecar registry.
REGISTRY_NAME = "review_status.json"

#: Documentation directories under ``docs/`` whose pages require sign-off.
#: Everything the help browser puts in front of a *user* is tracked; the
#: developer notes under ``development/`` are not, because they are not part of
#: the product. Add a directory here to bring it under review gating.
TRACKED_DIRS: tuple[str, ...] = (
    "manual",
    "fundamentals",
    "concepts",
    "guides",
    "getting_started",
    "reference",
    "references",
)

#: File suffixes treated as documentation pages.
PAGE_SUFFIXES: tuple[str, ...] = (".rst", ".md")


@dataclasses.dataclass
class ReviewRecord:
    """Sign-off recorded for a single page."""

    status: str = STATUS_UNREVIEWED
    reviewer: str = ""
    date: str = ""
    sha256: str = ""
    #: What produced the sign-off: ``"human"`` or ``"ai"``. Stored explicitly
    #: rather than inferred from *reviewer*, because a name says nothing.
    reviewer_kind: str = "human"

    def as_dict(self) -> dict[str, str]:
        """Return the record as a plain JSON-serialisable dict."""
        return {
            "status": self.status,
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
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
    reviewer_kind: str = ""
    #: The level the page held before it went stale, when it did.
    previous_status: str = ""

    @property
    def is_blocking(self) -> bool:
        """Whether this page would block a release.

        Only a *human* sign-off clears the gate: an agent cannot open the
        application, so it cannot confirm that a screenshot still matches the
        interface or that a procedure still works.
        """
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
    def ai_reviewed(self) -> list[PageStatus]:
        """Pages an agent has read and corrected, awaiting a human."""
        return [p for p in self.pages if p.status == STATUS_AI_REVIEWED]

    @property
    def unreviewed(self) -> list[PageStatus]:
        """Pages nobody and nothing has been through."""
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
            f"{len(self.ai_reviewed)} AI-reviewed, "
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
    """Return the ``docs/`` directory, or *None* when there is none to review.

    Returns
    -------
    pathlib.Path or None
        The documentation root; *None* when the installation carries no
        documentation at all.

    """
    from chisurf.plugins.core.help.api.toc import docs_root as _root

    root = _root()
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
            status = str(value.get("status", STATUS_UNREVIEWED))
            out[key] = ReviewRecord(
                status=status,
                reviewer=str(value.get("reviewer", "")),
                # Registries written before the AI level existed hold human
                # sign-offs only, so an absent kind means "human".
                reviewer_kind=str(
                    value.get(
                        "reviewer_kind",
                        "ai" if status == STATUS_AI_REVIEWED else "human",
                    )
                ),
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
    if record is None or record.status not in SIGNED_STATUSES:
        return PageStatus(path=str(p), rel_path=rel, status=STATUS_UNREVIEWED)

    try:
        current = content_hash(p.read_text(encoding="utf-8"))
    except Exception:
        current = ""
    intact = bool(current) and current == record.sha256
    return PageStatus(
        path=str(p),
        rel_path=rel,
        status=record.status if intact else STATUS_STALE,
        reviewer=record.reviewer,
        date=record.date,
        reviewer_kind=record.reviewer_kind,
        previous_status="" if intact else record.status,
    )


def set_status(path, status: str, reviewer: str = "", reviewer_kind: str = "") -> bool:
    """Record *status* for a page and persist the registry.

    Signing a page off stores the hash of its current content, so any later edit
    turns the page stale automatically.

    Parameters
    ----------
    path : str or pathlib.Path
        Documentation page.
    status : str
        :data:`STATUS_REVIEWED`, :data:`STATUS_AI_REVIEWED` or
        :data:`STATUS_UNREVIEWED` (which clears the record).
    reviewer : str, optional
        Name recorded alongside the sign-off.
    reviewer_kind : str, optional
        ``"human"`` or ``"ai"``; inferred from *status* when omitted.

    Returns
    -------
    bool
        *True* on success; *False* when the page is untracked or unreadable.

    Notes
    -----
    An **agent may not downgrade a human sign-off**. Recording
    :data:`STATUS_AI_REVIEWED` over an intact human ``reviewed`` record leaves
    the record alone and reports success: an automated pass over the whole
    manual must not quietly erase the pages somebody actually checked.

    """
    p = pathlib.Path(path).resolve()
    directory = _tracked_parent(p)
    if directory is None:
        return False

    rel = p.relative_to(directory).as_posix()
    records = load_registry(directory)

    if status not in SIGNED_STATUSES:
        records.pop(rel, None)
        return save_registry(directory, records)

    try:
        digest = content_hash(p.read_text(encoding="utf-8"))
    except Exception:
        return False

    existing = records.get(rel)
    if (
        status == STATUS_AI_REVIEWED
        and existing is not None
        and existing.status == STATUS_REVIEWED
        and existing.sha256 == digest
    ):
        return True

    if not reviewer_kind:
        reviewer_kind = "ai" if status == STATUS_AI_REVIEWED else "human"
    records[rel] = ReviewRecord(
        status=status,
        reviewer=reviewer,
        reviewer_kind=reviewer_kind,
        date=datetime.date.today().isoformat(),
        sha256=digest,
    )
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
