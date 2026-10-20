#!/usr/bin/env python
"""Generate GUI screenshots for the TTTR-LUT tutorial (headless, offscreen).

Draws the real emtk apps offscreen (``PilPainter``) so the tutorial shows the actual UI,
not mockups. Run with the project on the path::

    PYTHONPATH=. python docs/guides/make_screenshots.py

Requires the full GUI environment (the arm64 conda env), unlike
``make_figures.py`` which only needs matplotlib.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import time

# LLTF's fitter calls plt.show(); keep it off-screen.
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chisurf_grab_settings_"))
import chisurf.core.settings  # noqa: E402,F401

FIG =pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)
_SPC_FILE = pathlib.Path("test") / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
_PDB_148L = pathlib.Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve()
_T4L = pathlib.Path("chisurf/plugins/modelling/fret/examples/olga_t4l")
_T4L_TOP = _T4L / "3GUN_NMSim_cl-rep-001.pdb"
_T4L_DCD = _T4L / "3GUN_NMSim_cl-rep_894.dcd"


def _grab_ndx_overlay_axes():
    """Measured MFD bursts: pushing a FRET line selects its lifetime/E projection."""
    from chisurf.plugins.fret_line.gui.model import FretLineModel, push_to_ndx
    from chisurf.plugins.ndxplorer.gui.app import make_app

    source = pathlib.Path("modules/ndxplorer/tests/mfd/burstwise_All 0.1500#30")
    with tempfile.TemporaryDirectory(prefix="ndx-overlay-", dir=os.environ.get("TMPDIR")) as folder:
        copied = pathlib.Path(folder) / source.name
        shutil.copytree(source, copied)
        app = make_app(session_autosave=False)
        app.open_path(str(copied))
        tool = FretLineModel()
        try:
            assert app.model.has_data, app.model.error
            app.model.set_parameter("x", "FRET efficiency")
            app.model.set_parameter("y", "Tau (green)")
            tool.minimum, tool.maximum, tool.tau_d0 = 20.0, 120.0, 4.0
            tool.add_line()
            tool.push_callback = push_to_ndx
            tool.push()
            assert not tool.dialog_text, tool.dialog_text
            assert (app.model.x.name, app.model.y.name) == ("Tau (green)", "FRET efficiency")
            app.docks.focus("Overlays")
            _native_shot(app, "ndxplorer_overlay_axes.png", size=(900, 600))
        finally:
            app.close()
            tool.close()


def _grab_parameter_link_menu():
    """Grab the parameter link menu of the emtk shell for the linking reference.

    Two FCS fits (Kristine_with_error and the FCS demo, the general diffusion
    model); the link menu of the first fit's N is opened from its parameter
    table with *Link N to* and the second fit expanded, then the Analysis dock and
    the open menu are cropped out of the 1500x950 shell.
    """
    import io
    import sys

    from PIL import Image

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from screenshots.shell_driver import idle, shell

    from chisurf.core.experiments.fcs.demo import DEMO, make_demo
    from chisurf.emtk.model_sections import LinkMenu
    from test.native_emtk.test_emtk_shell_fits import KRISTINE, MODEL, _add_fit, _load

    driver, wait = shell(size=(1500, 950))
    app = driver.app
    _load(driver, app, KRISTINE)
    first = _add_fit(driver, app)
    _load(driver, app, make_demo(), DEMO["experiment"], DEMO["reader"])
    result = app.data.session.api.add_fit(
        [len(app.data.datasets.datasets) - 1], model_name=MODEL
    )
    wait(lambda: idle(app) and result.get("uid") in app.data.windows)
    app.data.show_fit(first)
    wait(lambda: idle(app) and app.data.analysis.info)
    fits: list = []
    app.data.read_fits_for_links(fits.extend)
    wait(lambda: idle(app) and fits)
    record = next(p for p in app.data.analysis.parameters if p["name"] == "N")
    views = app.data.editor.sections
    menu = LinkMenu(views, record, fits, (150.0, 812.0))
    views.dialogs.append(menu)
    link_to = menu.panel.entries[0]
    link_to.open = True
    link_to.entries[1].open = True
    driver.frame(4)
    driver.hover((1400.0, 900.0))
    driver.frame(3)
    image = Image.open(io.BytesIO(driver.screenshot()))
    image.crop((0, 520, 1000, 950)).save(FIG / "parameter_link_menu.png")
    app.close()
    print("wrote parameter_link_menu.png")


def _grab_burst_browser():
    """Guide 28: the native Burst Browser on the real sm-DNA burst folder, histogram of E."""
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    folder = pathlib.Path(
        "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/bi4_bur"
    ).resolve()
    app = app_from("burst_browser")
    driver = Driver(app, (1400, 860))
    driver.frame(2)
    app.load_folder(folder)
    wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1])
    options = app.model.hist_column_options()
    for column in ("FRET Efficiency", "E", "Proximity Ratio"):
        if column in options:
            app.model.hist_column = column
            break
    app.model.refresh()
    driver.frame(4)
    print("burst browser:", app.model.status_text(), "| hist", app.model.hist_column, flush=True)
    driver.screenshot(FIG / "burst_browser.png")
    print("wrote burst_browser.png", flush=True)
    app.close()


def _grab_2cde_tool():
    """Grab the native FRET-2CDE window on the plugin's demo folder (static and dynamic bursts)."""
    from emtk.testing import Driver
    from screenshots.emtk_shot import app_from, wait

    from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build

    folder = build(pathlib.Path(tempfile.mkdtemp(prefix="2cde_")) / "measurement")
    app = app_from("burst_2cde")
    driver = Driver(app, (1100, 720))
    driver.frame(3)
    app.model.donor_channels_text, app.model.acceptor_channels_text = "0", "1"
    app.controller.on_paths_dropped([folder])
    driver.frame(2)
    app.controller.run()
    wait(driver, lambda: not app.controller.running, timeout=300)
    driver.hover((12.0, 708.0))
    driver.frame(2)
    driver.screenshot(FIG / "burst_2cde_tool.png")
    print("wrote burst_2cde_tool.png:", app.model.status_text, flush=True)
    app.controller.close()


def _emtk_enter(driver, field, text):
    """Type *text* into the one-line field *field* of a native app and press Enter, as a person does."""
    from emtk import keys
    from emtk.events import CONTROL_MODIFIER

    driver.click(field)
    driver.press(ord("A"), CONTROL_MODIFIER)
    driver.type(str(text))
    driver.press(keys.KEY_RETURN)
    driver.frame(2)


def _emtk_park(driver):
    """Move the pointer to the empty bottom-left corner so no tooltip covers the figure."""
    driver.hover((12.0, float(driver.size[1]) - 12.0))
    driver.frame(2)


def _grab_drift_tool():
    """Grab the drift-correction workspace and its projections (guide 43).

    A synthetic stack with a *known* linear drift, so the trace in the figure is
    the ground truth and the before/after projections differ visibly. The real
    confocal test image is a stable acquisition with sub-pixel drift, which
    would make an honest but entirely uninformative screenshot.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    from chisurf.core.fio.image import imwrite

    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:64, 0:64]
    base = sum(
        90.0 * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 3.0**2))
        for cy, cx in rng.integers(8, 56, size=(14, 2))
    ) + rng.poisson(4.0, (64, 64))
    stack = np.stack([np.roll(base, (2 * k, -k), axis=(0, 1)) for k in range(12)]).astype(
        np.float32
    )
    path = pathlib.Path(tempfile.mkdtemp()) / "drift_demo.tif"
    imwrite(path, stack, axes="TYX")

    app = app_from("img_drift")
    driver = Driver(app, (1400, 820))
    driver.frame(2)
    _emtk_enter(driver, "filename", path)
    wait(driver, lambda: not app.job.busy)
    _emtk_park(driver)
    driver.screenshot(FIG / "drift_workspace.png")
    print("wrote drift_workspace.png", flush=True)
    # Both projections are drawn side by side on the Projection tab; the guide shows them one by one.
    app.docks.focus("Projection")
    driver.frame(4)
    _emtk_park(driver)
    from PIL import Image

    shot = FIG / "drift_projection.png"
    driver.screenshot(shot)
    image = Image.open(shot)
    for name, box in (("drift_before.png", (565, 20, 972, 810)), ("drift_after.png", (975, 20, 1385, 810))):
        image.crop(box).save(FIG / name)
        print("wrote", name, flush=True)
    shot.unlink()


def _grab_precision_tool():
    """Grab the RICS-precision calculator (guide 45).

    The tool needs no data at all -- it answers from the settings alone -- so
    this is simply the default acquisition, predicted. The default deliberately
    sits *beside* the optimum rather than on it, so the figure shows the marker
    off the minimum, which is the thing the tool exists to tell you.
    """
    from screenshots.emtk_shot import app_from, render, wait

    app = app_from("rics_precision")
    from emtk.testing import Driver

    driver = Driver(app, (1400, 760))
    driver.frame(2)
    app.predict()
    wait(driver, lambda: not app.job.busy)
    render(app, "precision_workspace.png", driver=driver)


def _grab_frc_tool():
    """Grab the FRC resolution panel (guide 51).

    Driven with the real confocal photon stream in the test data, so the figure
    shows an honest curve on honest photons: a 256x256 scan of a cell whose
    even/odd frame halves stop agreeing a few pixels in. The pixel size is the
    80 nm of that acquisition, so the headline is in nanometres.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    app = app_from("img_frc")
    driver = Driver(app, (1500, 850))
    driver.frame(2)
    _emtk_enter(driver, "filename", pathlib.Path("test/data/clsm/PQ_Olympus_MFIS.ht3").resolve())
    wait(driver, lambda: not app.job.busy)
    app.model.pixel_size_nm = 80.0
    driver.click("measure")
    wait(driver, lambda: not app.job.busy)
    _emtk_park(driver)
    driver.screenshot(FIG / "frc_workspace.png")
    print("wrote frc_workspace.png", flush=True)


def _grab_burst_gs_tool():
    """Grab the native photon-by-photon kinetics tool (guide 49).

    Fitted on the window's own default simulation (two states, 3000 and 1000 s^-1
    at E = 0.25 / 0.75, 200 bursts of 200 photons, seed 1) exactly as a person who
    opens it and presses *Fit* sees it, so the figure can be read against the
    truth. Two grabs: the fitted report and rates, and the transition-time scan
    (the part of the tool with no binned equivalent).
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    app = app_from("burst_gs")
    driver = Driver(app, (1440, 860))
    driver.frame(2)
    app.model.use_simulation = True  # the *Simulate* tick: no burst tables needed
    app.controller.run()
    wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1], timeout=600)
    print("burst_gs:", " ".join(app.model.results_text.split())[:400], flush=True)
    driver.screenshot(FIG / "burst_gs_workspace.png")
    print("wrote burst_gs_workspace.png", flush=True)

    app.model.scan_transition_time = True
    app.model.transit_points = 30
    app.controller.run()
    wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1], timeout=900)
    driver.screenshot(FIG / "burst_gs_transition_time.png")
    print("wrote burst_gs_transition_time.png", flush=True)
    app.close()


def _grab_tracking_tool():
    """Grab the particle-tracking tool (guide 50).

    Tracked on a simulated movie with a *known* diffusion coefficient, so the
    figure can be read against the truth: 8 particles at D = 0.5 px^2/frame.
    Two grabs -- the report beside the movie with detections marked, and the
    trajectories, which is the view that reveals identity swaps.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    app = app_from("img_tracking")
    driver = Driver(app, (1500, 900))
    driver.frame(2)
    model = app.model
    model.use_simulation = True
    model.sim_n_frames = 60
    model.sim_size = 256
    model.sim_n_particles = 8
    model.sim_diffusion = 0.5
    model.max_distance = 4.0
    model.min_track_length = 15
    model.n_bootstrap = 150
    driver.click("track")
    wait(driver, lambda: not app.job.busy)
    _emtk_park(driver)
    driver.screenshot(FIG / "tracking_workspace.png")
    print("wrote tracking_workspace.png", flush=True)
    app.docks.focus("Trajectories")
    driver.frame(4)
    _emtk_park(driver)
    driver.screenshot(FIG / "tracking_trajectories.png")
    print("wrote tracking_trajectories.png", flush=True)


def _grab_coloc_tool():
    """Grab the colocalization workspace and its intensity scatter (guide 38)."""
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    source = pathlib.Path("test/data/clsm/PQ_Olympus_MFIS.ht3")
    if not source.is_file():
        raise FileNotFoundError(source)
    app = app_from("img_coloc")
    driver = Driver(app, (1500, 900))
    driver.frame(2)
    # A detector setup as the Detector-Def tool defines it: named windows as channels.
    app.apply_setup_settings(
        {
            "name": "confocal",
            "detectors": {
                "green": {"chs": [0, 1], "micro_time_ranges": []},
                "red": {"chs": [4, 5], "micro_time_ranges": []},
            },
        }
    )
    app.model.filename = str(source)
    app.model.channel_a, app.model.channel_b = "green", "red"
    app.model.auto_background = True
    app.model.ccf_max_shift = 12
    app.start()
    wait(driver, lambda: not app.job.busy and not app.model.busy)
    _emtk_park(driver)
    driver.screenshot(FIG / "coloc_workspace.png")
    print("wrote coloc_workspace.png", flush=True)
    app.docks.focus("Intensity scatter")
    driver.frame(4)
    _emtk_park(driver)
    driver.screenshot(FIG / "coloc_scatter.png")
    print("wrote coloc_scatter.png", flush=True)

    # Object regime: synthetic puncta, because the real confocal test image is one
    # continuous cell and would segment into a single object.
    _grab_coloc_objects(app, driver)


def _grab_coloc_objects(app, driver):
    """Grab the object map + distance histogram on synthetic puncta (guide 38)."""
    import tempfile

    from screenshots.emtk_shot import FIG, wait

    from chisurf.core.fio.image import imwrite

    shape = (160, 160)
    yy, xx = np.mgrid[: shape[0], : shape[1]]

    def puncta(centres, sigma=2.2, amplitude=120.0):
        """Return an image with Gaussian puncta at *centres*."""
        image = np.zeros(shape, dtype=float)
        for cy, cx in centres:
            image += amplitude * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma**2))
        return image

    rng = np.random.default_rng(3)
    centres = [tuple(p) for p in rng.integers(12, 148, size=(28, 2))]
    partners = [(cy + 1, cx) for cy, cx in centres[:18]]
    strangers = [tuple(p) for p in rng.integers(12, 148, size=(6, 2))]
    a = puncta(centres) + rng.normal(0, 2, shape)
    b = puncta(partners + strangers) + rng.normal(0, 2, shape)

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "puncta.tif"
        imwrite(path, np.stack([a, b]).astype(np.float32), axes="CYX")
        app.model.object_analysis = True
        app.model.object_distance = 3.0
        app.model.filename = str(path)
        app.model.channel_a, app.model.channel_b = "ch0", "ch1"
        app.start()
        wait(driver, lambda: not app.job.busy and not app.model.busy)
        for title, name in (("Objects", "coloc_objects.png"), ("Object distances", "coloc_object_distances.png")):
            app.docks.focus(title)
            driver.frame(4)
            _emtk_park(driver)
            driver.screenshot(FIG / name)
            print("wrote", name, flush=True)


def _grab_accurate_fret_tool():
    """Grab the native accurate-FRET window and its E-S / E-lifetime plots (guide 41).

    A simulated ALEX table with known factors (alpha 0.08, delta 0.06, gamma 0.65, beta 1.4).
    """
    from PIL import Image
    from screenshots.emtk_shot import (
        accurate_fret_calibrated,
        show_tabs,
        simulated_alex_table,
    )

    table = simulated_alex_table(
        pathlib.Path(tempfile.mkdtemp()) / "accurate_fret_demo_bursts.csv",
        gamma=0.65, alpha=0.08, beta=1.4, delta=0.06,
    )
    app, driver = accurate_fret_calibrated(table)
    show_tabs(driver, "Report", "E–S populations")
    driver.screenshot(FIG / "accurate_fret_tool.png")
    print("wrote accurate_fret_tool.png", flush=True)
    # The two diagnostic plots on their own: the plot pane below its tab bar.
    for name, tab in (("accurate_fret_es.png", "E–S populations"),
                      ("accurate_fret_etau.png", "E–lifetime and FRET lines")):
        show_tabs(driver, tab)
        x, y, _w, h = driver.rect("E–S populations")  # the first tab: the pane's left edge
        shot = FIG / name
        driver.screenshot(shot)
        width, height = driver.size
        left = int(x) - 6
        Image.open(shot).crop((left, int(y + h) + 4, width, height)).save(shot)
        print("wrote", name, flush=True)
    app.close()


def _grab_chimol_viewer():
    """Figures for the molecular-viewer guide: a ray-traced render and the panel.

    Two mechanisms, because neither covers both:

    * the **panel** is drawn by ``docs/guides/screenshots/guides_plugins_emtk.py`` (emtk);
    * the **render** goes through chimol's own ray tracer, which needs no GPU and
      no display -- the same path the plugin's visual tests use.

    Note ``objects.widget`` is a **property**; calling it raises ``TypeError``
    rather than doing anything useful.
    """
    import pathlib as _pathlib

    from chimol.commands.command import Cmd

    pdb = _pathlib.Path(
        "test/data/atomic_coordinates/pdb_files/148l.pdb"
    ).resolve()

    # -- the object panel: drawn by docs/guides/screenshots/guides_plugins_emtk.py (chimol) --
    # (kept: why the old Qt grabs were retired)
    # `chimol_objects_panel.png` and `chimol_groups_panel.png` were grabs of a
    # Qt dock reached through `window.objects.widget`. That dock no longer
    # exists: chimol's WebGPU port moved the object list into the viewport and
    # marked the dock permanently hidden ("Objects is permanently hidden (the
    # list is in the viewport)", chimol/hosts/qt/window.py). The attribute is
    # gone, so this section raised AttributeError and took the accessibility
    # figure below down with it.
    #
    # The two figures are NOT regenerated from the viewport overlay either,
    # because that overlay does not yet list the objects: with obj2/obj3/obj4 in
    # `viewer.objects` it still draws only `all` and `sele`, before and after
    # `refresh_objects()`. Regenerating now would replace two figures that show
    # the old UI correctly with two that show the new UI wrongly.
    # Tracked in okf/references/known-issues.md.

    # -- a ray-traced render, coloured by solvent accessibility ---------------
    # Driven through a bare MolView rather than the plugin window: inside the
    # window `ray` hands the trace to a worker, which a script with no event loop
    # of its own never lets finish ("ray: cancelled").
    from chimol.core.viewer.viewer import Viewer
    from chimol.io.structure import _read_full_model

    import chisurf.core.structure as cs_struct

    view = Viewer()
    view.resize(900, 650)
    view.add_structure(
        _read_full_model(cs_struct.Structure, pdb),
        name="148l",
        source_path=str(pdb),
    )

    class _Host:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Host())
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda m: print("  chimol:", m))
    for line in (
        "hide everything",
        "show spheres, all",
        "set dot_solvent, on",
        "set dot_density, 3",
        "get_area all, 1, 1",
        # An explicit range rather than the data's own: the most exposed atom is
        # an outlier, so an automatic range leaves the whole surface reading blue.
        "spectrum b, blue_white_red, all, 0, 25",
        # `orient`/`zoom` with no target resolve nothing here and fail with
        # "nothing to orient" -- the viewer auto-names the object (obj2), it is
        # not called after the file. Naming `all` is what makes them frame it.
        "orient all",
        "zoom all",
        f"ray {FIG / 'chimol_accessibility.png'}, 900, 650",
    ):
        cmd.do(line)
    print("wrote chimol_accessibility.png")


def _grab_chimol_biofilm():
    """The simulated biofilm, two frames of it, ray-traced.

    Generated the way the demo generates it -- the agent simulator is run and
    ChiMOL opens its RMF -- so the figure cannot drift from what the demo shows.
    Traced rather than grabbed for the reason the accessibility figure is: the
    ray tracer needs no GL context, and this script has no display.

    A frame early in the run and a frame at the end, because the point of the
    demo is the difference between them.
    """
    from chimol.commands.command import Cmd
    from chimol.core.viewer.viewer import Viewer
    from chimol.io.structure import load_structure_payload
    from chimol.plugins.demos.material import generated_demo_path

    rmf = generated_demo_path("biofilm_growth.rmf")
    _reader, payload = load_structure_payload(str(rmf))

    view = Viewer()
    view.resize(900, 650)
    view.add_payload(payload, name="biofilm", source_path=str(rmf))

    class _Host:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Host())
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda m: print("  chimol:", m))
    for line in (
        "bg_color white",
        # As the demo does it: the camera must not follow the frame, or the
        # early figure is framed on the centroid of a colony a fraction of the
        # size and the two pictures cannot be compared.
        "set movie_recenter, off",
        "as spheres",
        "frame 60",
        "turn x, -75",
        "zoom all, 2, 1",
    ):
        cmd.do(line)
    for frame, name in ((30, "chimol_biofilm_early.png"), (60, "chimol_biofilm_late.png")):
        cmd.do(f"frame {frame}")
        cmd.do(f"ray {FIG / name}, 900, 650")
        print(f"wrote {name}")


def _grab_region_editor():
    """The shared region GUI on the CLSM tool: the list and the shapes.

    The real emtk app, a synthetic confocal frame, and one region of every kind the
    editor can hold -- a painted mask, a drawn ellipse (inverted) and a
    rectangle switched off -- so the guide shows what the columns mean.
    """
    from screenshots.emtk_shot import app_from, render

    from chisurf.core.roi import EllipseROI, RectangleROI

    app = app_from("clsm")
    model = app.model

    ny = nx = 128
    yy, xx = np.mgrid[0:ny, 0:nx]

    def blob(cy, cx, r, soft=6.0):
        return 1 / (1 + np.exp((np.hypot(yy - cy, xx - cx) - r) / soft * 4))

    frame = 900 * (blob(64, 64, 46) - blob(64, 64, 38)) + 500 * blob(58, 70, 18) + 25
    model.current_image = np.random.default_rng(3).poisson(frame).astype(float)
    model.selection_mask = np.zeros_like(model.current_image)
    model.selection_mask[20:40, 20:45] = 1.0
    model.notify("image")

    model.add_roi("membrane ring")
    model.regions.add(EllipseROI(70, 58, 18, 18, name="nucleus"), invert=True)
    model.regions.add(RectangleROI(5, 100, 40, 122, name="empty patch"), enabled=False)
    model.regions.combine = "and"

    driver = render(app, "regions_overlay.png", size=(1020, 780))
    driver.click("Brush & Decay.fold")  # make room, then open the collapsed region panel
    driver.frame(4)
    driver.click((100, 372, 40, 10))  # the "Analysis regions" header (it has no id of its own)
    driver.frame(3)
    render(app, "regions_list.png", driver=driver)


def _grab_hmm_tool():
    """Hidden-Markov-model tool (native app) fitted on a simulated two-state trace (guide 54).

    The trace is handed over in memory (``set_traces``, the seam the intensity trace uses);
    then **Fit** and **Scan states** are pressed as a person presses them, each waited for.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    rng = np.random.default_rng(0)
    transmat = np.array([[0.985, 0.015], [0.03, 0.97]])
    means = np.array([[18.0], [55.0]])
    states = np.zeros(4000, dtype=int)
    for t in range(1, len(states)):
        states[t] = rng.choice(2, p=transmat[states[t - 1]])
    trace = means[states] + rng.normal(0, 4, size=(len(states), 1))

    app = app_from("hmm")
    driver = Driver(app, (1400, 860))
    driver.frame(3)
    app.set_traces([trace], ["simulated"])
    app.model.time_step = 1e-3
    app.model.n_states = 2
    app.model.min_states, app.model.max_states = 1, 4
    driver.frame(2)
    driver.click("request_scan")
    wait(driver, lambda: not app.job.busy)
    driver.click("request_run")
    wait(driver, lambda: not app.job.busy)
    _emtk_park(driver)
    for tab, name in (("Histogram", "hmm_workspace.png"), ("Dwell times", "hmm_dwell.png"),
                      ("Scan", "hmm_scan.png")):
        driver.click(tab)  # the tab caption, as a person brings a panel forward
        driver.frame(4)
        _emtk_park(driver)
        driver.screenshot(FIG / name)
        print("wrote", name, flush=True)
    fit = app.model.fit
    print("hmm means", [s.mean for s in fit.summaries], "rates", fit.transition_rates, flush=True)
    app.close()


def _grab_burst_fusion_tool():
    """Burst-fusion tool on its own demo, whose molecule count is declared (guide 58).

    Driven as the guide walks it: *Load example*, threshold 0.7, *Estimate*, then
    *Run (Fuse)*; so the figures show the numbers a reader gets by pressing the
    same buttons. The whole window at its declared 1100 x 720, then the
    P(same) and proximity-ratio plot tabs.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, show_tabs, wait

    app = app_from("burst_fusion")
    driver = Driver(app, (1100, 720))
    driver.frame(2)

    def settle():
        wait(driver, lambda: (app.controller.poll(), not app.controller.running)[1], timeout=900)

    driver.click("load_example")
    settle()
    app.model.threshold = 0.7
    driver.click("toolAction_refresh")
    settle()
    driver.click("toolAction_run")
    settle()
    print("fusion:", {r["quantity"]: (r["before"], r["after"]) for r in app.model.summary_rows()})
    driver.screenshot(FIG / "burst_fusion_native_primary_window.png")
    driver = Driver(app, (1250, 800))
    driver.frame(3)
    show_tabs(driver, "P(same)")
    driver.screenshot(FIG / "burst_fusion_curve.png")
    show_tabs(driver, "Proximity ratio")
    driver.screenshot(FIG / "burst_fusion_proximity.png")
    print("wrote burst_fusion_native_primary_window.png, burst_fusion_curve.png, burst_fusion_proximity.png")
    app.close()


def _grab_ndx_gaussian_panel():
    """ndX's Gaussian-fit panel, with two populations actually fitted.

    Drives the real app (ndX is the emtk app): two simulated populations, one
    component seeded on each, the second one's centre held, then the EM. The
    screenshot therefore shows fitted numbers in the parameter table (and the
    held value), not a mockup of one.
    """
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent / "screenshots"))
    import ndx_emtk

    blobs = [(0.25, 0.35, 0.04, 0.05), (0.70, 0.70, 0.06, 0.03)]
    rng = np.random.default_rng(0)
    points = np.vstack(
        [
            np.column_stack([rng.normal(cx, sx, 3000), rng.normal(cy, sy, 3000)])
            for cx, cy, sx, sy in blobs
        ]
    )
    table = pathlib.Path(tempfile.mkdtemp(prefix="ndx-gauss-")) / "two_populations.csv"
    np.savetxt(table, np.column_stack([points, rng.normal(0, 1, len(points))]),
               delimiter=",", header="E,S,z", comments="")

    driver = ndx_emtk.replay(size=(1200, 540))
    ndx_emtk.open_table(driver, table)
    ndx_emtk.axes(driver, "E", "S", "z")
    driver.step({"op": "trigger", "action": "actionFit_Gaussians", "checked": True})
    panel = ndx_emtk.feature(driver, "analysis").gaussians
    for index, (cx, cy, sx, sy) in enumerate(blobs):
        # The second population's centre is held, to show what a held
        # parameter looks like beside the fitted ones.
        held = index == 1
        panel.add((cx + 0.04, cy - 0.04), np.diag([sx ** 2, sy ** 2]),
                  fixed={"x": held, "y": False})
    driver.settle()
    panel.fit()
    driver.settle(3)
    driver.step({"op": "capture", "name": "fit_panel", "target": "widget:win.dockWidget_Fit"})
    ndx_emtk.save(driver.shots["fit_panel"], FIG, "ndxplorer_gaussian_panel.png")
    driver.app.close()


def _grab_kappa2_tool():
    """Grab the k2 distribution calculator in the restricted-dye state (guide 61)."""
    from screenshots.emtk_shot import app_from, render

    app = app_from("kappa2_dist")
    # Not the defaults: a visibly restricted donor, so the panel shows a real
    # distance penalty rather than the near-zero one a mobile dye gives.
    m = app.tool._model
    m.r_Dinf = 0.15
    m.r_Ainf = 0.20
    app.compute_now()
    render(app, "kappa2_tool.png", size=(640, 820))


def _grab_maxent_decay():
    """MaxEnt decay on a decay whose lifetime distribution is known.

    The decay is built from a *bimodal* distribution (peaks at 1.1 ns and
    3.6 ns) rather than two discrete exponentials, because that is the case MEM
    exists for and the case the figure has to show it solving.

    **The fixture is integrated over each channel, not sampled at its edge.**
    A TCSPC channel counts arrivals during the bin, which is what the solver's
    forward model reproduces; a plain ``np.convolve`` of the decay with the IRF
    point-samples at the channel's left edge and lands **half a channel early**
    (measured: rms 6.5e-3 against a 64x-oversampled reference, versus 2.5e-4 for
    the solver). Feeding that in makes MEM fit a half-channel offset it cannot
    express, costs 0.5 in chi2r, and pushes the answer into the timeshift --
    which reads as a ChiSurf defect and is not one.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    import chisurf
    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

    n, dt, oversample = 512, 0.0323, 32
    # Build on a fine grid and average each channel down: that integration is
    # what a channel does, and what the solver's design matrix assumes.
    t_fine = (np.arange(n * oversample) + 0.5) * (dt / oversample)
    irf_fine = np.exp(-0.5 * ((t_fine - 1.0) / 0.12) ** 2)
    irf = irf_fine.reshape(n, oversample).mean(1)
    irf /= irf.sum()

    taus = np.linspace(0.2, 6.0, 200)
    weights = np.exp(-0.5 * ((taus - 1.1) / 0.25) ** 2)
    weights += 0.8 * np.exp(-0.5 * ((taus - 3.6) / 0.55) ** 2)
    weights /= weights.sum()
    pure_fine = (weights[:, None] * np.exp(-t_fine[None, :] / taus[:, None])).sum(0)
    conv = np.convolve(pure_fine, irf_fine / irf_fine.sum())[: n * oversample]
    conv = conv.reshape(n, oversample).mean(1)
    rng = np.random.default_rng(3)
    decay = rng.poisson(3.0e4 * conv / conv.max()).astype(float)

    fit = build_lifetime_fit(
        decay, bin_width=dt, irf=irf, n_components=2,
        start_bin=int(1.0 / dt), stop_bin=n - 1,
    )
    fit.data.name = "MEM-demo-decay"
    chisurf.fits = [fit]  # the session's live fit, which Refresh lists

    app = app_from("maxent_decay")
    driver = Driver(app, (1400, 900))
    driver.frame(3)
    driver.click("refresh")
    driver.click("use_fit")
    # The default grid reaches down to where no decay is left to describe; its
    # first bin then collects an edge spike that dwarfs both real peaks.
    app.model.settings.tau_min, app.model.settings.tau_max, app.model.settings.tau_bins = 0.4, 7.0, 120
    # Nuisance fitting is deliberately OFF: with the fixture discretised
    # correctly there is nothing for it to find (it recovers a timeshift of
    # -0.014 channels and improves chi2r by 0.0006, for 160x the run time).
    driver.frame(2)
    driver.click("run")
    wait(driver, lambda: app.jobs.process is None, timeout=600)
    _emtk_park(driver)
    driver.screenshot(FIG / "maxent_distribution.png")
    print("wrote maxent_distribution.png:", app.model.status, flush=True)
    driver.click("lcurve")
    wait(driver, lambda: app.jobs.process is None, timeout=900)
    _emtk_park(driver)
    driver.screenshot(FIG / "maxent_decay_window.png")
    print("wrote maxent_decay_window.png:", app.model.status, flush=True)
    app.close()


def _grab_global_view():
    """The parameter network with one lifetime shared across three fits.

    Three fits with a *link* between them, not three unrelated ones: the guide
    is about the shared parameter, and an unlinked network has nothing in it
    that a list of fits would not have shown.
    """
    import chisurf
    from chisurf.core.api.fitting_client import install_fitting_client
    from chisurf.core.data import DataCurve, DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.plugins.core.globalview.gui.app import make_app
    from chisurf.plugins.core.globalview.gui.model import GlobalViewModel

    def make(name, tau, n_curves=1):
        x = np.linspace(0.1, 25, 256)
        y = 1000.0 * np.exp(-x / tau) + 1.0
        curves = [
            DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"{name}-{i}") for i in range(n_curves)
        ]
        return FitGroup(
            data=DataCurveGroup(curves, name=name), model_class=tcspc_lifetime
        )

    fits = [make("Donor-only", 4.0), make("FRET-low", 2.4, 2), make("FRET-high", 1.3)]
    install_fitting_client(None)
    chisurf.fits = fits
    source = fits[0].model.parameters_all_dict["t0"]
    for fit in fits[1:]:
        fit.model.parameters_all_dict["t0"].link = source

    model = GlobalViewModel(fits=lambda: fits, groups=lambda: [])
    app = make_app(model=model, remember_layout=False)
    model.rebuild(force=True)
    _native_shot(app, "globalview_network.png", size=(1150, 760))
    model.representation = "factor graph"
    model.relayout()
    _native_shot(app, "globalview_factor_graph.png", size=(1150, 760))


def _grab_ebfret_tool():
    """ebFRET after an analysis of its simulated demo: K = 4 with the Viterbi path.

    The native window as a person drives it: *Load example*, Max states 4, *Run*
    (the real backend loop on the demo's forty four-state traces), then the
    four-state model and series 3 selected, so the Viterbi overlay and the
    posterior curves -- what the guide explains -- are on screen.
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    app = app_from("burst_ebfret")
    driver = Driver(app, (1200, 820))
    driver.frame(2)
    app.load_example()
    driver.frame(2)
    client = app.gui.client
    client.set("max_states", 4)
    client.run()
    wait(driver, lambda: not client.status()["running"], timeout=900)
    client.set("ensemble", 4)
    client.set("series", 3)
    driver.frame(6)
    driver.screenshot(FIG / "ebfret_gui.png")
    print("wrote ebfret_gui.png", flush=True)
    client.close()


def _grab_pto_inspector():
    """A container holding an instrument file and two results derived from it.

    A `.pto` with only the raw file in it has no provenance to draw, so the
    fixture writes a burst table derived from the instrument data and a decay
    derived from those bursts -- the two-step lineage the guide describes.
    """
    import shutil

    from screenshots.emtk_shot import app_from, render

    from chisurf.core.fio.pto import Measurement

    ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu")
    if not ptu.is_file():
        raise FileNotFoundError(f"instrument test data missing: {ptu}")

    work = pathlib.Path(tempfile.mkdtemp()) / "sample"
    work.mkdir()
    raw = work / "measurement.ptu"
    shutil.copy(ptu, raw)

    n_bursts = 128
    rng = np.random.default_rng(1)
    with Measurement.create(raw) as measurement:
        bursts = measurement.put_table(
            "bursts",
            {
                "First Photon": np.arange(n_bursts, dtype=np.int64),
                "Np": rng.integers(40, 400, n_bursts).astype(np.int32),
            },
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"M": 10, "T": 0.0005, "N": 20},
            derived_from=measurement.instrument_uid,
        )
        t = np.arange(256.0) * 0.032
        measurement.put_curve(
            "decay", t, 3.0e4 * np.exp(-t / 3.2) + 5.0,
            artifact_kind="tcspc_decay",
            operation_type="tcspc_histogram_computation",
            x_units="nanoseconds", y_units="counts",
            derived_from=bursts,
        )

    app = app_from("pto_inspector")
    app.model.set_filename(str(work / "measurement.pto"))
    render(app, "pto_inspector.png", (1400, 900))


def _grab_irf_estimator():
    """A blind IRF estimate on a decay that reaches baseline.

    50 ns of range at tau = 4 ns, deliberately: the method fits a *truncated*
    exponential, and with only a few lifetimes of measured tail the offset C is
    degenerate against the exponential -- tau comes back low and the recovered
    IRF grows a tail that is regularisation ringing, not an instrument
    response. The guide says so; this figure is the case where the assumption
    holds.
    """
    from screenshots.emtk_shot import app_from, render, wait

    n, dt = 500, 0.1002
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 5.0) / 0.5) ** 2)
    irf /= irf.sum()
    conv = np.convolve(np.exp(-t / 4.0), irf)[:n]
    rng = np.random.default_rng(5)
    decay = rng.poisson(4.0e4 * conv / conv.max() + 8.0).astype(float)

    app = app_from("irf_estimator")
    from emtk.testing import Driver

    driver = Driver(app, (1300, 860))
    driver.frame(2)
    app.model.load_data(decay, dt=dt)
    app.model.source_text = "simulated decay \u2014 \u03c4 = 4.0 ns, IRF FWHM 1.18 ns at 5.0 ns"
    driver.frame(2)
    app.start_estimate()
    wait(driver, lambda: app.future is None)
    render(app, "irf_estimator.png", driver=driver)


def _grab_console():
    """``console.png`` of guide 59: delegated to ``guides_56_65._grab_59_console``.

    That recipe asks ``api`` about a fit the shell really ran; the older body here set
    ``cs.fits`` by hand and overwrote the guide's figure on every bulk run.
    """
    import sys

    shots = str(pathlib.Path(__file__).resolve().parent / "screenshots")
    if shots not in sys.path:
        sys.path.insert(0, shots)
    import guides_56_65

    guides_56_65._grab_59_console()


def _simulate_us_alex(path, *, frac_high=0.5, seed=11, duration=25.0):
    """Write a small synthetic µs-ALEX measurement, with a known alternation.

    Two FRET populations, a background, and the laser alternation encoded in the
    macro time — the shape the ALEX Suite's first step exists to recognise. The
    header is borrowed from a bundled PTU so the macro-time resolution is real.
    """
    import tttrlib

    rng = np.random.default_rng(seed)
    # The header decides what a macro-time unit *is*, so the simulation has to
    # read it rather than assume: writing 50 ns photons under a 20 us header
    # makes the tool report a 80 ms alternation, which is not a thing.
    source = pathlib.Path("test/data/clsm/Leica_SP5.ptu")
    header = tttrlib.TTTR(str(source)).header
    res = float(header.macro_time_resolution)
    period = int(round(200e-6 / res))   # a 200 us alternation
    green = (int(0.05 * period), int(0.45 * period))
    red = (int(0.55 * period), int(0.95 * period))

    def stream(rate, t0, t1, efficiency):
        n = rng.poisson(rate * (t1 - t0))
        return rng.uniform(t0, t1, n), np.full(n, efficiency)

    times, effs = zip(*(
        [stream(1.5e3, 0.0, duration, 0.05)]
        + [stream(90e3, start, start + 1.5e-3, e)
           for start, e in zip(
               rng.uniform(0.0, duration - 2e-3, 900),
               np.where(rng.random(900) < frac_high, 0.68, 0.22))]
    ))
    t = np.concatenate(times)
    e = np.concatenate(effs)
    order = np.argsort(t)
    macro = (t[order] / res).astype(np.uint64)
    e = e[order]

    # Photons are NOT deleted outside the gates. Real µs-ALEX has no laser-off
    # hole in the folded intensity -- both lasers keep the sample emitting, so
    # the total is nearly flat and only the *detector ratio* alternates. A
    # simulation that gates the photons away produces a picture the window
    # detection finds trivially and a reader would not recognise.
    phase = macro % period
    donor_excited = (phase >= green[0]) & (phase < green[1])
    acceptor_excited = (phase >= red[0]) & (phase < red[1])
    p_acceptor = np.where(
        donor_excited, e,                     # donor excitation: E decides
        np.where(acceptor_excited, 0.95,      # acceptor excitation: nearly all
                 0.5))                        # the rise/fall, neither fully on
    routing = np.where(rng.random(macro.size) < p_acceptor, 1, 0).astype(np.int8)

    out = tttrlib.TTTR()
    out.append_events(macro, np.zeros(macro.size, np.uint16), routing,
                      np.zeros(macro.size, np.int8), True, 0)
    out.write(str(path), header)
    return path


def _grab_alex_suite_alternation():
    """Grab the native ALEX Suite's alternation step, converted on arrival from the shipped demo (guide 66)."""
    from emtk.testing import Driver
    from screenshots.emtk_shot import app_from, wait

    hub = app_from("alex_suite")
    driver = Driver(hub, (1180, 780))
    driver.frame(3)
    hub.select("data")
    driver.frame(3)
    driver.click(hub._target_rect("load_example"))  # the files step's own button, as the tour has it pressed
    driver.frame(3)
    driver.click("next")  # -> 3. Alternation, which converts on arrival
    alternation = hub.children["alternation"].model
    wait(driver, lambda: not alternation.running and not hub._busy(), timeout=300)
    driver.hover((12.0, 760.0))
    driver.frame(3)
    driver.screenshot(FIG / "alex_suite_alternation.png")
    print("wrote alex_suite_alternation.png:", hub.status, flush=True)
    hub.close()


def _grab_alex_suite_titration():
    """Grab the titration step, fitted on a simulated concentration series."""
    import csv

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="alex_titration_"))
    rng = np.random.default_rng(5)
    kd, rows = 50.0, []
    for concentration in (0.0, 5.0, 15.0, 50.0, 150.0, 500.0, 2000.0):
        bound = concentration / (kd + concentration)
        n = 4000
        n_high = int(round(n * bound))
        efficiencies = np.concatenate([
            np.full(n - n_high, 0.22), np.full(n_high, 0.68)])
        total = rng.poisson(200, n).astype(float) + 20.0
        green = total * 0.5
        i_da = rng.binomial(green.astype(int), efficiencies).astype(float)
        path = workdir / f"c{concentration:g}.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["Number of Photons (green)",
                             "Number of Photons (red)",
                             "Number of Photons (yellow)", "Duration (ms)"])
            for a, b, c in zip(green - i_da, i_da, total - green):
                writer.writerow([a, b, c, 1.0])
        rows.append((concentration, path))

    from emtk.testing import Driver
    from screenshots.emtk_shot import app_from

    hub = app_from("alex_suite")
    driver = Driver(hub, (1180, 780))
    driver.frame(3)
    hub.select("titration")
    driver.frame(3)
    model = hub.children["titration"].model
    model.add_files([str(path) for _, path in rows])
    for index, (concentration, _) in enumerate(rows):
        model.update_series_cell(index, "concentration", concentration)
    model.min_photons = 0
    model.run()
    driver.frame(4)
    driver.hover((12.0, 760.0))
    driver.frame(2)
    driver.screenshot(FIG / "alex_suite_titration.png")
    print("wrote alex_suite_titration.png:", model.summary.splitlines()[0], flush=True)
    hub.close()


def _native_shot(app, name, frames=4, size=(1200, 800)):
    """Draw a native emtk app a few frames and save the last into ``figures/``."""
    from emtk.pil_painter import PilPainter

    for _ in range(frames):
        painter = PilPainter(*size)
        app.draw(painter, 0, 0, *size)
    painter.frame.save(FIG / name)
    print("wrote", name)


def _grab_decay_gap_filter():
    """Histogram-Microtime with the inter-photon filter on: the burst photons of a single-molecule file.

    BH SPC-132 single-molecule DNA measurement (detectors 0/8 = green parallel/perpendicular),
    max gap 20000 ticks (0.27 ms at the 13.5 ns clock).
    """
    import time

    from emtk.pil_painter import PilPainter

    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    spc = pathlib.Path("chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc")
    app = create_app()
    app.add_files([spc])
    model = app.model
    model.filetype, model.auto_save = "SPC-130", False
    model.polarized, model.parallel, model.perpendicular = True, [0], [8]
    model.gap_filter, model.gap_ticks, model.gap_invert = True, 20000, False
    app.compute()
    end = time.time() + 120
    while (app.job.running or app.model.cumulative_parallel is None) and time.time() < end:
        app.draw(PilPainter(1200, 800), 0, 0, 1200, 800)  # the job publishes its model on a frame
        time.sleep(0.05)
    _native_shot(app, "decay_gap_filter.png")
    app.close()


def _grab_fcs_correlator_step():
    """The FCS workflow's Correlator step on its simulated example: 3 splits, laurence."""
    from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app

    hub = make_app()
    hub.select("files").load_example()
    corr = hub.select("correlator")
    corr.model.channel_a, corr.model.channel_b, corr.model.n_splits = "0", "1", 3
    corr.model.method = "laurence"
    corr.correlate(wait=True)
    _native_shot(hub, "fcs_correlator_step.png", frames=6)
    hub.close()


def _grab_intensity_trace():
    """Intensity-trace tool (native app) on a real smFRET TTTR file, binned and HMM-decoded (guide 74).

    The file is copied to a scratch folder first: *Compute HMM* writes its
    ``<stem>_HMM#<n>_<w>ms/`` output folder beside the TTTR file, and that must
    not land in ``test/data``. The detector setup is set explicitly (a grab that
    inherits the settings dir's last setup shows whatever that held).
    """
    from emtk.testing import Driver
    from screenshots.emtk_shot import FIG, app_from, wait

    src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    if not src.is_file():
        raise FileNotFoundError(f"instrument test data missing: {src}")
    work = pathlib.Path(tempfile.mkdtemp(dir="/tmp")) / "smfret"
    work.mkdir()
    spc = work / src.name
    shutil.copy(src, spc)

    app = app_from("intensity_trace")
    driver = Driver(app, (1400, 900))
    driver.frame(3)
    # Two detectors as the detector setup defines them: green = routing channels 0/8
    # (parallel/perpendicular), red = 1/9 -- acceptor first, so the per-bin ratio
    # n0/(n0+n1) is the proximity ratio rather than its complement.
    app.model.setup = {
        "detectors": {
            "red": {"chs": [1, 9], "micro_time_ranges": []},
            "green": {"chs": [0, 8], "micro_time_ranges": []},
        }
    }
    app.setup_name = "Edited setup"
    app.model.window_ms = 5.0
    app.model.hist_max = 100.0
    app.model.n_states = 2
    app.open_file(str(spc))
    wait(driver, lambda: not app.busy)
    driver.click("HMM")  # the HMM tab of the controls
    driver.click("Compute HMM")
    wait(driver, lambda: not app.busy, timeout=600)
    driver.click("Dwell Times")
    wait(driver, lambda: not app.busy)
    _emtk_park(driver)
    driver.screenshot(FIG / "intensity_trace.png")
    print("wrote intensity_trace.png:", app.status, flush=True)
    app.close()
    return app, work


def _grab_file_tools():
    """File tools: Split / Convert with a file loaded, and Time Windows run.

    Writes ``file_tools.png`` (TTTR -> Time Windows after *Process*, with the
    trace and its window boundaries) and ``file_tools_split.png`` (TTTR Split /
    Convert with a file loaded). Each tool is its own native emtk window.
    """
    import tttrlib
    from emtk.testing import Driver
    from screenshots.emtk_shot import app_from, render, wait

    src = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    if not src.is_file():
        raise FileNotFoundError(f"instrument test data missing: {src}")
    work = pathlib.Path(tempfile.mkdtemp(dir="/tmp")) / "smfret"
    work.mkdir()
    spc = work / src.name
    shutil.copy(src, spc)

    # 1) Split / Convert
    split = app_from("tttr_splitter")
    driver = Driver(split, (1300, 800))
    driver.frame(2)
    model = split.tool._model
    model.output_folder = str(work / "split")
    model.set_tttr(tttrlib.TTTR(str(spc)), str(spc))
    model.update()
    render(split, "file_tools_split.png", size=(1300, 800), driver=driver)

    # 2) TTTR -> Time Windows: queue the file, process, show the preview
    windows = app_from("tttr_time_windows")
    driver = Driver(windows, (1300, 800))
    driver.frame(2)
    controller = windows.tool
    controller.time_window_ms = 1000.0
    controller.add_paths([spc])
    controller._process_all()
    wait(driver, lambda: not controller.job.running and not controller.process_pending)
    render(windows, "file_tools.png", size=(1300, 800), driver=driver)
    return windows


def _grab_fcs_toolbox():
    """Grab the FCS workflow (Spectroscopy:Correlation:FCS): every correlator step, as the native rail draws it.

    Loads the BH SPC-132 test stream, turns on the photon filter, correlates the green channels against the
    red ones in ten chunks and hands them to the merger: the state a user reaches after one pass through the
    rail. Each step is written through :class:`emtk.testing.PixelPainter`.
    """
    from emtk.testing import PixelPainter, png_encode

    from chisurf.plugins.fcs.fcs_correlator.test.test_emtk_workflow import Hub
    from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app

    size = (1280, 800)
    hub = Hub(make_app(), size)
    app = hub.app

    def shot(name):
        from chisurf.emtk.background_build import join_all

        for _ in range(2):
            join_all()
            painter = PixelPainter(*size)
            app.draw(painter, 0, 0, *size)
        (FIG / name).write_bytes(png_encode(painter.width, painter.height, painter.px))
        print("wrote", name)

    # 1. Channel definitions: a detector setup and its correlation pairs.
    hub.nav("channel_def")
    shot("fcs_toolbox_channels.png")

    # 2. Files & steps: one photon stream, photon filter on, merger on.
    hub.nav("files")
    hub.child.add_paths([str(_SPC_FILE.resolve())])
    hub.draw(3)
    shot("fcs_toolbox_files.png")

    # 3. Photon / burst filter: default count-rate burst selection.
    hub.nav("filter")
    fm = app.filter_model
    fm.channel_numbers = "0, 1, 8, 9"
    fm.max_dmt = 0.5
    fm.min_ph = 30
    hub.draw(3)
    shot("fcs_toolbox_filter.png")

    # 4. Correlator: green x red cross-correlation, ten chunks.
    hub.nav("correlator")
    cm = app.correlator_model
    cm.channel_a, cm.channel_b = "0, 8", "1, 9"
    cm.n_bins, cm.n_casc, cm.n_splits = 4, 26, 10
    hub.click("correlate")
    hub.wait_correlated()
    print("chunks", len(cm._correlations))
    shot("fcs_toolbox_correlator.png")

    # 5. Merger: the chunks averaged.
    hub.nav("merger")
    hub.draw(3)
    shot("fcs_toolbox_merger.png")

    # Visit every optional tool once so a broken panel shows up here.
    for role in ("flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc"):
        hub.nav(role)
        print(role, "loaded:", role in app.children)
    app.close()


def _grab_vv_vh_g_factor_window():
    """The VV/VH G-Factor Calculator (Spectroscopy > Decay), a fast dye and a slow protein loaded.

    Synthetic VV/VH pairs whose answer is known (G = 1.2, rho 0.2 ns and 16 ns,
    tau 4 ns), generated as the G-factor parity test does.
    """
    import numpy as np
    from emtk.pil_painter import PilPainter

    from chisurf.core.fio import write_vv_vh
    from chisurf.emtk.plugins import load_plugin

    folder = pathlib.Path(tempfile.mkdtemp(prefix="gfactor_"))
    rng = np.random.default_rng(5)
    n, dt = 512, 0.05
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 5.0) / 0.1) ** 2)
    files = {}
    for name, rho in (("fast", 0.2), ("slow", 16.0)):
        r = 0.38 * np.exp(-t / rho)
        decay = np.convolve(irf, np.exp(-t / 4.0))[:n]
        vv = rng.poisson(decay * (1 + 2 * r) * 2000 + 3.0).astype(float)
        vh = rng.poisson(decay * (1 - r) / 1.2 * 2000 + 3.0).astype(float)
        files[name] = folder / f"{name}.dat"
        write_vv_vh(files[name], vv=vv, vh=vh, metadata={"dt": dt})

    app = load_plugin("vv_vh_g_factor")
    model = app.model
    model.fp_dt_ns = dt
    model.load(str(files["fast"]))
    model.load(str(files["slow"]), slow=True)
    model.background = True
    model.compute()
    for _ in range(4):
        painter = PilPainter(1200, 800)
        app.draw(painter, 0, 0, 1200, 800)
    painter.frame.save(FIG / "vv_vh_g_factor_window.png")
    app.close()
    print("wrote vv_vh_g_factor_window.png")


def _grab_lltf():
    """Grab the Lazy Lifetime Analysis window after a real fit.

    Loads the plugin's bundled donor-only decay, IRF and ``config.yml``, runs
    the real Fit (a child ``lltf fit`` process) with a two-lifetime model, waits
    for it and grabs the Results and Analysis Output tabs and the YAML editor.
    """
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.fluorescence_decay.lltf.gui.app import make_app

    ex = pathlib.Path("chisurf") / "plugins" / "fluorescence_decay" / "lltf" / "example"
    out = pathlib.Path(tempfile.mkdtemp(prefix="lltf_"))
    app = make_app()
    m = app.model
    m.decay_file = str((ex / "5-44_D0.dat").resolve())
    m.irf_file = str((ex / "IRF_D0.dat").resolve())
    m.output_dir = str(out)
    m.load_config(str((ex / "config.yml").resolve()))
    m.n_lifetimes = 2
    size = (1200, 800)

    def draw(n=1):
        painter = None
        for _ in range(n):
            painter = PilPainter(*size)
            app.draw(painter, 0, 0, *size)
        return painter

    app.start()
    for _ in range(600):  # the child process: ~5 s for one fixed-n fit
        draw()
        if m.process is None:
            break
        time.sleep(0.1)
    for tab, name in (("Results", "lltf_results.png"), ("Analysis Output", "lltf_output.png")):
        app.pending_tab = tab
        draw(4).frame.save(FIG / name)
        print(f"wrote {name}")
    app.edit_config()
    draw(4).frame.save(FIG / "lltf_settings.png")
    print("wrote lltf_settings.png")
    app.config_open = False
    r = m.result
    print("LLTF", [(round(x["lifetime"], 3), round(x["amplitude"], 3)) for x in r["lifetimes"]],
          round(r["reduced_chi_square"], 2), r.get("time_range"))
    app.close()


def _grab_synthetic_decay():
    """Grab the Synthetic Decay Generator in VM and VV/VH mode.

    Two lifetimes (1.2 and 4.0 ns, the defaults) on 1024 bins of 32 ps, the
    LLTF example IRF, 10^6 photons of Poisson noise; then the same spectrum as a
    polarized pair with g = 1.1 and one 2 ns rotation.
    """
    import numpy as np
    from screenshots.emtk_shot import app_from, render

    ex = pathlib.Path("chisurf") / "plugins" / "fluorescence_decay" / "lltf" / "example"
    irf = np.loadtxt(ex / "IRF_D0.dat")[:, 1]
    # 8 ps channels -> 32 ps: sum groups of four, keep the first 1024 bins
    irf32 = irf[: 4 * (irf.size // 4)].reshape(-1, 4).sum(axis=1)[:1024]
    irf_file = pathlib.Path(tempfile.mkdtemp(prefix="synth_")) / "irf_32ps.txt"
    np.savetxt(irf_file, irf32)

    app = app_from("synthetic_decay")
    from emtk.testing import Driver

    driver = Driver(app, (1400, 900))
    driver.frame(2)
    m = app.model
    m.n_bins = 1024
    m.bin_width = 0.032
    m.irf_path = str(irf_file)
    m.shot_noise = True
    m.photon_count = 1e6
    m.seed = 1
    m.generate()
    render(app, "synthetic_decay_vm.png", driver=driver)

    # The same spectrum as a polarized pair, as a user switches the mode.
    m.polarization = "vv/vh"
    m.g_factor = 1.1
    m.rotation_rows = [{"b": 0.38, "rho": 2.0}]
    driver.frame(2)
    m.generate()
    render(app, "synthetic_decay_vvvh.png", driver=driver)


def _grab_phasor_calculator():
    """Phasor calculator: 80 MHz, grid + ticks, FRET for tau_D0 = 4 ns, a 0.6/5 ns mixture."""
    from screenshots.emtk_shot import app_from, render

    from chisurf.plugins.microscopy.img_pixel_phasor import analysis

    app = app_from("phasor_calculator")
    m = app.tool._model
    g1, s1 = analysis.lifetime_to_phasor(0.6, 80.0)
    g2, s2 = analysis.lifetime_to_phasor(5.0, 80.0)
    m.g1, m.s1, m.g2, m.s2 = float(g1), float(s1), float(g2), float(s2)
    m.show_fret = True
    m.tau_d0 = 4.0
    m.show_component = True
    m.show_mixing = True
    m.frac1 = 0.5
    m.show_cursor = True
    gm = 0.5 * g1 + 0.5 * g2
    sm = 0.5 * s1 + 0.5 * s2
    m.cursor_g, m.cursor_s, m.cursor_radius = float(gm), float(sm), 0.04
    driver = render(app, "phasor_calculator.png", (1100, 760))
    # Open the three collapsed groups the way a user does, then grab the controls again.
    from emtk.testing import Driver

    driver = Driver(app, (1000, 1100))
    driver.frame(3)
    for title in ("Cursor", "Mixing region", "Two-component line"):  # bottom first: opening one moves the rest
        driver.click(title)
    render(app, "phasor_calculator_controls.png", driver=driver)
    return app




# ── guide 78: F-test and batch analysis on the ibh donor / donor-acceptor decays ──
_IBH = pathlib.Path("test/data/tcspc/ibh_sample")
_DT = 0.0141 * 8  # ns per channel after 8x rebinning (4096 -> 512)


def _ibh_decay(name):
    """Load an ibh .txt decay (8 header lines + 'Chan Data'), rebinned 8x."""
    import numpy as np

    y = np.loadtxt(_IBH / name, skiprows=9)[:, 1]
    return y.reshape(-1, 8).sum(1)


def _ibh_irf():
    """The shared prompt, its constant background removed, rebinned 8x."""
    import numpy as np

    y = np.loadtxt(_IBH / "Prompt.txt", skiprows=9)[:, 1]
    y = np.clip(y - np.median(y[-800:]), 0, None)
    return y.reshape(-1, 8).sum(1)


def _ibh_fit(decay, n):
    import warnings

    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

    warnings.simplefilter("ignore")
    fit = build_lifetime_fit(
        decay, bin_width=_DT, irf=_ibh_irf(), n_components=n,
        initial_lifetimes=[0.5, 2.0, 4.5][-n:], fit_background=True,
        start_bin=55, stop_bin=480,
    )
    return fit


def _grab_traj_tools():
    """The trajectory tools on the T4L NMSim trajectory: Align, FRET, Energy Calculator, Remove Clashed (guide 81).

    Each is its own Structure › Trajectory tool; each is built and drawn on its own.
    """
    from screenshots.emtk_shot import app_from, render

    from chisurf.core.structure import trajectory_data as md
    from chisurf.plugins.traj.potential_energy.potential_specs import make_potential

    out = pathlib.Path(tempfile.mkdtemp(prefix="traj_tools_"))
    top, dcd = str(_T4L_TOP), str(_T4L_DCD)
    ref = md.load(top)
    ca = ref.top.select("name CA")

    def idx(res, name):
        return int(ref.top.select(f"resSeq {res} and name {name}")[0])

    size = (900, 640)
    opened = []

    def tools_of(plugin_id):
        app = app_from(plugin_id)
        opened.append(app)
        return app

    align = tools_of("traj_align")
    align.model.set_topology(top)
    align.model.set_trajectory(dcd)
    align.model.atom_selection = ", ".join(str(i) for i in ca)
    align.model.save_aligned(str(out / "t4l_aligned.dcd"))
    render(align, "traj_tools_align.png", size)

    fret = tools_of("traj_fret")
    fret.model.set_topology(top)
    fret.model.set_trajectory(dcd)
    fret.model.donor = (idx(36, "CA"), idx(36, "CB"))
    fret.model.acceptor = (idx(132, "CA"), idx(132, "CB"))
    fret.model.forster_radius = 52.0
    fret.model.tau0 = 4.0
    fret.model.t_step = 1.0
    fret.model.calc(str(out / "t4l_36_132.csv"))
    render(fret, "traj_tools_fret.png", size)

    energy = tools_of("traj_energy_calculator")
    energy.model.set_topology(top)
    energy.model.set_trajectory(dcd)
    energy.model.stride = 10
    for name in ("Radius of Gyration", "Clash potential"):
        energy.model.add_potential(make_potential(name, {}), 1.0, name=name)
    energy.model.process(str(out / "t4l_energy.txt"))
    render(energy, "traj_tools_energy.png", size)

    clash = tools_of("traj_remove_clashes")
    clash.model.set_topology(top)
    clash.model.set_trajectory(dcd)
    clash.model.atom_selection = "name CA"
    clash.model.min_distance = 3.5
    clash.model.save_clash_free(str(out / "t4l_clash_free.dcd"))
    render(clash, "traj_tools_clashes.png", size)

    conv = tools_of("traj_convert")
    conv.model.set_topology(top)
    conv.model.set_trajectory(dcd)
    conv.model.set_target_directory(str(out))
    conv.model.filename = "t4l_every10"
    conv.model.stride = 10
    conv.model.convert()
    render(conv, "traj_tools_convert.png", size)
    for app in opened:
        app.close()


def _grab_fret_line_tool():
    """FRET Line Generator: static line (Gaussian sweep) + dynamic line 40<->70 A (guide 82).

    The emtk app (``chisurf.plugins.fret_line.gui.app``), driven through its model as the
    guide's steps do: one Gaussian component swept over RDA0 20-120 A, then a second
    component at 70 A (the first at 40 A) with the fraction of C0 swept 0-1.
    """
    from emtk.testing import Driver

    from chisurf.core.fluorescence.fret.fret_line import find_parameter
    from chisurf.plugins.fret_line.gui.app import make_app

    app = make_app()
    m = app.model
    m.sweep_label = next(s for s in m.sweep_labels() if "C0 [FRET: FD (Gaussian)] · RDA0" in s)
    m.minimum, m.maximum, m.tau_d0 = 20.0, 120.0, 4.0
    m.add_line()
    find_parameter(m.components[0]["model"], "distance.mean.0").value = 40.0
    m.add_component()
    find_parameter(m.components[1]["model"], "distance.mean.0").value = 70.0
    m.sweep_label = next(s for s in m.sweep_labels() if s.startswith("fraction · C0"))
    m.minimum, m.maximum = 0.0, 1.0
    m.add_line()
    driver = Driver(app, (1200, 800))
    app.show_advanced("components")
    app.show_advanced("editor")
    _emtk_park(driver)
    driver.screenshot(FIG / "fret_line_tool.png")
    print("wrote fret_line_tool.png")
    app.show_advanced("lines")
    _emtk_park(driver)
    driver.screenshot(FIG / "fret_line_tool_lines.png")
    print("wrote fret_line_tool_lines.png")
    app.close()


def main():
    """Generate all guide screenshots."""
    for grab in (
        _grab_parameter_link_menu,
        _grab_burst_browser,
        _grab_2cde_tool,
        _grab_coloc_tool,
        _grab_drift_tool,
        _grab_precision_tool,
        _grab_burst_gs_tool,
        _grab_burst_fusion_tool,
        _grab_frc_tool,
        _grab_tracking_tool,
        _grab_accurate_fret_tool,
        _grab_kappa2_tool,
        _grab_hmm_tool,
        _grab_chimol_viewer,
        _grab_chimol_biofilm,
        _grab_region_editor,
        _grab_ndx_gaussian_panel,
        _grab_ndx_overlay_axes,
        _grab_maxent_decay,
        _grab_vv_vh_g_factor_window,
        _grab_global_view,
        _grab_ebfret_tool,
        _grab_pto_inspector,
        _grab_irf_estimator,
        _grab_console,
        _grab_alex_suite_alternation,
        _grab_alex_suite_titration,
        _grab_decay_gap_filter,
        _grab_fcs_correlator_step,
        _grab_intensity_trace,
        _grab_file_tools,
        _grab_fcs_toolbox,
        _grab_lltf,
        _grab_synthetic_decay,
        _grab_phasor_calculator,
        _grab_traj_tools,
        _grab_fret_line_tool,
    ):
        try:
            grab()
        except Exception as exc:  # keep going; report which grab failed
            print(f"SKIP {grab.__name__}: {exc}")

    # ① Compute LUT — the native app with a real flat-light file loaded, so
    # the raw/after plots and the draggable region are shown.
    from screenshots.emtk_shot import app_from, render

    spc = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    lut_app = app_from("tttr_lut_tools")
    if spc.is_file():
        lut_app.model.add_files([str(spc.resolve())])
    render(lut_app, "lut_tools_workspace.png", size=(1120, 760))

    # The channel-definition editor (LUT handling section, lut_channel_box.png) is the one-page emtk editor:
    # docs/guides/screenshots/channel_editor_emtk.py draws it. The Batch Analysis figures
    # (batch_analysis_{loaded,files,run,results}.png) come from docs/guides/screenshots/batch_analysis_emtk.py.

    print("screenshots written to", FIG)


if __name__ == "__main__":
    main()
