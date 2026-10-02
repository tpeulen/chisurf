"""One more emtk gap found while upgrading lightpath_simulator, phasor_calculator and project_browser (run with PYTHONPATH=~/dev/emtk).

The column picker of a data_table lists only the visible columns, so a column declared ``"visible": false`` cannot be shown again
by the user; a host has to offer its own toggle (project_browser's Show ID / Show status).
"""
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


class M:
    def rows(self):
        return [{"a": 1, "b": 2}]


spec = {"sections": [{"type": "custom", "key": "data_table", "options": {"source": "rows", "column_picker": True,
        "columns": [{"key": "a", "title": "A"}, {"key": "b", "title": "B", "visible": False}]}}]}
m, form = M(), FormState()
app = ImApp(lambda: draw_form(spec, m, form))
for _ in range(3):
    painter = RecordingPainter(); app.draw(painter, 0, 0, 300, 200)
x, y = [t[:2] for t in painter.texts if t[5] == "A"][0]
app.pointer_move(x + 4, y + 4); app.draw(RecordingPainter(), 0, 0, 300, 200)
app.pointer_press(x + 4, y + 4, 2); painter = RecordingPainter(); app.draw(painter, 0, 0, 300, 200)
print("picker entries:", [t[5] for t in painter.texts if t[5] in ("A", "B")], "(expected both A and B)")
