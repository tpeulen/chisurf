"""EMTK immediate-mode UI for the RICS-precision calculator.

Left: the settings (sample, optics, scan, estimator) as they were authored in
``precision.view.json``. Right: the predicted error against pixel dwell time on
log axes with the user's own setting marked, the numbers behind the curve, and
the one-line verdict. The tool (:class:`~.tool.RicsPrecisionTool`) keeps the
Qt-free :class:`~.view_model.PrecisionViewModel` and runs the sweep off the UI
thread; this app renders its state and calls back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

if TYPE_CHECKING:
    from .tool import RicsPrecisionTool

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_ORANGE = (232, 115, 76, 255)
ACCENT_BLUE = (76, 155, 232, 255)
TEXT_DIM = (0.65, 0.7, 0.75, 1.0)

_TABLE_FLAGS = im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE


class PrecisionGui(TourTarget):
    """EMTK GUI for one RICS-precision prediction."""

    def __init__(
        self,
        tool: RicsPrecisionTool,
        on_predict: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_predict = on_predict
        self.on_export = on_export
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split("h", 0.42, Region("settings"), Region("result"))
        self.docks = DockManager(layout)
        self.docks.add_window(
            "settings", "⚙️ Settings", self._draw_settings, dock="settings", closable=False
        )
        self.docks.add_window(
            "result", "📉 Predicted precision", self._draw_result, dock="result", closable=False
        )

        self.help_window = EmTkHelpWindow(
            title="RICS precision — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(720.0, 540.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
            wait_for_controls=True,
        )

    # ── state plumbing ────────────────────────────────────────────────────

    @property
    def model(self):
        return self.tool.model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 900.0)
        height = float(h or vp.size[1] or 620.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the settings dock ─────────────────────────────────────────────────

    def _draw_settings(self, box: tuple[float, float, float, float]) -> None:
        before_inputs = {
            k: v for k, v in vars(self.model).items() if isinstance(v, (float, int, str, bool))
        }
        model = self.model

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        im.begin_disabled(bool(getattr(self.tool, "busy", False)))
        if im.button("▶ Predict"):
            if callable(self.on_predict):
                self.on_predict()
        im.set_item_tooltip(
            "Sweep the pixel dwell time and predict the relative error on D, "
            "marking your own setting on the curve."
        )
        im.pop_style_color(3)
        self.remember("predict")
        im.end_disabled()

        im.same_line()
        if im.button("💾 CSV"):
            if callable(self.on_export):
                self.on_export()
        im.set_item_tooltip(
            "Export the numbers behind the curve (dwell, line, frame, error) to a CSV file."
        )
        self.remember("export")
        im.same_line()
        if im.button("📖 Guide"):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.remember("guide")
        im.same_line()
        if im.button("❓ Help"):
            self.show_help()
        im.set_item_tooltip("The short help page: reading the curve and what moves the answer.")
        self.remember("help")
        im.separator()

        im.begin_disabled(bool(getattr(self.tool, "busy", False)))
        if im.collapsing_header("Sample", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip("Expand or collapse sample settings.")
            _, model.diffusion_coefficient = bounded_float(
                "D [µm²/s]", model.diffusion_coefficient, step=1.0, minimum=1e-06, maximum=100000.0
            )
            self.remember("diffusion_coefficient")
            if im.is_item_clicked():
                self.tour.notify_used("diffusion_coefficient")
            im.set_item_tooltip(
                "The diffusion coefficient you expect to measure (µm²/s); use a "
                "literature value or a guess and check how sensitive the "
                "prediction is to it."
            )
            _, model.n_particles = bounded_float(
                "Molecules in view", model.n_particles, step=5.0, minimum=0.01, maximum=1000000.0
            )
            self.remember("n_particles")
            im.set_item_tooltip(
                "Number of fluorescent molecules in the illuminated region; too "
                "few and the correlation is noisy, too many and its amplitude "
                "(which goes as 1/N) sinks into the background."
            )
            _, model.brightness_khz = bounded_float(
                "Brightness [kHz/mol.]",
                model.brightness_khz,
                step=10.0,
                minimum=0.001,
                maximum=100000.0,
            )
            self.remember("brightness_khz")
            im.set_item_tooltip(
                "Photons per second from a single molecule at the centre of the "
                "focus (kHz); the dominant lever on precision after the number "
                "of frames."
            )
        if im.collapsing_header("Optics", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip("Expand or collapse optics settings.")
            _, model.w_r = bounded_float(
                "w_r [µm]", model.w_r, step=0.05, minimum=0.001, maximum=100.0
            )
            self.remember("w_r")
            im.set_item_tooltip(
                "Lateral beam waist (µm); measure it with the waist calibration "
                "rather than guessing, as every predicted error scales with it."
            )
            _, model.w_z = bounded_float(
                "w_z [µm]", model.w_z, step=0.1, minimum=0.001, maximum=1000.0
            )
            self.remember("w_z")
            im.set_item_tooltip("Axial beam waist (µm); only its ratio to w_r matters here.")
            _, model.pixel_size_nm = bounded_float(
                "Pixel size [nm]", model.pixel_size_nm, step=5.0, minimum=1.0, maximum=100000.0
            )
            self.remember("pixel_size_nm")
            if im.is_item_clicked():
                self.tour.notify_used("pixel_size_nm")
            im.set_item_tooltip(
                "Physical pixel size (nm); it should sample the waist several "
                "times over, around 4–6 pixels across w_r."
            )
            _, model.two_d = im.checkbox("Membrane (2-D)", model.two_d)
            self.remember("two_d")
            im.set_item_tooltip(
                "Use the 2-D geometry for a membrane or a surface, which has "
                "different shape factors from a 3-D focus."
            )
        if im.collapsing_header("Scan", im.TreeNodeFlags.DEFAULT_OPEN):
            im.set_item_tooltip("Expand or collapse scan settings.")
            _, model.pixel_time_us = bounded_float(
                "Pixel dwell [µs]", model.pixel_time_us, step=1.0, minimum=0.01, maximum=100000.0
            )
            self.remember("pixel_time_us")
            if im.is_item_clicked():
                self.tour.notify_used("pixel_time_us")
            im.set_item_tooltip(
                "The dwell time you plan to use (µs); it is marked on the curve "
                "so you can see how far it sits from the optimum."
            )
            _, model.line_overhead = bounded_float(
                "Line overhead ×", model.line_overhead, step=0.1, minimum=1.0, maximum=100.0
            )
            self.remember("line_overhead")
            im.set_item_tooltip(
                "How much longer a line takes than the sum of its pixels, from "
                "flyback and settling; 1.2 means 20 % overhead."
            )
            _, model.nx = bounded_int("Pixels per line", model.nx, minimum=8, maximum=4096)
            self.remember("nx")
            im.set_item_tooltip(
                "Image width; a larger image averages more pixel pairs and so "
                "measures better, at the cost of a longer frame."
            )
            _, model.ny = bounded_int("Lines per frame", model.ny, minimum=8, maximum=4096)
            self.remember("ny")
            im.set_item_tooltip("Image height of the scan.")
            _, model.n_images = bounded_int(
                "Frames", model.n_images, step=10, minimum=1, maximum=100000
            )
            self.remember("n_images")
            im.set_item_tooltip(
                "Frames averaged; precision improves as the square root of "
                "this, so halving the error costs four times the acquisition time."
            )
        if im.collapsing_header("Estimator", 0):
            im.set_item_tooltip("Expand or collapse estimator settings.")
            _, model.n_lags = bounded_int("Lags fitted", model.n_lags, minimum=1, maximum=15)
            self.remember("n_lags")
            im.set_item_tooltip(
                "Largest lag included on each axis; the cost grows as the "
                "fourth power of this, and it must stay below half the smaller "
                "image dimension."
            )
            _, model.n_repeats = bounded_int(
                "Repeats", model.n_repeats, step=5, minimum=5, maximum=2000
            )
            self.remember("n_repeats")
            im.set_item_tooltip(
                "Monte-Carlo realisations behind each point; the prediction "
                "carries roughly 1/sqrt(2 × repeats) of its own uncertainty."
            )
            _, model.seed = bounded_int("Seed", model.seed, minimum=0, maximum=1000000)
            self.remember("seed")
            im.set_item_tooltip("Random seed, so a quoted prediction can be reproduced.")

        im.end_disabled()

        # ── the result dock ───────────────────────────────────────────────────

        for name, before in before_inputs.items():
            if getattr(self.model, name, before) != before:
                self.tour.notify_used(name)

    def _draw_result(self, box: tuple[float, float, float, float]) -> None:
        model = self.model
        rows = model.sweep_rows()

        # The plot takes a fixed third of the window; the table and the verdict
        # must stay visible under it, so a tall result dock grows the table,
        # never the plot.
        if implot.begin_plot("##sweep", (-1, min(220.0, max(150.0, box[3] * 0.35)))):
            implot.setup_axes("pixel dwell / µs", "predicted error / %")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend()
            series = model.sweep_series()
            if series:
                for s in series:
                    xs = np.asarray(s.get("x", []), dtype=np.float64)
                    ys = np.asarray(s.get("y", []), dtype=np.float64)
                    mask = np.isfinite(xs) & np.isfinite(ys) & (xs > 0) & (ys > 0)
                    if not mask.any():
                        continue
                    if s.get("no_line"):
                        implot.set_next_marker_style(
                            implot.MARKER_DIAMOND, 9.0, ACCENT_ORANGE[:3] + (255,)
                        )
                        implot.plot_scatter(s.get("name", "your setting"), xs[mask], ys[mask])
                    else:
                        implot.set_next_line_style(ACCENT_BLUE, 2.0)
                        implot.plot_scatter(s.get("name", "predicted error"), xs[mask], ys[mask])
                self.remember("plot")
            else:
                implot.plot_dummy("press Predict to sweep the dwell time")
            implot.end_plot()
            im.set_item_tooltip(
                "Predicted relative error on D against pixel dwell time (log "
                "axes), with your own setting marked; both ends rise — too fast "
                "and the molecule has not moved between pixels, too slow and it "
                "has already decorrelated."
            )

        im.spacing()
        im.text_colored("The numbers behind the curve", (0.9, 0.9, 0.9, 1.0))
        # Sized to the rows it actually has, capped to what the dock window can
        # still show under the plot, so the verdict line below is never pushed
        # out of the window.
        remaining = max(90.0, float(box[3]) - 320.0)
        table_h = min(remaining, len(rows) * 24.0 + 34.0)
        if im.begin_table("sweep_rows", 4, _TABLE_FLAGS, (0, table_h)):
            im.table_setup_column("dwell / µs", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("line / ms", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("frame / ms", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("error / %", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()
            im.set_item_tooltip(
                "The numbers behind the curve: predicted relative error on D for "
                "each dwell time; '—' means the timing is not realisable."
            )
            for row in rows:
                im.table_next_row()
                for i, key in enumerate(("dwell", "line", "frame", "error")):
                    im.table_set_column_index(i)
                    im.text_unformatted(row[key])
            im.end_table()

        im.spacing()
        im.separator()
        im.text_colored(model.status, (0.35, 0.75, 1.0, 1.0))


class RicsPrecisionApp(ImApp):
    """The EMTK ImApp for the RICS-precision calculator."""

    def __init__(
        self,
        tool: RicsPrecisionTool,
        on_predict: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.precision_gui = PrecisionGui(
            tool,
            on_predict=on_predict,
            on_export=on_export,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        self.native_layouts = {"main": self.precision_gui.docks}
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.precision_gui.item_rects

    def start_guide(self) -> None:
        self.precision_gui.start_guide()

    def show_help(self) -> None:
        self.precision_gui.show_help()

    def _render(self) -> None:
        self.precision_gui.draw()


__all__ = ["RicsPrecisionApp", "WINDOW_BG"]


def make_app(**kwargs):
    """Construct the standalone EMTK precision planner with threaded prediction."""
    from chisurf.emtk.i18n import install

    install()
    import threading
    from types import SimpleNamespace

    from chisurf.plugins.calculator.export import install_csv_export

    from .view_model import PrecisionViewModel

    state = SimpleNamespace(model=PrecisionViewModel(), busy=False)

    def predict():
        if state.busy:
            return
        state.busy = True

        def run():
            try:
                state.model.compute()
            finally:
                state.busy = False

        threading.Thread(target=run, daemon=True).start()

    app = RicsPrecisionApp(state, on_predict=predict)
    # Worker results must repaint even when there are no pointer events.
    app.continuous = True

    def write(path):
        if state.model.sweep is None:
            raise ValueError("Predict something before exporting.")
        rows = state.model.sweep_rows()
        lines = ["dwell_us,line_ms,frame_ms,error_percent"]
        lines += [f"{r['dwell']},{r['line']},{r['frame']},{r['error']}" for r in rows]
        path.write_text("\n".join(lines) + "\n")

    app.precision_gui.on_export = install_csv_export(app, "rics_precision.csv", write)
    app.write_csv = write
    return app
