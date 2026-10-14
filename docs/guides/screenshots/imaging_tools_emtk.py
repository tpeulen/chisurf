"""The Image Tools hub figure of docs/guides/98_imaging_tools.md, rendered headlessly by emtk.

Run from the repository root::

    IMP_BFF_GPU=off python docs/guides/screenshots/imaging_tools_emtk.py

The hub runs on a scratch settings folder with a one-detector setup on routing channel 1 (where the
Leica scan records its photons). It hands a copy of
``test/data/clsm/Leica_SP8.ptu`` to the pipeline as the photon source, opens **1. Intensity**, waits
for the background precompute (Intensity, N&B, Mean Micro-Time, Phasor) to finish and writes
``docs/guides/figures/imaging_tools.png`` at 1200x800.
"""

import os
import pathlib
import shutil
import sys
import tempfile
import time

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="imaging_tools_shot_"))
REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from docs.guides.screenshots.emtk_shot import app_from, render  # noqa: E402

SOURCE = REPO / "test" / "data" / "clsm" / "Leica_SP8.ptu"


def main():
    """Render imaging_tools.png."""
    from emtk.testing import Driver

    work = pathlib.Path(tempfile.mkdtemp(prefix="imaging_tools_data_"))
    source = work / SOURCE.name
    shutil.copy(SOURCE, source)
    hub = app_from("imaging_tools")
    driver = Driver(hub, (1200, 800))
    driver.settle()
    # The Leica SP8 scan records its photons on routing channel 1 (and markers on 15): a setup with
    # that one detector, as Setup would publish it. The default setup's channels are empty here.
    hub.set_setup(
        {
            "detectors": {"green": {"chs": [1], "micro_time_ranges": [[0, 32767]]}},
            "windows": {},
            "tttr_reading": {"file_type": "PTU"},
        }
    )
    hub.goto_role("pixel_intensity")
    driver.frame(3)
    hub.set_pipeline(source=str(source))
    end = time.monotonic() + 600
    while hub.precompute_pending() or hub._precomputing:
        if time.monotonic() > end:
            raise TimeoutError("background precompute did not finish")
        driver.frame()
        time.sleep(0.05)
    hub.goto_role("pixel_intensity")
    driver.settle()
    driver.frame(6)
    print(hub.status)
    render(hub, "imaging_tools.png", driver=driver)
    hub.close()


if __name__ == "__main__":
    main()
