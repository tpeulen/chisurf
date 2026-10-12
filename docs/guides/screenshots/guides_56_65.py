"""Grab functions for guides 56, 57, 65.

The guide-55 flow grab is left out on purpose: the flow demo currently draws
no arrows (known-issues), and re-grabbing would overwrite the figure that
shows the intended result.

Uses FIG and _pump from common.py. Each
function saves into FIG. Run each in its own subprocess with a timeout: the
acquisition and main-window grabs start threads and servers.
"""
import pathlib, tempfile, time

from common import FIG, _pump  # noqa: F401

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

