"""Dialogue, conditions and effects are data, and the data is run by code."""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import actions, engine
from chisurf.plugins.misc.games.lumis_quest.api import context as context_api
from chisurf.plugins.misc.games.lumis_quest.api import story as story_api
from chisurf.plugins.misc.games.lumis_quest.api import tiers
from chisurf.plugins.misc.games.lumis_quest.api.world import World


@pytest.fixture
def ctx():
    """A run with nothing in it, which every script has to cope with."""
    world = World()
    return context_api.GameContext(world=world, story=story_api.Story(world))


def _play(runner, choices=()):
    """Walk a scene to its end, taking the given choices in order."""
    picks = list(choices)
    seen = []
    screen = runner.screen
    guard = 0
    while screen is not None and guard < 40:
        guard += 1
        seen.append(screen)
        if screen.choices:
            screen = runner.choose(picks.pop(0) if picks else 0)
        else:
            screen = runner.advance()
    return seen


def test_a_scene_is_a_list_of_steps_and_the_runner_never_blocks(ctx):
    """One screen at a time, pumped by the host."""
    runner = engine.Runner({"s": [{"say": "one"}, {"say": "two"}]}, ctx)
    first = runner.start("s", who="Bram")
    assert first.text == "one" and first.who == "Bram"
    assert runner.advance().text == "two"
    assert runner.advance() is None and runner.finished


def test_authored_lines_are_handed_in_rather_than_written_into_the_scene(ctx):
    """One warden scene serves all five of them."""
    runner = engine.Runner({"s": [{"say_from": "lines"}, {"say": "end"}]}, ctx)
    runner.start("s", lines={"lines": ("a", "b")})
    assert [screen.text for screen in _play(runner)] == ["a", "b", "end"]


def test_a_choice_branches_and_a_condition_hides_an_option(ctx):
    """An option you cannot take must not be offered."""
    scene = {
        "s": [{"say": "well?", "choice": [
            {"text": "locked", "when": {"seals": 3}, "then": [{"say": "no"}]},
            {"text": "open", "then": [{"say": "yes"}]},
        ]}]
    }
    runner = engine.Runner(scene, ctx)
    screen = runner.start("s")
    assert screen.choices == ("open",)
    assert runner.choose(0).text == "yes"

    for warden in tiers.WARDENS[:3]:
        ctx.story.seal(warden.key)
    screen = runner.start("s")
    assert screen.choices == ("locked", "open")


def test_subject_resolves_so_one_scene_serves_every_warden(ctx):
    """``$subject`` is the only indirection the script language has."""
    scene = {"s": [{"when": {"seal": "$subject"},
                    "then": [{"say": "again"}], "else": [{"say": "first"}]}]}
    runner = engine.Runner(scene, ctx)
    assert runner.start("s", subject="ember").text == "first"
    ctx.story.seal("ember")
    assert runner.start("s", subject="ember").text == "again"
    assert runner.start("s", subject="prism").text == "first"


def test_an_effect_is_a_named_action_and_a_host_job_is_a_request(ctx):
    """The engine never starts a fight; it asks."""
    scene = {"s": [{"do": "seal", "args": {"warden": "ember"}},
                   {"do": "battle", "args": {"warden": "prism"}}]}
    runner = engine.Runner(scene, ctx)
    runner.start("s")
    _play(runner)
    assert "ember" in ctx.seals
    pending = runner.take_requests()
    assert [request.kind for request in pending] == ["battle"]
    assert pending[0].args == {"warden": "prism"}
    assert runner.take_requests() == [], "requests drain when taken"


def test_a_typo_in_a_script_is_loud(ctx):
    """A silently-false condition is a beat that can never complete."""
    with pytest.raises(engine.ScriptError):
        engine.evaluate({"nonsense": 1}, ctx)
    with pytest.raises(engine.ScriptError):
        engine.Runner({"s": [{"do": "nope"}]}, ctx).start("s")
    with pytest.raises(engine.ScriptError):
        engine.Runner({"s": [{"goto": "nowhere"}]}, ctx).start("s")
    with pytest.raises(engine.ScriptError):
        engine.Runner({}, ctx).start("missing")


def test_every_shipped_scene_runs_and_only_names_things_that_exist():
    """The guard that stops a story file rotting quietly."""
    scenes = engine.scenes()
    assert scenes, "the game ships dialogue"
    seen_actions, seen_gotos = set(), set()

    def walk(steps):
        for step in steps:
            if "do" in step:
                seen_actions.add(step["do"])
            if "goto" in step:
                seen_gotos.add(step["goto"])
            if "choice" in step:
                for option in step["choice"]:
                    assert option.get("text")
                    walk(option.get("then", []))
            for branch in ("then", "else"):
                walk(step.get(branch, []))
            if "say" in step:
                assert len(step["say"]) <= 200, step["say"]
                assert "—" not in step["say"], "no em-dash glyph in this font"

    for steps in scenes.values():
        walk(steps)
    assert seen_actions <= set(actions.ACTIONS), seen_actions - set(actions.ACTIONS)
    assert seen_gotos <= set(scenes), seen_gotos - set(scenes)


def test_every_beat_condition_in_the_shipped_arc_evaluates(ctx):
    """A beat whose rule the engine cannot answer never completes."""
    for beat in story_api.BEATS:
        assert isinstance(engine.evaluate(beat.when, ctx), bool), beat.key


def test_the_shipped_data_files_are_json_and_carry_what_they_claim():
    """A stripped install degrades; a corrupt one must not."""
    for name in ("story", "dialogue", "wardens", "agents"):
        loaded = engine.load(name)
        assert isinstance(loaded, dict) and loaded, name
    assert engine.load("does-not-exist") == {}
    assert len(json.dumps(engine.load("story"))) > 1000
