"""The emtk app in its populated state, every tab visited: after.json (union of the per-tab inventories) and the screenshots.

Usage: <out_dir>. The parity tool's own ``after`` draws the empty app, where the views, the table columns and the image controls are not on
screen; this draws what a user sees after choosing the drifting TIFF of make_data.py (and the photon stream, and the error states).
"""
import json, pathlib, sys, tempfile, time
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_inventory, emtk_screenshot, qt_free
from chisurf.core.fio.image import imwrite
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_drift.gui.app import make_app

out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import drifting_stack  # noqa: E402

REPO = out.resolve().parents[3]
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
tmp = pathlib.Path(tempfile.mkdtemp())
tif = tmp / "drift.tif"
imwrite(tif, drifting_stack())
SIZE = (1200, 800)


def fresh():
    app = make_app()
    return app, Driver(app, SIZE)


def load(app, drv, path):
    app.model.open_path(str(path))
    drv.settle()


def shot(app, name, size=SIZE):
    emtk_screenshot(app, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)


if len(sys.argv) < 3 or sys.argv[2] != "docs":
    union, interactive, missing = set(), [], set()
    app, drv = fresh()
    app.form.folds["Estimator"] = True
    load(app, drv, tif)
    for tab in ("Drift trace", "Projection", "Shifts"):
        app.docks.focus(tab)
        drv.draw(3)
        inv = emtk_inventory(app, SIZE)
        union |= set(inv["controls"]); interactive += inv["interactive"]; missing |= set(inv["controls_without_tooltip"])
        shot(app, tab.replace(" ", "_"))
        if tab in ("Drift trace", "Projection"):
            shot(app, tab.replace(" ", "_"), (800, 600))
        if tab == "Projection":  # the colormap list opened
            combo = [t for t in drv.draw(2).texts if t[5] == "inferno"][0][:4]
            drv.click_at(combo[0] + 10, combo[1] + combo[3] / 2)
            union |= set(emtk_inventory(app, SIZE)["controls"])
            shot(app, "Projection_colormap_open")
            drv.escape()
    app.docks.focus("Drift trace")
    for field, name in (("reference", "reference_list_open"), ("mode", "apply_by_list_open"), ("channel", "channel_list_open")):
        drv.click(field)
        union |= set(emtk_inventory(app, SIZE)["controls"])
        shot(app, name)
        drv.escape()
    (out / "after.json").write_text(json.dumps({"size": list(SIZE), "controls": sorted(union), "interactive": interactive,
                                                "controls_without_tooltip": sorted(missing), "qt_free": qt_free("img_drift")},
                                               indent=2, ensure_ascii=False))
    print(len(union), "controls;", len(missing), "without tooltip")

    # the other states
    app, drv = fresh(); load(app, drv, HT3); app.docks.focus("Drift trace"); shot(app, "photon_stream")
    app.docks.focus("Projection"); shot(app, "photon_stream_projection")
    app, drv = fresh(); drv.click("measure"); shot(app, "measure_pressed_empty")
    app, drv = fresh(); bad = tmp / "bad.tif"; bad.write_bytes(b"not a tiff"); load(app, drv, bad); shot(app, "corrupt_file")
    app, drv = fresh(); load(app, drv, tif); app.model.reference = "previous"; app.model.mode = "constant"; drv.click("measure"); drv.settle()
    shot(app, "previous_blanking")
    app, drv = fresh(); load(app, drv, tif); app.model.folder = str(tmp); drv.click("request_export_stack"); drv.draw(2); shot(app, "export_dialog")
    app, drv = fresh(); drv.click("help"); shot(app, "help")
    app, drv = fresh(); load(app, drv, tif); drv.click("guide"); app.tour.start(4); shot(app, "guide_measure_step")


# the figures of docs/guides/43_drift_correction.md
import numpy as np
from PIL import Image
app, drv = fresh(); load(app, drv, tif)
app.docks.focus("Drift trace"); emtk_screenshot(app, out / "docs_drift_workspace.png", SIZE)
app.docks.focus("Projection"); emtk_screenshot(app, out / "projection_full.png", SIZE)
drv.draw(3)
full = Image.open(out / "projection_full.png").convert("RGB")
for key, name in (("before.image", "drift_before"), ("after.image", "drift_after")):
    x, y, w, h = app.item_rects[key]
    crop = full.crop((int(x), int(y), int(x + w), int(y + h)))
    a = np.asarray(crop).astype(int)
    colored = (np.abs(a[..., 0] - a[..., 1]) + np.abs(a[..., 1] - a[..., 2])) > 10
    colored[:40] = False  # the legend
    ys, xs = np.nonzero(colored)
    pad = 24
    box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + pad, crop.width), min(ys.max() + pad, crop.height))
    crop.crop(box).save(out / f"docs_{name}.png")
(out / "projection_full.png").unlink()
