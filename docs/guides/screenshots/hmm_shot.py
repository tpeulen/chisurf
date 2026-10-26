"""Guide 92: the Hidden Markov model tool on its example trace (headless emtk).

``main`` writes ``hmm_window.png`` into ``docs/guides/figures``: after **Load example** (the
generated three-state, two-channel trace), a state scan from one to five and a fit with three
states -- the trace with the decoded path, the fitted states with the transition matrix, and the
summed-count histogram with the fitted emission densities.

Read the PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/hmm_shot.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402


def _finish(driver, app, timeout: float = 120.0) -> None:
    """Draw frames until the tool's background job is done."""
    end = time.monotonic() + timeout
    driver.frame(2)
    while app.job.busy and time.monotonic() < end:
        time.sleep(0.05)
        driver.frame(1)
    driver.frame(4)
    if app.job.error:
        raise RuntimeError(app.job.error)


def main() -> None:
    """Load the example, scan 1-5 states, fit three; one figure."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.hmm.gui.app import make_app

    app = make_app()
    driver = RealisticDriver(app, (1200, 800), real_painter=True)
    driver.frame(3)
    app.on_demo()
    model = app.model
    model.min_states, model.max_states = 1, 5
    app.start("run_scan")
    _finish(driver, app)
    model.n_states = 3
    app.start("run")
    _finish(driver, app)
    driver.screenshot(FIG / "hmm_window.png")
    print("wrote hmm_window.png", flush=True)


if __name__ == "__main__":
    main()
