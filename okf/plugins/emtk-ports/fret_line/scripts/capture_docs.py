"""Guide figures from the emtk app: the static and the dynamic line (guide 82). Usage: <out_dir> (writes docs_*.png)."""
import pathlib, sys
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.fret_line.gui.app import FRETLineApp
out = pathlib.Path(sys.argv[1]); size = (1200, 800)
app = FRETLineApp(); d = Driver(app, size); m = app.model; d.draw(3)
m.minimum, m.maximum = 20.0, 120.0; m.add_line()
m.add_component()
for comp, r in ((0, 40.0), (1, 70.0)):
    next(p for p in m.components[comp]["model"].parameters_all if p.canonical_id == "distance.mean.0").value = r
m.sweep_label = next(l for l in m.sweep_labels() if l.startswith("fraction · C0")); m.minimum, m.maximum = 0.0, 1.0; m.add_line()
d.draw(4); emtk_screenshot(app, out / "docs_fret_line_tool.png", size)
d.click(d.text_rect("FRET lines")); d.draw(4); emtk_screenshot(app, out / "docs_fret_line_tool_lines.png", size)
app.close()
