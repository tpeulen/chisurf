"""after.json: the union of the control inventories of the populated window (default and an Airy / linear state, the slice sections, the export dialog).
`emtk_port_parity after` inventories one default frame. Usage: inventory_after.py <out_dir>. Hermetic."""
import json, os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="psf_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "p.sqlite"))
out = pathlib.Path(sys.argv[1]).resolve()
(tmp / "home").mkdir(); os.chdir(tmp)
from test.gui.emtk_port_parity import emtk_inventory, qt_free
from chisurf.plugins.calculator.psf_calculator.gui.app import make_app
from chisurf.plugins.calculator.psf_calculator.tests.driving import PSFDriver
from chisurf.plugins.calculator.psf_calculator.tests import test_emtk_psf_clicks as T

app = make_app(); app.model.nxy, app.model.nz = 24, 7
d = PSFDriver(app); d.settle()
merged = {"controls": set(), "interactive": [], "controls_without_tooltip": set()}


def take():
    inv = emtk_inventory(app, (1200, 800))
    merged["controls"] |= set(inv["controls"]); merged["controls_without_tooltip"] |= set(inv["controls_without_tooltip"])
    seen = {(r["kind"], r["label"]) for r in merged["interactive"]}
    merged["interactive"] += [r for r in inv["interactive"] if (r["kind"], r["label"]) not in seen]


take()
for field in ("model", "polarization", "colormap", "slice_plane"):  # the entries of a choice show while its list is open
    d.click(field); d.draw(3); take(); d.escape(); d.draw(2)
T.pick(d, "polarization", "Linear at angle"); d.draw(3); take()
T.pick(d, "model", "Airy (scalar, 2-D)"); d.draw(3); take()
T.pick(d, "slice_plane", "XZ"); d.draw(3); take()
d.click("export_npy"); d.draw(3); take(); d.click_text("Cancel")
app.close(); app._executor.shutdown(wait=True)
result = {"size": [1200, 800], "controls": sorted(merged["controls"]), "interactive": merged["interactive"],
          "controls_without_tooltip": sorted(merged["controls_without_tooltip"]), "qt_free": qt_free("psf_calculator")}
(out / "after.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
print("after:", len(result["controls"]), "controls,", len(result["controls_without_tooltip"]), "without tooltip, qt-free", result["qt_free"]["ok"])
