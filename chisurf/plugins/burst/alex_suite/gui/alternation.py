"""Step 3 — turn µs-ALEX alternation into a normal PIE measurement.

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

The panel is rendered by the EMTK app in :mod:`.app` (:class:`AlexAlternationApp`);
this class holds the state it renders and the workflow logic behind it.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.navigation import find_status_reporter

logger = logging.getLogger("chisurf.plugins.burst")

#: Name of the detector setup this step writes. Reused (overwritten) on every
#: run, so a second measurement does not litter the store with near-duplicates.
SETUP_NAME = "ALEX Suite (auto)"


class AlexAlternationPanel(QtWidgets.QWidget):
    """Detect the ALEX alternation, fold it into the micro-time, name the gates.

    Nothing has to be typed for the common case — one button measures all seven
    of the old dialog's numbers — but everything it decides is *editable*, which
    is the difference between a detector and a black box. The period and the two
    laser gates are numbers in the controls dock, and the gates are also the
    draggable bands on the plot: drag a band or type an edge, they are the same
    edit. A gate change republishes the detector setup and reconverts nothing,
    because the fold into the micro-time depends on the period alone.

    The plot is what says whether the answer is right: two plateaus, the donor
    brighter in one of them.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the alternation panel: state + the EMTK app that renders it."""
        super().__init__(parent)
        self._workflow = parent
        self._result: dict | None = None
        self._files: list[pathlib.Path] = []
        self._converted: list[pathlib.Path] = []

        # ── the state the EMTK app renders ────────────────────────────────
        #: Routing channels as typed: "auto" or "0, 8".
        self.donor_text = "auto"
        self.acceptor_text = "auto"
        #: Alternation period in macro-time units; 0 means "auto" (measure it).
        self.period: int = 0
        #: The two laser gates: {"green": [lo, hi], "red": [lo, hi]} or None.
        self.windows: dict | None = None
        self.status_text = "No files yet — pick them in step 1."
        self.detail_text = ""
        self.detail_note = ""
        #: " = 100.0 µs" for the current period, or "" if the file carried no
        #: macro-time resolution. Kept so a gate edit can rewrite the summary
        #: line without re-opening the file.
        self._micro_suffix = ""
        #: The folded phase histogram the plot draws: centres + one row per
        #: detector, computed once per detection rather than per frame.
        self.phase_hist: dict = {}

        #: Arms the automatic detection *after* the panel has painted.
        self._autorun_timer = QtCore.QTimer(self)
        self._autorun_timer.setSingleShot(True)
        self._autorun_timer.timeout.connect(self._autorun)
        #: Applies a gate edit after typing settles, rather than per keystroke:
        #: typing "3784" is four edits, and each one would republish the setup
        #: to every downstream panel.
        self._apply_timer = QtCore.QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(400)
        self._apply_timer.timeout.connect(self._apply_manual_windows)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, AlexAlternationApp

        self.app = AlexAlternationApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

    def _refresh(self) -> None:
        """Repaint the canvas after a state change."""
        if hasattr(self, "host"):
            self.host.update()

    # ── the gates ────────────────────────────────────────────────────────

    def set_gate(self, name: str, lo: int, hi: int) -> None:
        """Commit one gate edit (typed edge or dragged band — the same edit).

        Neither reconverts anything: the fold uses only the period, so a gate
        change rewrites the published detector setup once typing settles.
        """
        if self.windows is None:
            return
        self.windows[name] = [int(lo), int(hi)]
        self._apply_timer.start()

    def _windows_from_state(self) -> dict | None:
        """Read the two gates, or ``None`` if either is empty or inverted."""
        windows = self.windows
        if not windows:
            return None
        result = {}
        for name in ("green", "red"):
            bounds = windows.get(name) or [0, 0]
            lo, hi = int(bounds[0]), int(bounds[1])
            if lo >= hi:
                return None
            result[name] = [lo, hi]
        return result

    def _apply_manual_windows(self) -> None:
        """Republish the detector setup from the gates as they now stand.

        Only the setup: the containers written by :meth:`run` stay as they are,
        because the fold that made them used the period and not the gates.
        """
        if self._result is None:
            return
        windows = self._windows_from_state()
        if windows is None:
            self.status_text = "Each gate needs a start below its end — the setup was not changed."
            self._refresh()
            return
        self._result["windows"] = windows
        setup = build_setup(
            windows,
            self._result["donor_channels"],
            self._result["acceptor_channels"],
            self._result["period"],
        )
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            adopt(setup, self._converted)
        self._write_detail(self._result["period"], self._result["confidence"], windows)
        self.status_text = (
            f"Gates {windows['green'][0]}\u2013{windows['green'][1]} and "
            f"{windows['red'][0]}\u2013{windows['red'][1]} published as "
            f"\u201c{SETUP_NAME}\u201d. Next \u25b6"
        )
        self._refresh()

    # ── workflow hand-off ───────────────────────────────────────────────

    def set_files(self, files) -> None:
        """Adopt the raw files chosen upstream, and measure them straight away.

        Detection is not a decision the user makes — it is a measurement of the
        instrument, and every number it produces is shown for checking. So
        arriving at this step with files runs it, rather than asking someone to
        press a button whose answer is already determined. It is armed on a
        zero-timer so the panel paints first: the measurement takes about a
        second and a half, and running it inside the panel's own construction
        would show a grey rectangle for that time instead of the step.
        """
        previous = list(self._files)
        self._files = [pathlib.Path(p) for p in files]
        if not self._files:
            return
        if self._files == previous and self._result is not None:
            return  # same measurement, already detected -- nothing to redo
        self.status_text = f"{len(self._files)} file(s) — detecting the alternation…"
        self.detail_text = ""
        self._refresh()
        self._autorun_timer.start(0)

    def _autorun(self) -> None:
        """Measure the alternation on arrival, and convert if it is µs-ALEX.

        Detecting without converting was the wrong half to automate. This step
        is declared *optional*, and the shell never runs an optional step for
        you — so **Next walks straight past it**, and the burst search then runs
        on files whose alternation is still in the macro time: gates that select
        no photons, every per-detector count zero, and a container written per
        file out of unconverted data. Two people in a row met that trap, which
        is one more than it deserved.

        Converting here is safe because the decision is not a judgement:
        :func:`detect_and_convert` refuses below ``MIN_CONFIDENCE``, so data
        that does not alternate is left alone, and :meth:`_needs_conversion`
        skips a measurement whose micro-time is already populated — PIE, or a
        container this step produced earlier. It is also cheap: 1.5 s for a
        3.8 M-photon file.
        """
        if self._result is not None or not self._files:
            return
        self.run(convert=self._needs_conversion())

    def _needs_conversion(self) -> bool:
        """Whether these files still carry their alternation in the macro time.

        A measurement whose micro-time is already populated is either PIE data
        (nothing to fold) or a container this step has already produced. Folding
        it again would overwrite a real micro-time with a phase — the one way
        this step can destroy information — so it is checked before, not after.
        """
        from chisurf.core.fio.staging import open_tttr

        try:
            tttr = open_tttr(str(self._files[0]))
            micro_times = np.asarray(tttr.micro_times)
        except Exception as exc:
            logger.warning(
                f"ALEX Suite: could not read {self._files[0].name} to decide "
                f"whether it needs converting — {exc}"
            )
            return False
        if micro_times.size and int(micro_times.max()) > 0:
            logger.info(
                f"ALEX Suite: {self._files[0].name} already has a micro-time; "
                "detecting only, not converting."
            )
            return False
        return True

    def result(self) -> dict | None:
        """Return the last detection result, or ``None`` if it has not run."""
        return self._result

    # ── the one action ──────────────────────────────────────────────────

    def run(self, *, convert: bool = True) -> None:
        """Detect the alternation and, unless ``convert`` is false, convert.

        The two halves are separable on purpose. **Detection is a measurement**
        of the instrument: it opens the first file, finds the period, the
        channel assignment and the gates, and writes nothing. **Conversion**
        folds every file and writes a container — minutes of work and a new file
        on disk. So arriving at the step detects (see :meth:`set_files`) and the
        button converts; nobody has to press anything to see what the data says,
        and nothing is written until they ask.
        """
        if not self._files:
            self.status_text = "No files — pick them in step 1 first."
            self._refresh()
            return
        try:
            donor = _channels(self.donor_text)
            acceptor = _channels(self.acceptor_text)
        except ValueError as exc:
            self.status_text = f"Channels: {exc}"
            self._refresh()
            return
        if (donor is None) != (acceptor is None):
            self.status_text = (
                "Give both channel assignments or neither — 'auto' decides them "
                "together, from which detector goes dark under acceptor excitation."
            )
            self._refresh()
            return

        from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert
        from chisurf.plugins.tttr.ptu_alex_creator import core

        reporter = find_status_reporter(self)
        task = (
            reporter.begin_task(
                "ALEX: detecting the alternation…", len(self._files) if convert else 0
            )
            if reporter
            else None
        )

        def report(done, total, what):
            if task is not None:
                task.setValue(done)
                task.setLabelText(
                    f"ALEX: embedding {total} file(s) into one .pto — {what}…"
                    if done < total
                    else f"ALEX: wrote {what}"
                )

        # A typed period overrides the measurement; 0 is the input's "auto".
        manual_period = int(self.period) or None
        # Arriving at the step already measured this file. If nothing that feeds
        # the fold has changed since, converting must not measure it again --
        # detection is the expensive half (a spectrum and an integer scan over
        # millions of photons), and re-running it to get an answer already on
        # screen is the whole of the wait.
        if convert and self._can_reuse_detection(manual_period, donor, acceptor):
            self._convert_detected()
            return
        try:
            outcome = detect_and_convert(
                self._files,
                donor_channels=donor,
                acceptor_channels=acceptor,
                period=manual_period,
                progress=report,
                dry_run=not convert,
            )
        except Exception as exc:
            logger.warning(f"ALEX Suite: alternation detection failed — {exc}")
            self.status_text = f"Detection failed: {exc}"
            self.detail_text = ""
            self._refresh()
            return
        finally:
            if task is not None:
                task.close()

        self._result = outcome
        # Show what was decided: an assignment the user never typed is exactly
        # the thing they have to be able to check.
        donor = outcome["donor_channels"]
        acceptor = outcome["acceptor_channels"]
        self.donor_text = ", ".join(str(c) for c in donor)
        self.acceptor_text = ", ".join(str(c) for c in acceptor)
        period = outcome["period"]
        self._converted = list(outcome["converted"])
        # Detecting *is* the request to re-measure, so the numbers are
        # overwritten even if they were edited by hand. Adjusting them
        # afterwards is the normal order, and that edit survives, because
        # nothing re-runs on its own.
        self.period = int(period)
        self.windows = {
            name: [int(round(bounds[0])), int(round(bounds[1]))]
            for name, bounds in outcome["windows"].items()
        }
        # The detection folded the first file to find the gates; the plot draws
        # that same stream rather than opening and folding it a second time.
        folded = outcome.get("folded")
        if folded is None:
            first = self._files[0]
            folded = core.apply_alex(
                core.load(str(first), core.resolve_filetype("Auto", str(first))), period, 0
            )
        self._store_phase(folded, period)
        self._report(
            period,
            outcome["confidence"],
            outcome["windows"],
            folded,
            outcome.get("channel_contrast"),
        )

        setup = build_setup(outcome["windows"], donor, acceptor, period)
        if not convert:
            # Detected only. The gates are on screen to be checked and the setup
            # is not published yet: publishing would point the rest of the
            # pipeline at containers that do not exist.
            self.status_text = (
                f"Detected from {self._files[0].name}. Check the plot and the "
                "gates, then press 🚦 to convert."
            )
            self._refresh()
            return
        self._publish(setup, outcome["converted"], outcome["failed"])

    def _can_reuse_detection(self, period, donor, acceptor) -> bool:
        """Whether the detection on screen still describes what would be run.

        The gates are deliberately *not* part of this: they shape the published
        setup, not the fold, so editing one must not cost a re-detection.
        """
        if self._result is None or self._converted:
            return False
        if period is not None and int(period) != int(self._result["period"]):
            return False
        for given, detected in ((donor, "donor_channels"), (acceptor, "acceptor_channels")):
            if given is not None and list(given) != list(self._result[detected]):
                return False
        return True

    def _convert_detected(self) -> None:
        """Fold and embed every file using the detection already on screen."""
        from chisurf.plugins.burst.alex_suite.api.convert import alex_to_pto

        outcome = self._result
        period = int(outcome["period"])
        reporter = find_status_reporter(self)
        task = (
            reporter.begin_task(f"ALEX: embedding {len(self._files)} file(s) into one .pto…", 0)
            if reporter
            else None
        )
        try:
            container = alex_to_pto(self._files, alex_period=period)
        except Exception as exc:
            logger.warning(f"ALEX Suite: conversion failed — {exc}")
            self.status_text = f"Conversion failed: {exc}"
            self._refresh()
            return
        finally:
            if task is not None:
                task.close()

        outcome["converted"] = [container]
        outcome["failed"] = []
        self._converted = [container]
        windows = self._windows_from_state() or outcome["windows"]
        setup = build_setup(
            windows, outcome["donor_channels"], outcome["acceptor_channels"], period
        )
        self._publish(setup, [container], [])

    def _publish(self, setup: dict, converted, failed) -> None:
        """Save the detector setup and hand the converted files downstream."""
        # The setup goes to the setup step through the workflow, not into a
        # selector here: that step *is* where a setup is chosen, and a second
        # selector on this panel would be a second answer to the same question.
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            adopt(setup, converted)
        n = len(converted)
        if not n:
            self.status_text = "Detection succeeded but no file could be converted — see the log."
            self._refresh()
            return
        note = f" ({len(failed)} failed — see the log)" if failed else ""
        message = (
            f"Converted {n} file(s) to .pto{note}; detector setup "
            f"“{SETUP_NAME}” is now the one the burst search uses. Next ▶"
        )
        self.status_text = message
        self._refresh()
        # The shell leaves the *last* task caption on its status bar, so without
        # this the window would still read "converting…" after it had finished.
        logger.info(message)

    def _write_detail(self, period, confidence, windows) -> None:
        """Write the one-line summary of period, gates and contrast.

        Separate from :meth:`_report` because a gate edit has to rewrite this
        line without re-opening the file the macro-time resolution came from.
        """
        g_lo, g_hi = windows["green"]
        r_lo, r_hi = windows["red"]
        self.detail_text = (
            f"Period {period}{self._micro_suffix} · green {g_lo:.0f}–{g_hi:.0f} · "
            f"red {r_lo:.0f}–{r_hi:.0f} · contrast {confidence:.0f}×"
        )

    def _report(self, period, confidence, windows, folded, contrast=None) -> None:
        """Show the detected numbers, in seconds as well as macro-time units."""
        try:
            resolution = float(folded.header.macro_time_resolution)
        except Exception:
            resolution = 0.0
        micro = f" = {period * resolution * 1e6:.1f} µs" if resolution else ""
        self._micro_suffix = micro
        verdict = (
            "a clear alternation"
            if confidence > 50
            else "a weak alternation; check the channel assignment, or this may not be µs-ALEX data"
        )
        g_lo, g_hi = windows["green"]
        r_lo, r_hi = windows["red"]
        self._write_detail(period, confidence, windows)
        channels = (
            ""
            if contrast is None
            else f" The donor and acceptor channels were assigned from the data: "
            f"the donor detector is {contrast:.0%} as bright under acceptor "
            f"excitation, which is the only thing that settles which is which."
        )
        self.detail_note = (
            f"Alternation period {period} macro-time units{micro}. Donor-excitation "
            f"gate {g_lo:.0f}–{g_hi:.0f}, acceptor-excitation gate {r_lo:.0f}–{r_hi:.0f} "
            f"(both trimmed at the laser rise and fall). Contrast {confidence:.0f}× — "
            f"{verdict}.{channels}"
        )

    def _store_phase(self, folded, period: int) -> None:
        """Histogram the folded phase per detector for the plot.

        Per detector, not summed: the sum has two plateaus whatever the channel
        assignment is, and it is the *swap* between which detector is brighter
        that says the assignment is right.
        """
        phase = np.asarray(folded.micro_times)
        routing = np.asarray(folded.routing_channels)
        edges = np.linspace(0, period, 201)
        centres = 0.5 * (edges[:-1] + edges[1:])
        result = self._result or {}
        donor_chs = list(result.get("donor_channels") or [])
        acceptor_chs = list(result.get("acceptor_channels") or [])
        donor_counts, _ = np.histogram(phase[np.isin(routing, donor_chs)], bins=edges)
        acceptor_counts, _ = np.histogram(phase[np.isin(routing, acceptor_chs)], bins=edges)
        self.phase_hist = {
            "centres": centres,
            "donor": donor_counts,
            "acceptor": acceptor_counts,
            "period": int(period),
        }


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
            "green": {
                "chs": donor_chs,
                "micro_time_ranges": [prompt],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "red": {
                "chs": acceptor_chs,
                "micro_time_ranges": [prompt],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "yellow": {
                "chs": acceptor_chs,
                "micro_time_ranges": [delayed],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
        },
        "tttr_reading": {
            "file_type": "PTO",
            "micro_time_binning": 1,
            "excitation_period": int(period),
        },
    }


def _channels(text: str) -> list[int] | None:
    """Parse ``"0, 8"`` into ``[0, 8]``; ``"auto"`` (or empty) into ``None``."""
    stripped = str(text).strip().lower()
    if not stripped or stripped == "auto":
        return None
    parts = [p.strip() for p in stripped.replace(";", ",").split(",") if p.strip()]
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"{text!r} is not 'auto' or a list of integers") from None
