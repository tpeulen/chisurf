"""FRET docking screenshot (guide 88): three docking runs of the shipped HIV-RT example.

The native emtk FRET window (Docking & Screening selected), driven headlessly: **Load example**,
Runs 3, Iterations 60, **Run**, wait for the three runs, write ``figures/88_docking_results.png``.
Run from the repository root with ``CHISURF_SETTINGS_DIR`` pointing at a scratch folder::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=docs/guides:. python docs/guides/screenshots/fret_docking_emtk.py
"""

from __future__ import annotations

import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver  # noqa: E402
from screenshots.emtk_shot import FIG  # noqa: E402

SIZE = (1200, 800)


def main() -> None:
    """Write 88_docking_results.png."""
    from chisurf.plugins.modelling.fret.gui.app import make_app

    app = make_app()
    driver = Driver(app, SIZE)
    driver.frame(3)
    app.select("Docking & Screening")
    card = app.children["Docking & Screening"]
    assert card.load_example(), "the example did not load"
    card.session.n_repeats = 3
    card.session.n_frames = 60
    card.run()
    end = time.monotonic() + 1800
    while card.session.running and time.monotonic() < end:
        time.sleep(0.1)
        driver.frame()
    assert not card.session.running, "docking did not finish"
    driver.frame(4)
    driver.screenshot(FIG / "88_docking_results.png")
    print("wrote 88_docking_results.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
