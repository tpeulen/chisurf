"""Populated captures of the native FPS JSON editor, same inputs as capture_qt.py. usage: capture_emtk.py <out_dir>

Writes after_populated_<tab>_<W>x<H>.png for every tab at 1200x800 and 800x600 and after.json: the union of the
control inventory over the empty state and every populated tab (the Qt inventory walks hidden tabs too, so a
single-tab emtk frame undercounts). Run after `emtk_port_parity after`, then `compare`.
"""
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures  # noqa: E402

out = pathlib.Path(sys.argv[1])
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
# the repo's test.gui first: a chisurf import loads the standard library's ``test`` package otherwise
from test.gui import emtk_port_parity as epp  # noqa: E402, I001
from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app  # noqa: E402
from chisurf.plugins.modelling.structure_tools.cards.fps_json import TABS  # noqa: E402

SIZES = ((1200, 800), (800, 600))
app = make_app()
empty = epp.emtk_inventory(app, SIZES[0])
fps, _ = fixtures.make(work)
app.load_path(str(fps))
ed = app.editor
ed.compute_all()
t0 = time.time()
while ed.busy and time.time() - t0 < 300:
    ed.poll()
    time.sleep(0.1)
ed.poll()
ed.selected_pos = ed.rows_pos[0]["row"]
ed.selected_dist = ed.rows_dist[0]["row"] if hasattr(ed, "rows_dist") else ed.selected_dist
controls, rows = set(empty["controls"]), list(empty["interactive"])
for tab in TABS:
    app.tab = tab
    slug = tab.lower().replace(" ", "")
    for size in SIZES:
        epp.emtk_screenshot(app, out / f"after_populated_{slug}_{size[0]}x{size[1]}.png", size)
    inv = epp.emtk_inventory(app, SIZES[0])
    controls |= set(inv["controls"])
    rows += inv["interactive"]
    print(tab, len(inv["controls"]), "controls", inv["controls_without_tooltip"])
# The Qt "Details..." dialog's fields are the folded Simulation / Advanced panels: opened by real clicks at 800x600,
# then the window wheeled to its end (the frame that showed the form unreachable before the emtk begin_child fix).
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui  # noqa: E402

app.tab = "Positions"
ui = Ui(app, SIZES[1])


def wheel_form():
    """One wheel notch over the form below the table (over the table the wheel scrolls the table)."""
    app.pointer_move(20, 450)
    ui.draw(1)
    app.wheel(20, 450, -3)
    ui.draw(1)


ui.click(ui.text_rect("p51_K173C", 0))
for fold in ("Simulation.fold", "Advanced.fold"):
    for _ in range(10):
        ui.draw(1)
        x, y, w, h = app.item_rects[fold]
        if y + h <= SIZES[1][1]:
            break
        wheel_form()
    ui.click(fold)
for _ in range(10):
    wheel_form()
epp.emtk_screenshot(app, out / "after_populated_positions_details_scrolled_800x600.png", SIZES[1])
x, y, w, h = app.item_rects["min_sphere_volume_fraction"]
print("last field", (x, y, w, h), "inside 800x600:", 0 <= y and y + h <= SIZES[1][1])
inv = epp.emtk_inventory(app, SIZES[0])
controls |= set(inv["controls"])
rows += inv["interactive"]
seen, uniq = set(), []
for r in rows:
    k = (r["kind"], r["label"])
    if k not in seen:
        seen.add(k)
        uniq.append(r)
after = {"size": list(SIZES[0]), "states": ["empty", *[f"populated:{t}" for t in TABS]],
         "controls": sorted(controls), "interactive": uniq,
         "controls_without_tooltip": sorted({f"{r['kind']}: {r['label']}" for r in uniq if not r["tooltip"]}),
         "qt_free": epp.qt_free("fps_json_editor")}
(out / "after.json").write_text(json.dumps(after, indent=2, ensure_ascii=False))
print("positions", len(ed.doc.positions), "distances", len(ed.doc.distances), "|", ed.av_message)
app.close()
