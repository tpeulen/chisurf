"""Guide 102: MMFDB Admin after Import / Export → Demo data… (headless emtk, temporary database).

Seeds a temporary MMFDB with the plugin's test fixture (:mod:`seeded_admin`), opens the
**Import / Export** panel of the native MMFDB Admin, presses **Demo data…**, answers the
confirmation, and writes ``docs/guides/figures/102_mmfdb_demo_result.png``. Read the PNG afterwards.

Run from the repository root (nothing touches ``~/.chisurf``; the database lives in a temp folder)::

    IMP_BFF_GPU=off python docs/guides/screenshots/mmfdb_admin_demo_shot.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402


def main() -> None:
    """Populate the demo data through the window and save the frame."""
    from chisurf.plugins.core.mmfdb_admin.test import seeded_admin as sa

    folder = sa.use_folder(pathlib.Path(tempfile.mkdtemp()) / "mmfdb")
    sa.seed(folder, sa.admin_client())

    from emtk.testing import Driver

    from chisurf.plugins.core.mmfdb_admin.gui.app import MMFDBAdminApp
    from chisurf.plugins.core.mmfdb_admin.gui.native.runner import InlineRunner

    app = MMFDBAdminApp(client=sa.admin_client(), runner=InlineRunner())
    app.model.user = "admin"
    driver = Driver(app, (1200, 800))
    driver.frame(3)
    panel = app.model.select("import_export")
    driver.frame(2)
    panel.populate_demo()
    driver.frame(2)
    app.model.dialog.yes()  # the confirmation the action asks first
    driver.frame(6)
    print(app.model.status, flush=True)
    driver.screenshot(FIG / "102_mmfdb_demo_result.png")
    print("wrote 102_mmfdb_demo_result.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
