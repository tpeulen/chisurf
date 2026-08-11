"""Drive the game headlessly and save a PNG of every screen worth looking at.

The project rule is that a GUI is unfinished until somebody has *looked* at it,
and a screenshot nobody can reproduce is a screenshot nobody can re-take when
the code moves. This is that harness: it runs the real ``update`` and ``draw``
through :func:`chisurf.gui.chigame.capture`, drives each screen into a realistic
state, and writes the gallery under ``test/renders/``.

Run it with the project environment on the path::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python \\
        -m chisurf.plugins.misc.games.lumis_quest.test.capture <output-dir>

Every scene sets its own state up front rather than being walked into over
hundreds of frames: a capture that depends on the town's day having gone a
particular way is a capture that changes every time somebody re-tunes a drive.
"""

from __future__ import annotations

import pathlib
import sys

#: The one thing that has to exist before chigame is imported.
from qtpy.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from chisurf.gui import chigame  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import agents  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import battle as battle_api  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import bestiary  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api import npcs as agents_npcs  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.api.world import build_world  # noqa: E402
from chisurf.plugins.misc.games.lumis_quest.gui.overworld import (  # noqa: E402
    OverworldGame,
)

#: World units per tile, spelled out so the arrangements below read as tiles.
TILE = 18.0


def capture(out: pathlib.Path, world, name: str, arrange, frames: int = 3,
            size: tuple[int, int] = (960, 540)):
    """Render one screen.

    Parameters
    ----------
    out : pathlib.Path
        Where the PNG goes.
    world : chisurf.plugins.misc.games.lumis_quest.api.world.World
        A prebuilt world, shared across shots so the corpus is only read once.
    name : str
        File stem.
    arrange : callable
        ``arrange(game)``, run once the game has finished loading, to put it
        into the state being photographed.
    frames : int, optional
        Frames to advance. More lets an animation settle.
    size : tuple of int, optional
        Pixel size.

    Returns
    -------
    OverworldGame
        The game, in case the caller wants to assert something about it.
    """
    game = OverworldGame(world=world, save_path=out / "capture-run.json")

    def script(index, host):
        if index == 0:
            game.finish_loading(skip_prologue=True)
            arrange(game)

    image = chigame.capture(game, size=size, frames=frames, script=script)
    chigame.save_png(image, out / f"{name}.png")
    return game


def _stand_in(game, warden: bool = False, which: int = 0):
    """Put Iris in the middle of a settlement.

    Parameters
    ----------
    game : OverworldGame
        The running game.
    warden : bool, optional
        Pick a Warden's seat rather than an ordinary settlement.
    which : int, optional
        Which one.

    Returns
    -------
    Village
        Where she is standing.
    """
    villages = [v for v in game.world.villages if bool(v.warden) is warden]
    village = villages[which % len(villages)]
    col, row, width, height = village.rect
    game.iris = [(col + width / 2) * TILE, (row + height * 0.62) * TILE]
    game.host.camera.center[:] = game.iris
    return village


def _pair_up(game, village):
    """Put two townsfolk of one settlement face to face.

    Parameters
    ----------
    game : OverworldGame
        The running game.
    village : Village
        Whose people.

    Returns
    -------
    tuple or None
        The two minds, or ``None`` when the settlement has fewer than two.
    """
    here = [mind for mind in game.society.minds
            if game.world.village_at(mind.npc.x, mind.npc.y) is village]
    if len(here) < 2:
        return None
    one, two = here[0], here[1]
    two.npc.x, two.npc.y = one.npc.x + 14.0, one.npc.y
    return one, two


def main(argv: list[str]) -> int:
    """Write the whole gallery.

    Parameters
    ----------
    argv : list of str
        Command line; the first entry is the output directory.

    Returns
    -------
    int
        Process exit status.
    """
    out = pathlib.Path(argv[0] if argv else "renders")
    out.mkdir(parents=True, exist_ok=True)
    world = build_world()

    def country(game):
        col, row, width, height = game.world.regions[0].rect
        game.iris = [(col + width * 0.5) * TILE, (row + height * 0.5) * TILE]
        game.host.camera.center[:] = game.iris
        game.view_height = 380.0

    capture(out, world, "lumis_country", country)
    capture(out, world, "lumis_town", lambda game: _stand_in(game))

    def wilds(game):
        """Open country, run on long enough that the wildlife has steered.

        Three frames is enough to prove a creature was *drawn*; it is not
        enough to prove it can move without ending up inside a rock. This one
        runs for several seconds of game time so that everything on screen has
        taken twenty-odd decisions and is standing wherever those put it -- and
        with Iris in the middle of them, so what is on screen is a beast's
        answer to being approached.
        """
        beast = min(
            (one for one in game.people if one.kind == "beast"),
            key=lambda one: abs(one.x) + abs(one.y), default=None,
        )
        if beast is not None:
            game.iris = [beast.x, beast.y + TILE * 3.0]
        game.host.camera.center[:] = game.iris
        game.view_height = 300.0

    capture(out, world, "lumis_wilds", wilds, frames=240)

    def seat(game):
        _stand_in(game, warden=True)
        game.view_height = 560.0

    capture(out, world, "lumis_warden_town", seat)
    capture(out, world, "lumis_overworld_map",
            lambda game: setattr(game, "show_map", True), frames=40)

    def fight(game):
        game.battle = battle_api.Battle(
            game.team,
            battle_api.wild_encounter("docs/guides/x.md", 0.7, game.pool,
                                      terrain=bestiary.WOOD, tier_cap=3),
            loadout=game.loadout, seals={"ember", "prism"},
        )
        game.battle.attack()

    capture(out, world, "lumis_battle", fight)

    def warden(game):
        npc = next(one for one in game.people if one.kind == "warden")
        game.iris = [npc.x, npc.y + 12.0]
        game.host.camera.center[:] = game.iris
        game._talk_to(npc)
        for _ in range(3):
            game.screen = game.runner.advance()

    capture(out, world, "lumis_warden", warden)

    def dark(game):
        col, row, width, height = game.world.regions[0].rect
        game.iris = [(col + width * 0.5) * TILE, (row + height * 0.5) * TILE]
        game.host.camera.center[:] = game.iris
        game._cross("dark")

    # Long enough for the shelved to have drifted and to be mid-hover, which is
    # the only way to see that the bob lifts the drawing and not the shadow.
    capture(out, world, "lumis_dark", dark, frames=150)

    def shelved(game):
        """The dark manifold, with the shelved actually on screen.

        The generic dark shot puts Iris wherever the region's middle happens to
        be, and whether a wraith is in frame is luck. This one goes to them, so
        the hover is something that can be *looked* at rather than something a
        unit test asserts about a float.
        """
        dark(game)
        # Screen mode holds the camera on the 16x14 screen Iris is standing in,
        # so moving her does not move the view. For a close look the follow
        # camera has to come back on, or the subject ends up behind the HUD.
        game.screen_mode = False
        game.view_height = 150.0
        found = [one for one in game.people if one.kind == "wraith"]
        for offset, one in enumerate(found[:3]):
            one.x = game.iris[0] + (offset - 1) * TILE * 1.6
            one.y = game.iris[1] - TILE * 1.6
            one.home = (one.x, one.y)
        game.host.camera.center[:] = game.iris

    capture(out, world, "lumis_shelved", shelved, frames=90)

    def party(game):
        game.labels.extend(game.pool[:3])
        game.bodies.extend([bestiary.BY_KEY["heron"], bestiary.BY_KEY["boar"]])
        game.menu_open = True
        game.menu_tab = game.TABS.index("PARTY")

    capture(out, world, "lumis_party", party)

    def tavern(game):
        npc = next(one for one in game.people if one.role == "tavern")
        game.iris = [npc.x, npc.y + 12.0]
        game.host.camera.center[:] = game.iris
        game._talk_to(npc)
        for _ in range(2):
            game.screen = game.runner.advance()

    capture(out, world, "lumis_tavern", tavern)

    def gossip(game):
        village = _stand_in(game, warden=True)
        game.society.mood = {"marking": 6.0}
        pair = _pair_up(game, village)
        if pair is not None:
            game.society.begin(*pair, topic="marking")
            game.iris = [pair[0].npc.x - 6.0, pair[0].npc.y + 40.0]
            game.host.camera.center[:] = game.iris
        game.view_height = 260.0

    capture(out, world, "lumis_gossip", gossip)

    def joining(game):
        village = _stand_in(game, warden=True)
        pair = _pair_up(game, village)
        if pair is None:
            return
        game.society.begin(*pair, topic="probe")
        game.iris = [pair[0].npc.x + 6.0, pair[0].npc.y + 16.0]
        game.host.camera.center[:] = game.iris
        game._overhear()

    capture(out, world, "lumis_joinin", joining)

    def tower(game):
        """At the door of the only built thing in the dark manifold."""
        game._cross("dark")
        game.people = agents_npcs.dark_population(game.world)
        vesper = next((one for one in game.people
                       if one.kind == "lanternwright"), None)
        if vesper is None:
            return
        game.iris = [vesper.x, vesper.y + 26.0]
        game.host.camera.center[:] = game.iris
        game.story.choose("discovery")
        game._talk_to(vesper)
        for _ in range(3):
            game.screen = game.runner.advance()

    capture(out, world, "lumis_tower", tower)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
