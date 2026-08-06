"""The documentation tools, the index behind them, and the help assistant.

The assistant that answers "how do I do this in ChiSurf?" is only as good as
its retrieval, so most of what is worth testing here is *which page comes
back* — a question routed to a developer note, or to the table register
because that page names every subject in the documentation, produces a fluent
answer about the wrong thing.

The end-to-end run uses a scripted model (as in ``test_runtime``), so the
whole loop — restricted registry, page reads, citation collection — is checked
without a key.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentContext
from chisurf.core.agent.doc_index import DocIndex, outline, read_body, read_section
from chisurf.core.agent.spec import SAFETY_READ, ToolError
from chisurf.core.agent.tools import documentation as doc_tools


@pytest.fixture(scope="module")
def index() -> DocIndex:
    """Return the documentation index, built once for the module."""
    return DocIndex.build()


@pytest.fixture
def context(tmp_path) -> AgentContext:
    """Return a context rooted somewhere harmless."""
    return AgentContext(working_directory=str(tmp_path))


# ── the index ─────────────────────────────────────────────────────────


def test_every_bundle_is_indexed(index):
    """The user documentation, the repository bundle, and the assistant's own."""
    bundles = {entry.bundle for entry in index.entries}
    assert {"docs", "okf", "assistant"} <= bundles
    assert len(index.entries) > 300


def test_pages_carry_the_header_they_were_given(index):
    """A page's kind and description come from its front matter, not a guess."""
    entry = index.get("docs/concepts/fret.md")
    assert entry is not None
    assert entry.type == "Concept"
    assert "energy" in entry.description.lower()
    assert "fret" in entry.tags
    assert entry.anchor == "concept-fret"


def test_the_kinds_are_the_ones_the_tools_advertise(index):
    """A tool description naming a kind that does not exist misroutes every use."""
    kinds = set(index.kinds())
    assert {"Concept", "Guide", "Fundamentals", "Plugin Reference", "File Format"} <= kinds


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("how do I fuse bursts", "docs/guides/58_burst_fusion.md"),
        ("orientation factor kappa squared", "docs/concepts/kappa2_orientation.md"),
        ("gamma correction factor smFRET", "docs/concepts/accurate_fret.md"),
    ],
)
def test_a_question_reaches_the_page_about_it(index, query, expected):
    documents = [hit["document"] for hit in index.search(query, limit=4, user_only=True)]
    assert expected in documents


def test_the_registers_do_not_win_searches(index):
    """The figure/table/code registers name every subject and explain none.

    They are the pages a term-frequency search returns for everything, which
    is what the listing penalty exists to stop.
    """
    registers = {"docs/reference/tables.md", "docs/reference/figures.md",
                 "docs/reference/code.md"}
    for query in ("chi2r", "burst search", "correlation curve"):
        top = index.search(query, limit=1, user_only=True)
        assert top, query
        assert top[0]["document"] not in registers, query


def test_a_users_question_is_not_answered_from_a_developer_note(index):
    """`user_only` is the boundary between using ChiSurf and changing it."""
    hits = index.search("plugin architecture", limit=8, user_only=True)
    assert hits
    assert all(not hit["document"].startswith("okf/") for hit in hits)
    assert all("development/" not in hit["document"] for hit in hits)


def test_related_pages_come_from_shared_tags(index):
    entry = index.get("docs/concepts/burst_fusion.md")
    related = index.related(entry)
    assert related
    assert any("burst" in other.document for other in related)


def test_a_page_reads_back_without_its_header(index):
    body = read_body("docs/concepts/fret.md")
    assert body is not None
    assert not body.lstrip().startswith("---")
    assert "Förster" in body


def test_a_section_can_be_read_on_its_own():
    body = read_body("docs/concepts/fret.md")
    headings = outline(body)
    assert headings
    first = headings[0].strip()
    section = read_section(body, first)
    assert section.startswith("#")
    assert first in section
    assert len(section) < len(body)


def test_the_index_survives_a_round_trip_through_its_cache():
    first = DocIndex.load()
    second = DocIndex.load()
    assert len(first.entries) == len(second.entries)
    assert first.entries[0] == second.entries[0]


# ── the tools ─────────────────────────────────────────────────────────


def test_browsing_unfiltered_reports_the_shape_rather_than_570_pages(context):
    result = doc_tools.browse_documentation(context)
    assert result["ok"]
    assert "kinds" in result and "tags" in result
    assert result["n_pages"] > doc_tools.BROWSE_LIMIT


def test_browsing_a_kind_lists_pages_with_their_descriptions(context):
    result = doc_tools.browse_documentation(context, kind="Fundamentals")
    assert result["ok"]
    assert result["pages"]
    assert all(page["type"] == "Fundamentals" for page in result["pages"])
    assert all(page["description"] for page in result["pages"])


def test_browsing_a_tag_crosses_the_directories(context):
    """A subject tag is the axis the folder layout cannot express."""
    result = doc_tools.browse_documentation(context, tag="fret")
    kinds = {page["type"] for page in result["pages"]}
    assert len(kinds) > 1


def test_an_unknown_filter_says_what_is_available(context):
    with pytest.raises(ToolError) as excinfo:
        doc_tools.browse_documentation(context, kind="Recipe")
    assert "Kinds:" in str(excinfo.value)


def test_a_near_miss_filter_is_offered_the_right_name(context):
    with pytest.raises(ToolError) as excinfo:
        doc_tools.browse_documentation(context, kind="Concpet")
    assert "Did you mean" in str(excinfo.value)
    assert "Concept" in str(excinfo.value)


def test_a_word_used_as_a_tag_is_sent_to_the_search(context):
    """A model's first instinct with a bare noun is to try it as a tag.

    It failed twice on "rhem weller" — once per word — and the error was a
    wall of 26 kinds and 20 tags, which taught it nothing.
    """
    with pytest.raises(ToolError) as excinfo:
        doc_tools.browse_documentation(context, tag="weller")
    assert "search_documentation" in str(excinfo.value)


def test_a_misspelled_search_finds_the_page_anyway(context):
    """The failure that made the assistant correct the user to another subject.

    Asked "rhem weller?", it searched, found nothing under *rhem*, and told
    the user their term did not exist — while a whole section of
    ``quenching_mechanisms.md`` is named after Rehm-Weller.
    """
    result = doc_tools.search_documentation(context, query="rhem weller", limit=3)
    documents = [page["document"] for page in result["pages"]]
    assert "docs/fundamentals/quenching_mechanisms.md" in documents
    assert result["corrected_from"] == {"rhem": ["rehm"]}
    assert "Say so in your answer" in result["note"]


def test_a_misspelled_phrase_still_finds_the_page(index):
    """Damerau, not Levenshtein: a transposition is one typo, not two.

    Under plain Levenshtein "rhem" is nearer to *them* than to *Rehm*, and the
    rarity tie-break is what keeps a common word from winning anyway.
    """
    assert index.near_spellings("rhem weller") == {"rhem": ["rehm"]}
    documents = [h["document"] for h in index.search("rhem weller", limit=3, user_only=True)]
    assert "docs/fundamentals/quenching_mechanisms.md" in documents


def test_a_corrected_search_says_that_it_corrected(context):
    """An answer must be able to tell the user which spelling was searched."""
    result = doc_tools.search_documentation(context, query="anisotrpy decay", limit=3)
    assert result["pages"]
    # One good word and one typo: the typo used to be silently ignored, because
    # the good word alone produced hits and the fallback never ran.
    assert result["corrected_from"]["anisotrpy"] == ["anisotropy"]


def test_the_scope_names_are_checked(context):
    with pytest.raises(ToolError):
        doc_tools.browse_documentation(context, scope="everything")


def test_scope_code_reaches_the_repository_bundle(context):
    result = doc_tools.search_documentation(
        context, query="plugin manifest", scope="code", limit=3
    )
    assert all(hit["document"].startswith("okf/") for hit in result["pages"])


def test_reading_a_section_returns_only_that_section(context):
    whole = doc_tools.read_documentation(context, document="docs/concepts/fret.md")
    heading = whole["outline"][1].strip()
    part = doc_tools.read_documentation(
        context, document="docs/concepts/fret.md", section=heading
    )
    assert len(part["content"]) < len(whole["content"])
    assert heading in part["content"]


def test_an_unknown_section_lists_the_headings(context):
    with pytest.raises(ToolError) as excinfo:
        doc_tools.read_documentation(
            context, document="docs/concepts/fret.md", section="Troubleshooting"
        )
    assert "headings are" in str(excinfo.value)


def test_reading_reports_the_related_pages(context):
    result = doc_tools.read_documentation(
        context, document="docs/concepts/burst_fusion.md", outline_only=True
    )
    assert result["related"]
    assert "content" not in result


def test_an_unknown_page_is_an_error_not_an_empty_answer(context):
    with pytest.raises(ToolError):
        doc_tools.read_documentation(context, document="docs/concepts/nonexistent.md")


def test_the_tools_are_all_read_only():
    for spec in doc_tools.registry.tools.values():
        assert spec.safety == SAFETY_READ
