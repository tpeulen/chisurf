"""Burst selection and summarization functions."""

from __future__ import annotations

import json
import logging
import shutil
import time
import warnings
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from chisurf.core.datastore import rows_from_table, store_from_rows
import tttrlib

import chisurf

from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe, write_mti_summary
from chisurf.core.fio.fluorescence.burst_manifest import (
    describe_tttr_source,
    write_analysis_manifest,
)
from chisurf.core.fluorescence.burst import burst_filter, count_rate_filter, cusum_filter
from chisurf.core.fluorescence.burst import tttrlib_search
from chisurf.core.fluorescence.burst.tttrlib_search import tttrlib_burst_filter
import chisurf.core.fluorescence.burst.kalman as kalman_mod
from chisurf.core.fluorescence.burst.utils import create_array_with_ones
from chisurf.core.math.signal import fill_small_gaps_in_array
from chisurf.core.math.signal import find_bursts as signal_find_bursts

from .io import (
    get_unique_folder_path,
    load_tttr,
    write_bur,
    write_container,
    write_hdf5,
    zip_output_folder,
)
from .serialization import to_jsonable
from .models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    PhotonFilterSettings,
)



def _manifest_settings(analysis_settings) -> dict:
    """The burst-search settings, in a JSON-safe shape for the manifest."""
    try:
        return {
            k: v for k, v in asdict(analysis_settings).items()
            if isinstance(v, (bool, int, float, str, list, dict, type(None)))
        }
    except Exception:
        return {}


def _delta_macro_time_ms(tttr: tttrlib.TTTR) -> np.ndarray:
    """Return delta macro times in milliseconds."""
    macro_times = tttr.macro_times
    d_t = np.diff(macro_times, prepend=macro_times[0])
    return d_t * tttr.header.macro_time_resolution * 1000.0


def _delta_macro_time_mask(
    tttr: tttrlib.TTTR, delta_settings: "DeltaMacroTimeFilterSettings"
) -> np.ndarray:
    """Boolean mask of photons whose inter-photon gap is inside ``[dT_min, dT_max]`` (ms).

    A photon-stream pre-filter: photons with a large delta macro time are the
    sparse, low-rate background between bursts, so keeping only the interval
    thins the stream to the burst-like photons before the burst search runs.
    """
    mask = np.ones(len(tttr), dtype=bool)
    if not (delta_settings.dT_min_active or delta_settings.dT_max_active):
        return mask
    delta_t = _delta_macro_time_ms(tttr)
    if delta_settings.dT_min_active:
        mask &= delta_t >= delta_settings.dT_min
    if delta_settings.dT_max_active:
        mask &= delta_t <= delta_settings.dT_max
    return mask


def _run_burst_search(
    tttr: tttrlib.TTTR,
    settings: PhotonFilterSettings,
    burst_detection: BurstDetectionSettings | None,
) -> np.ndarray:
    """Run the configured burst search on ``tttr`` and return a boolean mask.

    Only the search itself lives here — the channel/micro-time/delta-macro-time
    pre-filters are applied by :func:`apply_photon_filters`. Factoring it out is
    what lets the search run on a *reduced* photon stream (the delta-macro-time
    pre-filter) rather than the whole file.
    """
    n = len(tttr)
    used_filter = BurstFilterMode(settings.used_filter)

    # A registry-driven tttrlib search needs the tttrlib burst-search registry.
    # When the installed tttrlib does not publish it, fall back to the built-in
    # sliding-window burst search instead of aborting the whole analysis (which
    # would leave every downstream plot empty). Warn once so the substitution is
    # visible; the user can upgrade tttrlib or pick a built-in mode explicitly.
    if used_filter == BurstFilterMode.TTTRLIB and not tttrlib_search.is_available():
        import chisurf
        chisurf.logging.warning(
            "burst_selection: the installed tttrlib publishes no burst-search "
            "registry; falling back to the built-in sliding-window burst search. "
            "Upgrade tttrlib or choose a built-in filter mode to silence this."
        )
        used_filter = BurstFilterMode.BURST

    if used_filter == BurstFilterMode.COUNT_RATE:
        count_rate_settings = settings.count_rate_filter
        selection = count_rate_filter(
            tttr=tttr,
            n_ph_max=count_rate_settings.n_ph_max,
            time_window=count_rate_settings.time_window,
            invert=settings.invert_filter or count_rate_settings.invert,
            make_mask=True,
        )
        return np.asarray(selection) >= 0

    if used_filter == BurstFilterMode.BURST:
        detection = burst_detection or BurstDetectionSettings()
        detection_window = min(
            settings.delta_macro_time_filter.dT_max / 1000.0,
            detection.time_window,
        )
        selection = burst_filter(
            tttr=tttr,
            min_ph=detection.min_photons,
            ph_window=detection.photon_window,
            time_window=detection_window,
        )
        return np.asarray(selection, dtype=bool)

    if used_filter == BurstFilterMode.BOCPD:
        # BOCPD is retired: it never performed well enough to recommend, and
        # every search it competed with now lives in tttrlib. The mode value
        # survives so an old project still loads and says what happened
        # instead of failing somewhere deeper.
        raise ValueError(
            "the BOCPD burst search has been removed; choose another filter "
            "mode (the tttrlib searches supersede it)"
        )

    if used_filter == BurstFilterMode.KALMAN:
        # The Kalman detector now lives in tttrlib (burst_search_kalman), so
        # this mode runs the C++ implementation rather than the numba one that
        # used to live in chisurf.core.fluorescence.burst.kalman. The settings
        # and the mode name are unchanged, so saved projects keep working.
        #
        # A tttrlib too old to publish the registry falls back to the numba
        # implementation rather than failing, so an installation where it used
        # to work keeps working.
        kalman_settings = settings.kalman_filter
        min_counts = burst_detection.min_photons if burst_detection else 60
        if tttrlib_search.is_available():
            selection = tttrlib_burst_filter(
                tttr=tttr,
                algorithm="kalman",
                parameters=dict(
                    L=min_counts,
                    dt=kalman_settings.dt,
                    q=kalman_settings.q,
                    r_scale=kalman_settings.r_scale,
                    z_thresh=kalman_settings.z_thresh,
                    min_len=kalman_settings.min_len,
                    merge_gap=kalman_settings.merge_gap,
                    per_channel=True,
                ),
            )
            return np.asarray(selection, dtype=bool)
        channel_list = settings.channels
        if len(channel_list) < 1:
            channel_list = list(tttr.get_used_routing_channels())
        time_unit = tttr.header.macro_time_resolution
        timestamps = tttr.macro_times * time_unit
        channels = tttr.routing_channels
        timestamps_list = []
        for channel in channel_list:
            channel_timestamps = timestamps[channels == channel]
            timestamps_list.append(channel_timestamps)
            if len(channel_timestamps) == 0:
                return np.zeros(n, dtype=bool)
        bursts, _, _, _, _ = kalman_mod.kalman_burst_detection_multi(
            timestamps_list,
            dt=kalman_settings.dt,
            q=kalman_settings.q,
            r_scale=kalman_settings.r_scale,
            z_thresh=kalman_settings.z_thresh,
            min_len=kalman_settings.min_len,
            merge_gap=kalman_settings.merge_gap,
            min_counts=min_counts,
        )
        start_stop = kalman_mod.convert_bursts_to_start_stop(bursts, tttr)
        if len(start_stop) > 0:
            return np.asarray(create_array_with_ones(start_stop, n), dtype=bool)
        return np.zeros(n, dtype=bool)

    if used_filter == BurstFilterMode.CUSUM:
        cusum_settings = settings.cusum_filter
        selection = cusum_filter(
            tttr=tttr,
            min_ph=cusum_settings.min_photons,
            background_rate=cusum_settings.background_rate,
            sb_ratio=cusum_settings.sb_ratio,
            alpha=cusum_settings.alpha,
            beta=cusum_settings.beta,
        )
        return np.asarray(selection, dtype=bool)

    if used_filter == BurstFilterMode.TTTRLIB:
        # The algorithm and its parameters come from tttrlib's registry, so this
        # one branch covers every search tttrlib offers, present and future.
        # (Unavailable-registry is handled by the fallback above, so reaching
        # here means the registry is present.)
        tttrlib_settings = settings.tttrlib_search
        selection = tttrlib_burst_filter(
            tttr=tttr,
            algorithm=tttrlib_settings.algorithm,
            parameters=tttrlib_settings.parameters,
        )
        return np.asarray(selection, dtype=bool)

    raise ValueError(f"Unsupported filter mode: {settings.used_filter}")


def _search_on_delta_filtered_stream(
    tttr: tttrlib.TTTR,
    delta_mask: np.ndarray,
    settings: PhotonFilterSettings,
    burst_detection: BurstDetectionSettings | None,
) -> np.ndarray:
    """Run the burst search on the delta-macro-time-filtered stream, in original space.

    The delta-macro-time interval is applied to the *photon stream the search
    sees*: a reduced ``tttrlib`` object (``get_tttr_by_selection``) built from the
    photons inside the interval is searched, and the detected photons are mapped
    back to the full index space. Photons the interval excluded therefore cannot
    seed or extend a burst, but a burst that spans them still counts them
    downstream ("exclude from search only") because bursts are found over the
    original photon indices.
    """
    n = len(tttr)
    keep = np.flatnonzero(delta_mask)
    if keep.size == n:
        # Nothing removed — search the whole stream (no copy).
        return np.asarray(_run_burst_search(tttr, settings, burst_detection), dtype=bool)
    if keep.size == 0:
        return np.zeros(n, dtype=bool)
    reduced = tttr.get_tttr_by_selection(keep.astype(np.int32))
    sub_selection = np.asarray(
        _run_burst_search(reduced, settings, burst_detection), dtype=bool
    )
    selected = np.zeros(n, dtype=bool)
    selected[keep[sub_selection]] = True
    return selected


def apply_photon_filters(
    tttr: tttrlib.TTTR,
    settings: PhotonFilterSettings,
    burst_detection: BurstDetectionSettings | None = None,
) -> np.ndarray:
    """Apply ChiSurf-compatible photon pre-filters to a TTTR object.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        TTTR object.
    settings : PhotonFilterSettings
        Photon filter settings.
    burst_detection : BurstDetectionSettings, optional
        Burst filter settings used when ``settings.used_filter`` is ``"burst"``.

    Returns
    -------
    numpy.ndarray
        Boolean selection mask.
    """
    selected = np.ones(len(tttr), dtype=bool)

    if settings.channels:
        mask = tttrlib.TTTRMask()
        mask.select_channels(tttr, settings.channels, mask=True)
        selected = np.logical_and(selected, mask.get_mask())

    if settings.microtime_ranges:
        mask = tttrlib.TTTRMask()
        mask.select_microtime_ranges(tttr, settings.microtime_ranges)
        mask.flip()
        selected = np.logical_and(selected, mask.get_mask())

    # The delta-macro-time interval is a photon-stream pre-filter, not a mask
    # AND-ed onto the burst-search result. AND-ing it afterwards was a no-op in
    # practice — burst photons already have a small inter-photon gap, so the
    # interval never removed any of them. As a pre-filter it gates which photons
    # the search *sees* (see _search_on_delta_filtered_stream); with no search it
    # is the selection itself.
    delta_mask = _delta_macro_time_mask(tttr, settings.delta_macro_time_filter)

    used_filter = BurstFilterMode(settings.used_filter)

    if settings.filter_active:
        selection = _search_on_delta_filtered_stream(
            tttr, delta_mask, settings, burst_detection
        )
        selected = np.logical_and(selected, selection)
    else:
        selected = np.logical_and(selected, delta_mask)

    if settings.invert_filter and used_filter != BurstFilterMode.COUNT_RATE:
        selected = ~selected

    if settings.use_gap_fill and settings.max_gap > 0:
        selected = fill_small_gaps_in_array(selected, max_gap=settings.max_gap)

    return selected.astype(dtype=np.uint8)


def find_bursts(selected_mask: Iterable[int], max_gap: int = 4) -> np.ndarray:
    """Find burst start/stop pairs from a selected-photon mask.

    Parameters
    ----------
    selected_mask : iterable of int
        Boolean or integer selection mask.
    max_gap : int, default=4
        Maximum number of unselected photons to bridge inside a burst.

    Returns
    -------
    numpy.ndarray
        Array with shape ``(n_bursts, 2)`` containing start/stop photon indices.
    """
    mask = np.asarray(selected_mask, dtype=np.uint8)
    if len(mask) <= max_gap:
        return np.array([], dtype=np.uint64)
    return signal_find_bursts(mask, max_gap=max_gap)


def drop_short_bursts(start_stop: np.ndarray, min_photons: int) -> np.ndarray:
    """Return only the bursts holding at least *min_photons* photons.

    A burst-level criterion, and therefore one that has to be applied to the
    burst list rather than inside a search: only the sliding-window
    (``"burst"``) search enforces a photon minimum itself, so a count-rate,
    CUSUM, Kalman, or tttrlib-registry search used to return every contiguous
    run of selected photons -- down to two -- while the analysis folder's own
    name (``countrate_All 0.1500#60``) claimed a minimum of 60. This is what
    makes the claim true for every search.

    Parameters
    ----------
    start_stop : numpy.ndarray
        ``(n_bursts, 2)`` array of first/last photon indices, the *last* index
        inclusive (:func:`find_bursts`).
    min_photons : int
        Minimum photons per burst. Values below 2 leave *start_stop* untouched
        -- a "burst" of one photon is already dropped downstream.

    Returns
    -------
    numpy.ndarray
        The rows of *start_stop* whose photon count reaches *min_photons*, in
        their original order.
    """
    start_stop = np.asarray(start_stop)
    if min_photons < 2 or start_stop.size == 0:
        return start_stop
    counts = start_stop[:, 1].astype(np.int64) - start_stop[:, 0].astype(np.int64) + 1
    return start_stop[counts >= int(min_photons)]


def summarize_bursts(
    start_stop: np.ndarray,
    filename: str | Path,
    tttr: tttrlib.TTTR,
    windows: dict[str, tuple[int, int]] | None = None,
    detectors: dict[str, dict[str, Any]] | None = None,
    macro_time_resolution: float | None = None,
):
    """Generate a ChiSurf-compatible burst summary DataFrame.

    Parameters
    ----------
    start_stop : numpy.ndarray
        Burst start/stop indices.
    filename : str or Path
        Source TTTR filename.
    tttr : tttrlib.TTTR
        TTTR object.
    windows : dict, optional
        PIE windows.
    detectors : dict, optional
        Detector definitions.
    macro_time_resolution : float, optional
        Macro-time resolution override for output durations.

    Returns
    -------
    pandas.DataFrame
        Burst summary table.
    """
    return generate_burst_dataframe(
        start_stop=start_stop,
        filename=filename,
        tttr=tttr,
        windows=windows or {},
        detectors=detectors or {},
        include_interleaved_zeros=True,
        macro_time_resolution=macro_time_resolution,
    )


def legacy_output_folder_name(settings: AnalysisSettings) -> str:
    """Return the legacy output folder name for analysis settings."""
    channels = settings.photon_filter.channels
    channel_text = ",".join(str(channel) for channel in channels) if channels else "All"
    mode = BurstFilterMode(settings.photon_filter.used_filter)
    if mode == BurstFilterMode.COUNT_RATE:
        prefix = "countrate"
    elif mode == BurstFilterMode.BOCPD:
        prefix = "bocpd"
    elif mode == BurstFilterMode.KALMAN:
        prefix = "kalman"
    elif mode == BurstFilterMode.CUSUM:
        prefix = "cusum"
    elif mode == BurstFilterMode.TTTRLIB:
        prefix = settings.photon_filter.tttrlib_search.algorithm
    else:
        prefix = "burstwise"
    return (
        f"{prefix}_{channel_text} "
        f"{settings.photon_filter.delta_macro_time_filter.dT_max:.4f}"
        f"#{settings.burst_detection.min_photons}"
    )


def _prepare_legacy_output_folder(request: AnalysisRequest) -> Path | None:
    """Resolve and create the legacy output folder for a request."""
    if not request.files or not request.settings.output_formats:
        return None
    first_file = Path(request.files[0]).resolve()
    folder_name = request.legacy_output_folder_name or legacy_output_folder_name(request.settings)
    output_folder = get_unique_folder_path(first_file.parent / folder_name)
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder


def _write_legacy_output_info(request: AnalysisRequest, output_folder: Path) -> None:
    """Write legacy ``Info`` files for a request."""
    info_dir = output_folder / "Info"
    info_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(request.settings)
    payload.update(request.legacy_parameters)
    payload.update(
        {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "selected_setup": request.selected_setup,
            "channels": request.settings.photon_filter.channels,
            "microtime_ranges": request.settings.photon_filter.microtime_ranges,
            "files": [Path(file_name).name for file_name in request.files],
        }
    )
    with (info_dir / "photon_selection_parameters.json").open("w") as fp:
        json.dump(payload, fp, indent=4, default=str)
    with (info_dir / "datetime.txt").open("w") as fp:
        fp.write(f"Date: {time.strftime('%Y-%m-%d')}\nTime: {time.strftime('%H:%M:%S')}\n")


def analyze_file(
    path: str | Path,
    *,
    settings: AnalysisSettings | None = None,
    filetype: str | None = None,
    windows: dict[str, tuple[int, int]] | None = None,
    detectors: dict[str, dict[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    mti_output_dir: str | Path | None = None,
    macro_time_resolution: float | None = None,
) -> AnalysisResult:
    """Run burst selection for one TTTR file.

    Parameters
    ----------
    path : str or Path
        TTTR file path.
    settings : AnalysisSettings, optional
        Analysis settings.
    filetype : str, optional
        TTTR file type.
    windows : dict, optional
        PIE windows.
    detectors : dict, optional
        Detector definitions.
    output_dir : str or Path, optional
        Directory for ``.bur`` output.
    mti_output_dir : str or Path, optional
        Legacy analysis directory where the ``Info/*.mti`` sidecar is written.
    macro_time_resolution : float, optional
        Macro-time resolution override for output durations.

    Returns
    -------
    AnalysisResult
        Analysis result.
    """
    normalized_path = str(Path(path).resolve())
    analysis_settings = settings or AnalysisSettings()
    tttr = load_tttr(path, filetype=filetype)
    if len(tttr) == 0:
        return AnalysisResult(
            files=[str(path)],
            dataframes={str(path): []},
            metadata={"n_photons": 0, "n_selected": 0, "n_bursts": 0},
            output_paths={},
            output_paths_by_file={normalized_path: {}},
        )
    selected = apply_photon_filters(
        tttr,
        analysis_settings.photon_filter,
        burst_detection=analysis_settings.burst_detection,
    )
    # Both bounds come from the settings, and used not to. ``max_gap`` was left
    # at this function's own default of 4, so a run configured to bridge nothing
    # still bridged four photons; ``min_photons`` was applied by the
    # sliding-window search alone, so every other search returned runs of two
    # photons as bursts.
    photon_filter = analysis_settings.photon_filter
    search_gap = photon_filter.max_gap if photon_filter.use_gap_fill else 0
    start_stop = find_bursts(selected, max_gap=search_gap)
    # The floor of 2 is what keeps the reported ``n_bursts`` equal to the number
    # of rows in the table: the summarizer already skips a burst whose last
    # photon is not past its first, so counting those here reported thousands of
    # bursts that were never written.
    start_stop = drop_short_bursts(
        start_stop, max(2, analysis_settings.burst_detection.min_photons)
    )
    output_resolution = (
        float(tttr.header.macro_time_resolution)
        if macro_time_resolution is None
        else float(macro_time_resolution)
    )
    df = summarize_bursts(
        start_stop,
        path,
        tttr,
        windows=windows or {},
        detectors=detectors or {},
        macro_time_resolution=output_resolution,
    )

    output_paths: dict[str, str] = {}
    if "bur" in analysis_settings.output_formats and output_dir is not None:
        bur_path = Path(output_dir) / f"{Path(path).stem}.bur"
        write_bur(df, bur_path)
        output_paths["bur"] = str(bur_path)
        if mti_output_dir is not None:
            max_macro_time = float(tttr.macro_times[-1]) * output_resolution
            write_mti_summary(Path(path), Path(mti_output_dir), max_macro_time, append=True)
            output_paths["mti_dir"] = str(Path(mti_output_dir) / "Info")

            # Record *how* the source was read, not only that it was. A burst
            # table is a set of pointers back into a photon stream, so anything
            # that later wants those photons has to reopen the file — and with
            # nothing written down it has to guess the container type, which is
            # how ".spc" came to be opened as a type tttrlib does not have.
            try:
                write_analysis_manifest(
                    Path(mti_output_dir),
                    [
                        describe_tttr_source(
                            path,
                            tttr,
                            settings={
                                "windows": dict(windows or {}),
                                "detectors": dict(detectors or {}),
                                "macro_time_resolution": output_resolution,
                            },
                        )
                    ],
                    settings=_manifest_settings(analysis_settings),
                    software_version=getattr(chisurf, "__version__", None),
                )
            except Exception:
                logging.exception("could not write the burst reading manifest")

    return AnalysisResult(
        files=[str(path)],
        dataframes={str(path): rows_from_table(df)},
        metadata={
            "n_photons": int(len(tttr)),
            "n_selected": int(np.count_nonzero(selected)),
            "n_bursts": int(len(start_stop)),
            "macro_time_resolution": output_resolution,
        },
        output_paths=output_paths,
        output_paths_by_file={normalized_path: dict(output_paths)},
    )


def analyze_request(
    request: AnalysisRequest,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> AnalysisResult:
    """Run burst selection for a complete analysis request.

    Parameters
    ----------
    request : AnalysisRequest
        Analysis request.
    progress_callback : callable, optional
        Called as ``progress_callback(done, total, path)`` after each file
        finishes -- one file is the natural chunk here, so a batch reports
        real incremental progress instead of a single opaque call the caller
        can only watch as a busy spinner. Not used for cancellation: this is
        report-only, called directly and never expected to raise.

    Returns
    -------
    AnalysisResult
        Combined analysis result.
    """
    frames: dict[str, list[dict[str, Any]]] = {}
    output_paths: dict[str, str] = {}
    output_paths_by_file: dict[str, dict[str, str]] = {}
    metadata: dict[str, Any] = {
        "n_files": len(request.files),
        "n_bursts": 0,
        "n_selected": 0,
        "n_photons": 0,
    }
    legacy_output_folder = _prepare_legacy_output_folder(request) if request.legacy_output else None
    bur_output_dir = (
        legacy_output_folder / "bi4_bur"
        if legacy_output_folder is not None and "bur" in request.settings.output_formats
        else request.output_dir
    )
    hdf5_frames: list = []
    batch_macro_time_resolution: float | None = None
    total_files = len(request.files)

    for file_index, path in enumerate(request.files):
        result = analyze_file(
            path,
            settings=request.settings,
            filetype=request.filetype,
            windows=request.windows,
            detectors=request.detectors,
            output_dir=bur_output_dir,
            mti_output_dir=legacy_output_folder if legacy_output_folder is not None else None,
            macro_time_resolution=batch_macro_time_resolution,
        )
        if batch_macro_time_resolution is None and "macro_time_resolution" in result.metadata:
            batch_macro_time_resolution = float(result.metadata["macro_time_resolution"])
        frames.update(result.dataframes)
        output_paths.update(result.output_paths)
        output_paths_by_file.update(result.output_paths_by_file)
        if legacy_output_folder is not None and "hdf5" in request.settings.output_formats:
            frame = store_from_rows(result.dataframes.get(str(path), []))
            frame["Source File"] = str(path)
            hdf5_frames.append(frame)
        if "pto" in request.settings.output_formats:
            container = write_container(
                path,
                store_from_rows(result.dataframes.get(str(path), [])),
                parameters=to_jsonable(request.settings),
                out_dir=request.output_dir,
            )
            output_paths.setdefault("pto", container)
            output_paths_by_file.setdefault(str(path), {})["pto"] = container
        metadata["n_bursts"] += int(result.metadata.get("n_bursts", 0))
        metadata["n_selected"] += int(result.metadata.get("n_selected", 0))
        metadata["n_photons"] += int(result.metadata.get("n_photons", 0))
        if progress_callback is not None:
            progress_callback(file_index + 1, total_files, str(path))

    if legacy_output_folder is not None:
        _write_legacy_output_info(request, legacy_output_folder)
        output_paths["output_folder"] = str(legacy_output_folder)
        metadata["output_folder"] = str(legacy_output_folder)
        if "hdf5" in request.settings.output_formats and hdf5_frames:
            # Deprecated. The name carries a timestamp, so every re-run leaves
            # another file nobody reads, and the container holds the same table
            # with the provenance this never had. Kept working for pipelines
            # that still ask for it; the `.bur` companions stay because external
            # tools read those, and this had no such consumer.
            warnings.warn(
                "burst-selection HDF5 output is deprecated: use output_formats "
                "'pto' for the measurement's container, or 'bur' for the legacy "
                "companion layout.",
                DeprecationWarning,
                stacklevel=2,
            )
            hdf5_dir = legacy_output_folder / "hdf5"
            hdf5_path = hdf5_dir / f"burst_data_{time.strftime('%Y%m%d-%H%M%S')}.h5"
            write_hdf5(hdf5_frames, hdf5_path)
            output_paths["hdf5"] = str(hdf5_path)
        if request.settings.zip_output:
            zip_path = zip_output_folder(legacy_output_folder)
            output_paths["zip"] = str(zip_path)
            if request.settings.remove_folder:
                shutil.rmtree(legacy_output_folder)
                output_paths["output_folder"] = str(zip_path)
                metadata["output_folder"] = str(zip_path)

    return AnalysisResult(
        files=request.files,
        dataframes=frames,
        output_paths=output_paths,
        output_paths_by_file=output_paths_by_file,
        metadata=metadata,
    )
