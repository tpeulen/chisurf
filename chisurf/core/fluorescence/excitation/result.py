"""What an excitation-window detection found, and what a check of existing windows says.

One result shape for both alternation schemes:

* **PIE / nsALEX** -- the excitation pulses are in the *micro time* (TCSPC channels of
  ``resolution_s``, ``n_channels`` per sync period);
* **µs-ALEX** -- the alternation is in the *macro time*; the windows are phases of the alternation
  period (``n_channels`` macro-time ticks of ``resolution_s``).

Windows are half-open channel ranges ``[start, stop)`` in the units of the data they were detected
from, so :meth:`ExcitationWindows.windows_ns` and ``tttrlib.rescale_micro_time_ranges`` carry them to another
resolution or binning instead of silently mismatching.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import tttrlib

__all__ = [
    "ExcitationWindows",
    "Issue",
    "Pulse",
    "WindowCheck",
]

#: Outcomes of a detection.
KINDS = ("pie", "alex", "single", "unclear")
#: Severities of a check, mildest first.
SEVERITIES = ("ok", "info", "warning", "error")


@dataclasses.dataclass
class Pulse:
    """One excitation (a PIE pulse or an ALEX laser period) seen in the data.

    Attributes
    ----------
    rise : int
        Channel where the excitation starts (the pulse's rising edge, or the start of the laser-on
        phase of µs-ALEX).
    peak : int
        Channel of the maximum after the rise.
    core_stop : int
        First channel after the peak where the signal is below half its height: ``[rise,
        core_stop)`` is the part of the pulse a window boundary must not cut.
    excites : list of str
        Detectors that see light after this excitation (the others are dark).
    role : str
        ``"donor"`` (donor excitation), ``"acceptor"`` (acceptor excitation: the donor detectors
        are dark) or ``""`` when the data cannot tell.
    share : dict
        Per detector, the fraction of its background-corrected photons in this pulse's window.
    window : str
        Name of the window proposed for it.
    """

    rise: int
    peak: int
    core_stop: int
    excites: list[str] = dataclasses.field(default_factory=list)
    role: str = ""
    share: dict[str, float] = dataclasses.field(default_factory=dict)
    window: str = ""


@dataclasses.dataclass
class ExcitationWindows:
    """The excitation scheme a measurement shows and the windows proposed for it.

    Attributes
    ----------
    kind : str
        ``"pie"`` (two or more pulses in the micro time), ``"alex"`` (macro-time alternation),
        ``"single"`` (one excitation: a donor-only sample, or not an alternating measurement --
        windows cannot be placed, which is not an error) or ``"unclear"``.
    domain : str
        ``"micro"`` (windows in micro-time channels) or ``"macro"`` (phases of the alternation
        period in macro-time ticks).
    resolution_s : float
        Width of one channel (micro-time resolution, or macro-time tick for ALEX).
    n_channels : int
        Channels in the range (micro-time channels per sync period, or ticks per ALEX period).
    windows : dict
        ``{name: [start, stop)}`` in channels. Two excitations are ``prompt`` (donor excitation)
        and ``delayed`` (acceptor excitation).
    pulses : list of Pulse
    donor_detectors, acceptor_detectors : list of str
        Detectors found dark (donor) / lit (acceptor) under acceptor excitation.
    message : str
        One line for the user: what was seen, and what it means.
    notes : list of str
        Details and caveats (a window wrapping around the range end, a sync divider, ...).
    n_photons : int
        Photons the detection looked at.
    confidence : float
        Detection contrast (PIE: smallest pulse step in noise sigmas; ALEX: alternation contrast).
    """

    kind: str
    domain: str = "micro"
    resolution_s: float = 0.0
    n_channels: int = 0
    windows: dict[str, list[int]] = dataclasses.field(default_factory=dict)
    pulses: list[Pulse] = dataclasses.field(default_factory=list)
    donor_detectors: list[str] = dataclasses.field(default_factory=list)
    acceptor_detectors: list[str] = dataclasses.field(default_factory=list)
    message: str = ""
    notes: list[str] = dataclasses.field(default_factory=list)
    n_photons: int = 0
    confidence: float = 0.0

    @property
    def alternating(self) -> bool:
        """Two or more excitations were found: windows can be placed."""
        return self.kind in ("pie", "alex")

    def windows_ns(self) -> dict[str, list[float]]:
        """The windows in nanoseconds from the start of the range."""
        f = self.resolution_s * 1e9
        return {k: [v[0] * f, v[1] * f] for k, v in self.windows.items()}

    def windows_at(self, resolution_s: float) -> dict[str, list[int]]:
        """The windows in channels of another *resolution_s* (another binning of the same TAC)."""
        return tttrlib.rescale_micro_time_ranges(self.windows, self.resolution_s, resolution_s)

    def rescaled(self, resolution_s: float, n_channels: int | None = None) -> ExcitationWindows:
        """The same detection in channels of *resolution_s* (e.g. found on a coarse decay of 1024
        bins, expressed in the device's channels): windows and pulse positions converted."""
        if not self.resolution_s or not resolution_s:
            return dataclasses.replace(self)
        f = float(self.resolution_s) / float(resolution_s)
        n = int(n_channels) if n_channels else int(round(self.n_channels * f))

        def ch(x: int) -> int:
            return int(round(x * f)) % max(n, 1)

        out = dataclasses.replace(
            self,
            resolution_s=float(resolution_s),
            n_channels=n,
            windows={k: [int(round(v[0] * f)), min(int(round(v[1] * f)), n)]
                     for k, v in self.windows.items()},
            pulses=[dataclasses.replace(p, rise=ch(p.rise), peak=ch(p.peak),
                                        core_stop=ch(p.core_stop)) for p in self.pulses],
            notes=list(self.notes),
        )
        return out

    def setup_patch(self) -> dict:
        """What an Experiment setup takes over: the windows, and the channel width they are in
        (``tttr_reading.micro_time_resolution`` in ps), or the ALEX period."""
        if self.domain == "macro":
            return {
                "alex_windows": {k: list(v) for k, v in self.windows.items()},
                "alex_period_ticks": int(self.n_channels),
                "alex_period_s": float(self.n_channels * self.resolution_s),
            }
        return {
            "windows": {k: list(v) for k, v in self.windows.items()},
            "tttr_reading": {"micro_time_resolution": self.resolution_s * 1e12},
        }

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form (RPC, CLI ``--json``)."""
        d = dataclasses.asdict(self)
        d["windows_ns"] = self.windows_ns()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ExcitationWindows:
        """Inverse of :meth:`to_dict`."""
        fields = {f.name for f in dataclasses.fields(cls)}
        kw = {k: v for k, v in d.items() if k in fields}
        kw["pulses"] = [Pulse(**p) if isinstance(p, dict) else p for p in kw.get("pulses", [])]
        return cls(**kw)


@dataclasses.dataclass
class Issue:
    """One finding of a window check."""

    code: str
    severity: str
    message: str
    window: str = ""


@dataclasses.dataclass
class WindowCheck:
    """Existing windows held against what the data shows.

    Attributes
    ----------
    status : str
        The worst severity: ``"ok"``, ``"info"`` (nothing to change, e.g. one pulse only),
        ``"warning"`` (the windows do not match the data -- offer :attr:`proposal`) or ``"error"``
        (the windows cannot work, e.g. outside the data's channel range).
    issues : list of Issue
    detection : ExcitationWindows
    windows : dict
        The windows checked, in the data's channels (converted when their resolution was given).
    proposal : dict
        The detected windows in the data's channels (empty when nothing can be proposed).
    gates : dict
        The detectors' micro-time gates checked (``{detector: [[start, stop), ...]}``), in the
        data's channels.
    proposal_gates : dict
        Gates to take with :attr:`proposal`: the converted ones, a gate that hid a pulse or held
        no photons replaced by the whole range.
    """

    status: str
    issues: list[Issue]
    detection: ExcitationWindows
    windows: dict[str, list[int]] = dataclasses.field(default_factory=dict)
    proposal: dict[str, list[int]] = dataclasses.field(default_factory=dict)
    gates: dict[str, list[list[int]]] = dataclasses.field(default_factory=dict)
    proposal_gates: dict[str, list[list[int]]] = dataclasses.field(default_factory=dict)

    @property
    def mismatch(self) -> bool:
        """The windows should be looked at: offer the proposal."""
        return self.status in ("warning", "error")

    @property
    def summary(self) -> str:
        """One line: the verdict and its most severe reason."""
        if not self.issues:
            return f"Windows match the {self.detection.kind.upper()} pulses in the data."
        worst = max(self.issues, key=lambda i: SEVERITIES.index(i.severity))
        more = f" (+{len(self.issues) - 1} more)" if len(self.issues) > 1 else ""
        return worst.message + more

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form."""
        return {
            "status": self.status,
            "mismatch": self.mismatch,
            "summary": self.summary,
            "issues": [dataclasses.asdict(i) for i in self.issues],
            "detection": self.detection.to_dict(),
            "windows": self.windows,
            "proposal": self.proposal,
            "gates": self.gates,
            "proposal_gates": self.proposal_gates,
        }


