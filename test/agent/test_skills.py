"""Tests for the skill layer: parsing, discovery, routing and auto-loading."""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentConfig, AgentSession
from chisurf.core.agent.skills import (
    Skill,
    SkillLibrary,
    builtin_skill_directory,
    parse_skill,
    session_experiments,
    trigger_pattern,
)

SKILL_TEXT = """\
---
name: demo-skill
description: A demonstration skill. Use when demonstrating.
triggers: [demo, show me]
experiments: [TCSPC]
tools: [run_fit]
---

# Demo

Step one. Step two.
"""


# ── parsing ───────────────────────────────────────────────────────────


def test_frontmatter_and_body_are_parsed():
    skill = parse_skill(SKILL_TEXT, source="/tmp/demo/SKILL.md")
    assert skill.name == "demo-skill"
    assert skill.description.startswith("A demonstration skill")
    assert skill.triggers == ["demo", "show me"]
    assert skill.experiments == ["TCSPC"]
    assert skill.tools == ["run_fit"]
    assert "Step one" in skill.body
    assert "---" not in skill.body


def test_a_document_without_frontmatter_takes_its_name_from_the_directory():
    skill = parse_skill("# Just a body", source="/tmp/my-skill/SKILL.md")
    assert skill.name == "my-skill"
    assert skill.body == "# Just a body"


def test_a_nameless_skill_is_rejected():
    assert parse_skill("# Body with no name and no path") is None


def test_comma_separated_metadata_is_accepted():
    skill = parse_skill("---\nname: s\ntriggers: a, b , c\n---\nbody")
    assert skill.triggers == ["a", "b", "c"]


def test_broken_frontmatter_does_not_raise():
    skill = parse_skill("---\nname: [unclosed\n---\nbody", source="/tmp/x/SKILL.md")
    assert skill is not None and skill.name == "x"


# ── trigger matching ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("trigger", "text", "expected"),
    [
        ("decay", "fit this decay", True),
        ("decay", "fit these decays", True),
        ("decay", "the decayed sample", False),
        ("all files", "fit all 20 files", True),
        ("all files", "fit all of the files", True),
        ("all files", "all my careful measurements are in files", False),
        ("chi-square", "the chi-square is bad", True),
        ("fcs", "an fcs curve", True),
        ("fcs", "specfcsx", False),
    ],
)
def test_triggers_tolerate_real_phrasing(trigger, text, expected):
    assert bool(trigger_pattern(trigger).search(text)) is expected


def test_an_empty_trigger_matches_nothing():
    assert trigger_pattern("   ").search("anything") is None


# ── scoring and routing ───────────────────────────────────────────────


def test_the_session_experiment_type_is_a_weak_signal():
    skill = parse_skill(SKILL_TEXT, source="/tmp/demo/SKILL.md")
    assert skill.score("something unrelated") == 0.0
    assert skill.score("something unrelated", ["TCSPC"]) == 1.0
    assert skill.score("show me the demo", ["TCSPC"]) >= 4.0


def test_naming_a_skill_outright_wins():
    skill = parse_skill(SKILL_TEXT, source="/tmp/demo/SKILL.md")
    assert skill.score("use demo skill please") >= 3.0


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("fit the decay in this folder", "fit-decay"),
        ("what lifetime does this sample have?", "fit-decay"),
        ("what is in my data folder?", "explore-data"),
        ("why is the chi2 so bad?", "diagnose-fit"),
        ("write me a script that sums the counts", "write-analysis-script"),
        ("fit the FCS correlation curves", "fit-correlation"),
        ("fit each of my samples and compare them", "batch-fitting"),
        ("export the results to csv", "report-results"),
    ],
)
def test_the_builtin_skills_route_real_requests(question, expected):
    library = SkillLibrary.discover()
    assert expected in [skill.name for skill in library.match(question)]


def test_small_talk_loads_no_skill():
    assert SkillLibrary.discover().match("hello, how are you today?") == []


def test_matching_is_capped():
    library = SkillLibrary.discover()
    matched = library.match(
        "fit every decay, diagnose the chi2, export a csv and write a script", limit=2
    )
    assert len(matched) == 2


# ── the built-in library ──────────────────────────────────────────────


def test_every_builtin_skill_is_well_formed():
    library = SkillLibrary.discover()
    assert len(library.skills) >= 7
    for skill in library.skills.values():
        assert skill.description, f"{skill.name} has no description"
        assert "Use when" in skill.description or "Use whenever" in skill.description, (
            f"{skill.name}'s description must say when to use it — that is the routing signal"
        )
        assert skill.triggers, f"{skill.name} has no triggers"
        assert len(skill.body) > 400, f"{skill.name} carries too little procedure"


def test_builtin_skills_only_name_tools_that_exist():
    from chisurf.core.agent import build_default_registry

    known = set(build_default_registry().names())
    for skill in SkillLibrary.discover().skills.values():
        unknown = [tool for tool in skill.tools if tool not in known]
        assert not unknown, f"{skill.name} names tools that do not exist: {unknown}"


def test_a_user_skill_overrides_a_builtin_one(tmp_path):
    override = tmp_path / "fit-decay"
    override.mkdir()
    (override / "SKILL.md").write_text(
        "---\nname: fit-decay\ndescription: Mine. Use when testing.\n---\nlocal body",
        encoding="utf-8",
    )
    library = SkillLibrary.discover(extra_directories=[tmp_path])
    assert library.get("fit-decay").body == "local body"


def test_the_catalogue_can_exclude_the_loaded_skills():
    library = SkillLibrary.discover()
    catalogue = library.catalogue(exclude=["fit-decay"])
    assert "fit-decay" not in catalogue
    assert "diagnose-fit" in catalogue


def test_skills_are_discoverable_from_the_installed_package():
    assert (builtin_skill_directory() / "fit-decay" / "SKILL.md").is_file()


# ── auto-loading in the session ───────────────────────────────────────


@pytest.fixture()
def library():
    """Return a two-skill library independent of the built-in documents."""
    built = SkillLibrary()
    built.add(
        Skill(
            name="demo-skill",
            description="Demo. Use when demonstrating.",
            body="Do the demo thing.",
            triggers=["demo"],
        )
    )
    built.add(
        Skill(
            name="other-skill",
            description="Other. Use when othering.",
            body="Do the other thing.",
            triggers=["other"],
        )
    )
    return built


def _session(context, library, script=("done",), **config):
    """Build a scripted session wired to *library*."""
    from test.agent.test_runtime import ScriptedLLM

    return AgentSession(
        ScriptedLLM(list(script)),
        context=context,
        config=AgentConfig(**config),
        skills=library,
    )


def test_a_matching_skill_is_loaded_before_the_model_sees_the_question(context, library):
    agent = _session(context, library)
    agent.ask("please run the demo")

    assert agent.active_skills == ["demo-skill"]
    system_prompt = agent.llm.calls[0]["messages"][0]["content"]
    assert "Do the demo thing." in system_prompt
    assert "Active skill" in system_prompt


def test_unmatched_skills_are_only_advertised(context, library):
    agent = _session(context, library)
    agent.ask("please run the demo")
    system_prompt = agent.llm.calls[0]["messages"][0]["content"]
    assert "Do the other thing." not in system_prompt
    assert "other-skill" in system_prompt


def test_no_match_loads_nothing(context, library):
    agent = _session(context, library)
    agent.ask("hello there")
    assert agent.active_skills == []


def test_a_loaded_skill_survives_a_follow_up(context, library):
    agent = _session(context, library, script=["one", "two"])
    agent.ask("run the demo")
    agent.ask("and now?")
    assert agent.active_skills == ["demo-skill"]
    assert "Do the demo thing." in agent.llm.calls[1]["messages"][0]["content"]


def test_a_second_topic_adds_its_skill(context, library):
    agent = _session(context, library, script=["one", "two"])
    agent.ask("run the demo")
    agent.ask("now do the other thing")
    assert set(agent.active_skills) == {"demo-skill", "other-skill"}


def test_auto_loading_can_be_switched_off(context, library):
    agent = _session(context, library, auto_load_skills=False)
    agent.ask("please run the demo")
    assert agent.active_skills == []
    assert "other-skill" in agent.llm.calls[0]["messages"][0]["content"]


def test_the_number_of_active_skills_is_capped(context, library):
    agent = _session(context, library, max_active_skills=1)
    agent.ask("run the demo and the other thing")
    assert len(agent.active_skills) == 1


def test_loading_emits_an_event(clean_session, tmp_path, library):
    from chisurf.core.agent import AgentContext

    events = []
    context = AgentContext(
        working_directory=str(tmp_path),
        event_callback=lambda name, payload: events.append((name, payload)),
    )
    agent = _session(context, library)
    agent.ask("run the demo")
    loaded = [payload for name, payload in events if name == "skill.loaded"]
    assert loaded == [{"skill": "demo-skill", "trigger": "auto"}]


def test_reset_forgets_the_loaded_skills(context, library):
    agent = _session(context, library, script=["one", "two"])
    agent.ask("run the demo")
    agent.reset()
    agent.ask("hello")
    assert agent.active_skills == []


# ── the skill tools ───────────────────────────────────────────────────


def test_load_skill_tool_returns_the_instructions(context, library):
    from chisurf.core.agent.tools import skills as skill_tools

    agent = _session(context, library)
    result = skill_tools.load_skill(agent.context, name="other-skill")
    assert "Do the other thing." in result["instructions"]
    assert agent.active_skills == ["other-skill"]


def test_load_skill_tool_reports_an_unknown_name(context, library):
    from chisurf.core.agent import ToolError
    from chisurf.core.agent.tools import skills as skill_tools

    agent = _session(context, library)
    with pytest.raises(ToolError, match="Available"):
        skill_tools.load_skill(agent.context, name="no-such-skill")


def test_list_skills_tool_shows_what_is_loaded(context, library):
    from chisurf.core.agent.tools import skills as skill_tools

    agent = _session(context, library)
    agent.ask("run the demo")
    listing = skill_tools.list_skills(agent.context)
    assert listing["loaded"] == ["demo-skill"]
    assert {entry["name"] for entry in listing["available"]} == {
        "demo-skill",
        "other-skill",
    }


# ── session experiment detection ──────────────────────────────────────


def test_session_experiments_reports_distinct_names():
    class Experiment:
        def __init__(self, name):
            self.name = name

    class Dataset:
        def __init__(self, name):
            self.experiment = Experiment(name)

    assert session_experiments([Dataset("TCSPC"), Dataset("TCSPC"), Dataset("FCS")]) == [
        "TCSPC",
        "FCS",
    ]
