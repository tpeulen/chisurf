"""The emtk app in its populated state, every tab visited: after.json (union of the per-tab inventories) and the screenshots.

Usage: <out_dir> [docs]. The parity tool's own ``after`` draws the empty app, where the views, the table columns and the image controls are not on
screen; this draws what a user sees after choosing the drifting TIFF of make_data.py and pressing Map flow (and the demo, the pair-correlation
estimator and the error states). ``docs`` draws only the figure of docs/guides/55_pair_correlation.md. The demo is simulated once (about 20 s)
into a temporary folder.
"""
import json, pathlib, sys, tempfile
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_inventory, emtk_screenshot, qt_free
from chisurf.core.fio.image import imwrite
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_flow import demo
from chisurf.plugins.microscopy.img_flow.gui.app import make_app

out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import TIMING, drifting_stack  # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp())
flow = tmp / "flow.tif"
imwrite(flow, drifting_stack(0.5))
demo_file = tmp / "demo" / "flow_demo_poiseuille.ptu"
demo.demo_path = lambda directory=None: demo_file
SIZE = (1200, 800)
BASE = dict(tile=16, n_lags=4, min_quality=0.5, **TIMING)


def fresh():
    app = make_app()
    return app, Driver(app, SIZE)


def run(app, drv, path=None, **settings):
    if path is not None:
        app.model.open_path(str(path)); drv.settle()
    for k, v in (settings or BASE).items():
        setattr(app.model, k, v)
    drv.click("map_flow"); drv.settle()


def shot(app, name, size=SIZE):
    app.pointer_move(-1.0, -1.0)  # no hover highlight under a leftover pointer position
    emtk_screenshot(app, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)


if len(sys.argv) < 3 or sys.argv[2] != "docs":
    union, interactive, missing = set(), [], set()
    app, drv = fresh()
    app.form.folds["Display and estimator"] = True
    run(app, drv, flow)
    for tab in ("Profile", "Tiles"):
        app.docks.focus(tab)
        drv.draw(3)
        inv = emtk_inventory(app, SIZE)
        union |= set(inv["controls"]); interactive += inv["interactive"]; missing |= set(inv["controls_without_tooltip"])
        shot(app, tab); shot(app, tab, (800, 600))
    for field, name in (("method", "method_list_open"), ("subtract_average", "background_list_open"), ("channel", "channel_list_open")):
        drv.click(field)
        union |= set(emtk_inventory(app, SIZE)["controls"])
        shot(app, name)
        drv.escape()
    # the other states
    app, drv = fresh(); run(app, drv, flow, min_quality=0.99, **{k: v for k, v in BASE.items() if k != "min_quality"}); shot(app, "tight_quality")
    app, drv = fresh(); run(app, drv, flow, **dict(BASE, n_lags=30)); shot(app, "tiles_escaped")
    union |= set(emtk_inventory(app, SIZE)["controls"])  # the no-arrow caption and the diagnosis are controls of this state
    app, drv = fresh(); run(app, drv, flow, **dict(BASE, method="pcf", distance=4)); shot(app, "pair_correlation")
    app, drv = fresh(); run(app, drv, flow, **dict(BASE, arrow_scale=0.3)); shot(app, "arrow_scale_03")
    app, drv = fresh(); drv.click("map_flow"); shot(app, "map_pressed_empty")
    app, drv = fresh(); bad = tmp / "bad.tif"; bad.write_bytes(b"not a tiff"); app.model.open_path(str(bad)); drv.settle(); shot(app, "corrupt_file")
    app, drv = fresh(); run(app, drv, flow); app.model.folder = str(tmp); drv.click("request_export"); drv.draw(2); shot(app, "export_dialog")
    app, drv = fresh(); drv.click("help"); shot(app, "help")
    app, drv = fresh(); drv.click("guide"); app.tour.start(1); shot(app, "guide_demo_step")
    app, drv = fresh(); drv.click("demo"); drv.settle(timeout=300); shot(app, "demo_loaded")
    drv.click("map_flow"); drv.settle(); shot(app, "demo_mapped")
    app.docks.focus("Profile"); shot(app, "demo_profile_with_truth")

    (out / "after.json").write_text(json.dumps({"size": list(SIZE), "controls": sorted(union), "interactive": interactive,
                                                "controls_without_tooltip": sorted(missing), "qt_free": qt_free("img_flow")},
                                               indent=2, ensure_ascii=False))
    print(len(union), "controls;", len(missing), "without tooltip")

# the figure of docs/guides/55_pair_correlation.md: the flow tool on a stack with a known speed
app, drv = fresh(); run(app, drv, flow)
app.pointer_move(-1.0, -1.0); emtk_screenshot(app, out / "docs_flow_tool.png", SIZE)
