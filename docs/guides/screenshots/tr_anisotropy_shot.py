"""Guide 10: the Anisotropy Wizard on its built-in example (headless emtk, no Qt).

Presses **Load example** (four simulated VV/VH text decays: one 4 ns lifetime, one 2 ns rotation,
r0 0.38), then **Load / reload data**, and writes three steps of the wizard to
``docs/guides/figures/``: ``tr_anisotropy_data.png`` (Data), ``tr_anisotropy_normalize.png``
(Normalize IRF) and ``tr_anisotropy_components.png`` (Components). Read the PNGs afterwards.

Run from the repository root::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) python docs/guides/screenshots/tr_anisotropy_shot.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402


def main() -> None:
    """Walk the example through Data, Normalize IRF and Components and save each step."""
    from emtk.testing import Driver

    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import AnisotropyApp

    app = AnisotropyApp()
    app.model.example_folder = pathlib.Path(tempfile.mkdtemp())
    driver = Driver(app, (1200, 800))
    driver.frame(2)
    app.select_step(1)
    app.load_example()
    driver.frame(4)
    driver.screenshot(FIG / "tr_anisotropy_data.png")
    app.select_step(2)
    app.model.load_data()
    driver.frame(4)
    driver.screenshot(FIG / "tr_anisotropy_normalize.png")
    app.select_step(4)
    driver.frame(4)
    driver.screenshot(FIG / "tr_anisotropy_components.png")
    print(app.model.status, flush=True)
    print("wrote tr_anisotropy_{data,normalize,components}.png", flush=True)


if __name__ == "__main__":
    main()
