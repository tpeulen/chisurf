"""Guide 24 figures: CLSM-Draw on the Leica test scans and Pixel-wise MLE on its example (emtk).

Run from the repository root, headless, with a scratch settings dir::

    CHISURF_SETTINGS_DIR=$(mktemp -d) IMP_BFF_GPU=off \
        python docs/guides/screenshots/guide_24_scan_images.py [sp8] [sp5] [mle]

``sp8`` writes ``24_clsm_draw.png`` (Leica SP8, channels 0,1, the brightest 5 % of
pixels as the selection, its decay) and ``24_clsm_draw_rois.png`` (the same selection
saved as the region *bright patch*, the *Analysis regions* fold open). ``sp5`` writes
``24_clsm_draw_window.png`` (Leica SP5 preset, channel 0, a centre disc selected).
``mle`` writes ``24_mle_tool.png`` (Pixel-wise MLE: Load example, then Run).
Read the PNGs afterwards.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))


def _built(preset: str, path: str, channels: str):
    from emtk_shot import app_from

    app = app_from("clsm")
    m = app.model
    m.apply_preset(preset)
    m.load_file(str((REPO / path).resolve()))
    m.setup.channels_text = channels
    m.add_clsm()
    m.add_representation()
    return app


def grab_sp8() -> None:
    from emtk.testing import Driver
    from emtk_shot import FIG

    app = _built("Leica SP8", "test/data/clsm/Leica_SP8.ptu", "0,1")
    m = app.model
    img = m.current_image
    m.selection_mask = (img >= np.quantile(img, 0.95)).astype(float)
    m.notify("selection")
    d = m.recompute_decay()
    print("sp8 image", img.shape, "decay photons", float(np.sum(d["counts"])), flush=True)
    driver = Driver(app, (1400, 860))
    driver.settle()
    driver.frame(2)
    driver.screenshot(FIG / "24_clsm_draw.png")
    m.add_roi("bright patch")
    print("summary:", m.region_summary("bright patch"), flush=True)
    driver.frame(2)
    driver.click("Brush & Decay.fold")  # fold it, so the regions fit
    driver.frame(2)
    caption = next(t[5] for t in driver.painter.texts if "Analysis regions" in str(t[5]))
    driver.click(caption)
    driver.frame(2)
    driver.click("bright patch")  # select it: its area and mean intensity are shown below
    driver.frame(3)
    driver.screenshot(FIG / "24_clsm_draw_rois.png")
    print("wrote 24_clsm_draw.png, 24_clsm_draw_rois.png", flush=True)
    app.close()


def grab_sp5() -> None:
    from emtk.testing import Driver
    from emtk_shot import FIG

    app = _built("Leica SP5", "test/data/clsm/Leica_SP5.ptu", "0")
    m = app.model
    img = m.current_image
    yy, xx = np.indices(img.shape[-2:])
    cy, cx = img.shape[-2] / 2, img.shape[-1] / 2
    m.selection_mask = (((yy - cy) ** 2 + (xx - cx) ** 2) < (min(img.shape[-2:]) / 4) ** 2).astype(float)
    m.notify("selection")
    d = m.recompute_decay()
    print("sp5 image", img.shape, "decay photons", float(np.sum(d["counts"])), flush=True)
    driver = Driver(app, (1200, 800))
    driver.settle()
    driver.frame(2)
    driver.screenshot(FIG / "24_clsm_draw_window.png")
    print("wrote 24_clsm_draw_window.png", flush=True)
    app.close()


def grab_mle() -> None:
    import tempfile

    from emtk.testing import Driver
    from emtk_shot import FIG

    from chisurf.plugins.microscopy.img_pixel_mle.gui.app import make_app

    app = make_app()
    m = app.model
    m.example_folder = pathlib.Path(tempfile.mkdtemp())
    m.load_example()
    m.run()
    tau = np.asarray(m.results[0].tau)
    half = tau.shape[-1] // 2
    print("mle tau left/right", np.nanmedian(tau[..., :half]), np.nanmedian(tau[..., half:]), flush=True)
    driver = Driver(app, (1200, 800))
    driver.settle()
    driver.frame(3)
    driver.screenshot(FIG / "24_mle_tool.png")
    print("wrote 24_mle_tool.png", flush=True)
    app.close()


if __name__ == "__main__":
    wanted = set(sys.argv[1:]) or {"sp8", "sp5", "mle"}
    if "sp8" in wanted:
        grab_sp8()
    if "sp5" in wanted:
        grab_sp5()
    if "mle" in wanted:
        grab_mle()
