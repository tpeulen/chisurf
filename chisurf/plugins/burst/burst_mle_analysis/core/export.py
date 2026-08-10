"""The MLE lifetime results, written into the measurement's container.

The legacy layout is the widest in the burst set, and every part of its width
comes from the same cause — a companion carries one row per burst, so anything
that is not one row per burst has to leave the format:

* ``bg4/``, ``by4/``, ``br4/`` — the per-burst fits, one directory per detector
  colour, each merged onto the burst table by counting rows;
* ``b?4/channel_settings.json`` — a settings file dropped *inside* a companion
  directory, which every reader of that directory then has to skip;
* ``Info/experiment_settings.json`` — the IRF and the background that produced
  the fits, written as a JSON array-of-floats because there was nowhere to put a
  curve;
* ``Info/state_lifetimes.csv`` — the pooled per-state fits, which
  :meth:`write_state_lifetimes` documents as *deliberately* outside the
  companion system: "written as a companion it would misalign every burst after
  the first".

Here each of those is an object at the grain it actually has. The per-burst fits
are ``burst``, the pooled state fits are ``state``, and the IRF and background
are ``curve_point`` — a curve, which is what they were all along. Nothing needs
a directory name to be found, so nothing needs to be skipped.
"""

from __future__ import annotations

import numpy as np

from pathlib import Path
from typing import Any, Mapping

__all__ = ["write_mle_container"]

#: Units for the MLE result columns whose name does not carry one.
#:
#: The per-detector columns are named ``Tau (green)``, ``Tau S0 (red)`` and so
#: on — a colour in the parenthesis, not a unit — so the label convention that
#: covers the burst table cannot reach them. They are matched by prefix instead
#: of listed, because the state split multiplies every one of them by the number
#: of states and listing the product would go stale the first time a model gains
#: a parameter.
_UNIT_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("Tau", "nanoseconds"),
    ("rho", "nanoseconds"),
    ("Number of Photons", "photons"),
    ("Ng-p", "photons"),
    ("Ng-s", "photons"),
    ("2I*", "dimensionless"),
    ("gamma", "dimensionless"),
    ("r0", "dimensionless"),
    ("r Scatter", "dimensionless"),
    ("r Experimental", "dimensionless"),
)


#: `irf_model` -> the `_mmfdb_operation.algorithm` term for it.
#:
#: The IRF is not one method. A Gaussian fitted to the measured prompt, a
#: skew-normal fitted to it, and the measured prompt used raw are three
#: different instrument responses, and a lifetime fitted against each differs.
#: `operation_type` says only that a calibration happened; this says which,
#: so two containers can be told apart without parsing settings.
#:
#: An `irf_model` not listed here records nothing rather than the nearest
#: guess -- absent means unrecorded, never "the usual one".
_IRF_ALGORITHM = {
    "gaussian": "gaussian_prompt_fit",
    "skewed": "skew_normal_prompt_fit",
    "experimental": "measured_prompt",
    "raw": "measured_prompt",
}


def _units_by_prefix(columns) -> dict[str, str]:
    """Return ``{column: unit}`` for the columns a prefix rule recognises.

    Parameters
    ----------
    columns : iterable of str

    Returns
    -------
    dict
    """
    out: dict[str, str] = {}
    for name in columns:
        text = str(name)
        for prefix, unit in _UNIT_BY_PREFIX:
            if text.startswith(prefix):
                out[text] = unit
                break
    return out


def write_mle_container(
    source: str | Path,
    tables: Mapping[str, Any],
    *,
    state_rows=None,
    experiment: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    out_dir: str | Path | None = None,
) -> str:
    """Write one measurement's MLE results into its container.

    Parameters
    ----------
    source : str or Path
        The instrument file the bursts came from, or the container itself.
    tables : mapping of str to table
        ``{detector: per-burst fits}``. One object per detector, as the legacy
        layout had one directory per detector — the fits genuinely are per
        detector, and merging them into one wide table would lose which columns
        a given detector produced.
    state_rows : sequence of mapping, optional
        The pooled per-state fits, one row per ``(detector, state)``. Written at
        ``state`` grain, which is why it no longer has to live in ``Info/``.
    experiment : mapping, optional
        :meth:`experiment_settings` output — the per-detector IRF and background
        that produced these fits. Written as one curve object per detector; a
        detector with nothing loaded is skipped rather than written empty, so an
        absent IRF stays distinguishable from a zero one.
    parameters : mapping, optional
        The fit settings. Their hash is the identity of the run, so re-fitting
        with the same settings replaces these objects instead of adding beside
        them.
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import column_names, store_from_arrays, store_from_rows
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    written = ""
    for detector, table in tables.items():
        if table is None:
            continue
        written = write_burst_artifact(
            source, table,
            name=f"mle {str(detector).lower()}",
            artifact_kind="fit_result",
            operation_type="burst_lifetime_fitting",
            algorithm="mle",
            row_grain="burst",
            parameters=parameters,
            derived_from="bursts",
            units=_units_by_prefix(column_names(table)),
            out_dir=out_dir,
        )

    if state_rows is not None and len(state_rows):
        written = write_burst_artifact(
            source, store_from_rows(list(state_rows)),
            name="mle state lifetimes",
            artifact_kind="fit_result",
            operation_type="burst_lifetime_fitting",
            algorithm="mle",
            row_grain="state",
            parameters=parameters,
            derived_from=[f"mle {str(d).lower()}" for d in tables] or "bursts",
            source_row_column="State",
            units={
                "Tau": "nanoseconds", "rho": "nanoseconds",
                "Photons": "photons", "Photons (parallel)": "photons",
                "Photons (perpendicular)": "photons",
                "2I*": "dimensionless", "gamma": "dimensionless",
                "r0": "dimensionless",
            },
            out_dir=out_dir,
        )

    for detector, entry in (experiment or {}).get("detectors", {}).items():
        irf = np.asarray(entry.get("irf") or [], dtype=float)
        background = np.asarray(entry.get("background") or [], dtype=float)
        if irf.size == 0 and background.size == 0:
            continue
        n = max(irf.size, background.size)
        curve = {"Channel": np.arange(n, dtype=np.int64)}
        # Only the arrays that are actually there. Padding the shorter one would
        # invent counts, and the whole point of writing these as a curve is that
        # what was measured is recoverable.
        if irf.size == n:
            curve["IRF"] = irf
        if background.size == n:
            curve["Background"] = background
        written = write_burst_artifact(
            source, store_from_arrays(curve),
            name=f"irf {str(detector).lower()}",
            artifact_kind="irf_curve",
            operation_type="calibration",
            algorithm=_IRF_ALGORITHM.get(
                str((parameters or {}).get("irf_model", "")).lower(), ""),
            row_grain="curve_point",
            parameters=parameters,
            # Not derived from the bursts: an instrument response is measured
            # separately and *used* here. With no parent named, the container
            # attaches it to the photon stream it calibrated, which is the
            # narrowest true statement available.
            derived_from=(),
            units={"Channel": "dimensionless", "IRF": "counts",
                   "Background": "counts_per_second"},
            out_dir=out_dir,
        )
    return written
