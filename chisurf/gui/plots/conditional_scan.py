"""What the other parameters would have to be, if this one were fixed.

The question a correlated fit provokes — *"if this lifetime really were 4.2 ns,
what would the amplitudes have to be?"* — asked at every value at once, and
answered without evaluating the model. A profile scan answers it by re-fitting
at each point; in canonical form each answer is a matrix update, so dragging the
slider is free and the whole curve was computed from one curvature evaluation.

The plot is drawn in standardised units because that is where it reads: for a
Gaussian posterior each line is straight and **its slope is the correlation**.
A line at 45° means the two parameters move together one-for-one and the data
cannot tell them apart; a flat line means fixing this one tells you nothing about
that one. The numbers in real units are underneath.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.fitting
from chisurf.core.fitting import engine as E
from chisurf.gui import chiplot as cp
from chisurf.gui.chiplot import style as S
from chisurf.gui.plots import emtk_notes as N
from chisurf.gui.plots.plotbase import Plot

#: Line colours, reused per target parameter.
TARGET_COLOURS = (
    "#4c9be8",
    "#e8834c",
    "#5cc98a",
    "#c96ec9",
    "#e8c84c",
    "#7f7fe8",
    "#e85c7a",
    "#4cc9c9",
)

#: Half-width of the sweep, in standard deviations of the held parameter.
SCAN_SPAN = 3.0


class ConditionalScanPlot(Plot):
    """Hold one parameter at a value and read off the rest, interactively."""

    name = "What-if"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """The parameter choice, the held value, the plot and the readout."""
        from chisurf.gui.plots.emtk_page import PanelItem

        super().__init__(fit)
        self.fit = fit
        self._scan = None
        self._engine = None
        self._full_names = []
        #: Index into :attr:`parameters` of the held parameter.
        self.parameter = 0
        #: The held value, in standard deviations from the optimum.
        self.held_z = 0.0
        #: ``held = value`` above the plot, empty while there is no sweep.
        self.held_text = ""
        #: The notes under the plot (:mod:`~chisurf.gui.plots.emtk_notes`).
        self.readout = []
        # Frames until the requested re-fit check runs: one to show it started.
        self._check_pending = 0

        self.plot = cp.Panel()
        self.plot.set_labels(
            bottom="held value (standard deviations from the optimum)",
            left="shift in the other parameters (their own sd)",
        )
        self.panel_items = [PanelItem(self.plot, self.plot.control())]

        self._marker = None
        self._exact = None
        self._validity = None

    @property
    def parameters(self) -> list:
        """The parameters that can be held (short names)."""
        return [n.split(":")[-1] for n in self._full_names]

    def set_parameter(self, index: int) -> None:
        """Hold parameter *index* and recompute the sweep."""
        self.parameter = int(index)
        self._rebuild()

    def set_held(self, z: float) -> None:
        """Hold the parameter *z* standard deviations from its optimum."""
        self.held_z = float(np.clip(z, -SCAN_SPAN, SCAN_SPAN))
        self._draw_marker()

    def emtk_draw(self, box) -> None:
        """The controls row, then the plot over the readout."""
        from emtk import im

        if self._full_names and im.begin_grid("##what-if-bar", (0, 0, 0, 1, 0, 0)):
            im.text("Fix")
            im.next_cell()
            im.set_next_item_width(120.0)
            changed, picked = im.combo("##what-if-parameter", self.parameter, self.parameters)
            im.set_item_tooltip("The parameter to hold fixed.")
            if changed:
                self.set_parameter(picked)
            im.next_cell()
            im.text("at")
            im.next_cell()
            changed, z = im.slider_float("##what-if-held", self.held_z, -SCAN_SPAN, SCAN_SPAN,
                                         "%+.2f sd")
            im.set_item_tooltip("Where to hold it, in its own standard deviations.")
            if changed:
                self.set_held(z)
            im.next_cell()
            im.push_font({"family": "sans-serif", "bold": True})
            im.text(self.held_text)
            im.pop_font()
            im.next_cell()
            checking = self._check_pending > 0
            im.begin_disabled(checking or self._scan is None)
            if im.button("re-fitting…" if checking else "🔍 Check (re-fit)"):
                self._check_pending = 2
            im.end_disabled()
            im.set_item_tooltip(
                "Re-fit at each held value instead of assuming the posterior is "
                "Gaussian, and report how far the straight lines can be trusted."
            )
            im.end_grid()
        N.panel_and_notes("what-if", self.panel_items[0], self.readout)
        self._advance_check()

    def _advance_check(self) -> None:
        """Run a requested check one frame after the button said it started."""
        if self._check_pending == 2:
            self._check_pending = 1
            self.plot.control().refresh()
        elif self._check_pending == 1:
            self._check_pending = 0
            self._check_exact()
            self.plot.control().refresh()

    def _degrade(self, message: str) -> None:
        """Drop every trace of the previous update and say why there is nothing.

        Everything the previous sweep left goes, the parameter list first: with
        the *previous* engine and parameter list in place a selection change
        redrew the old sweep on top of *message*, so a fit with one free
        parameter kept showing a full what-if table for parameters that were no
        longer free.
        """
        self._scan = None
        self._engine = None
        self._full_names = []
        self._exact = None
        self._validity = None
        self._marker = None
        self.parameter = 0
        self.held_text = ""
        self.plot.clear()
        # ``clear()`` drops the curves but keeps the title, which would go on
        # naming the parameter that is no longer being fixed.
        self.plot.set_title(None)
        self.readout = [N.Line(message, N.MUTED)]

    def update(self, *args, **kwargs) -> None:
        """Rebuild the engine and the parameter list, then redraw."""
        super().update(*args, **kwargs)
        try:
            engine = E.GaussianEngine(self.fit).add_all_targets().run()
            form = engine.form()
        except Exception as e:
            self._degrade(f"no usable curvature: {e}")
            return
        if form is None or form.get_number_of_variables() < 2:
            self._degrade("needs a converged fit with at least two free parameters")
            return

        self._engine = engine
        current = self.parameters[self.parameter] if self.parameter < len(self._full_names) else None
        self._full_names = [str(n) for n in form.get_names()]
        # The same parameter stays held when the fit changes under it.
        self.parameter = self.parameters.index(current) if current in self.parameters else 0
        self._rebuild()

    def _rebuild(self, *args) -> None:
        """Recompute the sweep for the selected parameter and redraw."""
        if self._engine is None or not self._full_names:
            return
        index = max(0, self.parameter)
        if index >= len(self._full_names):
            return
        self._scan = self._engine.conditional_scan(
            self._full_names[index], points=61, span=SCAN_SPAN
        )
        # The overlay belongs to the parameter it was computed for.
        self._exact = None
        self._validity = None
        self._draw()

    # -- drawing ------------------------------------------------------------

    def _draw(self) -> None:
        """Draw every target's standardised response to the held value."""
        plot = self.plot
        plot.clear()
        self._marker = None
        scan = self._scan
        if scan is None or not scan["targets"]:
            self.readout = [N.Line("nothing left to condition on", N.MUTED)]
            return

        short = str(scan["name"]).split(":")[-1]
        plot.set_title(f"Fixing {short} — what the rest become")
        plot.legend()
        for k, target in enumerate(scan["targets"]):
            colour = TARGET_COLOURS[k % len(TARGET_COLOURS)]
            plot.line(
                scan["held_z"],
                target["z"],
                pen=S.to_pen(colour, width=1.8),
                name=str(target["name"]).split(":")[-1],
            )
        # The optimum, so "no change" has somewhere to be read off.
        plot.line(
            [-SCAN_SPAN, SCAN_SPAN], [0.0, 0.0], pen=S.to_pen("#808080", width=1.0, style="dash")
        )

        if self._exact is not None:
            exact_by_name = {t["name"]: t for t in self._exact["targets"]}
            for k, target in enumerate(scan["targets"]):
                other = exact_by_name.get(target["name"])
                if other is None:
                    continue
                colour = TARGET_COLOURS[k % len(TARGET_COLOURS)]
                z = np.asarray(other["z"], dtype=float)
                finite = np.isfinite(z)
                if not finite.any():
                    continue
                plot.scatter(
                    np.asarray(self._exact["held_z"])[finite],
                    z[finite],
                    size=8.0,
                    brush=colour,
                    pen=S.to_pen("#101010", width=1.0),
                )
            # The range the straight lines can actually be trusted over.
            valid = self._validity.get("valid_to") if self._validity else None
            if valid is not None and np.isfinite(valid) and valid < SCAN_SPAN:
                for sign in (-1.0, 1.0):
                    plot.line(
                        [sign * valid, sign * valid],
                        [-SCAN_SPAN * 1.05, SCAN_SPAN * 1.05],
                        pen=S.to_pen("#c05050", width=1.2, style="dash"),
                    )
        plot.set_range(
            x=(-SCAN_SPAN, SCAN_SPAN), y=(-SCAN_SPAN * 1.05, SCAN_SPAN * 1.05), padding=0.0
        )
        plot.grid(x=True, y=True, alpha=0.15)
        self._draw_marker()

    def _check_exact(self) -> None:
        """Re-fit at each held value and overlay the honest answer.

        The straight lines are exact only for a Gaussian posterior. Bounded
        parameters -- lifetimes, amplitude fractions, distances, FRET
        efficiencies -- routinely are not, and a weak component least of all, so
        this is the check that says whether the picture can be believed. It
        costs one fit per point, which is why it is a button.
        """
        if self._scan is None:
            return
        try:
            self._exact = self._engine.exact_conditional_scan(
                self._scan["name"], points=13, span=SCAN_SPAN
            )
            self._validity = (
                E.gaussian_validity(self._scan, self._exact) if self._exact is not None else None
            )
        except Exception as e:
            self._exact, self._validity = None, None
            self.readout = [N.Line(f"the re-fit check failed: {e}", N.MUTED)]
        if self._exact is not None:
            self._draw()

    def _draw_marker(self, *args) -> None:
        """Move the held-value marker and refresh the numbers underneath."""
        scan = self._scan
        if scan is None:
            return
        z = self.held_z
        held = scan["centre"] + z * scan["sd"]
        short = str(scan["name"]).split(":")[-1]
        self.held_text = f"{short} = {held:.6g}"

        if self._marker is None:
            self._marker = self.plot.vline(z, pen="#e0e0e0")
        else:
            try:
                self._marker.set_value(z)
            except Exception:
                self.plot.remove(self._marker)
                self._marker = self.plot.vline(z, pen="#e0e0e0")

        notes = []
        if self._validity is not None:
            valid = self._validity["valid_to"]
            colour = (
                N.GOOD
                if not np.isfinite(valid) or valid >= 2.0
                else N.FAIR
                if valid >= 1.0
                else N.BAD
            )
            notes.append(
                N.Line(f"\u25cf Re-fit check: {self._validity['verdict']}", colour, bold=True)
            )
            notes.append(
                N.Line(
                    f"(worst disagreement {self._validity['worst']:.2f}σ on "
                    f"{self._validity['worst_target'].split(':')[-1]}; dots are the "
                    "re-fitted truth)",
                    N.MUTED,
                )
            )
        notes.append(
            N.Line(
                "slope = correlation; the width is what the data still does not know "
                f"once {short} is pinned down",
                N.MUTED,
            )
        )
        table = N.Table(["parameter", "would be", "free", "r", "width"], bold=(1,))
        for target in scan["targets"]:
            mean = target["marginal"] + target["marginal_sd"] * target["correlation"] * z
            shrink = (
                1.0 - target["sd"] / target["marginal_sd"] if target["marginal_sd"] > 0 else 0.0
            )
            table.rows.append(
                [
                    str(target["name"]).split(":")[-1],
                    f"{mean:.6g} ± {target['sd']:.3g}",
                    f"{target['marginal']:.6g} ± {target['marginal_sd']:.3g}",
                    f"{target['correlation']:+.3f}",
                    f"{shrink:.0%} narrower",
                ]
            )
        notes.append(table)
        self.readout = notes
