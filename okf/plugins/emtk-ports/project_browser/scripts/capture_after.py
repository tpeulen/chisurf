"""Captures of the emtk project browser, states reached with real pointer and key input. Usage: capture_after.py <out_dir> <prefix>.

Hermetic: temp HOME, settings and a scratch project database with 'decay study' (2 versions) and 'fcs titration' (public)."""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pb_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "projects.sqlite"))
out = pathlib.Path(sys.argv[1]).resolve(); prefix = sys.argv[2]
(tmp / "home").mkdir(); os.chdir(tmp)
from types import SimpleNamespace
from emtk import testing
from emtk.testing import PixelPainter
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
restored = []
model = ProjectBrowserModel(context=SimpleNamespace(), payload_loader=restored.append, window_restorer=lambda p: None,
                            payload_provider=lambda name: {"datasets": {}, "fits": [], "name": name})
SIZES = ((1200, 800), (800, 600))
empty_app = ProjectBrowserApp(model=ProjectBrowserModel(context=SimpleNamespace(), client=object()), autoload=False)
app = ProjectBrowserApp(model=model)
drv = BrowserDriver(app, SIZES[0])


def shot(name, sizes=SIZES, a=None):
    a = a or app
    for size in sizes:
        drv.size = size
        for _ in range(3):
            p = PixelPainter(*size); a.draw(p, 0.0, 0.0, float(size[0]), float(size[1]))
        (out / f"{prefix}_{name}_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
    drv.size = SIZES[0]


shot("empty", a=empty_app)                    # nothing loaded: the message and the greyed actions
drv.settle(); drv.draw(3)
shot("populated")                              # the two projects, collapsed (the Qt first state)
T.expand(drv, "decay study"); T.select(drv, "v2 decay study")
shot("expanded_selected")                      # the Qt expanded/selected state: Open, Export, Delete, Inspect enabled
drv.click("inspect"); drv.settle(); drv.click_text("Summary"); shot("details_summary", SIZES[:1])
drv.click_text("Version graph"); shot("details_graph", SIZES[:1]); drv.click_text("Summary")
drv.click("show_id"); drv.click("show_status"); shot("id_and_status_columns")
drv.click("show_id"); drv.click("show_status")
x, y = T.centre(T.row_rect(drv, "v1 decay study")); T.press_on(drv, x, y, 2); shot("context_menu", SIZES[:1]); T.press_on(drv, 600, 700)
drv.type_into("search", "fcs"); drv.settle(); shot("search_fcs", SIZES[:1]); drv.click("clear_search"); drv.settle()
drv.click("save"); drv.draw(3); drv.click_text("Save version"); drv.settle(); shot("save_dialog_error", SIZES[:1])
drv.type_into("name", "native project"); drv.click("visibility_name"); drv.click_text("Public", last=True)
drv.click("notes", fx=0.3, fy=0.2); drv.type_text("first native version"); shot("save_dialog_filled", SIZES[:1]); drv.click_text("Save version"); drv.settle()
shot("after_save", SIZES[:1])
T.select(drv, "v2 decay study") if any(s.startswith("v2 decay study") for s in drv.draw(2).strings) else (T.expand(drv, "decay study"), T.select(drv, "v2 decay study"))
drv.click("delete"); shot("delete_confirm", SIZES[:1]); drv.click_text("Cancel")
drv.click("export"); shot("export_dialog", SIZES[:1])
name = next(s for s in drv.draw(2).strings if s.endswith("_v2.cs.pto")); drv.click_text(name); drv.select_all(); drv.type_text("decay_export"); drv.click_text("Save", last=True); drv.settle()
shot("exported", SIZES[:1])
drv.click("import_project"); drv.click_text("decay_export.cs.pto"); drv.click_text("Open", last=True); drv.settle(); shot("import_confirm_collisions", SIZES[:1]); drv.click_text("Cancel")
drv.click("guide"); drv.click_text("Next ►"); shot("guide_refresh_step", SIZES[:1]); drv.escape()
drv.click("help"); shot("help", SIZES[:1]); drv.escape()
app.close(); empty_app.close()
print("ok")
