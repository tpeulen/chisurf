"""Burst selection and summarization functions."""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import tttrlib

import chisurf
import chisurf.core.fluorescence.burst.kalman as kalman_mod
from chisurf.core.datastore import rows_from_table, store_from_rows
from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe, write_mti_summary
from chisurf.core.fio.fluorescence.burst_manifest import (
    describe_tttr_source,
    write_analysis_manifest,
)
from chisurf.core.fluorescence.burst import (
    burst_filter,
    count_rate_filter,
    cusum_filter,
    tttrlib_search,
)
from chisurf.core.fluorescence.burst.tttrlib_search import tttrlib_burst_filter
from chisurf.core.math.signal import fill_small_gaps_in_array
from chisurf.core.math.signal import find_bursts as signal_find_bursts

from .io import (
    get_unique_folder_path,
    load_tttr,
    write_bur,
    write_container,
    zip_output_folder,
)
from .models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSettings,
    BurstDetectionSettings,
    BurstFilterMode,
    DeltaMacroTimeFilterSettings,
    PhotonFilterSettings,
)
from .serialization import to_jsonable

#: Which filter ran -> its `_mmfdb_operation.algorithm` term.
#:
#: `operation_type` says a burst selection happened; this says how, which is
#: what makes two selections of one measurement comparable or not. Both
#: `COUNT_RATE` and `BURST` are the classic photons-in-a-time-window rate
#: threshold -- `count_rate_filter` selects on photons per window and
#: `burst_filter` is the L/m/T form of the same test -- so both are
#: `sliding_window`.
#:
#: `TTTRLIB` is not here: its algorithm is whatever the registry advertised and
#: is read from the settings. A mode absent from both records nothing rather
#: than the nearest guess.
_FILTER_ALGORITHM = {
    BurstFilterMode.COUNT_RATE: "sliding_window",
    BurstFilterMode.BURST: "sliding_window",
    BurstFilterMode.BOCPD: "bocpd",
    BurstFilterMode.KALMAN: "kalman",
    BurstFilterMode.CUSUM: "cusum_sprt",
}


def _selection_algorithm(settings) -> str:
    """The mmfdb term for the search `settings` selected, or "" if unrecorded."""
    used = getattr(settings, "used_filter", None)
    if used == BurstFilterMode.TTTRLIB:
        return str(getattr(getattr(settings, "tttrlib_search", None), "algorithm", "") or "")
    return _FILTER_ALGORITHM.get(used, "")


def _manifest_settings(analysis_settings) -> dict:
    """The burst-search settings, in a JSON-safe shape for the manifest."""
    try:
        return {
            k: v
            for k, v in asdict(analysis_settings).items()
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
    tttr: tttrlib.TTTR, delta_settings: DeltaMacroTimeFilterSettings
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
    len(tttr)
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
        # BOCPD now lives in tttrlib (burst_search_bocpd). The settings
        # and mode name are unchanged, so saved projects keep working.
        bocpd_settings = settings.bocpd_filter
        min_counts = burst_detection.min_photons if burst_detection else 20
        if tttrlib_search.is_available():
            selection = tttrlib_burst_filter(
                tttr=tttr,
                algorithm="bocpd",
                parameters=dict(
                    L=min_counts,
                    dt=bocpd_settings.dt,
                    prior_count=bocpd_settings.prior_count,
                    prior_duration=bocpd_settings.prior_duration,
                    changepoint_prob=bocpd_settings.changepoint_prob,
                    max_run=256,
                    per_channel=True,
                ),
            )
            return np.asarray(selection, dtype=bool)
        # fallback: direct call on timestamps
        from chisurf.core.fluorescence.burst.bocpd import bocpd_filter

        return bocpd_filter(
            tttr,
            min_ph=min_counts,
            dt=bocpd_settings.dt,
            prior_count=bocpd_settings.prior_count,
            prior_duration=bocpd_settings.prior_duration,
            changepoint_prob=bocpd_settings.changepoint_prob,
        )

    if used_filter == BurstFilterMode.KALMAN:
        # The Kalman detector now lives in tttrlib (burst_search_kalman), so
        # this mode runs the C++ implementation rather than the numba one that
        # used to live in chisurf.core.fluorescence.burst.kalman. The settings
        # and the mode name are unchanged, so saved projects keep working.
        #
        # ``is_available`` tests the *registry*, which is what the generic
        # ``algorithm=`` call below goes through. A tttrlib too old to publish
        # it still has the search itself, so the fallback calls that method
        # directly rather than reimplementing the recursion in Python.
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
        return np.asarray(
            kalman_mod.kalman_filter(
                tttr,
                min_ph=min_counts,
                dt=kalman_settings.dt,
                q=kalman_settings.q,
                r_scale=kalman_settings.r_scale,
                z_thresh=kalman_settings.z_thresh,
                min_len=kalman_settings.min_len,
                merge_gap=kalman_settings.merge_gap,
                per_channel=True,
            ),
            dtype=bool,
        )

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


def _search_and_apply_interval(
    tttr: tttrlib.TTTR,
    delta_mask: np.ndarray,
    settings: PhotonFilterSettings,
    burst_detection: BurstDetectionSettings | None,
) -> np.ndarray:
    """Search the whole stream, then let the delta-macro-time interval remove.

    The interval used to be applied the other way round -- as a *pre-filter*,
    building a reduced ``tttrlib`` object from the photons inside it and
    searching that. The reasoning was that a photon the interval excluded should
    not be able to seed a burst, which is true; the consequence was not
    anticipated. Every burst search is ultimately a statement about
    inter-photon times, and the interval is the same kind of statement, so on
    the reduced stream the search can find that *every* photon qualifies: a
    sliding window asking for ``m`` consecutive photons inside ``T`` is
    guaranteed to say yes once the interval has bounded the gap below ``T/m``,
    and a search scoring against an estimated background has no background left
    to estimate.

    That does not fail. It returns two or three enormous "bursts" covering the
    measurement, with a burst count, a mean size and a mean duration that all
    look like an analysis. A real session produced **8 bursts** in the written
    table while the panel above it said 866 -- and the panel was right, because
    the photon-filter wizard has always done it this way round.

    Measured on the bundled DNA measurement (sliding window, dT <= 0.0101 ms,
    60-photon minimum): searching first gives **801 bursts of mean 136.5
    photons**, pre-filtering gives 745 of mean 138.6 where it works at all --
    the same analysis when the pre-filter is healthy, and the only one that
    survives when it is not.

    The interval keeps its meaning: a photon outside it is not selected, so it
    cannot extend a burst. What it can no longer do is invent one.
    """
    selection = np.asarray(_run_burst_search(tttr, settings, burst_detection), dtype=bool)
    return selection & np.asarray(delta_mask, dtype=bool)


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

    # The delta-macro-time interval is a mask AND-ed onto the burst-search
    # result, and the search runs on the whole stream. It used to be the other
    # way round -- the interval reduced the stream first and the search saw only
    # what survived -- on the reasoning that an excluded photon should not be
    # able to seed a burst. See :func:`_search_and_apply_interval` for what that
    # did instead. With no search running, the interval is the selection itself.
    delta_mask = _delta_macro_time_mask(tttr, settings.delta_macro_time_filter)

    used_filter = BurstFilterMode(settings.used_filter)

    if settings.filter_active:
        selection = _search_and_apply_interval(tttr, delta_mask, settings, burst_detection)
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


def _all_containers(paths) -> bool:
    """Return whether every input is already a `.pto` measurement container.

    The test for "does this run need a folder at all". A container is the
    measurement *and* everything computed from it, so results belong inside it;
    a vendor file has nowhere to put them and still needs the legacy layout for
    the tools that read one.

    Parameters
    ----------
    paths : sequence
        The analysis inputs.

    Returns
    -------
    bool
        ``False`` for an empty list -- nothing to decide about, and defaulting
        to "container" there would silently suppress a folder someone asked for.
    """
    from chisurf.core.fio.pto import SUFFIX

    paths = list(paths or [])
    return bool(paths) and all(Path(p).suffix.lower() == SUFFIX for p in paths)


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


def _measurement_name(path) -> Path:
    """Return the name a burst table should record for *path*.

    A vendor file names itself. A container names the instrument file it holds
    -- there is only ever one measurement in a container, and that measurement
    is the `.spc`/`.ptu` it was packed from, not the box it is packed in. A
    container stacking several vendor files (one split measurement) has no
    single answer and keeps its own name, which is honest: those bursts really
    do span the set.

    Parameters
    ----------
    path : str or pathlib.Path

    Returns
    -------
    pathlib.Path
        A name, not a path to open — only its ``.name`` reaches the table.
    """
    path = Path(path)
    if path.suffix.lower() != ".pto":
        return path
    try:
        from chisurf.core.fio.pto import Measurement

        with Measurement.open(path, writable=False) as measurement:
            embedded = [
                m.name for m in measurement.artifacts() if m.uid in measurement.instrument_uids
            ]
    except Exception:  # noqa: BLE001 - naming must never fail an analysis
        return path
    return path.with_name(embedded[0]) if len(embedded) == 1 else path


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
        # The *measurement's* name, which for a container is the instrument
        # file inside it rather than the container itself. `First File` names
        # what a burst was found in, and a reader resolving it against an
        # unpacked folder would otherwise look for an `m000.pto` that is not
        # there beside the `m000.spc` it just recovered. It is also what makes
        # the analysis of a container and of the vendor file it holds produce
        # byte-identical tables, which is the claim `.pto` has to be able to
        # make about the folder it replaces.
        _measurement_name(path),
        tttr,
        windows=windows or {},
        detectors=detectors or {},
        macro_time_resolution=output_resolution,
    )

    output_paths: dict[str, str] = {}
    # An explicit `output_dir` is a request for the legacy folder, and the
    # folder is defined by its `.bur` plus `Info/` sidecars -- the same
    # "the request implies the format" rule the request path applies for
    # `legacy_output`. Without this, `analyze_file(..., output_dir=...)`
    # under the `["pto"]` default returned success and wrote nothing.
    # An explicitly *empty* `output_formats` still means "write nothing".
    formats = list(analysis_settings.output_formats)
    if output_dir is not None and formats and "bur" not in formats:
        formats.append("bur")
    if "bur" in formats and output_dir is not None:
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
    # A measurement that is already a container gets **no folder at all**. The
    # container holds the photons and every result computed from them, which is
    # the whole point of it; writing a parameter-named directory beside it puts
    # the same bursts in two places, freshly numbered on every run, and the two
    # then disagree the moment one of them is re-run. `.pto` in, `.pto` out.
    legacy_output = request.legacy_output and not _all_containers(request.files)
    if request.legacy_output and not legacy_output:
        chisurf.logging.info(
            "burst selection: the source is a .pto container, so the results go "
            "into it rather than into a burstwise folder beside it"
        )
    # Where a folder *is* written, the legacy layout is the `.bur` plus its
    # `Info/` sidecars -- that is what a reader (ndX) opens the folder for.
    # Asking for the folder while asking for no format that goes in it produced
    # a directory holding two Info files and nothing else, which ndX refused
    # with "No .bur files in 'bi4_bur' or 'bur'". So the request implies the
    # format.
    if legacy_output and "bur" not in request.settings.output_formats:
        request.settings.output_formats = list(request.settings.output_formats) + ["bur"]
    # Only where a folder was asked for and suppressed: the results still have
    # to land somewhere, and for a container that somewhere is the container. An
    # explicitly empty `output_formats` means "write nothing" and stays that.
    if request.legacy_output and not legacy_output and "pto" not in request.settings.output_formats:
        request.settings.output_formats = list(request.settings.output_formats) + ["pto"]
    legacy_output_folder = _prepare_legacy_output_folder(request) if legacy_output else None
    bur_output_dir = (
        legacy_output_folder / "bi4_bur"
        if legacy_output_folder is not None and "bur" in request.settings.output_formats
        else request.output_dir
    )
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
        if "pto" in request.settings.output_formats:
            run = legacy_output_folder_name(request.settings)
            container = write_container(
                path,
                store_from_rows(result.dataframes.get(str(path), [])),
                parameters=to_jsonable(request.settings),
                algorithm=_selection_algorithm(request.settings),
                out_dir=request.output_dir,
                # Named the way the folder layout names its directory, so a
                # container holding several analyses of one measurement is
                # addressed exactly as a folder of them is:
                # `m000.pto/countrate_All 0.1500#60`.
                run=run,
            )
            output_paths.setdefault("pto", container)
            output_paths_by_file.setdefault(str(path), {})["pto"] = container
            # The path a downstream step is pointed at. It reads like a folder
            # because that is the point; `burst_tree` resolves it.
            analysis_path = f"{container}/{run}" if run else container
            output_paths.setdefault("output_folder", analysis_path)
            output_paths_by_file.setdefault(str(path), {})["output_folder"] = analysis_path
        metadata["n_bursts"] += int(result.metadata.get("n_bursts", 0))
        metadata["n_selected"] += int(result.metadata.get("n_selected", 0))
        metadata["n_photons"] += int(result.metadata.get("n_photons", 0))
        if progress_callback is not None:
            progress_callback(file_index + 1, total_files, str(path))

    if legacy_output_folder is not None:
        _write_legacy_output_info(request, legacy_output_folder)
        output_paths["output_folder"] = str(legacy_output_folder)
        metadata["output_folder"] = str(legacy_output_folder)
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
