"""The ebFRET main window, drawn with emtk.

A plain port of ``ebfret.ui.MainWindow``: the same panels in the same places,
the same controls under the same names, the same menus and the same dialogs.
The layout is the MATLAB constructor's normalized geometry -- the *Time Series*
panel over the top 60 % of the window, the *Select Series* and *Crop* row under
it, the *Ensemble* panel with its four plots, and the *Select States*,
*States* and *Analysis* row along the bottom.

What differs is where the work happens. MATLAB's window *is* the data and runs
the analysis on its own thread between ``drawnow`` calls; here the window holds
only what it last drew. Every action goes to the backend through
:class:`~chisurf.plugins.burst.burst_ebfret.api.client.EbfretClient`, the
analysis runs there, and the window polls for a new revision to redraw.

Structure, as in the other emtk applications: :class:`EbfretGui` holds the
state and draws the panel bodies (``draw_*``); :class:`App` is the host
adapter -- layout, the menu bar, the modal dialog and pointer/key routing --
and is what a ``ControlHost`` or a ``PixelPainter`` drives.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

import emtk
from emtk import im, implot, keys
from emtk.view_form import FormState, draw_sections, find_section
from emtk.widgets.menus import Menu, MenuBar, MenuItem, Popup
from emtk.widgets.view_spec import load_view_spec

from ..core.session import FILE_TYPES, SESSION, SMD_JSON, SMD_JSON_GZ, SMD_MAT
from . import dialogs as dlg
from .controls import MainControls

SPECS = dlg.SPECS

__all__ = ["EbfretGui", "App", "MENU_H", "GEOMETRY"]

MENU_H = 22.0
#: Button / control-row height of the MATLAB layout (``bh = 40`` there, raised
#: to fit a titled frame around an emtk field row).
ROW_H = 50.0
PAD = 4.0

PANEL_EDGE = (92, 98, 110, 255)
PANEL_TITLE = (200, 205, 215, 255)
WINDOW_BG = (30, 32, 38, 255)
DIM = (150, 155, 165, 255)
RED = (255, 110, 110, 255)

#: Panel geometry as ``MainWindow.m`` writes it: ``(x, y_bottom, w, h)`` in
#: normalized window units, with ``hp``/``vp``/``bh`` resolved at draw time.
GEOMETRY = {
    "Time Series": lambda hp, vp, bh: (hp, 0.40 + 2 * vp + bh, 1 - 2 * hp, 0.60 - 3 * vp - bh),
    "Select Series": lambda hp, vp, bh: (hp, 0.40 + vp, 0.7 - hp, bh),
    "Crop": lambda hp, vp, bh: (0.7 + hp, 0.40 + vp, 0.3 - 2 * hp, bh),
    "Ensemble": lambda hp, vp, bh: (hp, 2 * vp + bh, 1 - 2 * hp, 0.40 - 2 * vp - bh),
    "Select States": lambda hp, vp, bh: (hp, vp, 0.3 - hp, bh),
    "States": lambda hp, vp, bh: (0.3 + hp, vp, 0.15 - hp, bh),
    "Analysis": lambda hp, vp, bh: (0.45 + hp, vp, 0.55 - 2 * hp, bh),
}

#: ``MainWindow.m``'s axis labels and titles.
SERIES_AXES = (
    ("signal", "", "Time [Δ t]", "Signal [Efret]"),
    ("raw", "", "Time [Δ t]", "Donor / Acceptor"),
)
ENSEMBLE_AXES = (
    ("obs", "Histograms", "Signal [Efret]", "Probability"),
    ("mean", "Centers", "μ [Efret]", ""),
    ("noise", "Noise", "σ [Efret]", ""),
    ("dwell", "Dwell Time", "τ  [Δ t]", ""),
)


def _rgb255(colour: Sequence[float] | None) -> tuple | None:
    """A MATLAB ``[r g b]`` in 0..1 as bytes."""
    if colour is None:
        return None
    return tuple(int(round(float(c) * 255)) for c in list(colour)[:3]) + (255,)


class EbfretGui:
    """The window's state and its panel bodies.

    Parameters
    ----------
    client : EbfretClient
        The backend session this window shows.
    directory : str, optional
        Where the file dialogs start.
    poll_interval : float
        Seconds between status polls while nothing is happening.

    Attributes
    ----------
    view : dict
        The last view the backend returned (see ``core.views``).
    dialogs : list of Dialog
        Open modal dialogs; the last one is on top and receives the pointer.
    item_rects : dict
        Screen rectangle of each named control as last drawn, for the guided
        tour's spotlight.
    used : list of str
        Controls the user has used, in order -- what a waiting tour step
        listens for.
    """

    def __init__(
        self, client: Any, directory: str | None = None, poll_interval: float = 0.1
    ) -> None:
        self.client = client
        self.directory = directory or dlg.default_directory()
        self.poll_interval = float(poll_interval)
        self.view: dict = {}
        self.status: dict = {}
        self.revision = -1
        self._last_poll = 0.0
        self.dialogs: list[dlg.Dialog] = []
        self.item_rects: dict[str, tuple] = {}
        self.used: list[str] = []
        self.on_used: Callable[[str], None] | None = None
        self.error = ""
        self.spec = load_view_spec(SPECS / "main.view.json")
        self.form_state = FormState(on_used=self.track)
        self.controls_model = MainControls(self)
        self.shown_tables: set[str] = set()
        self.refresh(force=True)

    # -- backend ---------------------------------------------------------- #
    def refresh(self, force: bool = False) -> None:
        """Poll the backend; fetch a new view when the revision moved.

        Parameters
        ----------
        force : bool
            Poll now regardless of the interval.
        """
        now = time.monotonic()
        if not force and now - self._last_poll < self.poll_interval:
            return
        self._last_poll = now
        try:
            self.status = self.client.status()
            if force or self.status.get("revision") != self.revision:
                view = self.client.view(timeout=0.05 if self.status.get("running") else 1.0)
                if not view.get("busy"):
                    self.view = view
                    self.revision = view.get("revision", self.status.get("revision"))
        except Exception as exc:  # the window must keep drawing; say what failed
            self.error = f"{type(exc).__name__}: {exc}"
        if self.status.get("error"):
            self.error = self.status["error"].strip().splitlines()[-1]

    def act(self, fn: Callable[[], Any], title: str = "ebFRET") -> Any:
        """Call the backend, show an error dialog when it raises, then refresh.

        Parameters
        ----------
        fn : callable
            The client call.
        title : str
            Error dialog title.

        Returns
        -------
        object
            What the call returned, or ``None`` after an error.
        """
        try:
            result = fn()
        except Exception as exc:
            self.show(dlg.MessageBox(title, str(exc)))
            result = None
        self.refresh(force=True)
        return result

    @property
    def controls(self) -> dict:
        """The control values of the last view."""
        return self.view.get("controls") or self.status.get("controls") or {}

    @property
    def has_data(self) -> bool:
        """Whether any series is loaded."""
        return bool(self.view.get("n_series") or self.status.get("n_series"))

    @property
    def running(self) -> bool:
        """Whether the analysis is running on the backend."""
        return bool(self.status.get("running"))

    # -- small widgets the panels and dialogs share ------------------------ #
    def track(self, name: str) -> None:
        """Record that control *name* was used (the tour waits on these)."""
        self.used.append(name)
        if self.on_used is not None:
            self.on_used(name)

    def remember(self, name: str, rect: tuple | None = None) -> None:
        """Store the last item's rectangle (or *rect*) under *name*."""
        rect = rect if rect is not None else im.get_item_rect()
        if rect is not None:
            self.item_rects[name] = tuple(rect)

    def show(self, dialog: dlg.Dialog) -> None:
        """Open a modal dialog on top."""
        self.dialogs.append(dialog)

    def draw_panel(self, title: str) -> None:
        """Draw a control panel from ``main.view.json`` by its MATLAB title."""
        section = find_section(self.spec, title)
        if section is not None:
            draw_sections(
                section.get("sections") or [],
                self.controls_model,
                self.form_state,
                int(section.get("n_col") or 1),
                titles=False,
            )

    def _plot(
        self,
        name: str,
        title: str,
        xlabel: str,
        ylabel: str,
        size: tuple,
        hide_y_ticks: bool = False,
    ) -> None:
        """One axes of a ``PlotPanel``: the view's lines, limits and scale."""
        origin = im.get_cursor_screen_pos()
        spec = (self.view.get("plots") or {}).get(name) or {}
        implot.begin_plot(f"{title}##{name}", size, implot.FLAGS_NO_LEGEND)
        implot.setup_axes(
            xlabel, ylabel, 0, implot.AXIS_FLAGS_NO_TICK_LABELS if hide_y_ticks else 0
        )
        if spec.get("xscale") == "log":
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        xlim, ylim = spec.get("xlim"), spec.get("ylim")
        if xlim and all(v is not None for v in xlim):
            implot.setup_axis_limits(implot.AXIS_X1, float(xlim[0]), float(xlim[1]))
        if ylim and all(v is not None for v in ylim):
            implot.setup_axis_limits(implot.AXIS_Y1, float(ylim[0]), float(ylim[1]))
        for index, line in enumerate(spec.get("lines") or []):
            colour = _rgb255(line.get("color")) or (200, 200, 200, 255)
            label = f"##{name}{index}"
            xs, ys = line.get("x") or [], line.get("y") or []
            if not xs:
                continue
            if line.get("marker") and line.get("linestyle") in ("none", "", None):
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 2.5, colour)
                implot.plot_scatter(label, xs, ys)
                continue
            dash = (6.0, 4.0) if line.get("linestyle") == "--" else None
            implot.set_next_line_style(colour, float(line.get("width", 1.2)), dash=dash)
            implot.plot_line(label, xs, ys)
        implot.end_plot()
        self.remember(f"plot.{name}", (origin[0], origin[1], size[0], size[1]))

    def draw_time_series(self, w: float, h: float) -> None:
        """The *Time Series* panel: signal over donor/acceptor."""
        plot_h = (h - 8.0) / 2.0
        for name, title, xlabel, ylabel in SERIES_AXES:
            self._plot(name, title, xlabel, ylabel, (w, plot_h))

    def draw_ensemble(self, w: float, h: float) -> None:
        """The *Ensemble* panel: histograms, centers, noise and dwell time."""
        plot_w = (w - 3 * 8.0) / 4.0
        for index, (name, title, xlabel, ylabel) in enumerate(ENSEMBLE_AXES):
            if index:
                im.same_line()
            self._plot(name, title, xlabel, ylabel, (plot_w, h), hide_y_ticks=True)

    def draw_select_series(self, w: float, h: float) -> None:
        """*Select Series* (declared in ``main.view.json``)."""
        self.draw_panel("Select Series")

    def draw_crop(self, w: float, h: float) -> None:
        """*Crop* (declared in ``main.view.json``)."""
        self.draw_panel("Crop")

    def draw_select_states(self, w: float, h: float) -> None:
        """*Select States* (declared in ``main.view.json``)."""
        self.draw_panel("Select States")

    def draw_states(self, w: float, h: float) -> None:
        """*States* (declared in ``main.view.json``)."""
        self.draw_panel("States")

    def draw_analysis(self, w: float, h: float) -> None:
        """*Analysis* (declared in ``main.view.json``)."""
        self.draw_panel("Analysis")

    def draw_table_panel(self, title: str) -> None:
        """A declared table panel (*Series List* or *States Table*).

        ChiSurf additions -- ebFRET's window has no tables -- opened from the
        View menu over the right of the panel they belong to.
        """
        im.text(title)
        self.draw_panel(title)

    # -- actions (the menus and buttons) ----------------------------------- #
    def run(self) -> None:
        """``analysisRunStopButtonCallBack``: Run."""
        self.act(self.client.run)

    def stop(self) -> None:
        """``analysisRunStopButtonCallBack``: Stop."""
        self.act(self.client.stop)

    def reset(self) -> None:
        """``analysisResetButtonCallBack``."""
        self.act(self.client.reset)

    def load_data(self) -> None:
        """*File > Load* (``load_data.m``)."""
        self.show(
            dlg.FileChooser(
                "Load", "open", FILE_TYPES, self._loaded, multiselect=True, directory=self.directory
            )
        )

    def _loaded(self, files: list[str], ftype: int) -> None:
        import os

        self.directory = os.path.dirname(files[0]) or self.directory
        if ftype == SESSION:
            if len(files) > 1:
                self.show(
                    dlg.MessageBox(
                        "Warning",
                        "You cannot load more than one ebfret session at a time. "
                        "The first selected file will be loaded.",
                    )
                )
            self.act(lambda: self.client.load(files[:1], ftype))
            return
        if self.has_data:
            self.show(
                dlg.Question(
                    "Append Data?",
                    "Would you like to keep already loaded time series, or replace them?\n\n"
                    " Warinng: Previous analysis will be lost.",
                    ["Keep", "Replace", "Cancel"],
                    lambda answer: (
                        None
                        if answer == "Cancel"
                        else self._load_files(files, ftype, answer == "Keep")
                    ),
                )
            )
        else:
            self._load_files(files, ftype, False)

    def _load_files(self, files: list[str], ftype: int, append: bool) -> None:
        if ftype not in (SMD_MAT, SMD_JSON, SMD_JSON_GZ):
            self._finish_load(files, ftype, append, None)
            return
        columns = self.act(lambda: self.client.smd_columns(files)) or []
        channels: list = []

        def ask(index: int) -> None:
            if index >= len(files):
                self._finish_load(files, ftype, append, channels)
                return

            def got(value: dict | None) -> None:
                channels.append(value)
                ask(index + 1)

            self.show(
                dlg.assign_smd_channels_dialog(
                    columns[index] if index < len(columns) else [], got, lambda: got(None)
                )
            )

        ask(0)

    def _finish_load(
        self, files: list[str], ftype: int, append: bool, channels: list | None
    ) -> None:
        result = self.act(lambda: self.client.load(files, ftype, append, channels))
        if result and result.get("message"):
            self.used.append("loaded")

    def load_demo(self) -> None:
        """Write the simulated demo dataset and load it (the tour's first step)."""
        from .. import demo

        path = demo.write_demo()
        self._loaded([str(path)], 2)

    def save_data(self) -> None:
        """*File > Save* (``save_data.m``)."""
        self.show(
            dlg.FileChooser(
                "Save",
                "save",
                [("ebFRET saved session (.mat)", ["*.mat"])],
                lambda paths, _i: self.act(lambda: self.client.save(paths[0])),
                directory=self.directory,
            )
        )

    def export_summary(self) -> None:
        """*File > Export > Analysis Summary* (``export_summary.m``)."""
        self.show(
            dlg.FileChooser(
                "Export Analysis Summary",
                "save",
                [("ebFRET analysis summary (.csv)", ["*.csv"])],
                lambda paths, _i: self.act(lambda: self.client.export_summary(paths[0])),
                directory=self.directory,
            )
        )

    def export_traces(self) -> None:
        """*File > Export > Traces* (``export_traces.m``)."""

        def chosen(paths: list[str], index: int) -> None:
            fmt = "dat" if index == 1 else "mat"
            self.show(
                dlg.SelectChannelsDialog(
                    lambda channels: (
                        self._select_analysis(
                            lambda k, g: self.act(
                                lambda: self.client.export_traces(paths[0], channels, k, g, fmt)
                            )
                        )
                        if any(channels.values())
                        else None
                    )
                )
            )

        self.show(
            dlg.FileChooser(
                "Export Traces",
                "save",
                [
                    ("ebFRET time series (.dat)", ["*.dat"]),
                    ("ebFRET time series (.mat)", ["*.mat"]),
                ],
                chosen,
                directory=self.directory,
            )
        )

    def export_smd(self) -> None:
        """*File > Export > Single-molecule Dataset (SMD)* (``export_smd.m``)."""

        def chosen(paths: list[str], index: int) -> None:
            fmt = {1: "mat", 2: "json", 3: "gz"}[index]
            self._select_analysis(
                lambda k, g: self.act(lambda: self.client.export_smd(paths[0], k, g, fmt))
            )

        self.show(
            dlg.FileChooser(
                "Export SMD",
                "save",
                [
                    ("ebFRET SMD export (.mat)", ["*.mat"]),
                    ("ebFRET SMD export (.json)", ["*.json"]),
                    ("ebFRET SMD export (.json.gz)", ["*.json.gz"]),
                ],
                chosen,
                directory=self.directory,
            )
        )

    def _select_analysis(self, on_ok: Callable[[int, str], None]) -> None:
        c = self.controls
        states = list(range(int(c.get("min_states", 2)), int(c.get("max_states", 6)) + 1))
        self.show(dlg.select_analysis_dialog(states, self.status.get("groups") or [], on_ok))

    def remove_bleaching(self) -> None:
        """*Analysis > Remove Photo-bleaching* (``remove_bleaching.m``)."""
        if not self.has_data:
            return

        def ok(method: int, params: dict) -> None:
            message = self.act(lambda: self.client.remove_bleaching(method, params))
            if message:
                self.show(dlg.MessageBox("Remove Photo-bleaching", message))
            self.update_priors()

        self.show(dlg.remove_bleaching_dialog(ok))

    def clip_outliers(self) -> None:
        """*Analysis > Clip Outliers* (``clip_outliers.m``)."""

        def ok(x_lim: tuple, max_outliers: int) -> None:
            message = self.act(lambda: self.client.clip_outliers(x_lim, max_outliers))
            if message:
                self.show(dlg.MessageBox("Clip Outliers", message))
            self.update_priors()

        self.show(dlg.clip_outliers_dialog(ok))

    def update_priors(self) -> None:
        """``update_priors.m``'s question."""

        def answer(choice: str) -> None:
            if choice == "Manual":
                self.init_priors()
            else:
                self.act(lambda: self.client.update_priors(choice))

        self.show(
            dlg.Question(
                "Update Priors",
                "Update prior distributions ?",
                ["Auto", "Manual", "Keep Current"],
                answer,
            )
        )

    def init_priors(self) -> None:
        """*Analysis > Set Priors* (``init_priors.m``)."""
        self.show(
            dlg.set_priors_dialog(
                lambda theta, counts, status: self.act(
                    lambda: self.client.init_priors(theta, counts, status)
                )
            )
        )

    def toggle(self, name: str) -> None:
        """A View menu checkmark."""
        self.act(lambda: self.client.set(name, not bool(self.controls.get(name, True))))


class App:
    """Host adapter: the layout, the menu bar, dialogs and input routing.

    Parameters
    ----------
    gui : EbfretGui
        The window state.
    on_exit : callable, optional
        *File > Exit*.
    """

    def __init__(self, gui: EbfretGui, on_exit: Callable[[], None] | None = None) -> None:
        self.gui = gui
        self.on_exit = on_exit
        self.io, self.storage = emtk.IO(), {}
        #: The dialog is its own frame, drawn after the panels have flushed, so
        #: the dimming lies over them rather than under them -- and its own IO,
        #: so while it is open the panels receive no pointer at all.
        self.dialog_io, self.dialog_storage = emtk.IO(), {}
        #: The table overlays are drawn after the panels, in their own frame; they
        #: share the panels' input, delivered to them when the pointer is over one.
        self.table_io, self.table_storage = emtk.IO(), {}
        self.table_boxes: list[tuple] = []
        self._pressed_io: Any = None
        self._focus_io: Any = None
        self.items = {
            "load": MenuItem("Load"),
            "save": MenuItem("Save"),
            "export_summary": MenuItem("Analysis Summary"),
            "export_traces": MenuItem("Traces"),
            "export_smd": MenuItem("Single-molecule Dataset (SMD)"),
            "exit": MenuItem("Exit"),
            "remove_bleaching": MenuItem("Remove Photo-bleaching"),
            "clip_outliers": MenuItem("Clip Outliers"),
            "init_priors": MenuItem("Set Priors"),
            "show_viterbi": MenuItem("Viterbi Paths", checked=True),
            "show_prior": MenuItem("Prior", checked=True),
            "show_posterior": MenuItem("Posterior", checked=True),
            "scale_plots": MenuItem("Normalize by Occupancy", checked=True),
            "table_series": MenuItem("Series List", checkable=True),
            "table_states": MenuItem("States Table", checkable=True),
        }
        it = self.items
        self.export_menu = Menu(
            "Export", [it["export_summary"], it["export_traces"], it["export_smd"]]
        )
        self.menus = {
            "File": Menu("File", [it["load"], it["save"], self.export_menu, it["exit"]]),
            "Analysis": Menu(
                "Analysis", [it["remove_bleaching"], it["clip_outliers"], it["init_priors"]]
            ),
            "View": Menu(
                "View",
                [
                    it["show_viterbi"],
                    it["show_prior"],
                    it["show_posterior"],
                    it["scale_plots"],
                    None,
                    it["table_series"],
                    it["table_states"],
                ],
            ),
        }
        self.menubar = MenuBar(list(self.menus.values()))
        self.box = (0.0, 0.0, 0.0, 0.0)
        self.panels: dict[str, tuple] = {}
        self.popup: tuple | None = None

    # -- commands ---------------------------------------------------------- #
    def command(self, name: str) -> None:
        """Run a menu entry by its key."""
        g = self.gui
        self.gui.track(f"menu.{name}")
        if name == "exit":
            if self.on_exit is not None:
                self.on_exit()
        elif name in ("show_viterbi", "show_prior", "show_posterior", "scale_plots"):
            g.toggle(name)
        elif name in ("table_series", "table_states"):
            title = "Series List" if name == "table_series" else "States Table"
            g.shown_tables ^= {title}
        else:
            # the menu keys are the MATLAB handle names; two callbacks are named
            # after their files instead (load_data.m, save_data.m)
            getattr(g, {"load": "load_data", "save": "save_data"}.get(name, name))()

    def modal(self) -> bool:
        """Whether a dialog is open."""
        return bool(self.gui.dialogs)

    def _sync_menus(self) -> None:
        c, data = self.gui.controls, self.gui.has_data
        for name in ("show_viterbi", "show_prior", "show_posterior", "scale_plots"):
            self.items[name].checked = bool(c.get(name, True))
            self.items[name].enabled = data
        self.items["table_series"].checked = "Series List" in self.gui.shown_tables
        self.items["table_states"].checked = "States Table" in self.gui.shown_tables

    # -- layout ------------------------------------------------------------ #
    def layout(self, x: float, y: float, w: float, h: float) -> dict[str, tuple]:
        """Screen boxes of the seven panels, from ``MainWindow.m``'s geometry.

        Returns
        -------
        dict
            Panel title -> ``(x, y, w, h)`` with ``y`` downwards.
        """
        top = y + MENU_H
        body_h = max(h - MENU_H, 200.0)
        hp, vp, bh = PAD / w, PAD / body_h, ROW_H / body_h
        boxes = {}
        for title, geometry in GEOMETRY.items():
            nx, ny, nw, nh = geometry(hp, vp, bh)
            boxes[title] = (x + nx * w, top + (1.0 - ny - nh) * body_h, nw * w, nh * body_h)
        return boxes

    def draw(self, painter: Any, x: float, y: float, w: float, h: float) -> None:
        """Draw the window: panels, dialogs, popups and the menu bar."""
        g = self.gui
        g.refresh()
        self.box = (x, y, w, h)
        self._sync_menus()
        self.menubar.set_viewport(x + w, y + h)
        painter.fill_rect(x, y, w, h, WINDOW_BG)
        self.panels = self.layout(x, y, w, h)
        for title, (px, py, pw, ph) in self.panels.items():
            _panel_frame(painter, px, py, pw, ph, title)

        modal = self.modal()
        with emtk.frame(painter, (x, y, w, h), io=self.io, storage=self.storage):
            bodies = {
                "Time Series": g.draw_time_series,
                "Select Series": g.draw_select_series,
                "Crop": g.draw_crop,
                "Ensemble": g.draw_ensemble,
                "Select States": g.draw_select_states,
                "States": g.draw_states,
                "Analysis": g.draw_analysis,
            }
            for title, body in bodies.items():
                px, py, pw, ph = self.panels[title]
                inner = (px + 6.0, py + 12.0, pw - 12.0, ph - 16.0)
                im.begin(f"##panel-{title}", inner, im.WindowFlags.NO_TITLE_BAR)
                im.begin_disabled(modal)
                body(inner[2] - 8.0, inner[3] - 8.0)
                im.end_disabled()
                im.end()
        g.item_rects.update(g.form_state.rects)
        self.table_boxes = []
        for title, host in (("Series List", "Time Series"), ("States Table", "Ensemble")):
            if title not in g.shown_tables:
                continue
            tx, ty, tw, th = self.panels[host]
            box = (tx + tw * 0.5, ty + 14.0, tw * 0.5 - 8.0, th - 22.0)
            painter.fill_rect(box[0] - 1, box[1] - 1, box[2] + 2, box[3] + 2, PANEL_EDGE)
            painter.fill_rect(box[0], box[1], box[2], box[3], WINDOW_BG)
            self.table_boxes.append(box)
            with emtk.frame(painter, (x, y, w, h), io=self.table_io, storage=self.table_storage):
                im.begin(
                    f"##table-{title}",
                    (box[0] + 6.0, box[1] + 4.0, box[2] - 12.0, box[3] - 8.0),
                    im.WindowFlags.NO_TITLE_BAR,
                )
                im.begin_disabled(modal)
                g.draw_table_panel(title)
                im.end_disabled()
                im.end()
        g.item_rects.update(g.form_state.rects)
        if modal:
            self._draw_dialog(painter, x, y, w, h)
        g.dialogs = [d for d in g.dialogs if not d.done]
        self._open_requested_dropdown()
        if self.popup is not None:
            self.popup[0].draw(painter, x, y, w, h)
        if g.error:
            painter.text(x + w - 520.0, y + 3.0, 510.0, MENU_H - 6.0, 2, g.error[:90], RED)
        self.menubar.draw(painter, x, y, w, MENU_H)
        self._remember_menu_rects()

    def _draw_dialog(self, painter: Any, x: float, y: float, w: float, h: float) -> None:
        dialog = self.gui.dialogs[-1]
        painter.fill_rect(x, y, w, h, (0, 0, 0, 110))
        dw, dh = min(dialog.size[0], w - 20.0), min(dialog.size[1] + 24.0, h - 40.0)
        dx, dy = x + (w - dw) / 2.0, y + max(MENU_H + 10.0, (h - dh) / 2.0)
        painter.fill_rect(dx - 1, dy - 1, dw + 2, dh + 2, (95, 110, 150, 255))
        painter.fill_rect(dx, dy, dw, dh, (40, 43, 52, 255))
        painter.text(dx + 8.0, dy + 3.0, dw - 16.0, 18.0, 0, dialog.title, (150, 180, 255, 255))
        with emtk.frame(painter, (x, y, w, h), io=self.dialog_io, storage=self.dialog_storage):
            im.begin(
                f"##dialog-{id(dialog)}",
                (dx + 6.0, dy + 24.0, dw - 12.0, dh - 28.0),
                im.WindowFlags.NO_TITLE_BAR,
            )
            dialog.draw(self.gui)
            im.end()
        self.gui.item_rects["dialog"] = (dx, dy, dw, dh)

    def _remember_menu_rects(self) -> None:
        for menu, rect in getattr(self.menubar, "_titles", []):
            self.gui.item_rects[f"menu.{menu.label}"] = tuple(rect)

    def _form_states(self) -> list:
        """The form states a choice list may have been requested from."""
        states = [self.gui.form_state]
        states += [d.state for d in self.gui.dialogs if hasattr(d, "state")]
        return states

    def _open_requested_dropdown(self) -> None:
        for state in self._form_states():
            request, state.dropdown_request = state.dropdown_request, None
            if request is None:
                continue
            key, (rx, ry, rw, rh), labels, current = request
            items = [
                MenuItem(text, checked=(index == current)) for index, text in enumerate(labels)
            ]
            popup = Popup(items)
            popup.open_at(rx, ry + rh)
            self.popup = (popup, items, key, state)

    # -- input ------------------------------------------------------------- #
    def active_io(self, px: float | None = None, py: float | None = None) -> Any:
        """The IO that receives input at a point: a dialog's while one is open,
        a table overlay's over one, the panels' otherwise."""
        if self.modal():
            return self.dialog_io
        if px is not None and any(
            bx <= px < bx + bw and by <= py < by + bh for bx, by, bw, bh in self.table_boxes
        ):
            return self.table_io
        return self.io

    def hover(self, px: float, py: float, *_box: Any) -> None:
        """Pointer moved with no button down."""
        target = self.active_io(px, py)
        for io in (self.io, self.dialog_io, self.table_io):
            io.mouse_pos = (px, py) if io is target else (-1.0, -1.0)

    def drag(self, px: float, py: float, *_box: Any) -> None:
        """Pointer moved with the button down."""
        (self._pressed_io or self.active_io(px, py)).mouse_pos = (px, py)

    def press(self, px: float, py: float, *extra: Any, **_kw: Any) -> None:
        """A button went down: popup, then menu bar, then the frame."""
        x, y, w, h = self.box
        clicks = extra[5] if len(extra) > 5 else 1
        if self.popup is not None:
            popup, items, key, state = self.popup
            result = popup.press(px, py, x, y, w, h)
            if result.item is not None:
                state.dropdown_result[key] = items.index(result.item)
            if not popup.open:
                self.popup = None
            return
        result = self.menubar.press(px, py, x, y, w, MENU_H)
        if result.item is not None:
            for name, item in self.items.items():
                if item is result.item:
                    self.command(name)
            return
        if result.consumed or py < y + MENU_H:
            if py < y + MENU_H:
                for menu, rect in getattr(self.menubar, "_titles", []):
                    if rect[0] <= px < rect[0] + rect[2]:
                        self.gui.track(f"menu.{menu.label}")
            return
        io = self._pressed_io = self._focus_io = self.active_io(px, py)
        io.mouse_pos = io.mouse_clicked_pos[0] = (px, py)
        io.mouse_clicked[0] = io.mouse_down[0] = True
        io.mouse_double_clicked[0] = clicks >= 2

    def release(self, *_args: Any, **_kw: Any) -> None:
        """The button came up."""
        self._pressed_io = None
        for io in (self.io, self.dialog_io, self.table_io):
            if io.mouse_down[0]:
                io.mouse_down[0] = False
                io.mouse_released[0] = True

    def scroll(self, rows: int) -> None:
        """Wheel: nothing in this window scrolls."""

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """A key press: Escape closes the top popup/menu/dialog, the rest types."""
        if key == keys.KEY_ESCAPE:
            if self.popup is not None:
                self.popup[0].close()
                self.popup = None
            elif any(m.open for m in self.menubar.menus):
                self.menubar.close()
            elif self.gui.dialogs:
                self.gui.dialogs.pop()
            return True
        io = self.dialog_io if self.modal() else (self._focus_io or self.io)
        io.key = int(key)
        io.text = "".join(c for c in (text or "") if c >= " " and c != "\x7f")
        return True


def _panel_frame(painter: Any, x: float, y: float, w: float, h: float, title: str) -> None:
    """A ``uipanel`` with a title: an etched rectangle broken by its caption."""
    painter.stroke_rect(x, y + 6.0, w, h - 6.0, PANEL_EDGE)
    tw = painter.text_width(title) + 8.0
    painter.fill_rect(x + 8.0, y, tw, 12.0, WINDOW_BG)
    painter.text(x + 12.0, y - 1.0, tw, 14.0, 0, title, PANEL_TITLE)
