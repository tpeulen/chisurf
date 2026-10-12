"""Figures of the manual's fitting pages, taken from the emtk shell.

Each ``shot_*`` function drives the shell (on a private in-process session, scratch settings) into the
state its figure shows and writes ``docs/manual/figures/<name>.png``. Most use a lifetime fit of the IBH
sample decay (``test/data/tcspc/ibh_sample``) with its measured prompt as IRF; the dock figures are the
Analysis dock floated into a box and cropped, the others the whole window.

    pixi run -e test python docs/guides/screenshots/manual_fitting.py [shot ...]

Writes into ``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manual_shell as M  # noqa: E402
from manual_shell import ManualShell  # noqa: E402

#: Where the dock box is floated: below the ribbon, which the shell keeps clear.
TOP = 125


def _analysis(shell, name: str, *open_titles: str, fit: bool = False, height: int = 480, width: int = 560,
              skip: int = 0):
    """Float the Analysis dock with only *open_titles* open; write it cropped to *height*, *skip* rows off the top."""
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    shell.show_analysis()
    shell.folds(*open_titles, fit=fit)
    return shell.crop_dock(ANALYSIS_KEY, name, (10, TOP, width, height), skip=skip)


def shot_convolution(s: ManualShell) -> None:
    """Fig.20: the Convolution box of a lifetime fit with the prompt loaded as IRF."""
    s.ibh_fit()
    _analysis(s, "manual_convolution.png", "Convolution", height=395, skip=70)


def shot_generic(s: ManualShell) -> None:
    """Fig.21: the Generic box with a background pattern loaded."""
    prompt = s.load_ibh("Prompt.txt")
    s.ibh_fit()
    s.folds("Generic", fit=False)
    s.pick_curve("generic.background_curve", prompt)
    _analysis(s, "manual_generic.png", "Generic", height=272, skip=88)


def shot_corrections(s: ManualShell) -> None:
    """Fig.22: the Corrections box with the white-light linearisation table loaded."""
    table = s.load_ibh("whitelight.txt")
    s.ibh_fit()
    s.folds("Corrections", fit=False)
    s.pick_curve("corrections.lintable", table)
    _analysis(s, "manual_corrections.png", "Corrections", height=254, skip=106)


def shot_fit_controller(s: ManualShell) -> None:
    """Fig.11: the Fit box (dataset, scoring range, Fit / MCTS / Sample)."""
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    s.ibh_fit()
    s.show_analysis()
    s.folds(fit=True)
    # Float the dock taller than the box and crop at the drawn rectangles: from the Fit fold to the
    # first editor fold below it, so the χ²ᵣ status line under the checkboxes is always whole.
    docks = s.app.docks
    docks.undock(ANALYSIS_KEY, (10.0, float(TOP), 560.0, 400.0))
    docks.focus(ANALYSIS_KEY)
    s.driver.hover((1495.0, 5.0))  # no tooltip over the figure
    s.driver.frame(5)
    rects = s.app.item_rects
    top = rects["analysis.Fit.fold"][1] - 2
    below = min(r[1] for k, r in rects.items() if k.startswith("editor.") and k.endswith(".fold") and r[1] > top)
    s.save("manual_fit_controller.png", crop=(10, top, 570, below - 2))


def shot_parameter_table(s: ManualShell) -> None:
    """Fig.10: a parameter table and the link menu a right click on a parameter opens (``ts``, the time shift)."""
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    s.ibh_fit()
    s.show_analysis()
    s.folds("Convolution", fit=False)
    s.app.docks.undock(ANALYSIS_KEY, (10.0, float(TOP), 560.0, 400.0))
    s.app.docks.focus(ANALYSIS_KEY)
    s.driver.frame(5)
    row = next(
        r
        for name, rows in s.data.editor._sources.items()
        if name.startswith("rows_")
        for r in rows
        if r.get("label") == "ts" or r.get("name") == "timeshift"
    )
    s.data.editor.section_context(row, "value", (300.0, float(TOP + 320)))
    s.settle(lambda: s.idle() and s.data.editor.sections.dialogs, "the link menu")
    s.driver.hover((1495.0, 5.0))
    s.driver.frame(4)
    s.save("manual_parameter_table.png", crop=(10, TOP + 70, 800, TOP + 470))


def shot_scoring_range(s: ManualShell) -> None:
    """Fig.12: the scoring range in the Fit box and on the Fit plot."""
    s.ibh_fit()
    s.show_analysis()
    s.folds(fit=True)
    s.page("Fit")
    s.save("manual_scoring_range.png", crop=(0, 120, 1500, 800))


def shot_fit_before_after(s: ManualShell) -> None:
    """Fig.13: the same fit before (a) and after (b) pressing Fit."""
    s.ibh_fit(run=False)
    s.show_analysis()
    s.folds("Lifetimes", fit=True)
    s.page("Fit")
    before = s.save("_before.png", crop=(0, 120, 1500, 950))
    s.run_fit()
    s.driver.frame(4)
    after = s.save("_after.png", crop=(0, 120, 1500, 950))
    s.stack("manual_fit_before_after.png", [before, after], ["a  before Fit", "b  after Fit"])
    before.unlink()
    after.unlink()


def shot_sampling(s: ManualShell) -> None:
    """Fig.15: a sampled fit -- Sample in the Fit box, the chain on Chain diagnostics."""
    from chisurf.core import settings
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    s.ibh_fit()
    s.show_analysis()
    s.folds(fit=True)
    sampling = settings.cs_settings["optimization"].setdefault("sampling", {})
    sampling.update(steps=2000, n_runs=4, method="blocked", thin=1)
    s.driver.click("analysis.sample")
    s.driver.frame(2)
    done, s.data.file_dialog = s.data._file_done, None
    done(tempfile.mkdtemp(prefix="manual-sampling-"))
    s.settle(lambda: s.idle() and s.data.sampling_job, "the sampling job")
    s.settle(lambda: not s.data.sampling_job, "the sampling verdict", timeout=900.0)
    s.app.docks.focus(ANALYSIS_KEY)
    s.page("Chain diagnostics")
    s.driver.frame(10)
    s.save("manual_sampling.png", crop=(0, 120, 1500, 800))


def shot_equation_parsing(s: ManualShell) -> None:
    """Fig.23: a parsed decay model (2-Lifetimes) fitted to the IBH donor decay."""
    s.ibh_fit(model="Parse-Model", run=False)
    editor = s.data.editor
    setattr(editor, editor.control_for("model_name"), "2-Lifetimes")
    s.settle(s.idle, "the equation")
    for name, value in (("a1", 0.5), ("tau1", 4.0), ("a2", 0.5), ("tau2", 1.0)):
        row = next(r for rows in editor._sources.values() for r in rows if r.get("label", r.get("name")) == name)
        editor.edit_cell(row, "value", value)
        s.settle(s.idle, name)
    s.show_analysis()
    s.run_fit()
    s.folds("Equation", "Equation parameters", fit=False)
    s.page("Fit")
    s.save("manual_equation_parsing.png", crop=(0, 120, 1500, 800))


def shot_donor_reference(s: ManualShell) -> None:
    """Fig.24: a FRET fit of the donor-acceptor sample, raw (a) and relative to its donor reference (b)."""
    from chisurf.emtk.fit_docks import PLOT_KEY

    s.ibh_fit("Decay_577D+577A+GTPgS.txt", model="FRET: Gaussian distances")
    page = s.page("Fit")
    window = (410, 158, 1500, 785)  # below the window's Code button, from the page tabs down
    raw = s.save("_raw.png", crop=window)
    model = page.settings_model()
    model.reference_mode = "tcspc_donor_reference"
    model.log_y = False  # a ratio reads on a linear axis
    model.curve_visibility["IRF"] = False  # not transformed: raw counts would fill the axis
    page.update()
    s.driver.frame(8)
    reference = s.save("_ref.png", crop=window)
    settings = s.crop_dock(PLOT_KEY, "_settings.png", (10, TOP, 400, 330))
    s.stack("manual_donor_reference.png", [raw, settings, reference],
            ["a  Raw", "b  Plot settings", "c  Donor reference"], vertical=False)
    for path in (raw, settings, reference):
        path.unlink()


def shot_calculators(s: ManualShell) -> None:
    """Fig.25: the Calculators hub on F-test / chi2-max (a) and FRET / homoFRET (b)."""
    from emtk.testing import Driver

    from chisurf.plugins.calculator.hub.gui.app import make_app

    paths = []
    for entry in ("f_test", "fret_calculator"):
        hub = make_app()
        hub.select(entry)
        driver = Driver(hub, (1000, 640))
        driver.settle()
        driver.frame(6)
        path = M.OUT / f"_calc_{entry}.png"
        driver.screenshot(path)
        paths.append(path)
    s.stack("manual_calculators.png", paths, ["a", "b"], vertical=False)
    for path in paths:
        path.unlink()
    print("wrote manual_calculators.png", flush=True)


def shot_parameter_link(s: ManualShell) -> None:
    """Fig.36: the lifetimes of a second fit linked to the first (a), and the menu that links them (b)."""
    from chisurf.emtk.fit_docks import ANALYSIS_KEY

    first = s.ibh_fit()
    s.ibh_fit("Decay_577D+577A+GTPgS.txt", run=False)
    s.show_analysis()
    s.folds("Lifetimes", fit=False)
    docks = s.app.docks
    docks.undock(ANALYSIS_KEY, (10.0, float(TOP), 700.0, 330.0))
    docks.focus(ANALYSIS_KEY)
    s.driver.frame(5)
    link = "amplitudes.lifetime_amplitude_options:lifetimes.link"
    s.click_editor(link)
    menu = s.data.editor.sections.dialogs[-1]
    s.driver.hover((1495.0, 5.0))
    s.driver.frame(4)
    opened = s.save("_menu.png", crop=(10, TOP + 70, 710, TOP + 290))
    call = next(
        c for c in menu.calls.values()
        if c.__defaults__[0]["fit_uid"] == first and c.__defaults__[0]["group"] == "lifetimes"
    )
    menu.panel.open = False
    call()
    s.settle(s.idle, "the link")
    s.driver.frame(4)
    linked = s.save("_linked.png", crop=(10, TOP + 70, 710, TOP + 290))
    s.stack("manual_parameter_link.png", [linked, opened], ["a  linked", "b  the link menu"])
    linked.unlink()
    opened.unlink()


def shot_global_view(s: ManualShell) -> None:
    """Fig.37: the two linked fits of Fig.36 in Global View; the link is the arrow to the followed parameter."""
    from emtk.testing import Driver

    from chisurf.emtk.fit_docks import ANALYSIS_KEY
    from chisurf.plugins.core.globalview.gui.app import make_app

    first = s.ibh_fit()
    s.ibh_fit("Decay_577D+577A+GTPgS.txt", run=False)
    s.show_analysis()
    s.folds("Lifetimes", fit=False)
    s.app.docks.undock(ANALYSIS_KEY, (10.0, float(TOP), 700.0, 330.0))
    s.app.docks.focus(ANALYSIS_KEY)
    s.driver.frame(5)
    s.click_editor("amplitudes.lifetime_amplitude_options:lifetimes.link")
    menu = s.data.editor.sections.dialogs[-1]
    call = next(
        c for c in menu.calls.values()
        if c.__defaults__[0]["fit_uid"] == first and c.__defaults__[0]["group"] == "lifetimes"
    )
    menu.panel.open = False
    call()
    s.settle(s.idle, "the link")
    # Global View reads the session's own fit objects.
    from chisurf.plugins.core.globalview.gui.model import GlobalViewModel

    app = make_app(GlobalViewModel(fits=lambda: list(s.state.fits)), remember_layout=False)
    driver = Driver(app, (1200, 760))
    driver.frame(12)
    model = app.model
    follower = next(r for r in model.parameter_records() if r.get("follower") and r["parameter"] == "t0")
    model.select_parameter(follower)
    driver.frame(10)
    path = M.OUT / "manual_global_view.png"
    driver.screenshot(path)
    print("wrote manual_global_view.png", flush=True)


SHOTS = {
    "convolution": shot_convolution,
    "generic": shot_generic,
    "corrections": shot_corrections,
    "fit_controller": shot_fit_controller,
    "parameter_table": shot_parameter_table,
    "scoring_range": shot_scoring_range,
    "fit_before_after": shot_fit_before_after,
    "sampling": shot_sampling,
    "equation_parsing": shot_equation_parsing,
    "donor_reference": shot_donor_reference,
    "calculators": shot_calculators,
    "parameter_link": shot_parameter_link,
    "global_view": shot_global_view,
}


#: Shots that need a taller window than the default 1500 x 950.
SIZES = {"fit_before_after": (1500, 1100)}


def main(names) -> None:
    """Take the shots named in *names* (all when empty), each in a fresh shell."""
    for name in names or list(SHOTS):
        shell = ManualShell(size=SIZES.get(name, (1500, 950)))
        SHOTS[name](shell)
        shell.close()
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
