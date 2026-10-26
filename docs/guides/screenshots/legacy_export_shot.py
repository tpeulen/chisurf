"""Guide 34: the Legacy Export window after unpacking a container (headless emtk).

``main`` opens the plugin's own demonstration container
(:func:`chisurf.plugins.core.legacy_export.demo.make_demo`: the Burst Selection demo
stream with 12 planted bursts, the burst-search run ``burstwise`` and the BVA run
``bva``) and writes two figures into ``docs/guides/figures``:

* ``34_legacy_export_folder.png`` -- after **Export burst folder**:
  ``burstwise/bi4_bur/bs_demo.bur`` plus the companion ``bv4/bs_demo.bv4``;
* ``34_legacy_export_alex.png`` -- after **Write ALEX-Suite CSVs** on the run
  ``burstwise``: the four default CSV files.

Read both PNGs afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/legacy_export_shot.py
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402

SIZE = (1000, 470)


def legacy_export_figures() -> None:
    """The window after the burst folder, then after the ALEX-Suite CSVs."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.plugins.core.legacy_export import demo
    from chisurf.plugins.core.legacy_export.gui.app import make_app

    work = pathlib.Path(tempfile.mkdtemp(prefix="legacy_export_", dir="/tmp"))
    try:
        container = demo.make_demo(work / "data")

        app = make_app()
        driver = RealisticDriver(app, SIZE, real_painter=True)
        driver.frame(3)
        driver.drop_files([container], (400, 200))
        assert app.model.filename == str(container), app.model.filename
        app.model.out_folder = str(work / "legacy")
        driver.frame(2)
        driver.click("export")
        driver.frame(3)
        written = [pathlib.Path(p) for p in app.model.written]
        assert any(p.suffix == ".bur" for p in written), written
        assert any(p.suffix == ".bv4" for p in written), written
        driver.screenshot(FIG / "34_legacy_export_folder.png")
        print("wrote 34_legacy_export_folder.png", flush=True)

        app.model.sample = "demo bursts"
        app.model.buffer = "PBS"
        driver.frame(1)
        driver.click("write_alex")
        driver.frame(3)
        assert "4 ALEX-Suite CSV" in app.model.status, app.model.status
        driver.screenshot(FIG / "34_legacy_export_alex.png")
        print("wrote 34_legacy_export_alex.png", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    """Draw the two figures."""
    legacy_export_figures()


if __name__ == "__main__":
    main()
