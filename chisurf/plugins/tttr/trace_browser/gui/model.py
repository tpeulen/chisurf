"""Qt-free state and actions of the Trace Browser.

:class:`TraceBrowserModel` holds what the Qt workspace
(:class:`chisurf.plugins.tttr.trace_browser.widget.TraceBrowser`) used to keep
inside its widgets: the current folder, the include-subfolders flag, the setup
(detector / channel definition) and the channels derived from it, the file rows
(name, path, size, rating, notes), the rating filter, the bin window, the y range,
the selection and the loaded trace.  The work the Qt tool did on that state is
here as plain methods -- scan a folder and fill the rows, filter them, read and
write ratings and notes (persisted through :mod:`..core.metadata`), clear, clear
the caches, and compute or load a trace (through :mod:`..core.trace` and the
RPC client, with the in-memory and on-disk caches) -- so the Qt tool and a later
native emtk app share one implementation.

Heavy methods (:meth:`~TraceBrowserModel.scan`,
:meth:`~TraceBrowserModel.precompute_all_traces`,
:meth:`~TraceBrowserModel.load_trace`) run headless and inside
:class:`chisurf.emtk.jobs.SnapshotJob`; the model provides ``notify(event)``,
``_observers`` and ``add_observer`` for that.

The module imports no Qt binding.  Computing a trace that is not cached still
needs the binning engine of the ``intensity_trace`` plugin (a Qt widget class,
imported lazily by :func:`..core.trace.load_trace` on a cache miss only).
"""

from __future__ import annotations

import logging
import pathlib
import shutil
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.plugins.tttr.trace_browser.core import metadata as _metadata
from chisurf.plugins.tttr.trace_browser.core import trace as _trace

try:
    import tttrlib
except Exception:  # pragma: no cover - tttrlib is an optional dependency here
    tttrlib = None

logger = logging.getLogger(__name__)

#: Labels of the rating filter, in the order of ``filter_index`` (0..4).
FILTER_LABELS = (
    "All",
    "≥ 1★",
    "≥ 2★★",
    "≥ 3★★★",
    "Only 0★",
)

#: Name of the per-folder trace cache directory (beside the data files).
CACHE_DIRNAME = ".tttr_trace_cache"

#: Container / format name of a setup -> typical file extensions.
FILETYPE_EXTENSIONS: dict[str, set[str]] = {
    "PTU": {".ptu"},
    "PT3": {".pt3"},
    "HT3": {".ht3"},
    "PT2": {".pt2"},
    "PT5": {".pt5"},
    "SPC-130": {".spc"},
    "SPC-600": {".spc"},
    "SPC-830": {".spc"},
    "PHU": {".phu"},
    "PHOTON_HDF5": {".h5", ".hdf5", ".photon.hdf5"},
    "HDF5": {".h5", ".hdf5"},
}


def get_tttr_supported_exts() -> list[str]:
    """Return the file extensions ``tttrlib`` reads (lower case, with the dot).

    Returns
    -------
    list of str
        Normalised extensions; empty when ``tttrlib`` is unavailable.
    """
    exts: list[str] = []
    try:
        if tttrlib is not None and hasattr(tttrlib, "get_supported_filetypes"):
            exts = list(tttrlib.get_supported_filetypes())
    except Exception:
        exts = []

    norm: list[str] = []
    for e in exts:
        s = str(e).strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = "." + s
        if s not in norm:
            norm.append(s)
    return norm


class TraceBrowserModel:
    """State and actions of the Trace Browser.

    Parameters
    ----------
    client : TraceBrowserClient, optional
        RPC client for metadata and trace loading; a local in-process one is
        created on first use.
    """

    def __init__(self, client: Any = None) -> None:
        self._client = client
        self._observers: list[Callable[[Any], None]] = []
        # -- folder and setup ------------------------------------------
        #: The folder whose traces are listed (``None`` before one is opened).
        self.current_folder: pathlib.Path | None = None
        #: Also list files in sub-folders.
        self.include_subfolders = False
        #: Detector / channel definition exactly as the setup page returns it.
        self.setup_settings: dict | None = None
        #: File type of the selected setup (``None`` or ``"Auto"`` = every supported type).
        self.setup_filetype: str | None = None
        #: Routing channels used by the traces (union over the setup's detectors).
        self.selected_channels: list[int] | None = None
        # -- files -----------------------------------------------------
        #: Per-folder metadata ``{relative path: {"rating": int, "annotation": str}}``.
        self.meta: dict[str, dict] = {}
        #: Every scanned file as a row dict (name, path, size, size_text, size_mb, rating, notes).
        self.files: list[dict[str, Any]] = []
        #: The rows that pass the rating filter (the file table's source).
        self.rows: list[dict[str, Any]] = []
        #: Index into :data:`FILTER_LABELS`.
        self.filter_index = 0
        # -- trace view ------------------------------------------------
        #: Bin window of the trace in milliseconds.
        self.window_ms = 10.0
        self.y_min = 0.0
        self.y_max = 1000.0
        #: Paths (str) of the selected rows.
        self.selected_files: list[str] = []
        #: The file whose trace is shown.
        self.current_file: pathlib.Path | None = None
        #: The shown trace: ``{"time_axis", "counts", "labels", "time_window_ms"}``.
        self.trace: dict[str, Any] | None = None
        #: Hand-off requests for the host application (filled by later cards).
        self.requests: list[dict[str, Any]] = []
        self.status_text = "Open a folder with TTTR files."
        self.error_text = ""
        #: ``callable(path) -> bool`` replacing the CLSM image probe (tests, hosts).
        self.image_probe: Callable[[pathlib.Path], bool] | None = None
        self._trace_mem_cache: dict[tuple[pathlib.Path, str], tuple] = {}
        self._is_image_cache: dict[pathlib.Path, bool] = {}

    # ── observers (SnapshotJob) ───────────────────────────────────────
    def add_observer(self, callback: Callable[[Any], None]) -> None:
        """Register ``callback(event)`` for :meth:`notify`."""
        self._observers.append(callback)

    def notify(self, event: Any = "updated") -> None:
        """Tell every observer that *event* happened."""
        for callback in list(self._observers):
            callback(event)

    # ── the backend client ────────────────────────────────────────────
    @property
    def client(self) -> Any:
        """The RPC client, created on first use."""
        if self._client is None:
            from .client import TraceBrowserClient

            self._client = TraceBrowserClient()
        return self._client

    # ── setup ─────────────────────────────────────────────────────────
    def apply_setup(self, settings: dict, filetype: str | None = None) -> None:
        """Accept a detector setup and derive the selected channels from it.

        Parameters
        ----------
        settings : dict
            Setup as returned by the detector wizard (``{"detectors": {...}, ...}``).
        filetype : str, optional
            The setup's file type; ``None`` / ``"Auto"`` accepts every supported type.
        """
        self.setup_settings = settings
        self.setup_filetype = filetype
        chs: list[int] = []
        for det in (settings or {}).get("detectors", {}).values():
            for c in det.get("chs", []):
                if c not in chs:
                    chs.append(c)
        self.selected_channels = sorted(chs) if chs else None
        logger.debug("TraceBrowser: Selected channels = %s", self.selected_channels)
        self.notify("setup")

    def allowed_exts(self) -> set[str]:
        """Return the file extensions allowed by the selected setup's file type.

        Returns
        -------
        set of str
            Lower-case extensions with the dot; every ``tttrlib``-supported one
            for ``Auto`` / no setup file type or an unknown one.
        """
        try:
            filetype = self.setup_filetype
            all_exts = set(get_tttr_supported_exts())
            if not filetype or str(filetype).strip().lower() == "auto":
                return all_exts
            exts = FILETYPE_EXTENSIONS.get(str(filetype).strip().upper())
            if exts:
                # Intersect with actually supported to be safe
                return {e for e in exts if (not all_exts or e in all_exts)} or exts
            return all_exts
        except Exception:
            return set(get_tttr_supported_exts())

    # ── rating filter ─────────────────────────────────────────────────
    @property
    def rating_filter(self) -> str:
        """Label of the active rating filter (one of :data:`FILTER_LABELS`)."""
        idx = self.filter_index
        return FILTER_LABELS[idx] if 0 <= idx < len(FILTER_LABELS) else FILTER_LABELS[0]

    @rating_filter.setter
    def rating_filter(self, label: str) -> None:
        self.filter_index = FILTER_LABELS.index(label) if label in FILTER_LABELS else 0

    def filter_accept(self, rating: int) -> bool:
        """Return whether *rating* passes the rating filter."""
        idx = self.filter_index
        if idx == 0:
            return True
        elif idx == 1:
            return rating >= 1
        elif idx == 2:
            return rating >= 2
        elif idx == 3:
            return rating >= 3
        elif idx == 4:
            return rating == 0
        return True

    def accepts(
        self, rating: int, path: pathlib.Path, allowed_exts: set[str] | None = None
    ) -> bool:
        """Return whether a file passes the rating filter and the setup's extensions."""
        if allowed_exts is None:
            allowed_exts = self.allowed_exts()
        rating_ok = self.filter_accept(rating)
        ext_ok = (not allowed_exts) or (pathlib.Path(path).suffix.lower() in allowed_exts)
        return rating_ok and ext_ok

    def set_rating_filter(self, value: Any = None) -> None:
        """Apply the rating filter (``value`` is an index or a label, optional)."""
        if isinstance(value, str):
            self.rating_filter = value
        elif isinstance(value, int):
            self.filter_index = value
        self.apply_filter()

    def apply_filter(self) -> list[pathlib.Path]:
        """Re-filter :attr:`files` into :attr:`rows`; drop files that vanished.

        Returns
        -------
        list of pathlib.Path
            The files that no longer exist and were dropped from :attr:`files`.
        """
        missing: list[pathlib.Path] = []
        kept: list[dict[str, Any]] = []
        for row in self.files:
            p = pathlib.Path(row["path"])
            try:
                if not p.exists():
                    missing.append(p)
                    continue
            except Exception:
                pass  # be conservative and keep the row
            kept.append(row)
        self.files = kept
        allowed = self.allowed_exts()
        self.rows = [r for r in kept if self.accepts(int(r["rating"]), pathlib.Path(r["path"]), allowed)]
        keep = {r["path"] for r in self.rows}
        self.selected_files = [s for s in self.selected_files if s in keep]
        if self.current_file is not None and not self.current_file.exists():
            self.current_file = None
            self.trace = None
        self.notify("rows")
        return missing

    # ── folder, scan ──────────────────────────────────────────────────
    def open_folder(self, folder: str | pathlib.Path) -> bool:
        """Open *folder*: load its metadata and scan it.

        Returns
        -------
        bool
            ``False`` (and :attr:`error_text` set) when *folder* is not a directory
            or scanning failed.
        """
        folder = pathlib.Path(folder)
        try:
            if not folder.exists() or not folder.is_dir():
                self.error_text = f"Not a folder: {folder}"
                logger.warning("TraceBrowser: Selected path is not a folder: %s", folder)
                return False
            self.error_text = ""
            self.current_folder = folder
            logger.info("TraceBrowser: Opened folder %s", folder)
            self.load_meta()
            self.scan()
            return True
        except Exception as e:
            self.error_text = f"Failed to open {folder}: {e}"
            logger.exception("TraceBrowser: Failed to open folder %s: %s", folder, e)
            return False

    def set_include_subfolders(self, value: Any = None) -> None:
        """Set the include-subfolders flag (when given) and rescan the open folder."""
        if value is not None:
            self.include_subfolders = bool(value)
        if self.current_folder:
            self.scan()

    def scan(self) -> list[dict[str, Any]]:
        """Scan :attr:`current_folder` and fill :attr:`files` and :attr:`rows`.

        Lists the files of the setup's file types (optionally recursively),
        skipping anything under a ``.trash`` folder and image-like (CLSM) TTTR
        files, auto-selects the channels of the first usable file when no setup
        defined them, and reads each file's rating and notes from the metadata.

        Returns
        -------
        list of dict
            The visible :attr:`rows`.
        """
        if not self.current_folder:
            return []
        folder = self.current_folder
        files: list[pathlib.Path] = []
        allowed_exts = self.allowed_exts()
        recursive = bool(self.include_subfolders)
        try:
            it = folder.rglob("*") if recursive else folder.iterdir()
        except Exception:
            it = folder.iterdir()
        for p in sorted(it):
            try:
                if not p.is_file():
                    continue
                # Exclude anything under a hidden .trash within the current folder
                try:
                    relp = p.relative_to(folder)
                    if any(part == ".trash" for part in relp.parts):
                        continue
                except Exception:
                    pass
                if not allowed_exts or p.suffix.lower() in allowed_exts:
                    # Skip CLSM/image TTTR files; Trace Browser should only list non-image TTTRs
                    try:
                        if self.is_image_tttr(p):
                            continue
                    except Exception:
                        pass
                    files.append(p)
            except Exception:
                continue
        # Auto-initialize channels if setup was not used: detect from first TTTR
        try:
            if tttrlib is not None and self.selected_channels is None and files:
                for _p in files:
                    try:
                        if self.is_image_tttr(_p):
                            continue
                    except Exception:
                        pass
                    try:
                        tt = tttrlib.TTTR(str(_p))
                        chs = sorted(tt.get_used_routing_channels())
                        if chs:
                            self.selected_channels = chs
                            logger.info("TraceBrowser: Auto-selected channels from %s: %s", _p.name, chs)
                            break
                    except Exception:
                        continue
        except Exception as _e:
            logger.debug("TraceBrowser: Auto channel initialization skipped: %s", _e)
        self.files = [self._make_row(p) for p in files]
        self.apply_filter()
        logger.debug(
            "TraceBrowser: Found %d files (%s), displaying %d after filter",
            len(files),
            "recursive" if recursive else "flat",
            len(self.rows),
        )
        self.status_text = f"{len(self.rows)} of {len(files)} file(s) in {folder}"
        self.notify("files")
        return self.rows

    def _make_row(self, p: pathlib.Path) -> dict[str, Any]:
        """Build the table row of file *p* from the disk and the metadata."""
        try:
            rel_txt = str(p.relative_to(self.current_folder))
        except Exception:
            rel_txt = p.name
        try:
            sz = p.stat().st_size
        except Exception:
            sz = 0
        rec = self.meta_get(p)
        return {
            "name": rel_txt,
            "path": str(p),
            "size": sz,
            "size_text": _trace.human_size(sz),
            "size_mb": float(sz) / (1024.0 * 1024.0),
            "rating": int(rec.get("rating", 0)),
            "notes": str(rec.get("annotation", "")),
        }

    def clear(self) -> None:
        """Clear the file list, the selection and the shown trace (files and metadata stay)."""
        self.files = []
        self.rows = []
        self.selected_files = []
        self.current_file = None
        self.trace = None
        logger.info("TraceBrowser: Cleared file list")
        self.notify("rows")

    # ── image detection ───────────────────────────────────────────────
    def is_clsm_compatible(self, tttr_obj: Any) -> bool:
        """Probe whether *tttr_obj* supports CLSM imaging (an image-like dataset)."""
        try:
            clsm = tttrlib.CLSMImage(tttr_data=tttr_obj)
            _ = getattr(clsm, "intensity", None)
            return _ is not None
        except Exception:
            return False

    def probe_image(self, path: pathlib.Path) -> bool:
        """The default image probe: open *path* with ``tttrlib`` and test CLSM support."""
        v = self._is_image_cache.get(path)
        if v is not None:
            return v
        if tttrlib is None:
            self._is_image_cache[path] = False
            return False
        try:
            tt = tttrlib.TTTR(str(path))
            v = self.is_clsm_compatible(tt)
            self._is_image_cache[path] = bool(v)
            return bool(v)
        except Exception:
            # On failure to open, treat as non-image to let other filters decide
            self._is_image_cache[path] = False
            return False

    def is_image_tttr(self, path: pathlib.Path) -> bool:
        """Return whether *path* is an image (CLSM) TTTR file (uses :attr:`image_probe` if set)."""
        if self.image_probe is not None:
            return bool(self.image_probe(path))
        return self.probe_image(path)

    # ── metadata: ratings and notes ───────────────────────────────────
    def load_meta(self) -> dict[str, dict]:
        """(Re)load the metadata of :attr:`current_folder` (RPC first, then the file)."""
        folder = self.current_folder
        if folder is None:
            self.meta = {}
            return self.meta
        self.meta = self.client.get_metadata(str(folder)) or _metadata.load_meta(folder)
        return self.meta

    def rel_key(self, path: pathlib.Path) -> str:
        """Return the metadata key of *path*: relative to the folder, else the file name."""
        try:
            if self.current_folder is not None:
                return str(pathlib.Path(path).resolve().relative_to(self.current_folder.resolve()))
        except Exception:
            pass
        try:
            return pathlib.Path(path).name
        except Exception:
            return str(path)

    def meta_get(self, path: pathlib.Path) -> dict:
        """Return the metadata record of *path* (an empty dict when there is none)."""
        key = self.rel_key(path)
        rec = self.meta.get(key)
        if rec is not None:
            return rec
        # Backward compatibility: older meta by filename only
        try:
            return self.meta.get(pathlib.Path(path).name, {})
        except Exception:
            return {}

    def meta_set(self, path: pathlib.Path, rec: dict) -> None:
        """Store *rec* as the metadata of *path* and push the metadata to the backend."""
        key = self.rel_key(path)
        self.meta[key] = rec
        if self.current_folder is not None:
            try:
                self.client.set_metadata(str(self.current_folder), dict(self.meta))
            except Exception:
                pass

    def flush_meta(self) -> bool:
        """Write the metadata to the folder's ``.trace_browser_meta.json``.

        Returns
        -------
        bool
            ``True`` when the file was written.
        """
        try:
            if self.current_folder:
                _metadata.save_meta(self.current_folder, self.meta)
                return True
        except Exception:
            pass
        return False

    def get_rating(self, path: str | pathlib.Path) -> int:
        """Return the 0..5 rating of *path* (0 when unrated)."""
        return int(self.meta_get(pathlib.Path(path)).get("rating", 0))

    def get_notes(self, path: str | pathlib.Path) -> str:
        """Return the notes (annotation) of *path*."""
        return str(self.meta_get(pathlib.Path(path)).get("annotation", ""))

    def set_rating(self, path: str | pathlib.Path, rating: int, flush: bool = True) -> None:
        """Set the rating of *path*, persist it and refresh the filtered rows.

        Parameters
        ----------
        path : str or pathlib.Path
            The file.
        rating : int
            New rating (0..5).
        flush : bool
            Also write the metadata file now (a host that debounces writes passes ``False``).
        """
        if not self.current_folder:
            return
        path = pathlib.Path(path)
        rec = self.meta_get(path)
        rec["rating"] = int(rating)
        self.meta_set(path, rec)
        self._sync_row(path, rating=int(rating))
        if flush:
            self.flush_meta()
        self.apply_filter()
        self.notify("meta")

    def set_notes(self, path: str | pathlib.Path, text: str, flush: bool = True) -> None:
        """Set the notes (annotation) of *path* and persist them."""
        if not self.current_folder:
            return
        path = pathlib.Path(path)
        rec = self.meta_get(path)
        rec["annotation"] = str(text)
        self.meta_set(path, rec)
        self._sync_row(path, notes=str(text))
        if flush:
            self.flush_meta()
        self.notify("meta")

    def _sync_row(self, path: pathlib.Path, **fields: Any) -> None:
        """Update the row of *path* in :attr:`files` (rows share the same dicts)."""
        sp = str(path)
        for row in self.files:
            if row["path"] == sp:
                row.update(fields)

    # ── selection ─────────────────────────────────────────────────────
    def set_selection(self, paths: list[str | pathlib.Path]) -> None:
        """Select the rows of *paths* (only files that are listed)."""
        listed = {r["path"] for r in self.rows}
        self.selected_files = [str(p) for p in paths if str(p) in listed]
        self.notify("selection")

    def first_selected(self) -> pathlib.Path | None:
        """Return the first selected file, or ``None``."""
        return pathlib.Path(self.selected_files[0]) if self.selected_files else None

    # ── y range ───────────────────────────────────────────────────────
    @property
    def y_range(self) -> tuple[float, float]:
        """The y range ordered as ``(low, high)`` (the two fields may be entered swapped)."""
        lo, hi = float(self.y_min), float(self.y_max)
        return (hi, lo) if lo > hi else (lo, hi)

    # ── traces and caches ─────────────────────────────────────────────
    def _cache_folder(self) -> str | None:
        return str(self.current_folder) if self.current_folder is not None else None

    def trace_signature(self, path: pathlib.Path, window_ms: float | None = None) -> str:
        """Return the cache signature of the trace of *path* for the current setup."""
        window_ms = self.window_ms if window_ms is None else window_ms
        return _trace.trace_signature(
            pathlib.Path(path), window_ms, self.setup_settings, self.selected_channels
        )

    def load_trace_cache(
        self, path: pathlib.Path, window_ms: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, list[str]] | None:
        """Return the on-disk cached trace of *path*, or ``None``."""
        window_ms = self.window_ms if window_ms is None else window_ms
        folder = self.current_folder or pathlib.Path(path).parent
        return _trace.load_cached(
            pathlib.Path(path), folder, window_ms, self.setup_settings, self.selected_channels
        )

    def compute_trace_cached(
        self, path: pathlib.Path, window_ms: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Return ``(time_axis, counts, labels)`` of *path*: memory cache, disk cache, compute.

        The computation and the on-disk cache are :func:`..core.trace.load_trace`
        (the same code the RPC backend runs); the in-memory cache is the model's.
        """
        path = pathlib.Path(path)
        window_ms = self.window_ms if window_ms is None else window_ms
        key = (path, self.trace_signature(path, window_ms))
        hit = self._trace_mem_cache.get(key)
        if hit is not None:
            return hit
        data = _trace.load_trace(
            str(path),
            time_window_ms=window_ms,
            setup_settings=self.setup_settings,
            selected_channels=self.selected_channels,
            cache_folder=self._cache_folder(),
        )
        result = (
            np.asarray(data["time_axis"], dtype=float),
            np.asarray(data["counts"], dtype=float),
            [str(label) for label in data["labels"]],
        )
        self._trace_mem_cache[key] = result
        return result

    def load_trace(
        self, path: str | pathlib.Path, window_ms: float | None = None
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Load the binned trace of *path* (RPC client first, then in-process compute).

        Returns
        -------
        tuple
            ``(time_axis, counts, labels)``; *counts* is ``(bins, series)``.
        """
        path = pathlib.Path(path)
        window_ms = self.window_ms if window_ms is None else window_ms
        trace = self.client.load_trace(
            str(path),
            time_window_ms=window_ms,
            setup_settings=self.setup_settings,
            selected_channels=self.selected_channels,
            cache_folder=self._cache_folder(),
        )
        if trace is not None:
            return (
                np.asarray(trace.get("time_axis", []), dtype=float),
                np.asarray(trace.get("counts", []), dtype=float),
                [str(label) for label in trace.get("labels", [])],
            )
        return self.compute_trace_cached(path, window_ms)

    def show_file(self, path: str | pathlib.Path) -> bool:
        """Load the trace of *path* into :attr:`trace` and make it the current file.

        Returns
        -------
        bool
            ``False`` (and :attr:`error_text` set) when the trace could not be loaded.
        """
        path = pathlib.Path(path)
        try:
            time_axis, counts, labels = self.load_trace(path)
        except Exception as e:
            self.error_text = f"Failed to load {path.name}: {e}"
            logger.exception("TraceBrowser: Failed to load %s: %s", path, e)
            return False
        self.error_text = ""
        self.trace = {
            "time_axis": time_axis,
            "counts": counts,
            "labels": labels,
            "time_window_ms": float(self.window_ms),
        }
        self.current_file = path
        self.notify("trace")
        return True

    def set_window_ms(self, value: Any = None) -> None:
        """Set the bin window (when given) and reload the trace of the current file."""
        if value is not None:
            self.window_ms = float(value)
        if self.current_file is not None:
            self.show_file(self.current_file)

    def warm_trace_cache(self, paths: list[pathlib.Path]) -> list[pathlib.Path]:
        """Load already-cached traces of *paths* into memory; return those still to compute."""
        todo: list[pathlib.Path] = []
        for p in paths:
            try:
                loaded = self.load_trace_cache(p, self.window_ms)
                if loaded is not None:
                    self._trace_mem_cache[(p, self.trace_signature(p, self.window_ms))] = loaded
                else:
                    todo.append(p)
            except Exception:
                todo.append(p)
        return todo

    def precompute_all_traces(
        self, progress: Callable[[int, int, pathlib.Path | None], bool | None] | None = None
    ) -> int:
        """Compute and cache the trace of every listed file for snappy browsing.

        Parameters
        ----------
        progress : callable, optional
            ``progress(i, total, path)`` before each file (return ``False`` to stop)
            and ``progress(total, total, None)`` once at the end.

        Returns
        -------
        int
            Number of traces computed.
        """
        if self.current_folder is None or tttrlib is None:
            return 0
        paths: list[pathlib.Path] = []
        for row in self.rows:
            pth = pathlib.Path(row["path"])
            # Defensive: skip image files even if present in the rows for any reason
            try:
                if self.is_image_tttr(pth):
                    continue
            except Exception:
                pass
            paths.append(pth)
        if not paths:
            return 0
        todo = self.warm_trace_cache(paths)
        if not todo:
            return 0
        computed = 0
        try:
            for i, p in enumerate(todo):
                if progress is not None and progress(i, len(todo), p) is False:
                    break
                try:
                    self.compute_trace_cached(p, self.window_ms)
                    computed += 1
                except Exception:
                    pass
        finally:
            if progress is not None:
                progress(len(todo), len(todo), None)
        self.notify("traces")
        return computed

    def clear_caches(self) -> int:
        """Clear the in-memory caches and the folder's on-disk trace cache.

        Returns
        -------
        int
            Number of cache directories removed (0 or 1).
        """
        self._trace_mem_cache.clear()
        self._is_image_cache.clear()
        removed_dirs = 0
        base = self.current_folder
        if base and isinstance(base, pathlib.Path):
            cache_dir = base / CACHE_DIRNAME
            try:
                if cache_dir.exists() and cache_dir.is_dir():
                    shutil.rmtree(str(cache_dir), ignore_errors=True)
                    removed_dirs += 1
            except Exception:
                pass
        logger.info("TraceBrowser: Cleared caches (memory + %d dir(s) removed)", removed_dirs)
        self.status_text = "Trace caches cleared."
        self.notify("caches")
        return removed_dirs
