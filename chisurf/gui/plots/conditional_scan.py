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
from qtpy import QtCore, QtWidgets

import chisurf.core.fitting
from chisurf.core.fitting import engine as E
from chisurf.gui.chiplot import Plot as ChiPlot
from chisurf.gui.chiplot import style as S
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

#: Slider steps per standard deviation.
STEPS_PER_SD = 20


class ConditionalScanPlot(Plot):
    """Hold one parameter at a value and read off the rest, interactively."""

    name = "What-if"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Build the selector, the slider and the plot."""
        super().__init__(fit)
        self.fit = fit
        self._scan = None
        self._engine = None
        self._full_names = []

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Fix"))
        self.parameter_box = QtWidgets.QComboBox()
        self.parameter_box.currentIndexChanged.connect(self._rebuild)
        # No stretch: a parameter name is short, and the slider is the control
        # the user actually drags.
        self.parameter_box.setMinimumWidth(120)
        self.parameter_box.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        top.addWidget(self.parameter_box, 0)
        top.addSpacing(8)
        top.addWidget(QtWidgets.QLabel("at"))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(int(-SCAN_SPAN * STEPS_PER_SD))
        self.slider.setMaximum(int(SCAN_SPAN * STEPS_PER_SD))
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._draw_marker)
        top.addWidget(self.slider, 1)
        self.held_label = QtWidgets.QLabel("")
        self.held_label.setMinimumWidth(170)
        self.held_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        top.addWidget(self.held_label, 0)
        # The straight lines are exact only for a Gaussian posterior, which a
        # bounded parameter or a weak component is not. This checks by
        # re-fitting, which costs a fit per point -- hence a button.
        self.check_button = QtWidgets.QToolButton()
        self.check_button.setText("🔍 Check (re-fit)")
        self.check_button.setToolTip(
            "Re-fit at each held value instead of assuming the posterior is "
            "Gaussian, and report how far the straight lines can be trusted."
        )
        self.check_button.clicked.connect(self._check_exact)
        top.addWidget(self.check_button, 0)
        self.layout.addLayout(top)

        self.plot = ChiPlot()
        self.plot.set_labels(
            bottom="held value (standard deviations from the optimum)",
            left="shift in the other parameters (their own sd)",
        )
        self.layout.addWidget(self.plot.canvas.widget(), 1)

        self.readout = QtWidgets.QLabel("")
        self.readout.setWordWrap(True)
        self.readout.setTextFormat(1)  # Qt::RichText
        self.layout.addWidget(self.readout, 0)

        self._marker = None
        self._exact = None
        self._validity = None

    # -- data ---------------------------------------------------------------

    def _degrade(self, message: str) -> None:
        """Drop every trace of the previous update and say why there is nothing.

        The combo box is cleared with its signals blocked: a bare ``clear()``
        emits ``currentIndexChanged``, which re-enters :meth:`_rebuild` and --
        with the *previous* engine and parameter list still in place -- redraws
        the old sweep on top of *message*, so a fit with one free parameter kept
        showing a full what-if table for parameters that were no longer free.
        """
        self._scan = None
        self._engine = None
        self._full_names = []
        self._exact = None
        self._validity = None
        self._marker = None
        self.parameter_box.blockSignals(True)
        self.parameter_box.clear()
        self.parameter_box.blockSignals(False)
        self.held_label.setText("")
        self.plot.clear()
        # ``clear()`` drops the curves but keeps the title, which would go on
        # naming the parameter that is no longer being fixed.
        self.plot.set_title(None)
        self.readout.setText(message)

    def update(self, *args, **kwargs) -> None:
        """Rebuild the engine and the parameter list, then redraw."""
        super().update(*args, **kwargs)
        try:
            engine = E.GaussianEngine(self.fit).add_all_targets().run()
            form = engine.form()
        except Exception as e:
            self._degrade(f"<i>no usable curvature: {e}</i>")
            return
        if form is None or len(form.names) < 2:
            self._degrade("<i>needs a converged fit with at least two free parameters</i>")
            return

        self._engine = engine
        names = [str(n) for n in form.names]
        current = self.parameter_box.currentText()
        self.parameter_box.blockSignals(True)
        self.parameter_box.clear()
        self.parameter_box.addItems([n.split(":")[-1] for n in names])
        self._full_names = names
        if current in [n.split(":")[-1] for n in names]:
            self.parameter_box.setCurrentIndex([n.split(":")[-1] for n in names].index(current))
        self.parameter_box.blockSignals(False)
        self._rebuild()

    def _rebuild(self, *args) -> None:
        """Recompute the sweep for the selected parameter and redraw."""
        if self._engine is None or not self._full_names:
            return
        index = max(0, self.parameter_box.currentIndex())
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
            self.readout.setText("<i>nothing left to condition on</i>")
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
        self.check_button.setEnabled(False)
        self.check_button.setText("re-fitting…")
        QtWidgets.QApplication.processEvents()
        try:
            self._exact = self._engine.exact_conditional_scan(
                self._scan["name"], points=13, span=SCAN_SPAN
            )
            self._validity = (
                E.gaussian_validity(self._scan, self._exact) if self._exact is not None else None
            )
        except Exception as e:
            self._exact, self._validity = None, None
            self.readout.setText(f"<i>the re-fit check failed: {e}</i>")
        finally:
            self.check_button.setEnabled(True)
            self.check_button.setText("🔍 Check (re-fit)")
        if self._exact is not None:
            self._draw()

    def _draw_marker(self, *args) -> None:
        """Move the held-value marker and refresh the numbers underneath."""
        scan = self._scan
        if scan is None:
            return
        z = self.slider.value() / float(STEPS_PER_SD)
        held = scan["centre"] + z * scan["sd"]
        short = str(scan["name"]).split(":")[-1]
        self.held_label.setText(f"<b>{short} = {held:.6g}</b>")

        if self._marker is None:
            self._marker = self.plot.vline(z, pen="#e0e0e0")
        else:
            # Moving the existing marker rather than adding one: redrawing on
            # every slider step would otherwise leave a line behind each time.
            try:
                self._marker.set_value(z)
            except Exception:
                self.plot.remove(self._marker)
                self._marker = self.plot.vline(z, pen="#e0e0e0")

        rows = []
        if self._validity is not None:
            valid = self._validity["valid_to"]
            colour = (
                "#3c8f5c"
                if not np.isfinite(valid) or valid >= 2.0
                else "#b07020"
                if valid >= 1.0
                else "#b03030"
            )
            rows.append(
                f"<span style='color:{colour}'><b>&#9679; Re-fit check:</b> "
                f"{self._validity['verdict']}</span> "
                f"<span style='color:#888'>(worst disagreement "
                f"{self._validity['worst']:.2f}&sigma; on "
                f"{self._validity['worst_target'].split(':')[-1]}; dots are the "
                f"re-fitted truth)</span><br>"
            )
        rows += [
            "<span style='color:#888'>slope = correlation; the width is what "
            "the data still does not know once "
            f"{short} is pinned down</span>",
            "<table cellspacing='6'><tr>"
            "<th align='left'>parameter</th><th align='left'>would be</th>"
            "<th align='left'>free</th><th align='left'>r</th>"
            "<th align='left'>width</th></tr>",
        ]
        for target in scan["targets"]:
            mean = target["marginal"] + target["marginal_sd"] * target["correlation"] * z
            shrink = (
                1.0 - target["sd"] / target["marginal_sd"] if target["marginal_sd"] > 0 else 0.0
            )
            rows.append(
                "<tr>"
                f"<td>{str(target['name']).split(':')[-1]}</td>"
                f"<td><b>{mean:.6g} &plusmn; {target['sd']:.3g}</b></td>"
                f"<td>{target['marginal']:.6g} &plusmn; "
                f"{target['marginal_sd']:.3g}</td>"
                f"<td>{target['correlation']:+.3f}</td>"
                f"<td>{shrink:.0%} narrower</td>"
                "</tr>"
            )
        rows.append("</table>")
        self.readout.setText("".join(rows))
