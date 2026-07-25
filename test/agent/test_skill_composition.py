"""Skills are composable: a procedure can be built out of smaller procedures.

Without this, a workflow that spans several methods has one bad choice and one
worse one — repeat the sub-procedures in every skill that needs them, or write
one monolith that cannot be reused a step at a time. A ``uses:`` declaration
makes the composition explicit, and loading a skill loads what it is made of.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent.skills import Skill, SkillLibrary, parse_skill


def library(*skills: Skill) -> SkillLibrary:
    """Return a library holding *skills*."""
    built = SkillLibrary()
    for skill in skills:
        built.add(skill)
    return built


def skill(name: str, *, uses=(), triggers=()) -> Skill:
    """Return a minimal skill."""
    return Skill(
        name=name,
        description=f"{name} description.",
        body=f"body of {name}",
        triggers=list(triggers),
        uses=list(uses),
    )


# ── the declaration ───────────────────────────────────────────────────


def test_uses_is_read_from_the_frontmatter():
    parsed = parse_skill(
        "---\n"
        "name: whole\n"
        "description: A composed procedure.\n"
        "uses: [part-one, part-two]\n"
        "---\n\n"
        "# Whole\n"
    )
    assert parsed.uses == ["part-one", "part-two"]


def test_a_skill_without_uses_composes_to_itself():
    single = skill("alone")
    assert library(single).compose([single]) == [single]


# ── composition ───────────────────────────────────────────────────────


def test_the_parts_come_with_the_whole():
    parts = [skill("part-one"), skill("part-two")]
    whole = skill("whole", uses=["part-one", "part-two"])
    composed = library(whole, *parts).compose([whole])

    assert [s.name for s in composed] == ["whole", "part-one", "part-two"]


def test_composition_is_transitive():
    """A part built of parts brings its own."""
    deep = skill("deep")
    middle = skill("middle", uses=["deep"])
    top = skill("top", uses=["middle"])

    assert [s.name for s in library(top, middle, deep).compose([top])] == [
        "top",
        "middle",
        "deep",
    ]


def test_a_skill_is_injected_once_however_many_paths_reach_it():
    shared = skill("shared")
    left = skill("left", uses=["shared"])
    right = skill("right", uses=["shared"])
    top = skill("top", uses=["left", "right"])

    names = [s.name for s in library(top, left, right, shared).compose([top])]
    assert names.count("shared") == 1


def test_a_cycle_terminates():
    """Two skills that use each other must not hang the request."""
    first = skill("first", uses=["second"])
    second = skill("second", uses=["first"])

    names = [s.name for s in library(first, second).compose([first])]
    assert sorted(names) == ["first", "second"]


def test_an_unknown_dependency_is_skipped_not_fatal():
    """A user skill may name a part they have not written yet."""
    whole = skill("whole", uses=["missing"])
    assert [s.name for s in library(whole).compose([whole])] == ["whole"]


# ── routing ───────────────────────────────────────────────────────────


def test_dependencies_do_not_compete_for_the_match_limit():
    """The point of the cut is to bound *topics*, not to starve a composition."""
    parts = [skill(f"part-{i}") for i in range(3)]
    whole = skill("whole", uses=[p.name for p in parts], triggers=["burst distance"])
    matched = library(whole, *parts).match("give me the burst distance", limit=1)

    assert [s.name for s in matched] == ["whole", "part-0", "part-1", "part-2"]


# ── the built-in library ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def builtins():
    """Return the shipped skill library."""
    return SkillLibrary.discover()


def test_every_declared_part_exists(builtins):
    """A typo in ``uses`` would silently drop a step of a procedure."""
    for name, entry in builtins.skills.items():
        for dependency in entry.uses:
            assert dependency in builtins.skills, f"{name} uses unknown skill {dependency!r}"


def test_no_builtin_skill_composes_itself(builtins):
    for name, entry in builtins.skills.items():
        assert name not in entry.uses, f"{name} uses itself"


def test_the_smfret_workflow_is_a_composition(builtins):
    """The user-facing claim: smFRET is several skills, and they compose."""
    smfret = {"burst-search", "burst-selection", "sub-ensemble-decay", "fret-from-bursts"}
    assert smfret <= set(builtins.skills), "the smFRET skills are missing"

    chain = [s.name for s in builtins.compose([builtins.skills["fret-from-bursts"]])]
    assert chain[0] == "fret-from-bursts"
    for part in smfret | {"fret-from-decays"}:
        assert part in chain, f"{part} is not reached from fret-from-bursts"


def test_the_headline_request_reaches_the_whole_chain(builtins):
    """Routing plus composition, on the wording a user actually typed."""
    matched = [
        s.name
        for s in builtins.match(
            "process the smfret burst data, select bursts with proximity ratio "
            "0.5-0.7 and determine the distance by tcspc"
        )
    ]
    for part in ("fret-from-bursts", "burst-search", "burst-selection", "sub-ensemble-decay"):
        assert part in matched, f"{part} missing from {matched}"


def test_each_smfret_skill_is_useful_on_its_own(builtins):
    """Decomposition is only real if the parts route independently."""
    for question, expected in (
        ("how many bursts are in this measurement?", "burst-search"),
        ("show me the proximity ratio histogram", "burst-selection"),
        ("build a sub-ensemble decay for that population", "sub-ensemble-decay"),
    ):
        matched = [s.name for s in builtins.match(question)]
        assert expected in matched, f"{question!r} -> {matched}"
