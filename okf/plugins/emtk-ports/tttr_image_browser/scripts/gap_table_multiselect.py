"""emtk gap: a data_table row cannot be added to / removed from the selection with Ctrl-click (the Qt list allowed it)."""
from emtk import im
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_sections
class M:
    rows = [{"n": f"r{i}"} for i in range(3)]; picked = []
    def pick(self, r): self.picked.append(r["n"])
spec = [{"type": "custom", "key": "data_table", "title": "T", "description": "d", "options": {"source": "rows", "selected_call": "pick", "columns": [{"key": "n", "title": "N", "description": "d"}]}}]
m, st = M(), FormState(); app = ImApp(lambda: (im.begin("W", (0, 0, 300, 200)), draw_sections(spec, m, st), im.end()))
def draw(): app.draw(RecordingPainter(), 0, 0, 300, 200)
for _ in range(3): draw()
t = st.tables["rows"].control; x, y, w, h = t._body_box; row = lambda i: (x + 20, y + (i + 0.5) * t._row_h)
app.pointer_move(*row(0)); draw(); app.press(*row(0), 0, 0, 0, 0, 0, 1); draw(); app.release(); draw()
app.pointer_move(*row(1)); draw(); app.press(*row(1), 0, 0, 0, 0, CONTROL_MODIFIER, 1); draw(); app.release(); draw()
print("selected", t.selected_key, sorted(t.also_selected), "callbacks", m.picked, "-> expected r0 and r1 selected after the Ctrl-click")
