"""The emtk app in its populated state, every tab visited: after.json (union of the per-tab inventories) and the screenshots.

Usage: <out_dir> [docs]. The parity tool's own ``after`` draws the empty app, where the views, the table columns and the image controls are
not on screen; this draws what a user sees after choosing the Poisson stack of make_data.py and pressing Measure (and the photon stream,
the two-file and two-channel splits, and the error states). ``docs`` draws only the figure of docs/guides/51_frc_resolution.md.
"""
import json, pathlib, sys, tempfile
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_inventory, emtk_screenshot, qt_free
from chisurf.core.fio.image import imwrite
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_frc.gui.app import make_app

out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import noisy_stack  # noqa: E402

REPO = out.resolve().parents[3]
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
tmp = pathlib.Path(tempfile.mkdtemp())
a, b = tmp / "a.tif", tmp / "b.tif"
imwrite(a, noisy_stack(seed=0)); imwrite(b, noisy_stack(seed=1))
SIZE = (1200, 800)


def fresh():
    app = make_app()
    return app, Driver(app, SIZE)


def load(app, drv, path):
    app.model.open_path(str(path)); drv.settle()


def run(app, drv, **settings):
    for k, v in settings.items():
        setattr(app.model, k, v)
    drv.click("measure"); drv.settle()


def shot(app, name, size=SIZE):
    emtk_screenshot(app, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)


if len(sys.argv) < 3 or sys.argv[2] != "docs":
    union, interactive, missing = set(), [], set()
    app, drv = fresh()
    app.form.folds["Estimator"] = True
    load(app, drv, a); run(app, drv, pixel_size_nm=25.0)
    for tab in ("Halves", "Rings"):
        app.docks.focus(tab)
        drv.draw(3)
        inv = emtk_inventory(app, SIZE)
        union |= set(inv["controls"]); interactive += inv["interactive"]; missing |= set(inv["controls_without_tooltip"])
        shot(app, tab)
        shot(app, tab, (800, 600))
        if tab == "Halves":
            combo = [t for t in drv.draw(2).texts if t[5] == "inferno"][0][:4]
            drv.click_at(combo[0] + 10, combo[1] + combo[3] / 2)
            union |= set(emtk_inventory(app, SIZE)["controls"])
            shot(app, "Halves_colormap_open")
            drv.escape()
    for field, name in (("split", "split_list_open"), ("criterion", "criterion_list_open"), ("axis_order", "axis_order_list_open"),
                        ("channel", "channel_list_open"), ("channel_2", "second_channel_list_open")):
        drv.click(field)
        union |= set(emtk_inventory(app, SIZE)["controls"])
        shot(app, name)
        drv.escape()
    (out / "after.json").write_text(json.dumps({"size": list(SIZE), "controls": sorted(union), "interactive": interactive,
                                                "controls_without_tooltip": sorted(missing), "qt_free": qt_free("img_frc")},
                                               indent=2, ensure_ascii=False))
    print(len(union), "controls;", len(missing), "without tooltip")
    app.docks.focus("Rings"); shot(app, "FRC_pixels_unit_after_pixel_size_cleared") if False else None

    # the other states
    app, drv = fresh(); load(app, drv, a); run(app, drv); shot(app, "pixels")
    app, drv = fresh(); load(app, drv, a); run(app, drv, criterion="half_bit", pixel_size_nm=25.0); shot(app, "half_bit")
    app, drv = fresh(); load(app, drv, a); app.model.set_second_filename(str(b)); run(app, drv, split="two_files", pixel_size_nm=25.0); shot(app, "two_files")
    app, drv = fresh(); load(app, drv, HT3); run(app, drv, pixel_size_nm=25.0); shot(app, "photon_even_odd")
    app, drv = fresh(); load(app, drv, HT3); app.model.channel, app.model.channel_2 = "ch0", "ch1"; run(app, drv, split="channels", pixel_size_nm=25.0)
    shot(app, "photon_channels")
    app, drv = fresh(); drv.click("measure"); shot(app, "measure_pressed_empty")
    app, drv = fresh(); load(app, drv, a); run(app, drv, split="two_files"); shot(app, "two_files_without_second")
    app, drv = fresh(); bad = tmp / "bad.tif"; bad.write_bytes(b"not a tiff"); load(app, drv, bad); run(app, drv); shot(app, "corrupt_file")
    app, drv = fresh(); load(app, drv, a); app.model.folder = str(tmp); run(app, drv); drv.click("request_export"); drv.draw(2); shot(app, "export_dialog")
    app, drv = fresh(); drv.click("help"); shot(app, "help")
    app, drv = fresh(); load(app, drv, a); drv.click("guide"); app.tour.start(4); shot(app, "guide_measure_step")

# the figure of docs/guides/51_frc_resolution.md: the photon stream, even / odd frames, 25 nm pixels
app, drv = fresh(); load(app, drv, HT3); run(app, drv, pixel_size_nm=25.0)
app.docks.focus("Halves"); emtk_screenshot(app, out / "docs_frc_workspace.png", SIZE)
