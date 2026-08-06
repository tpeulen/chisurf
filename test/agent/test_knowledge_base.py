"""The assistant's own knowledge bundle.

This is not the repository's ``okf/``: that one describes how ChiSurf is
built, this one what fluorescence analysis and ChiSurf's objects mean. It is
what lets a skill stay a procedure instead of a textbook.
"""

from __future__ import annotations

import re

import pytest
import yaml

from chisurf.core.agent import AgentContext, build_default_registry
from chisurf.core.agent.knowledge import (
    iter_prose_documents,
    knowledge_base_root,
    search_prose,
)
from chisurf.core.agent.skills import SkillLibrary
from chisurf.core.agent.tools import codebase as codebase_tools

BUNDLE = knowledge_base_root()
CONCEPTS = sorted((BUNDLE / "concepts").glob("*.md"))


def _frontmatter(text: str) -> dict:
    """Return the YAML frontmatter of a document, or an empty dict."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        return {}
    loaded = yaml.safe_load(match.group(1))
    return loaded if isinstance(loaded, dict) else {}


# ── the bundle ────────────────────────────────────────────────────────


def test_the_bundle_ships_with_the_package():
    assert BUNDLE.is_dir()
    assert (BUNDLE / "index.md").is_file()
    assert len(CONCEPTS) >= 5


def test_it_is_separate_from_the_repository_bundle():
    """The two answer different questions and must not be conflated."""
    from chisurf.core.agent.knowledge import repository_root

    assert BUNDLE != repository_root() / "okf"
    index = (BUNDLE / "index.md").read_text(encoding="utf-8")
    assert "okf/" in index, "the index should say how it differs from the repository bundle"


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda p: p.stem)
def test_every_concept_carries_okf_frontmatter(concept):
    meta = _frontmatter(concept.read_text(encoding="utf-8"))
    assert meta.get("type"), f"{concept.name} has no type"
    assert meta.get("title"), f"{concept.name} has no title"
    assert meta.get("description"), f"{concept.name} has no description"


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda p: p.stem)
def test_every_concept_has_substance(concept):
    body = concept.read_text(encoding="utf-8").split("---", 2)[-1]
    assert len(body) > 800, f"{concept.name} is too thin to be worth a lookup"


def test_the_index_links_to_documents_that_exist():
    index = (BUNDLE / "index.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\((concepts/[^)]+)\)", index)
    assert links, "the index lists no concepts"
    for link in links:
        assert (BUNDLE / link).is_file(), f"the index links to a missing concept: {link}"


def test_every_concept_is_listed_in_the_index():
    index = (BUNDLE / "index.md").read_text(encoding="utf-8")
    for concept in CONCEPTS:
        assert concept.name in index, f"{concept.name} is not listed in the index"


# ── reachable by the agent ────────────────────────────────────────────


def test_the_concepts_are_part_of_the_searchable_corpus():
    documents = {path.name for path in iter_prose_documents()}
    assert {concept.name for concept in CONCEPTS} <= documents


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("confidence interval", "uncertainty-and-model-choice.md"),
        ("donor only fraction", "fret-from-lifetimes.md"),
        ("instrument response deconvolution", "tcspc-decays.md"),
    ],
)
def test_a_question_reaches_the_concept_about_it(query, expected):
    found = [hit["document"].split("/")[-1] for hit in search_prose(query, limit=3)]
    assert expected in found


def test_a_concept_can_be_read_back(tmp_path):
    """A search result's identifier is one the read tool accepts.

    The two are separate calls and nothing forces them to agree on how a page
    is named; when they disagree the model finds the right page and then
    cannot open it.
    """
    from chisurf.core.agent.tools import documentation as documentation_tools

    context = AgentContext(working_directory=str(tmp_path))
    hit = search_prose("confidence interval", limit=1)[0]
    result = documentation_tools.read_documentation(context, document=hit["document"])
    assert "support plane" in result["content"].lower()


# ── the skills that rest on it ────────────────────────────────────────


def test_the_uncertainty_skill_exists_and_routes():
    library = SkillLibrary.discover()
    assert library.get("estimate-uncertainty") is not None
    for question in (
        "how certain is that lifetime?",
        "give me confidence intervals",
        "is the third component justified?",
        "are these error bars right?",
    ):
        matched = [skill.name for skill in library.match(question, limit=3)]
        assert "estimate-uncertainty" in matched, question


SKILLS = sorted(SkillLibrary.discover().skills.values(), key=lambda s: s.name)


@pytest.mark.parametrize("skill", SKILLS, ids=lambda s: s.name)
def test_code_in_a_skill_is_valid_python(skill):
    """A recipe a model copies has to compile, or it teaches a syntax error."""
    blocks = re.findall(r"```python\n(.*?)```", skill.body, flags=re.DOTALL)
    for index, block in enumerate(blocks):
        try:
            compile(block, f"{skill.name}#{index}", "exec")
        except SyntaxError as error:
            pytest.fail(f"{skill.name} code block {index} does not compile: {error}")


@pytest.mark.parametrize("skill", SKILLS, ids=lambda s: s.name)
def test_a_skill_only_promises_tools_that_exist(skill):
    known = set(build_default_registry().names())
    unknown = [tool for tool in skill.tools if tool not in known]
    assert not unknown, f"{skill.name} lists tools that do not exist: {unknown}"


def test_skill_links_into_the_knowledge_base_resolve():
    """A skill that points at a missing concept teaches nothing."""
    skills_root = BUNDLE.parent / "skills_builtin"
    for path in sorted(skills_root.rglob("SKILL.md")):
        for link in re.findall(r"\]\((\.\./[^)]+\.md)\)", path.read_text(encoding="utf-8")):
            assert (path.parent / link).resolve().is_file(), f"{path.parent.name}: {link}"
