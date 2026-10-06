"""Figures of the manual's fitting pages, taken from the current ChiSurf.

Each ``shot_*`` function drives a real Main (offscreen) into the state its
figure shows and writes ``docs/manual/figures/<name>.png``. Most use a
lifetime fit of the IBH sample decay (``test/data/tcspc/ibh_sample``) with its
measured prompt as IRF; the FRET and parsed-equation figures open produced
catalogue science (``python -m test.project.scientific_catalogue_probe --case N
DIR``: case 2 is ``tcspc_fret_gaussian``, case 9 ``ParseDecayModel``).

    python docs/guides/screenshots/manual_fitting.py CASE0_DIR CASE2_DIR CASE9_DIR [shot ...]

Writes into ``docs/manual/figures/``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
# Before anything else: chisurf's imports pull in the standard library's ``test``
# package, which would then shadow the repository's.
from test.gui.fit_window_page_probe import _frames, _open_main  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "manual" / "figures"
IBH = pathlib.Path("test/data/tcspc/ibh_sample")


# -- plumbing -------------------------------------------------------------------


def _pump(app, n: int = 8) -> None:
    for _ in range(n):
        app.processEvents()


def _curve(name: str, filename: str):
    import numpy as np

    from chisurf.core.data import DataCurve

    raw = np.loadtxt(IBH / filename, skiprows=9)
    x = np.arange(len(raw), dtype=float) * 0.0141
    curve = DataCurve(x=x, y=raw[:, 1], ey=np.sqrt(np.maximum(raw[:, 1], 1)))
    curve.name = name
    return curve


def _ibh_fit(name: str = "Decay_577D", filename: str = "Decay_577D.txt", fitted: bool = True,
             model_class=None, configure=None):
    """A lifetime fit of an IBH sample decay with its measured prompt as IRF."""
    import chisurf as cs
    from chisurf.core.data import DataCurveGroup
    from chisurf.core.experiments.tcspc.reader import TCSPCReader
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime

    data = _curve(name, filename)
    data.experiment = cs.experiment["TCSPC"]
    data.data_reader = TCSPCReader(record_provenance=False)
    fit = FitGroup(data=DataCurveGroup([data], name=name), model_class=model_class or tcspc_lifetime)
    fit.fit_range = (522, 3793)
    fit.model.set_dataset("response", _curve("Prompt", "Prompt.txt"))
    if configure is not None:
        configure(fit.model)
    fit.update()
    if fitted:
        fit.run()
    return fit


class Session:
    """A real Main, offscreen, with the windows a figure needs."""

    def __init__(self, case_dir) -> None:
        from qtpy import QtWidgets

        self.app, self.main, _ = _open_main(pathlib.Path(case_dir))
        self.main.resize(1500, 950)
        self.QtWidgets = QtWidgets

    def close_all(self) -> None:
        """Close every fit window and drop the session's fits (a figure starts empty)."""
        import chisurf as cs

        for window in self.main.mdiarea.subWindowList():
            window.close_confirm = False
            window.close()
        del cs.fits[:]
        _pump(self.app)

    def load_project(self, case_dir) -> None:
        """Load the produced science of a catalogue case into this Main."""
        from chisurf.core.api import ChiSurfAPI

        ChiSurfAPI(mode="local").load_project(str(pathlib.Path(case_dir) / "science-0.cs.pto"))
        _pump(self.app, 10)

    def open_fit(self, fit):
        """Open *fit* in a fit window and make it the current one."""
        import chisurf as cs
        from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

        cs.fits.append(fit)
        self.main._open_fit_subwindow(fit)
        _pump(self.app)
        sub = next(w for w in self.main.mdiarea.subWindowList()
                   if isinstance(w, FitSubWindow) and w.fit is fit)
        self.main.mdiarea.setActiveSubWindow(sub)
        sub.showMaximized()
        _pump(self.app)
        return sub

    def load_curve(self, fit, kind: str, filename: str) -> None:
        """Load an IBH file as the fit's background or linearisation table, as the editor does."""
        import chisurf as cs
        from chisurf.macros import model as model_macros

        curve = _curve(pathlib.Path(filename).stem, filename)
        cs.imported_datasets.append(curve)
        idx = len(cs.imported_datasets) - 1
        if kind == "background":
            model_macros.set_background_curve(idx, curve.name, fit=fit)
        else:
            model_macros.set_linearization(idx, curve.name, fit=fit)
        _pump(self.app, 10)

    def show_page(self, sub, title: str):
        """Make the fit window's page *title* current and draw it."""
        area = sub.plot_tab_widget
        index = next(i for i in range(area.count()) if area.tabText(i) == title)
        area.setCurrentIndex(index)
        sub.ensure_plot_created(index)
        sub.on_change_plot()
        sub.refresh_current_plot()
        self.settle(sub)
        return sub._plots_all[index]

    def current_window(self):
        from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

        return next(w for w in self.main.mdiarea.subWindowList() if isinstance(w, FitSubWindow))

    def dock(self, name: str):
        dock = self.main.findChild(self.QtWidgets.QDockWidget, name)
        dock.show()
        dock.raise_()
        _pump(self.app)
        return dock

    def box(self, title: str, expanded: bool = True):
        """The analysis dock's collapsible box titled *title*."""
        from chisurf.gui.widgets.collapsible_box import CollapsibleBox

        dock = self.dock("dockWidgetAnalysis")
        # The closed windows' editors linger hidden until deleted: the visible one.
        box = next(b for b in dock.findChildren(CollapsibleBox)
                   if b.title() == title and b.isVisibleTo(dock))
        box.auto_fold = False
        box.set_expanded(expanded)
        _pump(self.app, 20)
        return box

    def settle(self, sub=None) -> None:
        sub = sub or self.current_window()
        for _ in range(8):
            _frames(self.app, sub.plot_tab_widget, 1)
            settings = sub.plot_settings
            if settings is not None:
                settings.host.repaint()

    def save(self, image, name: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        image.save(str(OUT / name))
        print("wrote", name, flush=True)


def _side_by_side(images, labels=None, gap: int = 16, background="#ffffff"):
    """Compose QImages left to right (top-aligned), each with an optional bold label."""
    from qtpy import QtCore, QtGui

    images = [i.toImage() if hasattr(i, "toImage") else i for i in images]
    label_h = 26 if labels else 0
    width = sum(i.width() for i in images) + gap * (len(images) - 1)
    height = max(i.height() for i in images) + label_h
    out = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    out.fill(QtGui.QColor(background))
    painter = QtGui.QPainter(out)
    font = painter.font()
    font.setPointSize(15)
    font.setBold(True)
    painter.setFont(font)
    x = 0
    for index, image in enumerate(images):
        if labels:
            painter.drawText(QtCore.QRect(x + 4, 0, 200, label_h), QtCore.Qt.AlignLeft, labels[index])
        painter.drawImage(x, label_h, image)
        x += image.width() + gap
    painter.end()
    return out


def _crop(widget_image, rect):
    image = widget_image.toImage() if hasattr(widget_image, "toImage") else widget_image
    return image.copy(*rect)


# -- shots ----------------------------------------------------------------------


def shot_convolution(s: Session) -> None:
    """Fig.20: the Convolution box of a lifetime fit with the prompt loaded as IRF."""
    s.close_all()
    s.open_fit(_ibh_fit())
    s.save(s.box("Convolution").grab(), "manual_convolution.png")


def shot_generic(s: Session) -> None:
    """Fig.21: the Generic box with a background pattern loaded."""
    s.close_all()
    fit = _ibh_fit()
    s.open_fit(fit)
    s.load_curve(fit, "background", "Prompt.txt")
    s.box("Convolution", expanded=False)
    s.save(s.box("Generic").grab(), "manual_generic.png")


def shot_corrections(s: Session) -> None:
    """Fig.22: the Corrections box with the white-light linearisation table loaded."""
    s.close_all()
    fit = _ibh_fit()
    s.open_fit(fit)
    s.load_curve(fit, "linearization", "whitelight.txt")
    s.box("Convolution", expanded=False)
    s.box("Generic", expanded=False)
    s.save(s.box("Corrections").grab(), "manual_corrections.png")


def shot_fit_controller(s: Session) -> None:
    """Fig.11: the Fit box (dataset, scoring range, Fit / MCTS / Sample)."""
    s.close_all()
    s.open_fit(_ibh_fit())
    s.save(s.box("Fit").grab(), "manual_fit_controller.png")


def shot_parameter_table(s: Session) -> None:
    """Fig.10: a parameter table and the detail popup a click on a name opens (``ts``, the time shift)."""
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

    s.close_all()
    s.open_fit(_ibh_fit())
    box = s.box("Convolution")
    table = next(t for t in box.findChildren(ParameterGroupTableWidget) if t.isVisibleTo(box))
    row = next(r for r in range(table._model.rowCount())
               if getattr(table._model.param_at(r), "name", "") == "timeshift")
    table._open_details_popup(row)
    _pump(s.app, 20)
    popup = table._detail_popup
    s.save(_side_by_side([box.grab(), popup.grab()], ["a", "b"]), "manual_parameter_table.png")
    popup.close()


def shot_scoring_range(s: Session) -> None:
    """Fig.12: the scoring range in the Fit box and on the Fit plot."""
    s.close_all()
    sub = s.open_fit(_ibh_fit())
    s.dock("dockWidgetAnalysis")
    s.box("Convolution", expanded=False)
    s.box("Generic", expanded=False)
    s.show_page(sub, "Fit")
    s.save(s.main.grab(), "manual_scoring_range.png")


def _fit_window_image(s: Session, sub):
    """The fit window and the analysis dock's Fit and Lifetimes boxes, side by side."""
    s.show_page(sub, "Fit")
    lifetimes = s.box("Lifetimes").grab().toImage()
    controller = s.box("Fit").grab().toImage()
    left = _side_by_side([controller], None)
    from qtpy import QtGui

    stack = QtGui.QImage(max(controller.width(), lifetimes.width()),
                         controller.height() + lifetimes.height() + 8, QtGui.QImage.Format_RGB32)
    stack.fill(QtGui.QColor("#ffffff"))
    painter = QtGui.QPainter(stack)
    painter.drawImage(0, 0, left)
    painter.drawImage(0, controller.height() + 8, lifetimes)
    painter.end()
    window = sub.plot_tab_widget.host.grab().toImage().scaledToWidth(760)
    return _side_by_side([stack, window])


def shot_fit_before_after(s: Session) -> None:
    """Fig.13: the same fit before (a) and after (b) pressing Fit."""
    s.close_all()
    fit = _ibh_fit(fitted=False)
    sub = s.open_fit(fit)
    for title in ("Convolution", "Generic"):
        s.box(title, expanded=False)
    before = _fit_window_image(s, sub)
    fit.run()
    sub.refresh_current_plot()
    s.box("Lifetimes")
    _pump(s.app, 10)
    after = _fit_window_image(s, sub)
    s.save(_side_by_side([before, after], ["a  before Fit", "b  after Fit"], gap=30),
           "manual_fit_before_after.png")


def shot_sampling(s: Session) -> None:
    """Fig.15: a sampled fit -- Sample in the Fit box, the chain on Chain diagnostics."""
    from chisurf.core.fitting.fit import sample_fit

    s.close_all()
    fit = _ibh_fit()
    sub = s.open_fit(fit)
    sample_fit(fit=fit, target_directory=tempfile.mkdtemp(prefix="manual-sampling-"),
               method="blocked", steps=2000, thin=1, n_runs=4)
    for title in ("Convolution", "Generic"):
        s.box(title, expanded=False)
    s.box("Fit")
    s.show_page(sub, "Chain diagnostics")
    s.save(s.main.grab(), "manual_sampling.png")


def _two_lifetimes(model) -> None:
    """Pick the shipped *2-Lifetimes* equation, starting near the IBH donor decay."""
    model.model_name = "2-Lifetimes"
    for name, value in (("a1", 0.5), ("tau1", 4.0), ("a2", 0.5), ("tau2", 1.0)):
        for p in model.parameters_all:
            if p.name == name:
                p.value = value


def shot_equation_parsing(s: Session) -> None:
    """Fig.23: a parsed decay model (2-Lifetimes) fitted to the IBH donor decay."""
    from chisurf.core.models.tcspc.parse.tcspc_parse import ParseDecayModel

    s.close_all()
    sub = s.open_fit(_ibh_fit(model_class=ParseDecayModel, configure=_two_lifetimes))
    s.show_page(sub, "Fit")
    for title in ("Convolution", "Generic", "Corrections"):
        try:
            s.box(title, expanded=False)
        except StopIteration:
            pass
    s.box("Equation")
    s.save(s.main.grab(), "manual_equation_parsing.png")


def shot_donor_reference(s: Session) -> None:
    """Fig.24: a FRET fit of the donor-acceptor sample, raw (a) and relative to its donor reference (b)."""
    from chisurf.core.models.description import tcspc_fret_gaussian

    s.close_all()
    sub = s.open_fit(_ibh_fit("Decay_577D+577A+GTPgS", "Decay_577D+577A+GTPgS.txt",
                              model_class=tcspc_fret_gaussian))
    page = s.show_page(sub, "Fit")
    dock = s.dock("dockWidgetPlot")
    raw = sub.plot_tab_widget.host.grab().toImage().scaledToWidth(820)
    page.settings.reference_mode = "tcspc_donor_reference"
    page.settings.log_y = False  # a ratio reads on a linear axis
    page.settings.curve_visibility["IRF"] = False  # not transformed: raw counts would fill the axis
    page.update()
    s.settle(sub)
    settings = sub.plot_settings.grab().toImage()
    settings = settings.copy(0, 0, settings.width(), min(settings.height(), 330))
    reference = sub.plot_tab_widget.host.grab().toImage().scaledToWidth(820)
    del dock
    s.save(_side_by_side([raw, settings, reference], ["a  Raw", "b  Plot settings", "c  Donor reference"],
                         gap=18), "manual_donor_reference.png")


def shot_calculators(s: Session) -> None:
    """Fig.25: the Calculators hub on F-test / chi2-max (a) and FRET / homoFRET (b)."""
    from emtk.qt_host import ControlHost

    from chisurf.plugins.calculator.hub.gui.app import make_app

    images = []
    for entry in ("f_test", "fret_calculator"):
        hub = make_app()
        hub.select(entry)
        host = ControlHost(hub)
        host.resize(1000, 640)
        host.show()
        for _ in range(8):
            s.app.processEvents()
            host.repaint()
        images.append(host.grab())
        host.close()
    s.save(_side_by_side(images, ["a", "b"], gap=20), "manual_calculators.png")


def shot_parameter_link(s: Session) -> None:
    """Fig.36: the lifetime of a second fit linked to the first: its popup, and Global View."""
    from chisurf.gui.autoform.sections.parameter_table import PairedParameterTableWidget

    s.close_all()
    first = _ibh_fit("Decay_577D", "Decay_577D.txt")
    s.open_fit(first)
    second = _ibh_fit("Decay_577D+577A+GTPgS", "Decay_577D+577A+GTPgS.txt", fitted=False)
    sub = s.open_fit(second)
    for title in ("Convolution", "Generic"):
        s.box(title, expanded=False)
    box = s.box("Lifetimes")
    table = next(t for t in box.findChildren(PairedParameterTableWidget) if t.isVisibleTo(box))
    target = table._model.parameters[1]  # the first lifetime, tau_L1
    source = next(p for p in first.model.parameters_all if p.name == target.name)
    target.link = source
    second.update()
    table._refresh_all()
    _pump(s.app, 10)
    table._open_details_popup(target)
    _pump(s.app, 20)
    popup = table._detail_popup
    s.show_page(sub, "Fit")
    s.save(_side_by_side([box.grab(), popup.grab()], ["a", "b"]), "manual_parameter_link.png")
    popup.close()
    # The same two fits in Global View (Tools > Views > Global View): the link
    # is the arrow from the follower to the parameter it follows.
    from emtk.qt_host import ControlHost

    from chisurf.plugins.core.globalview.gui.app import make_app

    app = make_app(remember_layout=False)
    host = ControlHost(app)
    host.resize(1200, 760)
    host.show()
    for _ in range(12):
        s.app.processEvents()
        host.repaint()
    model = app.model
    follower = next(r for r in model.parameter_records() if r.get("follower"))
    model.select_parameter(follower)
    for _ in range(8):
        s.app.processEvents()
        host.repaint()
    s.save(host.grab(), "manual_global_view.png")
    host.close()


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
}


def main(case0: str, case2: str, case9: str, names) -> None:
    """Take the shots named in *names* (all when empty)."""
    s = Session(case0)
    s.case2, s.case9 = case2, case9
    for name in names or list(SHOTS):
        SHOTS[name](s)
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
