"""after.json over EVERY step in a populated state (the tool's own `after` draws only the first one), then `compare`.
Usage: <out_dir>. Run after `python -m test.gui.emtk_port_parity after tr_anisotropy --out <out_dir>` (screenshots, qt-free)."""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from test.gui.emtk_port_parity import SIZES, emtk_inventory
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app

out = pathlib.Path(sys.argv[1])
files = make_data(pathlib.Path(tempfile.mkdtemp()) / "data")
app = make_app(); m = app.model
for k, p in files.items():
    setattr(m, k + "_path", p)
m.load_data()
data = json.loads((out / "after.json").read_text())
controls, rows = set(data["controls"]), {r["id"]: r for r in data["interactive"]}
for stacked in (False, True):
    m.stacked_files = stacked
    for step in range(6):
        app.select_step(step)
        inv = emtk_inventory(app, SIZES[0])
        controls |= set(inv["controls"])
        for r in inv["interactive"]:
            rows[r["id"]] = r
data["controls"] = sorted(controls)
data["interactive"] = list(rows.values())
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip"))
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(len(controls), "controls;", len(data["controls_without_tooltip"]), "without tooltip")
