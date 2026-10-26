"""Guide 112: the FRET check on its own simulated PIE example (headless emtk).

``main`` writes four figures into ``docs/guides/figures``:

* ``112_fret_check_quality.png`` -- simple mode after *Simulate* on the ``PIE 2c`` example: the
  Measurement window (detected experiment) beside the Quality window (checks, 1 s count-rate
  trace, inter-burst gaps);
* ``112_fret_check_es.png`` -- the same run, the E / S window in front;
* ``112_fret_check_channels.png`` -- advanced mode: the Channels window (detected donor/acceptor
  channels, Dex/Aex windows, the micro-time histogram of every detector) beside the Bursts window;
* ``112_fret_check_trace.png`` -- advanced mode: the Corrections window (factors, *Subtract
  background*) beside the Time trace, every burst shaded on its own.

Read every PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/fret_check_shot.py
"""

from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, REPO  # noqa: E402

os.chdir(REPO)

#: The simulated example every figure shows: two-colour PIE with acceptor-only molecules.
EXAMPLE = "PIE 2c"
SIZE = (1400, 860)


def main() -> None:
    """Simulate the example, then draw the simple- and advanced-mode figures."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.burst.fret_check.app.frame import make_app

    app = make_app(runner="sync")
    s = app.session
    s.demo = EXAMPLE
    s.simulate()
    s.wait()
    driver = RealisticDriver(app, SIZE, real_painter=True)
    driver.frame(4)

    app.docks.focus("quality")
    driver.frame(4)
    driver.screenshot(FIG / "112_fret_check_quality.png")
    print("wrote 112_fret_check_quality.png", flush=True)

    app.docks.focus("es")
    driver.frame(4)
    driver.screenshot(FIG / "112_fret_check_es.png")
    print("wrote 112_fret_check_es.png", flush=True)

    s.mode = "advanced"
    driver.frame(3)
    app.docks.focus("channels")
    app.docks.focus("bursts")
    driver.frame(4)
    driver.screenshot(FIG / "112_fret_check_channels.png")
    print("wrote 112_fret_check_channels.png", flush=True)

    app.docks.focus("corrections")
    app.docks.focus("trace")
    driver.frame(4)
    driver.screenshot(FIG / "112_fret_check_trace.png")
    print("wrote 112_fret_check_trace.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
