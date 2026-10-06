"""Native burst-wise FCS correlator: inputs, settings and the detector setup left, the curves and their plots right."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

from .controller import BurstFcsController
from .panel import BurstFcsPanel

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "burst_fcs_emtk.view.json").read_text(encoding="utf-8"))
#: The guide's and the tests' names for the tables (a form records a table under its source).
ALIASES = {"file_rows": "files", "pair_rows": "pairs", "curve_rows": "curves"}
WHITE, RED, YELLOW = (255, 255, 255, 255), (230, 40, 40, 255), (250, 204, 21, 255)
#: Width the controls get at least in a narrow window.
MIN_CONTROLS = 430.0
DIALOGS = {
    "files": ("Open BUR/BST files", "open", True, "BUR/BST (*.bur *.bst);;All files (*)", ""),
    "folder": ("Add analysis folder", "folder", True, "", ""),
    "load_settings": ("Load settings", "open", False, "Settings (*.json)", ""),
    "save_settings": (
        "Save settings",
        "save",
        False,
        "Settings (*.json)",
        "burst_fcs_settings.json",
    ),
    "load_pairs": ("Load channel pairs or detector setup", "open", False, "JSON (*.json)", ""),
    "save_pairs": ("Save channel pairs", "save", False, "JSON (*.json)", "burst_fcs_pairs.json"),
    "export_curves": ("Export curves", "save", False, "JSON (*.json)", "burst_fcs_curves.json"),
}


class BurstFcsApp(TourTarget, ImApp):
    """The window: controls (Inputs, Settings, Detector setup) left; correlation, distribution and curve list right."""

    def __init__(self, controller: BurstFcsController | None = None):
        self.controller = controller or BurstFcsController()
        self.panel = BurstFcsPanel(self)
        self.selected_file = None
        self.selected_pair = None
        self.dialog = None
        self.dialog_action = ""
        self.pairs_json = ""
        self.item_rects: dict = {}
        self.forms: dict = {}
        self._limits: dict = {}
        self._ratio_set = False
        self.file_window = DialogWindow(
            "Burst FCS file chooser", size=(560.0, 420.0), key="burst_fcs_files"
        )
        self.pairs_window = DialogWindow(
            "Channel pairs (JSON)", size=(480.0, 360.0), key="burst_fcs_pairs"
        )
        self.setup = ChannelDefinitionWidget()
        self._setup_name = self.setup.model.current_name
        self.help_window = EmTkHelpWindow(
            title="Burst-wise FCS - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=lambda: self.tour.start(),
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
            on_step_change=lambda _i, step: step.get("tab") and self.select_tab(step["tab"]),
        )
        self.tab = "Inputs"
        self.docks = DockManager(
            Split(
                "h",
                0.38,
                Split("v", 0.13, Region("toolbar"), Region("controls")),
                Split(
                    "v",
                    0.5,
                    Region("correlation"),
                    Split("h", 0.6, Region("curves"), Region("distribution")),
                ),
            ),
            name="burst_fcs",
        )
        self.docks.add_window(
            "toolbar", "Burst-wise FCS", self.draw_toolbar, dock="toolbar", closable=False
        )
        self.docks.add_window("inputs", "Inputs", self.draw_inputs, dock="controls", closable=False)
        self.docks.add_window(
            "settings", "Settings", self.draw_settings, dock="controls", closable=False
        )
        self.docks.add_window(
            "setup", "Detector setup", self.draw_setup, dock="controls", closable=False
        )
        self.docks.add_window(
            "correlation",
            "Correlation G(t)",
            self.draw_correlation,
            dock="correlation",
            closable=False,
        )
        self.docks.add_window(
            "distribution",
            "Distribution P(tau_D)",
            self.draw_distribution,
            dock="distribution",
            closable=False,
        )
        self.docks.add_window("curves", "Curves", self.draw_curves, dock="curves", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(self._render, continuous=True)

    # -- helpers ------------------------------------------------------------------------------------------ #
    def select_tab(self, name):
        """Bring a tab of the controls forward (the guide does it per step)."""
        self.tab = name
        self.docks.focus(
            {"Inputs": "inputs", "Settings": "settings", "Detector setup": "setup"}.get(name, name)
        )

    def _used(self, name):
        self.tour.notify_used(name)

    def form(self, name, spec=None, panel=None):
        state = self.forms.setdefault(name, FormState(on_used=self._used))
        state.rects.clear()
        draw_form(spec or SPEC[name], panel or self.panel, state, titles=False)
        self.item_rects.update(state.rects)
        for source, alias in ALIASES.items():
            if source in state.rects:
                self.item_rects[alias] = state.rects[source]

    # -- the dialogs and the demonstration data ------------------------------------------------------------ #
    def choose(self, action):
        title, mode, multiple, filters, filename = DIALOGS[action]
        self.dialog_action = action
        self.dialog = FileDialog(
            title, mode=mode, multiselect=multiple, filters=filters, filename=filename
        )
        self.file_window.title = title
        self.file_window.show()

    def _answer(self, paths):
        c, action = self.controller, self.dialog_action
        try:
            if action in ("files", "folder"):
                c.add_files(paths)
                c.status = f"{len(c.files)} input(s) listed."
            elif action == "load_settings":
                c.load_settings(paths[0])
            elif action == "save_settings":
                c.save_settings(self._suffix(paths[0]))
            elif action == "load_pairs":
                c.apply_pairs(Path(paths[0]).read_text())
            elif action == "save_pairs":
                c.save_pairs(self._suffix(paths[0]))
            elif action == "export_curves":
                c.export_curves(self._suffix(paths[0]))
        except Exception as exc:  # noqa: BLE001 - shown on the status line
            c.status = f"Error: {exc}"

    @staticmethod
    def _suffix(path):
        return str(Path(path).with_suffix(".json")) if not Path(path).suffix else str(path)

    def show_pairs_json(self):
        self.pairs_json = json.dumps(self.controller._pair_presets, indent=2)
        self.pairs_window.show()

    def load_example(self):
        """Write the demonstration photon stream and burst table into a temporary folder and list the table."""
        from ..demo import make_demo

        folder = Path(tempfile.mkdtemp(prefix="burst_fcs_demo_"))
        try:
            _spc, table = make_demo(folder)
        except Exception as exc:  # noqa: BLE001
            self.controller.status = f"Error: could not write the demonstration data: {exc}"
            return
        self.controller.add_files([str(table)])
        if (
            not self.controller._pair_presets
            or self.controller.pairs_text.count("donor_ACF")
            and len(self.controller._pair_presets) == 1
        ):
            self.controller.apply_pairs(
                json.dumps(
                    [
                        {"pair_name": "ACF_0", "chs_a": [0], "chs_b": [0]},
                        {"pair_name": "ACF_1", "chs_a": [1], "chs_b": [1]},
                        {"pair_name": "cross_01", "chs_a": [0], "chs_b": [1]},
                    ]
                )
            )
        self.controller.status = "Demonstration data added (8 bursts, two detectors)."
        self._used("example")

    def adopt_current_setup(self):
        model = self.setup.model
        detectors = model.get_settings().get("detectors", {})
        if self.controller.adopt_setup(model.current_name or "", detectors):
            self._used("use_setup")

    # -- the windows ---------------------------------------------------------------------------------------- #
    def draw_toolbar(self, box):
        self.form("toolbar")
        self.form("progress") if self.controller.running else self.form("status")

    def draw_inputs(self, box):
        im.text_unformatted("Burst folders or BUR/BST files")
        self.form("files")
        im.text_unformatted("FCS channel pairs")
        self.form("pairs")
        self.remember("inputs", tuple(box))

    def draw_settings(self, box):
        self.form("correlator")
        self.form("fitting")
        self.form("settings_files")
        self.remember("settings", tuple(box))

    def draw_setup(self, box):
        self.form("setup_button")
        self.setup.draw()

    def draw_curves(self, box):
        self.form("curves")
        self.remember("curves_window", tuple(box))

    # -- the plots ---------------------------------------------------------------------------------------------- #
    def _frame(self, key, x, y):
        """Frame the data when it changes, leave the view alone while only the user moved it."""
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        keep = np.isfinite(x) & np.isfinite(y) & (x > 0)
        if not keep.any():
            return
        x, y = x[keep], y[keep]
        sig = tuple(round(float(v), 9) for v in (x.min(), x.max(), y.min(), y.max()))
        if self._limits.get(key) == sig:
            return
        self._limits[key] = sig
        pad = 0.06 * ((y.max() - y.min()) or abs(y.max()) or 1.0)
        implot.setup_axes_limits(
            x.min() / 1.3,
            x.max() * 1.3,
            min(0.0, float(y.min())) - pad if y.min() < 0 else float(y.min()) - pad,
            float(y.max()) + pad,
            implot.COND_ALWAYS,
        )

    def draw_correlation(self, box):
        m = self.controller._model
        series = m.corr_plot_series()
        self.item_rects["correlation_plot"] = self._plot_box()
        if implot.begin_plot("##correlation", (-1, -1), 0 if series else implot.FLAGS_NO_LEGEND):
            implot.setup_axes("Correlation time t_c (ms)", "G")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if series:
                implot.setup_legend()
                x = np.concatenate([np.asarray(s["x"], dtype=float) for s in series])
                y = np.concatenate([np.asarray(s["y"], dtype=float) for s in series])
                self._frame("corr", x, y)
                for s in series:
                    sx, sy = np.asarray(s["x"], dtype=float), np.asarray(s["y"], dtype=float)
                    ok = np.isfinite(sx) & np.isfinite(sy) & (sx > 0)
                    implot.set_next_line_style(
                        WHITE if s["name"] == "data" else RED, float(s.get("width", 1.5))
                    )
                    implot.plot_line(s["name"], sx[ok], sy[ok])
                lo = m.tmin_fit if m.tmin_fit > 0 else float(np.nanmin(x[x > 0]))
                hi = m.tmax_fit if m.tmax_fit > 0 else float(np.nanmax(x))
                left = implot.drag_line_x(201, float(lo), (90, 160, 240, 255))
                right = implot.drag_line_x(202, float(hi), (90, 160, 240, 255))
                if not self.controller.running and (left.modified or right.modified):
                    a, b = sorted((max(float(left.value), 0.0), max(float(right.value), 0.0)))
                    m.tmin_fit, m.tmax_fit = a, b
                    self._used("correlation_plot")
            else:
                implot.setup_axes_limits(1e-4, 1e2, 0.0, 1.0, implot.COND_ALWAYS)
                implot.plot_text("Run FCS, then select a curve", 1e-1, 0.5)
            implot.end_plot()
            im.set_item_tooltip(
                "The selected burst's correlation curve (white) and its fit (red). Drag the two vertical lines to set the fit window t_min and t_max; the wheel zooms."
            )

    def draw_distribution(self, box):
        series = self.controller._model.dist_plot_series()
        self.item_rects["distribution_plot"] = self._plot_box()
        if implot.begin_plot("##distribution", (-1, -1), 0 if series else implot.FLAGS_NO_LEGEND):
            implot.setup_axes("Diffusion time tau_D (ms)", "P")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if series:
                implot.setup_legend()
                for s in series:
                    sx, sy = np.asarray(s["x"], dtype=float), np.asarray(s["y"], dtype=float)
                    self._frame("dist", sx, sy)
                    implot.set_next_line_style(YELLOW, 2.0)
                    implot.plot_line(s["name"], sx[sx > 0], sy[sx > 0])
            else:
                implot.setup_axes_limits(1e-6, 30.0, 0.0, 1.0, implot.COND_ALWAYS)
                implot.plot_text("MaxEnt mode only", 1e-3, 0.5)
            implot.end_plot()
            im.set_item_tooltip(
                "The diffusion-time distribution P(tau_D) of the selected curve (MaxEnt mode)."
            )

    @staticmethod
    def _plot_box():
        x, y = im.get_cursor_screen_pos()
        w, h = im.get_content_region_avail()[:2]
        return (float(x), float(y), float(w), float(h))

    # -- one frame ----------------------------------------------------------------------------------------- #
    def _render(self):
        c = self.controller
        c.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, float(vp.size[0]), float(vp.size[1]))
        if not self._ratio_set:
            self._ratio_set = True
            self.docks.layout.ratio = max(0.38, min(0.55, MIN_CONTROLS / max(frame[2], 1.0)))
        name = self.setup.model.current_name
        if name != self._setup_name:
            self._setup_name = name
            if name:
                self.adopt_current_setup()
        self.docks.draw(frame)
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            if self.tour.awaiting:
                self.tour.draw(*vp.size)  # the highlighted control must stay clickable
            else:
                # A window of its own over the docks: drawn into the root window the card's buttons sat under the dock windows
                # (a button is hovered only when no other window is under the pointer), so Prev and most Next presses never arrived.
                flags = (
                    im.WindowFlags.NO_DECORATION
                    | im.WindowFlags.NO_BACKGROUND
                    | im.WindowFlags.NO_SAVED_SETTINGS
                    | im.WindowFlags.NO_MOVE
                    | im.WindowFlags.NO_NAV
                )
                im.begin(
                    "##burst_fcs_tour", (0.0, 0.0, float(vp.size[0]), float(vp.size[1])), flags
                )
                self.tour.draw(*vp.size)
                im.end()
        if self.dialog:
            closed = self.file_window.begin(frame) == "close"
            result = self.dialog.draw()
            self.file_window.end()
            if closed or result is False:
                self.dialog = None
            elif result:
                self.dialog = None
                self._answer(result)
        elif self.file_window.open:
            self.file_window.hide()
        if self.pairs_window.open:
            closed = self.pairs_window.begin(frame) == "close"
            im.text_wrapped(self.pairs_json)
            self.pairs_window.end()
            if closed:
                self.pairs_window.hide()
        self.setup.draw_dialogs(frame)
        c.datasets.render(frame)
        self.setup.poll()

    def files_dropped(self, paths):
        self.on_paths_dropped(paths)

    def on_paths_dropped(self, paths):
        self.controller.on_paths_dropped(paths)

    def close(self):
        self.setup.close()
        self.controller.close()


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BurstFcsApp(**kwargs)
