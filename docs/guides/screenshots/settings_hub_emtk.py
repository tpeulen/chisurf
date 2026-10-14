"""The Settings window figures of docs/guides/97_settings_hub.md, rendered headlessly by emtk.

Run from the repository root::

    IMP_BFF_GPU=off python docs/guides/screenshots/settings_hub_emtk.py

The hub runs on a scratch settings folder (CHISURF_SETTINGS_DIR). It grabs the first destination
(Getting Started), then ChiSurf Settings and Acquisition, each at 1200x800.
"""

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="settings_hub_shot_"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from docs.guides.screenshots.emtk_shot import render  # noqa: E402

SHOTS = (
    ("boarding", "97_settings_getting_started.png"),
    ("chisurf", "97_settings_chisurf.png"),
    ("acq", "97_settings_acquisition.png"),
)


def main():
    """Render the three Settings figures."""
    from emtk.testing import Driver

    from chisurf.plugins.core.setup.gui.app import make_app

    hub = make_app(settings_dir=os.environ["CHISURF_SETTINGS_DIR"])
    driver = Driver(hub, (1200, 800))
    for key, name in SHOTS:
        hub.select(key)
        driver.settle()
        driver.frame(6)
        render(hub, name, driver=driver)
    hub.close()


if __name__ == "__main__":
    main()
