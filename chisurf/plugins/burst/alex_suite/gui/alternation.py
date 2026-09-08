"""Step 2 — turn µs-ALEX alternation into a normal PIE measurement.

This is the whole of the old *Burst Search Settings → Microscope* dialog, which
asked for seven numbers: the alternation period, a phase shift, four laser
on/off edges and a channel-flip flag. Getting any of them wrong produced a
complete, plausible-looking analysis with the wrong answer, and nothing in the
program said so.

All seven are in the data. The period is the frequency at which the two
detectors alternate, the laser edges are the plateaus of the folded phase
histogram, and the "flip" is just which plateau the donor detector is brighter
in. So this step has one button.

What it produces is the point: after folding the alternation into the micro-time
(``tttrlib``'s ``alex_to_microtime``), a µs-ALEX file *is* a PIE file — the two
excitation periods are micro-time windows like any other — and every later step
is the ordinary ChiSurf burst pipeline, writing the ordinary ``.pto`` container
and ``.bur`` companions. Nothing downstream knows this data was ALEX.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui.chiplot import Plot
from chisurf.gui.widgets.navigation import find_status_reporter

logger = logging.getLogger("chisurf.plugins.burst")

#: Name of the detector setup this step writes. Reused (overwritten) on every
#: run, so a second measurement does not litter the store with near-duplicates.
SETUP_NAME = "ALEX Suite (auto)"


class AlexAlternationPanel(QtWidgets.QWidget):
    """Detect the ALEX alternation, fold it into the micro-time, name the gates.

    The panel is deliberately three controls and a button. The detected numbers
    are shown — they have to be checkable — but nothing has to be typed for the
    common case, and the plot is what says whether the answer is right: two
    plateaus, the donor brighter in one of them.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the alternation panel."""
        super().__init__(parent)
        self._workflow = parent
        self._result: dict | None = None
        self._files: list[pathlib.Path] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        intro = QtWidgets.QLabel(
            "<b>µs-ALEX only.</b> The lasers alternate in time here, not within "
            "one pulse period. This step finds the alternation, folds it into "
            "the micro-time and names the two excitation gates — after which "
            "the data is an ordinary PIE measurement and every later step is "
            "the normal burst pipeline.<br>"
            "<i>Already PIE / ns-ALEX (pulsed interleaved excitation)? "
            "Skip this step.</i>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.donor_edit = QtWidgets.QLineEdit("0")
        self.donor_edit.setToolTip(
            "Routing channels of the donor ('green') detector, comma separated."
        )
        self.acceptor_edit = QtWidgets.QLineEdit("1")
        self.acceptor_edit.setToolTip(
            "Routing channels of the acceptor ('red') detector, comma separated."
        )
        form.addRow("Donor channels", self.donor_edit)
        form.addRow("Acceptor channels", self.acceptor_edit)
        layout.addLayout(form)

        button_row = QtWidgets.QHBoxLayout()
        # The shell's Next / ⏩ trigger the child named ``toolAction_run`` — that
        # is how a step joins the walk of the whole pipeline.
        self.run_button = QtWidgets.QToolButton(self)
        self.run_button.setObjectName("toolAction_run")
        self.run_button.setText("🚦 Detect alternation and convert")
        self.run_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.run_button.clicked.connect(self.run)
        button_row.addWidget(self.run_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.detail_label = QtWidgets.QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(self.detail_label)

        self.plot = Plot(self)
        self.plot.set_labels(bottom="ALEX phase (macro-time units)", left="Photons")
        # Default (top-left) placement: a negative x offset anchors the legend's
        # *left* edge that far from the right, so it hangs off the plot and the
        # labels are clipped. Above the plateaus there is empty space anyway.
        self.plot.legend()
        layout.addWidget(self.plot, 1)

        self.status_label = QtWidgets.QLabel("No files yet — pick them in step 1.")
        layout.addWidget(self.status_label)

    # ── workflow hand-off ───────────────────────────────────────────────

    def set_files(self, files) -> None:
        """Adopt the raw files chosen upstream."""
        self._files = [pathlib.Path(p) for p in files]
        if self._files:
            self.status_label.setText(
                f"{len(self._files)} file(s) ready. Press Detect."
            )

    def result(self) -> dict | None:
        """Return the last detection result, or ``None`` if it has not run."""
        return self._result

    # ── the one action ──────────────────────────────────────────────────

    def run(self) -> None:
        """Detect the period, fold it, name the gates and convert every file."""
        if not self._files:
            self.status_label.setText("No files — pick them in step 1 first.")
            return
        try:
            donor = _channels(self.donor_edit.text())
            acceptor = _channels(self.acceptor_edit.text())
        except ValueError as exc:
            self.status_label.setText(f"Channels: {exc}")
            return

        from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert
        from chisurf.plugins.tttr.ptu_alex_creator import core

        reporter = find_status_reporter(self)
        task = reporter.begin_task(
            "ALEX: detecting the alternation…", len(self._files)) if reporter else None

        def report(index, total, name):
            if task is not None:
                task.setValue(index)
                task.setLabelText(f"ALEX: converting {name} ({index + 1}/{total})…")

        try:
            outcome = detect_and_convert(
                self._files,
                donor_channels=donor, acceptor_channels=acceptor,
                progress=report,
            )
        except Exception as exc:
            logger.warning(f"ALEX Suite: alternation detection failed — {exc}")
            self.status_label.setText(f"Detection failed: {exc}")
            self.detail_label.setText("")
            return
        finally:
            if task is not None:
                task.close()

        self._result = outcome
        period = outcome["period"]
        # Re-fold the first file only for the picture; the conversion above
        # already used these numbers on every file.
        first = self._files[0]
        folded = core.apply_alex(
            core.load(str(first), core.resolve_filetype("Auto", str(first))), period, 0)
        self._plot_phase(folded, outcome["windows"], donor, acceptor, period)
        self._report(period, outcome["confidence"], outcome["windows"], folded)

        setup = build_setup(outcome["windows"], donor, acceptor, period)
        self._publish(setup, outcome["converted"], outcome["failed"])

    def _publish(self, setup: dict, converted, failed) -> None:
        """Save the detector setup and hand the converted files downstream."""
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            adopt(setup, converted)
        n = len(converted)
        if not n:
            self.status_label.setText(
                "Detection succeeded but no file could be converted — see the log."
            )
            return
        note = f" ({len(failed)} failed — see the log)" if failed else ""
        message = (
            f"Converted {n} file(s) to .pto{note}; detector setup "
            f"“{SETUP_NAME}” is now the one the burst search uses. Next ▶"
        )
        self.status_label.setText(message)
        # The shell leaves the *last* task caption on its status bar, so without
        # this the window would still read "converting…" after it had finished.
        logger.info(message)

    def _report(self, period, confidence, windows, folded) -> None:
        """Show the detected numbers, in seconds as well as macro-time units."""
        try:
            resolution = float(folded.header.macro_time_resolution)
        except Exception:
            resolution = 0.0
        micro = f" = {period * resolution * 1e6:.1f} µs" if resolution else ""
        verdict = (
            "clear alternation" if confidence > 50 else
            "weak alternation — check the channel assignment, "
            "or this may not be µs-ALEX data"
        )
        g_lo, g_hi = windows["green"]
        r_lo, r_hi = windows["red"]
        self.detail_label.setText(
            f"<b>Period</b> {period}{micro} &nbsp;·&nbsp; "
            f"<b>green gate</b> {g_lo:.0f}–{g_hi:.0f} &nbsp;·&nbsp; "
            f"<b>red gate</b> {r_lo:.0f}–{r_hi:.0f} &nbsp;·&nbsp; "
            f"contrast {confidence:.0f}× ({verdict})"
        )

    def _plot_phase(self, folded, windows, donor, acceptor, period) -> None:
        """Plot the folded phase per detector, with the two gates shaded.

        Per detector, not summed: the sum has two plateaus whatever the channel
        assignment is, and it is the *swap* between which detector is brighter
        that says the assignment is right.
        """
        self.plot.clear()
        phase = np.asarray(folded.micro_times)
        rc = np.asarray(folded.routing_channels)
        edges = np.linspace(0, period, 201)
        centres = 0.5 * (edges[:-1] + edges[1:])
        for name, channels, colour in (
            # Short names: the legend is anchored inside the plot, and a long
            # one is clipped at the right edge rather than wrapped.
            ("donor", donor, "#2ca02c"),
            ("acceptor", acceptor, "#d62728"),
        ):
            counts, _ = np.histogram(phase[np.isin(rc, list(channels))], bins=edges)
            self.plot.line(centres, counts, pen=colour, name=name)
        for name, colour in (("green", "#2ca02c55"), ("red", "#d6272855")):
            lo, hi = windows[name]
            self.plot.region((lo, hi), brush=colour, movable=False)
        self.plot.autoscale()


def build_setup(windows: dict, donor, acceptor, period: int) -> dict:
    """Build a detector setup from the detected ALEX gates.

    The names are not free. ChiSurf's burst tables name a gated stream
    ``S {window} {detector}``, and everything that reads one — ndX's shipped MFD
    equations, the accurate-FRET column mapping, the shared conventions in
    :mod:`chisurf.core.fluorescence.burst.table` — recognises the Seidel
    vocabulary: excitation windows ``prompt`` and ``delayed``, detectors
    ``green``, ``red`` and ``yellow``. So that is what this writes, and the four
    ALEX streams come out under the names every reader already knows:

    ============  =========================  ==================
    ALEX stream   column                     meaning
    ============  =========================  ==================
    DD            ``S prompt green``         donor emission, donor excitation
    DA            ``S prompt red``           acceptor emission, donor excitation
    AA            ``S delayed yellow``       acceptor emission, acceptor excitation
    AD            ``S delayed green``        donor emission, acceptor excitation
    ============  =========================  ==================

    ``red`` and ``yellow`` are the *same physical detector* listed twice, once
    per excitation window — the Seidel convention, and what makes a two-detector
    ALEX measurement readable by tools written for a three-detector MFD setup.
    Naming the windows after the colours instead (``green``/``red``) produced a
    table whose columns no shipped equation matched, so the E-S step showed
    nothing while the burst files sat right there.
    """
    prompt = [int(round(windows["green"][0])), int(round(windows["green"][1]))]
    delayed = [int(round(windows["red"][0])), int(round(windows["red"][1]))]
    donor_chs = [int(c) for c in donor]
    acceptor_chs = [int(c) for c in acceptor]
    return {
        "setup_name": SETUP_NAME,
        "windows": {"prompt": prompt, "delayed": delayed},
        "detectors": {
            "green": {"chs": donor_chs, "micro_time_ranges": [prompt],
                      "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
            "red": {"chs": acceptor_chs, "micro_time_ranges": [prompt],
                    "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
            "yellow": {"chs": acceptor_chs, "micro_time_ranges": [delayed],
                       "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        },
        "tttr_reading": {
            "file_type": "PTO",
            "micro_time_binning": 1,
            "excitation_period": int(period),
        },
    }


def _channels(text: str) -> list[int]:
    """Parse ``"0, 8"`` into ``[0, 8]``."""
    parts = [p.strip() for p in str(text).replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("give at least one routing channel")
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"{text!r} is not a list of integers") from None
