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
    """The pad moves Iris, and the camera holds the screen she is on.

    It does not follow her *within* a screen -- that is the whole point of a
    screen-based camera, and a composed view is what it buys.
    """
    from chisurf.plugins.misc.games.lumis_quest.api import screens

    start = list(game.iris)
    game.host.keys.press(Action.DOWN)
    for _ in range(20):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] > start[1]

    where = screens.screen_of(*game.iris)
    assert game.screen_at == where
    centre = screens.centre_of(*where)
    # Mid-flip the camera is between the two screens, so it is checked against
    # the pair rather than the destination alone.
    was = screens.centre_of(*screens.screen_of(*start))
    low, high = sorted((was[1], centre[1]))
    assert low - 1.0 <= game.host.camera.center[1] <= high + 1.0


def test_crossing_an_edge_flips_the_screen(game):
    """A flip is the ceremony that makes a small world feel large."""
    from chisurf.plugins.misc.games.lumis_quest.api import screens

    # Driven through the camera directly: which tiles happen to be walkable at
    # a screen boundary is the world generator's business, not this test's.
    game.iris = [screens.WIDTH * 1.5, screens.HEIGHT * 1.5]
    game._screen_view(1 / 60)
    before = game.screen_at
    assert before == (1, 1)

    game.iris[1] = screens.HEIGHT * 2.5
    game._screen_view(1 / 60)
    assert game.screen_at == (before[0], before[1] + 1)
    for _ in range(int(screens.FLIP_SECONDS * 60) + 10):
        centre, height = game._screen_view(1 / 60)
        game.host.camera.center[0], game.host.camera.center[1] = centre
        game.host.camera.height = height
    assert game.host.camera.center[1] == pytest.approx(
        screens.centre_of(*game.screen_at)[1], abs=1.0
    )
    assert game.screen_name != screens.label(*before)


def test_a_screen_is_the_16_bit_playfield(game):
    """16 by 14 tiles, not the 8-bit 16 by 11."""
    from chisurf.plugins.misc.games.lumis_quest.api import screens

    assert (screens.COLS, screens.ROWS) == (16, 14)
    assert game.screen_mode, "the screen camera is the default"


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
    """A beat completes because the run shows it, not because of input."""
    assert game.story.current is not None
    assert game.story.current.key == "the-marked", \
        "the quick-start path is past the waking act"

    # Nothing about pressing a key completes it; facing a marked animal does.
    for _ in range(5):
        game.update(1 / 60, game.host.keys)
    assert game.story.current.key == "the-marked"
    game.story.witness("the-marked")
    assert game.story.current.key == "the-unbinding"

    game.story.choose("clarity")
    assert game.story.order["name"] == "The Order of Clarity"
    with pytest.raises(KeyError):
        game.story.choose("nonsense")


def test_diagonal_movement_is_not_faster(game):
    """Normalising the axis stops diagonals being a speed exploit.

    Measured from open ground rather than from world coordinate (0, 0), which
    is the corner of the sea outside every land: she is relocated out of it
    now, and two runs starting from an illegal position do not start from the
    same legal one.
    """
    open_ground = _open_ground(game)
    start = list(open_ground)

    game.iris = list(start)
    game.host.keys.press(Action.RIGHT)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    straight = abs(game.iris[0] - start[0])

    game.host.keys.release(Action.RIGHT)
    game.host.keys.end_frame()
    game.iris = list(start)
    game.host.keys.press(Action.RIGHT)
    game.host.keys.press(Action.DOWN)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
    diagonal = ((game.iris[0] - start[0]) ** 2
                + (game.iris[1] - start[1]) ** 2) ** 0.5
    assert straight > 50.0, "she has to have somewhere to walk"
    assert diagonal == pytest.approx(straight, rel=0.02)


def _open_ground(game) -> tuple[float, float]:
    """A spot with room to walk in every direction, for a movement test.

    Parameters
    ----------
    game : OverworldGame
        The running game.

    Returns
    -------
    tuple of float
        World coordinates.
    """
    region = game.world.regions[0]
    col, row, width, height = region.rect
    # The test walks 30 frames, which is over five tiles, so the run has to be
    # clear that far in both directions it uses. Scanned over the whole land
    # rather than around its middle: a small corpus makes a land that is mostly
    # compound and border woodland, with the open ground off to one side.
    span = 7
    for start_row in range(row + 1, row + height - span):
        for start_col in range(col + 1, col + width - span):
            if all(
                not tiles.is_blocking(game.world.tile_at(start_col + dx,
                                                         start_row + dy))
                for dx in range(span) for dy in range(span)
            ):
                return ((start_col + 0.5) * tiles.TILE,
                        (start_row + 0.5) * tiles.TILE)
    raise AssertionError("no open ground in the first land")


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


def test_the_party_tab_fits_a_label_and_swaps_a_body(game):
    """Bodies and labels are collected apart and combined by hand.

    That is the build: the same animal wearing a different dye is a different
    creature, so the screen has to let you say which animal and which dye
    without either of them being consumed.
    """
    from chisurf.plugins.misc.games.lumis_quest.api import bestiary

    if not game.pool:
        pytest.skip("spectra.db is not present in this install")
    spare = next(c for c in game.pool if c not in [f.creature for f in game.team])
    body = bestiary.BY_KEY["heron"]
    game.labels.append(spare)
    game.bodies.append(body)
    game.menu_open = True
    game.menu_tab = game.TABS.index("PARTY")

    was = game.team[0].beast.species
    game.menu_row = len(game.team) + 1          # the first body
    game._menu_confirm()
    assert game.team[0].beast.species is body, "the body swapped in"
    assert was in game.bodies, "and the one it replaced went back to the stable"

    game.menu_row = len(game.team) + len(game.bodies) + 2   # the first label
    game._menu_confirm()
    assert game.team[0].creature is spare, "the label was fitted"
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

    # An order will not take a probe with no seals: carry three first.
    from chisurf.plugins.misc.games.lumis_quest.api import tiers

    for warden in tiers.WARDENS[:3]:
        game.story.seal(warden.key)

    # Confirm through every screen of their case, until they ask.
    for _ in range(len(emissary.dialogue) + 2):
        if game.screen is not None and game.screen.choices:
            break
        assert game.story.chosen_order is None, "no pledge before the question"
        game.host.keys.tap(Action.CONFIRM)
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game.screen is not None and game.screen.choices, \
        "the dialogue must end in the question"

    game.menu_index = 0            # "I will serve."
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    order = emissary.role.split(":", 1)[1]
    assert game.story.chosen_order == order

    for _ in range(4):
        if game.speaking is None:
            break
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
        team=[(f.beast.species.key, f.creature.probe_id, f.hp) for f in game.team],
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


def test_a_hitched_frame_does_not_put_her_through_a_wall(game):
    """The bug behind "stuck on objects all the time".

    The frame step is capped at 0.1 s and a sprint is nearly 500 units a
    second, so one hitched frame used to move her two and a half tiles --
    through a wall, after which she was inside geometry and every move out was
    refused. Movement is sub-stepped now, so the cap is what she is tested at.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import BODY

    village = game.world.villages[0]
    col, row, width, height = village.rect
    for corner_x, corner_y in ((col + 1.5, row + height + 3.0),
                               (col + width - 1.5, row + height + 3.0)):
        game.iris = [corner_x * tiles.TILE, corner_y * tiles.TILE]
        game.host.keys.press(Action.UP)
        game.host.keys.press(Action.CONFIRM)      # sprint
        for _ in range(60):
            game.update(game.host.MAX_DT, game.host.keys)
            assert not game._solid(*game.iris), (
                f"walked into something solid at {game.iris}"
            )
        game.host.keys.release(Action.UP)
        game.host.keys.release(Action.CONFIRM)
    assert BODY * 2 < tiles.TILE, "the body has to fit through a one-tile gate"


def test_she_is_never_frozen_wherever_she_is_put(game):
    """Being unable to move at all is worse than being moved wrongly."""
    world = game.world
    tried = 0
    for village in world.villages[:4]:
        col, row, width, height = village.rect
        for spot in ((col + width / 2, row + height / 2),
                     (col + 1.5, row + 1.5),
                     (col + width - 1.5, row + height - 1.5)):
            game.iris = [spot[0] * tiles.TILE, spot[1] * tiles.TILE]
            game._unstick()
            assert not game._solid(*game.iris)
            before = list(game.iris)
            moved = False
            for action in (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT):
                game.host.keys.press(action)
                for _ in range(6):
                    game.update(1 / 60, game.host.keys)
                game.host.keys.release(action)
                if game.iris != before:
                    moved = True
                    break
            assert moved, f"frozen at {spot}"
            tried += 1
    assert tried >= 6


def test_being_inside_a_wall_is_recovered_from_not_frozen(game):
    """A save from an older build, or a corpus that changed underneath one."""
    village = game.world.villages[0]
    col, row, _, _ = village.rect
    # The compound's own corner is solid whatever kind of settlement it is.
    game.iris = [(col + 0.5) * tiles.TILE, (row + 0.5) * tiles.TILE]
    if not game._solid(*game.iris):
        pytest.skip("that corner is not solid in this layout")
    assert game._unstick(), "she was inside something and was not moved"
    assert not game._solid(*game.iris)
    assert game._unstick() is False, "unsticking twice must be a no-op"


def test_a_doorway_can_be_walked_through_off_centre(game):
    """Catching the lip of a gate is the most irritating thing a tile game does."""
    village = next((v for v in game.world.villages if v.kind != "hamlet"),
                   game.world.villages[0])
    gate_col, gate_row = village.gate
    entered = 0
    for offset in (-0.28, 0.0, 0.28):
        game.iris = [(gate_col + 0.5 + offset) * tiles.TILE,
                     (gate_row + 2.5) * tiles.TILE]
        if game._solid(*game.iris):
            continue
        game.host.keys.press(Action.UP)
        for _ in range(90):
            game.update(1 / 60, game.host.keys)
        game.host.keys.release(Action.UP)
        if game.iris[1] < (gate_row - 0.5) * tiles.TILE:
            entered += 1
    assert entered >= 2, "an off-centre approach has to slip into the doorway"


def test_a_town_is_big_enough_to_be_a_town(game):
    """And mostly walkable, because a plaza full of posts is an obstacle course."""
    from chisurf.plugins.misc.games.lumis_quest.api import places

    assert places.PITCH >= 4, "a street narrower than three tiles snags"
    for village in game.world.villages:
        _, _, width, height = village.rect
        assert width >= 12 and height >= 12, (village.place, width, height)

    open_ = solid = 0
    for village in game.world.villages:
        col, row, width, height = village.rect
        for y in range(row + 1, row + height - 1):
            for x in range(col + 1, col + width - 1):
                if tiles.is_blocking(game.world.tile_at(x, y)):
                    solid += 1
                else:
                    open_ += 1
    assert open_ / max(open_ + solid, 1) > 0.85, "too much of a compound is furniture"


def test_a_jump_goes_up_and_comes_back_down(game):
    """Height and fall velocity, on the model a top-down engine uses."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import HOP_HEIGHT

    assert game.z == 0.0 and not game.jumping
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.jumping and game.z > 0.0
    assert game.fall < 0.0, "rising means a negative fall velocity"

    peak = game.z
    for _ in range(120):
        game.update(1 / 60, game.host.keys)
        peak = max(peak, game.z)
        if not game.jumping:
            break
    assert peak > HOP_HEIGHT, peak
    assert not game.jumping, "she has to come down"
    assert game.z == 0.0 and game.fall == 0.0


def test_letting_go_early_makes_a_shorter_jump(game):
    """A jump with one height is a jump with no decision in it."""
    def peak_of(hold_frames: int) -> float:
        game.z = game.fall = 0.0
        game.jumping = False
        game.host.keys.press(Action.CONFIRM)
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
        high = game.z
        for frame in range(120):
            if frame == hold_frames:
                game.host.keys.release(Action.CONFIRM)
            game.update(1 / 60, game.host.keys)
            high = max(high, game.z)
            if not game.jumping:
                break
        game.host.keys.release(Action.CONFIRM)
        game.host.keys.end_frame()
        return high

    tapped = peak_of(1)
    held = peak_of(60)
    assert held > tapped * 1.2, (tapped, held)


def test_a_jump_clears_the_low_things_and_not_the_walls(game):
    """You hop a fence. You do not hop a house."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import HOPPABLE

    assert tiles.FENCE in HOPPABLE and tiles.WATER in HOPPABLE
    assert tiles.WALL not in HOPPABLE, "a wall is the shape of the place"
    assert tiles.BUILDING not in HOPPABLE
    assert tiles.CLIFF not in HOPPABLE

    # Airborne, a hoppable tile stops blocking; a wall never does.
    game.z, game.jumping = 0.0, False
    grounded_water = game._solid_at_tile(tiles.WATER)
    game.z, game.jumping = 20.0, True
    assert game.hopping
    assert grounded_water and not game._solid_at_tile(tiles.WATER)
    assert game._solid_at_tile(tiles.WALL), "walls stay solid in the air"
    game.z, game.jumping = 0.0, False


def test_an_exchange_says_what_it_did_where_it_did_it(game, wild_room):
    """A bar that moves is a bar that moved; a number over the thing is the hit.

    This also walks the emit path end to end, which matters more than it looks:
    every field name in it (`emission_nm`, the portrait anchors) is read only
    here, so a rename would otherwise sit in the tree raising an AttributeError
    that no test and no ordinary play session reaches until somebody wins.
    """
    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is not None

    # The anchors come from the draw, so take a frame first.
    game.draw(_scene(game))
    assert {"enemy", "ours"} <= set(game._portraits)

    game.host.keys.tap(Action.CONFIRM)          # Emit
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert len(game.battle_sparks) > 0, "an exchange produced no feedback at all"


def test_carrying_a_label_away_is_visible_on_the_overworld(game, wild_room):
    """The battle screen said it, and then the battle screen was torn down."""
    from chisurf.plugins.misc.games.lumis_quest.api import bestiary as bestiary_api

    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    fight = game.battle
    fight.finished = True
    fight.won = True
    fight.taken = fight.opponent.beast.label
    fight.freed = fight.opponent.beast.species
    fight.joined = True
    if fight.taken is None:
        pytest.skip("this encounter's beast carries no label")
    assert isinstance(fight.freed, bestiary_api.Species)

    # No page attached, so Confirm dismisses the fight rather than opening the
    # page's own question.
    game.encounter_room = None

    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.battle is None
    assert len(game.sparks) > 0
    assert game.battle_sparks.particles == [], "battle feedback outlived its screen"


def _scene(game):
    """A scene over the game's own host, for one frame.

    Returns
    -------
    chisurf.gui.chigame.scene.Scene
        Ready to draw into.
    """
    return chigame.Scene(_Recorder(), camera=game.host.camera)


class _Recorder:
    """A sprite batch that records, so a draw can be taken without a GPU."""

    def add(self, **quad) -> None:
        """Ignore one quad.

        Parameters
        ----------
        **quad
            Whatever the scene passes.
        """
