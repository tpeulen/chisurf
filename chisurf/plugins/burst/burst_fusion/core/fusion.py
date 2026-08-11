"""Fusing the bursts of a burst-analysis folder into a new folder.

The step sits between burst selection and everything that consumes bursts. It
reads a burst-analysis folder, decides which of its bursts the *same molecule*
produced (via the recurrence ``P_same(tau)`` curve — see
:mod:`chisurf.core.fluorescence.burst.fusion`), and writes a **new** analysis
folder in which each such run of bursts is one burst.

Two properties make it safe to drop into the pipeline:

* **It never edits the source folder's bursts.** The fused bursts go to a new
  folder, so the un-fused analysis stays exactly as it was and a threshold can
  be tried, looked at, and thrown away. The only thing written back into the
  source is an optional ``fu4`` companion recording which fused burst each
  original burst went into — a per-burst column, the burst-companion contract's
  own unit, so a browser or ndX can colour the original bursts by their group.
* **The emitted ``.bur`` is re-derived from the photons**, not arithmetic on the
  source table. A burst on disk is one ``(first photon, last photon)`` interval,
  so a fused burst is the span across its fragments and *contains the photons
  between them*; every column — durations, per-detector counts, window rates,
  mean micro times — has to be recomputed over that span or the fused table
  would disagree with the photons any downstream step reads. That is what
  :func:`~chisurf.core.fio.fluorescence.burst.generate_burst_dataframe` does,
  and it is the same writer burst selection itself uses, so the fused folder is
  a burst folder in every respect: BVA, 2CDE, the MLE and H2MM read it with no
  idea that fusion happened.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
from collections import OrderedDict
from collections.abc import Sequence
from typing import Any

import numpy as np

from chisurf.core.datastore import (
    column_names as _column_names,
    concat_stores,
    numeric_column,
    row_count,
    store_from_arrays,
    take_where,
    write_csv_table,
)

from chisurf.core.fio.fluorescence.burst import (
    generate_burst_dataframe,
    read_bur_file,
    write_mti_summary,
)
from chisurf.core.fio.fluorescence.burst_companion import write_companion
from chisurf.core.fio.fluorescence.burst_manifest import (
    describe_tttr_source,
    read_analysis_manifest,
    reading_settings_for,
    write_analysis_manifest,
)
from chisurf.core.fluorescence.burst.fusion import (
    fuse_burst_frame,
    fusion_statistics,
    fusion_window,
    group_labels,
    group_slices,
)
from chisurf.core.fluorescence.burst.photons import is_sentinel_file_reference

from ..api.models import FusionAnalysis, FusionSettings, MeasurementFusion

logger = logging.getLogger(__name__)

#: Companion written into the *source* folder: which fused burst each original
#: burst joined. Deliberately a different ending from the one written beside the
#: fused bursts — fusing a folder that is itself a fusion output would otherwise
#: overwrite that folder's own companion with a same-named file of other columns.
SOURCE_COMPANION = "fg4"

#: Companion written beside the *fused* bursts: how each one was assembled.
FUSED_COMPANION = "fu4"

#: Record of the run, written into the fused folder's ``Info``.
FUSION_INFO = "fusion.json"


class FusionError(RuntimeError):
    """Raised when a folder cannot be fused or written."""


# ── reading a burst folder ──────────────────────────────────────────────────

def bur_files(analysis_folder) -> list[pathlib.Path]:
    """Return the ``.bur`` tables of an analysis folder, sorted by name.

    Accepts the analysis folder, its ``bi4_bur`` directory, or any folder
    holding ``.bur`` files directly, because callers hold different things.
    """
    folder = pathlib.Path(analysis_folder)
    for candidate in (folder / "bi4_bur", folder / "bur", folder):
        if candidate.is_dir():
            found = sorted(candidate.glob("*.bur"))
            if found:
                return found
    found = sorted(folder.glob("**/*.bur"))
    if not found:
        raise FusionError(f"no .bur burst tables under {folder}")
    return found


def analysis_root(analysis_folder) -> pathlib.Path:
    """Return the analysis folder itself, given it or its burst directory."""
    folder = pathlib.Path(analysis_folder)
    if folder.name.lower() in ("bi4_bur", "bur"):
        return folder.parent
    return folder


def data_rows(frame):
    """Drop the interleaved zero rows of a ``.bur`` table.

    The ``2n + 1`` zero-interleaved layout is a storage convention, not data:
    every other row is an all-zero sentinel whose ``First File`` cell is ``"0"``
    rather than a measurement. Fusion reasons about bursts, so it works on the
    ``n`` real rows and lets the writer re-interleave.
    """
    if "First File" not in _column_names(frame):
        return frame
    keep = np.array(
        [not is_sentinel_file_reference(v) for v in np.asarray(frame["First File"])],
        dtype=bool,
    )
    return take_where(frame, keep)


def read_measurements(analysis_folder) -> OrderedDict:
    """Read every ``.bur`` of a folder as ``{stem: burst rows}``."""
    frames: OrderedDict = OrderedDict()
    for path in bur_files(analysis_folder):
        frames[path.stem] = data_rows(read_bur_file(path))
    return frames


def burst_times_s(frame) -> np.ndarray:
    """Per-burst arrival times in seconds, from the burst table's own column.

    The mean macro time is used — the same quantity the ``P_same`` curve is
    built from — so a threshold read off the plotted curve means exactly what it
    appears to mean when it is applied to a pair of bursts.
    """
    for column, scale in (("Mean Macro Time (ms)", 1e-3), ("Mean Macro Time (s)", 1.0)):
        if column in _column_names(frame):
            return numeric_column(frame, column) * scale
    raise FusionError("burst table has no 'Mean Macro Time' column")


def proximity_ratios(frame) -> np.ndarray | None:
    """Per-burst proximity ratio of a burst table, or ``None`` when unavailable."""
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

    if row_count(frame) == 0:
        return None
    return proximity_ratio(frame)


# ── the analysis ────────────────────────────────────────────────────────────

def analyze(analysis_folder, settings: FusionSettings | None = None) -> FusionAnalysis:
    """Decide which bursts of a folder fuse, without writing anything.

    Parameters
    ----------
    analysis_folder : path-like
        A burst-analysis folder (or its ``bi4_bur`` directory).
    settings : FusionSettings, optional
        Fusion settings; defaults are used when omitted.

    Returns
    -------
    FusionAnalysis
        The ``P_same`` curve, the recurrence window, the per-measurement
        grouping, a table-level preview of the fused bursts and the before/after
        statistics.
    """
    settings = settings or FusionSettings()
    root = analysis_root(analysis_folder)
    frames = read_measurements(analysis_folder)
    if not frames:
        raise FusionError(f"no bursts to fuse in {root}")

    times = {stem: burst_times_s(frame) for stem, frame in frames.items()}
    pooled = fusion_window(
        list(times.values()),
        threshold=settings.threshold,
        tau_min_s=settings.tau_min_s,
        tau_max_s=settings.tau_max_s,
        n_bins=settings.n_bins,
        min_pairs=settings.min_pairs,
    )

    windows_by_stem: dict[str, Any] = {}
    measurements: list[MeasurementFusion] = []
    tau_used = capped_window(pooled.tau_max_s, settings)
    for stem, frame in frames.items():
        if settings.pool_measurements:
            window = pooled
        else:
            window = fusion_window(
                [times[stem]],
                threshold=settings.threshold,
                tau_min_s=settings.tau_min_s,
                tau_max_s=settings.tau_max_s,
                n_bins=settings.n_bins,
                min_pairs=settings.min_pairs,
            )
        windows_by_stem[stem] = window
        labels = group_labels(
            times[stem], capped_window(window.tau_max_s, settings), max_group=settings.max_group
        )
        measurements.append(
            MeasurementFusion(
                stem=stem,
                source=frame,
                fused=fuse_burst_frame(frame, labels),
                labels=labels,
            )
        )

    before = concat_stores([m.source for m in measurements])
    after = concat_stores([m.fused for m in measurements])
    # Labels of different measurements collide; offset them so the pooled
    # group-size statistics count each measurement's groups separately.
    offset = 0
    all_labels: list[np.ndarray] = []
    for m in measurements:
        all_labels.append(np.asarray(m.labels, dtype=int) + offset)
        offset += int(m.labels.max()) + 1 if len(m.labels) else 0
    labels = np.concatenate(all_labels) if all_labels else np.zeros(0, dtype=int)

    statistics = fusion_statistics(before, after, labels)
    statistics["tau_max_s"] = float(pooled.tau_max_s)
    statistics["tau_used_s"] = float(tau_used)
    statistics["gap_capped"] = bool(tau_used < pooled.tau_max_s)
    statistics["threshold"] = float(pooled.threshold)
    statistics["resolved"] = bool(pooled.resolved)
    statistics["n_measurements"] = len(measurements)
    statistics["proximity_ratio"] = _ratio_statistics(before, after)
    return FusionAnalysis(
        folder=root,
        settings=settings,
        window=pooled,
        windows_by_stem=windows_by_stem,
        tau_used_s=float(tau_used),
        measurements=measurements,
        statistics=statistics,
    )


def capped_window(tau_max_s: float, settings: FusionSettings) -> float:
    """Return the window actually fused on: the curve's, capped by ``max_gap_ms``.

    The probability answers "same molecule?"; the cap answers "at what cost?".
    At low concentration ``P_same`` stays above any reasonable threshold out to
    tens of milliseconds, and bridging such a gap is *correct* about the molecule
    while being ruinous for the burst — a ``.bur`` row is one interval, so those
    milliseconds of background end up inside it. Capping keeps the step to the
    case it exists for: a single passage the search cut in two.
    """
    if settings.max_gap_ms and settings.max_gap_ms > 0:
        return float(min(tau_max_s, settings.max_gap_ms * 1e-3))
    return float(tau_max_s)


def _ratio_statistics(before, after) -> dict[str, Any]:
    """Proximity-ratio mean/std/count before and after fusion."""
    out: dict[str, Any] = {}
    for name, frame in (("before", before), ("after", after)):
        values = proximity_ratios(frame)
        if values is None:
            out[name] = {"mean": float("nan"), "std": float("nan"), "n": 0}
            continue
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values)]
        out[name] = {
            "mean": float(values.mean()) if values.size else float("nan"),
            "std": float(values.std()) if values.size else float("nan"),
            "n": int(values.size),
        }
    return out


# ── writing the fused folder ────────────────────────────────────────────────

def default_output_folder(analysis: FusionAnalysis) -> pathlib.Path:
    """Sibling folder name a fused analysis lands in by default.

    The threshold is in the name because it is the only choice that changes the
    result, and a run at a second threshold must not silently overwrite the
    first.
    """
    from chisurf.plugins.burst.burst_selection.api.io import get_unique_folder_path

    root = pathlib.Path(analysis.folder)
    return get_unique_folder_path(
        root.parent / f"{root.name}_fused_p{analysis.settings.threshold:.2f}"
    )


def reading_settings(analysis_folder, source_name: str) -> dict[str, Any]:
    """Return the recorded reading settings of one measurement of a burst folder."""
    manifest = read_analysis_manifest(analysis_root(analysis_folder))
    return reading_settings_for(source_name, manifest)


def _detector_definition(
    analysis: FusionAnalysis,
    source_name: str,
    detectors: dict[str, Any] | None,
    windows: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], float | None, str | None]:
    """Resolve detectors, windows, macro-time resolution and container type.

    Explicit arguments win; otherwise the burst folder's own reading manifest is
    used. Without either there is nothing to regenerate the per-detector columns
    from, and a fused table missing them would quietly break every downstream
    step — so this raises rather than writing a table that only looks right.
    """
    entry = reading_settings(analysis.folder, source_name)
    recorded = dict(entry.get("settings") or {})
    resolved_detectors = detectors if detectors is not None else recorded.get("detectors") or {}
    resolved_windows = windows if windows is not None else recorded.get("windows") or {}
    resolution = recorded.get("macro_time_resolution") or entry.get("macro_time_resolution")
    container = entry.get("container_type")
    if not resolved_detectors:
        raise FusionError(
            f"no detector definition for {source_name}: the source folder has no "
            "reading manifest (Info/analysis.json), so the fused burst table "
            "cannot be regenerated. Pass the detector setup explicitly (the "
            "workflow's channel definition supplies it in the GUI)."
        )
    return resolved_detectors, resolved_windows, resolution, container


def _merged_intervals(
    frame, labels: np.ndarray, n_photons: int
) -> tuple[list[tuple[int, int]], list[np.ndarray]]:
    """Fused ``(first, last)`` photon intervals and the rows each came from.

    Degenerate intervals are dropped *here*, with the rows that produced them,
    because :func:`generate_burst_dataframe` silently skips them too — and a
    companion built from the group list rather than the emitted rows would then
    be one row long and misalign every burst after it.
    """
    first = numeric_column(frame, "First Photon")
    last = numeric_column(frame, "Last Photon")
    intervals: list[tuple[int, int]] = []
    kept: list[np.ndarray] = []
    for rows in group_slices(labels):
        start = int(np.nanmin(first[rows]))
        stop = int(np.nanmax(last[rows]))
        if stop <= start or stop >= n_photons or start < 0:
            logger.debug("fusion: dropping degenerate burst interval (%s, %s)", start, stop)
            continue
        intervals.append((start, stop))
        kept.append(rows)
    return intervals, kept


def write_fused_analysis(
    analysis: FusionAnalysis,
    output_folder=None,
    detectors: dict[str, Any] | None = None,
    windows: dict[str, Any] | None = None,
    data_folder=None,
) -> dict[str, Any]:
    """Write a fused analysis as a new burst-analysis folder.

    Parameters
    ----------
    analysis : FusionAnalysis
        The result of :func:`analyze`.
    output_folder : path-like, optional
        Target folder; a threshold-named sibling of the source by default.
    detectors, windows : dict, optional
        Detector definition and PIE windows to regenerate the burst columns
        with. Default: whatever the source folder's reading manifest recorded.
    data_folder : path-like, optional
        Where the raw measurements live. Default: the source folder's parent,
        the layout burst selection writes.

    Returns
    -------
    dict
        ``output_folder``, the ``bur_files`` written, per-measurement burst
        counts and the resolved recurrence window.
    """
    from chisurf.core.fio.staging import open_tttr

    target = pathlib.Path(output_folder) if output_folder else default_output_folder(analysis)
    bur_dir = target / "bi4_bur"
    bur_dir.mkdir(parents=True, exist_ok=True)
    data_dir = pathlib.Path(data_folder) if data_folder else pathlib.Path(analysis.folder).parent

    written: list[str] = []
    per_measurement: dict[str, dict[str, int]] = {}
    sources: list[dict[str, Any]] = []

    for measurement in analysis.measurements:
        frame = measurement.source
        if len(frame) == 0:
            continue
        source_name = str(np.asarray(frame["First File"])[0])
        det, win, resolution, container = _detector_definition(
            analysis, source_name, detectors, windows
        )
        path = data_dir / source_name
        if not path.exists():
            raise FusionError(
                f"raw measurement {path} not found — the fused burst table is "
                "regenerated from the photons, so the source data must be readable"
            )
        routine = container or (
            None
            if not analysis.settings.file_type or analysis.settings.file_type.lower() == "auto"
            else analysis.settings.file_type
        )
        tttr = open_tttr(path, routine)

        intervals, kept = _merged_intervals(frame, measurement.labels, len(tttr))
        fused = generate_burst_dataframe(
            intervals,
            path,
            tttr,
            windows=win,
            detectors=det,
            include_interleaved_zeros=True,
            macro_time_resolution=resolution,
        )
        bur_path = bur_dir / f"{measurement.stem}.bur"
        write_csv_table(bur_path, fused)
        written.append(str(bur_path))
        per_measurement[measurement.stem] = {
            "bursts_before": int(len(frame)),
            "bursts_after": int(len(intervals)),
        }

        _write_fused_companion(target, measurement, frame, intervals, kept, fused)
        if analysis.settings.write_source_companion:
            _write_source_companion(analysis.folder, measurement, frame)

        macro_times = tttr.macro_times
        if len(macro_times):
            write_mti_summary(
                path,
                target,
                float(macro_times[-1]) * float(resolution or tttr.header.macro_time_resolution),
                append=True,
            )
        sources.append(
            describe_tttr_source(
                path,
                tttr,
                container_type=container,
                settings={
                    "windows": dict(win),
                    "detectors": dict(det),
                    "macro_time_resolution": resolution,
                },
            )
        )

    _write_info(analysis, target, per_measurement)
    if sources:
        import chisurf

        write_analysis_manifest(
            target,
            sources,
            settings={
                "burst_fusion": analysis.settings.to_dict(),
                "fused_from": str(analysis.folder),
                "tau_max_s": float(analysis.window.tau_max_s),
                "tau_used_s": float(analysis.tau_used_s),
            },
            software_version=getattr(chisurf, "__version__", None),
        )

    logger.info(
        "Burst fusion: %d -> %d bursts (P_same >= %.2f, gaps <= %.4g ms) -> %s",
        analysis.statistics["n_bursts_before"],
        sum(v["bursts_after"] for v in per_measurement.values()),
        analysis.settings.threshold,
        analysis.tau_used_s * 1e3,
        target,
    )
    return {
        "output_folder": str(target),
        "bur_files": written,
        "per_measurement": per_measurement,
        "tau_max_s": float(analysis.window.tau_max_s),
        "tau_used_s": float(analysis.tau_used_s),
        "resolved": bool(analysis.window.resolved),
    }


def write_fusion_container(
    source_path,
    measurement: MeasurementFusion,
    frame,
    fused,
    *,
    parameters: dict | None = None,
) -> str:
    """Write the fused bursts and how they were assembled, in one container.

    Fusion is the case the positional companion format could not express, in
    both directions at once. A fused burst is **coarser** than the bursts it was
    made from, so it does not fit their grid; and it has **several parents**,
    which a one-row-per-burst companion has no way to name. The legacy writer
    worked around both by putting the fused bursts in a new folder and writing
    the membership back into the *source* analysis's directory -- mutating
    somebody else's output to carry a relation the format could not hold.

    Here the membership is an artifact of its own: one row per source burst
    naming the fused burst it went into, joined by declared key. Nothing is
    written outside this measurement.

    Parameters
    ----------
    source_path : str or Path
        The instrument file the original bursts were found in.
    measurement : MeasurementFusion
        Carries ``labels`` -- for each source burst, the fused burst it joined.
    frame : pandas.DataFrame
        The source bursts.
    fused : pandas.DataFrame
        The fused bursts.
    parameters : dict, optional
        The fusion settings; their hash is the identity of the run.

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.fluorescence.burst_container import (
        deinterleave_bursts,
        open_measurement,
    )

    labels = np.asarray(measurement.labels, dtype=int)
    rows = deinterleave_bursts(frame)
    mapping = store_from_arrays(
        {
            "source_row": np.arange(labels.size, dtype=np.int64),
            "fused_row": labels.astype(np.int64),
        }
    )

    with open_measurement(source_path) as m:
        bursts = m._f.find("bursts")
        parents = [p for p in (m.instrument_uid, bursts) if p]
        fused_uid = m.put_table(
            "fused bursts",
            deinterleave_bursts(fused),
            artifact_kind="burst_table",
            operation_type="burst_fusion",
            row_grain="burst",
            parameters=parameters,
            derived_from=parents,
        )
        m.put_table(
            "fusion membership",
            mapping,
            artifact_kind="row_mapping",
            operation_type="burst_fusion",
            row_grain="pair",
            parameters=parameters,
            derived_from=[bursts, fused_uid] if bursts else [fused_uid],
            source_row_column="source_row",
            target_row_column="fused_row",
        )
        return str(m.path)


def _write_source_companion(folder, measurement: MeasurementFusion, frame) -> None:
    """Record each original burst's fused-burst membership beside the source."""
    labels = np.asarray(measurement.labels, dtype=int)
    if labels.size == 0:
        return
    sizes = np.bincount(labels)
    times = burst_times_s(frame)
    lag = np.zeros(labels.size)
    lag[1:] = np.diff(times) * 1e3
    rows = np.column_stack(
        [labels.astype(float), sizes[labels].astype(float), lag]
    )
    write_companion(
        analysis_root(folder),
        SOURCE_COMPANION,
        measurement.stem,
        ["Fusion Group", "Fusion Group Size", "Fusion Lag (ms)"],
        rows,
    )


def _write_fused_companion(
    target,
    measurement: MeasurementFusion,
    frame,
    intervals: Sequence[tuple[int, int]],
    kept: Sequence[np.ndarray],
    fused,
) -> None:
    """Record how each fused burst was assembled, beside the fused bursts.

    ``Fused Bursts`` is 1 for a burst fusion left alone, so the column is a
    filter downstream: keep only fused bursts, or only untouched ones, without
    having to diff two folders. ``Fused Gap Photons`` is the price of the
    span — the photons that fall between the fragments and are now inside the
    burst — which is the number to look at when deciding whether a threshold
    went too far.
    """
    if not intervals:
        return
    counts = numeric_column(frame, "Number of Photons")
    rows = []
    fused_rows = data_rows(fused)
    span_photons = numeric_column(fused_rows, "Number of Photons")
    for i, group in enumerate(kept):
        signal = float(np.nansum(counts[group]))
        span = float(span_photons[i]) if i < span_photons.size else signal
        rows.append([float(len(group)), max(span - signal, 0.0)])
    write_companion(
        target,
        FUSED_COMPANION,
        measurement.stem,
        ["Fused Bursts", "Fused Gap Photons"],
        rows,
    )


def _write_info(analysis: FusionAnalysis, target, per_measurement: dict[str, Any]) -> None:
    """Write the human-readable record of the run into ``Info/``."""
    info_dir = pathlib.Path(target) / "Info"
    info_dir.mkdir(parents=True, exist_ok=True)
    window = analysis.window
    payload = {
        "source_folder": str(analysis.folder),
        "settings": analysis.settings.to_dict(),
        "tau_max_s": float(window.tau_max_s),
        "tau_used_s": float(analysis.tau_used_s),
        "resolved": bool(window.resolved),
        "statistics": analysis.statistics,
        "per_measurement": per_measurement,
        "p_same_curve": {
            "tau_s": [float(v) for v in window.tau_s],
            "p_same": [None if not np.isfinite(v) else float(v) for v in window.p_same],
            "pairs": [float(v) for v in window.counts],
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (info_dir / FUSION_INFO).write_text(json.dumps(payload, indent=2, default=str))


def fuse_folder(
    analysis_folder,
    settings: FusionSettings | None = None,
    output_folder=None,
    detectors: dict[str, Any] | None = None,
    windows: dict[str, Any] | None = None,
    data_folder=None,
) -> dict[str, Any]:
    """Analyse and write in one call — the headless entry point.

    Returns
    -------
    dict
        The :func:`write_fused_analysis` payload plus the run statistics.
    """
    analysis = analyze(analysis_folder, settings)
    result = write_fused_analysis(
        analysis,
        output_folder=output_folder,
        detectors=detectors,
        windows=windows,
        data_folder=data_folder,
    )
    result["statistics"] = analysis.statistics
    return result
