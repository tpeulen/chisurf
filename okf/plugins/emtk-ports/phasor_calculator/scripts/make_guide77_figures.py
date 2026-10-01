"""Guide 77 figures: 80 MHz, harmonic 1, lifetimes 0.5-8 ns, FRET (tau_D0 4 ns), C1 0.6 ns, C2 5 ns, 50:50 mixture, cursor.

usage: make_guide77_figures.py <out_dir>   (run from the repo root)
"""
import io, pathlib, sys
from PIL import Image
from emtk import testing
from test.gui.emtk_port_parity import draw_app
from chisurf.plugins.calculator.phasor_calculator.gui.app import make_app
from chisurf.plugins.microscopy.img_pixel_phasor import analysis

out = pathlib.Path(sys.argv[1])
app = make_app()
m = app.tool._model
(m.g1, m.s1), (m.g2, m.s2) = (tuple(map(float, analysis.lifetime_to_phasor(t, 80.0))) for t in (0.6, 5.0))
m.show_fret = m.show_component = m.show_mixing = m.show_cursor = True
m.frac1 = 0.5
mix = (0.5 * (m.g1 + m.g2), 0.5 * (m.s1 + m.s2))
m.cursor_g, m.cursor_s, m.cursor_radius = round(mix[0], 3), round(mix[1], 3), 0.05
for title in ("Two-component line", "Mixing region", "Cursor"):
    app.phasor_gui.form.folds[title] = True
size = (1280, 820)
painter = draw_app(app, size)
png = testing.png_encode(painter.width, painter.height, painter.px)
(out / "phasor_calculator.png").write_bytes(png)
Image.open(io.BytesIO(png)).crop((0, 0, 486, size[1])).save(out / "phasor_calculator_controls.png")
print("mixture", tuple(round(v, 3) for v in mix))
