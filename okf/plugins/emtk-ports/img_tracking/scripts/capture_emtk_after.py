"""The emtk app in its populated state, every tab visited: after.json (union of the per-tab inventories) and the screenshots.

Usage: <out_dir>. The parity tool's own ``after`` draws the empty app, where the views, the table columns and the movie
controls are not on screen; this draws what a user sees after Track on the simulated movie of capture_qt_populated.py.
"""
import json, pathlib, sys, time
from emtk.testing import PixelPainter, RecordingPainter
from test.gui.emtk_port_parity import emtk_inventory, emtk_screenshot, qt_free
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.img_tracking.gui.app import make_app

out = pathlib.Path(sys.argv[1])
SMALL = dict(use_simulation=True, sim_n_frames=40, sim_size=160, sim_n_particles=6, sim_diffusion=0.5, sim_seed=1,
             max_distance=4.0, n_bootstrap=50)


def draw(app, size, n=3):
    for _ in range(n):
        app.draw(RecordingPainter(), 0, 0, *size)


def run(app, size):
    app.model.track()
    while app.job.busy:
        time.sleep(0.02); draw(app, size, 1)
    draw(app, size)


def folds_open(app, size):
    for fold in ("Simulate instead",):
        if not app.form.folds.get(fold, False):
            app.form.folds[fold] = True
    draw(app, size)


union, interactive, missing = set(), [], set()
app = make_app()
for k, v in SMALL.items():
    setattr(app.model, k, v)
folds_open(app, (1200, 800))
run(app, (1200, 800))
for tab in ("Movie", "Trajectories", "MSD", "Track lengths", "Tracks"):
    app.docks.focus(tab)
    draw(app, (1200, 800))
    inv = emtk_inventory(app, (1200, 800))
    union |= set(inv["controls"]); interactive += inv["interactive"]; missing |= set(inv["controls_without_tooltip"])
    emtk_screenshot(app, out / f"after_populated_{tab.replace(' ', '_')}_1200x800.png", (1200, 800))
    if tab == "Movie":  # the colormap list opened: its entries are controls too
        drv = Driver(app, (1200, 800))
        combo = [t for t in drv.draw(2).texts if t[5] == "magma"][0][:4]
        drv.click_at(combo[0] + 10, combo[1] + combo[3] / 2)
        union |= set(emtk_inventory(app, (1200, 800))["controls"])
        emtk_screenshot(app, out / "after_populated_Movie_colormap_open_1200x800.png", (1200, 800))
        drv.escape()
    if tab in ("Movie", "MSD"):
        emtk_screenshot(app, out / f"after_populated_{tab.replace(' ', '_')}_800x600.png", (800, 600))
drv = Driver(app, (1200, 800))
app.docks.focus("Movie")
drv.click("method")  # the detector list opened
union |= set(emtk_inventory(app, (1200, 800))["controls"])
emtk_screenshot(app, out / "after_populated_detector_list_open_1200x800.png", (1200, 800))
drv.escape()
(out / "after.json").write_text(json.dumps({"size": [1200, 800], "controls": sorted(union), "interactive": interactive,
                                            "controls_without_tooltip": sorted(missing),
                                            "qt_free": qt_free("img_tracking")}, indent=2, ensure_ascii=False))
print(len(union), "controls;", len(missing), "without tooltip")

# the figures of docs/guides/50_particle_tracking.md: the guide's own run (the model's simulation defaults: 8 particles,
# 60 frames, D = 0.5 px^2/frame, seed 1)
app = make_app()
app.model.use_simulation = True
app.form.folds["Simulate instead"] = False
app.model.track()
while app.job.busy:
    time.sleep(0.02); draw(app, (1200, 800), 1)
draw(app, (1200, 800))
print(app.model.status_line)
for tab, name in (("Movie", "tracking_workspace"), ("Trajectories", "tracking_trajectories")):
    app.docks.focus(tab)
    emtk_screenshot(app, out / f"docs_{name}.png", (1200, 800))
