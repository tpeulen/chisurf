"""EMTK immediate-mode UI for the combined FRET / HomoFRET calculator.

Two tabs, one canvas. Each tab is a dock layout of its own: the parameters on
the left, the distance distribution and its derived rate / anisotropy plots on
the right. The coupling that needed ``blockSignals`` gymnastics under Qt falls
out of immediate mode: the fields read and write the model, an edit runs its
one handler, and the handler's results are next frame's field values — there
are no signals to echo.
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
    from .tool import FretCalculatorTool, _FretModel, _HomoFretModel

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)

_TAB_BAR_H = 26.0


def _series_plot(name: str, series: list[dict]) -> None:
    """Draw one declarative plot series list; active solid, the other dashed."""
    for s in series:
        xs = np.asarray(s.get("x", []), dtype=float)
        ys = np.asarray(s.get("y", []), dtype=float)
        if not len(xs) or not len(ys):
            continue
        colour = s.get("color", "#888888")
        if isinstance(colour, str):
            colour = tuple(int(colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)) + (255,)
        dash = s.get("style") == "dash"
        implot.set_next_line_style(
            colour, float(s.get("width", 1.0)), dash=(4.0, 3.0) if dash else None
        )
        implot.plot_line(s.get("name") or name, xs, ys)


def _changed(value, new) -> bool:
    """One field's edit test, tolerant of array-free scalars only."""
    return new != value


class _HeteroTab(TourTarget):
    """The HeteroFRET calculator, rendered immediate-mode."""

    def __init__(
        self,
        tool: FretCalculatorTool,
        model: _FretModel,
        on_guide: Callable[[], None],
        on_help: Callable[[], None],
    ) -> None:
        self.tool = tool
        self.model = model
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split(
            "h",
            0.42,
            Region("params"),
            Split("v", 0.55, Region("distance"), Region("rate")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "params",
            "🎛️ FRET parameters",
            self._draw_params,
            dock="params",
            closable=False,
        )
        self.docks.add_window(
            "distance",
            "📏 Distance distribution",
            self._draw_distance,
            dock="distance",
            closable=False,
        )
        self.docks.add_window(
            "rate",
            "⚡ Rate-constant distribution",
            self._draw_rate,
            dock="rate",
            closable=False,
        )

    # ── plumbing ──────────────────────────────────────────────────────

    def _compute_forward(self) -> None:
        r = self.tool._client.compute_fret(
            R=self.model.R,
            R0=self.model.R0,
            tau0=self.model.tau0,
            kappa2=0.667,
            sigma=self.model.sigma,
            distribution="chi" if self.model.use_chi else "gaussian",
        )
        if r.get("ok"):
            self._apply(r["result"])

    def _apply(self, r: dict) -> None:
        """Write a compute result back, as ``_set_from_result`` did."""
        # Qt's spin boxes also bounded values written by inverse handlers.
        # E=0/1 produces infinite distance/rate; never feed those into plots.
        for attr, key, low, high in (
            ("R", "R", 0.1, 9999.0),
            ("E", "E", 0.0, 1.0),
            ("tau", "tau_DA", 0.0, 9999.0),
            ("kFRET", "kFRET", 0.0, 9999.0),
        ):
            value = float(r[key])
            if not np.isnan(value):
                setattr(self.model, attr, float(np.clip(value, low, high)))

    def _compute_from_lifetime(self) -> None:
        r = self.tool._client.compute_fret_from_lifetime(
            tau_DA=self.model.tau, R0=self.model.R0, tau0=self.model.tau0
        )
        if r.get("ok"):
            self._apply(r["result"])

    def _compute_from_efficiency(self) -> None:
        r = self.tool._client.compute_fret_from_efficiency(
            E=self.model.E, R0=self.model.R0, tau0=self.model.tau0
        )
        if r.get("ok"):
            self._apply(r["result"])

    def _compute_from_rate(self) -> None:
        r = self.tool._client.compute_fret_from_rate(
            kFRET=self.model.kFRET, R0=self.model.R0, tau0=self.model.tau0
        )
        if r.get("ok"):
            self._apply(r["result"])

    # ── the fields ────────────────────────────────────────────────────

    def _draw_params(self, box) -> None:
        m = self.model
        before_inputs = vars(m).copy()
        if im.button("📖 Guide"):
            self.on_guide()
        im.set_item_tooltip("A step-by-step walk through the calculator.")
        self.remember("guide")
        if im.get_line_avail() < 100.0:
            im.new_line()
        else:
            im.same_line()
        if im.button("❓ Help"):
            self.on_help()
        im.set_item_tooltip("The short help page for the FRET calculator.")
        self.remember("help")
        im.separator()

        # Each field: edit in place, then run the handler the old tab wired to
        # that field's editingFinished. One edit per frame drives one handler;
        # the results are written back for the next frame — no echo, no
        # blocking.
        _, v = bounded_float("τ₀ donor [ns]", m.tau0, step=0.1, minimum=0.001, maximum=9999.0)
        im.set_item_tooltip("Donor-only fluorescence lifetime (ns), no acceptor present.")
        self.remember("tau0")
        if _changed(m.tau0, v):
            m.tau0 = v
            self._compute_forward()
        _, v = bounded_float("R₀ [Å]", m.R0, step=0.5, minimum=0.1, maximum=999.0)
        im.set_item_tooltip("Förster radius R₀ (Å).")
        self.remember("R0")
        if _changed(m.R0, v):
            m.R0 = v
            self._compute_forward()
        _, v = bounded_float("σ [Å]", m.sigma, step=0.5, minimum=0.1, maximum=999.0)
        im.set_item_tooltip("Width of the donor-acceptor distance distribution (Å).")
        self.remember("sigma")
        if _changed(m.sigma, v):
            m.sigma = v
            self._compute_forward()
        self.remember("params")

        im.separator()
        _, checked = im.checkbox("Use χ² distribution", m.use_chi)
        im.set_item_tooltip(
            "Use a 3D non-central chi distance distribution instead of a "
            "Gaussian: non-negative and vanishing at contact, where a Gaussian "
            "assigns weight to negative distances."
        )
        if checked != m.use_chi:
            m.use_chi = checked
            self._compute_forward()
        self.remember("use_chi")

        im.separator()
        _, v = bounded_float("R_DA [Å]", m.R, step=0.5, minimum=0.1, maximum=9999.0)
        im.set_item_tooltip(
            "Donor-acceptor distance (Å); any of distance, lifetime, "
            "efficiency or rate may be entered and the others are recomputed."
        )
        self.remember("R")
        if _changed(m.R, v):
            m.R = v
            self._compute_forward()
        _, v = bounded_float("τ_DA [ns]", m.tau, step=0.05, minimum=0.0, maximum=9999.0)
        im.set_item_tooltip(
            "Donor lifetime in the presence of acceptor (ns); editing it "
            "back-computes the distance."
        )
        self.remember("tau")
        if _changed(m.tau, v):
            m.tau = v
            self._compute_from_lifetime()
        _, v = bounded_float("E", m.E, step=0.01, minimum=0.0, maximum=1.0)
        im.set_item_tooltip("FRET efficiency; editing it back-computes the distance.")
        self.remember("E")
        if _changed(m.E, v):
            m.E = v
            self._compute_from_efficiency()
        _, v = bounded_float("k_FRET [1/ns]", m.kFRET, step=0.01, minimum=0.0, maximum=9999.0)
        im.set_item_tooltip("FRET rate constant (1/ns); editing it back-computes the distance.")
        self.remember("kFRET")
        if _changed(m.kFRET, v):
            m.kFRET = v
            self._compute_from_rate()

        for name, before in before_inputs.items():
            if getattr(m, name) != before:
                getattr(self, "on_used", lambda name: None)(name)

    def _draw_distance(self, box) -> None:
        if implot.begin_plot("##het_distance", (-1, -1)):
            implot.setup_axes("R_DA [Å]", "p(R)")
            implot.setup_legend()
            _series_plot("distance", self.model.distance_plot_series())
            implot.end_plot()
            im.set_item_tooltip(
                "Donor-acceptor distance distribution: Gaussian vs the "
                "non-negative chi distribution, the active one solid."
            )
        self.remember("distance")

    def _draw_rate(self, box) -> None:
        if implot.begin_plot("##het_rate", (-1, -1)):
            implot.setup_axes("k_FRET [1/ns]", "p(k)")
            implot.setup_legend()
            _series_plot("rate", self.model.rate_plot_series())
            implot.end_plot()
            im.set_item_tooltip(
                "FRET-rate-constant distribution induced by the distance distribution."
            )
        self.remember("rate")

    def draw(self, x: float, y: float, w: float, h: float) -> None:
        self.docks.draw((x, y, w, h))


class _HomoTab(TourTarget):
    """The HomoFRET calculator, rendered immediate-mode."""

    def __init__(
        self,
        tool: FretCalculatorTool,
        model: _HomoFretModel,
        on_guide: Callable[[], None],
        on_help: Callable[[], None],
    ) -> None:
        self.tool = tool
        self.model = model
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split(
            "h",
            0.42,
            Region("params"),
            Split("v", 0.55, Region("distance"), Region("aniso")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "params",
            "🎛️ Homo-FRET parameters",
            self._draw_params,
            dock="params",
            closable=False,
        )
        self.docks.add_window(
            "distance",
            "📏 Distance distribution",
            self._draw_distance,
            dock="distance",
            closable=False,
        )
        self.docks.add_window(
            "aniso",
            "🧭 Anisotropy decay",
            self._draw_aniso,
            dock="aniso",
            closable=False,
        )

    def _compute(self) -> None:
        r = self.tool._client.compute_homo_fret(
            t_RM=self.model.t_RM,
            rho=self.model.rho,
            tau0=self.model.tau0,
            R0=self.model.R0,
        )
        if r.get("ok"):
            res = r["result"]
            self.model.k_homo = res["k_homo"]
            rda = res["R_DA"]
            if np.isfinite(rda) and rda > 0:
                self.model.R_DA = rda

    def _compute_backmap(self) -> None:
        r = self.tool._client.homo_backmap(
            R_DA=self.model.R_DA,
            R0=self.model.R0,
            tau0=self.model.tau0,
            rho=self.model.rho,
        )
        if r.get("ok"):
            res = r["result"]
            if np.isfinite(res["k_homo"]):
                self.model.k_homo = res["k_homo"]
            if np.isfinite(res["t_RM"]) and res["t_RM"] > 0:
                self.model.t_RM = res["t_RM"]

    def _draw_params(self, box) -> None:
        m = self.model
        before_inputs = vars(m).copy()
        if im.button("📖 Guide"):
            self.on_guide()
        im.set_item_tooltip("A step-by-step walk through the calculator.")
        self.remember("guide")
        if im.get_line_avail() < 100.0:
            im.new_line()
        else:
            im.same_line()
        if im.button("❓ Help"):
            self.on_help()
        im.set_item_tooltip("The short help page for the FRET calculator.")
        self.remember("help")
        im.separator()

        _, v = bounded_float("τ₀ donor [ns]", m.tau0, step=0.1, minimum=0.001, maximum=9999.0)
        im.set_item_tooltip("Donor-only fluorescence lifetime (ns).")
        self.remember("tau0")
        if _changed(m.tau0, v):
            m.tau0 = v
            self._compute()
        _, v = bounded_float("R₀ [Å]", m.R0, step=0.5, minimum=0.1, maximum=999.0)
        im.set_item_tooltip("Förster radius R₀ (Å).")
        self.remember("R0")
        if _changed(m.R0, v):
            m.R0 = v
            self._compute()
        _, v = bounded_float("t_RM [ns]", m.t_RM, step=0.1, minimum=0.001, maximum=9999.0)
        im.set_item_tooltip("Anisotropy decay (energy-migration) time t_RM (ns).")
        self.remember("t_RM")
        if _changed(m.t_RM, v):
            m.t_RM = v
            self._compute()
        _, v = bounded_float("ρ [ns]", m.rho, step=0.5, minimum=0.001, maximum=9999.0)
        im.set_item_tooltip("Rotational correlation time ρ (ns).")
        self.remember("rho")
        if _changed(m.rho, v):
            m.rho = v
            self._compute()
        self.remember("params")

        im.separator()
        _, v = bounded_float("R_DA [Å]", m.R_DA, step=0.5, minimum=0.0, maximum=9999.0)
        im.set_item_tooltip(
            "Donor-acceptor distance implied by the homo-FRET rate (Å); "
            "editing it back-maps to the anisotropy relaxation time."
        )
        self.remember("R_DA")
        if _changed(m.R_DA, v):
            m.R_DA = v
            self._compute_backmap()
        # k_Homo is an output of the forward compute / backmap, not an input
        # -- the old spin box was read-only, and disabled is that here.
        im.begin_disabled()
        bounded_float("k_Homo [1/ns]", m.k_homo, step=0.01, minimum=0.0, maximum=9999.0)
        im.set_item_tooltip(
            "Homo-FRET (energy-migration) rate constant, derived from "
            "t_RM / ρ; a computed output, not an input."
        )
        im.end_disabled()
        _, v = bounded_float("σ [Å]", m.sigma, step=0.5, minimum=0.1, maximum=999.0)
        im.set_item_tooltip("Width of the distance distribution shown in the plot below (Å).")
        m.sigma = v

        im.separator()
        _, checked = im.checkbox("Use χ² distribution", m.use_chi)
        im.set_item_tooltip(
            "Use a 3D non-central chi distance distribution (non-negative, "
            "vanishes at contact) instead of a Gaussian."
        )
        m.use_chi = checked
        self.remember("use_chi")

        for name, before in before_inputs.items():
            if getattr(m, name) != before:
                getattr(self, "on_used", lambda name: None)(name)

    def _draw_distance(self, box) -> None:
        if implot.begin_plot("##homo_distance", (-1, -1)):
            implot.setup_axes("R_DA [Å]", "p(R)")
            implot.setup_legend()
            _series_plot("distance", self.model.distance_plot_series())
            implot.end_plot()
            im.set_item_tooltip(
                "Distance distribution around R_DA: Gaussian vs the "
                "non-negative chi distribution, the active one solid."
            )
        self.remember("distance")

    def _draw_aniso(self, box) -> None:
        if implot.begin_plot("##homo_aniso", (-1, -1)):
            implot.setup_axes("t [ns]", "p(t)")
            implot.setup_legend()
            _series_plot("aniso", self.model.aniso_time_plot_series())
            implot.end_plot()
            im.set_item_tooltip(
                "Characteristic anisotropy-decay time distribution: rotational "
                "depolarisation (ρ) in parallel with energy-transfer "
                "depolarisation (2·k_FRET)."
            )
        self.remember("aniso")

    def draw(self, x: float, y: float, w: float, h: float) -> None:
        self.docks.draw((x, y, w, h))


class FretCalcApp(ImApp):
    """The EMTK ImApp for the FRET calculator: a tab bar over two dock layouts."""

    def __init__(self, tool: FretCalculatorTool) -> None:
        self.tool = tool
        self.hetero = _HeteroTab(
            tool, tool._hetero_model, on_guide=self.start_guide, on_help=self.show_help
        )
        self.homo = _HomoTab(
            tool, tool._homo_model, on_guide=self.start_guide, on_help=self.show_help
        )
        self.active_tab = 0
        self._tab_names = ("HeteroFRET", "HomoFRET")
        self._pending_tab: str | None = None

        # The tabs computed once at construction under Qt; keep that order so
        # the first frame shows computed outputs, not the model's defaults.
        self.hetero._compute_forward()
        self.homo._compute()

        self.help_window = EmTkHelpWindow(
            title="FRET Calculator — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
            wait_for_controls=True,
        )
        self.hetero.on_used = self.tour.notify_used
        self.homo.on_used = self.tour.notify_used
        self.native_layouts = {"hetero": self.hetero.docks, "homo": self.homo.docks}
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        active = self.hetero if self.active_tab == 0 else self.homo
        return active.item_rects

    def select_tab(self, index: int) -> None:
        """Switch tabs programmatically, as a caller of the old QTabWidget did."""
        self._pending_tab = self._tab_names[index]

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def _render(self) -> None:
        vp = im.get_main_viewport()
        width = float(vp.size[0] or 900.0)
        height = float(vp.size[1] or 620.0)

        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, _TAB_BAR_H), im.Cond.ALWAYS)
        if im.begin(
            "##fret_tabs",
            (0.0, 0.0, width, _TAB_BAR_H),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_SCROLLBAR,
        ):
            if im.begin_tab_bar("fret_calc_tabs"):
                pending = self._pending_tab
                self._pending_tab = None
                if im.begin_tab_item(
                    "HeteroFRET", im.TabItemFlags.SET_SELECTED if pending == "HeteroFRET" else 0
                ):
                    self.active_tab = 0
                    im.end_tab_item()
                im.set_item_tooltip(
                    "HeteroFRET: a donor-acceptor pair — distance, lifetime, "
                    "efficiency and rate distributions."
                )
                if im.begin_tab_item(
                    "HomoFRET", im.TabItemFlags.SET_SELECTED if pending == "HomoFRET" else 0
                ):
                    self.active_tab = 1
                    im.end_tab_item()
                im.set_item_tooltip(
                    "HomoFRET: energy migration between like dyes — anisotropy "
                    "decay and the implied donor-acceptor distance."
                )
                im.end_tab_bar()
            im.end()

        active = self.hetero if self.active_tab == 0 else self.homo
        active.draw(0.0, _TAB_BAR_H, width, height - _TAB_BAR_H)

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)


__all__ = ["FretCalcApp", "WINDOW_BG"]


def make_app(**kwargs):
    """Construct the standalone EMTK calculator without loading a Qt host."""
    from chisurf.emtk.i18n import install

    install()
    from types import SimpleNamespace

    from ..backend import services
    from .model import _FretModel, _HomoFretModel

    client = SimpleNamespace(
        compute_fret=services.fret_compute_handler,
        compute_fret_from_lifetime=services.fret_from_lifetime_handler,
        compute_fret_from_efficiency=services.fret_from_efficiency_handler,
        compute_fret_from_rate=services.fret_from_rate_handler,
        compute_homo_fret=services.homo_compute_handler,
        homo_backmap=services.homo_backmap_handler,
    )
    state = SimpleNamespace(
        _client=client, _hetero_model=_FretModel(), _homo_model=_HomoFretModel()
    )
    return FretCalcApp(state)
