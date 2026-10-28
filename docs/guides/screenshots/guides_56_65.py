"""Grab functions for guides 55, 56, 57, 59, 65 (settings, fit window, live plots), 67.

Uses FIG and _pump from common.py. Each
function saves into FIG. Run each in its own subprocess with a timeout: the
acquisition and main-window grabs start threads and servers.
"""
import pathlib
import tempfile
import time

from common import FIG, _pump  # noqa: F401


def _grab_55_flow():
    """The native Flow maps tool on its own demo (simulated Poiseuille flow, peak 2 µm/s), mapped with defaults."""
    from emtk.testing import Driver
    from emtk_shot import app_from, wait

    app = app_from("img_flow")
    driver = Driver(app, (1500, 880))
    driver.frame(3)
    driver.click("load_example")
    wait(driver, lambda: not app.job.busy, timeout=300)
    driver.click("map_flow")
    wait(driver, lambda: not app.job.busy, timeout=300)
    driver.hover((12.0, 868.0))
    driver.frame(3)
    print("flow:", app.model.status, flush=True)
    driver.screenshot(FIG / "flow_tool.png")
    print("wrote flow_tool.png", flush=True)
    app.close()
    return app


def _grab_56_fcs_saturation():
    """The saturation calculator (emtk window, FCS curve tab) on its default Rhodamine 6G scheme at 2 mW."""
    from emtk.testing import Driver
    from emtk_shot import app_from, render

    app = app_from("fcs_saturation")
    driver = Driver(app, (1500, 900))
    driver.frame(3)
    app.model.power_mW = 2.0
    app.compute()
    app.select_tab("FCS curve")
    driver.frame(3)
    print("power", app.model.power_mW, "wl", app.model.wavelength_nm, flush=True)
    render(app, "fcs_saturation_tool.png", driver=driver)
    app.select_tab("Info")
    driver.frame(3)
    driver.screenshot("/tmp/fcs_saturation_info.png")  # read it: its numbers are the caption's
    return app


def _grab_65_acquisition_settings():
    """Setup -> Settings -> Acquisition (native settings hub), simulator selected, pulsed excitation.

    Every change in that panel is stored at once, so the grab runs on a scratch settings folder.
    """
    import os

    from emtk.testing import Driver
    from emtk_shot import app_from

    os.environ["CHISURF_SETTINGS_DIR"] = tempfile.mkdtemp(prefix="acq_settings_")
    app = app_from("setup")
    driver = Driver(app, (1200, 900))
    driver.frame(3)
    driver.click("Acquisition")  # the hub's sidebar entry, as a person picks it
    driver.frame(4)
    acq = app.child
    acq.model.output_path = "/data/acquisition"  # not the grabbing user's home folder
    acq.model.device_type = "Simulation"
    acq.model.sim_excitation_mode = "Pulsed"
    driver.frame(4)
    driver.hover((12.0, 888.0))
    driver.frame(2)
    driver.screenshot(FIG / "65_acquisition_settings.png")
    print("wrote 65_acquisition_settings.png:", acq.model.device_type, acq.model.sim_excitation_mode, flush=True)
    app.close()
    return app



def _console_alone(names, lines, name, size=(900, 560)):
    """Run *lines* in the shell's ShellConsole hosted alone on the frame loop and save the frame as *name*."""
    from emtk.app import ImApp
    from emtk.testing import Driver

    from chisurf.emtk.console import ShellConsole

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="console59_"))
    console = ShellConsole(dict(names), history_path=tmp / "history.txt", session_file=tmp / "session.py")

    def gui() -> None:
        console.draw((0, 0, *size))
        console.draw_overlays((0, 0, *size))

    driver = Driver(ImApp(gui), size)
    driver.frame(2)
    for line in lines:
        console.execute(line)
        driver.frame(3)
    console.set_input("")
    driver.frame(3)
    print(console.transcript.text()[-800:], flush=True)
    driver.screenshot(FIG / name)
    print("wrote", name, flush=True)


def _grab_59_console():
    """The Console asking ``api`` about a fit that was really run: the shell's FCS demo, loaded, fitted.

    The shell runs the fit on its own session (server on private ports); the console is then given
    that session's ``api`` exactly as the shell gives its Console dock, and drawn alone so the
    transcript has the room.
    """
    import os

    import numpy as np
    from emtk.testing import Driver

    import chisurf
    from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY, READ_KEY
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    shell = EmtkShellApp({}, loader=lambda plugin_id: None)
    shell.data.adopt(session)
    driver = Driver(shell, size=(1500, 950))
    driver.frame(3)
    data = shell.data

    def settle(pred, timeout=180.0):
        end = time.monotonic() + timeout
        while not pred():
            if time.monotonic() > end:
                raise TimeoutError(data.status)
            driver.frame(1)
            time.sleep(0.02)
        driver.frame(2)

    idle = lambda: not data.busy and not data._dirty  # noqa: E731
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    driver.click("read.use_demo")
    driver.frame(2)
    driver.click("read.load")
    settle(lambda: idle() and any(r["name"] == "fcs_demo" for r in data.datasets.datasets))
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    driver.click("datasets.add_fit")
    settle(lambda: idle() and data.windows and data.analysis.info)
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(2)
    before = data.analysis.info["chi2r_current"]
    driver.click("analysis.run_fit")
    settle(lambda: idle() and data.analysis.info.get("chi2r_current") != before)
    names = {"cs": chisurf, "np": np, "os": os, "api": session.api}
    _console_alone(
        names,
        (
            "fits = api.list_fits(statistics=True)",
            "[(f['name'], round(f['chi2r_current'], 3)) for f in fits]",
            "api.get_parameter('N', fit_uid=fits[0]['uid'])['value']",
        ),
        "console.png",
        size=(1000, 320),
    )
    shell.close()


def _grab_59_console_inline_plot():
    """The Console drawing a matplotlib figure inline, under the cell that drew it (as the shell's dock does)."""
    import os

    import numpy as np

    os.environ.setdefault("MPLBACKEND", "agg")
    _console_alone(
        {"np": np},
        ("import pylab as plt; x = np.linspace(0, 10); y = np.sin(x); plt.plot(x, y)",),
        "console_inline_plot.png",
        size=(760, 560),
    )


def _grab_65_live_plots(out=None):
    """The live Decay, Correlation and MCS plots after a pulsed simulator run of 300 000 photons.

    The tool's simulator (one species, pulsed excitation) streamed through the acquisition pipeline into
    :class:`~chisurf.plugins.core.acq.gui.live_plots.LivePlots`, hosted alone; one grab per tab.
    Written to docs/images (or *out*).
    """
    from emtk.testing import Driver

    from chisurf.plugins.core.acq.gui.live_plots import LivePlots, stream_words
    from chisurf.plugins.core.acq.pipeline import AcquisitionPipeline, PipelineConfig
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )
    from chisurf.plugins.core.acq.test.test_live_plots import SIM, PlotsApp

    images = pathlib.Path(out) if out else FIG.parent.parent / "images"
    words = generate_spc132_uint32({**SIM, "pulsed_exc": 1, "N_ph_max": 300000})
    plots = LivePlots()
    pipeline = AcquisitionPipeline(plots.apply_to_config(PipelineConfig(photon_limit=300000)))
    app = PlotsApp(plots)
    stream_words(pipeline, words, app.events, every=8)
    pipeline.flush()
    app.events.put(("snapshot", pipeline.snapshot()))
    size = (1000, 760)
    driver = Driver(app, size)
    driver.frame(5)
    print(plots.qc_text(), flush=True)
    for tab, name in (("Decay", "acq_live_decay.png"), ("Correlation", "acq_live_correlation.png"),
                      ("MCS", "acq_live_mcs.png")):
        driver.click(f"(0,).{tab}")
        driver.frame(5)
        driver.screenshot(images / name)
        print("wrote", name, flush=True)


def _grab_67_nb():
    """Number & Brightness on its own demo: the Brightness ε map, then the parameter plane gated on the dimers."""
    from emtk.testing import Driver
    from emtk_shot import app_from, wait

    from chisurf.core.roi import RectangleROI

    app = app_from("img_pixel_nb")
    model = app.model
    driver = Driver(app, (1200, 800))
    driver.frame(3)
    driver.click("load_example")
    wait(driver, lambda: not app.job.busy and not model.busy, timeout=600)
    driver.frame(4)
    model.view_tab = "Brightness ε"
    model.show_tab()
    driver.frame(5)
    driver.hover((12.0, 788.0))
    driver.frame(2)
    driver.screenshot(FIG / "nb_brightness_map.png")
    print("wrote nb_brightness_map.png |", model.status_line, flush=True)
    model.gates.add(RectangleROI(0.0, 1.75, 3.5, 2.5, name="Rectangle"))
    model.regions_changed()
    model.view_tab = "Parameter plane"
    model.show_tab()
    driver.frame(5)
    try:
        driver.click("Analysis regions")
    except Exception as exc:  # noqa: BLE001 - the fold header may be named differently
        print("no Analysis regions header:", exc, flush=True)
    driver.frame(5)
    driver.hover((12.0, 788.0))
    driver.frame(2)
    driver.screenshot(FIG / "nb_parameter_plane.png")
    print("wrote nb_parameter_plane.png", flush=True)
    app.close()



def _grab_65_record_devices(out=None):
    """Record's TCSPC device panel (a MultiHarp 150 8N as libphacq describes it) and its Laser
    panel (a Sepia II's own controls), cropped to the settings column.

    The MultiHarp is phacq's replay of a recorded session with the real unit (libphacq
    ``tests/data/mh150_t3_live.txt``), shown under the unit's name; the Sepia II is phacq's
    simulated unit. Written to docs/guides/figures (or *out*).
    """
    from emtk.export import save_png
    from PIL import Image

    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live import devices
    from chisurf.plugins.core.acq.live import laser as laser_mod
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    out = pathlib.Path(out or FIG)
    replay = pathlib.Path.home() / "dev" / "libphacq" / "tests" / "data" / "mh150_t3_live.txt"
    mh = devices.DeviceEntry("picoquant", f"replay:{replay}", "PicoQuant", "MultiHarp 150 8N")
    sepia = devices.DeviceEntry("sepia", "sim:", "PicoQuant", "Sepia II")
    devices.attached_devices = lambda drivers=devices.TCSPC_DRIVERS: (
        [mh] if "picoquant" in drivers else [sepia]
    )
    laser_mod._sepia_units = lambda: [sepia]
    size = (1500, 1100)
    with tempfile.TemporaryDirectory() as tmp:
        model = RecordModel(output_dir=tmp, realtime=False)
        model.device_options = lambda: [(mh.key, "PicoQuant MultiHarp 150 8N 1035690")]
        model._update_rates = lambda force=False: None  # a replay has no live rates
        app = RecordApp(model)
        try:
            ui = Driver(app, size)
            model.source_kind, model.device_index = "device", mh.key
            model.advanced = True  # the settings form sits behind Advanced
            ui.draw(2)
            assert model.connect_device(), model.device_text
            app.focus_dock("acquisition")
            ui.draw(4)
            full = out / "_record_full.png"
            save_png(app, str(full), size=size)
            Image.open(full).crop((0, 218, 450, 560)).save(out / "65_record_device.png")
            model.laser_kind = "sepia"
            assert model.connect_laser(), model.laser_detail
            app.focus_dock("laser")
            ui.draw(4)
            save_png(app, str(full), size=size)
            Image.open(full).crop((0, 30, 450, 330)).save(out / "65_record_laser.png")
            full.unlink()
        finally:
            app.close()
