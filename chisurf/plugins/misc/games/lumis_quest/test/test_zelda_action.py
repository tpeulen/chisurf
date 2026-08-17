"""Tests for Zelda-style real-time overworld action combat, magic, weapons, and HUD."""

from __future__ import annotations

import pathlib
import pytest

pytest.importorskip("wgpu")
pytest.importorskip("rendercanvas")

from chisurf.gui import chigame
from chisurf.plugins.misc.games.lumis_quest.api import npcs as npcs_api
from chisurf.plugins.misc.games.lumis_quest.api import tiles as T
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world
from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (
    MAGIC_DATA,
    WEAPON_DATA,
    OverworldGame,
)


def _docs(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "docs"
    section = root / "guides"
    section.mkdir(parents=True)
    body = "Anisotropy and fluorescence decay mechanics.\n"
    names = [f"p{index}" for index in range(4)]
    for name in names:
        (section / f"{name}.md").write_text(f"# {name.upper()}\n\n{body}", encoding="utf-8")
    listing = "\n".join(names)
    (section / "index.md").write_text(
        f"# Guides\n\n```{{toctree}}\n:maxdepth: 1\n\n{listing}\n```\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def game(qapp, tmp_path):
    try:
        context = chigame.create_offscreen(size=(240, 180))
    except Exception as error:
        pytest.skip(f"no usable GPU adapter: {error}")
    docs = _docs(tmp_path)
    instance = OverworldGame(
        world=build_world(docs), save_path=tmp_path / "run.json", docs_root=docs
    )
    chigame.GameHost(instance, context, with_text=False, with_audio=False)
    instance.finish_loading()
    return instance


def test_overworld_weapon_attack(game):
    """Overworld weapon attack triggers cooldown, sparks, and cuts grass."""
    game.phase = "play"
    start_energy = game.energy
    assert game._attack_cooldown == 0.0

    game._attack_overworld()
    assert game._attack_cooldown > 0.0
    assert len(game.sparks) > 0
    assert game.energy >= start_energy


def test_overworld_beast_damage_and_knockback(game):
    """Weapon attacks deal overworld damage and knockback to beast NPCs."""
    game.phase = "play"
    pos = (game.player_pos[0] + 10.0, game.player_pos[1])
    beast = npcs_api.Npc(
        name="Wild Hare", kind="beast", x=pos[0], y=pos[1],
        home=pos, radius=20.0, line="..."
    )
    beast.hp = 60.0
    beast.max_hp = 60.0
    game.people.append(beast)
    game.facing = "right"
    # Unmarked: a marked animal is caught by the encounter battle now, not
    # damaged in place -- see _attack_overworld. This test is about the
    # damage path, so it is not left to the marked/unmarked roll.
    game._guardian_nm[(beast.species, int(beast.home[0]), int(beast.home[1]))] = 0.0

    game._attack_overworld()
    assert beast.hp < 60.0
    assert getattr(beast, "knockback_timer", 0.0) > 0.0


def test_a_marked_beast_is_caught_not_killed_in_real_time(game, monkeypatch):
    """A marked animal answers to the encounter battle, never to the blade.

    Real-time combat is for killing ordinary threats; a marked animal is
    what Unbind exists for, and that only happens inside the menu battle.
    Swinging at one has to open that battle rather than deleting it from the
    world for a flat reward and skipping capture entirely.
    """
    game.phase = "play"
    pos = (game.player_pos[0] + 10.0, game.player_pos[1])
    beast = npcs_api.Npc(
        name="Marked Hare", kind="beast", x=pos[0], y=pos[1],
        home=pos, radius=20.0, line="..."
    )
    beast.hp = 60.0
    beast.max_hp = 60.0
    game.people.append(beast)
    game.facing = "right"
    game._guardian_nm[(beast.species, int(beast.home[0]), int(beast.home[1]))] = 550.0

    called = []
    monkeypatch.setattr(game, "_try_encounter", lambda force=False: called.append(force))
    game._attack_overworld()

    assert called == [True], "the swing must open the catch battle, forced"
    assert beast.hp == 60.0, "a marked animal takes no real-time damage"
    assert beast in game.people, "and is never deleted from the world by a swing"


def test_overworld_magic_spells(game):
    """Casting magic spells consumes energy and triggers spell effects.

    Photons, specifically -- not story.unbound (labels taken off, ever), a
    permanent narrative counter scripts gate content on that a spendable
    cost used to corrupt on every cast.
    """
    game.phase = "play"
    game.energy = 100
    unbound_before = game.story.unbound

    # 1. Flame spell
    game.active_magic = "flame"
    game._cast_magic()
    assert game.energy == 90
    assert game._magic_cooldown > 0.0

    # Reset cooldown
    game._magic_cooldown = 0.0

    # 2. Heal spell
    game.active_magic = "heal"
    game._cast_magic()
    assert game.energy == 70

    # Reset cooldown
    game._magic_cooldown = 0.0

    # 3. Shield spell
    game.active_magic = "shield"
    game._cast_magic()
    assert game.energy == 55
    assert game._shield_timer > 0.0
    assert game.story.unbound == unbound_before, "casting must never touch it"


def test_weapon_and_magic_cycling(game):
    """Weapons and magic spells cycle correctly."""
    assert game.active_weapon == "sword"
    game._cycle_weapon()
    assert game.active_weapon == "lance"

    assert game.active_magic == "flame"
    game._cycle_magic()
    assert game.active_magic == "heal"


def test_a_beast_touching_iris_costs_real_hp(game):
    """The "-10 HP" popup used to be pure flavour text -- it costs her now."""
    game.phase = "play"
    beast = npcs_api.Npc(
        name="Wild Hare", kind="beast", x=game.player_pos[0], y=game.player_pos[1],
        home=(game.player_pos[0], game.player_pos[1]), radius=20.0, line="...",
    )
    game.people.append(beast)
    start_hp = game.player_vitality

    game._update_overworld_enemies(1 / 60)

    assert game.player_vitality == start_hp - 10


def test_iris_faints_when_her_hp_runs_out(game):
    """Fainting is a trip back to the spawn point, not a game over screen."""
    game.phase = "play"
    game.player_vitality = 1
    game.player_pos = [999999.0, 999999.0]  # nowhere near the spawn point
    beast = npcs_api.Npc(
        name="Wild Hare", kind="beast", x=game.player_pos[0], y=game.player_pos[1],
        home=(game.player_pos[0], game.player_pos[1]), radius=20.0, line="...",
    )
    game.people.append(beast)

    game._update_overworld_enemies(1 / 60)

    assert game.player_vitality == game.player_max_vitality // 2
    assert tuple(game.player_pos) == game.world.spawn()
