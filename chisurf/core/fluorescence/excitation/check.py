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
``single_pulse`` / ``unclear`` (info)
    One excitation pulse (donor-only sample, or not PIE) or no clear pulse: nothing is checked
    against pulses; nothing is proposed.
"""

from __future__ import annotations

import numpy as np

from .result import SEVERITIES, ExcitationWindows, Issue, WindowCheck, rescale_windows

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

    Returns
    -------
    WindowCheck
    """
    issues: list[Issue] = []
    res, n = float(detection.resolution_s), int(detection.n_channels)
    win = {str(k): [int(v[0]), int(v[1])] for k, v in (windows or {}).items()}
    unit = "phase ticks" if detection.domain == "macro" else "micro-time channels"
    if win and windows_resolution_s and res > 0:
        ratio = float(windows_resolution_s) / res
        if abs(ratio - 1.0) > 0.01:
            conv = rescale_windows(win, windows_resolution_s, res)
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
    if not detection.alternating:
        code = "single_pulse" if detection.kind == "single" else "unclear"
        issues.append(Issue(code, "info", detection.message + " Windows not checked."))
        return _verdict(issues, detection, win, {})
    if not win:
        issues.append(
            Issue(
                "no_windows",
                "warning",
                f"The data is clearly {detection.kind.upper()} ({len(detection.pulses)} "
                "excitations) but there are no windows.",
            )
        )
        return _verdict(issues, detection, win, dict(detection.windows))
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
    return _verdict(issues, detection, win, dict(detection.windows))


def _verdict(issues, detection, win, proposal) -> WindowCheck:
    """The worst severity, and what to offer: the detected windows when the windows do not hold the
    pulses, the converted windows when only their channel width was off."""
    worst = max((SEVERITIES.index(i.severity) for i in issues), default=0)
    status = SEVERITIES[worst]
    if not detection.alternating:
        proposal = {}
    elif {i.code for i in issues} == {"resolution_mismatch"}:
        proposal = dict(win)
    return WindowCheck(status, issues, detection, win, proposal)
