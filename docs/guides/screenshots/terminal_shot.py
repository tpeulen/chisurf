"""Guide 110 and guide 59: the Terminal app, its Python panes, and the Console dock (headless emtk).

``main`` writes three figures into ``docs/guides/figures``:

* ``110_terminal_panes.png`` -- the **Terminal** plugin on its own: a shell pane (``bash --norc``,
  prompt ``$``) that listed the plugin's package, split side by side with a Python pane that
  evaluated ``cs.__name__`` and ``np.arange(5) ** 2``;
* ``110_python_terminal.png`` -- the **Python Terminal** plugin on its own: a Python pane that read a
  value, split stacked with a second Python pane;
* ``console_dock.png`` -- the emtk shell with its **Console** dock in front: the Terminal app's
  strip (*New*, *Terminal*, *Python*, the two splits, *Close*, *Guide*, ``?``) over the shell's own
  Python pane after ``2 + 40``.

Read every PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/terminal_shot.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, REPO  # noqa: E402

#: A shell whose prompt does not carry the user's name, host or dotfiles.
os.environ["CHISURF_TERMINAL_SHELL"] = "/bin/bash --norc --noprofile -i"
os.environ["PS1"] = "$ "
os.environ["BASH_SILENCE_DEPRECATION_WARNING"] = "1"
os.chdir(REPO)


def _pump(driver, seconds: float) -> None:
    """Draw frames for *seconds* of wall time (a PTY child answers asynchronously)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(0.03)
        driver.frame(1)


def _type_line(driver, text: str) -> None:
    from emtk.keys import KEY_RETURN

    driver.type(text)
    driver.frame(1)
    driver.press(KEY_RETURN)
    # A Python cell runs on its console's worker: wait for it, so the figure shows its output.
    app = driver.app
    if hasattr(app, "_python_consoles"):
        consoles = app._python_consoles()
    else:
        panes = getattr(getattr(app, "workspace", None), "panes", {})
        consoles = [pane.console for pane in panes.values() if pane.kind == "python"]
    for console in consoles:
        console.wait(timeout=30.0)
    driver.frame(2)


def terminal_panes() -> None:
    """Terminal standalone: a shell pane split side by side with a Python pane."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.terminal.app import make_app

    app = make_app()
    driver = RealisticDriver(app, (1200, 560), real_painter=True)
    _pump(driver, 1.5)
    _type_line(driver, "ls chisurf/plugins/core/terminal")
    _pump(driver, 1.0)
    app.split_pane("right", "python")
    driver.frame(3)
    _type_line(driver, "cs.__name__")
    _type_line(driver, "np.arange(5) ** 2")
    _pump(driver, 0.5)
    driver.screenshot(FIG / "110_terminal_panes.png")
    print("wrote 110_terminal_panes.png", flush=True)
    app.close()


def python_terminal() -> None:
    """Python Terminal standalone: two Python panes, stacked."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.terminal.app import make_console_app

    app = make_console_app()
    driver = RealisticDriver(app, (1000, 620), real_painter=True)
    driver.frame(4)
    _type_line(driver, "x = np.linspace(0, 1, 5)")
    _type_line(driver, "x.mean()")
    app.split_pane("down")
    driver.frame(3)
    _type_line(driver, "len(cs.fits)")
    _pump(driver, 0.5)
    driver.screenshot(FIG / "110_python_terminal.png")
    print("wrote 110_python_terminal.png", flush=True)
    app.close()


def console_dock() -> None:
    """The emtk shell's Console dock: the Terminal app hosting the shell's console."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp(
        loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )
    driver = RealisticDriver(shell, (1440, 900), real_painter=True)
    driver.frame(4)
    shell.docks.focus("console")
    shell.console.focus_input()
    driver.frame(3)
    _type_line(driver, "2 + 40")
    _pump(driver, 0.5)
    driver.screenshot(FIG / "console_dock.png")
    print("wrote console_dock.png", flush=True)
    shell.close()


def main() -> None:
    """Draw the three figures."""
    terminal_panes()
    python_terminal()
    console_dock()


if __name__ == "__main__":
    main()
