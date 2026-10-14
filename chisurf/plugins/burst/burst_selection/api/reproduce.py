"""Reproduce a burst search stored in a ``.pto`` container, from the container alone.

A derived result goes into the measurement's container together with the
settings that made it, and :meth:`~chisurf.core.fio.pto.Measurement.lineage`
walks it back to the photon stream. This module closes that loop: it reads the
burst table of a run, follows its lineage to the primary data, re-runs the
burst selection with the *stored* settings through the same
:func:`~chisurf.plugins.burst.burst_selection.api.selection.analyze_file` a
normal run uses, and says whether the stored table is what those settings
produce.

It is the container counterpart of :mod:`.replay`, which re-runs a burst
selection recorded in the MMFDB database. Nothing is written: the re-run reads
the container in place with every output format switched off.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.plugins.burst.burst_selection.api.serialization import settings_from_dict

#: The burst-table columns that identify a burst: its photon interval.
INTERVAL_COLUMNS = ("First Photon", "Last Photon")


@dataclass
class Reproduction:
    """What re-running a stored burst search gave, beside what was stored.

    Attributes
    ----------
    table : str
        The burst table checked (``<run>/bi4_bur/<stem>.bur``).
    lineage : list of dict
        :meth:`Measurement.lineage` of the table, ending at the primary data.
    settings : dict
        The stored settings the search was re-run with.
    n_stored, n_reproduced : int
        Bursts in the stored table and in the re-run.
    first_photon_mismatch, last_photon_mismatch : int
        Largest index difference of the interval bounds when the counts agree,
        else ``-1``.
    """

    table: str
    lineage: list[dict] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    n_stored: int = 0
    n_reproduced: int = 0
    first_photon_mismatch: int = -1
    last_photon_mismatch: int = -1

    @property
    def is_exact(self) -> bool:
        """Whether the re-run found exactly the stored bursts."""
        return (
            self.n_stored == self.n_reproduced
            and self.first_photon_mismatch == 0
            and self.last_photon_mismatch == 0
        )


def _intervals(rows_or_table: Any) -> tuple[np.ndarray, np.ndarray]:
    """``(first, last)`` photon indices of every burst, padding rows dropped."""
    from chisurf.core.datastore import as_store
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts

    table = deinterleave_bursts(as_store(rows_or_table))
    first, last = (np.asarray(table[name], dtype=np.int64) for name in INTERVAL_COLUMNS)
    return first, last


def reproduce_burst_search(container: str | pathlib.Path, run: str = "") -> Reproduction:
    """Re-run the burst search stored in *container* and compare it with the stored table.

    Parameters
    ----------
    container : str or pathlib.Path
        The measurement's ``.pto``.
    run : str, optional
        The run to check (``countrate_All 0.2000#60``); empty takes the newest.

    Returns
    -------
    Reproduction

    Raises
    ------
    FileNotFoundError
        If the container holds no burst table for *run*.
    ValueError
        If the table's lineage does not reach the primary data, or it carries no
        settings to re-run with -- either way the result is not reproducible
        from the container, which is the claim being checked.
    """
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_file

    path = pathlib.Path(container)
    with Measurement.open(path, writable=False) as measurement:
        table = burst_table_name(measurement, run)
        if not table:
            raise FileNotFoundError(f"{path.name} holds no burst table for run {run!r}")
        lineage = measurement.lineage(table)
        primary = set(measurement.instrument_uids)
        if not lineage or lineage[-1]["uid"] not in primary:
            raise ValueError(f"{table} does not trace back to the photon stream in {path.name}")
        settings = lineage[0]["settings"]
        if not isinstance(settings, dict) or not settings or "_unparsed" in settings:
            raise ValueError(f"{table} records no usable burst-search settings")
        stored_first, stored_last = _intervals(measurement.get_store(table))

    analysis = settings_from_dict(json.loads(json.dumps(settings)))
    # Read, never write: the container is the evidence being checked.
    analysis.output_formats = []
    result = analyze_file(path, settings=analysis)
    rows = next(iter(result.dataframes.values()), [])
    first, last = _intervals(rows)

    report = Reproduction(
        table=table,
        lineage=lineage,
        settings=settings,
        n_stored=int(stored_first.size),
        n_reproduced=int(first.size),
    )
    if first.size == stored_first.size:
        report.first_photon_mismatch = (
            int(np.max(np.abs(first - stored_first))) if first.size else 0
        )
        report.last_photon_mismatch = int(np.max(np.abs(last - stored_last))) if last.size else 0
    return report
