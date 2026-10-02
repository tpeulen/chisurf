"""Native dataset picker with MMFDB filters and local object-store resolution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_KINDS = ("raw_data", "raw_measurement", "external_reference")
_SESSION_CLIENT: Any = None
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mmfdb-picker")


@dataclass
class DatasetSelection:
    artifact_id: str
    artifact_kind: str
    data_format: str | None
    label: str
    local_path: str | None = None
    metadata: dict = field(default_factory=dict)
    member_count: int = 0


def session_client() -> Any:
    """Reuse a configured client and existing credentials; never prompt for login."""
    global _SESSION_CLIENT
    if _SESSION_CLIENT is not None:
        return _SESSION_CLIENT
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient, client_config
    from chisurf.plugins.core.mmfdb_admin.gui.session import cached_token
    from chisurf.core.settings import cs_settings

    config = client_config(cs_settings.get("mmfdb", {}))
    client = MMFDBClient(inprocess=config["mode"] == "embedded")
    token = cached_token(client.host, client.cmd_port, client.pub_port)
    if not token:
        try:
            from mmfdb.security.credentials import load_runtime_session_token
            token = load_runtime_session_token(client.host, client.cmd_port, config["username"])
        except Exception:
            token = None
    if token and not getattr(client, "token", None):
        client.token = token
    _SESSION_CLIENT = client
    return client


def reset_session_client() -> None:
    global _SESSION_CLIENT
    _SESSION_CLIENT = None


def resolve_local_path(client: Any, selection: DatasetSelection) -> str | None:
    """Let MMFDB materialize a local or remote object; preserve service failures."""
    if selection.local_path:
        return selection.local_path
    result = client.call("mmfdb.datasets.open", {"artifact_id": selection.artifact_id}) or {}
    return result.get("local_path") or result.get("path")


def _display_name(dataset: dict) -> str:
    name = dataset.get("original_filename")
    if name:
        return str(name)
    metadata = dataset.get("metadata_json") or dataset.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = {}
    for candidate in (dataset.get("file_path"), dataset.get("folder_path"),
                      metadata.get("path") if isinstance(metadata, dict) else None):
        if candidate:
            return Path(str(candidate).rstrip("/\\")).name
    return str(dataset.get("artifact_id", "Dataset"))


class DatasetPicker:
    """Frame-rendered picker; selection and resolved-path callbacks are optional."""

    def __init__(self, *, client: Any = None, kinds: Sequence[str] | None = None,
                 formats: Sequence[str] | None = None, scope: str = "all",
                 on_selected: Callable[[DatasetSelection], None] | None = None,
                 on_paths: Callable[[list[Path]], None] | None = None) -> None:
        self.client = client
        self.kinds = list(DEFAULT_KINDS if kinds is None else kinds)
        self.formats = list(formats) if formats is not None else None
        self.scope = "own" if scope == "mine" else scope
        if self.scope not in {"own", "public", "all"}:
            raise ValueError("scope must be mine, own, public, or all")
        self.on_selected = on_selected
        self.on_paths = on_paths
        self.query = ""
        self.page = 0
        self.page_size = 50
        self.total = 0
        self.datasets: list[dict] = []
        self.selection: DatasetSelection | None = None
        self.error = ""
        self.is_open = False
        self._dialog = None
        self._pending = None
        self._pending_kind = ""
        self._pending_frame_hooked = False

    def open(self) -> None:
        self.is_open = True
        self._request_refresh()

    def _request_refresh(self) -> None:
        if self._pending is None:
            self._pending_kind = "browse"
            self._pending = _EXECUTOR.submit(self.refresh)
            self._pending_frame_hooked = False
            self._request_completion_frame()

    def _request_completion_frame(self) -> None:
        from emtk import im

        try:
            ctx = im.get_current_context()
        except RuntimeError:
            return
        if ctx is not None and not self._pending_frame_hooked:
            self._pending_frame_hooked = True
            self._pending.add_done_callback(lambda future: ctx.request_frame())

    def _poll(self) -> None:
        if self._pending is None or not self._pending.done():
            return
        future, kind = self._pending, self._pending_kind
        self._pending = None
        try:
            result = future.result()
            if kind == "cancelled":
                if self.is_open:
                    self._request_refresh()
            elif kind == "open":
                if not result:
                    raise ValueError("MMFDB did not return a local path for this dataset.")
                self.selection.local_path = str(result)
                self.accept()
        except Exception as exc:
            self.error = str(exc)

    def close(self) -> None:
        """Close without delivering an in-flight selection callback."""
        self.is_open = False
        if self._pending is not None:
            self._pending_kind = "cancelled"

    def refresh(self) -> bool:
        self.error = ""
        self.selection = None
        try:
            if self.client is None:
                self.client = session_client()
            result = self.client.call("mmfdb.datasets.browse", {
                "scope": self.scope, "query": self.query.strip() or None,
                "kinds": self.kinds, "formats": self.formats,
                "limit": self.page_size, "offset": self.page * self.page_size,
            }) or {}
            self.datasets = result.get("datasets", [])
            self.total = int(result.get("total", len(self.datasets)))
            return True
        except Exception as exc:
            self.datasets = []
            self.total = 0
            self.error = str(exc)
            return False

    def select(self, artifact_id: str) -> DatasetSelection | None:
        dataset = next((x for x in self.datasets if x.get("artifact_id") == artifact_id), None)
        if dataset is None:
            self.selection = None
            return None
        self.selection = DatasetSelection(
            artifact_id=artifact_id, artifact_kind=dataset.get("artifact_kind", ""),
            data_format=dataset.get("data_format"), label=_display_name(dataset),
            metadata=dataset, member_count=int(dataset.get("member_count", 0) or 0),
        )
        return self.selection

    def accept(self) -> bool:
        if self.selection is None:
            return False
        try:
            if self.on_paths is not None:
                local = resolve_local_path(self.client, self.selection)
                if not local:
                    raise ValueError("MMFDB did not return a local path for this dataset.")
                self.selection.local_path = str(local)
                self.on_paths([Path(local)])
            if self.on_selected is not None:
                self.on_selected(self.selection)
            self.is_open = False
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

    def render(self, frame: Any) -> None:
        if not self.is_open:
            return
        from emtk import im
        from emtk.dialog_window import DialogWindow

        self._poll()
        if self._dialog is None:
            self._dialog = DialogWindow("Select MMFDB dataset", size=(760, 540), key=f"dataset_{id(self)}")
        pressed = self._dialog.begin(frame)
        if self._pending is not None:
            self._request_completion_frame()
            im.text_wrapped("Loading datasets…" if self._pending_kind == "browse" else "Opening dataset…")
            if im.button("Cancel##dataset_pending") or pressed == "close":
                self.close()
            im.set_item_tooltip("Close the picker; the database operation can finish in the background.")
            self._dialog.end()
            return
        for label, scope in (("Mine", "own"), ("Public", "public"), ("All", "all")):
            if im.button(f"{label}##dataset_scope_{id(self)}"):
                self.scope, self.page = scope, 0
                self._request_refresh()
            im.set_item_tooltip(f"Browse {label.lower()} datasets; current scope is {self.scope}.")
            im.same_line()
        im.new_line()
        changed, self.query = im.input_text("Search##dataset", self.query)
        im.set_item_tooltip("Search dataset names and metadata; press Refresh to apply.")
        if changed:
            self.page = 0
        if im.button("Refresh##dataset"):
            self._request_refresh()
        im.set_item_tooltip("Reload datasets with the current scope, search, kind and format filters.")
        im.text_wrapped("Kinds: " + ", ".join(self.kinds) + " | Formats: " + ", ".join(self.formats or ["all"]))
        if self.error:
            im.text_wrapped("Database error: " + self.error)
        ctx = im.get_current_context()
        width, height = ctx.layout.avail()
        im.begin_child((*im.get_cursor_screen_pos(), max(100, width), max(80, height - 100)), clip=True)
        for dataset in self.datasets:
            artifact_id = str(dataset.get("artifact_id", ""))
            label = f"{_display_name(dataset)} [{dataset.get('artifact_kind', '')}] ({dataset.get('data_format') or 'unknown format'})"
            if im.selectable(f"{label}##dataset_{artifact_id}", selected=bool(self.selection and self.selection.artifact_id == artifact_id)):
                self.select(artifact_id)
            im.set_item_tooltip(f"Select dataset {artifact_id}; sample: {dataset.get('sample_name') or dataset.get('sample_id') or 'unspecified'}.")
        if not self.datasets and not self.error:
            im.text_wrapped("No datasets match these filters.")
        im.end_child()
        im.begin_disabled(self.page == 0)
        if im.button("Previous##dataset"):
            self.page -= 1
            self._request_refresh()
        im.set_item_tooltip("Show the previous page of datasets.")
        im.end_disabled()
        im.same_line()
        im.begin_disabled((self.page + 1) * self.page_size >= self.total)
        if im.button("Next##dataset"):
            self.page += 1
            self._request_refresh()
        im.set_item_tooltip("Show the next page of datasets.")
        im.end_disabled()
        im.same_line()
        im.text(f"{self.total} datasets")
        im.begin_disabled(self.selection is None)
        if im.button("Open selected##dataset"):
            if self.on_paths is None:
                self.accept()
            else:
                self._pending_kind = "open"
                self._pending = _EXECUTOR.submit(resolve_local_path, self.client, self.selection)
                self._pending_frame_hooked = False
                self._request_completion_frame()
        im.set_item_tooltip("Open the selected dataset in this tool; remote objects are downloaded by MMFDB.")
        im.end_disabled()
        im.same_line()
        if im.button("Cancel##dataset"):
            self.close()
        im.set_item_tooltip("Close the picker without opening a dataset.")
        self._dialog.end()
        if pressed == "close":
            self.close()
