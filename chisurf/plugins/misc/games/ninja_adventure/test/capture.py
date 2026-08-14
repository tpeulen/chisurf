"""Drive the Ninja Adventure port headlessly and save a PNG gallery.

Same contract as the Lumis Quest capture harness: the real ``update`` and
``draw`` through :func:`chisurf.gui.chigame.capture`, every screen in a
deterministic state, written under ``test/renders/``.

Run::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python \\
        -m chisurf.plugins.misc.games.ninja_adventure.test.capture [out-dir]
"""

from __future__ import annotations

import pathlib
import sys

from qtpy.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from chisurf.gui import chigame  # noqa: E402
from chisurf.gui.chigame.input import Action  # noqa: E402

from chisurf.plugins.misc.games.ninja_adventure import NinjaAdventure  # noqa: E402


def capture(out: pathlib.Path, name: str, arrange, frames: int = 3,
            size: tuple[int, int] = (640, 384)) -> NinjaAdventure:
    """Render one screen.

    Parameters
    ----------
    out : pathlib.Path
        Where the PNG goes.
    name : str
        File stem.
    arrange : callable
        ``arrange(game)``, run once the game is playing, to set the state.
    frames : int, optional
        Frames to advance.
    size : tuple of int, optional
        Pixel size.

    Returns
    -------
    NinjaAdventure
        The game, for callers that want to assert on it.
    """
    game = NinjaAdventure()

    def script(index, host):
        if index == 0:
            host.keys.press(Action.CONFIRM)
            host.keys.release(Action.CONFIRM)
            arrange(game)

    image = chigame.capture(game, size=size, frames=frames, script=script)
    chigame.save_png(image, out / f"{name}.png")
    return game


def main(argv: list[str]) -> int:
    """Write the gallery.

    Parameters
    ----------
    argv : list of str
        Optional output directory.

    Returns
    -------
    int
        Exit status.
    """
    out = pathlib.Path(argv[0]) if argv else pathlib.Path("renders")
    out.mkdir(parents=True, exist_ok=True)

    capture(out, "ninja_title", lambda game: None, frames=2)

    capture(out, "ninja_village", lambda game: game.camera.snap_to(game.player.position),
            frames=90)

    def crate(game):
        crate = next(d for d in game.destroyables if d.alias == "crate")
        game.player.position[:] = crate.position[0], crate.position[1] - 13.0
        game.player.velocity[:] = 0.0
        game.camera.snap_to(game.player.position)

    game = capture(out, "ninja_crate", crate, frames=1)
    # The swing, one frame in: club out, crate whole.
    game.player_weapon.swing()
    game.player.attack()
    game.player_weapon.update(0.01, game.player)

    def broke(game):
        crate = next(d for d in game.destroyables if d.alias == "crate")
        crate.take_damage(
            __import__("chisurf.gui.chigame.actors", fromlist=["Damage"]).Damage(1.0),
            crate.position,
        )
        crate.update(0.1)
        game.player.position[:] = crate.position[0], crate.position[1] - 13.0
        game.camera.snap_to(game.player.position)

    capture(out, "ninja_crate_broken", broke, frames=6)

    def swamp(game):
        enemy = game.enemies[0]
        game.player.position[:] = game._free_spot(*enemy.position + (0.0, 26.0))
        game.player.velocity[:] = 0.0
        game.camera.snap_to(game.player.position)

    game = capture(out, "ninja_swamp", swamp, frames=45)

    def storm(game):
        area = next(env for env in game._environments if env["meteo"])
        x0, y0, x1, y1 = area["rect"]
        game.player.position[:] = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        game.camera.snap_to(game.player.position)

    capture(out, "ninja_weather", storm, frames=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
