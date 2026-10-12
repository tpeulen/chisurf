"""Scanning labeling sites: one site simulated, one record reported.

A scan asks the same question of many attachment sites — what lifetime, what
quantum yield, what quenches the dye there — so the answer must have one shape
no matter which surface asked. This module owns that: building the per-site
project, running it, and reporting the result (or the failure) as a plain dict.

The CLI's ``quest scan``, the web UI's streaming ``/api/scan`` and the
``fps.json`` generator :func:`quest.core.fps_json.run_fps_scan` all call
:func:`simulate_site`. Concurrency and progress reporting stay with the caller,
because those are transport concerns; what a site *is* and what a result
*contains* are not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, MutableMapping, Optional, Tuple

__all__ = [
    "SITE_AV_PARAMETER_KEYS",
    "site_project",
    "simulate_site",
    "scan_positions",
]

#: Position keys copied from an fps.json entry into the site's AV parameters.
#: ``simulation_grid_resolution`` is the odd one out: it maps onto the
#: project-wide grid spacing ``dg`` rather than into ``av_parameter``.
SITE_AV_PARAMETER_KEYS: tuple[str, ...] = (
    "linker_length",
    "linker_width",
    "radius1",
    "radius2",
    "radius3",
    "simulation_grid_resolution",
    "simulation_type",
    "allowed_sphere_radius",
)


def site_project(
    project: Mapping[str, Any],
    position: Mapping[str, Any],
) -> MutableMapping[str, Any]:
    """Return a copy of *project* with the attachment set to *position*.

    Parameters
    ----------
    project : mapping
        The base project shared by every site in the scan.
    position : mapping
        One fps.json position entry (``chain_identifier``,
        ``residue_seq_number``, ``atom_name``, and optional AV overrides).
    """

    site = dict(project)
    site["attachment"] = {
        "chain": position.get("chain_identifier", ""),
        "residue": int(position.get("residue_seq_number", 0)),
        "atom": position.get("atom_name", "CB"),
    }

    site["av_parameter"] = dict(site.get("av_parameter") or {})
    for key in SITE_AV_PARAMETER_KEYS:
        if key not in position:
            continue
        if key == "simulation_grid_resolution":
            site["dg"] = float(position[key])
        else:
            site[key] = position[key]
            site["av_parameter"][key] = position[key]

    # The donor dye carries its own copy of the attachment and AV parameters
    # (see build_donor_from_project), so it has to follow the site.
    if site.get("fret", {}).get("enabled"):
        dyes = site.get("fret", {}).get("dyes") or []
        if dyes:
            donor = dict(dyes[0])
            donor["attachment"] = dict(site["attachment"])
            donor["av_parameter"] = dict(site["av_parameter"])
            fret = dict(site["fret"])
            fret["dyes"] = [donor, *dyes[1:]]
            site["fret"] = fret

    return site


def _failure(name: str, position: Mapping[str, Any], error: str) -> dict[str, Any]:
    return {
        "name": name,
        "chain": position.get("chain_identifier", ""),
        "residue": int(position.get("residue_seq_number", 0)),
        "residue_name": position.get("residue_name", ""),
        "atom": position.get("atom_name", "CB"),
        "status": "failed",
        "error": error,
        "lifetime": None,
        "quantum_yield": None,
        "contact_fraction": None,
        "av_volume": None,
        "contact_volume": None,
        "contact_to_free_ratio": None,
        "dominant_quencher": None,
        "dominant_quencher_fraction": None,
        "quenchers": [],
    }


def simulate_site(
    project: Mapping[str, Any],
    position: Mapping[str, Any],
    *,
    name: str,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Simulate one labeling site and return its record. Never raises.

    A buried residue or an unresolvable structure must not abort a scan of
    hundreds of sites, so a failure is reported as data: the same keys with
    ``status="failed"``, an ``error`` string, and null metrics.

    The simulation runs with ``save_outputs=False`` — a scan reads scalar
    metrics and ``aa_residence`` only, and writing a job directory per site
    costs more than the simulation itself.
    """

    from chisurf.plugins.quenching_estimator.api import local as api

    try:
        site = site_project(project, position)
        api.validate_project(site)
        result = api.simulate_project(
            site,
            pdb_path=pdb_path,
            nbins=nbins,
            tac_range=tac_range,
            project_dir=project_dir,
            save_outputs=False,
            # A scan reads scalar metrics and `aa_residence`; thinning point
            # clouds nobody will draw, once per residue, is pure overhead.
            render_data=False,
        )
    except Exception as exc:
        return _failure(name, position, str(exc))

    quenchers = api.top_quenchers(getattr(result, "aa_residence", None))
    return {
        "name": name,
        "chain": site["attachment"]["chain"],
        "residue": site["attachment"]["residue"],
        "residue_name": position.get("residue_name", ""),
        "atom": site["attachment"]["atom"],
        "status": "success",
        "lifetime": getattr(result, "lifetime_donor", 0.0),
        "quantum_yield": result.quantum_yield_donor,
        "contact_fraction": result.collisions_fraction,
        "av_volume": getattr(result, "av_volume", None),
        "contact_volume": getattr(result, "contact_volume", None),
        "contact_to_free_ratio": getattr(result, "contact_to_free_ratio", None),
        "dominant_quencher": quenchers[0]["residue_name"] if quenchers else None,
        "dominant_quencher_fraction": (quenchers[0]["quench_rate_fraction"] if quenchers else None),
        "quenchers": quenchers,
    }


def scan_positions(
    project: Mapping[str, Any],
    positions: Mapping[str, Mapping[str, Any]],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Path | str] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    report_progress: Optional[Callable[..., Any]] = None,
) -> Iterator[dict[str, Any]]:
    """Yield one record per entry in *positions*, in order.

    Sequential by design: callers that want concurrency own the pool, because
    how many sites run at once depends on the transport (see the web backend's
    ``SCAN_WORKERS``, kept small because the AV kernel holds the GIL).

    Parameters
    ----------
    should_cancel : callable, optional
        Polled **between sites**. Returning true stops the scan; sites already
        yielded stand. This is the only checkpoint a scan has, and it is a real
        one: a site takes seconds, so a cancel lands within one.

        A plain predicate rather than a job or a manager, so `quest.core` knows
        nothing about job bookkeeping and a caller with its own cancellation
        source -- a host, a Qt dialog -- can pass its own
        (okf/subsystems/tasks.md).
    report_progress : callable, optional
        Called as ``report_progress(percent, message)`` after each site.
    """

    total = max(1, len(positions))
    for index, (name, position) in enumerate(positions.items()):
        if should_cancel is not None and should_cancel():
            return
        yield simulate_site(
            project,
            position,
            name=name,
            pdb_path=pdb_path,
            nbins=nbins,
            tac_range=tac_range,
            project_dir=project_dir,
        )
        if report_progress is not None:
            report_progress(int(100 * (index + 1) / total), name)
