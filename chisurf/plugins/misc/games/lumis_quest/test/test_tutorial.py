"""The teaching sequence completes on game state, never on its own.

The tutorial's whole contract is the story's: a step retires because the world
shows it happened. These tests drive a stub game through the sequence and
assert each step waits for its own evidence and latches once it has it.
"""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import tutorial
from chisurf.plugins.misc.games.lumis_quest.api.save import RunState
from chisurf.plugins.misc.games.lumis_quest.api.tiles import FLOOR, GRASS, TILE


class _World:
    """A world of grass with one floor tile."""

    def tile_at(self, col: int, row: int) -> int:
        return FLOOR if (col, row) == (5, 5) else GRASS


class _Battle:
    """A fight with a log."""

    def __init__(self) -> None:
        self.log: list[str] = []


class _Game:
    """The state surface the tutorial reads."""

    def __init__(self) -> None:
        self.world = _World()
        self.player_pos = [0.0, 0.0]
        self.speaking = None
        self.resting = False
        self.menu_open = False
        self.battle = None
        self.verdict = None


def test_the_steps_come_in_first_run_order():
    """Walk, meet someone, get inside, recover, the pack, fight, act, answer."""
    keys = [step.key for step in tutorial.STEPS]
    assert keys == ["walk", "speak", "enter", "rest", "menu", "fight", "turn", "answer"]


def test_walking_is_the_first_lesson_and_takes_real_distance():
    """Standing still teaches nothing; a nudge is not a walk."""
    guide = tutorial.Tutorial()
    game = _Game()
    guide.observe(game)
    assert guide.current.key == "walk"

    game.player_pos[0] += TILE  # one tile is a nudge
    guide.observe(game)
    assert guide.current.key == "walk"

    for _ in range(6):
        game.player_pos[0] += TILE
        guide.observe(game)
    assert guide.current.key == "speak"


def _advance_to(guide: tutorial.Tutorial, game: _Game, key: str) -> None:
    """Complete every step before ``key`` by feeding the state it asks for."""
    while guide.current is not None and guide.current.key != key:
        step = guide.current.key
        if step == "walk":
            for _ in range(8):
                game.player_pos[0] += TILE
                guide.observe(game)
            continue
        if step == "speak":
            game.speaking = object()
        elif step == "enter":
            game.player_pos = [5.5 * TILE, 5.5 * TILE]
        elif step == "rest":
            game.resting = True
        elif step == "menu":
            game.menu_open = True
        elif step == "fight":
            game.battle = _Battle()
        elif step == "turn":
            game.battle = game.battle or _Battle()
            game.battle.log.append("emitted")
        elif step == "answer":
            game.verdict = object()
        guide.observe(game)


def test_each_step_waits_for_its_own_evidence():
    """A battle does not complete the resting step, and vice versa."""
    guide = tutorial.Tutorial()
    game = _Game()
    _advance_to(guide, game, "rest")
    assert guide.current.key == "rest"

    # A fight is not a rest: the step must not advance on the wrong state.
    game.battle = _Battle()
    guide.observe(game)
    assert guide.current.key == "rest"

    game.resting = True
    guide.observe(game)
    assert guide.current.key == "menu"

    game.menu_open = True
    guide.observe(game)
    assert guide.current.key == "fight"


def test_a_completed_step_stays_completed():
    """A battle that ended is still a battle the player has seen."""
    guide = tutorial.Tutorial()
    game = _Game()
    _advance_to(guide, game, "turn")
    game.battle = None  # the fight is over
    guide.observe(game)
    assert "fight" in guide.done, "the fight step must latch"


def test_the_whole_sequence_finishes_and_stays_finished():
    """Once taught, no banner ever again."""
    guide = tutorial.Tutorial()
    game = _Game()
    _advance_to(guide, game, "answer")
    game.verdict = object()
    guide.observe(game)
    assert guide.complete
    guide.observe(game)
    assert guide.current is None


def test_finish_retires_everything_at_once():
    """A run that has cleared rooms does not need teaching."""
    guide = tutorial.Tutorial()
    guide.finish()
    assert guide.complete


def test_progress_survives_the_save_file(tmp_path):
    """The teaching happens once per player, not once per session."""
    state = RunState(tutorial=["walk", "speak"])
    path = state.save(tmp_path / "run.json")
    loaded = RunState.load(path)
    assert loaded.tutorial == ["walk", "speak"]

    guide = tutorial.Tutorial(set(loaded.tutorial))
    assert guide.current.key == "enter"


def test_the_banners_name_controls_through_placeholders():
    """The text must survive a rebinding, so keys appear as placeholders."""
    for step in tutorial.STEPS:
        # Any brace in a banner must be a known placeholder, or format() at
        # draw time raises in the middle of a frame.
        step.teach.format(talk="Q", confirm="Shift", cancel="Backspace", menu="Tab")
