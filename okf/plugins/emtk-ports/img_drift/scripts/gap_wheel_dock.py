from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_sections
class M: v = 5
spec = [{"type": "value", "attr": "v", "kind": "int", "style": "spin", "minimum": 0, "maximum": 99, "step": 1, "description": "d"}]
def run(docked):
    m, st = M(), FormState()
    docks = DockManager(Region("r")); docks.add_window("w", "W", lambda b: draw_sections(spec, m, st), dock="r", closable=False)
    app = ImApp((lambda: docks.draw((0, 0, 400, 200))) if docked else (lambda: (im.begin("W", (0, 0, 400, 200)), draw_sections(spec, m, st), im.end())))
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, 400, 200)
    x, y, w, h = st.rects["v"]
    app.pointer_move(x + 10, y + 5); app.draw(RecordingPainter(), 0, 0, 400, 200)
    app.wheel(x + 10, y + 5, 1); app.draw(RecordingPainter(), 0, 0, 400, 200)
    return m.v
print("plain window:", run(False), " docked window:", run(True))   # 6 and 5 expected: the wheel is lost inside DockManager
