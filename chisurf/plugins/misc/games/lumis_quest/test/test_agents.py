"""The town has a day of its own, and the player can walk into the middle of it."""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import agents, npcs
from chisurf.plugins.misc.games.lumis_quest.api import story as story_api
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature corpus, so a test never builds the real one."""
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    names = [f"p{index}" for index in range(12)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name}\n\nProse.\n", encoding="utf-8")
    (section / "index.md").write_text(
        "# Guides\n\n```{toctree}\n\n" + "\n".join(names) + "\n```\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def town(tmp_path):
    """A world, its people, and their inner lives."""
    world = build_world(_docs(tmp_path))
    people = npcs.populate(world)
    return world, people, agents.Society(world, people, seed=7)


def test_only_the_people_who_can_wander_get_an_inner_life(town):
    """A Warden holding a hall is somewhere to walk to, not somebody who leaves."""
    _, people, society = town
    assert society.minds, "a town with nobody in it is not a town"
    assert {mind.npc.kind for mind in society.minds} == {"townsfolk"}
    kinds = {npc.kind for npc in people}
    assert "warden" not in {mind.npc.kind for mind in society.minds}
    assert "keeper" in kinds or "healer" in kinds


def test_needs_rise_and_send_somebody_somewhere_real(town):
    """A goal is a place in this settlement, not a jitter around a home point."""
    world, _, society = town
    mind = society.minds[0]
    mind.drives = {name: 0.0 for name in mind.drives}
    mind.drives["rest"] = 0.95

    where = [mind.npc.x, mind.npc.y]
    for _ in range(400):
        society.step(1 / 30.0)
        if mind.goal:
            break
    assert mind.goal == "rest"
    assert mind.target is not None
    village = world.village_at(*mind.target)
    assert village is not None and "tavern" in village.premises

    for _ in range(3000):
        society.step(1 / 30.0)
        if mind.memory:
            break
    assert mind.memory, "arriving has to mean something happened"
    assert abs(mind.npc.x - where[0]) + abs(mind.npc.y - where[1]) > 4.0


def test_two_people_who_meet_talk_and_then_leave_each_other_alone(town):
    """A conversation is a real event with a beginning and an end."""
    _, _, society = town
    one, two = society.minds[0], society.minds[1]
    two.npc.x, two.npc.y = one.npc.x + 8.0, one.npc.y

    topic = society.begin(one, two)
    assert topic
    assert one.talking and two.talking
    assert one.exchange == two.exchange, "they are in the same conversation"
    assert len(one.exchange) >= 3
    assert {who for who, _ in one.exchange} == {one.npc.name, two.npc.name}

    for _ in range(int(agents.LINE_SECONDS * len(one.exchange) * 30) + 30):
        society.step(1 / 30.0)
        if not one.talking:
            break
    assert not one.talking and not two.talking
    assert one.cooldown > 0.0, "they do not immediately start again"
    assert any("talked about" in line for line in one.memory)


def test_what_the_town_gossips_about_is_read_off_the_run(town):
    """Nobody discusses the probe who takes labels off before there is one."""
    world, _, society = town
    story = story_api.Story(world)
    quiet = agents.mood_from(story, unbound=0)
    assert quiet["probe"] < 1.0 and quiet["marking"] < 1.0

    story.witness("the-marked")
    story.seal("ember")
    loud = agents.mood_from(story, unbound=3)
    assert loud["probe"] > quiet["probe"]
    assert loud["marking"] > quiet["marking"]
    assert loud["wardens"] > quiet["wardens"]

    society.mood = {"marking": 500.0}
    assert society.pick_topic() == "marking"


def test_the_player_can_walk_in_on_a_conversation_and_end_it(town):
    """Overhearing is a real thing you do with the talk button."""
    _, _, society = town
    one, two = society.minds[0], society.minds[1]
    two.npc.x, two.npc.y = one.npc.x + 8.0, one.npc.y
    society.begin(one, two, topic="marking")
    society.step(1 / 30.0)

    heard = society.conversation_near(one.npc.x + 6.0, one.npc.y + 6.0)
    assert heard is not None
    assert society.conversation_near(one.npc.x + 4000.0, one.npc.y) is None
    assert len(society.transcript(heard)) == len(one.exchange)

    society.interrupt(heard)
    assert not one.talking and not two.talking
    assert any("interrupted" in line for line in one.memory)


def test_a_model_that_writes_the_words_never_changes_the_loop(town):
    """The words are the only part a provider touches."""
    _, _, society = town
    society.voice = lambda one, other, topic: [("A", "written"), ("B", "back")]
    one, two = society.minds[0], society.minds[1]
    society.begin(one, two, topic="fading")
    assert one.exchange == [("A", "written"), ("B", "back")]

    # And a voice that raises is a voice that is simply not used.
    def broken(one_, other_, topic_):
        raise RuntimeError("provider is down")

    society.voice = broken
    three, four = society.minds[2], society.minds[3]
    society.begin(three, four, topic="fading")
    assert len(three.exchange) >= 3, "the authored exchange stands"


def test_nobody_walks_through_a_wall_on_their_errands(town):
    """A day simulated inside the geometry, not over it."""
    world, _, society = town
    for _ in range(1500):
        society.step(1 / 30.0)
    for mind in society.minds:
        assert not npcs._blocked(world, mind.npc.x, mind.npc.y), mind.npc.name
