"""after.json with a trace loaded, a fit and a scan done, the Fitting and State scan sections open, every plot tab, then `compare`. Usage: <out_dir>."""
import test.gui.emtk_port_parity as parity  # noqa (first: the stdlib "test" must not win)
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from make_data import make_trace
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.core.hmm.gui.app import make_app
out = pathlib.Path(sys.argv[1]); app = make_app(); m = app.model
m.set_traces([make_trace()[0]], ["trace.csv"]); m.n_states = 3; m.time_step = 0.001; m.max_states = 5; m.run(); m.run_scan()
d = Driver(app); d.draw(3)
data = json.loads((out / "after.json").read_text()); controls = set(data["controls"]); rows = {r["id"]: r for r in data["interactive"]}
def grab():
    global controls
    inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
    for r in inv["interactive"]: rows[r["id"]] = r
grab(); d.click_text("> Fitting"); d.click_text("> State scan range"); grab()
for tab in ("Dwell times", "Scan", "Histogram"):
    d.click_text(tab, last=False); grab()
for name in ("covariance_type", "decode"):
    d.draw(2); d.click(app.forms["model" if name == "covariance_type" else "fitting"].rects[name]); grab(); d.escape()
app.help_window.show(); d.draw(2); grab()
data["controls"] = sorted(controls); data["interactive"] = list(rows.values())
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip"))
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)); print(len(controls), data["controls_without_tooltip"])
