"""Native multi-state FCS saturation calculator: the controls left, the state diagram and the predictions right."""

from __future__ import annotations

import json
import math
import pathlib
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.im_core import Col
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from chisurf.plugins.emtk_layout import button_row

from .model import SaturationModel
from .panel import POWER_CEILING_MW, TABS, SaturationPanel

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "saturation_emtk.view.json").read_text(encoding="utf-8"))
#: The state palette of the radial profile plot, reused for the diagram's nodes so a state keeps its colour.
STATE_COLOURS = ("#42a5f5", "#66bb6a", "#ab47bc", "#ffa726", "#ef5350", "#26c6da")
DARK_COLOUR = "#ffa726"
EXCITATION_COLOUR = "#ec407a"
#: Height of one table row and the header, for sizing a table to its rows.
ROW_H = 20.0
#: What a table with a selected row's description under it takes below its rows (two lines and their gap).
NOTE_H = 46.0
#: Colours of the selected tab button (button, hovered, active), the tab bar's selected colour.
MIN_CONTROLS = 400.0
SELECTED_TAB = ((66, 133, 220, 255), (82, 148, 235, 255), (66, 133, 220, 255))
#: The plots that follow the Qt dock tabs: tab -> the sections of ``view.json`` it shows (source attribute order).
PLOT_TABS = {
    "FCS curve": ("fcs_curves_series", "fcs_residual_series"),
    "Volume profile": ("volume_profile_series",),
    "Volume(P)": ("volume_power_series",),
    "Diffusion time": ("tau_d_power_series",),
}


def _colour(value) -> tuple:
    """A series colour (a name or ``#rrggbb``) as the 0..1 RGBA the plot takes."""
    from emtk.colormaps import to_rgba

    return tuple(float(c) for c in to_rgba(value))


def _plot_sections() -> dict[str, dict]:
    """The ``plot`` sections of the Qt spec by source attribute (titles, axis labels, log axes, descriptions)."""
    found: dict[str, dict] = {}

    def walk(sections):
        for section in sections:
            if section.get("type") == "plot":
                found[section["source"]] = section
            walk(section.get("sections", []))

    walk(json.loads((HERE / "view.json").read_text(encoding="utf-8"))["sections"])
    return found


PLOTS = _plot_sections()
#: The guide's names for the tables (the form records a table under its source).
TABLE_ALIASES = {"dark_rows": "k_dark", "exc_rows": "k_exc", "brightness_rows": "brightness", "optics_rows": "optics"}
SHORT_TITLES = {"Residual against a single diffusion component": "Residual vs one component"}


class SaturationApp(TourTarget, ImApp):
    """The saturation window: scheme and optics left, the prediction tabs right."""

    def __init__(self, model=None):
        self.model = model or SaturationModel()
        self.panel = SaturationPanel(self)
        self.result_tab = TABS[1]
        self._ratio_set = False
        self.dialog = None
        self.dialog_mode = ""
        self.file_window = None
        self.error = ""
        self.status = ""
        self.item_rects: dict = {}
        self._limits_key: dict = {}
        self.help_window = EmTkHelpWindow(
            title="FCS saturation - Help", resource=HERE / "help.md", owner=self, on_start_guide=lambda: self.tour.start()
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json", get_target_rect=lambda k: self.item_rects.get(k), owner=self, wait_for_controls=True,
            on_step_change=lambda _i, step: step.get("tab") and self.select_tab(step["tab"]),
        )
        names = ("toolbar", "photophysics", "k_dark", "k_exc", "brightness", "optics", "fcs_toggles", "profile_toggles")
        self.forms = {n: FormState(on_used=self.tour.notify_used) for n in names}
        self.docks = DockManager(Split("h", 0.40, Region("controls"), Region("plots")), name="saturation")
        self.docks.add_window("controls", "Photophysics and kinetics", self._draw_controls, dock="controls", closable=False)
        self.docks.add_window("plots", "FCS predictions", self._draw_results, dock="plots", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(self._render, continuous=False)

    def select_tab(self, label: str) -> None:
        """Show the result tab *label* (the guide and tests bring a tab forward this way)."""
        self.result_tab = label

    # -- actions of the toolbar (called by the panel) ------------------------------------------------------- #
    def compute(self) -> None:
        self.error = ""
        self.model._on_compute()
        self.status = "Computed."

    def choose(self, mode: str) -> None:
        self.dialog_mode = mode
        title = "Load scheme" if mode == "open" else "Save scheme"
        self.dialog = FileDialog(title, mode=mode, filename="scheme.json" if mode == "save" else "", filters="JSON (*.json)")
        self.file_window = DialogWindow(title, size=(560, 420), key=title)
        self.file_window.show()

    def load_scheme(self, path) -> None:
        """Load a scheme file, saying so when it cannot be read (the model skips a missing file without a word)."""
        if not pathlib.Path(path).is_file():
            raise FileNotFoundError(f"The scheme file {path} does not exist.")
        self.model.load_scheme_from_file(str(path))
        self.model._scheme_preset = "Custom"
        self.status = f"Loaded {pathlib.Path(path).name}"
        self.error = ""

    def load_session(self) -> None:
        self.model.load_user_settings()
        self.model._invalidate()
        self.model._on_changed()
        self.error = ""
        self.status = "Session restored."

    def save_session(self) -> None:
        self.model.save_user_settings()
        self.error = ""
        self.status = f"Session saved to {self.model.get_user_settings_path()}"

    # -- the left window ------------------------------------------------------------------------------------ #
    def _form(self, name: str) -> None:
        state = self.forms[name]
        state.rects.clear()
        draw_form(SPEC[name], self.panel, state, titles=False)
        self.item_rects.update(state.rects)
        for source, alias in TABLE_ALIASES.items():
            if source in state.rects:
                self.item_rects[alias] = state.rects[source]

    def _fold(self, title: str, tip: str, form: str, rows: int, key: str) -> None:
        """A titled table: the fold header, then the table sized to its rows."""
        opened = im.collapsing_header(title, im.TreeNodeFlags.DEFAULT_OPEN)
        im.set_item_tooltip(tip)
        self.item_rects[key + "_header"] = im.get_item_rect()
        if opened:
            SPEC[form]["sections"][0]["height"] = ROW_H * (rows + 1) + 8.0
            self._form(form)

    def _draw_controls(self, box) -> None:
        self._form("toolbar")
        for name in ("compute", "load_scheme", "save_scheme", "load_session", "save_session", "guide", "help"):
            if name in self.item_rects:
                self.item_rects[name.title().replace("_", " ")] = self.item_rects[name]
        if self.error:
            im.push_style_color(Col.TEXT, (255, 115, 100, 255))
            im.text_wrapped(self.error)
            im.pop_style_color(1)
        elif self.status:
            im.text_wrapped(self.status)
        else:
            im.text_disabled(" ")
        self._form("photophysics")
        sat = self.model.saturation
        n = sat.n_states
        unit = self.model.rate_unit
        self._fold(f"K_dark ({unit}), row to column",
                   "The power-independent transitions between states. Row is the state a transition starts from, column where it ends.",
                   "k_dark", n, "k_dark")
        self._fold("K_exc cross-sections, row to column",
                   "Excitation transitions relative to the peak excitation rate; 1 means a full cross-section.",
                   "k_exc", n, "k_exc")
        self._fold("State brightness Q",
                   "Relative fluorescence emitted by each state; dark states have zero.", "brightness", n, "brightness")
        self.remember("controls", tuple(box))

    # -- the right window ----------------------------------------------------------------------------------- #
    def _draw_results(self, box) -> None:
        buttons = [{"label": label, "key": label, "tip": f"Show {label}.",
                    "colours": SELECTED_TAB if label == self.result_tab else None} for label in TABS]
        picked = button_row(buttons, remember=self.remember)
        if picked:
            self.result_tab = picked
            self.tour.notify_used(picked)
        im.separator()
        tab = self.result_tab
        if tab == "State diagram":
            self._draw_state_tab()
        elif tab == "Info":
            self._draw_info()
        else:
            if tab == "FCS curve":
                self._form("fcs_toggles")
            elif tab == "Volume profile":
                self._form("profile_toggles")
            sources = PLOT_TABS[tab]
            avail = im.get_content_region_avail()[1]
            residual = 190.0 if len(sources) > 1 else 0.0
            for i, source in enumerate(sources):
                height = max(avail - residual - 8.0, 120.0) if i == 0 and len(sources) > 1 else (residual if i else -1)
                self._plot(source, height)
        self.remember("results", tuple(box))

    def _plot(self, source: str, height: float) -> None:
        """One series plot of the Qt spec: its axes, log scales, colours, dashes and markers."""
        section = dict(PLOTS[source])
        full_title = section["title"]
        section["title"] = SHORT_TITLES.get(full_title, full_title)  # a plot title is drawn inside the plot: keep it short
        section.setdefault("description", full_title + ".")
        series = [s for s in getattr(self.model, source) if len(s["x"])]
        title = section["title"]
        flags = 0 if section.get("legend", True) else implot.FLAGS_NO_LEGEND
        self.item_rects[source] = self._plot_box(height)
        if implot.begin_plot(title, (-1, height), flags):
            implot.setup_axes(section.get("x_label", ""), section.get("y_label", ""))
            if section.get("log_x"):
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if section.get("log_y"):
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if flags == 0:
                implot.setup_legend(implot.LOCATION_NORTH_EAST) if hasattr(implot, "LOCATION_NORTH_EAST") else implot.setup_legend()
            self._fit_limits(source, series, bool(section.get("log_x")))
            for item in series:
                x = np.asarray(item["x"], dtype=float)
                y = np.asarray(item["y"], dtype=float)
                colour = _colour(item.get("color", "white"))
                if item.get("no_line"):
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, float(item.get("symbol_size", 9)), colour)
                    implot.plot_scatter(item.get("name", ""), x, y)
                else:
                    implot.set_next_line_style(colour, float(item.get("width", 1.5)), (6, 4) if item.get("dash") else None)
                    implot.plot_line(item.get("name", ""), x, y)
            implot.end_plot()
            im.set_item_tooltip(re_plain(section.get("description") or f"{title}: prediction from the current scheme and optics."))

    @staticmethod
    def _plot_box(height: float) -> tuple:
        """Where a plot about to be drawn goes: the cursor, the room to the right and the height (-1: the room below)."""
        x, y = im.get_cursor_screen_pos()
        room_w, room_h = im.get_content_region_avail()[:2]
        return (float(x), float(y), float(room_w), float(room_h if height <= 0 else height))

    def _fit_limits(self, key: str, series: list, log_x: bool) -> None:
        """Frame the data whenever it changes; leave the view alone while only the user moved it."""
        xs = [np.asarray(s["x"], dtype=float) for s in series]
        ys = [np.asarray(s["y"], dtype=float) for s in series]
        if not xs:
            return
        x = np.concatenate(xs)
        y = np.concatenate(ys)
        x, y = x[np.isfinite(x)], y[np.isfinite(y)]
        if log_x:
            x = x[x > 0]
        if not len(x) or not len(y):
            return
        x0, x1, y0, y1 = float(x.min()), float(x.max()), float(y.min()), float(y.max())
        signature = tuple(round(v, 9) for v in (x0, x1, y0, y1)) + (len(series),)
        if self._limits_key.get(key) == signature:
            return
        self._limits_key[key] = signature
        pad = 0.06 * ((y1 - y0) or abs(y1) or 1.0)
        if log_x:
            x0, x1 = x0 / 1.2, x1 * 1.2
        else:
            span = (x1 - x0) or 1.0
            x0, x1 = x0 - 0.02 * span, x1 + 0.02 * span
        implot.setup_axes_limits(x0, x1, y0 - pad, y1 + pad, implot.COND_ALWAYS)

    # -- the state diagram -------------------------------------------------------------------------------- #
    def _positions(self, n: int) -> np.ndarray:
        if n == 2:
            return np.array([[-0.8, 0.0], [0.8, 0.0]])
        angle = np.pi + np.linspace(0, 2 * np.pi, n, endpoint=False)
        return np.stack([np.cos(angle), np.sin(angle)], axis=1)

    def _draw_state_tab(self) -> None:
        total = im.get_content_region_avail()[1]
        optics_h = ROW_H * 12 + 14.0 + NOTE_H
        self._diagram(max(total - optics_h - 28.0, 140.0))
        if im.collapsing_header("Optics and measurement", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip("Power, wavelength, extinction, beam waists, diffusion and the measurement settings.")
            SPEC["optics"]["sections"][0]["height"] = optics_h
            self._form("optics")

    def _diagram(self, height: float) -> None:
        model = self.model
        sat = model.saturation
        n = sat.n_states
        pos = self._positions(n)
        labels = list(sat.state_labels)
        flags = implot.FLAGS_EQUAL | implot.FLAGS_NO_MOUSE_TEXT if hasattr(implot, "FLAGS_NO_MOUSE_TEXT") else implot.FLAGS_EQUAL
        self.item_rects["state_scheme"] = self._plot_box(height)
        if implot.begin_plot(f"State scheme##{n}", (-1, height), flags):
            decorations = implot.AXIS_FLAGS_NO_DECORATIONS
            implot.setup_axes("", "", decorations, decorations)
            implot.setup_legend()
            implot.setup_axes_limits(-1.45, 1.45, -1.35, 1.35, implot.COND_ALWAYS)
            seen = set()
            for src, dst, group, value in SaturationPanel.state_edges(model):
                p, q = pos[src], pos[dst]
                chord = q - p
                length = float(np.hypot(*chord)) or 1.0
                normal = np.array([chord[1], -chord[0]]) / length  # to the right of the direction: the reverse edge bows away
                control = (p + q) / 2.0 + normal * 0.28 * length
                t = np.linspace(0.16, 0.84, 24)[:, None]
                curve = (1 - t) ** 2 * p + 2 * (1 - t) * t * control + t**2 * q
                colour = _colour(DARK_COLOUR if group == "dark" else EXCITATION_COLOUR)
                name = "dark transition" if group == "dark" else "excitation"
                label = name if name not in seen else f"##{group}{src}{dst}"
                seen.add(name)
                implot.set_next_line_style(colour, 2.0)
                implot.plot_line(label, curve[:, 0], curve[:, 1])
                tip = curve[-1]
                back = curve[-1] - curve[-3]
                back = back / (float(np.hypot(*back)) or 1.0)
                side = np.array([-back[1], back[0]])
                head = np.array([tip - 0.09 * back + 0.045 * side, tip, tip - 0.09 * back - 0.045 * side])
                implot.set_next_line_style(colour, 2.0)
                implot.plot_line(f"##head{group}{src}{dst}", head[:, 0], head[:, 1])
                mid = curve[len(curve) // 2]
                text = f"{value:g}" if group == "dark" else f"σ {value:g}"
                implot.plot_text(text, float(mid[0]), float(mid[1]), (0.0, 0.0))
            for i, label in enumerate(labels):
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 26.0, _colour(STATE_COLOURS[i % len(STATE_COLOURS)]))
                implot.plot_scatter(f"##state{i}", [float(pos[i, 0])], [float(pos[i, 1])])
                implot.plot_text(str(label), float(pos[i, 0]), float(pos[i, 1]), (0.0, 0.0))
            implot.end_plot()
            im.set_item_tooltip(
                "The scheme: states as circles, dark transitions (orange, rate in the units of K_dark) and excitation "
                "transitions (pink, sigma relative to the peak rate) as arrows. Edit the rates in the tables on the left."
            )
        self.item_rects["rate_matrix"] = self.item_rects.get("k_dark_header", self.item_rects["state_scheme"])

    # -- the summary ------------------------------------------------------------------------------------------ #
    def _draw_info(self) -> None:
        panel = self.panel
        rows = panel.info_rows()
        if not rows:
            im.text_wrapped("Press Compute to run the calculation.")
            return
        title = panel.info_title()
        if title:
            im.text_unformatted(title)
            im.separator()
        for label, value in rows:
            im.text_disabled(label)
            im.text_wrapped(value)
            im.spacing()
        footer = panel.info_footer()
        if footer:
            im.separator()
            im.text_wrapped(footer)

    # -- files ------------------------------------------------------------------------------------------------- #
    def _draw_dialog(self, box) -> None:
        if self.dialog is None:
            return
        close = self.file_window.begin(box)
        chosen = self.dialog.draw()
        self.file_window.end()
        if close or chosen is False:
            self.dialog = None
        elif chosen:
            path = chosen[0]
            mode, self.dialog = self.dialog_mode, None
            try:
                if mode == "open":
                    self.load_scheme(path)
                else:
                    if not pathlib.Path(path).suffix:
                        path = str(pathlib.Path(path).with_suffix(".json"))
                    self.model.save_scheme_to_file(path)
                    self.status = f"Saved {path}"
                self.error = ""
            except Exception as exc:  # noqa: BLE001 - shown in the window
                self.error = f"Error: {exc}"

    # -- one frame -------------------------------------------------------------------------------------------- #
    def _render(self) -> None:
        vp = im.get_main_viewport()
        box = (0.0, 0.0, float(vp.size[0]), float(vp.size[1]))
        if not self._ratio_set:
            self._ratio_set = True  # a narrow window gives the controls room for their fields; the bar still drags
            self.docks.layout.ratio = max(0.40, min(0.52, MIN_CONTROLS / max(float(vp.size[0]), 1.0)))
        self.docks.draw(box)
        self._draw_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def files_dropped(self, paths) -> None:
        """A dropped JSON file is loaded as a scheme."""
        for path in paths:
            if str(path).lower().endswith(".json"):
                try:
                    self.load_scheme(path)
                except Exception as exc:  # noqa: BLE001
                    self.error = f"Error: {exc}"
                return
        self.error = "Error: drop a scheme .json file."

    def close(self) -> None:
        """Persist the session as the Qt tool does when its window closes."""
        self.model.save_user_settings()


def re_plain(text: str) -> str:
    from chisurf.plugins.calculator.native_form import plain

    return plain(text)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return SaturationApp(SaturationModel(restore=kwargs.get("restore", True)))
