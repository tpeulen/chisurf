"""emtk gap: a wheel notch that an implot used for zooming is not consumed; it stays in io.mouse_wheel and steps the next spin field the pointer reaches."""
import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_sections
class M: v = 5
spec = [{"type": "value", "attr": "v", "kind": "int", "style": "spin", "minimum": 0, "maximum": 99, "step": 1, "description": "d"}]
m, st = M(), FormState()
def gui():
    im.begin("W", (0, 0, 400, 300)); implot.begin_plot("##p", (300, 150)); implot.plot_line("l", np.arange(5.0), np.arange(5.0)); implot.end_plot(); draw_sections(spec, m, st); im.end()
app = ImApp(gui); draw = lambda: app.draw(RecordingPainter(), 0, 0, 400, 300)
for _ in range(3): draw()
app.pointer_move(100, 60); draw(); app.wheel(100, 60, 4); draw()          # zoom the plot: the plot takes the notches
x, y, w, h = st.rects["v"]; app.pointer_move(x + 10, y + 5)                # ... then move to the spin field and just draw
for _ in range(5): draw()
print("v =", m.v, "after 5 frames with the pointer on the field and no wheel turned (expected 5); io.mouse_wheel =", app.io.mouse_wheel)
