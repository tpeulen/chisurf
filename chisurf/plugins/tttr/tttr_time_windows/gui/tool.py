"""PyQt-hosted EMTK GUI for TTTR Time Window BIDs, backed by the new API.

The UI is the EMTK app in :mod:`.app`; this window is its Qt host. OS file
drops land here (the base's window-level drop) and are routed onto the file
queue the app renders.
"""

from __future__ import annotations

from pathlib import Path

from chisurf import logging
from chisurf.core.support import i18n
from chisurf.gui.misc_helpers import persist_plugin_state
from chisurf.gui.widgets.tools import ChisurfDockTool

from ..api.models import TimeWindowResult
from .client import TimeWindowClient


def _supported_exts() -> set[str]:
    """Return the set of supported TTTR file extensions."""
    norm: set[str] = set()
    try:
        import tttrlib

        exts = getattr(tttrlib, "get_supported_filetypes", lambda: [])()
        for e in exts:
            s = str(e).strip().lower()
            if not s:
                continue
            if not s.startswith("."):
                s = "." + s
            norm.add(s)
    except Exception:
        pass
    if not norm:
        norm = {".ptu", ".phu", ".ht2", ".ht3", ".pt3", ".t3r"}
    return norm


def _is_supported_path(path: str) -> bool:
    """Return whether a path has a supported TTTR extension (optionally .gz/.bz2)."""
    lower = path.lower()
    return any(
        lower.endswith(ext) or lower.endswith(ext + ".gz") or lower.endswith(ext + ".bz2")
        for ext in _supported_exts()
    )


@persist_plugin_state("tttr_time_windows")
class TTTRTimeWindowTool(ChisurfDockTool):
    """Single-window TTTR→BID tool: EMTK canvas over split docks.

    Consolidates setup, file selection, preview, and processing into one
    window. Files arrive through the ➕ button, the OS drop on this window,
    or MMFDB; processing writes one ``.bst`` BID file per input.
    """

    tool_settings_name = "TTTRTimeWindowTool"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(i18n.tr("TTTR Time-Window BIDs"))
        try:
            self.resize(1000, 700)
        except Exception:
            pass

        self._client = TimeWindowClient()
        self._file_paths: list[Path] = []
        self._last_result: TimeWindowResult | None = None
        self._log_lines: list[str] = []
        self.time_window_ms: float = 10.0
        self.output_dir_text: str = ""
        #: The preview currently shown, as the app's plot data.
        self.preview_data: dict | None = None

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, TimeWindowApp

        self.app = TimeWindowApp(
            self,
            on_process=self._process_all,
            on_clear=self._clear_all,
            on_browse=self._choose_dir,
            on_add_files=self._add_files_dialog,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

    # ── files ───────────────────────────────────────────────────────

    def add_paths(self, paths) -> None:
        """Queue files, keeping only supported TTTR extensions, in order."""
        known = {str(p) for p in self._file_paths}
        for path in paths:
            p = Path(path)
            if not _is_supported_path(str(p)) or str(p) in known:
                continue
            self._file_paths.append(p)
            known.add(str(p))
        if self._file_paths and self.app.time_window_gui.preview_index < 0:
            self.app.time_window_gui.select_preview(0)
        self.host.update()

    def on_paths_dropped(self, paths) -> None:
        """OS drops on this window queue the TTTR files among them."""
        self.add_paths([p for p in paths if _is_supported_path(str(p))])

    def _add_files_dialog(self) -> None:
        from chisurf.gui.widgets.general import open_file

        paths, _ = open_file(
            caption=i18n.tr("Select TTTR files"),
            file_type="TTTR files (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r);;All files (*)",
            multiple=True,
        )
        if paths:
            self.add_paths(paths if isinstance(paths, list) else [paths])

    def _add_folder_dialog(self) -> None:
        from chisurf.gui.widgets.general import get_directory

        folder, _ = get_directory(caption=i18n.tr("Add TTTR folder"))
        if folder:
            self.add_paths(sorted(p for p in Path(folder).rglob("*") if p.is_file()))

    def _add_from_database(self) -> None:
        from chisurf.gui import dialogs
        from chisurf.gui.widgets.mmfdb import picker

        client = picker.inprocess_client()
        if client is None:
            dialogs.information(self, "MMFDB", "No MMFDB database is available in this session.")
            return
        paths = picker.pick_local_paths(parent=self, kinds=None, scope="all", client=client)
        if paths:
            self.add_paths(paths)

    def _remove_preview_file(self) -> None:
        gui = self.app.time_window_gui
        index = gui.preview_index
        if not 0 <= index < len(self._file_paths):
            return
        del self._file_paths[index]
        self.preview_data = None
        gui.preview = None
        gui.preview_index = -1
        if self._file_paths:
            gui.select_preview(min(index, len(self._file_paths) - 1))
        self.host.update()

    def load_preview_for_index(self, index: int) -> None:
        """Load the intensity-trace preview for queued file *index*."""
        if not (0 <= index < len(self._file_paths)):
            return
        path = self._file_paths[index]
        try:
            diag = self._load_preview(str(path), self.time_window_ms)
            if not diag or "counts" not in diag:
                self.preview_data = None
                self.app.time_window_gui.preview = None
                self.statusBar().showMessage(i18n.tr("Preview unavailable"), 4000)
            else:
                diag.setdefault("time_window_ms", self.time_window_ms)
                self.preview_data = diag
                self.app.time_window_gui.preview = diag
                self.statusBar().showMessage(f"Preview: {path.name}", 4000)
        except Exception as exc:
            self.preview_data = None
            self.app.time_window_gui.preview = None
            self._log(f"Preview failed for {path.name}: {exc}")
        self.host.update()

    def _load_preview(self, path: str, tw_ms: float) -> dict:
        """Decode one file's intensity trace (its own method: mockable)."""
        return self._client.load_preview(Path(path), tw_ms)

    # ── processing ──────────────────────────────────────────────────

    def _process_all(self) -> None:
        """Compute time-window BIDs for all queued files."""
        if not self._file_paths:
            self._log("No TTTR files to process. Add files first.")
            self.statusBar().showMessage(i18n.tr("No files to process"), 4000)
            return

        tw_ms = float(self.time_window_ms)
        out_dir_txt = self.output_dir_text.strip()
        output_dir: Path | None = Path(out_dir_txt) if out_dir_txt else None

        self.statusBar().showMessage(i18n.tr("Processing files…"))
        self._log(f"Processing {len(self._file_paths)} file(s) with time window = {tw_ms:.3f} ms…")

        try:
            result = self._client.analyze_files(
                self._file_paths,
                time_window_ms=tw_ms,
                output_dir=output_dir,
            )
            self._last_result = TimeWindowResult(**result)

            metadata = result.get("metadata", {})
            out_dir = metadata.get("output_dir", "?")
            total_windows = metadata.get("total_windows", 0)

            if out_dir and out_dir != "?":
                self.output_dir_text = str(out_dir)

            self._log(
                f"Done: {len(self._file_paths)} file(s), "
                f"{total_windows} total windows. "
                f"Output: {out_dir}"
            )

            n_windows = result.get("n_windows", {})
            for fp, cnt in n_windows.items():
                self._log(f"  {Path(fp).name}: {cnt} windows")

            self.statusBar().showMessage(
                f"Processed {len(self._file_paths)} file(s), {total_windows} windows",
                8000,
            )
        except Exception as exc:
            self._log(f"Processing failed: {exc}")
            self.statusBar().showMessage(i18n.tr("Processing failed"), 8000)
        self.host.update()

    def _clear_all(self) -> None:
        """Clear the file list and results."""
        self._file_paths = []
        self._last_result = None
        self._log_lines = []
        self.preview_data = None
        self.app.time_window_gui.preview = None
        self.app.time_window_gui.preview_index = -1
        self.statusBar().showMessage(i18n.tr("Cleared"), 4000)
        self.host.update()

    def _choose_dir(self) -> None:
        """Open a directory chooser dialog."""
        from chisurf.gui.widgets.general import get_directory

        d, _ = get_directory(caption=i18n.tr("Select output folder"))
        if d is not None:
            self.output_dir_text = str(d)
            self.host.update()

    # ── logging ─────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        """Append a message to the on-canvas log and the application log."""
        try:
            logging.info(msg)
        except Exception:
            pass
        self._log_lines.append(str(msg))
        self.host.update()
