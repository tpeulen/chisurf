"""Captures of the emtk phasor calculator, states reached with real pointer and key input. Usage: capture_after.py <out_dir> <prefix>."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path.cwd()))
from emtk import testing
from emtk.testing import PixelPainter
from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app
from chisurf.plugins.calculator.phasor_calculator.tests.driving import PhasorDriver
from chisurf.plugins.calculator.phasor_calculator.tests import test_emtk_phasor_clicks as T

out = pathlib.Path(sys.argv[1]).resolve(); prefix = sys.argv[2]
SIZES = ((1200, 800), (800, 600))
app = make_app(); drv = PhasorDriver(app, SIZES[0]); m = app.tool._model


def shot(name, sizes=SIZES):
    for size in sizes:
        drv.size = size
        for _ in range(3):
            p = PixelPainter(*size); app.draw(p, 0.0, 0.0, float(size[0]), float(size[1]))
        (out / f"{prefix}_{name}_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
    drv.size = SIZES[0]


drv.draw(3)
shot("default")                                    # the groups as the spec declares them (three folded)
for t in ("Two-component line", "Mixing region", "Cursor"):
    T.unfold(drv, t)
for name in ("show_polar_grid", "show_fret", "show_component", "show_mixing", "show_cursor"):
    drv.click(name)                                # real clicks on the toggles
shot("populated")                                  # the Qt populated state: everything on, every group open
drv.type_into("frequency", "40"); drv.type_into("taus", "1, 3, 6"); T.stepper(drv, "harmonic", +1)
shot("edited", SIZES[:1])
x, y, w, h = drv.rect("plot")
drv.drag((x + w / 2, y + h / 2), (x + w / 2 - 150, y + h / 2 + 90)); shot("plot_panned", SIZES[:1])
hx, hy, hw, hh = drv.rect("reference_rows")
head = next(t for t in drv.draw(2).texts if t[5] == "τ (ns)" and hx <= t[0] <= hx + hw)
drv.click_at(head[0] + 4, head[1] + 4); drv.click_at(head[0] + 4, head[1] + 4); shot("table_sorted", SIZES[:1])
drv.click("guide"); drv.click_text("Next ►"); shot("guide_frequency_step", SIZES[:1]); drv.escape()
drv.click("help"); shot("help", SIZES[:1]); drv.escape()
print("ok")
