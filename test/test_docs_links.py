"""Cross-references in the documentation must resolve.

Three kinds of link carry the documentation's connective tissue, and all three
fail silently: Sphinx emits a warning a full build buries, and the in-application
help browser renders a dead link as plain text. A reader sees a phrase that
looks like a reference to something and simply cannot follow it.

- ``{cite}`key```   -> an entry in docs/references/bibliography.yaml
- ``{ref}`anchor``` -> an ``(anchor)=`` target defined by some page
- ``{doc}`/path```  -> a page that exists on disk
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SKIP = ("_build", "_old_manual", "_ext")

CITE = re.compile(r"\{cite\}`([^`\n]+)`")
REF = re.compile(r"\{ref\}`([^`\n]+)`")
DOC = re.compile(r"\{doc\}`([^`\n]+)`")
ANCHOR = re.compile(r"^\(([A-Za-z0-9_.-]+)\)=", re.M)

#: Used in documentation-maintenance prose as a literal example of the syntax,
#: not as a citation of a work named "key".
LITERAL_EXAMPLES = {"key"}

#: Targets Sphinx generates itself, which no page declares.
BUILTIN_TARGETS = {"genindex", "modindex", "search"}

#: A bare "/" appears on the maintenance page as an illustration of the role,
#: not as a link to anything.
LITERAL_DOC_TARGETS = {"/"}


def _pages():
    for path in sorted(DOCS.rglob("*.md")):
        if any(p in path.parts for p in SKIP):
            continue
        yield path, path.read_text(encoding="utf-8", errors="replace")
    for path in sorted(DOCS.rglob("*.rst")):
        if any(p in path.parts for p in SKIP):
            continue
        yield path, path.read_text(encoding="utf-8", errors="replace")


def _target_text(raw: str) -> str:
    """``{ref}`shown text <anchor>``` -> ``anchor``; otherwise unchanged."""
    match = re.search(r"<([^>]+)>\s*$", raw.strip())
    return (match.group(1) if match else raw).strip()


def test_every_citation_resolves():
    """A {cite} key names an entry in the bibliography."""
    bib = set(yaml.safe_load((DOCS / "references" / "bibliography.yaml").read_text()))
    bad = []
    for path, text in _pages():
        for m in CITE.finditer(text):
            for key in (k.strip() for k in m.group(1).split(",")):
                if key and key not in bib and key not in LITERAL_EXAMPLES:
                    bad.append(f"{path.relative_to(REPO).as_posix()}: {{cite}}`{key}`")
    assert not bad, "citations with no bibliography entry:\n" + "\n".join(sorted(set(bad)))


def test_every_ref_resolves():
    """A {ref} names an anchor some page actually defines."""
    anchors = set()
    for _, text in _pages():
        anchors.update(ANCHOR.findall(text))
    bad = []
    for path, text in _pages():
        for m in REF.finditer(text):
            target = _target_text(m.group(1))
            if target and target not in anchors and target not in BUILTIN_TARGETS:
                bad.append(f"{path.relative_to(REPO).as_posix()}: {{ref}}`{target}`")
    assert not bad, "references to undefined anchors:\n" + "\n".join(sorted(set(bad)))


def test_every_doc_link_resolves():
    """A {doc} names a page that is on disk."""
    bad = []
    for path, text in _pages():
        for m in DOC.finditer(text):
            target = _target_text(m.group(1))
            if not target or target in LITERAL_DOC_TARGETS:
                continue
            base = DOCS / target.lstrip("/") if target.startswith("/") else path.parent / target
            if not (base.with_suffix(".md").exists() or base.with_suffix(".rst").exists()):
                bad.append(f"{path.relative_to(REPO).as_posix()}: {{doc}}`{target}`")
    assert not bad, "links to pages that do not exist:\n" + "\n".join(sorted(set(bad)))
