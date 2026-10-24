"""ChiSurf entrypoints and RPC handlers for the FRET check.

The desktop plugin runs the analysis inline (the sync runner): no Web Worker
inside ChiSurf. The RPC methods are the job JSON schemas from the app -- one
API for the plugin, the RPC and the page.
"""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["analyse", "detect", "make_app", "qc", "register_services"]

_PKG = "chisurf.plugins.burst.fret_check"


def make_app(path: str | None = None) -> Any:
    """Create the FRET check application for ChiSurf (inline, sync runner)."""
    from chisurf.plugins.burst.fret_check.app.frame import make_app as _make_app

    return _make_app(path=path, runner="sync")


def detect(
    filename: str = "",
    path: str = "",
    scenario: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Detect experiment configuration and routing channels from a TTTR file or simulation."""
    target = path or filename
    if scenario:
        from chisurf.plugins.burst.fret_check.sim import SCENARIOS, simulate

        sc = next((s for s in SCENARIOS if s.name == scenario), SCENARIOS[0])
        raw = simulate(sc)
    elif target:
        from chisurf.plugins.burst.fret_check.detect import load

        raw = load(target)
    else:
        raise ValueError("Must provide either a file path or a scenario name.")

    from chisurf.plugins.burst.fret_check.detect import detect_experiment
    from chisurf.plugins.burst.fret_check.jobs import experiment_to_dict

    exp = detect_experiment(raw)
    return experiment_to_dict(exp)


def analyse(
    filename: str = "",
    path: str = "",
    scenario: str = "",
    key: str = "",
    redetect: bool = False,
    experiment: dict | None = None,
    settings: dict | None = None,
    v_eff_fl: float = 1.0,
    correct: bool = False,
    factors: dict | None = None,
    auto_calibrate: bool = False,
    report: Callable[[float, str], None] | None = None,
    progress: Callable[[float, str], None] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run smFRET burst detection, quality control, and corrections."""
    from chisurf.plugins.burst.fret_check import jobs

    target = path or filename
    reporter = report or progress or (lambda f, m: None)
    job_key = key or target or scenario or "analysis"

    return jobs.analyse(
        reporter,
        key=job_key,
        path=target,
        scenario=scenario,
        redetect=redetect,
        experiment=experiment,
        settings=settings,
        v_eff_fl=v_eff_fl,
        correct=correct,
        factors=factors,
        auto_calibrate=auto_calibrate,
    )


def qc(
    filename: str = "",
    path: str = "",
    scenario: str = "",
    key: str = "",
    redetect: bool = False,
    experiment: dict | None = None,
    settings: dict | None = None,
    v_eff_fl: float = 1.0,
    correct: bool = False,
    factors: dict | None = None,
    auto_calibrate: bool = False,
    report: Callable[[float, str], None] | None = None,
    progress: Callable[[float, str], None] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run smFRET quality control and generate the quality verdict."""
    result = analyse(
        filename=filename,
        path=path,
        scenario=scenario,
        key=key,
        redetect=redetect,
        experiment=experiment,
        settings=settings,
        v_eff_fl=v_eff_fl,
        correct=correct,
        factors=factors,
        auto_calibrate=auto_calibrate,
        report=report,
        progress=progress,
        **kwargs,
    )
    return result["qc"]


def register_services(dispatcher: Any) -> None:
    """Register the RPC services on a ChiSurf service dispatcher."""
    dispatcher.register("fret_check.detect", lambda params: detect(**(params or {})))
    dispatcher.register("fret_check.analyse", lambda params: analyse(**(params or {})))
    dispatcher.register("fret_check.qc", lambda params: qc(**(params or {})))
