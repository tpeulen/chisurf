"""Qt-free view-model for the TTTR Image Browser.

Drives the reusable ``image_browser`` AutoForm section: browsable file entries
(with star ratings + size badges), the per-file intensity **mosaic** as the image
canvas, per-tile channel/micro-time labels, and an editable annotation note.  All
data flows through the existing Qt-free core via the RPC client
(:class:`TTTRImageBrowserClient`) — this module holds no Qt.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

import numpy as np

from ..gui.client import TTTRImageBrowserClient

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "browser.view.json"

#: Rating-filter choices (label → minimum/exact rating predicate).
RATING_FILTERS = ["All", "≥ 1★", "≥ 2★★", "≥ 3★★★", "Only 0★"]


class ImageBrowserViewModel:
    """State + logic for the TTTR image browser (no Qt)."""

    def __init__(self, client: TTTRImageBrowserClient | None = None) -> None:
        self._client = client or TTTRImageBrowserClient()
        self.current_folder: str | None = None
        self.setup_settings: dict | None = None
        self.recursive: bool = False
        self.rating_filter: str = "All"
        self.meta: dict[str, dict] = {}
        self.current_file: str | None = None
        self.selected_files: list[str] = []
        self._files: list[dict] = []
        self._mosaic_cache: dict[str, dict] = {}
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── observers ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb*, called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers of a state change."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("image-browser observer failed", exc_info=True)

    # ── folder / scan ──
    def open_folder(self, folder: str) -> None:
        """Open *folder*, load its metadata and list its image files."""
        self.current_folder = str(folder)
        try:
            self.meta = self._client.get_metadata(self.current_folder)
        except Exception:
            self.meta = {}
        self._mosaic_cache.clear()
        self._rescan()
        self.notify("folder")

    def _rescan(self) -> None:
        if not self.current_folder:
            self._files = []
            return
        try:
            self._files = self._client.list_files(
                self.current_folder, recursive=self.recursive, setup_settings=self.setup_settings
            )
        except Exception:
            logger.debug("list_files failed", exc_info=True)
            self._files = []

    def set_recursive(self, on: bool) -> None:
        """Toggle recursive scanning and re-list the current folder."""
        self.recursive = bool(on)
        if self.current_folder:
            self._rescan()
            self.notify("folder")

    def rating_filter_options(self) -> list[str]:
        """Return the selectable rating-filter labels (for the choice section)."""
        return list(RATING_FILTERS)

    def set_rating_filter(self, value) -> None:
        """Set the rating filter (one of :data:`RATING_FILTERS`)."""
        self.rating_filter = str(value)
        self.notify("filter")

    def clear(self) -> None:
        """Clear the file list and preview."""
        self._files = []
        self.current_file = None
        self.selected_files = []
        self.notify("folder")

    def clear_caches(self) -> None:
        """Drop the in-memory mosaic cache (on-disk caches handled by the tool)."""
        self._mosaic_cache.clear()
        self.notify("changed")

    def on_drop(self, paths) -> None:
        """Open the first dropped directory (drag-drop a folder onto the list)."""
        for p in paths or []:
            path = pathlib.Path(p)
            if path.is_dir():
                self.open_folder(str(path))
                return

    # ── metadata helpers ──
    def _rel_key(self, path: str) -> str:
        try:
            if self.current_folder:
                return str(
                    pathlib.Path(path)
                    .resolve()
                    .relative_to(pathlib.Path(self.current_folder).resolve())
                )
        except Exception:
            pass
        return pathlib.Path(path).name

    def _rec(self, path: str) -> dict:
        key = self._rel_key(path)
        return self.meta.get(key) or self.meta.get(pathlib.Path(path).name, {})

    def _save_rec(self, path: str, rec: dict) -> None:
        self.meta[self._rel_key(path)] = rec
        if self.current_folder:
            try:
                self._client.set_metadata(self.current_folder, dict(self.meta))
            except Exception:
                logger.debug("set_metadata failed", exc_info=True)

    def rating_of(self, path: str) -> int:
        """Return the stored star rating (0 when unset) for *path*."""
        return int(self._rec(path).get("rating", 0) or 0)

    def set_rating(self, path: str, value: int) -> None:
        """Persist a star rating for *path* and refresh the list."""
        rec = dict(self._rec(path))
        rec["rating"] = int(value)
        self._save_rec(path, rec)
        self.notify("rating")

    def note_of(self, path: str) -> str:
        """Return the stored annotation text for *path*."""
        return str(self._rec(path).get("annotation", "") or "")

    def set_note(self, path: str, text: str) -> None:
        """Persist the annotation text for *path*."""
        rec = dict(self._rec(path))
        rec["annotation"] = str(text)
        self._save_rec(path, rec)

    # ── AutoForm image_browser accessors ──
    def _passes_filter(self, path: str) -> bool:
        rating = self.rating_of(path)
        f = self.rating_filter
        if f == "Only 0★":
            return rating == 0
        if f == "≥ 1★":
            return rating >= 1
        if f == "≥ 2★★":
            return rating >= 2
        if f == "≥ 3★★★":
            return rating >= 3
        return True  # "All"

    def file_entries(self) -> list[dict]:
        """Browsable file entries (id = path; badge = size + rating stars)."""
        entries: list[dict] = []
        for rec in self._files:
            path = rec.get("path")
            if not path or not self._passes_filter(path):
                continue
            rating = self.rating_of(path)
            badge = rec.get("size_text", "")
            if rating:
                badge = f"{badge}  {'★' * rating}"
            entries.append(
                {
                    "id": path,
                    "label": self._rel_key(path),
                    "badge": badge,
                    "rating": rating,
                }
            )
        return entries

    def _mosaic(self) -> dict | None:
        if not self.current_file:
            return None
        cached = self._mosaic_cache.get(self.current_file)
        if cached is not None:
            return cached
        res = None
        try:
            res = self._client.load_image(
                self.current_file,
                setup_settings=self.setup_settings,
                max_side=512,
                cache_folder=self.current_folder,
            )
        except Exception:
            logger.debug("load_image failed", exc_info=True)
        if res is None:
            return None
        entry = {
            "mosaic": np.asarray(res["mosaic"], dtype=np.uint8),
            "labels": res.get("labels", []),
            "cols": int(res.get("cols", 1)),
            "rows": int(res.get("rows", 1)),
        }
        self._mosaic_cache[self.current_file] = entry
        return entry

    def current_image(self):
        """Intensity mosaic (2-D uint8) of the current file, or None."""
        m = self._mosaic()
        return m["mosaic"] if m else None

    def image_labels(self) -> list[dict]:
        """Per-tile channel/micro-time labels positioned on the mosaic."""
        m = self._mosaic()
        if not m or not m["labels"]:
            return []
        mosaic, cols, rows = m["mosaic"], m["cols"], m["rows"]
        tile_h = mosaic.shape[0] // max(rows, 1)
        tile_w = mosaic.shape[1] // max(cols, 1)
        out = []
        for idx, text in enumerate(m["labels"]):
            r, c = divmod(idx, max(cols, 1))
            out.append({"x": c * tile_w + 3, "y": r * tile_h + 3, "text": str(text)})
        return out

    def current_note(self) -> str:
        """Annotation text of the current file (for the editable note box)."""
        return self.note_of(self.current_file) if self.current_file else ""

    def info_html(self) -> str:
        """Short status/summary shown above the annotation note."""
        if not self.current_folder:
            return "<i>Open a folder (or drop one here) with TTTR imaging files.</i>"
        n = len(self.file_entries())
        return f"<i>{n} image(s) in {pathlib.Path(self.current_folder).name}</i>"

    def select_file(self, path) -> None:
        """image_browser ``select_call``: record the selection and notify."""
        self.selected_files = [path] if path else []
        self.notify("select")

    # ── setup / pipeline ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt a shared detector definition and re-list the folder."""
        if not payload:
            return
        self.setup_settings = payload
        if self.current_folder:
            self._rescan()
        self.notify("setup")
