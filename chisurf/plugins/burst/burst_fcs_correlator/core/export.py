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

import yaml

RESULT_COLUMNS = yaml.safe_load(Path(__file__).with_name("result_columns.yaml").read_text())["columns"]

__all__ = ["write_fcs_container", "write_fcs_results"]

#: Units for the columns this analysis names itself.
#:
#: A diffusion time is milliseconds — the shared table has no entry for it,
#: because the burst columns that carry a time say so in their label and these
#: do not: ``td_mean__green-red`` is a pair name in the suffix, not a unit.
FCS_COLUMN_UNITS: dict[str, str] = {"Burst Index": "dimensionless"}
for _feature in RESULT_COLUMNS:
    for _name in (_feature["column"], _feature["source"]):
        FCS_COLUMN_UNITS[_name] = _feature["unit"]



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
        else:
            for feature in RESULT_COLUMNS:
                if text.startswith(feature["column"] + "__"):
                    out[text] = feature["unit"]
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



def write_fcs_results(rows, burst_counts, *, parameters=None, cancel_check=None):
    """Publish indexed FCS results into each measurement's container.

    Parameters
    ----------
    rows : sequence of mapping
        Results with First File, Burst Folder, Burst Index and diffusion times.
    burst_counts : mapping
        Actual input-range count by (analysis folder, measurement stem).
    parameters : mapping, optional
        Scientific settings and selected channel pairs for provenance.
    cancel_check : callable, optional
        Raises before publication when the run has been cancelled.

    Returns
    -------
    list of pathlib.Path
        Published containers. The legacy ``td4`` companion is made on request by
        :func:`~chisurf.core.fio.fluorescence.legacy_export.export_legacy`.
    """
    import hashlib
    import json
    import logging
    import shutil
    from contextlib import ExitStack
    from tempfile import TemporaryDirectory

    import numpy as np

    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import container_for

    groups = {}
    for row in rows:
        source = Path(row["First File"])
        root = Path(row.get("Burst Folder", source.parent))
        groups.setdefault((root, source), []).append(row)
    def fingerprint(path):
        if not path.exists():
            return None
        stat = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return stat.st_ino, stat.st_size, stat.st_mtime_ns, digest

    prepared = []
    original = {}
    staged_containers = {}
    with ExitStack() as stack:
        for (root, source), group in groups.items():
            if cancel_check is not None:
                cancel_check()
            columns = {}
            has_pairs = any("pair_name" in row for row in group)
            for row in group:
                bid = int(row["Burst Index"])
                suffix = "__" + str(row["pair_name"]) if has_pairs else ""
                for feature in RESULT_COLUMNS:
                    key, prefix = feature["source"], feature["column"]
                    if key in row:
                        columns.setdefault(prefix + suffix, {})[bid] = float(row[key])
            if not columns:
                continue
            ids = sorted({int(row["Burst Index"]) for row in group})
            count = burst_counts.get((str(root), source.stem))
            if count is None:
                count = ids[-1] + 1
                logging.warning("Missing burst count for %s; inferring %s from results", source, count)
            if any(bid < 0 or bid >= count for bid in ids):
                raise ValueError("A result lies outside the declared input burst grid")
            sparse = {"Burst Index": np.asarray(ids, dtype=float)}
            for j, (name, values) in enumerate(columns.items()):
                sparse[name] = np.asarray([values.get(bid, np.nan) for bid in ids])
            # Copy an existing PTO before extending it: all scientific lineage
            # survives, and a failed/cancelled run leaves its original untouched.
            stage = Path(stack.enter_context(TemporaryDirectory(prefix=".burst-fcs-", dir=source.parent)))
            target = container_for(source)
            original.setdefault(target, fingerprint(target))
            staged_source = staged_containers.get(target, source)
            if target not in staged_containers:
                if target.exists():
                    shutil.copy2(target, stage / target.name)
                if source.suffix == ".pto":
                    staged_source = stage / source.name
            written = Path(write_fcs_container(staged_source, store_from_arrays(sparse),
                                               parameters=parameters, out_dir=stage))
            if target not in staged_containers:
                staged_containers[target] = written
                prepared.append((written, target))
        if cancel_check is not None:
            cancel_check()
        if any(fingerprint(target) != initial for target, initial in original.items()):
            raise RuntimeError("Burst FCS outputs changed while the run was preparing")
        backups = []
        published = []
        expected = {}
        try:
            for i, (staged, target) in enumerate(prepared):
                if cancel_check is not None:
                    cancel_check()
                if fingerprint(target) != original[target]:
                    raise RuntimeError(f"Burst FCS output changed before publication: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = staged.parent / f"rollback-{i}"
                if target.exists():
                    shutil.copy2(target, backup)
                    backups.append((target, backup))
                else:
                    backups.append((target, None))
                staged.replace(target)
                published.append(target)
                expected[target] = fingerprint(target)
            if cancel_check is not None:
                cancel_check()
        except BaseException:
            for target, backup in reversed(backups):
                if target not in published:
                    continue
                if fingerprint(target) != expected[target]:
                    raise RuntimeError(f"Concurrent change prevents Burst FCS rollback: {target}")
                if backup is not None:
                    backup.replace(target)
                elif target in published:
                    target.unlink()
            raise
        return published
