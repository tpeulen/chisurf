"""The Games hub figure of docs/guides/95_games.md, rendered headlessly by emtk.

Run from the repository root::

    python docs/guides/screenshots/games_emtk.py

It opens the hub, selects Breakout, launches the ball and lets it fly for about a second of real
time, then writes ``docs/guides/figures/games_breakout.png`` at 1200x800.
"""

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="games_shot_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from docs.guides.screenshots.emtk_shot import render  # noqa: E402


def main():
    """Render games_breakout.png."""
    from emtk.testing import Driver

    from chisurf.plugins.misc.games.gui.app import make_app

    hub = make_app()
    driver = Driver(hub, (1200, 800))
    driver.settle()
    game = hub.select("Breakout")
    driver.frame(3)
    game.model.launch() if hasattr(game, "model") else game.game.launch()
    end = time.monotonic() + 1.2
    while time.monotonic() < end:
        driver.frame()
        time.sleep(0.016)
    render(hub, "games_breakout.png", driver=driver)
    hub.close()


if __name__ == "__main__":
    main()
