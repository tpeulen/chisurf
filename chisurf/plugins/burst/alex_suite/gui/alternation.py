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
        #: The setup this panel last handed the workflow, so reflecting the
        #: workflow's choice back into the combo does not re-publish it.
        self._published_setup = ""
        #: True while this panel is driving the combo itself.
        self._setting_combo = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # One line here; the explanation is the tooltip, and the long version is
        # behind the ? button (help.md). A panel whose top third is prose is a
        # panel nobody reads.
        intro = QtWidgets.QLabel(
            "<b>µs-ALEX only</b> — already PIE / ns-ALEX? Skip this step.", self)
        intro.setToolTip(
            "In µs-ALEX the lasers alternate in time, so which laser was on is "
            "in the photon's macro-time. This step measures the alternation and "
            "folds it into the micro-time, after which the measurement is an "
            "ordinary PIE one and every later step is the normal burst "
            "pipeline.\n\nIn PIE / ns-ALEX that information is already in the "
            "micro-time, so there is nothing to fold — pick your detector setup "
            "above and go on to the burst search."
        )
        layout.addWidget(intro)

        # The setup selector belongs here, not only inside the burst-search
        # step's Filter Settings where every other tool hides it. This is the
        # step that *decides* the channel definition, so it is where someone
        # asks "which setup am I using?" -- and someone whose data is already
        # PIE, who skips the detection entirely, still needs to pick one.
        from chisurf.gui.widgets.setup_selector import SetupSelector

        setup_row = QtWidgets.QHBoxLayout()
        setup_row.setContentsMargins(0, 0, 0, 0)
        setup_row.addWidget(QtWidgets.QLabel("Detector setup", self))
        self.setup_selector = SetupSelector(
            self, placeholder="— none yet; press Detect to make one —",
            loader=_merged_setups)
        self.setup_selector.setToolTip(
            "The detector setup every later step uses: which routing channels "
            "are the donor and acceptor, and which micro-time window is which "
            "excitation.\n\nDetecting writes one called “ALEX Suite (auto)” "
            "and selects it. Already PIE data? Pick your own setup here and "
            "skip the detection."
        )
        self.setup_selector.setupChanged.connect(self._on_setup_chosen)
        setup_row.addWidget(self.setup_selector, 1)
        layout.addLayout(setup_row)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        self.donor_edit = QtWidgets.QLineEdit("auto")
        self.donor_edit.setToolTip(
            "Routing channels of the donor ('green') detector, comma separated.\n"
            "'auto' works it out from the data: under acceptor excitation the "
            "donor detector sees essentially nothing, and nothing else about the "
            "sample changes that."
        )
        self.acceptor_edit = QtWidgets.QLineEdit("auto")
        self.acceptor_edit.setToolTip(
            "Routing channels of the acceptor ('red') detector, comma separated.\n"
            "'auto' works it out from the data."
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

    def _on_setup_chosen(self, name: str) -> None:
        """Publish a hand-picked setup as the one the workflow uses.

        The path for data that is already PIE: the user never presses Detect, so
        nothing else would ever set the workflow's channel definition and every
        later step would fall back to whatever setup it last saw.
        """
        # Repopulating the combo emits a change for whatever lands in it first,
        # which would publish an unrelated setup as the workflow's the moment
        # this panel refreshed itself.
        if self._setting_combo or not name or name == self._published_setup:
            return
        setup = dict(self.setup_selector.current_setup_dict() or {})
        if not setup:
            return
        setup.setdefault("setup_name", name)
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            self._published_setup = name
            adopt(setup, [])
        self.status_label.setText(
            f"Using detector setup “{name}”. "
            "Press Detect as well if this is µs-ALEX data."
        )

    def show_setup(self, name: str) -> None:
        """Reflect the workflow's current setup in the selector."""
        self._published_setup = name
        self._setting_combo = True
        try:
            self.setup_selector.refresh()
            self.setup_selector.set_current(name)
        except Exception:
            logger.warning(f"ALEX Suite: could not show the setup {name!r}")
        finally:
            self._setting_combo = False

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
        if (donor is None) != (acceptor is None):
            self.status_label.setText(
                "Give both channel assignments or neither — 'auto' decides them "
                "together, from which detector goes dark under acceptor excitation."
            )
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
        # Show what was decided: an assignment the user never typed is exactly
        # the thing they have to be able to check.
        donor = outcome["donor_channels"]
        acceptor = outcome["acceptor_channels"]
        self.donor_edit.setText(", ".join(str(c) for c in donor))
        self.acceptor_edit.setText(", ".join(str(c) for c in acceptor))
        period = outcome["period"]
        # Re-fold the first file only for the picture; the conversion above
        # already used these numbers on every file.
        first = self._files[0]
        folded = core.apply_alex(
            core.load(str(first), core.resolve_filetype("Auto", str(first))), period, 0)
        self._plot_phase(folded, outcome["windows"], donor, acceptor, period)
        self._report(period, outcome["confidence"], outcome["windows"], folded,
                     outcome.get("channel_contrast"))

        setup = build_setup(outcome["windows"], donor, acceptor, period)
        self._publish(setup, outcome["converted"], outcome["failed"])

    def _publish(self, setup: dict, converted, failed) -> None:
        """Save the detector setup and hand the converted files downstream."""
        adopt = getattr(self._workflow, "adopt_alex_conversion", None)
        if callable(adopt):
            self._published_setup = SETUP_NAME
            adopt(setup, converted)
        self.show_setup(SETUP_NAME)
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

    def _report(self, period, confidence, windows, folded, contrast=None) -> None:
        """Show the detected numbers, in seconds as well as macro-time units."""
        try:
            resolution = float(folded.header.macro_time_resolution)
        except Exception:
            resolution = 0.0
        micro = f" = {period * resolution * 1e6:.1f} µs" if resolution else ""
        verdict = (
            "a clear alternation" if confidence > 50 else
            "a weak alternation; check the channel assignment, or this may not "
            "be µs-ALEX data"
        )
        g_lo, g_hi = windows["green"]
        r_lo, r_hi = windows["red"]
        self.detail_label.setText(
            f"<b>Period</b> {period}{micro} &nbsp;·&nbsp; "
            f"<b>green</b> {g_lo:.0f}–{g_hi:.0f} &nbsp;·&nbsp; "
            f"<b>red</b> {r_lo:.0f}–{r_hi:.0f} &nbsp;·&nbsp; "
            f"<b>contrast</b> {confidence:.0f}×"
        )
        channels = (
            "" if contrast is None else
            f"\n\nThe donor and acceptor channels were assigned from the data: "
            f"the donor detector is {contrast:.0%} as bright under acceptor "
            f"excitation, which is the only thing that settles which is which."
        )
        self.detail_label.setToolTip(
            f"Alternation period {period} macro-time units{micro}.\n"
            f"Donor-excitation gate {g_lo:.0f}–{g_hi:.0f}, acceptor-excitation "
            f"gate {r_lo:.0f}–{r_hi:.0f} (both trimmed at the laser rise and "
            f"fall).\nContrast {confidence:.0f}x — {verdict}.{channels}"
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


def _merged_setups(db_path=None) -> dict:
    """Every saved detector setup, from *both* stores.

    There are two, and they are not the same one: the RPC store
    (``detector_setups.*``) writes the settings JSON, while the pickers read
    through the wizard's loader, which reads MMFDB and — once MMFDB is in use —
    never falls back to that JSON. A setup written to one is then invisible in
    the other, so this step could publish a setup the combo beside it did not
    list. Merging on read is the workaround; the split is recorded in
    ``okf/references/known-issues.md``.

    MMFDB wins on a name collision: it is the store the rest of the application
    reads, so showing the JSON's copy of a name would misrepresent what the
    other tools will use.
    """
    setups: dict = {}
    last_used = ""
    from chisurf.core.data_io.detector_setups import load_detector_setups as json_load

    for load, kwargs in (
        (json_load, {}),
        (_wizard_loader(), {"db_path": db_path, "skip_migration": True}),
    ):
        if load is None:
            continue
        try:
            data = load(**{k: v for k, v in kwargs.items() if v is not None}) or {}
        except Exception:
            continue
        found = data.get("setups")
        if isinstance(found, dict):
            setups.update(found)
        last_used = data.get("last_used") or last_used
    return {"setups": setups, "last_used": last_used}


def _wizard_loader():
    """Return the wizard's MMFDB-aware loader, or ``None`` if unimportable."""
    try:
        from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
            load_detector_setups,
        )
    except Exception:
        return None
    return load_detector_setups


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
