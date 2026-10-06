"""The µs-ALEX alternation step without a toolkit: detect the laser alternation, fold it into the micro-time, name
the gates.

The old *Burst Search Settings → Microscope* dialog asked for seven numbers (the alternation period, a phase shift,
four laser edges and a channel-flip flag). All seven are in the data: the period is the frequency at which the two
detectors alternate, the laser edges are the plateaus of the folded phase histogram, and the "flip" is which plateau
the donor detector is brighter in. After the fold (``tttrlib``'s ``alex_to_microtime``) a µs-ALEX measurement *is*
a PIE measurement and every later step is the ordinary burst pipeline.

:class:`AlexAlternationModel` holds what the step shows (the channel fields, the period, the two gates, the folded
phase histogram, the status lines) and does the work on a background thread: detection is a measurement of the
instrument (about 1.5 s for 3.8 M photons), the conversion writes one ``.pto`` container. The emtk view is
:class:`..gui.app.AlexAlternationGui`; the legacy Qt panel (:mod:`.alternation`) and the native hub
(:mod:`.native`) both drive this model. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

logger = logging.getLogger("chisurf.plugins.burst")

#: Name of the detector setup this step writes. Reused (overwritten) on every run, so a second measurement does
#: not litter the store with near-duplicates.
SETUP_NAME = "ALEX Suite (auto)"
#: Seconds a typed gate edge waits before the setup is republished (typing "3784" is four edits).
GATE_SETTLE_S = 0.4


def build_setup(windows: dict, donor, acceptor, period: int) -> dict:
    """Build a detector setup from the detected ALEX gates.

    The names are not free. ChiSurf's burst tables name a gated stream ``S {window} {detector}``, and everything
    that reads one (ndX's shipped MFD equations, the accurate-FRET column mapping, the shared conventions in
    :mod:`chisurf.core.fluorescence.burst.table`) recognises the Seidel vocabulary: excitation windows ``prompt``
    and ``delayed``, detectors ``green``, ``red`` and ``yellow``. So the four ALEX streams come out as

    ============  =========================  ==================
    ALEX stream   column                     meaning
    ============  =========================  ==================
    DD            ``S prompt green``         donor emission, donor excitation
    DA            ``S prompt red``           acceptor emission, donor excitation
    AA            ``S delayed yellow``       acceptor emission, acceptor excitation
    AD            ``S delayed green``        donor emission, acceptor excitation
    ============  =========================  ==================

    ``red`` and ``yellow`` are the *same physical detector* listed twice, once per excitation window (the Seidel
    convention), which makes a two-detector ALEX measurement readable by tools written for a three-detector MFD
    setup.

    Parameters
    ----------
    windows : dict
        ``{"green": (lo, hi), "red": (lo, hi)}`` in macro-time units of the folded phase.
    donor, acceptor : sequence of int
        Routing channels of the two detectors.
    period : int
        Alternation period in macro-time units.

    Returns
    -------
    dict
        The detector setup (``setup_name``, ``windows``, ``detectors``, ``tttr_reading``).
    """
    prompt = [int(round(windows["green"][0])), int(round(windows["green"][1]))]
    delayed = [int(round(windows["red"][0])), int(round(windows["red"][1]))]
    donor_chs = [int(c) for c in donor]
    acceptor_chs = [int(c) for c in acceptor]

    def detector(chs, window):
        return {"chs": list(chs), "micro_time_ranges": [list(window)], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}

    return {
        "setup_name": SETUP_NAME,
        "windows": {"prompt": prompt, "delayed": delayed},
        "detectors": {
            "green": detector(donor_chs, prompt),
            "red": detector(acceptor_chs, prompt),
            "yellow": detector(acceptor_chs, delayed),
        },
        "tttr_reading": {"file_type": "PTO", "micro_time_binning": 1, "excitation_period": int(period)},
    }


def parse_channels(text: str) -> list[int] | None:
    """Parse ``"0, 8"`` into ``[0, 8]``; ``"auto"`` (or empty) into ``None``.

    Raises
    ------
    ValueError
        If *text* is neither ``auto`` nor a list of integers.
    """
    stripped = str(text).strip().lower()
    if not stripped or stripped == "auto":
        return None
    parts = [p.strip() for p in stripped.replace(";", ",").split(",") if p.strip()]
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"{text!r} is not 'auto' or a list of integers") from None


def needs_conversion(path: Path) -> bool:
    """Whether a measurement still carries its alternation in the macro time.

    A measurement whose micro-time is already populated is either PIE data (nothing to fold) or a container this
    step produced earlier; folding it again would overwrite a real micro-time with a phase (the one way this step
    can destroy information), so it is checked before, not after. An unreadable file is not converted either.
    """
    from chisurf.core.fio.staging import open_tttr

    try:
        micro_times = np.asarray(open_tttr(str(path)).micro_times)
    except Exception as exc:  # noqa: BLE001 - unknown is not "needs folding"
        logger.warning(f"ALEX Suite: could not read {Path(path).name} to decide whether it needs converting - {exc}")
        return False
    return not (micro_times.size and int(micro_times.max()) > 0)


def phase_histogram(folded, period: int, donor_channels, acceptor_channels) -> dict[str, Any]:
    """Histogram the folded phase per detector (200 bins over one period).

    Per detector, not summed: the sum has two plateaus whatever the channel assignment is; it is the *swap* of
    which detector is brighter that says the assignment is right.
    """
    phase = np.asarray(folded.micro_times)
    routing = np.asarray(folded.routing_channels)
    edges = np.linspace(0, period, 201)
    donor, _ = np.histogram(phase[np.isin(routing, list(donor_channels))], bins=edges)
    acceptor, _ = np.histogram(phase[np.isin(routing, list(acceptor_channels))], bins=edges)
    return {
        "centres": 0.5 * (edges[:-1] + edges[1:]),
        "donor": donor,
        "acceptor": acceptor,
        "period": int(period),
    }


class AlexAlternationModel:
    """State and actions of the alternation step (the attributes :class:`..app.AlexAlternationGui` draws).

    Parameters
    ----------
    on_converted : callable, optional
        ``on_converted(setup, converted_paths)``: the conversion (or a later gate edit) produced a detector setup
        and the containers the rest of the pipeline should analyse. The hub adopts both.
    """

    def __init__(self, on_converted: Callable[[dict, list[Path]], None] | None = None) -> None:
        self.on_converted = on_converted
        #: Routing channels as typed: "auto" or "0, 8".
        self.donor_text = "auto"
        self.acceptor_text = "auto"
        #: Alternation period in macro-time units; 0 means "auto" (measure it).
        self.period: int = 0
        #: The two laser gates: ``{"green": [lo, hi], "red": [lo, hi]}`` or ``None``.
        self.windows: dict | None = None
        self.status_text = "No files yet - pick them in 2. Files."
        self.detail_text = ""
        self.detail_note = ""
        #: The folded phase histogram the plot draws (centres + one row per detector).
        self.phase_hist: dict = {}
        self.files: list[Path] = []
        self.converted: list[Path] = []
        self.result: dict | None = None
        #: What the last arrival decided: "convert", "pie" (already has a micro-time) or "" (nothing yet).
        self.decision = ""
        self._micro_suffix = ""
        self._thread: threading.Thread | None = None
        self._outcome: tuple[str, Any] | None = None
        self._gate_edit_at: float | None = None
        self._observers: list[Callable[[str], None]] = []

    # -- observers ------------------------------------------------------------------------------------------- #
    def add_observer(self, callback: Callable[[str], None]) -> None:
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        for callback in list(self._observers):
            callback(event)

    @property
    def running(self) -> bool:
        """Whether a detection or conversion is under way (Next waits for it)."""
        return self._thread is not None and self._thread.is_alive()

    # -- arrival --------------------------------------------------------------------------------------------- #
    def set_files(self, files, *, auto: bool = True) -> None:
        """Adopt the raw files chosen upstream and, with *auto*, act on them at once.

        A measurement whose alternation is still in the macro time (an empty micro-time) is detected and converted
        straight away: the step is optional, so Next walks past it without running anything, and a burst search on
        unconverted µs-ALEX data gates on a micro-time of zeros and finds nothing. Data that already has a
        micro-time (PIE / ns-ALEX, or a container this step wrote) is left alone.
        """
        files = [Path(p) for p in files or ()]
        if not files or (files == self.files and (self.result is not None or self.decision)):
            return
        self.files = files
        self.result = None
        self.converted = []
        self.detail_text = self.detail_note = ""
        self.phase_hist = {}
        if not auto:
            self.status_text = f"{len(files)} file(s). Press Detect alternation and convert."
            return
        if needs_conversion(files[0]):
            self.decision = "convert"
            self.status_text = f"{len(files)} file(s) with the alternation in the macro time - detecting and converting..."
            self.run(convert=True)
        else:
            self.decision = "pie"
            self.status_text = (
                f"{files[0].name} already has a micro-time (PIE / ns-ALEX, or converted before): nothing to convert. "
                "Press Next; or Detect only to check for an alternation anyway."
            )
        self.notify("files")

    # -- the action ------------------------------------------------------------------------------------------ #
    def run(self, *, convert: bool = True) -> bool:
        """Detect the alternation and, unless *convert* is false, convert, on a background thread.

        Returns whether the job started (``False``: no files, a bad channel field, or a job already running; the
        reason is in :attr:`status_text`).
        """
        if self.running:
            return False
        if not self.files:
            self.status_text = "No files - pick them in 2. Files first."
            return False
        try:
            donor = parse_channels(self.donor_text)
            acceptor = parse_channels(self.acceptor_text)
        except ValueError as exc:
            self.status_text = f"Channels: {exc}"
            return False
        if (donor is None) != (acceptor is None):
            self.status_text = (
                "Give both channel assignments or neither - 'auto' decides them together, from which detector goes "
                "dark under acceptor excitation."
            )
            return False
        manual_period = int(self.period) or None
        reuse = convert and self._can_reuse_detection(manual_period, donor, acceptor)
        files = list(self.files)
        windows = self._windows_from_state()

        def work():
            try:
                if reuse:
                    from chisurf.plugins.burst.alex_suite.api.convert import alex_to_pto

                    container = alex_to_pto(files, alex_period=int(self.result["period"]))
                    self._outcome = ("converted", (container, windows))
                else:
                    from chisurf.plugins.burst.alex_suite.api.convert import detect_and_convert

                    outcome = detect_and_convert(
                        files,
                        donor_channels=donor,
                        acceptor_channels=acceptor,
                        period=manual_period,
                        dry_run=not convert,
                    )
                    self._outcome = ("detected", (outcome, convert))
            except Exception as exc:  # noqa: BLE001 - shown in the step
                self._outcome = ("failed", exc)

        self._outcome = None
        self.status_text = "Converting with the detection on screen..." if reuse else (
            "Detecting the alternation and converting..." if convert else "Detecting the alternation..."
        )
        self._thread = threading.Thread(target=work, name="alex-alternation", daemon=True)
        self._thread.start()
        return True

    def wait(self, timeout: float = 120.0) -> None:
        """Block until the running job has finished and apply its result (scripts and tests)."""
        if self._thread is not None:
            self._thread.join(timeout)
        self.poll()

    def poll(self) -> bool:
        """Apply a finished job's result and a settled gate edit (called every frame); whether anything changed."""
        changed = False
        if self._outcome is not None and not self.running:
            kind, payload = self._outcome
            self._outcome = None
            self._thread = None
            if kind == "failed":
                logger.warning(f"ALEX Suite: alternation detection failed - {payload}")
                self.status_text = f"Detection failed: {payload}"
                self.detail_text = ""
            elif kind == "converted":
                container, windows = payload
                self._finish_conversion([Path(container)], [], windows)
            else:
                self._apply_detection(*payload)
            changed = True
            self.notify("updated")
        if self._gate_edit_at is not None and time.monotonic() - self._gate_edit_at >= GATE_SETTLE_S:
            self._gate_edit_at = None
            self.apply_gates()
            changed = True
        return changed

    def _can_reuse_detection(self, period, donor, acceptor) -> bool:
        """Whether the detection on screen still describes what would be run (the gates shape only the setup)."""
        if self.result is None or self.converted:
            return False
        if period is not None and int(period) != int(self.result["period"]):
            return False
        for given, detected in ((donor, "donor_channels"), (acceptor, "acceptor_channels")):
            if given is not None and list(given) != list(self.result[detected]):
                return False
        return True

    def _apply_detection(self, outcome: dict, convert: bool) -> None:
        self.result = outcome
        donor, acceptor = outcome["donor_channels"], outcome["acceptor_channels"]
        # An assignment the user never typed is exactly what they have to be able to check.
        self.donor_text = ", ".join(str(c) for c in donor)
        self.acceptor_text = ", ".join(str(c) for c in acceptor)
        period = int(outcome["period"])
        self.period = period
        self.windows = {name: [int(round(b[0])), int(round(b[1]))] for name, b in outcome["windows"].items()}
        folded = outcome.get("folded")
        if folded is not None:
            self.phase_hist = phase_histogram(folded, period, donor, acceptor)
        self._report(period, outcome["confidence"], outcome["windows"], folded, outcome.get("channel_contrast"))
        if not convert:
            self.status_text = (
                f"Detected from {self.files[0].name}. Check the plot and the gates, then press Detect alternation "
                "and convert."
            )
            return
        self._finish_conversion(list(outcome.get("converted") or []), list(outcome.get("failed") or []), None)

    def _finish_conversion(self, converted: list[Path], failed: list, windows: dict | None) -> None:
        self.converted = [Path(p) for p in converted]
        if self.result is not None:
            self.result["converted"] = list(self.converted)
            self.result["failed"] = list(failed)
        if not self.converted:
            self.status_text = "Detection succeeded but no file could be converted - see the log."
            return
        self._publish(windows or self._windows_from_state() or self.result["windows"])
        note = f" ({len(failed)} failed - see the log)" if failed else ""
        self.status_text = (
            f"Converted {len(self.files)} file(s) into {self.converted[0].name}{note}; detector setup "
            f"“{SETUP_NAME}” is the one the burst search uses. Press Next."
        )
        logger.info(self.status_text)

    def setup(self, windows: dict | None = None) -> dict:
        """The detector setup of the current detection and gates (empty before a detection)."""
        if self.result is None:
            return {}
        return build_setup(
            windows or self._windows_from_state() or self.result["windows"],
            self.result["donor_channels"],
            self.result["acceptor_channels"],
            int(self.result["period"]),
        )

    def _publish(self, windows: dict) -> None:
        if callable(self.on_converted):
            self.on_converted(self.setup(windows), list(self.converted))

    # -- the gates ------------------------------------------------------------------------------------------- #
    def set_gate(self, name: str, lo: int, hi: int) -> None:
        """Commit one gate edit (typed edge or dragged band: the same edit); the setup follows once typing settles.

        Nothing is reconverted: the fold uses the period alone.
        """
        if self.windows is None:
            return
        self.windows[name] = [int(lo), int(hi)]
        self._gate_edit_at = time.monotonic()

    def _windows_from_state(self) -> dict | None:
        """The two gates, or ``None`` if either is empty or inverted."""
        if not self.windows:
            return None
        result = {}
        for name in ("green", "red"):
            lo, hi = (int(v) for v in (self.windows.get(name) or [0, 0]))
            if lo >= hi:
                return None
            result[name] = [lo, hi]
        return result

    def apply_gates(self) -> None:
        """Republish the detector setup from the gates as they now stand (the containers stay)."""
        if self.result is None:
            return
        windows = self._windows_from_state()
        if windows is None:
            self.status_text = "Each gate needs a start below its end - the setup was not changed."
            return
        self.result["windows"] = windows
        if self.converted:
            self._publish(windows)
        self._write_detail(self.result["period"], self.result["confidence"], windows)
        self.status_text = (
            f"Gates {windows['green'][0]}–{windows['green'][1]} and {windows['red'][0]}–{windows['red'][1]}"
            + (f" published as “{SETUP_NAME}”. Press Next." if self.converted else " set.")
        )

    # -- the report ------------------------------------------------------------------------------------------ #
    def _write_detail(self, period, confidence, windows) -> None:
        g_lo, g_hi = windows["green"]
        r_lo, r_hi = windows["red"]
        self.detail_text = (
            f"Period {period}{self._micro_suffix} · green {g_lo:.0f}–{g_hi:.0f} · red {r_lo:.0f}–{r_hi:.0f} · "
            f"contrast {confidence:.0f}×"
        )

    def _report(self, period, confidence, windows, folded, contrast=None) -> None:
        try:
            resolution = float(folded.header.macro_time_resolution)
        except Exception:  # noqa: BLE001 - no header, no seconds
            resolution = 0.0
        self._micro_suffix = f" = {period * resolution * 1e6:.1f} µs" if resolution else ""
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
            else f" The donor and acceptor channels were assigned from the data: the donor detector is "
            f"{contrast:.0%} as bright under acceptor excitation, which is the only thing that settles which is which."
        )
        self.detail_note = (
            f"Alternation period {period} macro-time units{self._micro_suffix}. Donor-excitation gate "
            f"{g_lo:.0f}–{g_hi:.0f}, acceptor-excitation gate {r_lo:.0f}–{r_hi:.0f} (both trimmed at the laser rise "
            f"and fall). Contrast {confidence:.0f}× — {verdict}.{channels}"
        )


__all__ = [
    "GATE_SETTLE_S",
    "SETUP_NAME",
    "AlexAlternationModel",
    "build_setup",
    "needs_conversion",
    "parse_channels",
    "phase_histogram",
]
