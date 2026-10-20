"""Figures of the manual's anisotropy pages: the Anisotropy wizard and the fits it builds.

The data are the stacked VV/VH recording bundled in ``test/data/tcspc/Jordi``: a
water-scatter IRF (``H2O_8-0 ps_2048 ch.dat``) and a dye decay
(``02_18-577+7.5uM(577)UP_8ps.dat``), 2048 channels of 8 ps each, the VV
channel followed by the VH channel in one column. For the "two single files"
layout the same measurement is written as four two-column files (time, counts)
into a scratch folder first.

    IMP_BFF_GPU=off pixi run -e test python docs/guides/screenshots/manual_anisotropy.py wizard
    IMP_BFF_GPU=off pixi run -e test python docs/guides/screenshots/manual_anisotropy.py main
    IMP_BFF_GPU=off pixi run -e test python docs/guides/screenshots/manual_anisotropy.py ribbon

``main`` drives the emtk shell (the default ChiSurf window) with ``emtk.testing.Driver``.

Writes into ``docs/manual/figures/``. Run from the repository root, offscreen.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.getcwd())
import numpy as np  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import shell_driver as sd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "manual" / "figures"
DATA = ROOT / "test" / "data" / "tcspc" / "Jordi"
IRF = DATA / "H2O_8-0 ps_2048 ch.dat"
DECAY = DATA / "02_18-577+7.5uM(577)UP_8ps.dat"
#: Channel width of the recording, ns.
BIN = 0.008
#: A second recording of the same dye (9 ps channels): the "second sample" of the joint fit.
IRF2 = DATA / "H2O_9-1 ps_2048 ch.dat"
DECAY2 = DATA / "02_18-577+7.5uM(577)UP_9ps.dat"
BIN2 = 0.009
#: The corrections the manual's first pass starts from.
CORRECTIONS = {"g_factor": 1.16, "l1": 0.12, "l2": 0.44}


def _say(name: str) -> None:
    print("wrote", name, flush=True)


def _shot(ui, name: str) -> None:
    """Park the pointer over empty space (no hover tooltip), then grab *name*."""
    ui.app.pointer_move(120.0, float(ui.size[1]) - 60.0)
    ui.draw(3)
    ui.screenshot(OUT / name)
    _say(name)


def _hermetic() -> pathlib.Path:
    """A scratch settings folder with the corrections the manual quotes (g 1.16, l1 0.12, l2 0.44)."""
    import json

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="manual-anisotropy-"))
    os.environ["CHISURF_SETTINGS_DIR"] = str(scratch / "settings")
    os.environ["MMFDB_SETTINGS_DIR"] = str(scratch / "mmfdb")
    (scratch / "settings").mkdir(parents=True, exist_ok=True)
    (scratch / "settings" / "anisotropy_corrections.json").write_text(
        json.dumps({"g_factor": 1.16, "l1": 0.12, "l2": 0.44})
    )
    return scratch


def split_into_two_column_files(folder: pathlib.Path) -> dict:
    """Write the stacked recording as four ``time counts`` files (the two-file layout)."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, path in (("irf", IRF), ("data", DECAY)):
        counts = np.loadtxt(path)
        half = len(counts) // 2
        x = np.arange(half) * BIN
        for channel, part in (("vv", counts[:half]), ("vh", counts[half:])):
            target = folder / f"{name}_{channel.upper()}.txt"
            np.savetxt(target, np.column_stack((x, part)), fmt=["%.3f", "%d"])
            out[f"{name}_{channel}"] = str(target)
    return out


def wizard() -> None:
    """The six steps of the Anisotropy wizard (its emtk window), driven with the bundled data."""
    scratch = _hermetic()
    import chisurf.core.settings as settings

    settings.chisurf_settings_path = scratch / "settings"
    from chisurf.plugins.emtk_test_input import Driver
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app

    OUT.mkdir(parents=True, exist_ok=True)
    size = (1100, 720)

    ui = Driver(make_app(), size=size)
    ui.draw()
    ui.click_name("Data")
    _shot(ui, "anisotropy_wizard_data_empty.png")

    # two single files with a time column
    # a short, readable folder: the paths are shown in the fields
    files = split_into_two_column_files(pathlib.Path("/tmp/chisurf_anisotropy_example"))
    m = ui.app.model
    m.stacked_files = False
    m.first_column_is_time = True
    m.use_header = False
    m.skiprows = 0
    for key, path in files.items():
        setattr(m, key + "_path", path)
    ui.draw()
    _shot(ui, "anisotropy_wizard_two_files.png")

    # the stacked VV/VH layout: one IRF file, one data file
    ui = Driver(make_app(), size=size)
    ui.draw()
    ui.click_name("Data")
    m = ui.app.model
    m.stacked_files = True
    m.first_column_is_time = False
    m.use_header = False
    m.bin_width = BIN
    m.irf_vv_path = str(_recorded_at(IRF, 80.0))
    m.data_vv_path = str(_recorded_at(DECAY, 80.0))
    m.load_data()  # the laser rate in the file footer fills the Repetition rate field
    ui.draw()
    _shot(ui, "anisotropy_wizard_stacked.png")

    ui.click_name("Normalize IRF")
    ui.click_text("Load / reload data")
    ui.draw(4)
    _shot(ui, "anisotropy_wizard_normalize_irf.png")

    ui.click_name("Corrections")
    _shot(ui, "anisotropy_wizard_corrections.png")

    ui.click_name("Components")
    _shot(ui, "anisotropy_wizard_components.png")


    # re-using calibrated corrections on a new sample: values typed into the steps
    m.g_factor, m.l1, m.l2 = 1.01, 0.0437, 0.349
    m.lifetime_spectrum = [[0.7, 2.6], [0.3, 1.6]]
    m.rotation_spectrum = [[0.38, 10.0]]
    ui.click_name("Components")
    _shot(ui, "anisotropy_wizard_components_reuse.png")
    os._exit(0)


def _recorded_at(path, rate_mhz):
    """A scratch copy of the recording whose footer names its laser rate (``# rep_rate: MHz``).

    The bundled files carry no metadata; a VV/VH file written by an acquisition says its rate and the
    wizard reads it into its *Repetition rate* field, which is what this copy stands in for.
    """
    import pathlib as _p
    import tempfile as _t

    folder = _p.Path(_t.gettempdir()) / "chisurf_anisotropy_recordings"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / _p.Path(path).name
    target.write_text(_p.Path(path).read_text() + f"# rep_rate: {rate_mhz}\n")
    return target


def _wizard_in_shell(driver, wait, irf, decay, bin_width=BIN, rate=80.0):
    """Open the Anisotropy Wizard in the shell (Tools › Wizards), load the stacked files, create the fits.

    Returns the three fit uids ``(vv, vh, global)`` in creation order.
    """
    app = driver.app
    known = {r["uid"] for r in app.data.datasets.fits}
    hosted = app.open_plugin("tr_anisotropy")
    wait(lambda: hosted.app is not None or bool(hosted.error))
    m = hosted.app.model
    m.stacked_files = True
    m.first_column_is_time = False
    m.use_header = False
    m.bin_width = bin_width
    m.irf_vv_path = str(_recorded_at(irf, rate))
    m.data_vv_path = str(_recorded_at(decay, rate))
    assert m.load_data(), m.status
    assert m.create_fits(), m.status
    wait(lambda: len({r["uid"] for r in app.data.datasets.fits} - known) >= 3 and sd.idle(app))
    new = [r for r in app.data.datasets.fits if r["uid"] not in known]
    app.close_plugin("tr_anisotropy")
    driver.frame(3)
    by_name = {r["name"]: r["uid"] for r in new}
    return (
        next(u for n, u in by_name.items() if n.endswith("VV")),
        next(u for n, u in by_name.items() if n.endswith("VH")),
        next(u for n, u in by_name.items() if n.startswith("Global")),
    )


def _free_corrections(driver, wait, uid: str) -> None:
    """Untick *Fixed* of g, l1 and l2 of fit *uid* (the VH fit follows through its links)."""
    app = driver.app
    sd.show(driver, wait, uid)
    for name in ("g", "l1", "l2"):
        row = next(
            r
            for src, rows in app.data.editor._sources.items()
            if src.startswith("rows_")
            for r in rows
            if r.get("name") == name
        )
        app.data.edit_model_parameter(row, "fixed", False)
        wait(lambda: sd.idle(app))


def _ribbon_shot(driver) -> None:
    """Where the wizard is: the ribbon's Tools tab, Wizards group."""
    app = driver.app
    app.ribbon.ribbon.current = "Tools"
    sd.shot_shell(driver, "anisotropy_ribbon_tools.png")
    app.ribbon.ribbon.current = "Spectroscopy"


def ribbon() -> None:
    """Only ``anisotropy_ribbon_tools.png`` (the first shot of :func:`main_window`)."""
    scratch = _hermetic()
    import chisurf.core.settings as settings

    settings.chisurf_settings_path = scratch / "settings"
    OUT.mkdir(parents=True, exist_ok=True)
    driver, _wait = sd.shell()
    _ribbon_shot(driver)
    os._exit(0)


def main_window() -> None:
    """The shell with the fits the wizard builds, and the global fit across two samples."""
    scratch = _hermetic()
    import chisurf.core.settings as settings

    settings.chisurf_settings_path = scratch / "settings"
    OUT.mkdir(parents=True, exist_ok=True)
    driver, wait = sd.shell()
    app = driver.app

    _ribbon_shot(driver)

    # first sample: the wizard's fits, with the corrections the manual starts from
    vv, vh, glob = _wizard_in_shell(driver, wait, IRF, DECAY)
    sd.tile(app, first=vv)
    sd.show(driver, wait, vv)
    sd.shot_shell(driver, "anisotropy_fit_windows.png")
    sd.shot_region(driver, "anisotropy_analysis_vv.png")
    sd.tile(app, first=vh)
    sd.show(driver, wait, vh)
    sd.shot_region(driver, "anisotropy_analysis_vh.png")

    # step 1: each polarisation fitted alone, corrections fixed -- VV first, then VH, as the page says
    sd.tile(app, first=vv)
    sd.show(driver, wait, vv)
    sd.run(driver, wait)
    sd.show(driver, wait, vh)
    sd.run(driver, wait)  # then the VH fit, as the page says
    sd.tile(app, first=vv)
    sd.show(driver, wait, vv)
    sd.shot_shell(driver, "anisotropy_step1_vv_fit.png")

    # step 2: corrections free (on VV), then the joint fit
    _free_corrections(driver, wait, vv)
    sd.shot_region(driver, "anisotropy_step2_corrections_free.png")
    sd.tile(app, first=glob)
    sd.show(driver, wait, glob)
    sd.run(driver, wait)
    sd.shot_shell(driver, "anisotropy_step2_global_fit.png")

    # the second sample, the same way: six fit windows, tabbed, and the Datasets dock listing the fits
    from chisurf.emtk.fit_docks import DATASETS_KEY

    _wizard_in_shell(driver, wait, IRF2, DECAY2, bin_width=BIN2, rate=71.0)
    app.docks.hide("start")
    app.tab_windows()
    sd.show(driver, wait, glob)  # the first sample's (fitted) global fit in front
    app.docks.focus(DATASETS_KEY)
    driver.frame(4)
    sd.shot_shell(driver, "anisotropy_two_samples.png")
    os._exit(0)


if __name__ == "__main__":
    {"wizard": wizard, "main": main_window, "ribbon": ribbon}[sys.argv[1]]()
