"""Qt-free model of the native TTTR image browser.

Extends :class:`~.view_model.ImageBrowserViewModel` (the Qt tool's view model, unchanged: folder scan, ratings,
annotations, the detector-window mosaic and its tile labels) with what the emtk window needs: the table rows,
a multi-selection, the display settings of the image (colormap, gamma, levels), the toolbar actions with their
enabled state, the exports (raw copy, TIFF stacks, DOCX report) and the settings the host persists.

The model never reads an image in the draw loop: the app asks :meth:`wanted_image` which mosaic it lacks and
loads it on a worker (:class:`MosaicLoader`); the actions that take long (a scan, the exports) are model methods
the app runs on a snapshot worker.
"""

from __future__ import annotations

import io
import pathlib
import shutil
from types import SimpleNamespace
from typing import Any

import numpy as np

from chisurf.plugins.microscopy.imaging_emtk.model_base import EmtkModelMixin

from .client import TTTRImageBrowserClient
from .view_model import RATING_FILTERS, ImageBrowserViewModel

#: Colormaps the Qt image dock offers (``chisurf.gui.autoform.sections.builtin.IMAGE_COLORMAPS``), in its order.
COLORMAPS = ("viridis", "magma", "inferno", "plasma", "cividis", "turbo", "gray")

#: Longest side, in pixels, of the mosaic the preview reconstructs (the Qt view model asks for the same).
MAX_SIDE = 512


def local_client() -> TTTRImageBrowserClient:
    """The browser's RPC client wired straight to the service handlers (no server, no Qt)."""
    from ..api import contract as c
    from ..backend import services as s

    routes = {
        c.METHOD_LIST_FILES: s._list_files_handler,
        c.METHOD_GET_METADATA: s._get_metadata_handler,
        c.METHOD_SET_METADATA: s._set_metadata_handler,
        c.METHOD_LOAD_IMAGE: s._load_image_handler,
        c.METHOD_EXPORT_TIFF: s._export_tiff_handler,
        c.METHOD_CONTRACT: lambda p: s._contract_handler(),
    }
    return TTTRImageBrowserClient(
        SimpleNamespace(call=lambda method, params=None: routes[method](params or {}))
    )


class MosaicLoader:
    """Reconstructs one mosaic on a worker without touching the model the user is editing.

    The app runs ``SnapshotJob(loader).start("load", ...)``; the finished copy carries ``path`` and ``result``,
    which the app hands to :meth:`ImageBrowserModel.store_mosaic` when the file is still the one asked for.
    """

    def __init__(self, client: TTTRImageBrowserClient) -> None:
        self._client = client
        self.path: str | None = None
        self.result: dict | None = None

    def load(self, path: str, setup_settings: dict | None, folder: str | None) -> None:
        """Load (or read from the on-disk cache) the mosaic of *path*."""
        self.path, self.result = path, None
        self.result = self._client.load_image(
            path, setup_settings=setup_settings, max_side=MAX_SIDE, cache_folder=folder
        )

    def notify(self, _event: str = "") -> None:
        """Snapshot workers announce progress here; nothing listens."""


class ImageBrowserModel(EmtkModelMixin, ImageBrowserViewModel):
    """State and actions of the native browser (no Qt)."""

    SETTINGS = (
        "recursive",
        "rating_filter",
        "colormap",
        "gamma",
        "auto_levels",
        "show_labels",
        "multi_select",
    )

    def __init__(self, client: TTTRImageBrowserClient | None = None) -> None:
        super().__init__(client or local_client())
        self.status_line = "Open a folder of photon files, or drop one on the window."
        # selection
        self.multi_select = False
        self.select_all_requested = False
        # display of the mosaic
        self.colormap = "magma"
        self.gamma = 1.0
        self.auto_levels = True
        self.level_low = 0.0
        self.level_high = 255.0
        self.show_labels = True
        self.reset_view_requested = False
        # requests the app answers (help window, guided tour, hand-off to the pipeline)
        self.requests: list[str] = []
        self.can_next = False
        self.setup_name = ""
        self.last_written: list[str] = []
        self._failed: dict[str, str] = {}

    # ------------------------------------------------------------------ choices
    def rating_filter_choices(self) -> list[str]:
        """The rating-filter labels (what ``restore_settings`` checks a saved value against)."""
        return list(RATING_FILTERS)

    def colormap_options(self) -> list[str]:
        """The colormaps the display offers."""
        return list(COLORMAPS)

    def colormap_choices(self) -> list[str]:
        """The colormaps (what ``restore_settings`` checks a saved value against)."""
        return list(COLORMAPS)

    # ------------------------------------------------------------------ enabled / bounds
    def enabled(self, name: str) -> bool:
        """Whether the field or action *name* can be used now."""
        if name in ("copy_files", "export_tiff"):
            return bool(self.paths()) and not self.busy
        if name == "export_docx":
            return bool(self.file_entries()) and bool(self.current_folder) and not self.busy
        if name == "clear":
            return bool(self._files) and not self.busy
        if name == "clear_caches":
            return bool(self.current_folder) and not self.busy
        if name in ("choose_folder", "recursive"):
            return not self.busy
        if name == "next_step":
            return self.can_next
        if name == "select_all_files":
            return bool(self.file_entries())
        if name in ("rate_0", "rate_1", "rate_2", "rate_3", "current_rating"):
            return self.current_file is not None
        if name in ("level_low", "level_high"):
            return not self.auto_levels and self.current_image() is not None and not self.busy
        if name in ("colormap", "gamma", "auto_levels", "show_labels", "reset_view"):
            return self.current_image() is not None and not self.busy
        return True

    def bounds(self, name: str) -> tuple[float, float] | None:
        """Moving limits of a field (the display levels keep ``Min`` below ``Max``); ``None``: the spec's own."""
        if name == "level_low":
            return 0.0, max(0.0, float(self.level_high) - 1.0)
        if name == "level_high":
            return min(254.0, float(self.level_low) + 1.0), 255.0
        return None

    # ------------------------------------------------------------------ files
    @property
    def folder_text(self) -> str:
        """The opened folder (an empty text before one is opened)."""
        return self.current_folder or ""

    def open_folder(self, folder: str) -> None:
        """Open *folder*: its metadata, its photon files, nothing selected."""
        path = pathlib.Path(str(folder))
        if not path.is_dir():
            self.status_line = f"Not a folder: {path}"
            return
        self._failed = {}
        super().open_folder(str(path))
        self.folder = str(path)
        self.status_line = self.info_text()

    def on_drop(self, paths) -> None:
        """Open the first dropped directory (the Qt workspace ignores everything else)."""
        for p in paths or []:
            if pathlib.Path(p).is_dir():
                self.open_folder(str(p))
                return
        if paths:
            self.status_line = "Drop a folder of photon files, not a single file."

    def apply_pipeline_context(self, payload: dict) -> None:
        """The imaging hub's current source: open the folder that holds it and select it."""
        files = payload.get("files") or ([payload["file"]] if payload.get("file") else [])
        if not files:
            return
        first = pathlib.Path(str(files[0]))
        folder = first if first.is_dir() else first.parent
        if self.current_folder != str(folder):
            self.open_folder(str(folder))
        if first.is_file() and str(first) in [e["id"] for e in self.file_entries()]:
            self.select_file(str(first))

    def clear(self) -> None:
        """Clear the file list and the preview (no file, rating or note is changed)."""
        super().clear()
        self.status_line = "Cleared the file list."

    def clear_caches(self) -> None:
        """Remove the in-memory mosaics and every ``.tttr_image_cache`` folder below the opened folder."""
        super().clear_caches()
        self._failed = {}
        if self.current_folder:
            from ..core.image import CACHE_DIR_NAME

            for directory in pathlib.Path(self.current_folder).rglob(CACHE_DIR_NAME):
                if directory.is_dir():
                    shutil.rmtree(directory, ignore_errors=True)
        self.status_line = "Image caches cleared."

    # ------------------------------------------------------------------ table
    def rows(self) -> list[dict]:
        """One record per listed file: ``path``, ``name`` (relative), ``size_mb`` and the ``rating`` as stars."""
        sizes = {rec.get("path"): rec.get("size", 0) for rec in self._files}
        out = []
        for entry in self.file_entries():
            out.append(
                {
                    "path": entry["id"],
                    "name": entry["label"],
                    "size_mb": float(sizes.get(entry["id"], 0)) / (1024.0 * 1024.0),
                    "rating": "★" * int(entry["rating"]),
                }
            )
        return out

    def select_row(self, record: Any) -> None:
        """The table's ``selected_call``: select the row, or toggle it while *Multiple selection* is on."""
        path = record.get("path") if isinstance(record, dict) else None
        if path is None:
            self.select_file(None)
            return
        if not self.multi_select:
            self.select_file(path)
            return
        selected = list(self.selected_files)
        if path in selected:
            selected.remove(path)
            self.selected_files = selected
            if self.current_file == path:
                self.current_file = selected[-1] if selected else None
        else:
            selected.append(path)
            self.selected_files = selected
            self.current_file = path
        self.notify("select")

    def select_all_files(self) -> None:
        """Select every listed file (the table applies its own text filter to this)."""
        self.select_all_requested = True
        self.multi_select = True

    def set_multi_select(self, on: bool) -> None:
        """The *Multiple selection* check box: switching it off keeps only the current file."""
        self.multi_select = bool(on)
        if not self.multi_select and len(self.selected_files) > 1:
            keep = self.current_file if self.current_file in self.selected_files else self.selected_files[-1]
            self.selected_files = [keep]
            self.current_file = keep
            self.notify("select")

    def paths(self) -> list[str]:
        """The files the exports act on: the selection, or the current file."""
        return list(self.selected_files) or ([self.current_file] if self.current_file else [])

    def info_text(self) -> str:
        """What the Qt info panel said (how many images are listed), plus the selection count."""
        if not self.current_folder:
            return ""
        n = len(self.file_entries())
        text = f"{n} image(s) in {pathlib.Path(self.current_folder).name}"
        if len(self.selected_files) > 1:
            text += f", {len(self.selected_files)} selected"
        return text

    def file_info(self) -> str:
        """The current file's mosaic in words (tiles and size), or why there is none."""
        path = self.current_file
        if not path:
            return ""
        name = pathlib.Path(path).name
        if path in self._failed:
            return f"{name}: {self._failed[path]}"
        m = self._mosaic_cache.get(path)
        if m is None:
            return f"{name}: loading"
        h, w = m["mosaic"].shape
        return f"{name}: {len(m['labels'])} tile(s), mosaic {w} x {h} px"

    def setup_text(self) -> str:
        """Which detector setup the tiles follow."""
        if not self.setup_settings:
            return "none: every supported file type, one tile with all channels"
        reading = self.setup_settings.get("tttr_reading", {}) or {}
        n = len(self.setup_settings.get("detectors", {}) or {})
        name = f"{self.setup_name}: " if self.setup_name else ""
        return f"{name}{n} detector(s), file type {reading.get('file_type') or 'auto'}"

    # ------------------------------------------------------------------ rating
    def rate(self, value: int) -> None:
        """Set the rating of the current file (0 clears it)."""
        if self.current_file:
            self.set_rating(self.current_file, int(value))
            self.status_line = f"{pathlib.Path(self.current_file).name}: rating {int(value)}"

    @property
    def current_rating(self) -> int:
        """Stars of the current file (the *Rating* radio buttons read and write this)."""
        return self.rating_of(self.current_file) if self.current_file else 0

    @current_rating.setter
    def current_rating(self, value: int) -> None:
        self.rate(int(value))

    def rate_0(self) -> None:
        """Clear the rating of the current file."""
        self.rate(0)

    def rate_1(self) -> None:
        """One star for the current file."""
        self.rate(1)

    def rate_2(self) -> None:
        """Two stars for the current file."""
        self.rate(2)

    def rate_3(self) -> None:
        """Three stars for the current file."""
        self.rate(3)

    # ------------------------------------------------------------------ mosaic
    def mosaic_for(self, path: str) -> dict | None:
        """The mosaic of *path* (loaded synchronously when it is not cached; ``None`` when it cannot be made)."""
        cached = self._mosaic_cache.get(path)
        if cached is not None:
            return cached
        if path in self._failed:
            return None
        loader = MosaicLoader(self._client)
        loader.load(path, self.setup_settings, self.current_folder)
        return self.store_mosaic(path, loader.result)

    def _mosaic(self) -> dict | None:
        """The cached mosaic of the current file; the draw loop never reads a photon file."""
        return self._mosaic_cache.get(self.current_file) if self.current_file else None

    def load_current(self) -> dict | None:
        """Make the mosaic of the current file now (headless use; the app does this on a worker)."""
        return self.mosaic_for(self.current_file) if self.current_file else None

    def store_mosaic(self, path: str, result: dict | None) -> dict | None:
        """Keep the mosaic a loader produced (``None``: remember that the file has none)."""
        if result is None:
            self._failed[path] = (
                "no image could be reconstructed (check the file type and the detector setup)"
            )
            self.notify("image")
            return None
        entry = {
            "mosaic": np.asarray(result["mosaic"], dtype=np.uint8),
            "labels": result.get("labels", []),
            "cols": int(result.get("cols", 1)),
            "rows": int(result.get("rows", 1)),
        }
        self._mosaic_cache[path] = entry
        self._failed.pop(path, None)
        self.notify("image")
        return entry

    def wanted_image(self) -> str | None:
        """The current file when its mosaic is neither cached nor known to be missing (the app loads it)."""
        path = self.current_file
        if path and path not in self._mosaic_cache and path not in self._failed:
            return path
        return None

    def image_error(self) -> str:
        """Why the current file shows no image (empty when it does, or while it loads)."""
        path = self.current_file
        return self._failed.get(path, "") if path else ""

    def tile_labels(self) -> list[dict]:
        """The per-tile channel / micro-time labels (none when the labels are switched off)."""
        return self.image_labels() if self.show_labels else []

    def tile_width(self) -> int:
        """Width in mosaic pixels of one tile (0 without an image)."""
        m = self._mosaic()
        return int(m["mosaic"].shape[1] // max(m["cols"], 1)) if m else 0

    def level_range(self) -> tuple[float, float]:
        """The display levels in use: the mosaic's own range while *Automatic levels* is on."""
        image = self.current_image()
        if image is None:
            return float(self.level_low), float(self.level_high)
        if self.auto_levels:
            return float(image.min()), float(image.max())
        return float(self.level_low), float(self.level_high)

    def histogram(self) -> np.ndarray | None:
        """Counts of the 8-bit mosaic per level (256 bins), or ``None`` without an image."""
        image = self.current_image()
        if image is None:
            return None
        return np.bincount(np.asarray(image).ravel(), minlength=256)[:256]

    def reset_view(self) -> None:
        """Ask the image to show the whole mosaic again."""
        self.reset_view_requested = True

    # ------------------------------------------------------------------ toolbar actions
    def choose_folder(self) -> None:
        """Open the folder chooser (the toolbar's *Open*)."""
        self.request_dialog("folder")

    def copy_files(self) -> None:
        """Ask for a destination folder; the selected raw files are copied there."""
        if self.paths():
            self.request_dialog("copy")
        else:
            self.status_line = "Select image files first."

    def export_tiff(self) -> None:
        """Ask for a destination folder; the intensity stacks of the selected files are written there."""
        if self.paths():
            self.request_dialog("tiff")
        else:
            self.status_line = "Select image files first."

    def export_docx(self) -> None:
        """Ask for a file name; a Word report of the listed files is written there."""
        if self.file_entries() and self.current_folder:
            self.request_dialog("docx")
        else:
            self.status_line = "Open a folder with image files first."

    def dialog_filename(self, kind: str) -> str:
        """The name a save dialog starts with (the Qt tool wrote ``<folder>.docx`` into the folder)."""
        if kind == "docx" and self.current_folder:
            folder = pathlib.Path(self.current_folder)
            return f"{folder.name or 'images'}.docx"
        return ""

    def show_help(self) -> None:
        """Ask the app to open the help window."""
        self.requests.append("help")

    def start_guide(self) -> None:
        """Ask the app to start the guided tour."""
        self.requests.append("guide")

    def next_step(self) -> None:
        """Hand the current image to the imaging pipeline (the app owns the coordinator)."""
        self.requests.append("next")

    # ------------------------------------------------------------------ worker methods
    def do_copy_files(self, folder: str) -> None:
        """Copy the selected raw files into *folder*, keeping their paths relative to the opened folder."""
        out = pathlib.Path(folder)
        out.mkdir(parents=True, exist_ok=True)
        done = 0
        base = pathlib.Path(self.current_folder).resolve() if self.current_folder else None
        for source in self.paths():
            source = pathlib.Path(source)
            try:
                relative = source.resolve().relative_to(base)
            except (TypeError, ValueError):
                relative = pathlib.Path(source.name)
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            done += 1
        self.status_line = f"Copied {done} raw file(s) to {out}."

    def do_export_tiff(self, folder: str) -> None:
        """Write one intensity TIFF stack per file and detector into *folder*."""
        paths = self.paths()
        if not paths:
            self.status_line = "Select image files first."
            return
        written = self._client.export_tiff(paths, str(folder), self.setup_settings)
        self.last_written = list(written)
        if written:
            self.status_line = f"Wrote {len(written)} TIFF stack(s) to {folder}."
        else:
            self.status_line = "No TIFF stack written: no file gave an image (check the detector setup)."

    def do_export_docx(self, path: str) -> None:
        """Write the DOCX report of the listed files (name, rating, annotation, mosaic) to *path*."""
        from matplotlib import colormaps
        from PIL import Image

        from ..core.image import get_magma_lut
        from .report import Document

        entries = self.file_entries()
        if not entries:
            self.status_line = "Open a folder with image files first."
            return
        document = Document()
        document.add_heading("TTTR Image Browser Export", level=1)
        skipped = 0
        cmap = colormaps[self.colormap] if self.colormap in colormaps else None
        for entry in entries:
            source = entry["id"]
            document.add_heading(pathlib.Path(source).name, level=2)
            document.add_paragraph(f"Rating: {self.rating_of(source)}")
            document.add_paragraph(f"Annotation: {self.note_of(source)}")
            mosaic = self.mosaic_for(source)
            if mosaic is None:
                skipped += 1
                continue
            array = mosaic["mosaic"]
            if self.colormap == "magma" or cmap is None:
                lut = get_magma_lut()
                rgb = np.asarray(lut[array], dtype=np.uint8) if lut is not None else array
            else:
                rgb = (cmap(array / 255.0)[..., :3] * 255).astype(np.uint8)
            buffer = io.BytesIO()
            Image.fromarray(rgb).save(buffer, format="PNG")
            buffer.seek(0)
            document.add_picture(buffer, width=6)
        document.save(str(path))
        self.last_written = [str(path)]
        note = f" ({skipped} without an image)" if skipped else ""
        self.status_line = f"Saved report: {path}{note}"

    # ------------------------------------------------------------------ settings
    def export_settings(self) -> dict[str, Any]:
        """The settings the host remembers: display, filters, the folder and its selection, the detector setup."""
        state = super().export_settings()
        state.update(
            current_folder=self.current_folder,
            selected_files=list(self.selected_files),
            setup_settings=self.setup_settings,
        )
        return state

    def restore_settings(self, state: dict[str, Any]) -> None:
        """Adopt remembered settings; a folder that is gone and values of the wrong type are ignored."""
        if not isinstance(state, dict):
            return
        super().restore_settings(state)
        if not 0.1 <= float(self.gamma) <= 5.0:
            self.gamma = 1.0
        setup = state.get("setup_settings")
        if isinstance(setup, dict):
            self.setup_settings = setup
        folder = state.get("current_folder")
        if isinstance(folder, str) and pathlib.Path(folder).is_dir():
            self.open_folder(folder)
            known = {rec.get("path") for rec in self._files}
            wanted = [p for p in state.get("selected_files", []) if isinstance(p, str) and p in known]
            if wanted:
                self.selected_files = wanted
                self.current_file = wanted[-1]
                self.notify("select")
