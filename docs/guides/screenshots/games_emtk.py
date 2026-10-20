"""The Breakout figure of docs/guides/95_games.md, rendered headlessly by emtk.

Run from the repository root::

    python docs/guides/screenshots/games_emtk.py

It opens Breakout (Tools › Games › Breakout, a window of its own), launches the ball and lets it
fly for about a second of real time, then writes ``docs/guides/figures/games_breakout.png`` at
820x690 (the game's declared window), and ``docs/guides/figures/games_ribbon.png``: the shell's
Tools tab with its Games group.
"""

import os
import pathlib
import sys
import tempfile
import time

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="games_shot_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from docs.guides.screenshots.emtk_shot import FIG, render  # noqa: E402


def breakout():
    """Render games_breakout.png."""
    from emtk.testing import Driver

    from chisurf.plugins.misc.games.breakout.app import make_app

    game = make_app()
    driver = Driver(game, (820, 690))
    driver.settle()
    driver.frame(3)
    game.model.launch() if hasattr(game, "model") else game.game.launch()
    end = time.monotonic() + 1.2
    while time.monotonic() < end:
        driver.frame()
        time.sleep(0.016)
    render(game, "games_breakout.png", driver=driver)
    game.close()


def ribbon():
    """Render games_ribbon.png: the Tools tab, where Games is a group of five buttons."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp(loader=lambda plugin_id: None, console_history=False, console_session_file=False)
    driver = RealisticDriver(shell, (1440, 900), real_painter=True)
    driver.frame(3)
    driver.click("ribbon.tab.Tools")
    driver.frame(3)
    driver.click("ribbon.group.Tools.Games")
    driver.frame(4)
    driver.screenshot(FIG / "games_ribbon.png")
    print("wrote games_ribbon.png", flush=True)
    shell.close()


def main():
    """Render both figures."""
    breakout()
    ribbon()


if __name__ == "__main__":
    main()
