"""The ``sources:`` front-matter block must stay usable as attribution.

``docs/`` is CC BY-SA 4.0, so a page that adapts outside material owes credit to
it. The obligation is per page and is declared in front matter, rendered by
``docs/_ext/source_attribution.py``. A block that is malformed, that names a
licence the documentation cannot absorb, or that credits nothing reachable is
worse than no block at all -- it looks like the obligation was met.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

#: Kept in step with the inbound table in docs/licensing.md and with
#: source_attribution.ACCEPTED.
ACCEPTED = {
    "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-4.0", "CC-BY-3.0",
    "CC0-1.0", "public-domain",
}


def _pages():
    """Yield (path, front-matter mapping) for every documentation page."""
    for path in sorted(DOCS.rglob("*.md")):
        if any(p in path.parts for p in ("_build", "_old_manual", "_ext")):
            continue
        match = FRONT_MATTER.match(path.read_text(encoding="utf-8", errors="replace"))
        if not match:
            continue
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            continue
        if isinstance(meta, dict):
            yield path, meta


def _declared():
    """Yield (path, source-entry) for every declared source."""
    for path, meta in _pages():
        for entry in meta.get("sources") or []:
            yield path, entry


def test_every_source_entry_is_well_formed():
    """A source names what was taken, from where, and under what terms."""
    bad = []
    for path, entry in _declared():
        rel = path.relative_to(REPO).as_posix()
        if not isinstance(entry, dict):
            bad.append(f"{rel}: entry is {type(entry).__name__}, not a mapping")
            continue
        for field in ("text", "url", "licence"):
            if not str(entry.get(field, "")).strip():
                bad.append(f"{rel}: source is missing {field!r}")
    assert not bad, "malformed sources: entries:\n" + "\n".join(bad)


def test_every_source_licence_can_be_absorbed():
    """The documentation cannot relicense NC/ND or GPL-only prose as CC BY-SA."""
    bad = []
    for path, entry in _declared():
        if not isinstance(entry, dict):
            continue
        licence = str(entry.get("licence", "")).strip()
        if licence and licence not in ACCEPTED:
            bad.append(
                f"{path.relative_to(REPO).as_posix()}: {licence!r} is not one the "
                f"documentation can absorb (see docs/licensing.md)"
            )
    assert not bad, "unusable source licences:\n" + "\n".join(bad)


def test_every_source_url_is_a_link():
    """A bare title is not attribution -- the reader has to be able to get there."""
    bad = []
    for path, entry in _declared():
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        if url and not url.startswith(("http://", "https://")):
            bad.append(f"{path.relative_to(REPO).as_posix()}: {url!r} is not a URL")
    assert not bad, "unreachable source URLs:\n" + "\n".join(bad)


def test_the_renderer_and_this_test_agree_on_what_is_accepted():
    """Two lists of accepted licences drift; pin them together."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "source_attribution", DOCS / "_ext" / "source_attribution.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ACCEPTED == ACCEPTED
