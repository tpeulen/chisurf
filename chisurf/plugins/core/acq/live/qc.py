"""Live quality traffic lights: the FRET quality checker's verdict on the bursts measured so far.

Nothing is judged here. The checks, thresholds and texts are the FRET quality checker's
(:func:`chisurf.plugins.burst.fret_check.qc.run_qc`); this module hands it the live run in the
shape it reads -- its ``Experiment`` and ``Bursts`` -- for the measurement type at hand, and turns
its levels into lights: green (ok), amber (warn), red (bad), grey (information only, not enough
data yet, or not applicable to this measurement type). The overall light is the worst check.

Per preset:

* **PIE / µs-ALEX** -- streams DD, DA, AA; proximity ratio and stoichiometry: every check.
* **two colour, MFD** -- donor and acceptor; no stoichiometry, so the checker's low-E check stands
  in and donor-only / acceptor-only is *not applicable*.
* **single colour** -- one stream; the two-colour checks are *not applicable*.
* FRET-2CDE / ALEX-2CDE are not computed live: grey, *not computed live*.

The action of an amber or red light is the checker's issue text (what is wrong and what to do).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .setups import Experiment

__all__ = ["LIGHT", "MIN_BURSTS", "MIN_SECONDS", "live_qc"]

#: Before this many bursts and seconds the lights stay grey.
MIN_BURSTS = 50
MIN_SECONDS = 5.0

LIGHT = {"ok": "green", "warn": "amber", "bad": "red", "info": "grey"}

_NOT_COMPUTED = ("FRET-2CDE > 30", "ALEX-2CDE > 30")


def _issue_actions() -> dict[str, str]:
    try:  # the checker's issue texts (its report's Issues section)
        from chisurf.plugins.burst.fret_check.report import _ISSUE_ACTION

        return dict(_ISSUE_ACTION)
    except Exception:  # noqa: BLE001 - fall back to each check's own explanation
        return {}


def _column(table: dict, prefix: str) -> np.ndarray | None:
    for name, col in table.items():
        if name.startswith(prefix):
            return np.asarray(col, dtype=float)
    return None


def _streams(table: dict, exp: Experiment, background: dict) -> tuple[dict, dict]:
    """Per-burst counts and background (counts/s) of the streams the checker reads."""
    d, a, p, q = exp.donor, exp.acceptor, exp.prompt, exp.delay
    if exp.preset in ("pie", "alex"):
        spec = {"DD": f"{p} {d}", "DA": f"{p} {a}", "AA": f"{q} {a}"}
        counts = {k: _column(table, f"S {v} (photons)") for k, v in spec.items()}
    elif exp.preset in ("two_color", "mfd"):
        dets = list((exp.setup.get("detectors") or {}).keys())
        don = [n for n in dets if n == d or n.startswith(d + "_")]
        acc = [n for n in dets if n == a or n.startswith(a + "_")]
        spec = {"DD": don, "DA": acc}
        counts = {
            k: sum(np.asarray(table[f"Number of Photons ({n})"], dtype=float) for n in names)
            for k, names in spec.items()
        }
        bg = {k: sum(background.get(n, 0.0) for n in names) for k, names in spec.items()}
        return counts, bg
    else:  # single colour, three-colour PIE: all photons as one stream
        n = np.asarray(table["Number of Photons"], dtype=float)
        dets = list((exp.setup.get("detectors") or {}).keys())
        return {"all": n}, {"all": sum(background.get(x, 0.0) for x in dets)}
    bg = {k: float(background.get(v, 0.0)) for k, v in spec.items()}
    return counts, bg


def live_qc(
    table: dict[str, np.ndarray],
    exp: Experiment,
    *,
    elapsed_s: float,
    background_cps: dict[str, float],
    trace: tuple[np.ndarray, np.ndarray],
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
        The live burst table (the analyzer's ``table()``).
    exp : Experiment
        Setup and preset (which checks apply, which streams are DD/DA/AA).
    elapsed_s : float
    background_cps : dict
        The analyzer's per-stream background (``snapshot()['background_cps']``).
    trace : (ndarray, ndarray)
        Total count rate in 1 s bins: bin centres (s), kHz.
    macro_clock_s, micro_res_s, n_micro, n_photons : clocks and size of the run.
    v_eff_fl : float
        Effective volume for the checker's concentration estimate.

    Returns
    -------
    dict
        ``ready``, ``level`` (overall light), ``checks`` (``name``, ``light``, ``value``,
        ``detail``, ``action``), the checker's ``metrics``, and ``why`` while not ready.
    """
    from chisurf.plugins.burst.fret_check.detect import Experiment as QcExperiment
    from chisurf.plugins.burst.fret_check.pipeline import Bursts
    from chisurf.plugins.burst.fret_check.qc import run_qc

    n = int(len(table.get("First Photon", ())))
    if n < MIN_BURSTS or elapsed_s < MIN_SECONDS:
        return {"ready": False, "level": "grey", "checks": [], "metrics": {},
                "why": f"{n} of {MIN_BURSTS} bursts, {elapsed_s:.0f} of {MIN_SECONDS:.0f} s"}  # fmt: skip
    two_colour = exp.preset not in ("single_color", "three_color_pie")
    donor = exp.channels("donor")
    acceptor = exp.channels("acceptor") if two_colour else []
    qexp = QcExperiment(
        container="live",
        n_photons=int(n_photons),
        duration_s=float(elapsed_s),
        macro_time_resolution_s=float(macro_clock_s),
        micro_time_resolution_s=float(micro_res_s),
        n_micro_channels=int(n_micro),
        channels=[*donor, *acceptor],
        channel_counts={},
        excitation="alternating" if exp.alternating else "cw",
        donor_channels=list(donor),
        acceptor_channels=list(acceptor),
    )
    counts, background = _streams(table, exp, background_cps)
    duration = np.asarray(table["Duration (ms)"], dtype=float) * 1e-3
    t_mid = np.asarray(table["Mean Macro Time (ms)"], dtype=float) * 1e-3
    pr = table.get("Proximity Ratio")
    bursts = Bursts(
        start=np.asarray(table["First Photon"]),
        stop=np.asarray(table["Last Photon"]),
        t_start=t_mid - 0.5 * duration,
        duration=duration,
        counts=counts,
        background=background,
        E=np.asarray(pr, dtype=float) if pr is not None else np.zeros(n),
        S=np.asarray(table["Stoichiometry"], dtype=float)
        if exp.alternating and "Stoichiometry" in table
        else None,
    )
    report = run_qc(None, qexp, bursts, v_eff_fl=v_eff_fl, trace=trace)
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
    shown = {c["name"] for c in checks}

    def na(name, value, detail):
        if name not in shown:
            checks.append(
                {"name": name, "light": "grey", "value": value, "detail": detail, "action": ""}
            )

    if not exp.alternating and two_colour:
        na("donor-only / acceptor-only", "not applicable",
           "needs alternating excitation (PIE or ALEX) to measure stoichiometry")  # fmt: skip
    if not two_colour:
        na(
            "donor-only / acceptor-only",
            "not applicable",
            "a single-colour measurement has no FRET pair",
        )
        na("low-E / donor-only", "not applicable", "a single-colour measurement has no FRET pair")
    for name in _NOT_COMPUTED:
        na(
            name,
            "not computed live",
            "the 2CDE filters need the photons of each burst; run the FRET checker on the recording",
        )
    return {"ready": True, "level": LIGHT.get(report.level, "grey"), "checks": checks,
            "metrics": report.metrics, "why": ""}  # fmt: skip
