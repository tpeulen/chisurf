"""What expert mode produces: structured findings about the documentation.

Signing a page off says "this is fine". This is the other half -- saying what is
*not*, and saying it in a form somebody can act on.

Because the game is gamepad-playable there is no typing, and that turns out to
be a feature rather than a constraint. A finding is a **span plus a category**:
the exact sentence at fault, and which of a fixed list of faults it is. That is
more useful than prose, not less -- it is machine-checkable, it points at an
exact location, and two people flagging the same problem produce the same
record.

Two safety rules, and both come from this being a shared working tree:

* **Nothing is written into** ``docs/``. Findings pool in the per-user directory.
  Several agents and the user hold uncommitted edits in this repository at once,
  and a game that writes into the documentation during play would silently
  destroy work.
* **A finding is bound to the page's content hash.** Exporting one whose page
  has since changed would point at a line that has moved or gone, so those are
  reported as stale instead of exported.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib

#: The faults a player can report. Fixed, because a fixed list is what makes the
#: output comparable -- and because there is no keyboard to type a new one on.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("undefined-symbol", "a symbol used before it is defined"),
    ("wrong-units", "the units are wrong or missing"),
    ("missing-citation", "a claim with nothing to back it"),
    ("contradicts", "this contradicts another page"),
    ("stale-screenshot", "the picture no longer matches the interface"),
    ("dead-link", "the link goes nowhere"),
    ("unstated-assumption", "an assumption nobody states"),
    ("notation-drift", "the notation disagrees with the code"),
)

#: Where findings pool. Outside the repository, deliberately.
FINDINGS_FILE = pathlib.Path.home() / ".chisurf" / "lumis_quest_findings.json"


@dataclasses.dataclass
class Finding:
    """One reported defect.

    Attributes
    ----------
    address : str
        Repository-relative page address.
    content_hash : str
        The page's hash when the finding was made.
    span : str
        The exact sentence at fault.
    category : str
        One of the keys in :data:`CATEGORIES`.
    found_at : str
        ISO date the finding was made.
    """

    address: str
    content_hash: str
    span: str
    category: str
    found_at: str = ""

    def __post_init__(self) -> None:
        """Stamp the date when one was not supplied."""
        if not self.found_at:
            self.found_at = datetime.date.today().isoformat()

    @property
    def describes(self) -> str:
        """The category in words.

        Returns
        -------
        str
            The human-readable description, or the raw key if unknown.
        """
        return dict(CATEGORIES).get(self.category, self.category)

    def as_dict(self) -> dict:
        """Serialise to plain JSON types.

        Returns
        -------
        dict
            Ready for :func:`json.dumps`.
        """
        return dataclasses.asdict(self)


def load(path: pathlib.Path | None = None) -> list[Finding]:
    """Read the pooled findings.

    Parameters
    ----------
    path : pathlib.Path, optional
        Source file.

    Returns
    -------
    list of Finding
        Empty when there are none, or the file cannot be read.
    """
    source = path or FINDINGS_FILE
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            found.append(Finding(**entry))
        except TypeError:
            continue
    return found


def save(findings: list[Finding], path: pathlib.Path | None = None) -> pathlib.Path:
    """Write the pooled findings.

    Parameters
    ----------
    findings : list of Finding
        What to store.
    path : pathlib.Path, optional
        Destination.

    Returns
    -------
    pathlib.Path
        Where it was written.
    """
    target = path or FINDINGS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([finding.as_dict() for finding in findings], indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def add(finding: Finding, path: pathlib.Path | None = None) -> list[Finding]:
    """Pool one finding, without duplicating it.

    Parameters
    ----------
    finding : Finding
        What was found.
    path : pathlib.Path, optional
        Destination.

    Returns
    -------
    list of Finding
        The pool after adding.
    """
    pool = load(path)
    for existing in pool:
        same_place = (existing.address, existing.span) == (finding.address, finding.span)
        if same_place and existing.category == finding.category:
            return pool
    pool.append(finding)
    save(pool, path)
    return pool


def current_hash(page: pathlib.Path) -> str:
    """The page's hash right now.

    Parameters
    ----------
    page : pathlib.Path
        The page.

    Returns
    -------
    str
        Its content hash, or ``""`` when it cannot be read.
    """
    from chisurf.plugins.core.help.api import review

    try:
        return review.content_hash(page.read_text(encoding="utf-8"))
    except OSError:
        return ""


def export(
    findings: list[Finding],
    repo_root: pathlib.Path,
    destination: pathlib.Path,
) -> tuple[int, int]:
    """Write the findings out as a report a person can work from.

    Parameters
    ----------
    findings : list of Finding
        The pool.
    repo_root : pathlib.Path
        Directory the addresses are relative to.
    destination : pathlib.Path
        Where to write the report.

    Returns
    -------
    tuple of int
        ``(exported, stale)``. A finding whose page has changed since it was
        made is **not** exported: it points at a sentence that has moved or
        gone, and a report full of stale line references is worse than a short
        accurate one.
    """
    fresh: list[Finding] = []
    stale = 0
    for finding in findings:
        page = repo_root / finding.address
        if finding.content_hash and current_hash(page) != finding.content_hash:
            stale += 1
            continue
        fresh.append(finding)

    by_page: dict[str, list[Finding]] = {}
    for finding in fresh:
        by_page.setdefault(finding.address, []).append(finding)

    lines = [
        "# Documentation findings",
        "",
        f"{len(fresh)} finding(s) across {len(by_page)} page(s)."
        + (f" {stale} stale finding(s) omitted." if stale else ""),
        "",
    ]
    for address in sorted(by_page):
        lines.append(f"## {address}")
        lines.append("")
        for finding in by_page[address]:
            lines.append(f"- **{finding.category}** — {finding.describes}")
            lines.append(f"  > {finding.span}")
            lines.append("")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return len(fresh), stale
