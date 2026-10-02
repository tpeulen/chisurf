"""The emtk app of an imaging pixel plugin in its populated state, every tab visited: after.json and the screenshots.
Usage: capture_emtk_after_pixel.py <plugin_id> <out_dir>. Temporary settings and HOME; the real ~/.chisurf is checked unchanged."""
import json, os, pathlib, sys, tempfile
from test.gui.emtk_port_parity import emtk_inventory, emtk_screenshot, qt_free  # before chisurf: chisurf puts ndxplorer's own `test` first

tmp = pathlib.Path(tempfile.mkdtemp())
REAL = pathlib.Path.home() / ".chisurf"
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
(tmp / "home").mkdir()


def main():
    import importlib
    from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    pid, out = sys.argv[1], pathlib.Path(sys.argv[2])
    before = data.real_settings_state()
    app = importlib.import_module(f"chisurf.plugins.microscopy.{pid}.gui.app").make_app()
    drv = Driver(app, (1200, 800))
    path = data.tiff_pair(tmp / "pair.tif") if pid == "img_coloc" else data.flim_ptu(tmp / "flim.ptu", n_channels=2 if pid == "img_pixel_mle" else 1)
    union, missing = set(), set()

    def shot(name, size=(1200, 800)):
        app.pointer_move(-1.0, -1.0)
        emtk_screenshot(app, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)

    if pid == "img_pixel_mle":
        m = app.model
        m.add_files([path]); m.add_irf([data.irf_ptu(tmp / "irf.ptu")])
        m.channels_parallel_text, m.channels_perpendicular_text, m.micro_time_stop, m.min_photons = "0", "1", 250, 3
        drv.click("request_run")
    elif pid == "img_coloc":
        app.model.open_path(path)
        app.model.ccf_max_shift, app.model.object_analysis = 8, True
        drv.click("run_coloc")
    else:
        app.model.open_path(path)
        drv.click("run_maps")
    drv.settle(timeout=300)
    for tab in list(app.windows):
        app.docks.focus(tab); drv.draw(3)
        inv = emtk_inventory(app, (1200, 800))
        union |= set(inv["controls"]); missing |= set(inv["controls_without_tooltip"])
        key = tab.replace(" ", "_").replace("(", "").replace(")", "")
        shot(key); shot(key, (800, 600))
    # every folding panel open: the controls inside are on screen for the inventory (and one screenshot shows them)
    def panels(sections):
        for sec in sections:
            if sec.get("collapsible"):
                yield sec["title"]
            yield from panels(sec.get("sections", []))

    for title in panels(app.spec["sections"]):
        app.form.folds[title] = True
    for tab in list(app.windows):
        app.docks.focus(tab); drv.draw(3)
        union |= set(emtk_inventory(app, (1200, 800))["controls"]); missing |= set(emtk_inventory(app, (1200, 800))["controls_without_tooltip"])
    app.docks.focus(next(iter(app.windows))); drv.draw(3); shot("all_folds_open")
    if pid == "img_coloc":
        app.docks.focus("Intensity scatter"); drv.draw(3)
        drv.click_text_scrolling("> Analysis regions"); drv.click_text_scrolling("Add rectangle"); drv.settle(timeout=120)
        union |= set(emtk_inventory(app, (1200, 800))["controls"])
        shot("with_gate"); shot("with_gate", (800, 600))
    if pid in ("img_pixel_phasor", "img_pixel_nb"):
        app.docks.focus("Phasor plot" if pid == "img_pixel_phasor" else "Parameter plane"); drv.draw(3)
        drv.click_text_scrolling("> Analysis regions"); drv.click_text_scrolling("Add ellipse"); drv.draw(3)
        union |= set(emtk_inventory(app, (1200, 800))["controls"])
        shot("with_cursor"); shot("with_cursor", (800, 600))
    drv.click("help"); shot("help"); drv.escape()
    drv.click("guide"); shot("guide"); app.tour.stop()
    app.model.folder = str(tmp)
    if pid not in ("img_pixel_mle", "img_coloc"):
        drv.click("request_hdf5"); drv.draw(2); shot("hdf5_dialog")
    elif pid == "img_coloc":
        drv.click("request_export"); drv.draw(2); shot("export_dialog")
    else:
        drv.click("sel_files.add"); drv.draw(2); shot("add_files_dialog")
    (out / "after.json").write_text(json.dumps({"size": [1200, 800], "controls": sorted(union), "interactive": [],
                                                "controls_without_tooltip": sorted(missing), "qt_free": qt_free(pid)}, indent=2, ensure_ascii=False))
    assert data.real_settings_state() == before, "the real ~/.chisurf was touched"
    print(len(union), "controls;", len(missing), "without tooltip; real ~/.chisurf unchanged")


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    main()
