"""`docs/` is an Open Knowledge Format bundle, and these tests keep it one.

The documentation is read twice: by a person, who wants the prose, and by the
in-application assistant, which navigates by the machine-readable header each
page carries. The header is only worth anything if it is *always* there and
*never* shown, so both halves are guarded here — a page added without one
fails, and a header that leaks into rendered output fails.

Conformance is the specification's own: every non-reserved Markdown file
carries parseable YAML front matter with a non-empty ``type``, and the bundle
root declares the version it targets.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from build_tools.docs import okf  # noqa: E402
from build_tools.docs.okf_frontmatter import SKIP_PARTS, iter_pages  # noqa: E402

DOCS = REPO_ROOT / "docs"


def _all_pages() -> list[pathlib.Path]:
    """Every Markdown page of the bundle, generated ones included."""
    return [
        path
        for path in sorted(DOCS.rglob("*.md"))
        if not SKIP_PARTS.intersection(path.parts)
    ]


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_every_page_carries_parseable_front_matter():
    """Conformance rule 1 and 2: a header, and a non-empty ``type`` in it."""
    offenders: list[str] = []
    for path in _all_pages():
        relative = path.relative_to(DOCS).as_posix()
        text = path.read_text(encoding="utf-8")
        raw, _ = okf.split_front_matter(text)
        if not raw.strip():
            offenders.append(f"{relative}: no front matter")
            continue
        meta = okf.read_front_matter(text)
        if not meta:
            offenders.append(f"{relative}: front matter does not parse as a YAML mapping")
        elif not str(meta.get("type", "")).strip():
            offenders.append(f"{relative}: front matter has no 'type'")
    assert not offenders, "run build_tools/docs/okf_frontmatter.py\n" + "\n".join(offenders)


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_the_bundle_root_declares_the_specification_version():
    """The version is declared once, in the root index, and as a string."""
    meta = okf.read_front_matter((DOCS / "index.md").read_text(encoding="utf-8"))
    assert meta.get("okf_version") == okf.OKF_VERSION
    assert isinstance(meta["okf_version"], str), "0.10 would read as 0.1 unquoted"


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_only_the_root_declares_the_version():
    """A per-page version would let two halves of the bundle disagree."""
    declaring = [
        path.relative_to(DOCS).as_posix()
        for path in _all_pages()
        if path != DOCS / "index.md"
        and "okf_version" in okf.read_front_matter(path.read_text(encoding="utf-8"))
    ]
    assert not declaring, f"okf_version belongs only in docs/index.md: {declaring}"


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_pages_describe_themselves():
    """A description is what makes the header useful.

    A ``type`` satisfies the specification; the description is the line the
    assistant ranks on before it decides which page to read.
    """
    thin = []
    for path in _all_pages():
        meta = okf.read_front_matter(path.read_text(encoding="utf-8"))
        description = str(meta.get("description", "")).strip()
        if len(description) < 20:
            thin.append(f"{path.relative_to(DOCS).as_posix()}: {description!r}")
    assert not thin, "pages with no usable description:\n" + "\n".join(thin)


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_the_header_never_reaches_the_reader():
    """The help browser renders prose, not metadata."""
    from chisurf.plugins.core.help.api.markdown import render_markdown

    page = (DOCS / "concepts" / "fret.md").read_text(encoding="utf-8")
    html = render_markdown(page)
    assert "type: Concept" not in html
    assert "Förster" in html


def test_the_review_banner_goes_below_the_header_and_speaks_the_page_s_language():
    """Two ways the banner used to break the page it was stamping.

    Prepending anything ahead of the front matter hides it from MyST, and the
    whole header then renders as a setext heading — every stamped page's title
    became its own metadata. And a reStructuredText directive prepended to a
    Markdown page reaches the reader as the literal text ``.. warning::``.
    """
    import sys as _sys

    _sys.path.insert(0, str(DOCS / "_ext"))
    import review_banner

    page = "---\ntype: Concept\ntitle: X\n---\n\n# X\n\nbody\n"
    source = [page]
    review_banner._on_source_read(_FakeApp("/tmp/x.md"), "x", source)
    assert source[0].startswith("---\ntype: Concept")
    assert ":::{warning}" in source[0]
    assert ".. warning::" not in source[0]

    source = ["Title\n=====\n\nbody\n"]
    review_banner._on_source_read(_FakeApp("/tmp/x.rst"), "x", source)
    assert source[0].startswith(".. warning::")


class _FakeConfig:
    review_banner_enabled = True


class _FakeEnv:
    def __init__(self, path: str):
        self._path = path

    def doc2path(self, docname: str) -> str:
        return self._path


class _FakeApp:
    """Just enough Sphinx for the banner hook."""

    def __init__(self, path: str):
        self.config = _FakeConfig()
        self.env = _FakeEnv(path)


@pytest.fixture(autouse=True)
def _banner_status(monkeypatch):
    """Make every page look unreviewed, so the banner hook always fires."""
    from chisurf.plugins.core.help.api import review

    monkeypatch.setattr(review, "is_tracked", lambda path: True)
    monkeypatch.setattr(
        review,
        "status_of",
        lambda path: type("R", (), {"status": review.STATUS_UNREVIEWED})(),
    )


@pytest.mark.skipif(not DOCS.is_dir(), reason="documentation not in this distribution")
def test_titles_agree_with_the_first_heading():
    """A header whose title is not the page's title misdirects every lookup."""
    from chisurf.plugins.core.help.api.markdown import extract_title

    disagreeing = []
    for path in iter_pages(DOCS):
        text = path.read_text(encoding="utf-8")
        meta = okf.read_front_matter(text)
        heading = extract_title(text)
        if heading and str(meta.get("title", "")).strip():
            if okf.plain_text(heading) != str(meta["title"]).strip():
                disagreeing.append(
                    f"{path.relative_to(DOCS).as_posix()}: {meta['title']!r} != {heading!r}"
                )
    assert not disagreeing, "\n".join(disagreeing)
