"""Write the CSV files the old ALEX-Suite wrote.

People who used ALEX-Suite have scripts, spreadsheets and figure templates that
read its export: five files sharing one stem, each fully quoted, each with the
section headers the old ``SessionFile.write`` emitted. Asking them to rewrite all
of that is the real cost of switching, and it is avoidable — the numbers ChiSurf
has are the same numbers, so this module lays them out the old way.

It is a *compatibility* writer, not the storage format. ChiSurf's own record of a
burst analysis is the `.pto` container and the burst companions beside it
(``okf/subsystems/burst-companions.md``); this is what you hand to the script you
did not write.

Qt-free.
"""

from __future__ import annotations

import csv
import datetime
import pathlib
from dataclasses import dataclass, field

import numpy as np

from chisurf.plugins.burst.alex_suite.api.histograms import (
    Corrections,
    EsHistograms,
    Thresholds,
)

__all__ = ["Metadata", "LegacyExport", "write_legacy_export", "LEGACY_PARTS"]

#: The five files of an ALEX-Suite export, by the suffix appended to the stem.
LEGACY_PARTS = ("meta", "hist_E", "hist_S", "hist_2D", "original_bursts")


@dataclass
class Metadata:
    """The old *Experimental* panel: what the sample was.

    Free-form on purpose — it is written verbatim into the ``_meta`` file and
    read by nobody but a human.
    """

    sample_name: str = ""
    date: str = field(default_factory=lambda: datetime.date.today().isoformat())
    buffer: str = ""
    excitation_green: str = ""
    excitation_red: str = ""
    description: str = ""

    def rows(self) -> list[tuple[str, str]]:
        """Return the ``(name, value)`` rows, in the old panel's order."""
        return [
            ("sample_name", self.sample_name),
            ("date", self.date),
            ("buffer_used", self.buffer),
            ("exc_green", self.excitation_green),
            ("exc_red", self.excitation_red),
            ("description", self.description),
        ]


@dataclass
class LegacyExport:
    """Which of the five files to write."""

    metadata: bool = True
    e_histogram: bool = True
    s_histogram: bool = True
    histogram_2d: bool = True
    original_bursts: bool = False


def _write(path: pathlib.Path, rows) -> None:
    """Write fully-quoted CSV rows, the way the old exporter did."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        for row in rows:
            writer.writerow(row)


def write_legacy_export(
    stem: str | pathlib.Path,
    histograms: EsHistograms,
    *,
    corrections: Corrections = Corrections(),
    thresholds: Thresholds = Thresholds(),
    metadata: Metadata | None = None,
    search_parameters: dict | None = None,
    parts: LegacyExport = LegacyExport(),
    e_fit=None,
    e_components=(),
    s_fit=None,
    s_components=(),
    burst_table: dict | None = None,
) -> list[pathlib.Path]:
    """Write an ALEX-Suite-shaped export and return the files written.

    Parameters
    ----------
    stem : str or pathlib.Path
        Output stem; ``_meta.csv``, ``_hist_E.csv`` … are appended. A ``.csv``
        suffix on the stem is stripped first, so both ``run`` and ``run.csv``
        produce the same five names.
    histograms : EsHistograms
        From :func:`~chisurf.plugins.burst.alex_suite.api.histograms.es_histograms`.
    corrections, thresholds : Corrections, Thresholds
        Written into the ``_meta`` file, as the old panels' parameter blocks.
    metadata : Metadata, optional
        The sample description block.
    search_parameters : dict, optional
        Burst-search settings, written as the ``BURST SEARCH PARAMETERS`` block.
    parts : LegacyExport
        Which files to write.
    e_fit, s_fit : array_like, optional
        Fitted curves on the E and S axes.
    e_components, s_components : sequence of array_like, optional
        Individual fit components, written as the old ``GUESS n`` columns.
    burst_table : dict, optional
        ``{column: array}`` written as the ``_original_bursts`` file. Required
        when ``parts.original_bursts`` is set.

    Returns
    -------
    list of pathlib.Path
        The files written, in :data:`LEGACY_PARTS` order.
    """
    stem = pathlib.Path(stem)
    if stem.suffix.lower() == ".csv":
        stem = stem.with_suffix("")
    written: list[pathlib.Path] = []

    if parts.metadata:
        rows: list = []
        blocks = [
            ("BURST SEARCH PARAMETERS", list((search_parameters or {}).items())),
            (
                "THRESHOLDS",
                [
                    ("total_min", thresholds.total_min),
                    ("total_max", thresholds.total_max),
                    ("Tau_min", thresholds.duration_min_ms),
                    ("Tau_max", thresholds.duration_max_ms),
                    ("E_min", thresholds.e_range[0]),
                    ("E_max", thresholds.e_range[1]),
                    ("S_min", thresholds.s_range[0]),
                    ("S_max", thresholds.s_range[1]),
                    ("S_min_1D", thresholds.s_range_for_e[0]),
                    ("S_max_1D", thresholds.s_range_for_e[1]),
                    ("E_min_1D", thresholds.e_range_for_s[0]),
                    ("E_max_1D", thresholds.e_range_for_s[1]),
                ],
            ),
            ("EXPERIMENTAL", (metadata or Metadata()).rows()),
            (
                "ACCURATE FRET",
                [
                    ("bkg_DD", corrections.bg_dd),
                    ("bkg_DA", corrections.bg_da),
                    ("bkg_AA", corrections.bg_aa),
                    ("alpha", corrections.alpha),
                    ("delta", corrections.delta),
                    ("gamma", corrections.gamma),
                    ("beta", corrections.beta),
                ],
            ),
            (
                "PLOT OPTIONS",
                [
                    ("bins_E", len(histograms.e_centres)),
                    ("bins_S", len(histograms.s_centres)),
                    ("n_bursts", int(histograms.e.size)),
                    ("n_bursts_total", int(histograms.n_bursts_total)),
                ],
            ),
        ]
        for title, items in blocks:
            rows.append([title])
            rows.extend([name, value] for name, value in items)
        path = stem.with_name(stem.name + "_meta.csv")
        _write(path, rows)
        written.append(path)

    if parts.e_histogram:
        path = stem.with_name(stem.name + "_hist_E.csv")
        _write(
            path, _histogram_rows("E", histograms.e_centres, histograms.e_hist, e_fit, e_components)
        )
        written.append(path)

    if parts.s_histogram:
        path = stem.with_name(stem.name + "_hist_S.csv")
        _write(
            path, _histogram_rows("S", histograms.s_centres, histograms.s_hist, s_fit, s_components)
        )
        written.append(path)

    if parts.histogram_2d:
        rows = [["2D HISTOGRAM"]]
        rows.extend(list(row) for row in histograms.hist_2d)
        path = stem.with_name(stem.name + "_hist_2D.csv")
        _write(path, rows)
        written.append(path)

    if parts.original_bursts:
        if not burst_table:
            raise ValueError("parts.original_bursts is set but no burst_table was given")
        names = list(burst_table)
        columns = [np.asarray(burst_table[name]).ravel() for name in names]
        rows = [["BURSTS"], names]
        rows.extend(zip(*columns))
        path = stem.with_name(stem.name + "_original_bursts.csv")
        _write(path, rows)
        written.append(path)

    return written


def _histogram_rows(axis: str, centres, counts, fit, components) -> list:
    """Rows of one 1-D histogram file: centres, counts, fit and components.

    Ragged inputs are padded with 0.0, as ``izip_longest`` did in the original —
    a fit computed on a different grid should not silently truncate the
    histogram it is written beside.
    """
    components = [np.asarray(c, dtype=float).ravel() for c in (components or ())]
    fit_arr = np.empty(0) if fit is None else np.asarray(fit, dtype=float).ravel()
    header = [f"BIN CENTERS {axis}", f"{axis} HISTOGRAM", f"{axis} FIT"]
    header += [f"{axis} GUESS {i + 1}" for i in range(len(components))]

    columns = [
        np.asarray(centres, dtype=float).ravel(),
        np.asarray(counts, dtype=float).ravel(),
        fit_arr,
        *components,
    ]
    height = max((c.size for c in columns), default=0)
    padded = [np.pad(c, (0, height - c.size)) for c in columns]
    return [header, *zip(*padded)]
