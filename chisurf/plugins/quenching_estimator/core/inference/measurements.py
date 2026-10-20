"""Measurement tables of a quenching analysis, read from CSV into numpy record arrays.

Three tables make up one data set (the shipped example is MalE, ``examples/male/``):

``tcspc_fit_results.csv``
    One row per TCSPC fit: ``Date``, ``D2O %``, ``Variant`` (the labelled residue as typed),
    ``Dye``, ``Condition`` (``APO``/``HOLO`` for the protein, ``dye`` for the free dye),
    ``tauX`` (ns) and ``Data path name``.
``amino_acid_quenching_flt.csv``
    The free-dye titrations, one row per concentration point: ``Date``, ``Dye``,
    ``Amino acid``, ``Concentration, mM``, ``tauX0, ns`` (the day's unquenched lifetime) and
    ``tauX``.
``titration_summary.csv``
    One row per dye and amino acid, as summarised by the experimenter (Stern-Volmer constant
    and bimolecular quenching constant with their errors). The analysis recomputes these from
    the points; the summary is kept for comparison.

**The site number is taken from the file name.** Some rows of the lifetime table carry the
wrong ``Variant``; the data file name (``...MalE186AF488_...``) is authoritative.
:func:`read_lifetimes` corrects those rows and reports each correction.

Empty cells read as NaN (floats) or ``""`` (text). The column names of the arrays are the
reader's, listed in :data:`LIFETIME_FIELDS`, :data:`TITRATION_POINT_FIELDS` and
:data:`TITRATION_SUMMARY_FIELDS`.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: The shipped MalE data set.
EXAMPLE_FOLDER = Path(__file__).resolve().parents[2] / "examples" / "male"

LIFETIMES_FILE = "tcspc_fit_results.csv"
TITRATION_POINTS_FILE = "amino_acid_quenching_flt.csv"
TITRATION_SUMMARY_FILE = "titration_summary.csv"

#: Dyes whose name, written directly after ``MalE<site>``, marks a data file's site number.
LABEL_DYES = ("Atto655", "AF488", "Cy3B")

#: ``(array field, CSV column, kind)``; kind is ``int``, ``float`` or ``str``.
LIFETIME_FIELDS = (
    ("date", "Date", "int"),
    ("d2o_percent", "D2O %", "float"),
    ("variant", "Variant", "float"),
    ("dye", "Dye", "str"),
    ("condition", "Condition", "str"),
    ("tau_x", "tauX", "float"),
    ("data_path", "Data path name", "str"),
)
TITRATION_POINT_FIELDS = (
    ("date", "Date", "int"),
    ("dye", "Dye", "str"),
    ("amino_acid", "Amino acid", "str"),
    ("concentration_mM", "Concentration, mM", "float"),
    ("tau0_ns", "tauX0, ns", "float"),
    ("tau_x", "tauX", "float"),
)
TITRATION_SUMMARY_FIELDS = (
    ("dye", "dye", "str"),
    ("quencher", "quencher", "str"),
    ("n_dates", "n_dates", "int"),
    ("n_points", "n_points", "int"),
    ("tau0_ns", "tau0_ns", "float"),
    ("ksv_per_M", "KSV_per_M", "float"),
    ("ksv_err_per_M", "KSV_err_per_M", "float"),
    ("kq_per_M_s", "kq_per_M_s", "float"),
    ("kq_err_per_M_s", "kq_err_per_M_s", "float"),
)

#: Integer cells that are empty read as this value.
MISSING_INT = -1


def site_pattern(dyes=LABEL_DYES):
    """The regular expression that finds a site number in a data file name.

    Parameters
    ----------
    dyes : sequence of str, optional
        Dye names that may follow ``MalE<site>`` directly.

    Returns
    -------
    re.Pattern
        Case-insensitive pattern; group 1 is the site number.
    """
    return re.compile(r"MalE(\d+)(?:" + "|".join(re.escape(d) for d in dyes) + ")", re.IGNORECASE)


@dataclass(frozen=True)
class SiteCorrection:
    """One lifetime row whose site number was corrected from its data file name.

    Attributes
    ----------
    row : int
        Index of the row in the lifetime array.
    dye, condition : str
        The row's dye and condition.
    d2o_percent : float
        The row's heavy-water percentage.
    variant : float
        The site number as typed in the table (NaN when empty).
    site : int
        The site number from the file name, now in the ``site`` field.
    data_path : str
        The data file name the site was read from.
    """

    row: int
    dye: str
    condition: str
    d2o_percent: float
    variant: float
    site: int
    data_path: str


@dataclass(frozen=True)
class Measurements:
    """One data set of a quenching analysis.

    Attributes
    ----------
    lifetimes : numpy.ndarray
        Structured array, fields of :data:`LIFETIME_FIELDS` plus ``site`` (float, NaN when the
        row has no site, e.g. the free dye).
    titration_points : numpy.ndarray
        Structured array, fields of :data:`TITRATION_POINT_FIELDS`.
    titration_summary : numpy.ndarray
        Structured array, fields of :data:`TITRATION_SUMMARY_FIELDS`.
    corrections : tuple of SiteCorrection
        The lifetime rows whose site was corrected from the file name.
    folder : pathlib.Path
        Where the tables were read from.
    """

    lifetimes: np.ndarray
    titration_points: np.ndarray
    titration_summary: np.ndarray
    corrections: tuple[SiteCorrection, ...] = field(default_factory=tuple)
    folder: Path | None = None


def _convert(text, kind):
    """Convert one CSV cell.

    Parameters
    ----------
    text : str
        The cell as written.
    kind : {"int", "float", "str"}
        Target type.

    Returns
    -------
    int, float or str
        Empty cells give :data:`MISSING_INT`, NaN or ``""``.
    """
    text = text.strip() if kind != "str" else text
    if kind == "str":
        return text
    if text == "":
        return MISSING_INT if kind == "int" else math.nan
    if kind == "int":
        return int(float(text)) if "." in text or "e" in text.lower() else int(text)
    return float(text)


def read_table(path, fields):
    """Read a CSV file into a structured array.

    Parameters
    ----------
    path : str or pathlib.Path
        CSV file with a header row.
    fields : sequence of tuple
        ``(array field, CSV column, kind)`` triples; every column must be in the header. Other
        columns are ignored.

    Returns
    -------
    numpy.ndarray
        One record per data row, in file order. Text fields are sized to their longest value.

    Raises
    ------
    KeyError
        When a declared column is missing from the header.
    """
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    index = {}
    for name, column, _ in fields:
        if column not in header:
            raise KeyError(f"{Path(path).name}: column {column!r} is missing")
        index[name] = header.index(column)
    columns = {
        name: [_convert(row[index[name]] if index[name] < len(row) else "", kind) for row in rows]
        for name, _, kind in fields
    }
    dtype = []
    for name, _, kind in fields:
        if kind == "str":
            width = max([len(v) for v in columns[name]] + [1])
            dtype.append((name, f"U{width}"))
        else:
            dtype.append((name, "i8" if kind == "int" else "f8"))
    out = np.empty(len(rows), dtype=dtype)
    for name, _, _ in fields:
        out[name] = columns[name]
    return out


def correct_sites(lifetimes, pattern=None):
    """Add the ``site`` field: the typed variant, corrected from the data file name.

    A row is corrected when its file name carries a site number (``MalE<n><dye>``) that differs
    from the typed ``variant`` (or the variant is empty).

    Parameters
    ----------
    lifetimes : numpy.ndarray
        Structured array with ``variant`` and ``data_path`` fields.
    pattern : re.Pattern, optional
        Site pattern; :func:`site_pattern` by default.

    Returns
    -------
    tuple
        ``(array, corrections)``: a copy with the extra float field ``site`` and the list of
        :class:`SiteCorrection`.
    """
    pattern = pattern or site_pattern()
    dtype = lifetimes.dtype.descr + [("site", "f8")]
    out = np.empty(len(lifetimes), dtype=dtype)
    for name in lifetimes.dtype.names:
        out[name] = lifetimes[name]
    out["site"] = lifetimes["variant"]
    corrections = []
    for i, row in enumerate(lifetimes):
        match = pattern.search(str(row["data_path"]))
        if match is None:
            continue
        site = int(match.group(1))
        if not (float(row["variant"]) == site):  # NaN compares unequal: corrected as well
            out["site"][i] = site
            corrections.append(
                SiteCorrection(
                    row=i,
                    dye=str(row["dye"]),
                    condition=str(row["condition"]),
                    d2o_percent=float(row["d2o_percent"]),
                    variant=float(row["variant"]),
                    site=site,
                    data_path=str(row["data_path"]),
                )
            )
    return out, tuple(corrections)


def read_lifetimes(path):
    """Read the TCSPC lifetime table and correct its site numbers.

    Rows without a dye are dropped, as in the analysis.

    Parameters
    ----------
    path : str or pathlib.Path
        ``tcspc_fit_results.csv``.

    Returns
    -------
    tuple
        ``(array, corrections)``; see :func:`correct_sites`.
    """
    table = read_table(path, LIFETIME_FIELDS)
    table = table[np.char.str_len(table["dye"]) > 0]
    return correct_sites(table)


def read_titration_points(path, complete_only=True):
    """Read the free-dye titration points.

    Parameters
    ----------
    path : str or pathlib.Path
        ``amino_acid_quenching_flt.csv``.
    complete_only : bool, optional
        Drop rows without a dye or a lifetime (default), as the analysis does.

    Returns
    -------
    numpy.ndarray
        Fields of :data:`TITRATION_POINT_FIELDS`.
    """
    table = read_table(path, TITRATION_POINT_FIELDS)
    if complete_only:
        table = table[(np.char.str_len(table["dye"]) > 0) & np.isfinite(table["tau_x"])]
    return table


def read_titration_summary(path):
    """Read the experimenter's titration summary.

    Parameters
    ----------
    path : str or pathlib.Path
        ``titration_summary.csv``.

    Returns
    -------
    numpy.ndarray
        Fields of :data:`TITRATION_SUMMARY_FIELDS`; the Stern-Volmer constants in 1/M, the
        bimolecular quenching constants in 1/(M s).
    """
    return read_table(path, TITRATION_SUMMARY_FIELDS)


def load_measurements(folder=None):
    """Read the three tables of one data set.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Folder holding the three CSV files; the shipped MalE set (:data:`EXAMPLE_FOLDER`) by
        default.

    Returns
    -------
    Measurements
        The lifetimes (sites corrected), titration points and titration summary.
    """
    folder = Path(folder) if folder is not None else EXAMPLE_FOLDER
    lifetimes, corrections = read_lifetimes(folder / LIFETIMES_FILE)
    return Measurements(
        lifetimes=lifetimes,
        titration_points=read_titration_points(folder / TITRATION_POINTS_FILE),
        titration_summary=read_titration_summary(folder / TITRATION_SUMMARY_FILE),
        corrections=corrections,
        folder=folder,
    )
