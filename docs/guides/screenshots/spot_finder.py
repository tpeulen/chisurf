"""Spot Finder screenshots on a real HT3 confocal image (mGBP puncta in a MEF cell).

The window is the native emtk app, driven headlessly (no Qt) and written to ``figures/``.
"""
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
for entry in (REPO, REPO / "docs" / "guides"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from emtk.testing import Driver  # noqa: E402

from screenshots.emtk_shot import FIG, app_from, wait  # noqa: E402

MGBP = (
    os.path.expanduser(os.environ.get("CHISURF_TTTR_DATA", "~/dev/tttr-data"))
    + "/imaging/pq/ht3/58 MEF ko mGBP7 + GFP-mGBP7 + mCherry-mGBP6 + IFNg_green.ht3"
)


def _park(driver):
    """Move the pointer to the empty bottom-left corner so no tooltip covers the figure."""
    driver.hover((12.0, float(driver.size[1]) - 12.0))
    driver.frame(2)


def _grab_spot_finder():
    """The detection settings and the detected regions after a Preview (guide 84)."""
    app = app_from("spot_finder")
    driver = Driver(app, (1500, 950))
    driver.frame(2)
    m = app.model
    m.files = [MGBP]
    m.workflow = "camera_spots"
    m.settings.threshold = 50.0  # in image units: see guide 84
    m.settings.max_sigma = 4.0
    m.name = "puncta"
    app.start("preview")
    wait(driver, lambda: not app.job.busy)
    print(m.status_text)
    driver.frame(3)
    _park(driver)
    shot = FIG / "spot_finder_detection.png"
    driver.screenshot(shot)
    print("wrote spot_finder_detection.png", flush=True)
    # The regions view alone: the image panel (top right) with every region drawn as its ellipse.
    from PIL import Image

    image = Image.open(shot)
    w, h = image.size
    image.crop((int(w * 0.34), 0, w, int(h * 0.70))).save(FIG / "spot_finder_regions.png")
    print("wrote spot_finder_regions.png", flush=True)


def _grab_spot_finder_hub():
    """The Spot Finder as an entry of the Imaging Tools list (guide 84)."""
    app = app_from("imaging_tools")
    driver = Driver(app, (1500, 950))
    driver.frame(2)
    app.goto_role("spot_finder")
    driver.frame(6)
    child = app.child
    child.start("load_demo")  # Load example: the built-in known-field demo
    wait(driver, lambda: not child.job.busy)
    child.start("run")  # Detect
    wait(driver, lambda: not child.job.busy)
    driver.frame(4)
    _park(driver)
    driver.screenshot(FIG / "spot_finder_hub.png")
    print("wrote spot_finder_hub.png", flush=True)


if __name__ == "__main__":
    for name in sys.argv[1:] or ["_grab_spot_finder", "_grab_spot_finder_hub"]:
        globals()[name]()
