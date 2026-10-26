"""Guide 114: the Project data window on its demonstration project (headless emtk).

``main`` writes two figures into ``docs/guides/figures``:

* ``114_project_data_located.png`` -- after **Load example** and a folder search: the moved file
  ``c`` is listed missing, the two candidates of that name below it, the one with the recorded
  size first;
* ``114_project_data_self_contained.png`` -- after **Use candidate**, **Make self-contained** and
  **Save project**: every dataset embedded, the project needs no other file.

Read every PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/project_data_shot.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG  # noqa: E402


def _click(driver, app, name: str) -> None:
    driver.frame(2)
    x, y, w, h = app.form.rects[name]
    driver.click((x + w / 2, y + h / 2))
    driver.frame(2)


def _settle(driver, app, timeout: float = 30.0) -> None:
    end = time.monotonic() + timeout
    driver.frame(1)
    while app.model.busy and time.monotonic() < end:
        time.sleep(0.02)
        driver.frame(1)
    driver.frame(2)


def main() -> None:
    """Locate the moved file, make the project self-contained, save; two figures."""
    from emtk.testing_realistic import RealisticDriver

    import chisurf.plugins.core.project_data.gui.app as project_data_app

    project_data_app.session_source = lambda: None  # the demonstration project, not a live session
    app = project_data_app.ProjectDataApp()
    driver = RealisticDriver(app, (980, 700), real_painter=True)
    _click(driver, app, "load_example")
    model = app.model
    backup = model.source.path.parent.parent / "backup"
    app._start({"search": lambda: model.search(backup)})  # the folder dialog's answer
    _settle(driver, app)
    driver.screenshot(FIG / "114_project_data_located.png")
    print("wrote 114_project_data_located.png", flush=True)
    _click(driver, app, "use_candidate")
    _click(driver, app, "make_self_contained")
    _settle(driver, app)
    _click(driver, app, "save_project")
    driver.frame(3)
    driver.screenshot(FIG / "114_project_data_self_contained.png")
    print("wrote 114_project_data_self_contained.png", flush=True)


if __name__ == "__main__":
    main()
