"""Step 1 of the burst workflow, *Data Selection*, drawn with emtk.

:class:`BurstDataSelectionModel` holds the raw TTTR files every later step reads, and registers each newly added
local file in MMFDB (object store + raw-data registry) through :func:`import_raw_file`. Nothing in it imports Qt.

:class:`BurstDataSelectionApp` draws a *source* -- the model, or the legacy Qt ``BurstDataSelectionWidget`` that
speaks the same few methods (``paths``, ``add_paths``, ``remove_index``, ``clear``, ``mmfdb_payload``,
``import_path``) -- as three windows: the file table (``data_table`` from ``data_selection.view.json``), the
selected file's details with its MMFDB status, and a summary. Files come from :class:`emtk.file_dialog.FileDialog`,
a drop on the window, or the shared MMFDB :class:`chisurf.emtk.dataset_picker.DatasetPicker`.
"""

from __future__ import annotations

import base64
import datetime
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.core.fio.staging import TTTR_EXTENSIONS
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import button_row

HERE = Path(__file__).resolve().parent

#: Kept for the Qt host, which paints its background before the first frame.
WINDOW_BG = (30, 32, 38, 255)

#: MMFDB kinds the database picker offers for raw data.
MMFDB_KINDS = ("raw_data", "raw_measurement", "external_reference")


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def expand_paths(paths) -> list[Path]:
    """Files as given, folders replaced by the TTTR files directly inside them (sorted); resolved."""
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            out.extend(
                sorted(
                    child.resolve()
                    for child in path.iterdir()
                    if child.is_file() and child.suffix.lower().lstrip(".") in _EXTENSIONS
                )
            )
        else:
            out.append(path.resolve())
    return out


_EXTENSIONS = {str(ext).lower().lstrip(".") for ext in TTTR_EXTENSIONS}


def import_raw_file(client: Any, path: Path) -> dict[str, Any]:
    """Put a local file into the MMFDB object store and register it as raw TTTR data.

    The RPC object store cannot read the client's file system, so the bytes go as base64 rather than a path. A
    failing registration is kept beside the stored object (``raw_data_error``); a failing upload is the whole
    entry's ``error``. Never raises.
    """
    try:
        encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        object_result = (
            client.call(
                "mmfdb.objects.put",
                {
                    "data": encoded,
                    "filename": Path(path).name,
                    "metadata": {"source": "burst_analysis.data_selection"},
                },
            )
            or {}
        )
        payload: dict[str, Any] = {"object_result": object_result}
        try:
            raw_result = (
                client.call(
                    "raw_data.register",
                    {
                        "raw_data": {
                            "file_path": str(path),
                            "data_type": "TTTR",
                            # One of MMFDB's storage_mode vocabulary terms; "file" is not one, and every
                            # registration was rejected.
                            "storage_mode": "local_file",
                            "header_metadata": {
                                "mmfdb_object": object_result.get("object", {}),
                                "source": "burst_analysis.data_selection",
                            },
                        }
                    },
                )
                or {}
            )
            payload["raw_data_result"] = raw_result
        except Exception as raw_exc:  # noqa: BLE001 - kept beside the stored object
            payload["raw_data_error"] = str(raw_exc)
        return payload
    except Exception as exc:  # noqa: BLE001 - the entry says why
        return {"error": str(exc)}


class BurstDataSelectionModel:
    """The raw TTTR files of a burst workflow, and their MMFDB registration (no Qt, no emtk).

    Parameters
    ----------
    client : object, optional
        An MMFDB client (``call(method, params)``). Default: the shared session client of the dataset picker,
        made on the first import.
    auto_import : bool
        Register each newly added file in MMFDB (the Qt step does this on every add).
    on_change : callable, optional
        Called after the file list changed.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        auto_import: bool = True,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._paths: list[Path] = []
        self._client = client
        self.auto_import = bool(auto_import)
        self.on_change = on_change
        self.imports: dict[str, dict[str, Any]] = {}
        self.selections: dict[str, dict[str, Any]] = {}
        self._imported: set[str] = set()
        self.selected_index: int | None = None
        self.status_text = "No TTTR files selected."

    # -- the source protocol ------------------------------------------------------------------------------- #
    def paths(self) -> list[Path]:
        """The selected raw TTTR files, in order."""
        return list(self._paths)

    def mmfdb_payload(self) -> dict[str, Any]:
        """MMFDB import and database-selection records, by file."""
        return {"imports": self.imports, "selections": self.selections}

    def client(self) -> Any:
        if self._client is None:
            from chisurf.emtk.dataset_picker import session_client

            self._client = session_client()
        return self._client

    def add_paths(self, paths) -> int:
        """Add files and folders (expanded, de-duplicated); register new local files. Returns how many were added."""
        added = 0
        for path in expand_paths(paths):
            if path in self._paths:
                continue
            self._paths.append(path)
            added += 1
            key = str(path)
            if self.auto_import and key not in self._imported:
                self._imported.add(key)
                self.import_path(path)
        if added and self.selected_index is None:
            self.selected_index = 0
        self._changed()
        return added

    def import_path(self, path: Path) -> dict[str, Any]:
        """Register *path* in MMFDB now (again, if it was before); the record is kept in :attr:`imports`."""
        try:
            client = self.client()
        except Exception as exc:  # noqa: BLE001 - no database: the record says so
            entry = {"error": f"MMFDB unavailable: {exc}"}
        else:
            entry = (
                {"error": "MMFDB unavailable."} if client is None else import_raw_file(client, path)
            )
        self.imports[str(path)] = entry
        self._changed(notify=False)
        return entry

    def remove_index(self, index: int) -> None:
        if 0 <= index < len(self._paths):
            del self._paths[index]
            if self.selected_index is not None and self.selected_index >= len(self._paths):
                self.selected_index = len(self._paths) - 1 if self._paths else None
            self._changed()

    def clear(self) -> None:
        self._paths.clear()
        self.selected_index = None
        self._changed()

    def add_database_selection(self, selection: Any, local_path: str) -> None:
        """A dataset chosen in the MMFDB picker: remembered, then added as a file (not registered again)."""
        path = Path(local_path).resolve()
        self.selections[str(path)] = {
            "artifact_id": getattr(selection, "artifact_id", ""),
            "artifact_kind": getattr(selection, "artifact_kind", ""),
            "label": getattr(selection, "label", ""),
        }
        self._imported.add(str(path))
        self.add_paths([path])

    # -- views --------------------------------------------------------------------------------------------- #
    def imported_count(self) -> int:
        return sum(1 for entry in self.imports.values() if "error" not in entry)

    def _changed(self, notify: bool = True) -> None:
        self.status_text = (
            f"{len(self._paths)} TTTR file(s) selected; {self.imported_count()} imported to MMFDB."
            if self._paths
            else "No TTTR files selected."
        )
        if notify and callable(self.on_change):
            self.on_change()

    # -- persistence --------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        return {"paths": [str(p) for p in self._paths]}

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        paths = [p for p in (state or {}).get("paths", []) if Path(p).exists()]
        if paths:
            auto, self.auto_import = self.auto_import, False  # restored files were registered when first added
            try:
                self.add_paths(paths)
            finally:
                self.auto_import = auto


def _status(entry: dict | None) -> str:
    if not entry:
        return "not imported"
    if "error" in entry:
        return "error"
    if "raw_data_error" in entry:
        return "stored (not registered)"
    return "in MMFDB"


class BurstDataSelectionApp(TourTarget, ImApp):
    """Files, details and summary of the workflow's raw data (emtk; no Qt).

    Parameters
    ----------
    source : BurstDataSelectionModel or object, optional
        What is drawn and edited (default: a new :class:`BurstDataSelectionModel`).
    on_proceed : callable, optional
        Called by *Proceed to Burst Selection* (the workflow hub moves to the next step).
    """

    DIALOGS = {
        "add_files": ("Add TTTR files", "open"),
        "add_folder": ("Add a folder of TTTR files", "folder"),
    }

    def __init__(
        self,
        source: Any = None,
        *,
        on_proceed: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.source = source if source is not None else BurstDataSelectionModel()
        self.model = self.source
        self.on_proceed = on_proceed
        self._on_guide = on_guide
        self._on_help = on_help
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.filter_text = ""
        self.selected_index: int | None = None
        self.form = FormState()
        self.spec = load_view_spec(str(HERE / "data_selection.view.json"))
        self.dialog = None
        self.dialog_action = ""
        self._dialog_window = None
        self.picker = None
        self.message = ""
        self.help_window = EmTkHelpWindow(
            title="Data Selection - Help",
            resource=HERE / "data_selection_help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(680.0, 500.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "data_selection_guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split("h", 0.62, Region("files"), Split("v", 0.55, Region("details"), Region("summary"))),
            name="burst_data_selection",
        )
        self.docks.add_window("files", "TTTR data files", self._draw_files, dock="files", closable=False)
        self.docks.add_window("details", "File details", self._draw_details, dock="details", closable=False)
        self.docks.add_window("summary", "Summary", self._draw_summary, dock="summary", closable=False)
        super().__init__(gui=self._render, continuous=False)

    # -- tour / help ---------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        if callable(self._on_guide):
            self._on_guide()
        else:
            self.tour.start()

    def show_help(self) -> None:
        if callable(self._on_help):
            self._on_help()
        else:
            self.help_window.show()

    def track(self, name: str) -> None:
        self.tour.notify_used(name)

    # -- what the file table binds to ----------------------------------------------------------------------- #
    def _paths(self) -> list[Path]:
        return list(self.source.paths())

    def file_rows(self) -> list[dict]:
        imports = self.source.mmfdb_payload().get("imports", {})
        query = self.filter_text.casefold()
        rows = []
        for index, path in enumerate(self._paths()):
            if query and query not in path.name.casefold():
                continue
            try:
                size = _format_size(path.stat().st_size)
            except OSError:
                size = "missing"
            rows.append(
                {
                    "index": index,
                    "number": index + 1,
                    "file": path.name,
                    "size": size,
                    "format": path.suffix.upper().lstrip("."),
                    "status": _status(imports.get(str(path))),
                    "path": str(path),
                }
            )
        return rows

    def select_file(self, record) -> None:
        if isinstance(record, dict) and "index" in record:
            self.selected_index = int(record["index"])
            self.track("files")

    def remove_file_row(self, record) -> None:
        if isinstance(record, dict) and "index" in record:
            self.source.remove_index(int(record["index"]))
            self._clamp_selection()

    def _clamp_selection(self) -> None:
        n = len(self._paths())
        if self.selected_index is not None and self.selected_index >= n:
            self.selected_index = n - 1 if n else None

    # -- actions -------------------------------------------------------------------------------------------- #
    def browse(self, action: str) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode = self.DIALOGS[action]
        options: dict[str, Any] = {}
        paths = self._paths()
        if paths:
            options["directory"] = str(paths[-1].parent)
        if mode == "open":
            patterns = sorted("*." + ext for ext in _EXTENSIONS)
            options["filters"] = [("TTTR files", patterns), ("All files", ["*"])]
        self.dialog = FileDialog(title, mode=mode, multiselect=mode == "open", **options)
        self.dialog_action = action
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-data-file")
        self._dialog_window.show()

    def _dialog_done(self, result: list[str]) -> None:
        try:
            added = self.source.add_paths([Path(p) for p in result])
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.message = f"Could not add: {exc}"
            return
        self.message = "" if added is None or added else "Nothing new to add (already in the list, or no TTTR files)."
        if self.selected_index is None and self._paths():
            self.selected_index = 0

    def open_database(self) -> None:
        from chisurf.emtk.dataset_picker import DatasetPicker

        def chosen(selection):
            local_path = getattr(selection, "local_path", None)
            if not local_path:
                return
            adder = getattr(self.source, "add_database_selection", None)
            if callable(adder):
                adder(selection, local_path)
            else:
                self.source.add_paths([Path(local_path)])
            if self.selected_index is None and self._paths():
                self.selected_index = 0

        try:
            # ``on_paths`` makes the picker resolve the dataset to a local file before ``on_selected`` runs.
            self.picker = DatasetPicker(
                kinds=MMFDB_KINDS, scope="all", on_paths=lambda _paths: None, on_selected=chosen
            )
            self.picker.open()
        except Exception as exc:  # noqa: BLE001 - no database
            self.picker = None
            self.message = f"MMFDB is not available: {exc}"

    def files_dropped(self, paths) -> bool:
        paths = list(paths)
        if not paths:
            return False
        self.source.add_paths([Path(p) for p in paths])
        if self.selected_index is None and self._paths():
            self.selected_index = 0
        return True

    on_paths_dropped = files_dropped
    on_files_dropped = files_dropped

    # -- windows -------------------------------------------------------------------------------------------- #
    def _draw_files(self, box=None) -> None:
        paths = self._paths()
        self._clamp_selection()
        selected = self.selected_index is not None and 0 <= self.selected_index < len(paths)
        pressed = button_row(
            [
                {"label": "Add files", "key": "add_files", "keys": ["toolAction_add"],
                 "tip": "Choose TTTR measurement files to add to the workflow."},
                {"label": "Add folder", "key": "add_folder",
                 "tip": "Add every TTTR file directly inside a folder."},
                {"label": "Database (MMFDB)", "key": "database",
                 "tip": "Choose raw data registered in MMFDB; the file is resolved to a local path."},
                {"label": "Remove", "key": "remove", "enabled": selected,
                 "tip": "Remove the selected file from the list." if selected
                 else "Select a file in the table first."},
                {"label": "Clear", "key": "clear", "enabled": bool(paths),
                 "tip": "Remove every file from the list." if paths else "No files to remove."},
                {"label": "Guide", "key": "guide", "tip": "A step-by-step walk through this step."},
                {"label": "Help", "key": "help", "tip": "What this step does and what it hands on."},
            ],
            remember=self.remember,
        )
        if pressed in self.DIALOGS:
            self.track(pressed)
            self.browse(pressed)
        elif pressed == "database":
            self.track("database")
            self.open_database()
        elif pressed == "remove" and selected:
            self.source.remove_index(int(self.selected_index))
            self._clamp_selection()
        elif pressed == "clear":
            self.source.clear()
            self.selected_index = None
        elif pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()
        im.align_text_to_frame_padding()
        im.text("Filter")
        im.same_line()
        im.set_next_item_width(min(260.0, max(120.0, im.get_content_region_avail()[0] - 10.0)))
        _changed, self.filter_text = im.input_text("##data_filter", self.filter_text, hint="file name contains")
        im.set_item_tooltip("Show only files whose name contains this text.")
        self.remember("filter")
        if self.message:
            im.text_wrapped(self.message)
        draw_sections(self.spec["sections"], self, self.form)
        if "data_table" in self.form.rects:
            self.item_rects["files"] = tuple(self.form.rects["data_table"])
        if not paths:
            im.text_disabled("No files yet: add TTTR files or a folder, or drop them on this window.")

    def _draw_details(self, box=None) -> None:
        paths = self._paths()
        if self.selected_index is None or not 0 <= self.selected_index < len(paths):
            im.text_wrapped("No file selected. Click a file in the table to see its details.")
            return
        path = paths[self.selected_index]
        im.text(f"Name: {path.name}")
        im.text_wrapped(f"Path: {path}")
        try:
            stat = path.stat()
            im.text(f"Size: {_format_size(stat.st_size)} ({stat.st_size:,} bytes)")
            modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            im.text(f"Modified: {modified}")
        except OSError as exc:
            im.text_wrapped(f"The file cannot be read: {exc}")
        im.separator()
        entry = self.source.mmfdb_payload().get("imports", {}).get(str(path))
        im.text(f"MMFDB: {_status(entry)}")
        if entry and "error" in entry:
            im.text_wrapped(str(entry["error"]))
        elif entry:
            obj = (entry.get("object_result") or {}).get("object", {}) or {}
            raw = (entry.get("raw_data_result") or {}).get("raw_data", {}) or {}
            im.text(f"Object: {obj.get('object_uuid', '-')}")
            im.text(f"Raw data: {raw.get('raw_data_id', '-')}")
            if entry.get("raw_data_error"):
                im.text_wrapped(f"Registration failed: {entry['raw_data_error']}")
        label = "Import again" if entry else "Import now"
        if im.button(label + "##data_import"):
            self.track("import")
            self.source.import_path(path)
        im.set_item_tooltip("Store this file in the MMFDB object store and register it as raw TTTR data.")
        self.remember("import")

    def _draw_summary(self, box=None) -> None:
        paths = self._paths()
        total = 0
        for path in paths:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        imports = self.source.mmfdb_payload().get("imports", {})
        registered = sum(1 for p in paths if "error" not in (imports.get(str(p)) or {"error": 1}))
        im.bullet_text(f"Files: {len(paths)}")
        im.bullet_text(f"On disk: {_format_size(total)}")
        im.bullet_text(f"In MMFDB: {registered} of {len(paths)}")
        im.separator()
        im.begin_disabled(not paths or not callable(self.on_proceed))
        if im.button("Proceed to Burst Selection"):
            self.track("proceed")
            self.on_proceed()
        im.end_disabled()
        im.set_item_tooltip(
            "Go on to 2. Burst Selection with these files." if paths else "Add TTTR files first."
        )
        self.remember("proceed")

    # -- frame ---------------------------------------------------------------------------------------------- #
    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, float(w), float(h))
        self.docks.draw(frame)
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                self._dialog_done(result)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        if self.picker is not None:
            self.picker.render(frame)
            if not getattr(self.picker, "is_open", True):
                self.picker = None
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            self.tour.draw(float(w), float(h))

    # -- persistence ---------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        export = getattr(self.source, "export_settings", None)
        state = dict(export()) if callable(export) else {}
        state["filter"] = self.filter_text
        return state

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self.filter_text = str(state.get("filter", ""))
        restore = getattr(self.source, "restore_settings", None)
        if callable(restore):
            restore(state)

    def close(self) -> None:
        if self.picker is not None:
            try:
                self.picker.close()
            except Exception:  # noqa: BLE001
                pass


def make_app(**kwargs) -> BurstDataSelectionApp:
    """The data-selection step alone."""
    from chisurf.emtk.i18n import install

    install()
    return BurstDataSelectionApp(**kwargs)


__all__ = [
    "BurstDataSelectionApp",
    "BurstDataSelectionModel",
    "WINDOW_BG",
    "expand_paths",
    "import_raw_file",
    "make_app",
]
