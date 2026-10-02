"""after.json over both tabs, populated, then `compare`. Usage: <out_dir> (after `python -m test.gui.emtk_port_parity after vv_vh_g_factor --out <out_dir>`)."""
import test.gui.emtk_port_parity as parity  # noqa (first: the stdlib "test" must not win)
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from make_data import make_data
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.vv_vh_g_factor.gui.app import create_app
out = pathlib.Path(sys.argv[1]); files = make_data(tempfile.mkdtemp())
app = create_app(); m = app.model
m.fp_dt_ns = 0.05; m.load(files["fast"]); m.load(files["slow"], slow=True); m.background = True; m.manual_g = m.manual_tau = m.manual_rs = m.manual_l = True; m.compute()
m.batch_files = [files["batch1"]]; m.compute_batch()
data = json.loads((out / "after.json").read_text()); controls = set(data["controls"]); rows = {r["id"]: r for r in data["interactive"]}
d = Driver(app)
for tab in ("Batch anisotropy", "G-factor and mixing"):
    d.draw(); 
    try: d.click_text(tab)
    except AssertionError: pass
    inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
    for r in inv["interactive"]: rows[r["id"]] = r
data["controls"] = sorted(controls); data["interactive"] = list(rows.values())
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip"))
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)); print(len(controls), data["controls_without_tooltip"])
