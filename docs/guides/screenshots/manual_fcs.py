"""Screenshots of the FCS chapters of the manual (``docs/manual/``), of today's ChiSurf.

They replace the pictures extracted from the historical Word manual. Each
``grab_*`` function drives the emtk shell (the default ChiSurf window), driven with ``emtk.testing.Driver``, with data bundled in
the repository and writes into ``docs/manual/figures/``::

    CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) IMP_BFF_GPU=off \
    pixi run -e test python docs/guides/screenshots/manual_fcs.py grab_fcs_walkthrough

Run one function per process (each builds its own main window). Read every
PNG afterwards: a grab that ran is not a figure that looks right.

The A488 walkthrough of ``fit_of_a_fcs_curve.md`` needs several measurements of
one free dye. The repository bundles three Zeiss Confocor3 measurements of
Alexa 488 (``test/data/fcs/confocor3``); the autocorrelation of detector 1 of
each is written as a Seidel *Kristine* ``.cor`` file into a scratch folder and
loaded through the GUI, as the manual's text describes.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import shell_driver as sd  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "manual" / "figures"
CONFOCOR3 = pathlib.Path("test/data/fcs/confocor3/Zeiss_Confocor3_A488+GFP")


def _native_shot(app, name: str, frames: int = 6, size=(1200, 800)) -> None:
    """Draw a native emtk app a few frames and save the last into ``OUT``."""
    from emtk.pil_painter import PilPainter

    OUT.mkdir(parents=True, exist_ok=True)
    painter = None
    for _ in range(frames):
        painter = PilPainter(*size)
        app.draw(painter, 0, 0, *size)
    painter.frame.save(OUT / name)
    print("wrote", name, flush=True)


# --------------------------------------------------------------------------
# Correlator workflow (FCS hub)
# --------------------------------------------------------------------------


def grab_correlator_steps() -> None:
    """The FCS hub's Correlator and FCS Merger steps on its simulated example.

    *Files & Steps* adds the hub's simulated two-channel TTTR example with the
    merger step switched on; the correlator splits it into 6 subsets
    (Laurence algorithm), the merger then lists the subsets and their merged
    curve.
    """
    import time

    from emtk.pil_painter import PilPainter

    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

    hub = make_app()
    files = hub.select("files")
    files.load_example()
    files.use_merger = True
    hub._files_changed()
    corr = hub.select("correlator")
    corr.model.channel_a, corr.model.channel_b, corr.model.n_splits = "0", "1", 6
    corr.model.method = "laurence"
    corr.correlate(wait=True)
    _native_shot(hub, "fcs_correlator_step.png")
    merger = hub.select("merger")
    end = time.time() + 60
    while time.time() < end:
        hub.draw(PilPainter(1200, 800), 0, 0, 1200, 800)
        rows = getattr(getattr(merger, "model", None), "rows", None)
        if rows:
            break
        time.sleep(0.05)
    _native_shot(hub, "fcs_merger_step.png")
    hub.close()


# --------------------------------------------------------------------------
# The walkthrough in the emtk shell
# --------------------------------------------------------------------------

FORMULA = "3D Gauss, 1 bunching"
#: The parameters of :data:`FORMULA`, the ones :func:`_report` prints.
SHOWN = ("b", "N", "td", "s", "ba", "bt")


def _a488_kristine_files() -> list[str]:
    """The AC1 curve of each bundled Confocor3 A488 measurement, as Kristine ``.cor``."""
    import numpy as np

    from chisurf.core.fio.fluorescence.fcs.confocor3 import read_zeiss_fcs
    from chisurf.core.fio.fluorescence.fcs.kristine import write_kristine

    work = pathlib.Path(tempfile.mkdtemp(prefix="a488-"))
    paths = []
    for number, source in enumerate(sorted(CONFOCOR3.glob("00*_A488.fcs")), 1):
        curve = read_zeiss_fcs(str(source))[0]  # detector 1 autocorrelation
        path = work / f"A488_ACF_{number}.cor"
        write_kristine(
            filename=str(path),
            correlation_time=curve["correlation_times"],
            correlation_amplitude=curve["correlation_amplitudes"],
            correlation_amplitude_uncertainty=1.0 / np.asarray(curve["correlation_amplitude_weights"]),
            acquisition_time=curve["acquisition_time"],
            mean_countrate=curve["mean_count_rate"],
            verbose=False,
        )
        paths.append(str(path))
    return paths


def _dataset(app, name: str) -> dict:
    """The row of the dataset *name* in the Datasets dock."""
    return next(r for r in app.data.datasets.datasets if r["name"] == name)


def _fit(app, name: str) -> dict:
    """The fit row whose data name is *name*."""
    return next(r for r in app.data.datasets.fits if r["name"] == name)


def _add_fit(driver, wait, dataset: str, model: str) -> str:
    """Select *dataset*, choose *model* and press **+ Analysis**; returns the new fit's uid."""
    from chisurf.emtk.fit_docks import DATASETS_KEY

    app = driver.app
    app.docks.focus(DATASETS_KEY)
    driver.frame(2)
    app.data.datasets.select_dataset(_dataset(app, dataset))
    app.data.datasets.model = model
    driver.frame(2)
    known = {r["uid"] for r in app.data.datasets.fits}
    driver.click("datasets.add_fit")
    wait(lambda: sd.idle(app) and {r["uid"] for r in app.data.datasets.fits} - known and app.data.analysis.info)
    return next(r["uid"] for r in app.data.datasets.fits if r["uid"] not in known)


def _formula(driver, wait, uid: str) -> None:
    """Choose the equation :data:`FORMULA` in the Equation section of fit *uid*."""
    app = driver.app
    sd.show(driver, wait, uid)
    app.data.set_model_state("model_name", FORMULA, "Model")
    wait(lambda: sd.idle(app))


def _range(driver, wait, uid: str, last: int) -> None:
    """Fit range: the second point (the first carries afterpulsing) to index *last*."""
    app = driver.app
    sd.show(driver, wait, uid)
    app.data.set_range(1, last)
    wait(lambda: sd.idle(app))


def _row(app, name: str) -> dict:
    """The parameter-table row *name* of the model editor."""
    return next(
        r
        for src, rows in app.data.editor._sources.items()
        if src.startswith("rows_")
        for r in rows
        if r.get("name") == name
    )


def _report(app, uid: str, label: str) -> None:
    """Print fit *uid*'s χ²ᵣ and parameter values, so the page's numbers can be checked against the figure."""
    info = app.data.session.api.get_fit_info(fit_uid=uid)
    info = info.get("fit", info)
    model = info.get("model") or (info.get("members") or [{}])[0]
    values = {p["name"]: round(p["value"], 5) for p in model.get("parameters_all", []) if p["name"] in SHOWN}
    print(label, info.get("name"), "chi2r", info.get("chi2r"), values, flush=True)


def grab_fcs_walkthrough() -> None:
    """``fit_of_a_fcs_curve.md``: load, add fits, choose the model, fit, link, global fit."""
    import chisurf as cs
    from chisurf.emtk.fit_docks import DATASETS_KEY, READ_KEY

    OUT.mkdir(parents=True, exist_ok=True)
    driver, wait = sd.shell()
    app = driver.app
    data = app.data

    app.docks.focus(READ_KEY)
    data.read.experiment = "FCS"
    data.read.experiment_changed("FCS")
    data.read.setup = "Seidel Kristine"
    data.read.setup_changed("Seidel Kristine")
    driver.frame(3)
    sd.shot_shell(driver, "fcs_main_window.png")

    for path in _a488_kristine_files():
        data.read.path = path
        driver.click("read.load")
        wait(lambda: sd.idle(app))
    app.docks.focus(DATASETS_KEY)
    driver.frame(3)
    sd.shot_shell(driver, "fcs_datasets_added.png")

    data.datasets.select_dataset(_dataset(app, "A488_ACF_1"))
    data.datasets.model = "Parse-Model"
    driver.frame(3)
    sd.shot_shell(driver, "fcs_add_analysis.png")

    app.docks.hide("start")
    uids = [_add_fit(driver, wait, f"A488_ACF_{n}", "Parse-Model") for n in (1, 2, 3)]
    sd.show(driver, wait, uids[0])
    app.tab_windows()
    sd.show(driver, wait, uids[2])
    sd.shot_shell(driver, "fcs_fit_windows.png")
    sd.show(driver, wait, uids[1])
    sd.shot_shell(driver, "fcs_fit_windows_tabbed.png")
    sd.tile(app, first=uids[0])
    sd.show(driver, wait, uids[0])
    sd.shot_shell(driver, "fcs_fit_windows_tiled.png")
    app.tab_windows()

    _formula(driver, wait, uids[0])
    sd.shot_shell(driver, "fcs_model_3d_gauss_bunching.png")
    sd.shot_region(driver, "fcs_model_parameters.png")

    sd.run(driver, wait)
    _report(app, uids[0], "first fit")
    sd.shot_shell(driver, "fcs_first_fit.png")

    # the first point carries detector afterpulsing, the long-lag tail is noise:
    # start at the second point and end the fit range at ~100 ms
    x = cs.fits[0].data.x
    last = int(abs(x - 100.0).argmin())
    _range(driver, wait, uids[0], last)
    sd.shot_shell(driver, "fcs_fit_range.png")
    sd.run(driver, wait)
    _report(app, uids[0], "second fit")
    sd.shot_shell(driver, "fcs_second_fit.png")

    for uid in uids[1:]:
        _formula(driver, wait, uid)
        _range(driver, wait, uid, last)
        sd.run(driver, wait)
        _report(app, uid, "alone")
    sd.tile(app, first=uids[0])
    sd.show(driver, wait, uids[0])
    sd.shot_shell(driver, "fcs_all_fitted.png")

    # link td, s and bt of curve 2 to curve 1 through each row's menu
    info = data.session.api.get_fit_info(fit_uid=uids[0])
    info = info.get("fit", info)
    parent = {p["name"]: p["uid"] for p in info["model"]["parameters_all"]}
    sd.tile(app, first=uids[1])
    sd.show(driver, wait, uids[1])
    row = _row(app, "td")
    data.editor.section_context(row, "value", (250.0, 880.0))
    wait(lambda: sd.idle(app) and data.editor.sections.dialogs)
    driver.click("🔗 Link td to")  # opens the list of the session's fits
    driver.frame(4)
    sd.shot_shell(driver, "fcs_link_menu.png")
    data.editor.sections.dialogs[-1].panel.open = False
    driver.frame(2)
    for uid in uids[1:]:
        sd.tile(app, first=uid)
        sd.show(driver, wait, uid)
        for name in ("td", "s", "bt"):
            data.link_model_parameter(_row(app, name), parent[name])
            wait(lambda: sd.idle(app))
        # Fit the child once: linked to curve 1's td, s and bt, its own N and ba (fitted alone against
        # a 33 µs bt) are far off -- a model with a bunching bump over the data until they are refitted.
        sd.run(driver, wait)
        _report(app, uid, "linked")
    sd.shot_region(driver, "fcs_linked_parameters.png")

    # a global fit over the three curves
    app.docks.focus(DATASETS_KEY)
    data.datasets.select_dataset(_dataset(app, "Global Dataset"))
    data.datasets.model = "Global fit"
    driver.frame(3)
    sd.shot_shell(driver, "fcs_add_global_fit.png")

    # the global fit: its window, the three curves added under Local fits, then Fit. Until it has run,
    # curves 2 and 3 show curve 1's td, s and bt with their own (alone-fitted) N and ba -- a model far off
    # the data -- so the closing figure is taken after the joint fit.
    known = {r["uid"] for r in data.datasets.fits}
    driver.click("datasets.add_fit")
    wait(lambda: sd.idle(app) and len({r["uid"] for r in data.datasets.fits} - known) == 1)
    glob = next(r["uid"] for r in data.datasets.fits if r["uid"] not in known)
    sd.show(driver, wait, glob)
    editor = data.editor
    candidate = editor.control_for("selected_candidate_fit")
    add = editor.action_for("press", "add_selected_fit")
    names = {r["uid"]: r["name"] for r in data.datasets.fits}
    for uid in uids:
        setattr(editor, candidate, names[uid])
        wait(lambda: sd.idle(app))
        driver.click(f"editor.{add}")
        wait(lambda: sd.idle(app))
    sd.run(driver, wait)
    _report(app, glob, "global")
    for uid in uids:
        _report(app, uid, "joint")
    sd.tile(app, first=glob)
    for uid in uids:
        data.show_fit(uid)
        driver.frame(3)
    sd.show(driver, wait, glob)
    sd.shot_shell(driver, "fcs_global_fit.png")

    # File -> Fits
    driver.click("menu.File")
    driver.frame(3)
    sd.shot_shell(driver, "fcs_file_menu.png")
    os._exit(0)


def main(names: list[str]) -> None:
    """Run the named ``grab_*`` functions, then leave without the interpreter teardown."""
    for name in names:
        globals()[name]()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
