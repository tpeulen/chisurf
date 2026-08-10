"""Walking the overworld, headlessly."""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import tiles  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (  # noqa: E402
    OverworldGame,
)


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    """A miniature documentation tree, so tests never build the real corpus.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Temporary directory.

    Returns
    -------
    pathlib.Path
        The docs root.
    """
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    # Real prose, not stubs: a page too thin to question leaves the challenge
    # and flagging paths skipped, which is how they went untested before.
    body = (
        "The fundamental anisotropy of a fluorophore describes how much "
        "polarisation memory survives the excited-state lifetime, and it is "
        "bounded above by two fifths for a single absorbing dipole.\n\n"
        "Rotational correlation time governs how quickly that memory is lost, "
        "so a larger molecule tumbling slowly retains polarisation for longer "
        "than a small one in the same solvent.\n"
    )
    names = [f"p{index}" for index in range(8)]
    for name in names:
        (section / f"{name}.md").write_text(
            f"# {name.upper()}\n\n{body}", encoding="utf-8"
        )
    listing = "\n".join(names)
    (section / "index.md").write_text(
        f"# Guides\n\n```{{toctree}}\n:maxdepth: 1\n\n{listing}\n```\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def game(qapp, tmp_path):
    """An overworld on a tiny world, wired to a headless host.

    Returns
    -------
    OverworldGame
        Ready to step.
    """
    try:
        context = chigame.create_offscreen(size=(240, 180))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    docs = _docs(tmp_path)
    instance = OverworldGame(world=build_world(docs), save_path=tmp_path / "run.json",
                             docs_root=docs)
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    # The loader is staged so a player sees progress; a test wants the world on
    # the next line.
    instance.finish_loading()
    return instance


def test_iris_walks(game):
    """The pad moves Iris and the camera follows."""
    start = list(game.iris)
    game.host.keys.press(Action.DOWN)
    for _ in range(20):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] > start[1]
    assert game.host.camera.center[1] > start[1]


def test_iris_cannot_walk_through_a_wall(game):
    """The world has bounds, and they are the tiles themselves."""
    village = game.world.villages[0]
    col, row, width, height = village.rect
    # Stand just below the south wall, off to one side of the gate.
    game.iris = [(col + 1.5) * tiles.TILE, (row + height + 0.5) * tiles.TILE]
    before = list(game.iris)

    game.host.keys.press(Action.UP)
    for _ in range(120):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] >= before[1] - tiles.TILE, "she walked through the compound wall"


def test_iris_cannot_leave_the_world(game):
    """Walking hard at the edge must not put her outside the grid.

    She starts where the game starts her -- a land is ringed by water, so
    teleporting her into the moat first would only prove she cannot swim.
    """
    game.host.keys.press(Action.LEFT)
    game.host.keys.press(Action.UP)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert 0.0 <= game.iris[0] <= game.world.width * tiles.TILE
    assert 0.0 <= game.iris[1] <= game.world.height * tiles.TILE
    assert not game.world.blocked(*game.iris), "she ended up inside something solid"


def test_the_story_advances_from_the_world_not_from_a_button(game):
    """A beat completes because the corpus shows it, not because of input."""
    from chisurf.plugins.misc.games.lumis_quest.api.story import ACT_ONE

    assert game.story.current is not None
    game.update(1 / 60, game.host.keys)
    assert game.story.current.key != ACT_ONE[0].key, "arrival completes on arriving"

    game.story.choose("clarity")
    assert game.story.order["name"] == "The Order of Clarity"
    with pytest.raises(KeyError):
        game.story.choose("nonsense")


def test_diagonal_movement_is_not_faster(game):
    """Normalising the axis stops diagonals being a speed exploit."""
    game.iris = [0.0, 0.0]
    game.host.keys.press(Action.RIGHT)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    straight = abs(game.iris[0])

    game.host.keys.release(Action.RIGHT)
    game.host.keys.end_frame()
    game.iris = [0.0, 0.0]
    game.host.keys.press(Action.RIGHT)
    game.host.keys.press(Action.DOWN)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    diagonal = (game.iris[0] ** 2 + game.iris[1] ** 2) ** 0.5
    assert diagonal == pytest.approx(straight, rel=0.02)


def test_lumi_follows_without_overlapping(game):
    """The companion trails rather than sticking to Iris."""
    game.host.keys.press(Action.RIGHT)
    for _ in range(90):
        game.update(1 / 60, game.host.keys)
    gap = ((game.iris[0] - game.lumi[0]) ** 2 + (game.iris[1] - game.lumi[1]) ** 2) ** 0.5
    assert 5.0 < gap < 60.0, gap


def test_the_nearest_room_is_reported(game):
    """The HUD names where you are standing."""
    first = game.world.rooms[0]
    game.iris = list(first.position)
    assert game.here is first

    last = game.world.rooms[-1]
    game.iris = list(last.position)
    assert game.here is last


def test_the_land_is_named_where_she_stands(game):
    """Standing on a land reports its fantasy name, not the directory."""
    game.iris = list(game.world.rooms[0].position)
    assert game.land is not None
    assert game.land.title.startswith("The ")


def test_menu_toggles_a_map_that_fits_the_world(game):
    """The map view frames everything rather than guessing a height."""
    # The map lives behind the pause menu now: Menu opens it, the MAP tab is
    # first, and Confirm toggles the map and closes the menu.
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_open

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.show_map is True and not game.menu_open

    # `update` is driven directly here, so this test owns the frame boundary
    # that GameHost.frame() would otherwise call. Without it `just_pressed`
    # stays latched and a toggle fires on every iteration.
    for step in range(120):
        game.update(1 / 30, game.host.keys)
        game.host.keys.end_frame()
        assert game.show_map is True, f"toggled off again at step {step}"
    assert game.show_map is True

    min_x, min_y, max_x, max_y = game.world.bounds()
    width, height = game.host.ctx.size
    aspect = width / height
    assert game.host.camera.height >= (max_y - min_y)
    assert game.host.camera.height * aspect >= (max_x - min_x)


def test_the_shoulders_zoom_within_bounds(game):
    """Zoom is clamped, so the view cannot be lost."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import VIEW_MAX, VIEW_MIN

    game.host.keys.press(Action.SHOULDER_L)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.view_height <= VIEW_MAX

    game.host.keys.release(Action.SHOULDER_L)
    game.host.keys.press(Action.SHOULDER_R)
    for _ in range(600):
        game.update(1 / 60, game.host.keys)
    assert game.view_height >= VIEW_MIN


def test_it_renders(qapp, tmp_path):
    """A frame comes out with the world drawn on it."""
    try:
        frame = chigame.capture(
            OverworldGame(world=build_world(_docs(tmp_path)),
                          save_path=tmp_path / "run.json"),
            size=(320, 240), frames=3, with_audio=False
        )
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    assert frame.shape == (240, 320, 4)


@pytest.fixture
def wild_room(game):
    """A room forced into the wild state.

    The temporary corpus lies outside the tracked directories, so its pages do
    not come back wild on their own -- and skipping on that left the whole
    encounter path untested. The state is what these tests are about, so they
    set it.
    """
    if not game.pool:
        pytest.skip("spectra.db is not present in this install")
    room = game.world.rooms[0]
    room.state = "wild"
    return room


def test_only_a_wild_building_holds_a_guardian(game, wild_room):
    """A page somebody has read is a village you walk through, not a fight."""
    wild = wild_room

    # Standing far away starts nothing, even at a wild room.
    game.iris = [wild.position[0] + 400.0, wild.position[1]]
    game._try_encounter()
    assert game.battle is None

    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is not None
    assert game.encounter_room is wild


def test_the_same_page_always_holds_the_same_guardian(game, wild_room):
    """A wild encounter that reshuffles every visit is a slot machine."""
    wild = wild_room

    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    first = game.battle.opponent.creature.name
    game.battle = None
    game._try_encounter()
    assert game.battle.opponent.creature.name == first


def test_the_battle_menu_is_driven_by_the_pad(game, wild_room):
    """Every choice is reachable from the nine actions, with no text entry."""
    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()

    labels = [label for label, _ in game._battle_options()]
    assert labels[0] == "Emit" and labels[-1] == "Withdraw"

    game.host.keys.tap(Action.DOWN)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_index == 1

    # Cancel withdraws, and the encounter then dismisses on Confirm.
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.battle.finished and game.battle.fled

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.battle is None


def test_walking_is_suspended_during_an_encounter(game, wild_room):
    """The pad drives the menu, not Iris."""
    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()

    before = list(game.iris)
    game.host.keys.press(Action.DOWN)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    assert game.iris == before


def test_a_spent_team_cannot_start_a_fight(game, wild_room):
    """Attrition is the danger, so a bleached team has to stop."""
    wild = wild_room
    for fighter in game.team:
        fighter.hp = 0
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is None


def test_a_cleared_room_yields_gear_once(game, wild_room):
    """Loot is seeded by the page, and a room cannot be farmed."""
    if not game.gear_pool:
        pytest.skip("spectra.db is not present in this install")
    game._award_loot(wild_room)
    assert len(game.inventory) == 1
    first = game.inventory[0].name

    game._award_loot(wild_room)
    assert len(game.inventory) == 1, "the same room paid out twice"
    assert game.inventory[0].name == first


def test_fitting_a_filter_changes_what_is_visible(game):
    """The loot loop: different optics, different world."""
    if not game.gear_pool:
        pytest.skip("spectra.db is not present in this install")
    narrow = min(
        (p for p in game.gear_pool if p.slot == "emission" and p.bandwidth_nm > 5),
        key=lambda p: p.bandwidth_nm,
    )
    game.equip(narrow)
    assert game.loadout.emission is narrow
    assert game.loadout.sees(narrow.center_nm)
    assert not game.loadout.sees(narrow.center_nm + 120.0)


def test_standing_on_a_clinic_recovers_the_team(game):
    """Photon budgets persist between fights, so recovery is a place you go."""
    village = game.world.villages[0]
    col, row = village.clinic
    assert game.world.tile_at(col, row) == tiles.CLINIC

    for fighter in game.team:
        fighter.hp = 1
    game.iris = [(col + 0.5) * tiles.TILE, (row + 0.5) * tiles.TILE]
    for _ in range(120):
        game.update(1 / 60, game.host.keys)
    assert game.resting
    assert all(f.hp > 1 for f in game.team)


def test_recovery_only_happens_at_the_clinic(game):
    """Otherwise attrition is not a constraint at all."""
    for fighter in game.team:
        fighter.hp = 5
    room = game.world.rooms[0]
    game.iris = [room.position[0], room.position[1] + tiles.TILE * 3]
    for _ in range(60):
        game.update(1 / 60, game.host.keys)
    if game.resting:
        pytest.skip("that spot happens to be a clinic")
    assert all(f.hp == 5 for f in game.team)


def test_the_menu_has_tabs_and_closes(game):
    """Nine actions is the whole controller, so every screen lives behind Menu."""
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_open and game.TABS[game.menu_tab] == "MAP"

    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.TABS[game.menu_tab] == "RIG"

    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert not game.menu_open


def test_walking_is_suspended_while_the_menu_is_open(game):
    """The pad drives the menu, not Iris."""
    game.menu_open = True
    before = list(game.iris)
    game.host.keys.press(Action.DOWN)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    assert game.iris == before


def test_the_mode_tab_switches_between_training_and_expert(game):
    """The one switch that decides whether anything is signed off."""
    from chisurf.plugins.misc.games.lumis_quest.api import review_bridge

    game.menu_open = True
    game.menu_tab = game.TABS.index("MODE")
    game.menu_row = 1
    game._menu_confirm()
    assert game.mode == review_bridge.EXPERT

    game.menu_row = 0
    game._menu_confirm()
    assert game.mode == review_bridge.TRAINING


def test_the_rig_tab_fits_a_found_part(game):
    """Crafting is assembling a path from what you have found."""
    if not game.gear_pool:
        pytest.skip("spectra.db is not present in this install")
    part = next(p for p in game.gear_pool if p.slot == "emission")
    game.inventory.append(part)

    game.menu_open = True
    game.menu_tab = game.TABS.index("RIG")
    game.menu_row = 0
    game._menu_confirm()

    assert game.rig.emission is part, "the part must land in its own slot"
    assert game.loadout.emission is part, "and fit as the single filter too"


def test_the_party_tab_swaps_a_collected_creature_in(game):
    """A collection you cannot field is a list."""
    if not game.pool:
        pytest.skip("spectra.db is not present in this install")
    spare = next(c for c in game.pool if c not in [f.creature for f in game.team])
    game.collection.append(spare)
    game.team[0].hp = 1  # the most spent slot is the one replaced

    game.menu_open = True
    game.menu_tab = game.TABS.index("PARTY")
    game.menu_row = len(game.team)  # first collected creature
    game._menu_confirm()

    assert spare in [f.creature for f in game.team]
    assert len(game.team) == 3, "the party size is fixed; a swap is a swap"


def test_the_model_is_off_by_default(game):
    """A configured provider must not silently add a network call to play.

    The first visit to every page would otherwise stall mid-encounter on a
    machine that happens to have an AI provider set up.
    """
    from chisurf.plugins.misc.games.lumis_quest.api import providers

    assert game.use_model is False
    assert isinstance(
        providers.best_available(prefer_model=game.use_model),
        providers.DeterministicProvider,
    )


def test_the_mode_tab_can_opt_into_the_model(game):
    """Opting in is a deliberate act, on the same screen as the mode switch."""
    game.menu_open = True
    game.menu_tab = game.TABS.index("MODE")
    game.menu_row = 2
    game._menu_confirm()
    assert game.use_model is True
    game._menu_confirm()
    assert game.use_model is False


def test_flagging_records_a_span_and_a_category(game, wild_room, tmp_path):
    """Expert mode's other half: saying what is *not* fine."""
    from chisurf.plugins.misc.games.lumis_quest.api import findings, review_bridge

    game.findings_path = tmp_path / "findings.json"
    game.mode = review_bridge.EXPERT
    game.encounter_room = wild_room
    questions, content_hash = review_bridge.challenge_for(
        wild_room.path, cache_dir=tmp_path / "cache"
    )
    if not questions:
        pytest.skip("this fixture page is too thin to question")
    game.challenge, game.challenge_hash = questions[0], content_hash

    game._begin_flag()
    if not game.flagging:
        pytest.skip("this fixture page has nothing specific enough to flag")
    assert game.flag_stage == "span"

    game.host.keys.tap(Action.CONFIRM)
    game._flag_input(game.host.keys)
    game.host.keys.end_frame()
    assert game.flag_stage == "category"

    game.host.keys.tap(Action.CONFIRM)
    game._flag_input(game.host.keys)
    assert not game.flagging

    pool = findings.load(game.findings_path)
    assert len(pool) == 1
    assert pool[0].address == wild_room.address
    assert pool[0].category in dict(findings.CATEGORIES)
    assert pool[0].span, "a finding points at an exact sentence"


def test_flagging_is_expert_only(game, wild_room, tmp_path):
    """Training teaches; it does not file defects."""
    from chisurf.plugins.misc.games.lumis_quest.api import review_bridge

    game.findings_path = tmp_path / "findings.json"
    game.mode = review_bridge.TRAINING
    game.encounter_room = wild_room
    questions, content_hash = review_bridge.challenge_for(
        wild_room.path, cache_dir=tmp_path / "cache"
    )
    if not questions:
        pytest.skip("this fixture page is too thin to question")
    game.challenge, game.challenge_hash = questions[0], content_hash

    game.host.keys.tap(Action.SHOULDER_L)
    game._challenge_input(game.host.keys)
    assert not game.flagging, "the flag interface is expert-only"


def test_loading_is_staged_so_the_screen_appears_before_the_work(qapp, tmp_path):
    """Building the world takes over a second.

    Doing it inside setup means the window appears already frozen with nothing
    on it, so the stages run one per frame -- and the first stage is deliberately
    empty, or the heaviest one still runs before anything is drawn.
    """
    from chisurf.gui import chigame
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")

    game = OverworldGame(world=build_world(_docs(tmp_path)),
                         save_path=tmp_path / "run.json")
    host = chigame.GameHost(game, context, with_text=False, with_audio=False)
    assert game.phase == "loading" and game.load_step == 0

    host.frame(1 / 60)
    assert game.load_step == 1, "the first stage must do no work"

    for _ in range(10):
        if game.phase != "loading":
            break
        host.frame(1 / 60)
    assert game.phase == "title", "loading ends at the front door"
    assert game.world.rooms and game.people is not None


def test_the_title_screen_offers_a_new_journey_and_then_a_continue(qapp, tmp_path):
    """The game has a front door: the title menu.

    A fresh install offers New Journey (which opens on the story); a machine
    with a saved run puts Continue first, and continuing skips the opening
    entirely — a run already played does not need telling what the Fading is.
    """
    from chisurf.gui import chigame
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")

    docs = _docs(tmp_path)
    run = tmp_path / "run.json"
    fresh = OverworldGame(world=build_world(docs), save_path=run, docs_root=docs)
    chigame.GameHost(fresh, context, with_text=False, with_audio=False)
    fresh.finish_loading(skip_prologue=False)
    assert fresh.phase == "title"
    assert fresh._title_rows()[0] == "New Journey", "no save, nothing to continue"

    if not fresh.pool:
        pytest.skip("spectra.db is not present in this install")

    # New Journey opens on the prologue, and the run begins without Lumi.
    fresh.host.keys.tap(Action.CONFIRM)
    fresh.update(1 / 60, fresh.host.keys)
    fresh.host.keys.end_frame()
    assert fresh.phase == "prologue"
    assert not fresh.story.has_lumi, "the hound is found, not issued"

    fresh.iris = [123.0, 456.0]
    fresh.save_run()
    assert save_api.RunState.load(run).position == (123.0, 456.0)

    resumed = OverworldGame(world=build_world(docs), save_path=run, docs_root=docs)
    chigame.GameHost(resumed, context, with_text=False, with_audio=False)
    resumed.finish_loading(skip_prologue=False)
    assert resumed.phase == "title"
    assert resumed._title_rows()[0] == "Continue"

    resumed.host.keys.tap(Action.CONFIRM)
    resumed.update(1 / 60, resumed.host.keys)
    resumed.host.keys.end_frame()
    assert resumed.phase == "play", "continuing skips the opening"


def test_new_journey_over_a_saved_run_asks_before_erasing(qapp, tmp_path):
    """Starting over is destructive, so it takes a second press to mean it."""
    from chisurf.gui import chigame
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")

    docs = _docs(tmp_path)
    run = tmp_path / "run.json"
    played = OverworldGame(world=build_world(docs), save_path=run, docs_root=docs)
    chigame.GameHost(played, context, with_text=False, with_audio=False)
    played.finish_loading()
    if not played.pool:
        pytest.skip("spectra.db is not present in this install")
    played.save_run()

    game = OverworldGame(world=build_world(docs), save_path=run, docs_root=docs)
    chigame.GameHost(game, context, with_text=False, with_audio=False)
    game.finish_loading(skip_prologue=False)
    assert game.phase == "title"

    # Move to New Journey and confirm once: the row becomes a question.
    game.host.keys.tap(Action.DOWN)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.phase == "title", "one press must not erase a run"
    assert "erase" in game._title_rows()[1]

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.phase == "prologue", "the second press means it"


def test_the_awakening_scene_is_staged_and_the_hound_joins(qapp, tmp_path):
    """Wake with the keeper speaking; find the dim hound; it joins.

    The Act Zero contract: Lumi is not at heel from frame one, the elder's
    words witness the waking beat, and befriending the hound completes its
    beat and starts the trail.
    """
    from chisurf.gui import chigame
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import OverworldGame

    try:
        context = chigame.create_offscreen(size=(160, 120))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")

    docs = _docs(tmp_path)
    game = OverworldGame(world=build_world(docs), save_path=tmp_path / "run.json",
                         docs_root=docs)
    chigame.GameHost(game, context, with_text=False, with_audio=False)
    game.finish_loading(skip_prologue=False)
    if not game.pool:
        pytest.skip("spectra.db is not present in this install")

    game._begin_journey()
    assert game.phase == "prologue"

    # Skip the cards: the keeper should already be speaking over Iris.
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.phase == "play"
    assert game.speaking is not None and game.speaking.role == "elder"
    assert game.story.current.key == "wake"

    # Hear him out: the waking is witnessed when he has said his piece.
    for _ in range(len(game.speaking.dialogue)):
        game.host.keys.tap(Action.CONFIRM)
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game.speaking is None
    assert "wake" in game.story.seen
    assert game.story.current.key == "the-hound"

    # Find the dim hound and speak to it: it joins, and the beat completes.
    hound = next(npc for npc in game.people if npc.role == "lumi")
    game.iris = [hound.x, hound.y + 10.0]
    game.host.keys.tap(Action.SHOULDER_L)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.speaking is hound
    for _ in range(len(hound.dialogue)):
        game.host.keys.tap(Action.CONFIRM)
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game.story.has_lumi, "the hound joins when its scene is played out"
    assert all(npc.role != "lumi" for npc in game.people)
    current = game.story.current
    assert current is None or current.key not in ("wake", "the-hound"), \
        "Act Zero is over once the hound is at heel"


def test_an_order_is_chosen_by_talking_to_an_emissary(game):
    """A doctrine you serve is a person you met, not a menu row.

    The full flow: stand beside an emissary, talk through their case, be asked,
    pledge. ``story.choose`` fires only at the end, and walking away leaves the
    choice unmade.
    """
    emissary = next(n for n in game.people if n.kind == "emissary")
    game.iris = [emissary.x, emissary.y + 10.0]
    assert game.story.chosen_order is None

    game.host.keys.tap(Action.SHOULDER_L)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.speaking is emissary

    # Confirm through every screen of their dialogue.
    for _ in range(len(emissary.dialogue)):
        assert game.story.chosen_order is None, "no pledge before the question"
        game.host.keys.tap(Action.CONFIRM)
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game.pledging, "the dialogue must end in the question"

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    order = emissary.role.split(":", 1)[1]
    assert game.story.chosen_order == order
    assert game.pledge_ack, "the pledge is acknowledged in their voice"

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.speaking is None


def test_walking_away_from_an_emissary_leaves_the_choice_open(game):
    """Cancel is walking away, and the order can still be chosen later."""
    emissary = next(n for n in game.people if n.kind == "emissary")
    game.iris = [emissary.x, emissary.y + 10.0]
    game.host.keys.tap(Action.SHOULDER_L)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.speaking is emissary

    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.speaking is None
    assert game.story.chosen_order is None


def test_the_tutorial_teaches_walking_first_and_advances_on_real_state(game):
    """The banner points at the next real thing and waits for the real press."""
    assert game.tutorial.current.key == "walk"

    game.host.keys.press(Action.DOWN)
    for _ in range(60):
        game.update(1 / 60, game.host.keys)
    game.host.keys.release(Action.DOWN)
    game.host.keys.end_frame()
    assert "walk" in game.tutorial.done
    assert game.tutorial.current.key == "speak"

    # Speaking to anyone -- the healer inside the gate will do -- retires it.
    someone = next(n for n in game.people if n.kind != "beast")
    game.iris = [someone.x, someone.y + 10.0]
    game.host.keys.tap(Action.SHOULDER_L)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    # The tutorial watches at the top of the frame, so the press it waits for
    # is witnessed on the frame after it lands.
    game.update(1 / 60, game.host.keys)
    assert "speak" in game.tutorial.done


def test_the_tutorial_persists_with_the_run(game, tmp_path):
    """Teaching happens once per player, not once per session."""
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    game.tutorial.done = {"walk", "speak"}
    game.save_run()
    state = save_api.RunState.load(game._save_path)
    assert state.tutorial == ["speak", "walk"]


def test_a_pre_tutorial_save_with_progress_skips_the_teaching(game):
    """A run that has cleared rooms does not need telling how to walk."""
    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    if not game.pool:
        pytest.skip("spectra.db is not present in this install")
    save_api.RunState(
        position=(100.0, 100.0),
        team=[(f.creature.probe_id, f.hp) for f in game.team],
        cleared=["docs/guides/p0.md"],
    ).save(game._save_path)
    game._restore()
    assert game.tutorial.complete


def test_the_tutorial_banner_names_the_active_keys(game):
    """A banner that says the wrong key is worse than no banner."""
    labels = game._key_labels()
    assert labels["talk"] == "Q"
    step = game.tutorial.current
    assert step is not None
    step.teach.format(**labels)  # must not raise mid-frame


def test_the_options_tab_changes_the_controls_and_the_speed(game):
    """Adjustable, and every scheme covers every action."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import SCHEMES

    for keys in SCHEMES.values():
        assert set(keys.values()) == set(Action), "a scheme must reach every action"

    game.menu_open = True
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 0
    before = game.scheme
    game._menu_confirm()
    assert game.scheme != before
    assert game.host.keys.bindings == SCHEMES[game.scheme]

    game.menu_row = 1
    speed = game.walk_speed
    game._menu_confirm()
    assert game.walk_speed != speed


def test_regenerating_redraws_the_wilderness_but_not_the_world(game):
    """A player who has learned where a page lives must not lose that."""
    rooms = {room.address: room.tile for room in game.world.rooms}
    lands = [region.title for region in game.world.regions]

    game.menu_open = True
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 3
    game._menu_confirm()
    assert game.phase == "loading" and not game.menu_open

    game._pending = None
    game.finish_loading()
    assert [r.title for r in game.world.regions] == lands
    assert {room.address: room.tile for room in game.world.rooms} == rooms
