"""after.json over lifetime and FRET mode, populated, L-curve/sampling section open, JSON editor open; then `compare`. Usage: <out_dir>."""
import test.gui.emtk_port_parity as parity  # noqa (first: the stdlib "test" must not win)
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
from stub_fit import stub_fit
import numpy as np
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app
out = pathlib.Path(sys.argv[1]); st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
app = make_app(); m = app.model; m.load_fit(stub_fit()); m.settings.tau_bins = 32; m.settings.tau_max = 8.0
import chisurf
chisurf.fits = [stub_fit()]; chisurf.imported_datasets = [stub_fit().data]
app.refresh_sources(); m.run()
d = Driver(app); d.draw(3)
data = json.loads((out / "after.json").read_text()); controls = set(data["controls"]); rows = {r["id"]: r for r in data["interactive"]}
def grab():
    global controls
    inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
    for r in inv["interactive"]: rows[r["id"]] = r
grab()
d.wheel(120, 400, -10.0); d.draw(3); d.click_text("> L-curve span and sampling"); d.wheel(120, 400, -10.0); grab()
m.settings.mode = "fret"; m.donor = np.array([1.0, 4.1]); d.wheel(120, 400, 30.0); grab()
m.settings.mode = "lifetime"; app.open_settings(); d.draw(2); grab(); app.edit_settings = False
data["controls"] = sorted(controls); data["interactive"] = list(rows.values())
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip"))
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)); print(len(controls), data["controls_without_tooltip"])
