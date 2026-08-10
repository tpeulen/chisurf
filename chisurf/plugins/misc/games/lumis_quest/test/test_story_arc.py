"""The arc runs wake → hound → choice → work → dawn, driven by state."""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import story as story_api
from chisurf.plugins.misc.games.lumis_quest.api.story import (
    BEATS,
    WORK_GOAL,
    Story,
    cleared_in_lands,
)
from chisurf.plugins.misc.games.lumis_quest.api.world import (
    SETTLED,
    WILD,
    build_world,
)


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    names = [f"p{index}" for index in range(4)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name}\n\nProse.\n", encoding="utf-8")
    (section / "index.md").write_text(
        "# Guides\n\n```{toctree}\n\n" + "\n".join(names) + "\n```\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def world(tmp_path):
    built = build_world(_docs(tmp_path))
    for room in built.rooms:
        room.state = WILD
    return built


def test_the_arc_has_a_beginning_a_middle_and_an_end():
    """Acts zero, one and two, in walking order."""
    keys = [beat.key for beat in BEATS]
    assert keys == [
        "wake", "the-hound", "arrival", "first-light", "the-frontier",
        "the-choice", "the-work", "the-dawn",
    ]


def test_a_fresh_run_starts_asleep_and_without_the_hound(world):
    """Act Zero: nothing is given away at the door."""
    story = Story(world)
    assert story.current.key == "wake"
    assert not story.has_lumi

    story.witness("wake")
    assert story.current.key == "the-hound"

    story.has_lumi = True
    assert story.current.key == "arrival"


def test_the_work_counts_only_the_orders_own_lands():
    """A clear in a foreign land is a good deed, not doctrine work."""
    cleared = {
        "docs/guides/a.md", "docs/guides/b.md", "docs/reference/c.md",
    }
    assert cleared_in_lands(cleared, "clarity") == 2
    assert cleared_in_lands(cleared, "rigour") == 1
    assert cleared_in_lands(cleared, None) == 0


def test_the_work_counts_from_the_pledge_not_from_the_start(world):
    """Ground cleared before pledging honours nobody."""
    story = Story(world)
    story.witness("wake")
    story.has_lumi = True
    story.witness("arrival")
    world.rooms[0].state = SETTLED
    story.witness("first-light")
    world.rooms[1].state = story_api.SCOUTED
    story.witness("the-frontier")

    # Pledge with two clears already on the books: they must not count.
    story.choose("clarity", baseline=2)
    story.doctrine_count = 2
    assert story.current.key == "the-work"
    assert story.work_progress == (0, WORK_GOAL)

    story.doctrine_count = 2 + WORK_GOAL
    assert story.work_progress == (WORK_GOAL, WORK_GOAL)
    assert story.current.key == "the-dawn"

    story.witness("dawn")
    assert story.current is None, "the arc ends"


def test_every_order_has_an_epilogue():
    """The dawn speaks in the chosen doctrine's voice."""
    for order in story_api.ORDERS:
        cards = story_api.EPILOGUES[order]
        assert len(cards) >= 2
        for title, body in cards:
            assert title and body
