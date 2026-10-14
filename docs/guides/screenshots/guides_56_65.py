"""Grab functions for guides 55, 56, 57, 59, 65.

Uses FIG and _pump from common.py. Each
function saves into FIG. Run each in its own subprocess with a timeout: the
acquisition and main-window grabs start threads and servers.
"""
import pathlib, tempfile, time

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
    import time

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
