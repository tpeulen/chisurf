"""The calibration's column schema, read from the declaration beside it.

One file decides what a stored calibration is called, and both directions use
it: the writer turns a factor into a column, the reader turns a column back into
a factor. Splitting that across a writer and a reader is how a stored artifact
and the code that loads it drift apart without either being wrong on its own.

The names are flrCIF's (`_flr_fret_calibration_parameters`,
`_flr_fret_forster_radius`), not chisurf's — see
``calibration_columns.yaml`` for why that matters.
"""

from __future__ import annotations

import functools
import pathlib

import yaml

__all__ = ["calibration_columns", "column_for_factor", "factor_for_column",
           "is_derived"]

_DECLARATION = pathlib.Path(__file__).with_name("calibration_columns.yaml")

#: Headers earlier versions wrote, mapped to the factor they held. Kept so a
#: container written before the schema was anchored still restores: the file on
#: disk is the thing that cannot be migrated.
_LEGACY_COLUMNS = {"r0": "r0"}


@functools.lru_cache(maxsize=1)
def calibration_columns() -> tuple[dict, ...]:
    """Every declared calibration column, in the order the paper introduces them."""
    data = yaml.safe_load(_DECLARATION.read_text(encoding="utf-8"))
    return tuple(dict(entry) for entry in data["columns"])


def column_for_factor(factor: str) -> str | None:
    """The column a calibration factor is written under, or ``None``."""
    for spec in calibration_columns():
        if spec["factor"] == factor:
            return spec["column"]
    return None


def is_derived(column: str) -> bool:
    """Whether a column is a function of the others.

    ``gG/gR`` is ``(phi_a/phi_d)/gamma``. It is written so the file can be read
    without recomputing it, and never applied back — restoring a derived value
    on top of the quantities it derives from is how the two stop agreeing.
    """
    for spec in calibration_columns():
        if spec["column"] == column:
            return bool(spec.get("derived", False))
    return False


def factor_for_column(column: str) -> str | None:
    """The calibration factor a column holds, or ``None``.

    Understands the headers older containers used, because a file already
    written cannot be asked to follow a newer schema.
    """
    for spec in calibration_columns():
        if spec["column"] == column:
            return spec["factor"]
    return _LEGACY_COLUMNS.get(column)
