"""Burst-wise diffusion times, written into the measurement's container.

The legacy `td4` companion has the defect the companion contract exists to
prevent, in its own writer: the row grid is built from
``df['Burst Index'].unique()`` — the bursts the correlator produced a result
for — while the companion is merged onto the burst table **by position**. A
burst the correlator skipped (too few photons, a pair with no counts) is
therefore not a blank row but a *missing* one, and every burst after it is
merged against the wrong burst's diffusion time. The misalignment is silent:
the file has the right shape, the columns have the right names, and only the
values are attributed to the wrong bursts.

Here the burst number is a declared key rather than a row position, so a burst
without a result is simply absent and says so. A correlation pair stays a
column, which the legacy writer had right — one column per pair, one row per
burst.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["write_fcs_container"]

#: Units for the columns this analysis names itself.
#:
#: A diffusion time is milliseconds — the shared table has no entry for it,
#: because the burst columns that carry a time say so in their label and these
#: do not: ``td_mean__green-red`` is a pair name in the suffix, not a unit.
FCS_COLUMN_UNITS: dict[str, str] = {
    "Burst Index": "dimensionless",
    "td_mean": "milliseconds",
    "td_peak": "milliseconds",
    "td_mean_ms": "milliseconds",
    "td_peak_ms": "milliseconds",
}


def _units_for(columns) -> dict[str, str]:
    """Return ``{column: unit}``, matching the per-pair suffix by prefix.

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
        if text in FCS_COLUMN_UNITS:
            out[text] = FCS_COLUMN_UNITS[text]
        elif text.startswith("td_"):
            out[text] = "milliseconds"
    return out


def write_fcs_container(
    source: str | Path,
    table,
    *,
    parameters: Mapping[str, Any] | None = None,
    out_dir: str | Path | None = None,
) -> str:
    """Write one measurement's burst-wise diffusion times into its container.

    Parameters
    ----------
    source : str or Path
        The instrument file the bursts came from, or the container itself.
    table : tttrlib.DataStore or pandas.DataFrame
        One row per burst that produced a result, carrying ``Burst Index`` and
        one ``td_*`` column per correlation pair. Bursts without a result are
        left out; the key is what makes that safe.
    parameters : mapping, optional
        The correlator settings — channel pairs, cascades, bins. Their hash is
        the identity of the run.
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import column_names
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    return write_burst_artifact(
        source,
        table,
        name="burst fcs",
        artifact_kind="fcs_correlation",
        operation_type="burst_correlation",
        row_grain="burst",
        parameters=parameters,
        derived_from="bursts",
        # The join the legacy format did by counting. Declaring it is the whole
        # difference: a burst the correlator skipped is an absent row rather
        # than a one-row shift in everything after it.
        source_row_column="Burst Index",
        target_row_column="Burst Index",
        units=_units_for(column_names(table)),
        out_dir=out_dir,
    )
