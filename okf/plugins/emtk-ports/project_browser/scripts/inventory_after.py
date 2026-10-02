"""after.json of the populated window: the union of the control inventories of the browser (expanded, a version selected), every details tab and the
Save and Delete dialogs. Usage: inventory_after.py <out_dir>. Hermetic (temp HOME, settings, scratch database)."""
import json, os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pb_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "projects.sqlite"))
out = pathlib.Path(sys.argv[1]).resolve()
(tmp / "home").mkdir(); os.chdir(tmp)
from types import SimpleNamespace
from test.gui.emtk_port_parity import emtk_inventory, qt_free
from chisurf.macros.core_fit import get_project_payload
from chisurf.plugins.core.project_browser.gui.app import ProjectBrowserApp
from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient
from chisurf.plugins.core.project_browser.gui.model import ProjectBrowserModel
from chisurf.plugins.core.project_browser.test.driving import BrowserDriver
from chisurf.plugins.core.project_browser.test import test_emtk_project_browser_clicks as T

client = ProjectBrowserClient(inprocess=True)
payload = get_project_payload("decay study").to_dict()
first = client.save_project(project_name="decay study", project_payload=payload, notes="first fit", visibility="private", fit_count=0, dataset_count=0)
client.save_project(project_name="decay study", project_payload=payload, project_id=first["project_id"], parent_version_id=first["version_id"],
                    notes="refit with IRF", visibility="private", fit_count=0, dataset_count=0)
client.save_project(project_name="fcs titration", project_payload=get_project_payload("fcs titration").to_dict(), notes="public set", visibility="public", fit_count=0, dataset_count=0)
app = ProjectBrowserApp(model=ProjectBrowserModel(context=SimpleNamespace(), payload_provider=lambda n: {"datasets": {}, "fits": [], "name": n}))
d = BrowserDriver(app); d.settle(); d.draw(3)
T.expand(d, "decay study"); T.select(d, "v2 decay study"); d.click("inspect"); d.settle()
merged = {"controls": set(), "interactive": [], "controls_without_tooltip": set()}


def take():
    inv = emtk_inventory(app, (1200, 800))
    merged["controls"] |= set(inv["controls"]); merged["controls_without_tooltip"] |= set(inv["controls_without_tooltip"])
    seen = {(r["kind"], r["label"]) for r in merged["interactive"]}
    merged["interactive"] += [r for r in inv["interactive"] if (r["kind"], r["label"]) not in seen]


for tab in ("Summary", "Artifacts", "Parameters", "Branches", "Version graph"):
    d.click_text(tab); d.draw(3); take()
d.click("save"); d.draw(3); take(); d.click_text("Cancel")
d.click("delete"); d.draw(3); take(); d.click_text("Cancel")
app.close()
result = {"size": [1200, 800], "controls": sorted(merged["controls"]), "interactive": merged["interactive"],
          "controls_without_tooltip": sorted(merged["controls_without_tooltip"]), "qt_free": qt_free("project_browser")}
(out / "after.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
print("after:", len(result["controls"]), "controls,", len(result["controls_without_tooltip"]), "without tooltip, qt-free", result["qt_free"]["ok"])
