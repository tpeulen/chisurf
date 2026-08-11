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
    screen-based camera, and a composed view is what it buys. Scrolling is
    the default now, so this opts into screen mode explicitly to test it.
    """
    from chisurf.plugins.misc.games.lumis_quest.api import screens

    game.screen_mode = True
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


def test_scrolling_is_the_default_camera(game):
    """Screen-by-screen is still there, but scrolling is what a new run gets."""
    assert not game.screen_mode


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


def test_a_wide_house_blocks_the_ground_its_sprite_actually_covers(game):
    """A real building sprite is wider than the one tile its room sits on.

    ``_building`` draws it that wide (:attr:`OverworldGame._sprite_tiles`), so
    walking was only blocked at the room's own ``BUILDING`` tile -- she could
    step straight through the painted wall either side of the door. The
    columns the sprite actually spans get the same whole-tile solidity.
    """
    wide = next(
        (r for r in game.world.rooms
         if game._sprite_tiles.get(game._house_sprite(r, lit=False), (1.0, 1.0))[0] > 1.0),
        None,
    )
    if wide is None:
        pytest.skip("no room in this seed picked a wider-than-one-tile house")
    col = int(wide.position[0] // tiles.TILE)
    row = int(wide.position[1] // tiles.TILE)
    assert (col - 1, row) in game._building_solid or (col + 1, row) in game._building_solid

    # And walking at it from the side the sprite overhangs must actually
    # refuse the step, not just add an entry to the lookup nothing reads.
    extra_col = col - 1 if (col - 1, row) in game._building_solid else col + 1
    game.iris = [(extra_col + 0.5) * tiles.TILE, (row + 1.5) * tiles.TILE]
    before = list(game.iris)
    game.host.keys.press(Action.UP)
    for _ in range(60):
        game.update(1 / 60, game.host.keys)
    assert game.iris[1] >= before[1] - tiles.TILE, "she walked through the sprite's overhang"


def test_a_door_is_hittable_from_beside_it_not_only_dead_centre(game):
    """A one-tile door used to need her exact centre inside that one cell.

    Widened to a small ring of samples around wherever she is standing
    (`DOOR_REACH`), which is what made walking up to a cave mouth and
    pressing the key at a normal angle actually work.
    """
    col = row = None
    for r in range(game.world.height):
        for c in range(game.world.width):
            if game.world.tile_at(c, r) == tiles.CAVE:
                col, row = c, r
                break
        if col is not None:
            break
    if col is None:
        pytest.skip("this seed has no cave mouth in the lit world")

    centre = [(col + 0.5) * tiles.TILE, (row + 0.5) * tiles.TILE]
    game.iris = list(centre)
    assert game._door_scene() == "cave", "dead centre must still hit"

    # Half a tile off to one side -- inside DOOR_REACH, previously a miss.
    game.iris = [centre[0] + tiles.TILE * 0.5, centre[1]]
    assert game._door_scene() == "cave", "just beside it must hit too"


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


def test_lumi_faces_the_way_it_is_actually_walking(game):
    """Its own facing, not Iris's -- and drawn from real art, not a guess.

    The chase can point Lumi a different way than Iris last turned, and it
    has its own up/down/right art now (no more falling back to the down
    sprite while walking away, which read as staring at the camera).
    """
    game.story.has_lumi = True
    game.facing = "left"  # deliberately not the direction Lumi will step

    game.iris = [game.lumi[0], game.lumi[1] - 100.0]  # north of Lumi
    game.update(1 / 60, game.host.keys)
    assert game.lumi_facing == "up"
    assert game._lumi_sprite() == ("up", False)

    game.iris = [game.lumi[0] + 100.0, game.lumi[1]]  # east of Lumi
    game.update(1 / 60, game.host.keys)
    assert game.lumi_facing == "right"
    assert game._lumi_sprite() == ("right", False)

    game.iris = [game.lumi[0] - 100.0, game.lumi[1]]  # west of Lumi
    game.update(1 / 60, game.host.keys)
    assert game.lumi_facing == "left"
    assert game._lumi_sprite() == ("right", True), "mirrors the right frame, same as everyone else"


def test_the_nearest_room_is_reported(game):
    """The HUD names where you are standing."""
    first = game.world.rooms[0]
    game.iris = list(first.position)
    assert game.here is first

    last = game.world.rooms[-1]
    game.iris = list(last.position)
    assert game.here is last


def test_entering_a_house_opens_its_room_and_leaving_returns_her(game):
    """Interiors were built, tested and unreachable -- this is what opens one.

    `ENTERABLE`/`interiors.build` already existed; nothing on the overworld
    had ever called either.
    """
    room = game.world.rooms[0]
    x, y = room.position
    # One tile south of the door -- room.position is already the door
    # tile's own centre, so a further +1.0 (not +1.5) tile lands her in the
    # middle of the tile just outside it.
    game.iris = [x, y + tiles.TILE]
    before = list(game.iris)

    building = game._building_scene()
    assert building is not None, "standing this close must find the door"
    tile, col, row = building
    assert (col, row) == room.tile

    game._enter_building(tile, col, row)
    assert game.interior is not None
    assert game.interior.title

    # Walk toward the door (south wall) and out again.
    game.host.keys.press(Action.DOWN)
    for _ in range(400):
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
        if game.interior is None:
            break
    assert game.interior is None, "walking to the door must step back outside"
    assert game.iris == before, "leaving must return her to exactly where she went in"


def test_the_bottom_band_only_names_a_room_she_is_actually_near(game):
    """`here` has no distance limit of its own -- the band adds one.

    Across open ground the *nearest* room can be many tiles away, and the
    bottom band showed its name anyway, which was most of why it never went
    away: `_nearby_room` is the fix, `here` unchanged (other callers still
    want "nearest regardless of distance" and add their own cutoff, e.g.
    `_try_encounter`'s guardian range).
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import ROOM_LABEL_RANGE

    room = game.world.rooms[0]
    game.iris = list(room.position)
    assert game._nearby_room() is room, "standing on it must still report it"

    game.iris = [room.position[0] + ROOM_LABEL_RANGE * 5, room.position[1]]
    nearest = game.here
    assert nearest is not None
    distance = ((nearest.position[0] - game.iris[0]) ** 2
                + (nearest.position[1] - game.iris[1]) ** 2) ** 0.5
    if distance <= ROOM_LABEL_RANGE:
        pytest.skip("this seed's rooms are too dense to get clear of all of them")
    assert game._nearby_room() is None, "too far to be 'standing near' the nearest room"


def test_the_land_is_named_where_she_stands(game):
    """Standing on a land reports its fantasy name, not the directory."""
    game.iris = list(game.world.rooms[0].position)
    assert game.land is not None
    assert game.land.title.startswith("The ")


def test_the_land_banner_arms_on_arrival_and_counts_down(game):
    """The banner names a crossing, then gets out of the way on its own.

    It used to sit on screen permanently, which was the whole complaint: you
    could not see the world it was describing. Arriving retimes it; standing
    still afterwards only counts it down, never back up.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (
        LAND_BANNER_SECONDS,
    )

    game.iris = list(game.world.rooms[0].position)
    game.update(1 / 60, game.host.keys)
    assert game.land is not None
    assert game._land_banner_land is game.land
    assert game._land_banner_timer == pytest.approx(LAND_BANNER_SECONDS)

    game.update(1.0, game.host.keys)
    assert game._land_banner_timer == pytest.approx(LAND_BANNER_SECONDS - 1.0)

    for _ in range(10):
        game.update(1.0, game.host.keys)
    assert game._land_banner_timer == 0.0


def test_menu_toggles_a_map_that_fits_the_world(game):
    """The map view frames everything rather than guessing a height."""
    # The map lives behind the pause menu now: Menu opens it, STATUS is the
    # first tab, and Confirm on MAP toggles the map and closes the menu.
    game.host.keys.tap(Action.MENU)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_open
    game.menu_tab = game.TABS.index("MAP")

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
    assert game.menu_open and game.TABS[game.menu_tab] == "STATUS"

    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.TABS[game.menu_tab] == "MAP"

    game.host.keys.tap(Action.SHOULDER_R)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.TABS[game.menu_tab] == "RIG"

    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert not game.menu_open


def _pixel_for(game, wx: float, wy: float) -> tuple[float, float]:
    """The canvas pixel a world point would be clicked at.

    Inverts `OverworldGame._click_world`'s own formula so the test does not
    have to duplicate assumptions about where the camera happens to be
    sitting.
    """
    camera = game.host.camera
    width_px, height_px = game.host.ctx.size
    half = camera.half_extent(width_px / max(height_px, 1))
    left = float(camera.center[0]) - half[0]
    top = float(camera.center[1]) - half[1]
    px = (wx - left) / (half[0] * 2.0) * width_px
    py = (wy - top) / (half[1] * 2.0) * height_px
    return px, py


def test_clicking_a_tab_selects_it(game):
    """Mouse control in the pause menu: a tab is a click target, not just L/R."""
    game.menu_open = True
    game.menu_tab = 0
    camera = game.host.camera
    half = camera.half_extent(game.host.ctx.size[0] / max(game.host.ctx.size[1], 1))
    cx, cy = float(camera.center[0]), float(camera.center[1])
    span = half[0] * 1.5
    target = 2  # "RIG"
    tab_x = cx - span * 0.5 + (target + 0.5) * span / len(game.TABS)
    tab_y = cy - half[1] * 0.62
    game.host.keys.click_at(*_pixel_for(game, tab_x, tab_y))
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.TABS[game.menu_tab] == "RIG"


def test_clicking_a_tab_selects_it_on_a_hidpi_display(qapp, tmp_path):
    """A click was landing nowhere near the cursor on a Retina display.

    Qt's own mouse-event coordinates are logical points; ``ctx.size`` (and
    the old formula built on it) is physical pixels. At a 2x pixel ratio --
    the default on most Macs -- that halved the fraction every click
    resolved to, so a click square on a menu tab used to land at a world
    point nowhere near it and nothing ever seemed to respond to the mouse.
    """
    try:
        context = chigame.create_offscreen(size=(240, 180))
    except Exception as error:  # pragma: no cover - depends on the machine
        pytest.skip(f"no usable GPU adapter: {error}")
    context.canvas.set_pixel_ratio(2.0)
    context.canvas.set_logical_size(240, 180)
    assert context.canvas.get_physical_size() == (480, 360)
    assert context.canvas.get_logical_size() == (240, 180)

    docs = _docs(tmp_path)
    game = OverworldGame(world=build_world(docs), save_path=tmp_path / "run.json",
                         docs_root=docs)
    chigame.GameHost(game, context, with_text=False, with_audio=False)
    game.finish_loading(skip_prologue=True)

    game.menu_open = True
    game.menu_tab = 0
    camera = game.host.camera
    half = camera.half_extent(context.canvas.get_logical_size()[0]
                               / max(context.canvas.get_logical_size()[1], 1))
    cx, cy = float(camera.center[0]), float(camera.center[1])
    span = half[0] * 1.5
    target = 2  # "RIG"
    tab_x = cx - span * 0.5 + (target + 0.5) * span / len(game.TABS)
    tab_y = cy - half[1] * 0.62

    # The click a real Qt widget would report: logical points, not the
    # canvas' physical pixel count.
    logical_w, logical_h = context.canvas.get_logical_size()
    left, top = cx - half[0], cy - half[1]
    click_x = (tab_x - left) / (half[0] * 2.0) * logical_w
    click_y = (tab_y - top) / (half[1] * 2.0) * logical_h
    game.host.keys.click_at(click_x, click_y)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.TABS[game.menu_tab] == "RIG"


def test_clicking_a_row_selects_and_confirms_it(game):
    """A row click is choose-and-confirm in one, the way a button is."""
    game.menu_open = True
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 0
    before = game.scheme
    camera = game.host.camera
    half = camera.half_extent(game.host.ctx.size[0] / max(game.host.ctx.size[1], 1))
    cx, cy = float(camera.center[0]), float(camera.center[1])
    row_x = cx - half[0] * 0.62
    row_y = cy - half[1] * 0.44  # top, row index 0
    game.host.keys.click_at(*_pixel_for(game, row_x, row_y))
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_row == 0
    assert game.scheme != before, "a row click must select AND confirm"


def test_clicking_a_title_row_selects_and_confirms_it(game):
    """Mouse control on the title screen too, not just the pause menu."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import VIEW_HEIGHT

    game.phase = "title"
    game.title_index = 0
    rows = game._title_rows()
    target = len(rows) - 1  # "controls: ..." -- confirming it must not crash
    before = game.scheme
    camera = game.host.camera
    cx, cy = float(camera.center[0]), float(camera.center[1])
    scale = camera.height / VIEW_HEIGHT
    row_y = cy + target * 16.0 * scale
    game.host.keys.click_at(*_pixel_for(game, cx, row_y))
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.title_index == target
    assert game.scheme != before, "clicking the controls row must cycle it"


def test_the_escape_key_is_actually_bound_to_cancel(game):
    """A bound Action is not proof the real key reaches it.

    `test_cancel_taps_the_menu_open_but_held_it_zooms` below drives
    `Action.CANCEL` directly and so passed while "Escape" pressed nothing at
    all in play: the game's own default `host.keys.bindings` (set in
    `setup`, independent of `chigame.input.DEFAULT_BINDINGS`) had never
    mapped the literal key "Escape" to any action, only "Backspace" -- this
    checks the string, not the enum, so that gap cannot reopen unnoticed.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import SCHEMES

    for scheme_keys in SCHEMES.values():
        assert scheme_keys.get("Escape") is Action.CANCEL
    assert game.host.keys.bindings.get("Escape") is Action.CANCEL


def test_cancel_opens_the_menu_on_a_plain_tap(game):
    """Escape/Backspace is Cancel, and every game this shape opens its menu on it.

    Cancel used to double as hold-to-zoom-out, which made whether a press
    opened the menu depend on exactly how long it was held before release --
    reported back as Escape simply not working half the time. It is just the
    menu key now, and pressing it is enough; nothing else needs to happen
    first, and holding it does not change the camera.
    """
    start_height = game.view_height
    game.host.keys.tap(Action.CANCEL)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.menu_open, "a tap must open the menu"
    assert game.view_height == start_height, "cancel must not also zoom"

    game.menu_open = False
    game.host.keys.press(Action.CANCEL)
    for _ in range(30):
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game.menu_open, "the press already opened it -- holding must not close it again"
    assert game.view_height == start_height, "holding cancel must not zoom"


def test_the_mouse_wheel_zooms(game):
    """Scrolled up (negative dy) zooms in, matching a map; down zooms out."""
    start = game.view_height
    game.host.keys.scroll(-120.0)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.view_height < start, "scrolling up must zoom in"

    zoomed_in = game.view_height
    game.host.keys.scroll(120.0)
    game.update(1 / 60, game.host.keys)
    game.host.keys.end_frame()
    assert game.view_height > zoomed_in, "scrolling down must zoom back out"

    # end_frame clears it -- a wheel tick is one instant, not a held input.
    before = game.view_height
    game.update(1 / 60, game.host.keys)
    assert game.view_height == before, "a wheel step must not repeat on its own"


def test_free_roam_autosaves_between_the_ceremony_saves(game):
    """A crash between a new journey and the next Warden's seal lost everything.

    Autosave is the safety net in between, not a replacement for either.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import AUTOSAVE_SECONDS

    game._save_path.unlink(missing_ok=True)
    game._autosave_timer = 0.0
    step = 1.0
    for _ in range(int(AUTOSAVE_SECONDS / step) - 1):
        game.update(step, game.host.keys)
    assert not game._save_path.exists(), "must not save before the interval is up"

    for _ in range(3):
        game.update(step, game.host.keys)
    assert game._save_path.exists(), "must autosave once the interval elapses"


def test_autosave_does_not_fire_mid_battle(game, wild_room):
    """Saving mid-transaction is how a run gets corrupted, not protected."""
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import AUTOSAVE_SECONDS

    game.iris = [wild_room.position[0], wild_room.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is not None

    game._save_path.unlink(missing_ok=True)
    game._autosave_timer = AUTOSAVE_SECONDS  # already due, if it were checked
    for _ in range(int(AUTOSAVE_SECONDS) + 5):
        game.update(1.0, game.host.keys)
    assert not game._save_path.exists(), "battle input never reaches the autosave tick"


def test_the_status_tab_reports_what_the_hud_used_to_show_permanently(game):
    """The stat block moved behind Menu; it did not just disappear."""
    game.menu_tab = game.TABS.index("STATUS")
    rows = game._menu_rows()
    joined = " ".join(rows)
    assert "settled" in joined and "scouted" in joined
    assert "wild" in joined
    assert "seal" in joined and "licence" in joined
    assert f"mode: {game.mode}" in joined
    assert f"level {game.game_state.level}" in joined, "the walk used to pay out nothing at all"


def test_the_warden_compass_points_somewhere_real(game):
    """next_warden existed but nothing ever asked it where they stood."""
    from chisurf.plugins.misc.games.lumis_quest.api import tiers

    warden = tiers.next_warden(game.story.seals)
    assert warden is not None, "a fresh run has not beaten any yet"
    line = game._warden_compass()
    assert warden.name in line
    assert any(point in line for point in game._COMPASS), "a bearing, not just a name"

    village = next(v for v in game.world.villages if v.warden == warden.key)
    col, row, width, height = village.rect
    region = game.world.region_at((col + width * 0.5) * tiles.TILE,
                                  (row + height * 0.5) * tiles.TILE)
    land = region.title if region is not None else village.place
    assert land in line

    # Holding every seal names the ladder as climbed, not a stale bearing.
    game.story.seals = {w.key for w in tiers.WARDENS}
    assert "held" in game._warden_compass()


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
    # Rows 0 and 1 are the weapon/magic cycle now; found parts start at 2.
    game.menu_row = 2
    game._menu_confirm()

    assert game.rig.emission is part, "the part must land in its own slot"
    assert game.loadout.emission is part, "and fit as the single filter too"


def test_the_rig_tab_cycles_the_overworld_weapon_and_magic(game):
    """_cycle_weapon/_cycle_magic were dead code -- no button was free for
    them on the nine-action pad, so they are menu rows instead."""
    game.menu_open = True
    game.menu_tab = game.TABS.index("RIG")

    weapon = game.active_weapon
    game.menu_row = 0
    game._menu_confirm()
    assert game.active_weapon != weapon
    assert game.active_weapon in game.weapons

    magic = game.active_magic
    game.menu_row = 1
    game._menu_confirm()
    assert game.active_magic != magic
    assert game.active_magic in game.magics


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


def test_llm_status_menu_display_and_hover_info(game):
    """The MODE and OPTIONS tabs show the LLM indicator and hover setup guidance."""
    game.menu_open = True
    game.menu_tab = game.TABS.index("MODE")
    mode_rows = game._menu_rows()
    assert any("llm status:" in r for r in mode_rows)
    llm_mode_idx = [i for i, r in enumerate(mode_rows) if "llm status:" in r][0]

    game.menu_row = llm_mode_idx
    scene = _scene(game)
    game._draw_menu(scene, game.host.camera, game.host.camera.half_extent(16 / 9))

    game.menu_tab = game.TABS.index("OPTIONS")
    opt_rows = game._menu_rows()
    assert any("llm provider:" in r for r in opt_rows)
    llm_opt_idx = [i for i, r in enumerate(opt_rows) if "llm provider:" in r][0]
    game.menu_row = llm_opt_idx
    game._options_confirm()


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


def test_a_real_sign_off_pays_xp_but_training_never_does(game, wild_room, tmp_path):
    """Levelling answers to a page actually reviewed, not to combat or a guess.

    Casting spells used to spend a permanent narrative counter; the same
    mistake here would be XP for merely walking through the challenge
    screen. It has to come from review_bridge.clear_page saying "signed",
    which only happens in EXPERT mode with the right answer.
    """
    from chisurf.plugins.misc.games.lumis_quest.api import review_bridge

    game.mode = review_bridge.TRAINING
    game.encounter_room = wild_room
    questions, content_hash = review_bridge.challenge_for(
        wild_room.path, cache_dir=tmp_path / "cache"
    )
    if not questions:
        pytest.skip("this fixture page is too thin to question")
    game.challenge, game.challenge_hash = questions[0], content_hash
    game.menu_index = questions[0].answer
    xp_before = game.game_state.xp

    game.host.keys.tap(Action.CONFIRM)
    game._challenge_input(game.host.keys)
    game.host.keys.end_frame()
    assert not game.verdict.signed_off, "training mode signs nothing off"
    assert game.game_state.xp == xp_before, "and so must pay nothing"

    # The same page, in EXPERT mode with the right answer, is a real review.
    game.mode = review_bridge.EXPERT
    game.encounter_room = wild_room
    game.challenge, game.challenge_hash = questions[0], content_hash
    game.menu_index = questions[0].answer
    game._pending_first_clear = True

    game.host.keys.tap(Action.CONFIRM)
    game._challenge_input(game.host.keys)
    game.host.keys.end_frame()
    if game.verdict.reason == "untracked":
        pytest.skip("this fixture page is outside the tracked directories")
    assert game.verdict.signed_off
    assert game.game_state.xp > xp_before


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


def test_the_title_screen_draws_the_world_behind_the_menu(game):
    """A flat panel used to stand in for a background; the world does now."""
    game.phase = "title"
    frame = _frame(game)
    sprite_quads = [q for q in frame.quads if q.get("shape") == chigame.SPRITE]
    assert len(sprite_quads) > 5, "the spawn area should paint real ground and cover"


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

    # Hear him out: the waking is witnessed when he has said his piece. Each
    # line now takes two taps -- the appearing-text effect makes the first
    # one finish the line rather than advance past it.
    for _ in range(len(game.speaking.dialogue) * 2):
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
    for _ in range(len(hound.dialogue) * 2):
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

    # Confirm through every screen of their case, until they ask. Twice the
    # budget: the appearing-text effect makes the first tap on a line finish
    # revealing it rather than advance past it.
    for _ in range(len(emissary.dialogue) * 2 + 4):
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


def test_the_workshop_and_an_infusion_survive_save_and_restore(game):
    """A gathered shelf and a fixed-in reagent are run state, not scenery."""
    if not game.pool or not game.team:
        pytest.skip("spectra.db is not present in this install")
    game.workshop.gather("roxs", 3)
    game.workshop.gather("trolox", 1)
    assert game.workshop.craft("unblinking")
    game.party_slot = 0
    infusions_at = len(game.team) + 1 + len(game.bodies) + 1 + len(game.labels) + 1
    game.menu_row = infusions_at
    game._party_confirm()
    assert game.team[0].beast.infusion == "unblinking"
    materials_before = dict(game.workshop.materials)

    game.save_run()
    game._restore()

    assert game.workshop.materials == materials_before
    assert game.workshop.crafted == []
    assert game.team[0].beast.infusion == "unblinking"


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
    screen_mode = game.screen_mode
    game._menu_confirm()
    assert game.screen_mode != screen_mode

    game.menu_row = 2
    speed = game.walk_speed
    game._menu_confirm()
    assert game.walk_speed != speed

    game.menu_row = 4
    music_volume = game.music_volume
    game._menu_confirm()
    assert round(game.music_volume - music_volume, 2) == 0.1
    assert game.host.audio.music_volume == game.music_volume

    game.menu_row = 5
    sfx_volume = game.sfx_volume
    game._menu_confirm()
    assert round(game.sfx_volume - sfx_volume, 2) == 0.1
    assert game.host.audio.sfx_volume == game.sfx_volume

    # A full turn of the dial wraps back to silent rather than getting stuck
    # at 100%.
    game.music_volume = 1.0
    game.menu_row = 4
    game._menu_confirm()
    assert game.music_volume == 0.0


def test_regenerating_redraws_the_wilderness_but_not_the_world(game):
    """A player who has learned where a page lives must not lose that."""
    rooms = {room.address: room.tile for room in game.world.rooms}
    lands = [region.title for region in game.world.regions]

    game.menu_open = True
    game.menu_tab = game.TABS.index("OPTIONS")
    game.menu_row = 7
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


def test_a_wild_encounter_opens_with_a_zoom_and_a_flash(game, wild_room):
    """Cut to zoomed in, then update() eases the camera back out.

    `_draw_battle` fades a flash over the same window -- see
    `BATTLE_ZOOM_START`/`ENCOUNTER_FLASH_SECONDS`.
    """
    from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (
        BATTLE_ZOOM_START,
        ENCOUNTER_FLASH_SECONDS,
    )

    game.iris = [wild_room.position[0], wild_room.position[1] + tiles.TILE]
    game.view_height = 300.0
    game._try_encounter()
    assert game.battle is not None
    assert game._battle_intro == pytest.approx(ENCOUNTER_FLASH_SECONDS)
    assert game.host.camera.height == pytest.approx(300.0 * BATTLE_ZOOM_START), (
        "a wild encounter must cut in already zoomed, not ease into the zoom too"
    )

    for _ in range(int(ENCOUNTER_FLASH_SECONDS * 60) + 30):
        game.update(1 / 60, game.host.keys)
        game.host.keys.end_frame()
    assert game._battle_intro == 0.0, "the flash must not run forever"
    assert game.host.camera.height == pytest.approx(300.0, rel=0.05), (
        "the zoom must settle back to the overworld's own framing"
    )


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


class _Quads:
    """A sprite batch that records every quad, so a frame can be inspected."""

    def __init__(self) -> None:
        self.quads: list[dict] = []

    def add(self, **quad) -> None:
        """Record one quad.

        Parameters
        ----------
        **quad
            Whatever the scene passes through.
        """
        self.quads.append(quad)


def _frame(game):
    """Draw one frame into a recorder.

    Returns
    -------
    _Quads
        Every quad the frame queued.
    """
    batch = _Quads()
    game.draw(chigame.Scene(batch, camera=game.host.camera,
                            font=_MeasuringFont()))
    return batch


class _MeasuringFont:
    """Stands in for the real atlas, with the real metrics.

    The atlas needs a GPU; the numbers that decide layout do not. The face is
    proportional, so this has to answer per character rather than hand back one
    nominal width -- which is exactly what the real one does.
    """

    def __init__(self) -> None:
        from chisurf.gui.chigame import pixelfont
        self._font = pixelfont
        self._metrics = pixelfont.metrics()
        self.cell_h = pixelfont.HEIGHT

    def _box(self, char: str):
        """Atlas placement and advance for one character.

        Returns
        -------
        tuple of int
            ``(atlas x, ink width, advance)``.
        """
        return self._metrics.get(char, self._metrics["?"])

    def box_of(self, char: str) -> float:
        """Drawn width over line height.

        Returns
        -------
        float
            As the real atlas reports it.
        """
        return self._box(char)[1] / self._font.HEIGHT

    def advance_of(self, char: str) -> float:
        """Pen advance over line height.

        Returns
        -------
        float
            As the real atlas reports it.
        """
        return self._box(char)[2] / self._font.HEIGHT

    def measure(self, text: str, height: float) -> float:
        """How wide a string will be, in world units.

        Returns
        -------
        float
            Advance width.
        """
        return height * sum(self.advance_of(char) for char in text)

    @property
    def aspect(self) -> float:
        """A nominal character width over line height.

        Returns
        -------
        float
            The advance of a digit.
        """
        return self.advance_of("0")

    @property
    def pitch(self) -> float:
        """Same as :attr:`aspect`.

        Returns
        -------
        float
            Nominal advance over line height.
        """
        return self.aspect

    def uv_for(self, char: str):
        """Atlas rectangle, which nothing here reads.

        Returns
        -------
        tuple of float
            A unit rectangle.
        """
        return (0.0, 0.0, 1.0, 1.0)


def _glyphs_and_panels(batch):
    """Split a recorded frame into text quads and the panels behind them.

    Returns
    -------
    tuple
        ``(glyph quads, panel quads)``.
    """
    from chisurf.gui.chigame.render import GLYPH
    glyphs = [q for q in batch.quads if q.get("shape") == GLYPH]
    # The panels are the handful of very large quads; the tiles are many small
    # ones, so area sorts them apart without needing the pack to say so.
    panels = sorted(batch.quads, key=lambda q: -(q["size"][0] * q["size"][1]))[:6]
    return glyphs, panels


def test_no_battle_text_is_drawn_off_the_screen(game, wild_room):
    """The class of bug that hid behind a blurry font.

    Every readout in this screen was placed against a hard-coded offset, so the
    last option sat inside a rounded corner -- "Withdraw", the one a player in
    trouble is looking for, was shaved off. A sharper face did not cause that;
    it stopped hiding it.
    """
    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is not None

    glyphs, _ = _glyphs_and_panels(_frame(game))
    assert glyphs, "the battle screen drew no text at all"
    # The encounter takes the whole screen now, so the screen is the container.
    camera = game.host.camera
    width, height = game.host.ctx.size
    half = camera.half_extent(width / max(height, 1))
    px, py = float(camera.center[0]), float(camera.center[1])
    pw, ph = float(half[0]) * 2.0, float(half[1]) * 2.0
    for quad in glyphs:
        x, y = quad["pos"]
        w, h = quad["size"]
        assert x - w / 2 >= px - pw / 2 - 1e-6, "text runs off the left of the screen"
        assert x + w / 2 <= px + pw / 2 + 1e-6, "text runs off the right of the screen"
        assert y - h / 2 >= py - ph / 2 - 1e-6, "text runs off the top of the screen"
        assert y + h / 2 <= py + ph / 2 + 1e-6, "text runs off the bottom of the screen"


def test_the_readouts_do_not_print_through_each_other(game):
    """Eleven readouts at eleven fixed offsets is eleven chances to collide.

    A row that appears only while resting used to shift nothing, so it landed
    on whatever was beneath it.
    """
    game.resting = True
    game.labels.extend(game.pool[:2])
    glyphs, _ = _glyphs_and_panels(_frame(game))
    # Group the left-hand column's glyphs into lines by their y, and check the
    # lines are separated by at least a glyph's height.
    # Every string is drawn twice -- the console drop shadow is a dark copy one
    # font pixel down and right -- so the shadow pass has to come out before
    # anything counts lines, or every line "overlaps" its own shadow.
    ink = [q for q in glyphs if any(q["color"][:3])]
    left = min((q["pos"][0] for q in ink), default=0.0)
    column = [q for q in ink if q["pos"][0] < left + tiles.TILE * 12]
    lines = sorted({round(q["pos"][1], 3) for q in column})
    heights = {round(q["pos"][1], 3): q["size"][1] for q in column}
    for first, second in zip(lines, lines[1:]):
        gap = second - first
        assert gap >= max(heights[first], heights[second]) * 0.95, (
            f"two readouts overlap at y={first:.1f} and y={second:.1f}")


def test_battle_loss_or_flee_triggers_cooldown_and_faint_preventing_attack_loop(game, wild_room):
    """Losing or fleeing a battle must trigger encounter cooldown and faint if lost, avoiding loop."""
    wild = wild_room
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._try_encounter()
    assert game.battle is not None

    # Test Fleeing
    game.battle.flee()
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)
    assert game.battle is None
    assert game._encounter_cooldown > 0.0, "Fleeing must set encounter cooldown"

    # Enforce re-encounter attempt during cooldown
    game._try_encounter(force=True)
    assert game.battle is None, "Should not re-trigger encounter during cooldown"

    # Test Defeat / Fainting
    game.iris = [wild.position[0], wild.position[1] + tiles.TILE]
    game._encounter_cooldown = 0.0
    game._try_encounter(force=True)
    assert game.battle is not None

    game.battle.finished = True
    game.battle.won = False
    game.battle.fled = False
    game.host.keys.tap(Action.CONFIRM)
    game.update(1 / 60, game.host.keys)

    assert game.battle is None
    assert game._encounter_cooldown > 0.0
    assert any(f.alive for f in game.team), "Team should have restored HP on faint"


def test_minigame_request_awards_photons_and_xp(game):
    """Minigame request in dialogue awards photons and XP."""
    from chisurf.plugins.misc.games.lumis_quest.api.engine import Request
    xp_before = game.game_state.xp
    photons_before = game.photons
    game._serve(Request(kind="minigame", args={"game": "minesweeper"}))
    assert game.game_state.xp > xp_before, "Minigame must award XP"
    assert game.photons >= photons_before, "Minigame must restore photons"



def test_salvaging_a_dark_ruin_yields_a_reagent_once_and_persists(game):
    """A ruin in the dark manifold is worth one reagent, ever.

    Pressing the action key at a ruin salvages a crafting reagent; pressing
    again at the same cell yields nothing, and the picked-clean set survives
    a save/restore round trip so a reload cannot farm it either.
    """
    import numpy as np

    from chisurf.plugins.misc.games.lumis_quest.api import save as save_api

    cells = np.argwhere(game.world.dark == tiles.RUIN)
    assert cells.size, "the miniature world must ruin at least one premises"
    row, col = (int(value) for value in cells[0])

    game.dark = True
    game.iris = [col * tiles.TILE + tiles.TILE / 2.0,
                 row * tiles.TILE + tiles.TILE / 2.0]

    found = game._ruin_scene()
    assert found == (col, row)

    before = dict(game.workshop.materials)
    game._salvage_dark_ruin(*found)
    gained = sum(game.workshop.materials.values()) - sum(before.values())
    assert gained == 1, "one ruin, one reagent"
    assert (col, row) in game.salvaged
    assert game._ruin_scene() is None, "a picked-clean ruin offers nothing"

    # The lit side never offers a salvage, whatever stands there.
    game.dark = False
    assert game._ruin_scene() is None

    # And the set survives the save file.
    state = game.snapshot()
    reloaded = save_api.RunState.load(state.save(game._save_path))
    assert f"{col},{row}" in reloaded.salvaged
