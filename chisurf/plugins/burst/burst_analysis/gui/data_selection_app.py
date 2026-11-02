"""Step 1 of the burst workflow, *Data Selection*, drawn with emtk.

:class:`BurstDataSelectionModel` holds the raw TTTR files every later step reads, and registers each newly added
local file in MMFDB (object store + raw-data registry) through :func:`import_raw_file`. Nothing in it imports Qt.

:class:`BurstDataSelectionApp` draws a *source* -- the model, or any object that
speaks the same few methods (``paths``, ``add_paths``, ``remove_index``, ``clear``, ``mmfdb_payload``,
``import_path``) -- as three windows: the file table (``data_table`` from ``data_selection.view.json``), the
selected file's details with its MMFDB status, and a summary. Files come from the Datasets workspace: the
Input section lists its photon streams (the hosting plugin's manifest ``accepts`` ``photons``).
"""

from __future__ import annotations

import base64
import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.core.fio.staging import TTTR_EXTENSIONS
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import action_caption, action_tooltip, button_row

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

log = logging.getLogger(__name__)

#: Why a file was not registered: MMFDB stores objects only for a signed-in user, so without a session every
#: upload is refused ("Authentication required"); the file is used from disk all the same.
NOT_SIGNED_IN = (
    "Not signed in to MMFDB: the file is used from disk and not registered. "
    "Sign in (MMFDB Admin) to register it."
)


def signed_in(client: Any) -> bool:
    """Whether *client* can write to MMFDB: an MMFDB client carries a session ``token``; one that has none is
    anonymous, and MMFDB refuses an anonymous upload. A client without a ``token`` attribute authenticates
    itself (a test double, a pre-authorised transport)."""
    return client is not None and (not hasattr(client, "token") or bool(getattr(client, "token")))


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
        self._told_not_signed_in = False
        #: Which workspace dataset each file came from (its burst runs go into that dataset's
        #: analysis container in the project).
        self.sources: dict[str, str] = {}

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
            if client is None:
                entry = {"error": "MMFDB unavailable."}
            elif not signed_in(client):
                # Not a fault: no request is sent, and the notice is given once, not once per file.
                entry = {"skipped": NOT_SIGNED_IN}
                if not self._told_not_signed_in:
                    self._told_not_signed_in = True
                    log.info("Burst data selection: %s", NOT_SIGNED_IN)
            else:
                entry = import_raw_file(client, path)
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
        return sum(1 for entry in self.imports.values() if _registered(entry))

    def _changed(self, notify: bool = True) -> None:
        if not self._paths:
            self.status_text = "No TTTR files selected."
        elif any("skipped" in (self.imports.get(str(p)) or {}) for p in self._paths):
            self.status_text = f"{len(self._paths)} TTTR file(s) selected; not signed in to MMFDB, so they are not registered."
        else:
            self.status_text = f"{len(self._paths)} TTTR file(s) selected; {self.imported_count()} imported to MMFDB."
        if notify and callable(self.on_change):
            self.on_change()

    # -- persistence --------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        return {"paths": [str(p) for p in self._paths]}

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        paths = [p for p in (state or {}).get("paths", []) if Path(p).exists()]
        if paths:
            auto, self.auto_import = (
                self.auto_import,
                False,
            )  # restored files were registered when first added
            try:
                self.add_paths(paths)
            finally:
                self.auto_import = auto


def _registered(entry: dict | None) -> bool:
    """Whether *entry* (an :attr:`BurstDataSelectionModel.imports` record) put the file in MMFDB."""
    return entry is not None and bool(entry) and "error" not in entry and "skipped" not in entry


def _status(entry: dict | None) -> str:
    if not entry:
        return "not imported"
    if "skipped" in entry:
        return "not signed in"
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

    #: The plugin whose manifest ``accepts`` ``photons`` the Input section feeds.
    WORKSPACE_PLUGIN = "burst_analysis"
    #: The Summary dock's proceed button and its tooltip (a workflow whose next step is another one renames it).
    PROCEED_LABEL = "Proceed to Burst Selection"
    PROCEED_TIP = "Go on to 2. Burst Selection with these files."

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
        self.message = ""
        # The Input section: the workspace's photon streams.
        from chisurf.core.plugin.workspace_input import input_section, spec_for
        from chisurf.emtk.plugins import manifest
        from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput

        self.input = NamedWorkspaceInput(self.WORKSPACE_PLUGIN, "photons", app=self)
        found = spec_for(manifest(self.WORKSPACE_PLUGIN), kind="photons")
        self.input_spec = {"sections": [input_section(found[1])]} if found else {"sections": []}
        self.input_form = FormState()
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
            Split(
                "h", 0.62, Region("files"), Split("v", 0.55, Region("details"), Region("summary"))
            ),
            name="burst_data_selection",
        )
        self.docks.add_window(
            "files", "TTTR data files", self._draw_files, dock="files", closable=False
        )
        self.docks.add_window(
            "details", "File details", self._draw_details, dock="details", closable=False
        )
        self.docks.add_window(
            "summary", "Summary", self._draw_summary, dock="summary", closable=False
        )
        super().__init__(gui=self._render, continuous=False)

    #: The workflow's Simple / Advanced mode (standalone: everything).
    advanced = True

    def set_advanced(self, advanced: bool) -> None:
        """Simple: the files and how to add them. The file details (path, MMFDB import) and the
        summary are Advanced -- unless a workflow puts controls of its own in the summary."""
        self.advanced = bool(advanced)
        keep_summary = type(self)._draw_summary_extra is not BurstDataSelectionApp._draw_summary_extra
        for key in ("details",) + (() if keep_summary else ("summary",)):
            if key in self.docks.windows:
                if advanced:
                    self.docks.show(key)
                else:
                    self.docks.hide(key)
        self.docks.focus("files")

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
    def take_photons(self, paths, uids=()) -> int:
        """Add photon streams from the workspace; remember the dataset each came from."""
        paths = [Path(str(p)) for p in paths]
        added = self.source.add_paths(paths)
        sources = getattr(self.source, "sources", None)
        if isinstance(sources, dict):
            for path, uid in zip(paths, uids):
                if uid:
                    sources[str(path)] = str(uid)
        if self.selected_index is None and self._paths():
            self.selected_index = 0
        self.message = "" if added is None or added else "Nothing new to add (already in the list)."
        return int(added or 0)

    # -- windows -------------------------------------------------------------------------------------------- #
    def _draw_files(self, box=None) -> None:
        paths = self._paths()
        self._clamp_selection()
        selected = self.selected_index is not None and 0 <= self.selected_index < len(paths)
        self.input.workspace_input_on_used = self.track
        self.input_form.rects.clear()
        draw_form(self.input_spec, self.input, self.input_form)
        for name, rect in self.input_form.rects.items():
            self.item_rects[name] = tuple(rect)
        if "workspace_input_rows" in self.input_form.rects:  # the guide's name for adding data
            self.item_rects["add_files"] = tuple(self.input_form.rects["workspace_input_rows"])
            self.item_rects["toolAction_add"] = self.item_rects["add_files"]
        pressed = button_row(
            [
                {
                    "label": "Remove",
                    "key": "remove",
                    "enabled": selected,
                    "tip": "Remove the selected file from the list."
                    if selected
                    else "Select a file in the table first.",
                },
                *(
                    []
                    if not self.advanced  # Simple: Remove does it, one file at a time
                    else [
                        {
                            "label": "Clear",
                            "key": "clear",
                            "enabled": bool(paths),
                            "tip": "Remove every file from the list." if paths else "No files to remove.",
                        }
                    ]
                ),
                # in a workflow's Simple mode the hub's own Help and Guide are the ones
                *(
                    []
                    if not self.advanced
                    else [
                        {"label": action_caption("guide"), "key": "guide", "tip": action_tooltip("guide")},
                        {"label": action_caption("help"), "key": "help", "tip": action_tooltip("help")},
                    ]
                ),
            ],
            remember=self.remember,
        )
        if pressed == "remove" and selected and self.selected_index is not None:
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
        im.text(tr("Filter"))
        im.same_line()
        im.set_next_item_width(min(260.0, max(120.0, im.get_content_region_avail()[0] - 10.0)))
        _changed, self.filter_text = im.filter_field(
            "##data_filter",
            self.filter_text,
            tr("file name contains"),
            tooltip=tr("Show only files whose name contains this text."),
        )
        self.remember("filter")
        if self.message:
            im.text_wrapped(self.message)
        draw_sections(self.spec["sections"], self, self.form)
        if "data_table" in self.form.rects:
            self.item_rects["files"] = tuple(self.form.rects["data_table"])
        if not paths:
            im.text_disabled(tr("No files yet: pick photon streams in the Input section above."))

    def _draw_details(self, box=None) -> None:
        paths = self._paths()
        if self.selected_index is None or not 0 <= self.selected_index < len(paths):
            im.text_wrapped(tr("No file selected. Click a file in the table to see its details."))
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
        if entry and ("error" in entry or "skipped" in entry):
            im.text_wrapped(str(entry.get("error") or entry["skipped"]))
        elif entry:
            obj = (entry.get("object_result") or {}).get("object", {}) or {}
            raw = (entry.get("raw_data_result") or {}).get("raw_data", {}) or {}
            im.text(f"Object: {obj.get('object_uuid', '-')}")
            im.text(f"Raw data: {raw.get('raw_data_id', '-')}")
            if entry.get("raw_data_error"):
                im.text_wrapped(f"Registration failed: {entry['raw_data_error']}")
        label = "Import again" if _registered(entry) else "Import now"
        if im.button(label + "##data_import"):
            self.track("import")
            self.source.import_path(path)
        im.set_item_tooltip(
            tr("Store this file in the MMFDB object store and register it as raw TTTR data.")
        )
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
        registered = sum(1 for p in paths if _registered(imports.get(str(p))))
        im.bullet_text(f"Files: {len(paths)}")
        im.bullet_text(f"On disk: {_format_size(total)}")
        im.bullet_text(f"In MMFDB: {registered} of {len(paths)}")
        im.separator()
        im.begin_disabled(not paths or not callable(self.on_proceed))
        if im.button(self.PROCEED_LABEL) and self.on_proceed is not None:
            self.track("proceed")
            self.on_proceed()
        im.end_disabled()
        im.set_item_tooltip(self.PROCEED_TIP if paths else "Add TTTR files first.")
        self.remember("proceed")
        self._draw_summary_extra()

    def _draw_summary_extra(self) -> None:
        """Below the proceed button: nothing here; a workflow adds its own controls (the ALEX Suite's demo data)."""

    # -- frame ---------------------------------------------------------------------------------------------- #
    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, float(w), float(h))
        self.docks.draw(frame)
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
