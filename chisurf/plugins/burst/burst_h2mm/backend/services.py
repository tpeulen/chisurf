"""ServiceDispatcher-compatible RPC handlers for H2MM burst analysis."""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import numpy as np

from chisurf.core.datastore import column_names

from ..api.contract import (
    METHOD_COMPUTE,
    METHOD_DESCRIBE_CONTRACT,
    METHOD_PREPARE_WORKFLOW,
    contract_descriptor,
    service_success,
)
from ..api.models import H2mmResult, H2mmSettings, StateFitSummary, StreamSettings
from ..api.serialization import settings_from_dict, to_jsonable

logger = logging.getLogger(__name__)


def register_services(dispatcher: Any) -> None:
    """Register H2MM RPC handlers with a ServiceDispatcher."""
    dispatcher.register(METHOD_COMPUTE, lambda params: compute_handler(**(params or {})))
    dispatcher.register(
        METHOD_PREPARE_WORKFLOW, lambda params: prepare_workflow_handler(**(params or {}))
    )
    dispatcher.register(METHOD_DESCRIBE_CONTRACT, lambda params: contract_handler(**(params or {})))


def list_methods() -> dict[str, str]:
    """Return H2MM RPC method descriptions."""
    return {
        METHOD_COMPUTE: "Fit photon-by-photon HMM (H2MM) models over burst data.",
        METHOD_PREPARE_WORKFLOW: "Resolve H2MM settings and folders from a burst workflow context.",
        METHOD_DESCRIBE_CONTRACT: "Return the H2MM workflow contract.",
    }


# ---------------------------------------------------------------------------
# Shared analysis runner (also used by the CLI)
# ---------------------------------------------------------------------------


class H2mmAnalysisBundle:
    """In-memory container returned to the GUI (not serialised over RPC)."""

    def __init__(self, analysis, data, settings):
        self.analysis = analysis
        self.data = data
        self.settings = settings


def run_analysis(
    settings: H2mmSettings,
    analysis_folder: str | pathlib.Path | None = None,
    files: list[str] | None = None,
    pattern: str = "*.bur",
    progress=None,
) -> tuple[H2mmResult, H2mmAnalysisBundle]:
    """Load bursts, fit H2MM models, and build a serialisable result.

    Parameters
    ----------
    settings : H2mmSettings
        Analysis configuration.
    analysis_folder : str or Path, optional
        Folder to search for ``.bur`` files (``pattern``).
    files : list of str, optional
        Explicit ``.bur`` file paths (take precedence over the folder).
    pattern : str
        Glob for ``.bur`` files when ``analysis_folder`` is used.
    progress : callable, optional
        Forwarded to :func:`~..core.analysis.analyze` — called after each
        state-count fit for progress bars / live plots.

    Returns
    -------
    result : H2mmResult
        JSON-serialisable summary.
    bundle : H2mmAnalysisBundle
        The full in-memory analysis (for GUI plotting).
    """
    from ..core import photons as photons_mod
    from ..core.analysis import analyze
    from ..core.photons import StreamDef, bursts_from_dataframe

    bur_paths = _resolve_bur_files(files, analysis_folder, pattern)
    if not bur_paths:
        raise ValueError("no .bur files found for H2MM analysis")

    df = photons_mod.load_bur_dataframe(bur_paths)
    data_dir = pathlib.Path(bur_paths[0]).parent
    tttrs = _load_tttrs(df, data_dir, settings.file_type)

    base_time_s = _macro_resolution(tttrs) * max(int(settings.time_scale), 1)

    stream_defs = [
        StreamDef(s.name, list(s.channels), [tuple(r) for r in s.micro_time_ranges])
        for s in settings.streams
    ]
    data, meta = bursts_from_dataframe(
        df,
        tttrs,
        stream_defs,
        time_scale=int(settings.time_scale),
        min_photons=int(settings.min_photons),
        return_meta=True,
        divisors=int(getattr(settings, "divisors", 1)),
    )

    # The per-EM-map cache cost scales with the number of *unique* inter-photon
    # Δt; unscaled fine-resolution macro times can make this huge and the fit
    # slow. Point the user at the time-scale lever.
    n_slots = int(data.unique_dt.shape[0])
    if n_slots > 20000:
        try:
            from chisurf import logging as _log

            _log.warning(
                "H2MM: %d unique inter-photon Δt (time_scale=%d) — each EM map "
                "rebuilds that many propagators, so fits will be slow. Increase "
                "'Macro-time scale' (e.g. to %d) to speed up ~%.0fx.",
                n_slots,
                int(settings.time_scale),
                int(settings.time_scale) * 100,
                n_slots / 3000.0,
            )
        except Exception:
            pass

    acceptor = 1 if len(stream_defs) > 1 else 0
    ana = analyze(
        data,
        state_counts=settings.state_counts,
        criterion=settings.criterion,
        base_time_s=base_time_s,
        acceptor_stream=acceptor,
        donor_stream=0,
        n_restarts=int(settings.n_restarts),
        max_iter=int(settings.max_iter),
        tol=float(settings.tol),
        seed=int(settings.seed),
        engine=settings.engine,
        surrogates=_load_surrogates(settings),
        refine_iters=int(settings.refine_iters),
        patience=settings.patience,
        divisors=int(getattr(settings, "divisors", 1)),
        decoder=getattr(settings, "decoder", "viterbi"),
        decoder_seed=int(getattr(settings, "decoder_seed", 0)),
        progress=progress,
    )

    result = _result_from_analysis(ana, settings)
    bundle = H2mmAnalysisBundle(analysis=ana, data=data, settings=settings)
    bundle.meta = meta
    bundle.burst_df = df
    bundle.tttrs = tttrs
    bundle.micro_time_ns = _micro_resolution(tttrs) * 1e9
    return result, bundle


def _load_surrogates(settings: H2mmSettings) -> dict[int, object] | None:
    """Load a trained surrogate for the surrogate engines (keyed by its n_states)."""
    if not getattr(settings, "surrogate_path", "") or "surrogate" not in settings.engine:
        return None
    from ..core.surrogate import SurrogateModel

    sm = SurrogateModel.load(settings.surrogate_path)
    return {int(sm.n_states): sm}


def _burst_sources(burst_df, burst_rows):
    """Return ``(source names in index order, source index per analysed burst)``.

    The burst table names the measurement of every burst; ``burst_rows`` says
    which of its rows survived extraction. Together they label each analysed
    burst with the file it came from — the piece a per-photon ``Photon`` index
    needs to be unambiguous.
    """
    import numpy as np

    if burst_df is None or burst_rows is None:
        return [], None
    if "First File" not in column_names(burst_df):
        return [], None
    rows = np.asarray(burst_rows, dtype=np.int64)
    if rows.size == 0:
        return [], None
    files = np.asarray(burst_df["First File"]).astype(str)
    names: list[str] = []
    index: dict[str, int] = {}
    out = np.zeros(rows.size, dtype=np.int64)
    for i, row in enumerate(rows):
        name = pathlib.Path(str(files[int(row)])).stem
        if name not in index:
            index[name] = len(names)
            names.append(name)
        out[i] = index[name]
    return names, out


def _write_state_tttr(result, bundle, out_dir, burst_df, burst_rows) -> None:
    """Write the decoded assignment back into the photon stream, if asked.

    Optional because it rewrites (a copy of) the measurement: one PTU per source
    file whose routing channels encode ``(stream, state)``, and/or a msgpack
    sidecar that leaves the source alone. Either makes a per-state decay an
    ordinary channel or mask selection in any tool.
    """
    settings = bundle.settings
    if not bool(getattr(settings, "write_state_tttr", False)):
        return
    want_ptu = bool(getattr(settings, "state_tttr_ptu", True))
    want_sidecar = bool(getattr(settings, "state_tttr_sidecar", True))
    if not (want_ptu or want_sidecar):
        return
    tttrs = getattr(bundle, "tttrs", None)
    meta = getattr(bundle, "meta", None)
    if not tttrs or meta is None or burst_rows is None or burst_df is None:
        logger.warning(
            "state TTTR output requested but the source photons are not available - skipped"
        )
        return
    if "First File" not in column_names(burst_df):
        logger.warning(
            "state TTTR output needs the burst table's 'First File' "
            "column to know which measurement each photon came from "
            "- skipped"
        )
        return

    from ..core.state_tttr import write_state_tttr

    ana = bundle.analysis
    try:
        written = write_state_tttr(
            meta,
            ana.path,
            np.asarray(bundle.data.streams),
            tttrs,
            burst_rows,
            list(np.asarray(burst_df["First File"]).astype(str)),
            out_dir,
            model=ana.best.model,
            decoder=str(getattr(ana, "decoder", "viterbi")),
            seed=int(getattr(ana, "decoder_seed", 0)),
            n_states=int(ana.best.n_states),
            write_tttr=want_ptu,
            write_sidecar=want_sidecar,
        )
    except Exception as exc:
        # Loud: a missing state file is the whole point of having ticked the box.
        logger.error("state TTTR output failed (%s: %s)", type(exc).__name__, exc)
        result.output_paths["state_tttr_error"] = f"{type(exc).__name__}: {exc}"
        return
    result.output_paths.update(written.as_output_paths())


def write_result_tables(
    result: H2mmResult,
    bundle: H2mmAnalysisBundle,
    out_dir: pathlib.Path,
) -> None:
    """Write the JSON summary plus the ndX-openable per-photon/per-burst tables.

    Records every written path in ``result.output_paths``.
    """
    from ..core.export import (
        build_dwell_table,
        build_tables,
        write_burst_companions,
        write_csv,
        write_hdf5,
    )

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "h2mm_result.json"
    with open(out_path, "w") as fh:
        json.dump(result.to_dict(), fh, indent=2)
    result.output_paths["result_json"] = str(out_path)

    meta = getattr(bundle, "meta", None)
    # Writing the state back into the photons is an independent choice from the
    # ndX tables -- it answers a different need and must not be skipped just
    # because the per-photon table was turned off.
    _write_state_tttr(
        result,
        bundle,
        out_dir,
        getattr(bundle, "burst_df", None),
        getattr(meta, "burst_rows", None),
    )

    if meta is None or not getattr(bundle.settings, "write_photons", True):
        return
    ana = bundle.analysis
    micro_ns = getattr(bundle, "micro_time_ns", None)

    # One definition of "which streams are green", shared with the plot, so a
    # written table and a drawn curve cannot disagree about what a colour is.
    from ..core.decays import colour_groups, decay_table, state_decays

    stream_groups = colour_groups(ana, bundle.settings)

    # Which measurement each analysed burst came from, so the per-photon table
    # can say so: Photon numbers restart in every file.
    burst_df = getattr(bundle, "burst_df", None)
    burst_rows = getattr(meta, "burst_rows", None)
    source_names, burst_sources = _burst_sources(burst_df, burst_rows)
    if source_names:
        result.output_paths.setdefault("sources", ",".join(source_names))

    tables = build_tables(
        bundle.data,
        meta,
        ana.path,
        ana.fret,
        ana.base_time_s,
        stream_groups=stream_groups,
        micro_time_ns=(micro_ns if micro_ns else None),
        burst_sources=burst_sources,
    )
    # Formats are two independent choices, not a fallback chain: HDF5 is compact
    # and fast to reload, CSV is what every other tool opens, and a folder can
    # carry both. The fallback survives *inside* that: if HDF5 was asked for and
    # cannot be written, the CSV is written whether or not it was ticked, so a
    # run never ends with the state assignment nowhere on disk.
    want_hdf5 = bool(getattr(bundle.settings, "photon_hdf5", True))
    want_csv = bool(getattr(bundle.settings, "photon_csv", True))
    if not (want_hdf5 or want_csv):
        want_hdf5 = True
    if want_hdf5:
        try:
            result.output_paths["photons_hdf5"] = write_hdf5(
                tables.photons, out_dir / "h2mm_photons.h5"
            )
        except Exception:  # pragma: no cover - pytables optional
            want_csv = True
    if want_csv:
        result.output_paths["photons_csv"] = write_csv(tables.photons, out_dir / "h2mm_photons.csv")
    result.output_paths["bursts_csv"] = write_csv(tables.bursts, out_dir / "h2mm_bursts.csv")

    # Per-dwell table (one row per Viterbi dwell) — the unit ndxplorer filters on
    # (min photons, drop burst-edge dwells, select by state/duration).
    dwells_df = build_dwell_table(
        bundle.data,
        meta,
        ana.dwells,
        ana.base_time_s,
        stream_groups=stream_groups,
        micro_time_ns=(micro_ns if micro_ns else None),
    )
    result.output_paths["dwells_csv"] = write_csv(dwells_df, out_dir / "h2mm_dwells.csv")

    # Per-state decays, kept per detector. A decay is only defined within one
    # detection colour, so this is written at the finest meaningful key --
    # (state, stream, routing channel) -- and merged upwards by the reader.
    decays = state_decays(
        meta.micro_time,
        meta.channel,
        bundle.data.streams,
        ana.path,
        n_states=int(ana.fret.shape[0]),
        groups=stream_groups,
        micro_time_ns=(micro_ns if micro_ns else None),
    )
    result.output_paths["state_decays_csv"] = write_csv(
        decay_table(decays), out_dir / "h2mm_state_decays.csv"
    )

    # Per-measurement companions beside the .bur files themselves, so a burst
    # folder loaded in ndX carries the H2MM state as just another column and
    # bursts can be gated on it. Written to the *analysis* folder, not this
    # output folder: that is where the .bur files and their bv4/2c4 siblings are.
    companions = write_burst_companions(
        getattr(bundle, "burst_df", None),
        getattr(meta, "burst_rows", None),
        bundle.data,
        ana.path,
        ana.fret,
        pathlib.Path(out_dir).parent,
    )
    for target in companions:
        result.output_paths[f"companion_{target.stem}"] = str(target)


def _result_from_analysis(ana, settings: H2mmSettings) -> H2mmResult:
    """Convert a :class:`H2mmAnalysis` into the serialisable result model."""
    import numpy as np

    best = ana.best.model
    scan = [
        StateFitSummary(
            n_states=f.n_states,
            loglik=f.loglik,
            bic=f.bic,
            icl=f.icl,
            converged=bool(f.model.converged),
            n_iter=int(f.model.n_iter),
        )
        for f in ana.scan
    ]
    dwell_mean = [
        float(np.mean(v)) * ana.base_time_s if v.size else 0.0
        for _, v in sorted(ana.dwell_times.items())
    ]
    has_alex = bool(np.isfinite(np.asarray(ana.stoichiometry)).any())
    return H2mmResult(
        n_states=ana.best.n_states,
        criterion=settings.criterion,
        scan=scan,
        prior=[float(x) for x in best.prior],
        trans=[[float(x) for x in row] for row in best.trans],
        obs=[[float(x) for x in row] for row in best.obs],
        trans_rates=[[float(x) for x in row] for row in ana.trans_rates],
        fret=[float(x) for x in ana.fret],
        stoichiometry=[float(x) for x in ana.stoichiometry] if has_alex else [],
        has_alex=has_alex,
        populations=[float(x) for x in ana.populations],
        posterior_populations=(
            [float(x) for x in np.asarray(ana.posterior_populations)]
            if ana.posterior_populations is not None
            and np.isfinite(np.asarray(ana.posterior_populations)).any()
            else []
        ),
        decoder=str(getattr(ana, "decoder", "viterbi")),
        decoder_seed=int(getattr(ana, "decoder_seed", 0)),
        n_underflow=int(getattr(ana, "n_underflow", 0)),
        dwell_decoder=str(getattr(ana, "dwell_decoder", "viterbi")),
        dwell_mean_s=dwell_mean,
        n_transitions=len(ana.transitions),
        n_bursts=ana.n_bursts,
        n_photons=ana.n_photons,
        base_time_s=ana.base_time_s,
        settings_applied=to_jsonable(settings),
    )


# ---------------------------------------------------------------------------
# RPC handlers
# ---------------------------------------------------------------------------


def compute_handler(
    files: list[str] | None = None,
    analysis_folder: str | None = None,
    pattern: str = "*.bur",
    settings: dict[str, Any] | None = None,
    workflow_context: dict[str, Any] | None = None,
    write_output: bool = True,
) -> dict[str, Any]:
    """Run H2MM analysis from explicit parameters or a workflow handoff."""
    try:
        resolved_folder = _resolve_analysis_folder(analysis_folder, files, workflow_context)
        h2mm_settings = _settings_from_workflow(settings, workflow_context)

        result, bundle = run_analysis(
            h2mm_settings,
            analysis_folder=resolved_folder,
            files=files,
            pattern=pattern,
        )

        if write_output and resolved_folder is not None:
            write_result_tables(result, bundle, pathlib.Path(resolved_folder) / "h2mm")

        payload = to_jsonable(result)
        payload["analysis_folder"] = str(resolved_folder) if resolved_folder else None
        payload["workflow_context"] = workflow_context or {}
        return service_success(payload)
    except Exception as exc:  # pragma: no cover - defensive envelope
        return _service_error(str(exc))


def prepare_workflow_handler(
    workflow_context: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    analysis_folder: str | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve H2MM inputs from explicit params plus a workflow context."""
    try:
        resolved_folder = _resolve_analysis_folder(analysis_folder, files, workflow_context)
        h2mm_settings = _settings_from_workflow(settings, workflow_context)
        return service_success(
            {
                "analysis_folder": str(resolved_folder) if resolved_folder else None,
                "settings": to_jsonable(h2mm_settings),
                "workflow_context": workflow_context or {},
            }
        )
    except Exception as exc:  # pragma: no cover
        return _service_error(str(exc))


def contract_handler() -> dict[str, Any]:
    """Return the H2MM workflow contract descriptor."""
    return service_success(contract_descriptor())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_bur_files(
    files: list[str] | None,
    analysis_folder: str | pathlib.Path | None,
    pattern: str,
) -> list[pathlib.Path]:
    """Return the list of ``.bur`` files to analyse."""
    if files:
        return [pathlib.Path(f) for f in files if str(f).endswith(".bur")]
    if analysis_folder:
        folder = pathlib.Path(analysis_folder)
        if folder.is_file() and folder.suffix == ".bur":
            return [folder]
        return sorted(folder.glob("**/" + pattern))
    return []


def _resolve_analysis_folder(
    analysis_folder: str | None,
    files: list[str] | None,
    workflow_context: dict[str, Any] | None,
) -> pathlib.Path | None:
    """Resolve the analysis folder from supported inputs."""
    candidates: list[str] = []
    if analysis_folder:
        candidates.append(str(analysis_folder))
    if workflow_context:
        folder = workflow_context.get("burst_folder") or workflow_context.get("analysis_folder")
        if isinstance(folder, str):
            candidates.append(folder)
    if files:
        candidates.append(str(pathlib.Path(files[0]).parent))
    for candidate in candidates:
        path = pathlib.Path(candidate).expanduser()
        if path.exists():
            return path
    return pathlib.Path(candidates[0]).expanduser() if candidates else None


def _load_tttrs(df, data_dir: pathlib.Path, file_type: str):
    """Load TTTR objects referenced by the burst table.

    ChiSurf burst outputs are commonly nested as
    ``<tttr-folder>/<analysis-folder>/bi4_bur/*.bur`` while the ``First File``
    column stores only ``m000.spc``.  Search upward from the ``.bur`` directory
    so those relative references resolve back to the original TTTR folder.
    """
    import tttrlib

    data_dir = pathlib.Path(data_dir)
    tttrs: dict[str, Any] = {}
    # dict.fromkeys, not Series.unique: the burst table is a store now, and both
    # keep first-appearance order.
    for ff in dict.fromkeys(np.asarray(df["First File"]).tolist()):
        if _is_empty_tttr_reference(ff):
            continue
        if ff in tttrs:
            continue
        cand = pathlib.Path(ff)
        for path in _tttr_path_candidates(cand, data_dir):
            if path.exists():
                ftype = file_type
                if not ftype or ftype.lower() == "auto":
                    ftype = tttrlib.inferTTTRFileType(str(path))
                tttrs[ff] = tttrlib.TTTR(str(path), ftype)
                break
    if not tttrs:
        raise FileNotFoundError("could not locate any TTTR file referenced by the .bur data")
    return tttrs


def _is_empty_tttr_reference(value: Any) -> bool:
    """Return ``True`` for placeholder ``First File`` values in empty .bur rows."""
    text = str(value).strip()
    return text == "" or text == "0" or text.lower() == "nan"


def _tttr_path_candidates(candidate: pathlib.Path, data_dir: pathlib.Path):
    """Yield plausible filesystem locations for a ``First File`` value."""
    if candidate.is_absolute():
        yield candidate
        return

    seen: set[pathlib.Path] = set()
    for parent in (data_dir, *data_dir.parents):
        path = parent / candidate
        if path not in seen:
            seen.add(path)
            yield path


def _macro_resolution(tttrs) -> float:
    """Return the macro-time resolution (seconds) from the first TTTR header."""
    for tttr in tttrs.values():
        try:
            return float(tttr.header.tag("MeasDesc_GlobalResolution")["value"])
        except Exception:
            try:
                return float(tttr.header.macro_time_resolution)
            except Exception:
                continue
    return 1.0


def _micro_resolution(tttrs) -> float:
    """Return the micro-time (TCSPC) resolution (seconds) from the first TTTR header.

    Used to report the per-burst donor lifetime column (``Tau (green)``) in ns for
    the ndxplorer FRET-line plot. Falls back to ``0.0`` (→ NaN lifetimes) when the
    header carries no micro-time resolution.
    """
    for tttr in tttrs.values():
        try:
            return float(tttr.header.tag("MeasDesc_Resolution")["value"])
        except Exception:
            try:
                return float(tttr.header.micro_time_resolution)
            except Exception:
                continue
    return 0.0


def _settings_from_workflow(
    settings: dict[str, Any] | None,
    workflow_context: dict[str, Any] | None,
) -> H2mmSettings:
    """Build H2MM settings, deriving streams from a workflow context."""
    if settings:
        return settings_from_dict(H2mmSettings, settings)

    streams: list[StreamSettings] = []
    file_type = "SPC-130"
    if workflow_context:
        channel_settings = workflow_context.get("channel_settings") or {}
        detectors = channel_settings.get("detectors") or {}
        for name, det in detectors.items():
            streams.append(
                StreamSettings(
                    name=str(name),
                    channels=[int(c) for c in det.get("chs", [])],
                    micro_time_ranges=[
                        (int(a), int(b)) for a, b in det.get("micro_time_ranges", [])
                    ],
                )
            )
        tttr_reading = channel_settings.get("tttr_reading") or {}
        if tttr_reading.get("file_type"):
            file_type = str(tttr_reading["file_type"])

    kwargs: dict[str, Any] = {"file_type": file_type}
    if streams:
        kwargs["streams"] = streams
    return H2mmSettings(**kwargs)


def _service_error(message: str) -> dict[str, Any]:
    """Return a ServiceDispatcher-compatible error envelope."""
    try:
        from chisurf.server.services import OPERATION_FAILED, service_error

        return service_error(message, error_code=OPERATION_FAILED)
    except Exception:
        return {"ok": False, "error": message}
