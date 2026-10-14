"""Image Browser screenshots (guide 86): the mosaic of a Leica SP8 scan, then zoomed in.

The native emtk app, driven headlessly the way a person does (folder dropped, row clicked, a
rating, an annotation typed, wheel notches over the image) and written to ``figures/``. Run from
the repository root with ``CHISURF_SETTINGS_DIR`` pointing at a scratch folder::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=docs/guides:. python docs/guides/screenshots/image_browser_emtk.py
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver as ShotDriver  # noqa: E402
from screenshots.emtk_shot import FIG  # noqa: E402

SIZE = (1200, 800)
DATA = REPO / "test" / "data" / "clsm"

#: Two detectors over the routing channels of the Leica files (SP8 has channel 1, SP5 0 to 2).
SETUP = {
    "windows": {"all": [0, 4095]},
    "detectors": {
        "green": {
            "chs": [0, 1],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
        "red": {
            "chs": [2],
            "micro_time_ranges": [[0, 4095]],
            "g_factor": 1.0,
            "l1": 0.0,
            "l2": 0.0,
        },
    },
    "tttr_reading": {
        "file_type": "PTU",
        "macro_time_resolution": 50.0,
        "micro_time_resolution": 16.0,
        "micro_time_binning": 1,
        "effective_micro_time_resolution": 16.0,
        "excitation_period": 50.0,
    },
    "setup_name": "",
    "apply_lut": False,
    "polarization_resolved": True,
    "channel_luts": {},
    "channel_shifts": {},
}


def _settle(drv, app, timeout=180.0):
    """Draw until the scan and mosaic workers are done."""
    end = time.monotonic() + timeout
    drv.draw(2)
    while (
        app.job.busy or app.load_job.busy or app._queue or app.model.wanted_image()
    ) and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    drv.draw(3)


def main() -> None:
    """Write image_browser_mosaic.png and image_browser_zoomed.png."""
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    work = pathlib.Path(tempfile.mkdtemp(prefix="image_browser_shot_")) / "imgs"
    (work / "sub").mkdir(parents=True)
    shutil.copy2(DATA / "Leica_SP8.ptu", work / "Leica_SP8.ptu")
    shutil.copy2(DATA / "Leica_SP5.ptu", work / "sub" / "Leica_SP5.ptu")

    app = make_app()
    drv = Driver(app, SIZE)
    app.model.apply_setup_settings(ChannelDefinition(SETUP).get_settings())
    drv.drop(str(work))
    _settle(drv, app)
    x, y, w, h = drv.text_rect("Leica_SP8.ptu")
    drv.hover(x + w / 2, y + h / 2)
    drv.click_text("Leica_SP8.ptu")
    _settle(drv, app)
    drv.click("current_rating.2")  # two stars
    box = drv.rect("annotation")
    drv.click_at(box[0] + 20, box[1] + 15)
    drv.type_text("good cell, bleached after frame 3")
    drv.hover(6.0, SIZE[1] - 6.0)
    _settle(drv, app)
    ShotDriver(app, SIZE).screenshot(FIG / "image_browser_mosaic.png")
    print("wrote image_browser_mosaic.png", flush=True)

    ix, iy, iw, ih = app.item_rects["image"]
    cx, cy = ix + iw * 0.3, iy + ih * 0.5
    for _ in range(6):
        drv.wheel(cx, cy, 1)
    drv.drag((cx, cy), (cx + 60, cy - 20))
    drv.hover(6.0, SIZE[1] - 6.0)
    _settle(drv, app)
    ShotDriver(app, SIZE).screenshot(FIG / "image_browser_zoomed.png")
    print("wrote image_browser_zoomed.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
