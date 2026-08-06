"""The documentation is a web, and these are the strands that must not break.

Two layers explain the same analysis from different ends: a concept says what a
method measures, a guide says which buttons to press. Either one alone leaves
the reader stuck — the theory with no way to run it, the recipe with no way to
know what it means — so every page carries the link across, and a cross-
reference has to resolve to a page that exists.
"""

import pathlib
import re

import pytest

from chisurf.plugins.core.help.api import toc as toc_api
from chisurf.plugins.core.help.api import xref

#: Guides that document the application itself rather than an analysis, and so
#: have no concept page to point at.
GUIDES_WITHOUT_A_CONCEPT = {
    "40_ai_assistant.md",
    "53_reusing_results.md",
    "59_console.md",
    "index.md",
}

_MD_LINK = re.compile(r"\]\(([^)]+)\)")
_ROLE = re.compile(r"\{(?:doc|ref)\}`([^`]+)`")


def _targets(path: pathlib.Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    targets = set(_MD_LINK.findall(text))
    targets |= {
        body.split("<")[-1].strip("<> ") for body in _ROLE.findall(text)
    }
    return targets


def _concept_pages() -> list[pathlib.Path]:
    return sorted(toc_api.docs_root().glob("concepts/*.md"))


def _guide_pages() -> list[pathlib.Path]:
    return [
        path
        for path in sorted(toc_api.docs_root().glob("guides/*.md"))
        if path.name not in GUIDES_WITHOUT_A_CONCEPT
    ]


def test_every_concept_points_at_a_guide():
    missing = [
        path.name
        for path in _concept_pages()
        if not any("guides/" in target for target in _targets(path))
    ]
    assert not missing, missing


def test_every_guide_points_at_a_concept():
    missing = [
        path.name
        for path in _guide_pages()
        if not any("concept" in target for target in _targets(path))
    ]
    assert not missing, missing


@pytest.mark.parametrize("page", _concept_pages() + _guide_pages(), ids=lambda p: p.name)
def test_cross_references_resolve(page):
    """A role that resolves to nothing is shown as plain words — a dead end."""
    text = page.read_text(encoding="utf-8")
    dead = []
    for role, body in re.findall(r"\{(doc|ref|numref)\}`([^`]+)`", text):
        target, _anchor, _label = xref.document_reference(role, body, page.parent)
        if target is None:
            dead.append(f"{{{role}}}`{body}`")
    assert not dead, dead


@pytest.mark.parametrize("page", _concept_pages() + _guide_pages(), ids=lambda p: p.name)
def test_document_links_resolve(page):
    """``[text](other.md)`` must name a page that is really there."""
    dead = []
    for target in _targets(page):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if not target.endswith((".md", ".rst")) and ".md#" not in target:
            continue
        path = target.split("#", 1)[0]
        if xref.resolve_document(path, page.parent) is None:
            dead.append(target)
    assert not dead, dead
