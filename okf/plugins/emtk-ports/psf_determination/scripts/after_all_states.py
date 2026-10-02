"""after.json with a stack loaded, beads detected and fitted, every profile tab, the dataset picker, the file dialog, the help window and the non-auto levels; then `compare`. Usage: <out_dir>."""
import test.gui.emtk_port_parity as parity  # noqa (first: the stdlib "test" must not win)
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
st.chisurf_settings_path = pathlib.Path(tempfile.mkdtemp())
from make_data import make_stack
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.microscopy.psf_determination.gui.app import make_app
out = pathlib.Path(sys.argv[1]); app = make_app(); m = app.model
m.pixel_size_nm, m.z_step_nm = 100.0, 300.0; m.set_stack(make_stack()); m.detect_beads(); m.fit_all(); m.selected_bead = (10, 20, 20); m.fit_selected(); app.canvas.z = 10
d = Driver(app); d.draw(3)
data = json.loads((out / "after.json").read_text()); controls = set(data["controls"]); rows = {r["id"]: r for r in data["interactive"]}
def grab():
    global controls
    inv = parity.emtk_inventory(app, parity.SIZES[0]); controls |= set(inv["controls"])
    for r in inv["interactive"]: rows[r["id"]] = r
grab()
for tab in ("y profile", "z profile", "x profile"):
    d.click_text(tab); grab()
d.click_text("Automatic levels"); grab(); d.click_text("Automatic levels")
d.click_text("magma"); grab(); d.escape()
app.help_window.show(); d.draw(2); grab(); app.help_window.hide() if hasattr(app.help_window, "hide") else None
data["controls"] = sorted(controls); data["interactive"] = list(rows.values())
data["controls_without_tooltip"] = sorted(r["label"] for r in rows.values() if not r.get("tooltip"))
(out / "after.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)); print(len(controls), data["controls_without_tooltip"])
