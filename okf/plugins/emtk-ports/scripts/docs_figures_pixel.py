"""The figures of the imaging pixel guides (24_scan_images, 38_colocalization, 67_number_and_brightness), drawn from the emtk apps in a populated state.

Usage: docs_figures_pixel.py [24|38|67 ...]. Temporary settings and HOME; the data are the seeded synthetic streams of ``pixel_testing`` and the plugin's N&B demo.
"""
import os, pathlib, sys, tempfile

from test.gui.emtk_port_parity import emtk_screenshot  # before chisurf: chisurf puts ndxplorer's own `test` first

tmp = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
(tmp / "home").mkdir()
FIG = pathlib.Path("docs/guides/figures")
SIZE = (1200, 800)


def shot(app, name):
    app.pointer_move(-1.0, -1.0)
    emtk_screenshot(app, FIG / name, SIZE)


def main():
    from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    which = set(sys.argv[1:]) or {"24", "38", "67"}
    if "24" in which:
        from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app as intensity
        from chisurf.plugins.microscopy.img_pixel_micro_time.gui.app import make_app as micro
        from chisurf.plugins.microscopy.img_pixel_phasor.gui.app import make_app as phasor
        from chisurf.plugins.microscopy.img_pixel_mle.gui.app import make_app as mle
        f = data.flim_ptu(tmp / "flim.ptu")
        f2 = data.flim_ptu(tmp / "flim2.ptu", n_channels=2)
        irf = data.irf_ptu(tmp / "irf.ptu")
        for make, tab, name in ((intensity, "Intensity", "24_intensity_tool.png"), (micro, "Mean micro-time (ns)", "24_micro_time_tool.png"), (phasor, "Phasor plot", "24_phasor_tool.png")):
            app = make(); drv = Driver(app, SIZE)
            app.model.open_path(f); drv.click("run_maps"); drv.settle(timeout=300)
            if name.endswith("phasor_tool.png"):
                app.docks.focus("Phasor plot"); drv.draw(3)
                drv.click_text_scrolling("> Analysis regions"); drv.click_text_scrolling("Add ellipse")
                roi = app.model.cursors.get("Ellipse").roi
                roi.cx, roi.cy, roi.rx, roi.ry = 0.89, 0.38, 0.12, 0.1
                app.model.notify_cursors()
            app.docks.focus(tab); drv.draw(3); shot(app, name)
        app = mle(); drv = Driver(app, SIZE); m = app.model
        m.add_files([f2]); m.add_irf([irf]); m.channels_parallel_text, m.channels_perpendicular_text, m.micro_time_stop, m.min_photons = "0", "1", 250, 3
        drv.click("request_run"); drv.settle(timeout=300); app.docks.focus("Lifetime map"); drv.draw(3); shot(app, "24_mle_tool.png")
    if "38" in which:
        from chisurf.plugins.microscopy.img_coloc.gui.app import make_app
        pair = data.tiff_pair(tmp / "pair.tif")
        app = make_app(); drv = Driver(app, SIZE)
        drv.type_into("filename", pair); drv.settle(timeout=120)
        app.docks.focus("Coefficients"); drv.draw(3); shot(app, "coloc_workspace.png")
        app.model.ccf_max_shift = 8; app.model.object_analysis = True; app.model.object_distance = 4.0; app.model.compute(); drv.settle(timeout=120)
        for tab, name in (("Objects", "coloc_objects.png"), ("Object distances", "coloc_object_distances.png")):
            app.docks.focus(tab); drv.draw(3); shot(app, name)
        app.model.gate_enabled = True
        app.model.gate_a_min, app.model.gate_a_max, app.model.gate_b_min, app.model.gate_b_max = 25.0, 110.0, 20.0, 110.0
        app.model.compute(); drv.settle(timeout=120)
        app.docks.focus("Intensity scatter"); drv.draw(3); shot(app, "coloc_scatter.png")
    if "67" in which:
        from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app
        app = make_app(); drv = Driver(app, SIZE)
        drv.click("demo"); drv.settle(timeout=300)
        app.docks.focus("Brightness ε"); drv.draw(3); shot(app, "nb_brightness_map.png")
        m = app.model
        app.docks.focus("Parameter plane"); drv.draw(3)
        drv.click_text_scrolling("> Analysis regions"); drv.click_text_scrolling("Add rectangle"); drv.settle(timeout=60)
        x0, x1, y0, y1 = m.plane_extent()
        roi = m.gates.get("Rectangle").roi
        roi.x0, roi.x1, roi.y0, roi.y1 = x0, x1, 1.75, y1
        m.notify_gates(); drv.draw(3); shot(app, "nb_parameter_plane.png")


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    main()
