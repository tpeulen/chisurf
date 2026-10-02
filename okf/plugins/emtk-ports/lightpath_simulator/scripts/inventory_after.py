"""after.json of the populated window: the union of the control inventories of every results tab and of the Easy Mode tab.

`emtk_port_parity after` inventories one default frame; a tabbed window shows one tab at a time, so the controls of the other
tabs would be reported lost. Usage: inventory_after.py <out_dir>
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui.emtk_port_parity import emtk_inventory, qt_free
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lp_env
from chisurf.plugins.core.lightpath_simulator.gui.app import create_app
from chisurf.plugins.core.lightpath_simulator.tests.driving import LPDriver

out = pathlib.Path(sys.argv[1])
app = create_app(client=lp_env.in_process_client()); c = app.controller; c.auto_update = False
d = LPDriver(app); d.settle()
for n in c.document.nodes:
    if n.type == "detector": n.config["probe_id"] = lp_env.IDS["APD (flat QE)"]
d.click("calculate"); d.settle()
merged = {"controls": set(), "interactive": [], "controls_without_tooltip": set()}
states = []
for tab in ("Signals", "Excitation", "Emission", "Detected", "Förster radius"):
    states.append(lambda t=tab: d.click_text(t))
states.append(lambda: d.click_text("Easy Mode"))
states.append(lambda: (d.click_text("Optical Components"), d.click_text("Backend"), d.click_text("Connections"), d.click_text("MMFDB", last=True)))
for step in states:
    step(); d.draw(3)
    inv = emtk_inventory(app, (1200, 800))
    merged["controls"] |= set(inv["controls"]); merged["controls_without_tooltip"] |= set(inv["controls_without_tooltip"])
    seen = {(r["kind"], r["label"]) for r in merged["interactive"]}
    merged["interactive"] += [r for r in inv["interactive"] if (r["kind"], r["label"]) not in seen]
app.close()
result = {"size": [1200, 800], "controls": sorted(merged["controls"]), "interactive": merged["interactive"],
          "controls_without_tooltip": sorted(merged["controls_without_tooltip"]), "qt_free": qt_free("lightpath_simulator")}
(out / "after.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
print("after:", len(result["controls"]), "controls,", len(result["controls_without_tooltip"]), "without tooltip, qt-free", result["qt_free"]["ok"])
