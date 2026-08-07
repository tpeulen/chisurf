"""Staged loading of large data files from slow (network) storage.

Large TTTR files (PTU/HT3/SPC) are read by ``tttrlib`` in a single blocking
C++ call that offers no progress callback, so loading a multi-GB file from a
slow network share freezes the caller (and, in the GUI, the whole interface).

This module provides a transport-agnostic, **Qt-free** building block that
gives back genuine progress *and* transfer speed for that case:

1. Probe the source throughput by timing a small head read.
2. If the source is *slow* (and large enough to matter), stream-copy it to a
   local temporary file with our own chunked read loop -- which is where the
   ``progress_cb`` (bytes/percent/MB-s/ETA) information comes from -- and hand
   the local copy to the reader. The subsequent ``tttrlib`` parse then runs
   against fast local disk.
3. If the source is *fast* (local SSD, fast NAS) the probe bytes are discarded
   and the original path is returned unchanged -- no needless copy.

The staged copy is **ephemeral**: :func:`staged_source` deletes it once the
caller is done. Because there is no Qt dependency here, this is usable from the
headless server/CLI as well as the GUI; the GUI layer
(``chisurf.gui.widgets.staged_loading``) only adds a progress dialog on top.

Examples
--------
>>> from chisurf.core.fio import staging
>>> with staging.staged_source(path) as local:  # doctest: +SKIP
...     tttr = tttrlib.TTTR(str(local))

Readers that just want a ``tttrlib.TTTR`` use :func:`open_tttr`, which stages
on slow storage, parses, and deletes the temp in one call.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

__all__ = [
    "CONTAINER_SELECTOR",
    "CancelCallback",
    "ProgressCallback",
    "StagingCancelled",
    "TTTR_EXTENSIONS",
    "TTTR_FILE_FILTER",
    "VENDOR_EXTENSIONS",
    "format_rate",
    "import_measurement",
    "open_tttr",
    "split_container_spec",
    "stage_path_if_slow",
    "staged_source",
]

#: The vendor formats ChiSurf reads photons from.
#:
#: **Import sources, not the working format.** Each is a recording as some
#: instrument's software wrote it; opening one produces the measurement's
#: container, inside which those exact bytes are kept and remain recoverable.
VENDOR_EXTENSIONS: tuple[str, ...] = (
    ".ptu", ".phu", ".ht3", ".ht2", ".pt3", ".pt2", ".t3r",
    ".spc", ".set", ".hdf5", ".h5", ".photons", ".cz-raw", ".sm",
)

#: Every extension a photon measurement may arrive as, **container first**.
#:
#: Order is the point: this seeds the file-dialog filters, and the first entry
#: is what a dialog offers by default. `.pto` is ChiSurf's format for TTTR data;
#: everything after it is something to import.
TTTR_EXTENSIONS: tuple[str, ...] = (".pto",) + VENDOR_EXTENSIONS


def _filter(label: str, extensions) -> str:
    return f"{label} ({' '.join('*' + e for e in extensions)})"


#: Qt file-dialog filter for opening photon data.
#:
#: One definition, because a dialog that lists a different set from the reader
#: is a dialog that hides files ChiSurf can open — which is how `.pto` was
#: absent from every one of them while being the format they all produce.
TTTR_FILE_FILTER: str = ";;".join((
    _filter("Photon data", TTTR_EXTENSIONS),
    _filter("Photon container", (".pto",)),
    _filter("Vendor photon files", VENDOR_EXTENSIONS),
    "All files (*)",
))

# --- Tunables ---------------------------------------------------------------
# Defaults may be overridden via the ``data_loading`` section of
# ``chisurf.settings.cs_settings`` (see :func:`_settings`), which is editable
# through the "Data loading" settings AutoForm. They are intentionally
# conservative: the only cost of a wrong "slow" guess is one extra local copy;
# the cost of a wrong "fast" guess is a frozen-feeling load with no progress.

#: Files smaller than this are loaded directly -- staging overhead is not worth
#: it and a progress bar on a sub-second copy only flickers.
DEFAULT_MIN_SIZE = 32 * 1024 * 1024  # 32 MiB

#: Sources slower than this (measured over the probe) are staged locally.
DEFAULT_THRESHOLD_MBPS = 40.0

#: Chunk size for both the probe and the copy loop.
DEFAULT_CHUNK_BYTES = 4 * 1024 * 1024  # 4 MiB

#: How much of the head to read before deciding slow-vs-fast...
DEFAULT_PROBE_BYTES = 8 * 1024 * 1024  # 8 MiB
#: ...but stop probing early once this much wall-clock has elapsed, so we never
#: block for long on a very slow link just to make the decision.
DEFAULT_PROBE_MIN_SECONDS = 0.3
#: ...and require at least this many bytes before trusting the measurement.
DEFAULT_PROBE_MIN_BYTES = 1 * 1024 * 1024  # 1 MiB

#: Minimum wall-clock between successive ``progress_cb`` invocations, to avoid
#: flooding a GUI marshal queue on a fast link.
DEFAULT_PROGRESS_INTERVAL = 0.1


#: ``progress_cb(bytes_done, total_bytes, mbps, eta_seconds)``. ``eta_seconds``
#: is ``None`` until a rate can be estimated.
ProgressCallback = Callable[[int, int, float, float | None], None]
#: ``cancel_cb() -> bool``; return ``True`` to abort the copy.
CancelCallback = Callable[[], bool]


class StagingCancelled(Exception):
    """Raised by :func:`stage_path_if_slow` when ``cancel_cb`` requests abort."""


#: Default values for the ``data_loading`` settings section. These seed both
#: the runtime fallbacks (:func:`_settings`) and the AutoForm JSON view-spec
#: (``chisurf/gui/widgets/staged_loading_view.json``); keep the two in sync.
DEFAULTS = {
    "enabled": True,
    # Opening a vendor photon file produces the measurement's container, which
    # is what makes `.pto` the format ChiSurf works in rather than one it can
    # also write. Off means a vendor file is read where it lies and results go
    # to the legacy layouts.
    "import_to_container": True,
    "min_size": DEFAULT_MIN_SIZE,
    "threshold_mbps": DEFAULT_THRESHOLD_MBPS,
    "chunk_bytes": DEFAULT_CHUNK_BYTES,
    "probe_bytes": DEFAULT_PROBE_BYTES,
    "probe_min_seconds": DEFAULT_PROBE_MIN_SECONDS,
    "probe_min_bytes": DEFAULT_PROBE_MIN_BYTES,
    "progress_interval": DEFAULT_PROGRESS_INTERVAL,
}


def _settings() -> dict:
    """Return the ``data_loading`` settings section merged over :data:`DEFAULTS`."""
    cfg = dict(DEFAULTS)
    try:
        import chisurf.settings as settings

        section = settings.cs_settings.get("data_loading")
        if isinstance(section, dict):
            cfg.update(section)
    except Exception:
        pass
    return cfg


def _cache_dir() -> Path:
    """Directory used for ephemeral staging copies."""
    try:
        import chisurf.settings as settings

        base = Path(settings._chisurf_user_cache_dir)
    except Exception:
        base = Path(tempfile.gettempdir()) / "chisurf"
    staging = base / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def format_rate(mbps: float) -> str:
    """Format a transfer rate in MB/s (or GB/s for fast links)."""
    if mbps >= 1000.0:
        return f"{mbps / 1000.0:.2f} GB/s"
    return f"{mbps:.1f} MB/s"


def _emit(
    cb: ProgressCallback | None,
    done: int,
    total: int,
    t0: float,
    state: dict,
    *,
    force: bool = False,
) -> None:
    """Throttled progress emission with rate/ETA derived from ``t0``."""
    if cb is None:
        return
    now = perf_counter()
    if not force and (now - state["last"]) < state["interval"]:
        return
    state["last"] = now
    elapsed = now - t0
    rate_bps = (done / elapsed) if elapsed > 0 else 0.0
    mbps = rate_bps / 1e6
    eta = ((total - done) / rate_bps) if rate_bps > 0 else None
    cb(done, total, mbps, eta)


def stage_path_if_slow(
    src,
    *,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    min_size: int | None = None,
    threshold_mbps: float | None = None,
    chunk_bytes: int | None = None,
    probe_bytes: int | None = None,
) -> tuple[Path, bool]:
    """Copy *src* to a fast local temp file when it lives on slow storage.

    The source is opened once. A small head is read and timed; if the measured
    throughput is at or above ``threshold_mbps`` (or the file is below
    ``min_size``, or the whole file fit in the probe) the original path is
    returned unchanged. Otherwise the already-read probe bytes plus the rest of
    the file are streamed to a temp file in the chisurf cache dir, invoking
    ``progress_cb`` throughout, and that temp path is returned.

    Parameters
    ----------
    src : str or pathlib.Path
        Source file to (maybe) stage.
    progress_cb : callable, optional
        Called as ``progress_cb(bytes_done, total_bytes, mbps, eta_seconds)``
        during the copy. Not called when the file is not staged.
    cancel_cb : callable, optional
        Polled between chunks; if it returns ``True`` the partial copy is
        removed and :class:`StagingCancelled` is raised.
    min_size, threshold_mbps, chunk_bytes, probe_bytes
        Override the module defaults (themselves overridable via settings).

    Returns
    -------
    (pathlib.Path, bool)
        ``(path_to_open, was_staged)``. When ``was_staged`` is ``True`` the
        caller owns the returned temp file and must delete it (use
        :func:`staged_source` to do this automatically).
    """
    cfg = _settings()
    min_size = int(cfg["min_size"] if min_size is None else min_size)
    threshold_mbps = float(cfg["threshold_mbps"] if threshold_mbps is None else threshold_mbps)
    chunk_bytes = int(cfg["chunk_bytes"] if chunk_bytes is None else chunk_bytes)
    probe_bytes = int(cfg["probe_bytes"] if probe_bytes is None else probe_bytes)
    probe_min_seconds = float(cfg["probe_min_seconds"])
    probe_min_bytes = int(cfg["probe_min_bytes"])
    interval = float(cfg["progress_interval"])

    src = Path(src)
    # Staging globally disabled, or file too small for staging to be worthwhile.
    if not cfg.get("enabled", True):
        return src, False
    total = src.stat().st_size
    if total < min_size:
        return src, False

    state = {"last": 0.0, "interval": interval}

    fh = open(src, "rb")
    try:
        # --- Probe: read the head and time it -------------------------------
        probe = bytearray()
        t0 = perf_counter()
        while len(probe) < probe_bytes:
            if cancel_cb is not None and cancel_cb():
                raise StagingCancelled()
            chunk = fh.read(min(chunk_bytes, probe_bytes - len(probe)))
            if not chunk:
                break  # whole file smaller than probe window
            probe += chunk
            elapsed = perf_counter() - t0
            if elapsed >= probe_min_seconds and len(probe) >= probe_min_bytes:
                break

        elapsed = perf_counter() - t0
        mbps = ((len(probe) / 1e6) / elapsed) if elapsed > 0 else float("inf")

        # Fast enough, or the probe already drained the file -> don't stage.
        if mbps >= threshold_mbps or len(probe) >= total:
            return src, False

        # --- Slow: stream-copy probe bytes + remainder to a temp file -------
        staging_dir = Path(tempfile.mkdtemp(prefix="stage-", dir=_cache_dir()))
        # Preserve the original filename so tttrlib's container-type detection
        # (which keys off the extension/name) behaves identically.
        dst = staging_dir / src.name
        try:
            done = 0
            with open(dst, "wb") as out:
                out.write(probe)
                done = len(probe)
                _emit(progress_cb, done, total, t0, state, force=True)
                while True:
                    if cancel_cb is not None and cancel_cb():
                        raise StagingCancelled()
                    chunk = fh.read(chunk_bytes)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    _emit(progress_cb, done, total, t0, state)
            _emit(progress_cb, done, total, t0, state, force=True)
            return dst, True
        except BaseException:
            # Cancel or I/O error: drop the partial copy before propagating.
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
    finally:
        fh.close()


@contextlib.contextmanager
def staged_source(
    src,
    *,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    **kwargs,
):
    """Context manager yielding a local path, deleting any staged temp on exit.

    >>> with staged_source(path) as local:        # doctest: +SKIP
    ...     tttr = tttrlib.TTTR(str(local))
    """
    local, staged = stage_path_if_slow(src, progress_cb=progress_cb, cancel_cb=cancel_cb, **kwargs)
    try:
        yield local
    finally:
        if staged:
            shutil.rmtree(local.parent, ignore_errors=True)


#: Separates a container path from the member inside it, as ``tttrlib`` spells
#: it: ``"run.pto|m001.ptu"``.
CONTAINER_SELECTOR = "|"


def split_container_spec(src) -> tuple[Path, str]:
    """Split ``"<path>|<member>"`` into the path and the member.

    A photon container holds several objects, so a caller may name which one to
    read. Everything that touches the filesystem — staging, existence checks,
    size probes — must use the path alone; only the reader understands the
    selector.

    Parameters
    ----------
    src : str or pathlib.Path
        A path, or a path followed by a member name.

    Returns
    -------
    tuple of (pathlib.Path, str)
        The path, and the member name (``""`` when none was given).
    """
    text = str(src)
    if CONTAINER_SELECTOR not in text:
        return Path(text), ""
    path, _, selector = text.partition(CONTAINER_SELECTOR)
    return Path(path), selector


#: Default RNG seed for LUT dithering. tttrlib's ``apply_luts_and_shifts``
#: distributes fractional micro-time bins stochastically (Felekyan dithering,
#: which avoids the binning artifacts of deterministic rounding). Seed ``-1``
#: (and ``0``) mean "random" -> non-reproducible reads; any *positive* fixed
#: seed makes dithering reproducible, so reading the same file twice yields the
#: same decay. We default to a fixed positive seed for reproducibility.
LUT_DITHER_SEED = 42


def open_tttr(
    src,
    routine=None,
    *,
    channel_luts: dict | None = None,
    channel_shifts: dict | None = None,
    apply_lut: bool | None = None,
    lut_seed: int = LUT_DITHER_SEED,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    **stage_kwargs,
):
    """Build a :class:`tttrlib.TTTR`, staging *src* locally first when slow.

    Drop-in replacement for ``tttrlib.TTTR(path[, routine])`` that adds the
    slow-storage staging + progress behaviour. The staged temp copy (if any) is
    deleted once parsing finishes -- ``tttrlib`` has the events in memory by
    then, so the on-disk copy is no longer needed.

    When a channel definition (setup) is associated with the read, this is also
    the single seam that applies **per-routing-channel TAC linearization LUTs**
    and **photon-level micro-time shifts**, so every reader that passes a setup's
    correction becomes LUT-aware. With no LUT/shift (the default) the returned
    object is identical to a plain ``tttrlib.TTTR(...)`` open.

    Parameters
    ----------
    src : str or pathlib.Path
        File to read.
    routine : str or int, optional
        ``tttrlib`` container type. **Prefer ``None``**: the library identifies
        the container from the file, so guessing one from an extension is
        unnecessary and gets it wrong. Legacy and misspelled names are resolved
        by :func:`resolve_container_type` rather than reaching ``tttrlib``,
        which answers an unknown type with an empty object rather than an error.
    channel_luts : dict, optional
        Mapping ``{routing_channel: NTAC_fract}`` of cumulative TAC-linearization
        LUTs (see :mod:`chisurf.plugins.tttr.tttr_lut_tools.core.tac_lut`). Only
        applied when *apply_lut* is true.
    channel_shifts : dict, optional
        Mapping ``{routing_channel: int}`` of photon-level micro-time shifts
        (wrapping, applied after any LUT). Independent of *apply_lut*.
    apply_lut : bool
        Master gate for LUT linearization. When false, *channel_luts* is ignored
        (raw micro-times); *channel_shifts* is still applied if given.
    lut_seed : int
        RNG seed for the LUT dithering (see :data:`LUT_DITHER_SEED`). A positive
        value makes reads reproducible; ``-1``/``0`` request random dithering.
    progress_cb, cancel_cb
        Forwarded to :func:`stage_path_if_slow`.
    **stage_kwargs
        Forwarded to :func:`stage_path_if_slow` (e.g. ``threshold_mbps``).
    """
    import tttrlib

    # When the caller does not specify the correction (apply_lut is None), consult
    # the process-global active-setup context so every read through this single
    # seam is LUT-aware without threading the setup to each call site. Pass
    # apply_lut=False explicitly to force a raw read (inspection/editor tools).
    if apply_lut is None:
        from chisurf.core.fio.lut_context import get_active_setup_lut

        ctx_luts, ctx_shifts, ctx_apply = get_active_setup_lut()
        apply_lut = ctx_apply
        if channel_luts is None:
            channel_luts = ctx_luts
        if channel_shifts is None:
            channel_shifts = ctx_shifts

    # A container type the library does not know is not an error it reports: it
    # prints to stderr and returns an object with zero photons, which reads
    # downstream as an empty measurement. Resolve it to something accepted, or
    # to auto-detection, before it gets that far.
    container = resolve_container_type(routine)

    # A photon container may name the member to read -- "run.pto|m001.ptu".
    # Only the part before the separator is a path, so staging must not see the
    # selector or it stages a file that does not exist.
    path, selector = split_container_spec(src)

    with staged_source(
        path, progress_cb=progress_cb, cancel_cb=cancel_cb, **stage_kwargs
    ) as local:
        spec = f"{local}|{selector}" if selector else str(local)
        if container is None:
            tttr = tttrlib.TTTR(spec)
        else:
            tttr = tttrlib.TTTR(spec, container)

    apply_setup_lut(
        tttr, channel_luts, channel_shifts, apply_lut=bool(apply_lut), lut_seed=lut_seed
    )
    return tttr


#: Names that were once used as container types but that ``tttrlib`` has never
#: accepted. ``"SPC"`` in particular was written by hand in a dozen call sites
#: (and in an extension→routine table), where it produced
#: "Container type SPC not supported" and an unreadable file — for a format
#: ``tttrlib`` detects perfectly well on its own.
_CONTAINER_ALIASES = {
    "SPC": None,        # ambiguous between SPC-130 and SPC-600: let it detect
    "BH": None,
    "SPC130": "SPC-130",
    "SPC-132": "SPC-130",
    "BH132": "SPC-130",       # the name chisurf's own photon reader used
    "BH630_X48": "SPC-600_4096",
    "HDF5": "PHOTON-HDF5",
    "PHOTONHDF5": "PHOTON-HDF5",
}


def import_measurement(src, *, out_dir=None, create: bool | None = None):
    """Return the container for *src*, importing a vendor file into one.

    The seam that makes `.pto` the format ChiSurf works in rather than one it
    can also write. A vendor file is a *recording*, in whatever the instrument's
    software emits; opening it here produces the measurement's container with
    those exact bytes inside it, and everything computed afterwards goes in the
    same file instead of into directories beside it.

    Nothing is lost and nothing is moved: the vendor file stays where it is,
    byte-for-byte recoverable from the container
    (:meth:`~chisurf.core.fio.pto.Measurement.disassemble`), and deleting the
    original is the user's decision, never this function's.

    Parameters
    ----------
    src : str or pathlib.Path
        A vendor photon file, or a container (returned unchanged).
    out_dir : str or pathlib.Path, optional
        Where the container goes. Defaults to beside *src* — wrong for
        read-only source media, right everywhere else.
    create : bool, optional
        Whether to create the container when it does not exist yet. Defaults to
        the ``data_loading.import_to_container`` setting, which is on.

        Passing ``False`` asks only "is there one?": the answer is the existing
        container or *src* unchanged. That is what a read-only inspection wants,
        and what a caller must pass when it is looking at someone else's file.

    Returns
    -------
    pathlib.Path
        The container, or *src* when there is none and none was created.
    """
    from chisurf.core.fio.pto import Measurement, SUFFIX, is_measurement

    path, _ = split_container_spec(src)
    if is_measurement(path):
        return path

    target_dir = Path(out_dir) if out_dir is not None else path.parent
    target = target_dir / (path.stem + SUFFIX)
    if is_measurement(target):
        return target

    if create is None:
        create = bool(_settings().get("import_to_container", True))
    if not create or not path.exists():
        return path

    try:
        with Measurement.create(path, out_dir=out_dir):
            pass
    except Exception as exc:
        # An unwritable directory is the ordinary case here -- data on a
        # read-only share, or a colleague's folder -- and it must not stop the
        # file being read. The vendor path still works; only the container does
        # not exist.
        logging.info("could not import %s into a container: %s", path, exc)
        return path
    return target


def supported_container_types() -> tuple:
    """Container types this ``tttrlib`` build accepts.

    Asked of the library rather than hard-coded, because a list written down
    here goes stale silently: the previous one omitted ``CZ-RAW``, ``SM`` and
    ``PHOTONS`` and would have rejected them as unknown.
    """
    import tttrlib

    try:
        return tuple(tttrlib.TTTR.get_supported_container_names())
    except Exception:  # pragma: no cover - very old tttrlib
        return ("PTU", "HT3", "SPC-130", "SPC-600_256", "SPC-600_4096", "PHOTON-HDF5")


def resolve_container_type(routine=None):
    """Turn a caller's container-type argument into one ``tttrlib`` accepts.

    **Auto-detection is the right default and is what most callers should pass.**
    ``tttrlib`` identifies the container from the file itself, so guessing one
    from a file extension — the mistake that produced ``"SPC"`` — is both
    unnecessary and wrong. A routine should only be given when it is *known*:
    recorded with the measurement, or chosen by the user for a format the file
    cannot distinguish (SPC-130 against SPC-600, which differ in record layout).

    Parameters
    ----------
    routine : str or int, optional
        Requested container type. ``None``, empty, or an unrecognised name
        yields ``None`` (auto-detect); a known legacy alias is translated.

    Returns
    -------
    str or int or None
        A value safe to hand to ``tttrlib``, or ``None`` to auto-detect.

    Notes
    -----
    This never raises. ``tttrlib`` does not raise either on a bad container
    type — it prints to stderr and hands back an object with **zero photons**,
    which downstream looks like an empty measurement rather than a failed read.
    Silently degrading to auto-detection is strictly better than that.
    """
    if routine is None or isinstance(routine, int):
        return routine
    name = str(routine).strip()
    if not name:
        return None
    supported = supported_container_types()
    if name in supported:
        return name
    upper = name.upper()
    if upper in _CONTAINER_ALIASES:
        mapped = _CONTAINER_ALIASES[upper]
        logging.info(
            "container type %r is not a tttrlib type; %s",
            name,
            f"reading as {mapped}" if mapped else "detecting it from the file",
        )
        return mapped
    for candidate in supported:
        if candidate.upper() == upper:
            return candidate
    logging.warning(
        "unknown container type %r (tttrlib offers %s); detecting from the file",
        name,
        ", ".join(supported),
    )
    return None


def apply_setup_lut(
    tttr,
    channel_luts: dict | None,
    channel_shifts: dict | None = None,
    *,
    apply_lut: bool = True,
    lut_seed: int = LUT_DITHER_SEED,
) -> bool:
    """Apply per-channel TAC-linearization LUTs + shifts to *tttr* **in place**.

    The single sanctioned way to LUT-correct a ``tttrlib.TTTR`` you already have
    (e.g. a raw object opened for a decay preview). Any code that produces a
    micro-time histogram from a setup that carries LUTs should call this before
    histogramming — otherwise the decay is raw and ignores the LUT. Reads opened
    through :func:`open_tttr` already run this.

    LUT first (linearize the TAC axis), then the wrapping photon-level shift, so
    the shift moves photons in uniform corrected bins. Uses a fixed positive
    dither seed for reproducibility.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        Object to correct in place.
    channel_luts : dict or None
        ``{routing_channel: NTAC_fract}``; ignored when *apply_lut* is false or empty.
    channel_shifts : dict or None
        ``{routing_channel: int}`` photon-level shifts (applied regardless of *apply_lut*).
    apply_lut : bool
        Master gate for the LUT linearization.
    lut_seed : int
        Dither seed (see :data:`LUT_DITHER_SEED`).

    Returns
    -------
    bool
        ``True`` if a LUT was applied.
    """
    applied = False
    if apply_lut and channel_luts:
        import numpy as np

        luts = {int(k): np.asarray(v, dtype=np.float64) for k, v in channel_luts.items()}
        if luts:
            tttr.apply_channel_luts(luts, {})
            tttr.apply_luts_and_shifts(int(lut_seed), True)
            applied = True
    if channel_shifts:
        from chisurf.core.fio.tttr_shift import apply_shifts

        apply_shifts(tttr, 0, {int(k): int(v) for k, v in channel_shifts.items()})
    return applied
