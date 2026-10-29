"""The one pre-flight every PIE analysis runs before it uses micro-time windows.

Burst selection, the burst analyses that read prompt/delayed streams and any other consumer of
a setup's windows call :func:`windows_preflight` on the measurement they are about to analyse.
It runs the shared detection and check (:func:`~.measure.check_setup`) on the micro time only
(the windows are micro-time ranges; a µs-ALEX file is the Alternation step's business) and turns
the verdict into one line for the analysis's warnings -- the same words everywhere. A donor-only
measurement gives a short note, never a warning: one pulse cannot say where the windows belong.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .measure import check_setup, detect_windows, histograms_from_tttr, setup_detectors
from .result import WindowCheck

__all__ = ["WindowsPreflightMixin", "apply_check", "windows_message", "windows_preflight"]

#: Findings about detector gates only.
_GATE_CODES = {"gate_outside_range", "gate_misses_pulse", "gate_empty"}
#: Findings that may concern gates as much as windows.
_EITHER_CODES = {"resolution_mismatch", "single_pulse", "unclear"}
#: Photons the pre-flight reads: the shape of the decays, not the whole file.
PREFLIGHT_PHOTONS = 1_000_000


def windows_preflight(
    tttr: Any,
    windows: Mapping | None,
    *,
    detectors: Mapping | None = None,
    tttr_reading: Mapping | None = None,
    setup: Mapping | None = None,
) -> WindowCheck | None:
    """Check *windows* against the micro time of *tttr*; ``None`` when there is nothing to check
    (no windows and no micro time).

    Parameters
    ----------
    tttr : tttrlib.TTTR or path
        The measurement about to be analysed.
    windows : mapping
        ``{name: [start, stop]}`` in micro-time channels.
    detectors, tttr_reading : mapping, optional
        The setup's detectors (name the histograms) and reading routine (the channel width the
        windows are in).
    setup : mapping, optional
        A whole setup instead of the three parts.
    """
    s = dict(setup or {})
    if windows is not None:
        s["windows"] = {k: [int(v[0]), int(v[1])] for k, v in dict(windows).items()}
    if detectors is not None:
        s["detectors"] = dict(detectors)
    if tttr_reading is not None:
        s["tttr_reading"] = dict(tttr_reading)
    try:
        det = detect_windows(tttr, setup=s, kind="pie", max_photons=PREFLIGHT_PHOTONS)
    except Exception:  # noqa: BLE001 - a stream that cannot be histogrammed: nothing to say
        return None
    if det.n_channels <= 8 and not s.get("windows"):
        return None
    hists, _, _ = histograms_from_tttr(tttr, setup_detectors(s) or None,
                                       max_photons=PREFLIGHT_PHOTONS)
    return check_setup(s, detection=det, histograms=hists)


def windows_message(check: WindowCheck | None) -> str | None:
    """One line for an analysis's warnings, or ``None`` when the windows hold the pulses."""
    if check is None:
        return None
    det = check.detection
    if not det.alternating:
        if det.kind == "single" and check.windows:
            return ("One excitation pulse in the micro time (donor-only or not PIE): the PIE "
                    "windows were not checked against the data.")
        return None
    if not check.mismatch:
        return None
    found = check.proposal or check.detection.windows
    proposal = ", ".join(f"{k} {v[0]}–{v[1]}" for k, v in found.items())
    fixed = {d: g for d, g in check.proposal_gates.items() if g != check.gates.get(d)}
    if fixed:
        proposal += ("; " if proposal else "") + "gates " + ", ".join(
            f"{d} " + " ".join(f"{a}–{b}" for a, b in g) for d, g in fixed.items())
    codes = {i.code for i in check.issues}
    what = ("Detector gates" if codes & _GATE_CODES and not codes - _GATE_CODES - _EITHER_CODES
            or (not check.windows and check.gates) else "PIE windows")
    return (f"{what} do not match the data: {check.summary} Detected windows: {proposal} "
            "(Excitation Windows / setup editor: Auto-detect).")


def apply_check(setup: Mapping, check: WindowCheck) -> dict:
    """*setup* with what *check* proposes: the windows, the detector gates, and the channel width
    they are in -- what *Use detected windows* writes everywhere. Unchanged when nothing is
    proposed (one pulse, unclear)."""
    out = dict(setup)
    if not check.proposal and not (check.mismatch and check.proposal_gates):
        return out
    det = check.detection
    if det.domain == "macro":
        out["alex_windows"] = {k: list(v) for k, v in check.proposal.items()}
        out["alex_period_s"] = det.n_channels * det.resolution_s
        return out
    if check.proposal:
        out["windows"] = {k: [int(v[0]), int(v[1])] for k, v in check.proposal.items()}
    elif check.windows:  # a gate-only fix keeps the windows, in the data's channels
        out["windows"] = {k: [int(v[0]), int(v[1])] for k, v in check.windows.items()}
    if check.proposal_gates:
        detectors = {k: dict(v) for k, v in (out.get("detectors") or {}).items()}
        for name, ranges in check.proposal_gates.items():
            if name in detectors:
                detectors[name]["micro_time_ranges"] = [list(r) for r in ranges]
        out["detectors"] = detectors
    out["tttr_reading"] = {**(out.get("tttr_reading") or {}),
                           "micro_time_resolution": det.resolution_s * 1e12}
    return out


class WindowsPreflightMixin:
    """The pre-flight as a tool model holds it: the latest check, its line, the offer.

    Every tool that uses a setup's windows mixes this in, so the warning, the *Use detected
    windows* button and what pressing it does are the same everywhere. The host implements
    :meth:`preflight_setup` (the setup the tool will use: ``windows``, ``detectors``,
    ``tttr_reading``) and :meth:`take_preflight_setup` (store the corrected setup), calls
    :meth:`run_windows_preflight` with the measurement it is about to analyse, and declares in its
    ``view.json``::

        {"type": "info", "source": "windows_check_text",
         "hidden_when": {"attr": "windows_check_quiet", "equals": true}, ...},
        {"type": "button_row", "hidden_when": {"attr": "windows_check_offer", "equals": false},
         "buttons": [{"label": "Use detected windows", "action": "use_detected_windows", ...}]}
    """

    #: The latest check (``None`` before a measurement was looked at).
    windows_check: WindowCheck | None = None

    def preflight_setup(self) -> dict:  # pragma: no cover - the host's
        """The setup the tool uses (``windows``, ``detectors``, ``tttr_reading``)."""
        raise NotImplementedError

    def take_preflight_setup(self, setup: dict) -> None:  # pragma: no cover - the host's
        """Store *setup* (the windows, gates and channel width the user took)."""
        raise NotImplementedError

    def run_windows_preflight(self, tttr: Any) -> str | None:
        """Check the tool's setup against *tttr*; the line for its warnings (``None``: fine)."""
        try:
            self.windows_check = windows_preflight(tttr, None, setup=self.preflight_setup())
        except Exception:  # noqa: BLE001 - a check that cannot run says nothing
            self.windows_check = None
        return windows_message(self.windows_check)

    def windows_check_text(self) -> str:
        """The verdict line (empty when the windows hold the pulses)."""
        return windows_message(self.windows_check) or ""

    @property
    def windows_check_quiet(self) -> bool:
        """Nothing to say about the windows."""
        return not self.windows_check_text()

    @property
    def windows_check_offer(self) -> bool:
        """The windows do not match and detected ones can be taken."""
        c = self.windows_check
        return bool(c is not None and c.mismatch and (c.proposal or c.proposal_gates))

    def use_detected_windows(self) -> bool:
        """Take the detected windows (and gates, and their channel width) into the tool's setup."""
        c = self.windows_check
        if c is None or not (c.proposal or (c.mismatch and c.proposal_gates)):
            return False
        self.take_preflight_setup(apply_check(self.preflight_setup(), c))
        self.windows_check = None
        return True
