"""Native, declaration-backed reader settings for the existing shell host seam."""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import SECTION_KEYS, FormState, draw_form

from chisurf.core.dataspec import _SECTION_TYPES, ModelView, Section
from chisurf.core.support.i18n import tr
from chisurf.emtk.dataset_picker import DatasetPicker


def native_reader_spec(view: ModelView | Mapping) -> dict:
    """Convert typed descriptors through their owning registry or copy native JSON.

    Parameters
    ----------
    view : ModelView or mapping
        The reader's existing declaration. Native-only metadata stays intact.

    Returns
    -------
    dict
        A detached declaration retaining section types and binding callbacks.
    """
    if isinstance(view, Mapping):
        return copy.deepcopy(dict(view))
    if not isinstance(view, ModelView):
        raise TypeError("reader view_spec must return ModelView or a native mapping")
    if view.plots:
        raise ValueError("unsupported reader plots require a registered native preview")
    kinds = {cls: kind for kind, cls in _SECTION_TYPES.items()}

    def convert(value):
        """Retain JSON section types while walking the existing frozen descriptors."""
        if isinstance(value, Section):
            kind = kinds.get(type(value))
            if kind is None:
                raise ValueError(f"unsupported reader section {type(value).__name__}")
            return {
                "type": kind,
                **{field.name: convert(getattr(value, field.name))
                   for field in dataclasses.fields(value) if getattr(value, field.name) is not None},
            }
        if isinstance(value, Mapping):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [convert(item) for item in value]
        return value

    return {"sections": convert(view.sections)}


def _target(model: Any, path: str | None) -> Any:
    """Resolve the same optional dotted target used by the shared form renderer."""
    for name in str(path or "").split("."):
        if name:
            model = getattr(model, name)
    return model


class _DataSource:
    """Bind the existing data_source dialect to native file and database pickers."""

    def __init__(self, app: ReaderSettingsApp, section: dict) -> None:
        self.app = app
        self.target = _target(app.model, section.get("target"))
        self.options = dict(section.get("options") or {})
        self.attr = str(self.options.get("attr") or "")
        self.name = self.attr
        self.state = FormState(on_used=lambda name: app.request_frame())
        label = self.options.get("label") or tr("File")
        tip = self.options.get("description") or section.get("description") or tr("Input file.")
        buttons = [{"label": tr("Browse"), "action": "browse",
                    "description": tr("Choose an input from disk.")}]
        if self.options.get("mmfdb", True) and self.options.get("mode") != "folder":
            buttons.append({"label": tr("Database"), "action": "database",
                            "description": tr("Choose a dataset from the database.")})
        self.spec = {"sections": [
            {"type": "value", "attr": "path", "kind": "str", "label": label,
             "description": tip, "placeholder": self.options.get("placeholder", ""),
             "read_only": self.options.get("read_only", False)},
            {"type": "button_row", "buttons": buttons},
        ]}

    @property
    def path(self) -> str:
        """Read the actual reader value every frame rather than keeping a copy."""
        return str(getattr(self.target, self.attr) or "")

    @path.setter
    def path(self, path: str) -> None:
        """Commit a typed, browsed, database-picked or dropped path identically."""
        if self.app.closed or self.options.get("read_only"):
            return
        call = self.options.get("call")
        if call:
            getattr(self.target, call)(str(path))
        else:
            setattr(self.target, self.attr, str(path))
        self.app.request_frame()

    def enabled(self, name: str) -> bool:
        """Read-only source declarations disable all ways of changing the input."""
        return name == "path" or not self.options.get("read_only", False)

    def browse(self) -> None:
        """Open the existing native file/folder dialog for this declared input."""
        mode = self.options.get("mode", "open")
        if mode == "file":
            mode = "open"
        current = Path(self.path).expanduser() if self.path else None
        directory = current if current and mode == "folder" else current.parent if current else None
        self.app.file_source = self
        self.app.file_dialog = FileDialog(
            tr("Choose input"), mode=mode,
            filters=self.options.get("filter", "All files (*)"),
            directory=str(directory) if directory else None,
        )
        self.app.file_window = DialogWindow(tr("Choose input"), size=(760, 540))
        self.app.request_frame()

    def database(self) -> None:
        """Ask MMFDB to materialize an input through its existing native picker."""
        self.app.picker = DatasetPicker(
            client=self.app.dataset_client,
            kinds=self.options.get("mmfdb_kinds"),
            formats=self.options.get("mmfdb_formats"),
            scope=self.options.get("mmfdb_scope", "all"),
            on_paths=lambda paths: setattr(self, "path", str(paths[0])) if paths else None,
        )
        self.app.picker.open()
        self.app.request_frame()


class ReaderSettingsApp(ImApp):
    """Render a complete reader declaration over its original scientific owner.

    Parameters
    ----------
    reader : object
        Reader with a callable ``view_spec`` returning native JSON or ModelView.
    dataset_client : object, optional
        Existing MMFDB client; resolved lazily by DatasetPicker when omitted.
    """

    def __init__(self, reader: Any, *, dataset_client: Any = None) -> None:
        self.model = reader
        self.dataset_client = dataset_client
        self.form = FormState()
        self.sources: dict[str, _DataSource] = {}
        self.file_dialog: FileDialog | None = None
        self.file_window: DialogWindow | None = None
        self.file_source: _DataSource | None = None
        self.picker: DatasetPicker | None = None
        self.closed = False
        self.spec = native_reader_spec(reader.view_spec())
        register = getattr(reader, "register_settings_sections", None)
        if callable(register):
            register(self.form)
        self.form.custom["data_source"] = self._draw_source
        sections = self.spec.get("sections")
        if not isinstance(sections, (list, tuple)) or not sections:
            raise ValueError("reader view_spec must declare nonempty sections")
        self._prepare(sections)
        self.form.on_used = lambda name: self.request_frame()
        super().__init__(gui=self._render, continuous=False)

    def _prepare(self, sections) -> None:
        """Validate the entire view before a host can show any partial settings."""
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError("unsupported reader section declaration")
            kind = section.get("type")
            if kind == "value" and section.get("kind") in {"file", "directory"}:
                options = {
                    "attr": section.get("attr"), "call": section.get("call"),
                    "label": section.get("label"), "description": section.get("description"),
                    "placeholder": section.get("placeholder", ""),
                    "read_only": section.get("read_only", False),
                    "mode": "folder" if section["kind"] == "directory" else "open",
                }
                section.update(type="custom", key="data_source", options=options)
                kind = "custom"
            if kind not in SECTION_KEYS or section.get("set_action") or section.get("collapsed_when"):
                raise ValueError(f"unsupported reader section {kind!r}")
            if kind == "custom":
                key = section.get("key")
                if key not in {*self.form.custom, "data_table", "code_editor"}:
                    raise ValueError(f"unsupported reader custom section {key!r}")
                if key == "data_source":
                    options = section.get("options") or {}
                    if options.get("guards"):
                        raise ValueError("unsupported reader drop guards require a native handler")
                    source = _DataSource(self, section)
                    if not source.attr or not hasattr(source.target, source.attr):
                        raise ValueError("data_source requires a declared reader attribute")
                    if options.get("call") and not callable(getattr(source.target, options["call"], None)):
                        raise ValueError("data_source requires a callable declared setter")
                    if source.name in self.sources:
                        raise ValueError(f"duplicate reader input {source.name!r}")
                    self.sources[source.name] = source
            self._prepare(section.get("sections") or ())

    @property
    def item_rects(self) -> dict:
        """Expose the rendered controls to the shared Driver and guided-tour contract."""
        return self.form.rects

    def _draw_source(self, section, model, state, width) -> None:
        """Draw a source using standard declared fields/buttons, never hand widgets."""
        source = self.sources[str(section["options"]["attr"])]
        im.push_id(source.name)
        draw_form(source.spec, source, source.state)
        im.pop_id()
        for name, rect in source.state.rects.items():
            state.rects[source.name if name == "path" else f"{source.name}.{name}"] = rect

    def _render(self) -> None:
        """Draw the declared form and existing native input dialogs in one surface."""
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_RESIZE
        self.form.rects.clear()
        im.begin("##reader-settings", box, flags=flags)
        draw_form(self.spec, self.model, self.form)
        im.end()
        if self.file_dialog is not None:
            window, source = self.file_window, self.file_source
            assert window is not None and source is not None
            close = window.begin(box)
            paths = self.file_dialog.draw()
            window.end()
            if close or paths is False:
                self.file_dialog = None
            elif paths:
                self.file_dialog = None
                source.path = str(paths[0])
        if self.picker is not None:
            self.picker.render(box)

    def on_files_dropped(self, paths) -> bool:
        """Route a drop only when one declared input accepts its file type."""
        if self.closed or len(self.sources) != 1 or not paths:
            return False
        source = next(iter(self.sources.values()))
        if source.options.get("read_only"):
            return False
        extensions = source.options.get("extensions") or ()
        if extensions and Path(paths[0]).suffix.lower() not in {
            str(ext).lower() if str(ext).startswith(".") else "." + str(ext).lower()
            for ext in extensions
        }:
            return False
        source.path = str(paths[0])
        return True

    def animating(self) -> bool:
        """Keep native picker progress visible while its worker is pending."""
        return bool(self.picker and self.picker._pending is not None) or super().animating()

    def close(self) -> None:
        """Detach host callbacks and cancel picker delivery without closing the reader."""
        if self.closed:
            return
        self.closed = True
        self.set_frame_request_callback(None)
        if self.picker is not None:
            self.picker.close()
        self.file_dialog = None
        self.form.custom.clear()
