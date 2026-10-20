"""Declared table layouts of the quenching analysis, read from ``settings/analysis/*.yaml``.

A declaration file lists, per table, the columns the analysis writes: the header (``column``),
the numpy kind (``dtype``), the units, the vocabulary ``term`` that anchors the column in the
mmfdb/flrCIF dictionaries, and a description. The analysis code fills record arrays whose
fields are exactly these columns, so a renamed or added column is a settings change.

A declaration may also carry a ``settings`` mapping: the selections an analysis step makes
(which dye is the reference, how many prior points a site error is worth, ...). The algorithms
read them from there instead of hardcoding them.
"""

from __future__ import annotations

from functools import cache, lru_cache
from pathlib import Path

import numpy as np
import yaml

#: ``settings/analysis/`` of the plugin.
ANALYSIS_SETTINGS_DIR = Path(__file__).resolve().parents[2] / "settings" / "analysis"

#: The measurement-statistics declaration (titrations, water, lifetime errors, kQ per dye).
MEASUREMENT_COLUMNS = ANALYSIS_SETTINGS_DIR / "measurement_columns.yaml"

_KINDS = {"float": "f8", "int": "i8", "bool": "?"}


@cache
def _read(path):
    """Parse one declaration file (cached per path).

    Parameters
    ----------
    path : str
        Path of the YAML file.

    Returns
    -------
    dict
        The parsed document.
    """
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def declaration(path=MEASUREMENT_COLUMNS):
    """Return a declaration document.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Declaration file; the measurement columns by default.

    Returns
    -------
    dict
        Table name -> ``{"description", "columns"}``, plus an optional ``settings`` mapping.
    """
    return _read(str(path))


def settings(path=MEASUREMENT_COLUMNS):
    """Return the ``settings`` mapping of a declaration file.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Declaration file; the measurement columns by default.

    Returns
    -------
    dict
        The selections declared beside the columns (empty when there are none).
    """
    return dict(declaration(path).get("settings") or {})


def columns(table, path=MEASUREMENT_COLUMNS):
    """Return the column entries of one declared table.

    Parameters
    ----------
    table : str
        Table name, a top-level key of the declaration.
    path : str or pathlib.Path, optional
        Declaration file; the measurement columns by default.

    Returns
    -------
    list of dict
        One mapping per column (``column``, ``dtype``, ``units``, ``term``, ``description``).

    Raises
    ------
    KeyError
        When the table is not declared.
    """
    doc = declaration(path)
    if table not in doc or "columns" not in (doc[table] or {}):
        raise KeyError(f"{Path(path).name}: no table {table!r}")
    return list(doc[table]["columns"])


def table_dtype(table, path=MEASUREMENT_COLUMNS, text_width=16):
    """The numpy dtype of a declared table.

    Parameters
    ----------
    table : str
        Table name.
    path : str or pathlib.Path, optional
        Declaration file; the measurement columns by default.
    text_width : int, optional
        Width of ``str`` columns.

    Returns
    -------
    numpy.dtype
        Structured dtype, one field per declared column, in declared order.
    """
    fields = []
    for entry in columns(table, path):
        kind = entry.get("dtype", "float")
        fields.append((entry["column"], f"U{text_width}" if kind == "str" else _KINDS[kind]))
    return np.dtype(fields)


def make_table(table, rows, path=MEASUREMENT_COLUMNS):
    """Build a declared table from row mappings.

    Parameters
    ----------
    table : str
        Table name.
    rows : sequence of dict
        One mapping per row, keyed by the declared column names. Every declared column must be
        present; extra keys are an error, so a column cannot be written without a declaration.
    path : str or pathlib.Path, optional
        Declaration file; the measurement columns by default.

    Returns
    -------
    numpy.ndarray
        Structured array with :func:`table_dtype`; text columns sized to their longest value.

    Raises
    ------
    KeyError
        When a row misses a declared column or carries an undeclared one.
    """
    rows = list(rows)
    names = [entry["column"] for entry in columns(table, path)]
    declared = set(names)
    for row in rows:
        if set(row) != declared:
            missing = sorted(declared - set(row))
            extra = sorted(set(row) - declared)
            raise KeyError(f"table {table!r}: missing {missing}, undeclared {extra}")
    width = max([len(str(row[n])) for row in rows for n in names] + [1])
    dtype = table_dtype(table, path, text_width=width)
    out = np.empty(len(rows), dtype=dtype)
    for name in names:
        out[name] = [row[name] for row in rows]
    return out
