"""Hold existing excitation windows against what the data shows.

:func:`check_windows` is the one check every PIE / ALEX consumer calls (the Record tool during a
run, the setup editor, burst selection and the analyses that read prompt/delayed windows): the
same findings and severities everywhere, and a proposal the user may take -- never applied
silently.

Findings (:class:`~.result.Issue` codes):

``resolution_mismatch`` (warning)
    The windows were defined in channels of another width (another TAC range or binning); they
    are converted before the other checks, and the converted windows are what is proposed.
``outside_range`` (error / warning)
    A window starts beyond the data's channel range (error), or ends far beyond it (warning).
``no_windows`` (warning)
    The data clearly alternates and there are no windows.
``pulse_uncovered`` (warning)
    A detected pulse rises in no window.
``window_cuts_pulse`` (warning)
    A window boundary lies inside a pulse (between its rise and its half-height decay).
``window_mixes_pulses`` (warning)
    One window holds two excitation pulses: its photons mix donor and acceptor excitation.
``windows_swapped`` (warning)
    ``prompt`` holds the acceptor-excitation pulse and ``delayed`` the donor's.
``window_empty`` (warning)
    A window holds almost no photons.
``alex_period_mismatch`` (warning)
    µs-ALEX: the windows were made for another alternation period.
``gate_outside_range`` (error), ``gate_misses_pulse`` / ``gate_empty`` (warning)
    A detector's micro-time gate starts beyond the data, holds none of the excitations the
    detector sees (a gate keeping one of them on purpose is fine), or holds almost none of its
    photons; the gate is proposed opened to the whole range.
``single_pulse`` / ``unclear`` (info)
    One excitation pulse (donor-only sample, or not PIE) or no clear pulse: nothing is checked
    against pulses; nothing is proposed.
"""

from __future__ import annotations

import numpy as np
from tttrlib import rescale_micro_time_ranges

from .result import (
    SEVERITIES,
    ExcitationWindows,
    Issue,
    WindowCheck,
)

__all__ = ["check_windows"]

#: A window with less than this fraction of the photons is reported empty.
EMPTY_FRACTION = 0.005


def _inside(x: int, lo: int, hi: int, n: int) -> bool:
    """Whether channel *x* is in the circular range ``[lo, hi)``."""
    if lo <= hi:
        return lo <= x < hi
    return x >= lo or x < hi


def _strictly_inside(b: int, lo: int, hi: int, n: int) -> bool:
    """Whether a boundary *b* falls strictly inside the circular span ``(lo, hi)``."""
    span = (hi - lo) % n
    off = (b - lo) % n
    return 0 < off < span


def check_windows(
    windows: dict | None,
    detection: ExcitationWindows,
    *,
    windows_resolution_s: float | None = None,
    histogram: np.ndarray | None = None,
    gates: dict | None = None,
    histograms: dict | None = None,
    alex_period_ticks: float | None = None,
    gate_channels: dict | None = None,
) -> WindowCheck:
    """Check *windows* against *detection* (what the data shows).

    Parameters
    ----------
    windows : dict
        ``{name: [start, stop)}`` -- the setup's windows (micro-time channels for PIE, phase ticks
        for ALEX).
    detection : ExcitationWindows
        From :func:`~.measure.detect_windows` / :func:`~.pie.detect_pie_windows`.
    windows_resolution_s : float, optional
        The channel width the windows were defined at. When it differs from the data's, the
        windows are converted (and that is reported).
    histogram : array, optional
        Photons per channel of the data (all detectors), for the empty-window check.
    gates : dict, optional
        The detectors' micro-time gates ``{detector: [[start, stop], ...]}`` (a setup's
        ``detectors.*.micro_time_ranges``), in the same channels as *windows*: converted with them,
        and checked -- a gate beyond the range, a gate that holds none of the pulses its detector
        sees, a gate that holds almost none of its detector's photons.
    histograms : dict, optional
        Per-detector photons per channel (the names :attr:`Pulse.excites` uses), for the gates.
    gate_channels : dict, optional
        ``{detector: routing channels}``. Detectors that share channels and split the micro time
        between them by their gates (PIE's ``red`` / ``yellow`` on one acceptor detector) hold a
        pulse together: a pulse outside one detector's gate is fine when a sibling's gate holds it.
    alex_period_ticks : float, optional
        µs-ALEX: the alternation period the windows were made for, in macro-time ticks. A period
        off the detected one by more than 0.5 % is reported (the windows then fold another
        cycle) and the detected period and windows are proposed.

    Returns
    -------
    WindowCheck
    """
    issues: list[Issue] = []
    res, n = float(detection.resolution_s), int(detection.n_channels)
    win = {str(k): [int(v[0]), int(v[1])] for k, v in (windows or {}).items()}
    unit = "phase ticks" if detection.domain == "macro" else "micro-time channels"
    gate = {str(d): [[int(r[0]), int(r[1])] for r in (rs or [])]
            for d, rs in (gates or {}).items() if rs}
    if gate and windows_resolution_s and res > 0 and abs(windows_resolution_s / res - 1) > 0.01:
        gate = rescale_micro_time_ranges(gate, windows_resolution_s, res)
        if not win:
            issues.append(Issue(
                "resolution_mismatch", "warning",
                f"The detector gates are in {windows_resolution_s * 1e12:.4g} ps channels, the "
                f"data in {res * 1e12:.4g} ps: converted.",
            ))
    if win and windows_resolution_s and res > 0:
        ratio = float(windows_resolution_s) / res
        if abs(ratio - 1.0) > 0.01:
            conv = rescale_micro_time_ranges(win, windows_resolution_s, res)
            issues.append(
                Issue(
                    "resolution_mismatch",
                    "warning",
                    f"The windows are in {windows_resolution_s * 1e12:.4g} ps channels, the data in "
                    f"{res * 1e12:.4g} ps: converted ("
                    + ", ".join(f"{k} {win[k][0]}–{win[k][1]} → {conv[k][0]}–{conv[k][1]}"
                                for k in win)
                    + ").",
                )
            )
            win = conv
    for name, (lo, hi) in win.items():
        if n and lo >= n:
            issues.append(
                Issue(
                    "outside_range",
                    "error",
                    f"Window {name} starts at {lo}, beyond the data's {n} {unit}: it is empty.",
                    name,
                )
            )
        elif n and hi > n * 1.02 + 1:
            issues.append(
                Issue(
                    "outside_range",
                    "warning",
                    f"Window {name} ends at {hi}, beyond the data's {n} {unit}.",
                    name,
                )
            )
    if histogram is not None and win:
        h = np.asarray(histogram, dtype=float).ravel()
        total = float(h.sum())
        if total > 0:
            for name, (lo, hi) in win.items():
                frac = float(h[max(lo, 0) : max(min(hi, h.size), 0)].sum()) / total
                if frac < EMPTY_FRACTION and not any(
                    i.window == name and i.severity == "error" for i in issues
                ):
                    issues.append(
                        Issue(
                            "window_empty",
                            "warning",
                            f"Window {name} ({lo}–{hi}) holds {100 * frac:.2g} % of the photons.",
                            name,
                        )
                    )
    proposal_gates = (_check_gates(gate, detection, histograms, issues, unit, gate_channels)
                      if gate else {})
    if (detection.domain == "macro" and detection.alternating and alex_period_ticks
            and abs(float(alex_period_ticks) / n - 1.0) > 0.005):
        issues.append(Issue(
            "alex_period_mismatch", "warning",
            f"The alternation period is {n} ticks ({n * res * 1e6:.2f} µs), the setup's "
            f"{float(alex_period_ticks):.0f} ({float(alex_period_ticks) * res * 1e6:.2f} µs): its "
            "windows fold another cycle.",
        ))
        return _verdict(issues, detection, win, dict(detection.windows), gate, proposal_gates)
    if not detection.alternating:
        code = "single_pulse" if detection.kind == "single" else "unclear"
        issues.append(Issue(code, "info", detection.message + " Windows not checked."))
        return _verdict(issues, detection, win, {}, gate, proposal_gates)
    if not win and gate:  # a gate-only consumer (imaging, MFD streams): its gates are the check
        return _verdict(issues, detection, win, {}, gate, proposal_gates)
    if not win:
        issues.append(
            Issue(
                "no_windows",
                "warning",
                f"The data is clearly {detection.kind.upper()} ({len(detection.pulses)} "
                "excitations) but there are no windows.",
            )
        )
        return _verdict(issues, detection, win, dict(detection.windows), gate, proposal_gates)
    for p in detection.pulses:
        label = (p.role + " " if p.role else "") + "excitation"
        where = f"{p.rise} ({p.rise * res * 1e9:.1f} ns)"
        holding = [k for k, (lo, hi) in win.items() if lo < hi and _inside(p.rise, lo, hi, n)]
        if not holding:
            issues.append(
                Issue(
                    "pulse_uncovered",
                    "warning",
                    f"The {label} rising at {where} is in no window.",
                )
            )
        lo, hi = p.rise, p.core_stop
        if detection.domain == "macro":  # a laser plateau: its middle must not be cut
            span = (hi - lo) % n
            lo, hi = (lo + span // 10) % n, (hi - span // 10) % n
        for name, (a, b) in win.items():
            for edge in (a, b):
                if 0 < edge < n and _strictly_inside(edge, lo + 1, hi, n):
                    issues.append(
                        Issue(
                            "window_cuts_pulse",
                            "warning",
                            f"Window {name} has its boundary at {edge}, inside the {label} "
                            f"({p.rise}–{p.core_stop}).",
                            name,
                        )
                    )
    for name, (a, b) in win.items():
        inside = [p for p in detection.pulses if a < b and _inside(p.rise, a, b, n)
                  and _inside(p.peak, a, b, n)]
        roles = {p.role for p in inside}
        if len(inside) > 1 and (len(roles) > 1 or "" in roles):
            issues.append(
                Issue(
                    "window_mixes_pulses",
                    "warning",
                    f"Window {name} ({a}–{b}) holds {len(inside)} excitation pulses: its photons "
                    "mix the excitations.",
                    name,
                )
            )
    roles = {p.window: p.role for p in detection.pulses}
    if "prompt" in win and "delayed" in win and roles.get("prompt") == "donor":
        donor = next(p for p in detection.pulses if p.role == "donor")
        acc = next((p for p in detection.pulses if p.role == "acceptor"), None)
        pa, pb = win["prompt"], win["delayed"]
        if acc is not None and _inside(acc.rise, pa[0], pa[1], n) and _inside(
            donor.rise, pb[0], pb[1], n
        ):
            issues.append(
                Issue(
                    "windows_swapped",
                    "warning",
                    "prompt holds the acceptor-excitation pulse and delayed the donor's: swapped.",
                )
            )
    return _verdict(issues, detection, win, dict(detection.windows), gate, proposal_gates)


def _check_gates(gates, detection, histograms, issues, unit, channels=None) -> dict:
    """Findings on the detectors' gates; returns the gates to propose (a broken gate opened to the
    whole range, the others as they are)."""
    n = int(detection.n_channels)
    # the gates to propose: as they are, an end past the data clipped to its range
    proposal = {d: [[r[0], min(r[1], n) if n else r[1]] for r in rs] for d, rs in gates.items()}
    broken: set[str] = set()
    for d, ranges in gates.items():
        if n and all(lo >= n for lo, _ in ranges):
            issues.append(Issue(
                "gate_outside_range", "error",
                f"The gate of detector {d} starts beyond the data's {n} {unit}: it sees nothing.",
            ))
            broken.add(d)
            continue
        mine = set((channels or {}).get(d) or [])
        siblings = [o for o in gates if o != d and mine
                    and mine & set((channels or {}).get(o) or [])]
        # A gate that keeps one excitation on purpose (BVA / FRET-2CDE gate the acceptor to the
        # prompt pulse; ALEX-2CDE streams; red/yellow split one detector) is fine: only a gate
        # that holds none of the excitations its detector sees -- here or in a sibling's gate on
        # the same channels -- is wrong.
        seen = [p for p in detection.pulses if d in p.excites]
        held = [p for p in seen if any(lo <= p.peak < hi for lo, hi in ranges)
                or any(lo <= p.peak < hi for o in siblings for lo, hi in gates[o])]
        if seen and not held:
            peaks = ", ".join(str(p.peak) for p in seen)
            issues.append(Issue(
                "gate_misses_pulse", "warning",
                f"The gate of detector {d} ({_fmt(ranges)}) leaves out every excitation it sees "
                f"(peaks at {peaks}).",
            ))
            broken.add(d)
        h = (histograms or {}).get(d)
        if h is not None and d not in broken and not siblings:
            h = np.asarray(h, dtype=float).ravel()
            total = float(h.sum())
            inside = sum(float(h[max(lo, 0):max(min(hi, h.size), 0)].sum()) for lo, hi in ranges)
            if total > 0 and inside / total < 0.05:
                issues.append(Issue(
                    "gate_empty", "warning",
                    f"The gate of detector {d} ({_fmt(ranges)}) holds "
                    f"{100 * inside / total:.2g} % of its photons.",
                ))
                broken.add(d)
    for d in broken:
        proposal[d] = [[0, n]]
    return proposal


def _fmt(ranges) -> str:
    return ", ".join(f"{lo}–{hi}" for lo, hi in ranges)


def _verdict(issues, detection, win, proposal, gates=None, proposal_gates=None) -> WindowCheck:
    """The worst severity, and what to offer: the detected windows when the windows do not hold the
    pulses, the converted windows when only their channel width was off."""
    worst = max((SEVERITIES.index(i.severity) for i in issues), default=0)
    status = SEVERITIES[worst]
    codes = {i.code for i in issues}
    if not detection.alternating:
        proposal = {}
    elif codes == {"resolution_mismatch"} or (
        win and not codes & _WINDOW_CODES and codes
    ):
        proposal = dict(win)
    return WindowCheck(status, issues, detection, win, proposal, dict(gates or {}),
                       dict(proposal_gates or {}) if (codes - {"single_pulse", "unclear"}) else {})


#: Findings about the windows themselves (the others are about gates or the channel width).
_WINDOW_CODES = {"alex_period_mismatch", "outside_range", "no_windows", "pulse_uncovered", "window_cuts_pulse",
                 "window_mixes_pulses", "windows_swapped", "window_empty"}
