"""Guard: the shipped package does not name PRDs.

**The rule: source does not mention PRDs.** A PRD is a planning artifact — it
has a lifecycle (`planned` → `in-progress` → `done`), it gets superseded, and
its number means nothing to someone reading the code. A comment saying "see
PRD-82" is a pointer that goes stale on its own and that the reader cannot
follow from inside the file. The durable pointer is the **OKF concept** that
owns the area, which is maintained precisely because it describes what *is*
rather than what was planned.

So write::

    # See the columnar-store concept (/subsystems/columnar-store.md).

and not::

    # See PRD-82.

Often the right fix is neither: a reference that only says "this was designed
somewhere" adds nothing the code does not already say, and should go.

Scope is the shipped package, `chisurf/` — its Python, its `view.json` view
specs, its YAML settings and its shipped markdown. `okf/` is where PRDs live and
`test/` documents process, so neither is covered.

`test/prd_mention_allowlist.txt` is a **shrinking** record of files written
before the rule; it is never somewhere to add yourself to make this test pass.
The end state is an empty list and the deletion of both files.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "prd_mention_allowlist.txt"

#: Extensions that count as shipped source.
_SUFFIXES = {".py", ".json", ".md", ".ui", ".yaml", ".yml", ".rst"}

#: "PRD-82", "PRD 82", "PRD_82", "PRDs 5", "prd82" — every spelling seen in the
#: tree. A bare "PRD" with no number is prose about the process and is allowed.
_PRD_RE = re.compile(r"\bPRDs?[\s\-_]?#?\d+", re.IGNORECASE)


def _load_allowlist() -> set[str]:
    """Return the allow-listed repo-relative paths.

    Returns
    -------
    set of str
    """
    if not _ALLOWLIST.exists():
        return set()
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_mentions() -> set[str]:
    """Return every shipped-source file that names a PRD.

    Returns
    -------
    set of str
        Repo-relative POSIX paths.
    """
    found = set()
    for path in _PKG.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _PRD_RE.search(text):
            found.add(path.relative_to(_ROOT).as_posix())
    return found


def test_no_new_prd_mentions_in_source():
    """No shipped-source file names a PRD unless it is allow-listed."""
    offenders = sorted(_current_mentions() - _load_allowlist())
    assert not offenders, (
        "Source must not name a PRD — point at the OKF concept that owns the "
        "area instead, or drop the reference:\n  " + "\n  ".join(offenders)
    )


def test_prd_mention_allowlist_has_no_stale_entries():
    """Every allow-listed file still names a PRD.

    A file that has been cleaned must be struck from the list, otherwise the
    list stops being a worklist and starts being decoration.
    """
    stale = sorted(_load_allowlist() - _current_mentions())
    assert not stale, (
        "These files no longer name a PRD — strike them from "
        "test/prd_mention_allowlist.txt:\n  " + "\n  ".join(stale)
    )
