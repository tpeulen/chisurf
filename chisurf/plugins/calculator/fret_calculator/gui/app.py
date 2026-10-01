"""Native emtk FRET / HomoFRET calculator (forms from fret.view.json and homofret.view.json).

Two tabs, each a dock layout of its own: the parameter form on the left, the
distance distribution and its derived rate (or anisotropy-time) distribution
on the right. The form is the view spec drawn by ``emtk.view_form.draw_form``;
an edit runs the one model method the spec's ``call`` names, and its results
are the next frame's field values.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import FretCalculatorModel

HERE = Path(__file__).parent

_TAB_BAR_H = 26.0
_NO_FILES = "The FRET Calculator takes no dropped files."


def _rgba(colour) -> tuple:
    """A ``#rrggbb`` series colour as an RGBA tuple."""
    if isinstance(colour, str):
        return tuple(int(colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)) + (255,)
    return colour


def _series_plot(name: str, series: list[dict]) -> None:
    """Draw one declarative series list; the active distribution solid, the other dashed."""
    for s in series:
        xs = np.asarray(s.get("x", []), dtype=float)
        ys = np.asarray(s.get("y", []), dtype=float)
        if not len(xs) or not len(ys):
            continue
        implot.set_next_line_style(
            _rgba(s.get("color", "#888888")),
            float(s.get("width", 1.0)),
            dash=(4.0, 3.0) if s.get("style") == "dash" else None,
        )
        implot.plot_line(s.get("name") or name, xs, ys)


def _split_spec(spec: dict) -> tuple[dict, list[dict]]:
    """The form half of a view spec (everything but ``plot`` sections) and its plots."""
    plots: list[dict] = []
    forms: list[dict] = []
    for section in spec.get("sections", []):
        found = [s for s in section.get("sections", []) if s.get("type") == "plot"]
        if found or section.get("type") == "plot":
            plots.extend(found or [section])
        else:
            forms.append(section)
    return {"sections": forms}, plots


class _Tab:
    """One calculator tab: its model, its form state and its three dock windows."""

    def __init__(self, app: FretCalcApp, model, second: str, title: str) -> None:
        self.app = app
        self.model = model
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.form_spec, self.plots = _split_spec(model.view_spec())
        self.docks = DockManager(
            Split("h", 0.42, Region("params"), Split("v", 0.55, Region("distance"), Region(second)))
        )
        self.second = second
        self.docks.add_window("params", title, self._draw_params, dock="params", closable=False)
        for key, plot in zip(("distance", second), self.plots):
            self.docks.add_window(
                key, plot.get("title", key), self._plot_drawer(key, plot), dock=key, closable=False
            )

    # -- windows --------------------------------------------------------------- #
    def _draw_params(self, box) -> None:
        app = self.app
        if im.button("Guide"):
            app.start_guide()
        im.set_item_tooltip("A step-by-step walk through the calculator.")
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button("Help"):
            app.show_help()
        im.set_item_tooltip("The help page for the FRET calculator.")
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        im.text_wrapped(self.model.status_text())
        self.form.rects.clear()
        draw_form(self.form_spec, self.model, self.form)

    def _plot_drawer(self, key: str, plot: dict):
        def draw(box) -> None:
            if implot.begin_plot(f"##{key}_{self.model.spec_file}", (-1, -1)):
                implot.setup_axes(plot.get("x_label"), plot.get("y_label"))
                implot.setup_legend(implot.LOCATION_NORTH_EAST)
                _series_plot(key, getattr(self.model, plot["source"])())
                implot.end_plot()
                im.set_item_tooltip(plot.get("description", ""))
            self.item_rects[key] = im.get_item_rect()

        return draw

    # -- what the existing tests and the calculators hub call ------------------ #
    def _compute_forward(self) -> None:
        self.model.compute_forward()

    _compute = _compute_forward

    def _compute_from_lifetime(self) -> None:
        self.model.from_lifetime()

    def _compute_from_efficiency(self) -> None:
        self.model.from_efficiency()

    def _compute_from_rate(self) -> None:
        self.model.from_rate()

    def _compute_backmap(self) -> None:
        self.model.backmap()

    def target_rect(self, name: str):
        return self.form.rects.get(name) or self.form.rects.get(name + ".fold") or self.item_rects.get(name)

    def draw(self, x: float, y: float, w: float, h: float) -> None:
        self.docks.draw((x, y, w, h))


class FretCalcApp(ImApp):
    """The calculator: a tab bar over two dock layouts."""

    def __init__(self, model: FretCalculatorModel | None = None) -> None:
        self.model = model or FretCalculatorModel()
        self.hetero = _Tab(self, self.model.hetero, "rate", "FRET parameters")
        self.homo = _Tab(self, self.model.homo, "aniso", "Homo-FRET parameters")
        self.tabs = (self.hetero, self.homo)
        self.item_rects: dict[str, tuple] = {}
        self._pending_tab: int | None = None
        self.help_window = EmTkHelpWindow(
            title="FRET Calculator - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=self.target_rect,
            owner=self,
            wait_for_controls=True,
            on_step_change=self._show_step_tab,
        )
        for tab in self.tabs:
            tab.form.on_used = self.tour.notify_used
        self.native_layouts = {"hetero": self.hetero.docks, "homo": self.homo.docks}
        super().__init__(gui=self._render, continuous=False)

    # -- tabs and tour ------------------------------------------------------------ #
    @property
    def active_tab(self) -> int:
        return self.model.tab

    @property
    def active(self) -> _Tab:
        return self.tabs[self.model.tab]

    def select_tab(self, index: int) -> None:
        """Switch tabs programmatically (the tab bar applies it on the next frame)."""
        self._pending_tab = int(index)
        self.model.tab = int(index)

    def _show_step_tab(self, index: int, step: dict) -> None:
        tab = step.get("tab")
        if tab in self.model.TABS:
            self.select_tab(self.model.TABS.index(tab))

    def target_rect(self, name: str):
        return self.item_rects.get(name) or self.active.target_rect(name)

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    # -- one frame ----------------------------------------------------------------- #
    def _tab_bar(self, width: float) -> None:
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, _TAB_BAR_H), im.Cond.ALWAYS)
        if im.begin(
            "##fret_tabs",
            (0.0, 0.0, width, _TAB_BAR_H),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_SCROLLBAR,
        ):
            if im.begin_tab_bar("fret_calc_tabs"):
                pending, self._pending_tab = self._pending_tab, None
                tips = (
                    "HeteroFRET: a donor-acceptor pair - distance, lifetime, efficiency and rate.",
                    "HomoFRET: energy migration between like dyes - anisotropy decay and the "
                    "implied donor-acceptor distance.",
                )
                for index, (name, tip) in enumerate(zip(self.model.TABS, tips)):
                    flags = im.TabItemFlags.SET_SELECTED if pending == index else 0
                    if im.begin_tab_item(name, flags):
                        if self.model.tab != index:
                            self.model.tab = index
                            self.tour.notify_used("tab_" + name.lower())
                        im.end_tab_item()
                    im.set_item_tooltip(tip)
                    self.item_rects["tab_" + name.lower()] = im.get_item_rect()
                im.end_tab_bar()
        im.end()

    def _render(self) -> None:
        vp = im.get_main_viewport()
        width = float(vp.size[0] or 900.0)
        height = float(vp.size[1] or 620.0)
        self._tab_bar(width)
        self.active.draw(0.0, _TAB_BAR_H, width, height - _TAB_BAR_H)
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)

    # -- file drops: the calculator has no file input (the Qt tool said so in its status bar) -- #
    def files_dropped(self, paths) -> bool:
        paths = [p for p in (paths or ()) if p]
        if paths:
            self.active.model.status = _NO_FILES
        return bool(paths)

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- persistence ------------------------------------------------------------------ #
    def export_settings(self) -> dict:
        """Inputs of both tabs and the selected tab (outputs are recomputed)."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; invalid entries are ignored."""
        self.model.restore_settings(settings)
        for tab in self.tabs:
            tab.form.buffers.clear()
        self._pending_tab = self.model.tab


__all__ = ["FretCalcApp"]


def make_app(**kwargs) -> FretCalcApp:
    """Construct the standalone calculator without any Qt host."""
    from chisurf.emtk.i18n import install

    install()
    return FretCalcApp()
