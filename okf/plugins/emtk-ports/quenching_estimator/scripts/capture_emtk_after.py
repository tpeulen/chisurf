"""The native QuEst window (the Structure Tools card hosted by the plugin): empty, structure loaded, after the (failing) run.
Usage: <out_dir>. Hermetic (temporary HOME/settings/MMFDB); no network; the structure is quest's own test file."""
import os, pathlib, sys, tempfile, time
tmp = pathlib.Path(tempfile.mkdtemp(prefix="quest_after_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
(tmp / "s").mkdir(); (tmp / "home").mkdir()
import json
from test.gui.emtk_port_parity import emtk_inventory, qt_free
from emtk.pil_painter import PilPainter
from emtk.testing import png_encode
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.quenching_estimator.gui.app import make_app
PDB = "/Users/tpeulen/dev/quest/tests/148l.pdb"
out = pathlib.Path(sys.argv[1]); union, missing = set(), set()
def shot(app, name, size):
    app.pointer_move(-1.0, -1.0)
    for _ in range(3):
        p = PilPainter(*size); app.draw(p, 0, 0, *size)
    (out / f"after_populated_{name}_{size[0]}x{size[1]}.png").write_bytes(png_encode(p.width, p.height, p.px))
    inv = emtk_inventory(app, size); union.update(inv["controls"]); missing.update(inv["controls_without_tooltip"])
for size in ((1200, 800), (800, 600)):
    app = make_app(); ui = Driver(app, size); ui.draw(3)
    shot(app, "empty", size)
    app.session.load_structure(PDB); m = app.session.model
    m.attachment_chain, m.attachment_residue, m.attachment_atom = "E", 117, "CB"
    m.n_photons, m.t_max, m.parallel_trajectories = 1000, 50.0, 1
    ui.draw(3); shot(app, "structure_loaded", size)
    ui.click("simulate")
    end = time.monotonic() + 120
    while app.session.running and time.monotonic() < end:
        time.sleep(0.05); ui.draw(1)
    ui.draw(3); shot(app, "after_run_failure", size)
    for tab in ("3D Structure", "Quenching Chemistry", "Project JSON", "Plots & Dynamics"):
        ui.click(f"tab_{tab}"); ui.draw(3); shot(app, "tab_" + tab.replace(" ", "_").replace("&", "and"), size)
    for title in ("Structure", "Dye", "Simulation", "Quenching", "FRET", "Advanced"):     # every panel open: the inventory sees every field
        app.form.folds[title] = True
    ui.click("tab_Plots & Dynamics"); ui.draw(4); shot(app, "all_panels_open", size)
    app.close()
(out / "after.json").write_text(json.dumps({"controls": sorted(union), "controls_without_tooltip": sorted(missing),
                                            "qt_free": qt_free("quenching_estimator", "chisurf.plugins.quenching_estimator.gui.app:make_app")}, indent=2))
print(len(union), "controls;", len(missing), "without tooltip")
