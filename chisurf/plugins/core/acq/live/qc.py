"""Live quality traffic lights: the FRET quality checker's verdict on the bursts measured so far.

Nothing is judged here. The checks, thresholds and texts are the FRET quality checker's
(:func:`chisurf.plugins.burst.fret_check.qc.run_qc`); this module only hands it the live run in the
shape it reads -- its ``Experiment`` and ``Bursts`` -- and turns its levels into lights:
green (ok), amber (warn), red (bad), grey (information only, or not enough data yet). The overall
light is the worst check, as the checker's own ``QCReport.level``.

The action text of an amber or red light is the checker's issue text (what is wrong and what to do),
the same line its report prints, falling back to the check's own explanation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["MIN_BURSTS", "MIN_SECONDS", "LIGHT", "live_qc"]

#: Before this many bursts and seconds the lights stay grey: a verdict on a handful of bursts
#: would flip at every refresh.
MIN_BURSTS = 50
MIN_SECONDS = 5.0

#: The checker's levels as lights.
LIGHT = {"ok": "green", "warn": "amber", "bad": "red", "info": "grey"}


def _issue_actions() -> dict[str, str]:
    try:  # the checker's issue texts (its report's Issues section)
        from chisurf.plugins.burst.fret_check.report import _ISSUE_ACTION

        return dict(_ISSUE_ACTION)
    except Exception:  # noqa: BLE001 - fall back to each check's own explanation
        return {}


def live_qc(
    table: dict[str, np.ndarray],
    *,
    elapsed_s: float,
    background_per_s: dict[str, float],
    trace: tuple[np.ndarray, np.ndarray],
    setup,
    macro_clock_s: float,
    micro_res_s: float,
    n_micro: int,
    n_photons: int,
    v_eff_fl: float = 1.0,
) -> dict[str, Any]:
    """The checker's report on the live run, as lights.

    Parameters
    ----------
    table : dict
        The live burst table (``PieBurstAnalyzer.results()``).
    elapsed_s : float
        Measurement time so far.
    background_per_s : dict
        Counts per second outside bursts, per stream (``DD``, ``DA``, ``AA``).
    trace : (ndarray, ndarray)
        Total count rate in 1 s bins: bin centres (s) and kHz.
    setup : PieSetup
    macro_clock_s, micro_res_s, n_micro, n_photons : clocks and size of the run.
    v_eff_fl : float
        Effective volume for the checker's concentration estimate.

    Returns
    -------
    dict
        ``ready`` (enough data for a verdict), ``level`` (overall light), ``checks`` (each with
        ``name``, ``light``, ``value``, ``detail``, ``action``) and the checker's ``metrics``.
    """
    from chisurf.plugins.burst.fret_check.detect import Experiment
    from chisurf.plugins.burst.fret_check.pipeline import Bursts
    from chisurf.plugins.burst.fret_check.qc import run_qc

    n = int(len(table.get("First Photon", ())))
    if n < MIN_BURSTS or elapsed_s < MIN_SECONDS:
        return {
            "ready": False,
            "level": "grey",
            "checks": [],
            "metrics": {},
            "why": f"{n} of {MIN_BURSTS} bursts, {elapsed_s:.0f} of {MIN_SECONDS:.0f} s",
        }
    exp = Experiment(
        container="live",
        n_photons=int(n_photons),
        duration_s=float(elapsed_s),
        macro_time_resolution_s=float(macro_clock_s),
        micro_time_resolution_s=float(micro_res_s),
        n_micro_channels=int(n_micro),
        channels=[*setup.donor_channels, *setup.acceptor_channels],
        channel_counts={},
        excitation="alternating",
        donor_channels=list(setup.donor_channels),
        acceptor_channels=list(setup.acceptor_channels),
    )
    duration = np.asarray(table["Duration (ms)"], dtype=float) * 1e-3
    t_mid = np.asarray(table["Mean Macro Time (ms)"], dtype=float) * 1e-3
    bursts = Bursts(
        start=np.asarray(table["First Photon"]),
        stop=np.asarray(table["Last Photon"]),
        t_start=t_mid - 0.5 * duration,
        duration=duration,
        counts={
            k: np.asarray(table[f"Number of Photons ({k})"], dtype=float)
            for k in ("DD", "DA", "AA")
        },
        background={k: float(v) for k, v in background_per_s.items()},
        E=np.asarray(table["E"], dtype=float),
        S=np.asarray(table["S"], dtype=float),
    )
    report = run_qc(None, exp, bursts, v_eff_fl=v_eff_fl, trace=trace)
    actions = _issue_actions()
    checks = [
        {
            "name": c.name,
            "light": LIGHT.get(c.level, "grey"),
            "value": c.value,
            "detail": c.detail,
            "action": actions.get(c.name, c.detail) if c.level in ("warn", "bad") else "",
        }
        for c in report.checks
    ]
    return {
        "ready": True,
        "level": LIGHT.get(report.level, "grey"),
        "checks": checks,
        "metrics": report.metrics,
        "why": "",
    }
