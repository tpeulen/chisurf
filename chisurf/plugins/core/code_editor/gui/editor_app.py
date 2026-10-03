"""EMTK immediate-mode multi-document Code Editor.

Features:
- Multi-tab file editing with syntax highlighting (Python, JSON, C++, etc.)
- Embedded AI Assistant Chat panel with bidirectional code insertion and ACP sync
- Project file tree browser
- Script execution console & output logs
- Pure EMTK rendering with DockManager layout
"""

from __future__ import annotations

import os
import pathlib
import queue
import re
import shlex
import subprocess
import sys
import threading
import uuid
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import emtk.im as im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.im_core import Col
from emtk.widgets.text_editor import Language, TextEditor

from chisurf.plugins.core.code_editor.gui.chat_app import ChatGui, ChatModel
from chisurf.plugins.core.code_editor.gui.native_lsp import NativeLspClient
from chisurf.plugins.core.code_editor.gui.notebook_app import SHELL_EXECUTION_LOCK, NativeNotebook
from chisurf.plugins.core.code_editor.gui.process_tools import CancellableRuffRunner
from chisurf.plugins.core.code_editor.ruff_runner import RuffRunner
from chisurf.plugins.core.code_editor.symbols import extract_python_symbols

from .editor_preferences import (
    COLOR_SCHEMES,
    LANGUAGES,
    font_choices,
    language_for,
    palette_for,
    rgba,
)

WINDOW_BG = (24, 26, 32, 255)

# EMTK's default 8 pt chrome is too small for the editor's dense desktop
# workspace. Keep text-zoom preferences relative to this readable baseline.
# 1.4 compensated for the old Qt-host DPI bug that rendered emtk text at the
# wrong size on some platforms; with fonts now pixel-exact at the emtk level
# the extra scale double-applied and made the whole UI too large.
CODE_EDITOR_UI_SCALE = 1.0


def _detect_language(path_str: str) -> Language | None:
    """Return appropriate syntax highlighting Language for a file path."""
    ext = pathlib.Path(path_str).suffix.lower()
    if ext in (".py", ".pyw"):
        return Language.python()
    elif ext in (".yaml", ".yml"):
        return Language.yaml()
    elif ext in (".md", ".markdown"):
        return Language.markdown()
    elif ext in (".json", ".ipynb"):
        return Language.json()
    elif ext in (".c", ".cpp", ".cc", ".h", ".hpp"):
        return Language.cpp()
    return None


class EditorDocument:
    """Represents a single open document buffer in the editor."""

    def __init__(
        self,
        path: str | None = None,
        name: str = "Untitled.py",
        content: str = "",
    ) -> None:
        self.document_id = str(uuid.uuid4())
        self.path = str(path) if path else None
        self.name = pathlib.Path(path).name if path else name
        lang = _detect_language(self.name)
        self._editor = TextEditor(content, language=lang)
        self.notebook: NativeNotebook | None = None
        if pathlib.Path(self.name).suffix.lower() == ".ipynb":
            try:
                self.notebook = NativeNotebook.from_json(content, self.path) if content.strip() else NativeNotebook.new()
            except (ValueError, TypeError, KeyError):
                pass  # Corrupt notebooks remain recoverable in the raw JSON editor.
        self.diagnostics: list[dict[str, Any]] = []
        self.lsp_diagnostics: list[dict[str, Any]] = []
        self._symbols_text: str | None = None
        self._symbols = []
        self._initial_text = self.text

    @property
    def editor(self) -> TextEditor:
        return self.notebook.active_cell.editor if self.notebook is not None else self._editor

    @property
    def text(self) -> str:
        return self.notebook.dumps() if self.notebook is not None else self._editor.text

    @text.setter
    def text(self, val: str) -> None:
        if self.notebook is not None:
            try:
                self.notebook.reload(val)
            except (ValueError, TypeError):
                notebook = NativeNotebook.new()
                notebook.active_cell.editor.set_text(val)
                self.notebook.data, self.notebook.cells = notebook.data, notebook.cells
                self.notebook.active_index = 0
        else:
            self._editor.set_text(val)

    @property
    def is_modified(self) -> bool:
        return self.text != self._initial_text

    def mark_saved(self) -> None:
        if self.notebook is not None:
            for cell in self.notebook.cells:
                cell.editor.mark_saved()
        else:
            self._editor.mark_saved()
        self._initial_text = self.text


class EditorModel:
    """State and operations for the multi-document editor."""

    def __init__(self, project_root: str | pathlib.Path | None = None) -> None:
        self.documents: list[EditorDocument] = []
        self.active_index: int = 0
        self.project_root: pathlib.Path = (
            pathlib.Path(project_root) if project_root else pathlib.Path.cwd()
        )
        self.output_logs: list[str] = [
            "ChiSurf EMTK Code Editor initialized.",
            f"Project root: {self.project_root}",
        ]
        self.is_running_script: bool = False
        self._script_process: subprocess.Popen | None = None
        self._script_thread: threading.Thread | None = None
        self._script_stop = threading.Event()
        self.run_endpoint = "process"
        self.event_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._ruff_running = False
        self._ruff_runner: CancellableRuffRunner | None = None
        self._closed = False
        self._owner_thread = threading.get_ident()
        self.request_frame: Callable[[], None] | None = None
        self._call_lock = threading.Lock()
        self._queued_calls: dict[threading.Event, dict] = {}
        self.lsp_client: NativeLspClient | None = None
        self.lsp_status = "LSP disabled"
        self.enable_lsp = False
        self._lsp_documents: dict[str, EditorDocument] = {}
        self.completions: list[dict] = []
        self.hover_text = ""
        self._completion_document: EditorDocument | None = None
        self._completion_source = ""
        from chisurf.plugins.core.code_editor.backend.services import STORE
        self.document_store = STORE
        self.document_store.changed.connect(self._on_store_changed)
        self._store_revisions: dict[str, int] = {}
        self._store_sources: dict[str, str] = {}
        self.recent_files: list[str] = []
        self.font_scale = 1.0
        self.font_family = "monospace"
        self.font_size = 0
        self.language = "Auto"
        self.color_scheme = "Dark"
        self.display_colors = dict(COLOR_SCHEMES["Dark"])
        self.caret_line_visible = True
        self.enable_ruff = True
        self.run_ruff_on_save = False
        self.ruff_timeout_ms = 5000
        self.ruff_extra_args: list[str] = []
        self.show_line_numbers = True
        self.show_whitespace = False
        self.tab_size = 4
        self.insert_spaces = True
        self.enable_rpc = False
        self.rpc_host = "127.0.0.1"
        self.rpc_cmd_port = 8775
        self.rpc_pub_port = 8776
        self.rpc_status = "Editor RPC disabled"
        self._rpc_server = None
        self._rpc_runner = None

        try:
            from chisurf.emtk.code_links import register_emtk_editor

            register_emtk_editor(self)
        except Exception:
            pass

        # Open a default initial buffer
        self.new_document("main.py", "# Welcome to ChiSurf EMTK Code Editor\nprint('Hello from ChiSurf!')\n")

    @property
    def active_doc(self) -> EditorDocument | None:
        if 0 <= self.active_index < len(self.documents):
            return self.documents[self.active_index]
        return None

    def new_document(self, name: str = "Untitled.py", content: str = "") -> EditorDocument:
        requested = pathlib.Path(name)
        existing = {doc.name for doc in self.documents}
        counter = 2
        while name in existing:
            name = f"{requested.stem}_{counter}{requested.suffix}"
            counter += 1
        doc = EditorDocument(path=None, name=name, content=content)
        self.documents.append(doc)
        self.active_index = len(self.documents) - 1
        self._sync_document_store(activate=True)
        return doc

    def open_file(self, path: str | pathlib.Path, line: int | None = None) -> EditorDocument | None:
        resolved = pathlib.Path(path).resolve()
        target_doc = None
        for idx, doc in enumerate(self.documents):
            if doc.path and pathlib.Path(doc.path).resolve() == resolved:
                self.active_index = idx
                target_doc = doc
                break

        if target_doc is None:
            try:
                with open(resolved, encoding="utf-8") as f:
                    content = f.read()
                target_doc = EditorDocument(path=str(resolved), name=resolved.name, content=content)
                self.documents.append(target_doc)
                self.active_index = len(self.documents) - 1
                self.log_output(f"Opened {resolved}")
            except Exception as e:
                self.log_output(f"Failed to open {resolved}: {e}")
                return None

        for header in target_doc.text.splitlines()[:5]:
            if header.strip().startswith("# !chisurf:"):
                endpoint = header.split(":", 1)[1].strip().lower()
                if endpoint in ("console", "ipython", "process"):
                    self.run_endpoint = "console" if endpoint == "ipython" else endpoint
                break

        if line is not None and target_doc is not None:
            try:
                from emtk.widgets.text_editor import Pos

                target_line = max(0, int(line) - 1)
                target_doc.editor.set_cursor(Pos(target_line, 0))
                target_doc.editor.scroll_to_line(target_line, align="middle")
            except Exception as e:
                self.log_output(f"Failed to position cursor at line {line}: {e}")

        self.recent_files = [str(resolved)] + [path for path in self.recent_files if path != str(resolved)]
        self.recent_files = self.recent_files[:20]
        self._sync_document_store(activate=True)
        return target_doc

    def save_document(self, index: int | None = None, path: str | pathlib.Path | None = None, *, overwrite: bool = False) -> bool:
        idx = self.active_index if index is None else index
        if not (0 <= idx < len(self.documents)):
            return False
        doc = self.documents[idx]
        destination = pathlib.Path(path).resolve() if path is not None else (pathlib.Path(doc.path) if doc.path else None)
        if destination is None:
            self.log_output("Choose a destination with Save As before saving an unnamed document.")
            return False
        if destination.exists() and str(destination) != doc.path and not overwrite:
            self.log_output(f"Confirm replacing {destination} before saving.")
            return False
        try:
            destination.write_text(doc.text, encoding="utf-8")
            doc.path = str(destination)
            doc.name = destination.name
            if doc.notebook is not None:
                doc.notebook.path = doc.path
            else:
                doc.editor.set_language(_detect_language(doc.name))
            doc.mark_saved()
            self.log_output(f"Saved {doc.path}")
            self.recent_files = [doc.path] + [path for path in self.recent_files if path != doc.path]
            self.recent_files = self.recent_files[:20]
            self._sync_document_store()
            if self.enable_ruff and self.run_ruff_on_save:
                self.start_ruff()
            return True
        except Exception as e:
            self.log_output(f"Failed to save {destination}: {e}")
            return False

    def reload_document(self, index: int | None = None, *, discard_changes: bool = False) -> bool:
        index = self.active_index if index is None else index
        if not 0 <= index < len(self.documents):
            return False
        doc = self.documents[index]
        if doc.path is None:
            self.log_output("Save the document before reloading from disk.")
            return False
        if doc.is_modified and not discard_changes:
            self.log_output("Confirm discarding unsaved changes before reloading.")
            return False
        try:
            content = pathlib.Path(doc.path).read_text(encoding="utf-8")
            if doc.notebook is not None:
                doc.notebook.reload(content)
            else:
                doc.text = content
            doc.mark_saved()
            self.log_output(f"Reloaded {doc.path}")
            return True
        except Exception as error:
            self.log_output(f"Failed to reload {doc.path}: {error}")
            return False

    def export_notebook(self, path: str | pathlib.Path, index: int | None = None, *, overwrite: bool = False) -> bool:
        index = self.active_index if index is None else index
        if not 0 <= index < len(self.documents):
            return False
        doc = self.documents[index]
        target = pathlib.Path(path).resolve()
        if doc.notebook is None or target.suffix.lower() != ".py" or str(target) == doc.path:
            self.log_output("Choose a separate .py destination to export notebook source.")
            return False
        if target.exists() and not overwrite:
            self.log_output(f"Confirm replacing {target} before exporting.")
            return False
        try:
            target.write_text(doc.notebook.export_python(), encoding="utf-8")
            self.log_output(f"Exported notebook source to {target}")
            return True
        except Exception as error:
            self.log_output(f"Failed to export notebook: {error}")
            return False

    def close_document(self, index: int | None = None) -> None:
        idx = self.active_index if index is None else index
        if 0 <= idx < len(self.documents):
            closed = self.documents.pop(idx)
            if closed.notebook is not None:
                closed.notebook.close()
            self.document_store.remove(closed.document_id)
            self._store_revisions.pop(closed.document_id, None)
            self._store_sources.pop(closed.document_id, None)
            if self.document_store.active_document_id == closed.document_id:
                self.document_store.active_document_id = None
            if idx < self.active_index:
                self.active_index -= 1
            self.active_index = min(self.active_index, max(0, len(self.documents) - 1))
            self._sync_document_store()

    def log_output(self, line: str) -> None:
        self.output_logs.append(line)
        if len(self.output_logs) > 1000:
            self.output_logs = self.output_logs[-1000:]

    # -- Chat Integration ----------------------------------------------------

    def get_file_content(self, path: str) -> str | None:
        resolved = pathlib.Path(path).resolve()
        for doc in self.documents:
            if doc.path and pathlib.Path(doc.path).resolve() == resolved:
                return doc.text
        return None

    def set_file_content(self, path: str, content: str) -> bool:
        resolved = pathlib.Path(path).resolve()
        for doc in self.documents:
            if doc.path and pathlib.Path(doc.path).resolve() == resolved:
                doc.text = content
                self._sync_document_store()
                return True
        return False

    def insert_code_at_cursor(self, code: str) -> None:
        doc = self.active_doc
        if doc and hasattr(doc.editor, "paste"):
            doc.editor.clipboard = code
            doc.editor.paste()

    def replace_selected_code(self, code: str) -> None:
        doc = self.active_doc
        if doc and hasattr(doc.editor, "paste"):
            doc.editor.clipboard = code
            doc.editor.paste()

    def start_rpc(self, host: str | None = None, cmd_port: int | None = None, pub_port: int | None = None) -> bool:
        """Enable the existing Qt-free loopback transport for live native buffers."""
        from chisurf.plugins.core.code_editor.rpc_server import EditorRpcServer
        self.stop_rpc()
        if host is not None:
            self.rpc_host = host
        if cmd_port is not None:
            self.rpc_cmd_port = cmd_port
        if pub_port is not None:
            self.rpc_pub_port = pub_port
        try:
            if not (1 <= self.rpc_cmd_port <= 65535 and 1 <= self.rpc_pub_port <= 65535) or self.rpc_cmd_port == self.rpc_pub_port:
                raise ValueError("Choose two distinct RPC ports between 1 and 65535")
            self._rpc_runner = CancellableRuffRunner()
            server = EditorRpcServer(host=self.rpc_host, cmd_port=self.rpc_cmd_port, pub_port=self.rpc_pub_port,
                store=self.document_store, runner=self._rpc_runner)
            server.start()
            self._rpc_server = server
            self.enable_rpc = True
            self.rpc_status = f"Editor RPC ready: {self.rpc_host}:{self.rpc_cmd_port}"
            return True
        except Exception as error:
            self._rpc_server = None
            self._rpc_runner = None
            self.enable_rpc = False
            self.rpc_status = f"Editor RPC unavailable: {error}"
            self.log_output(self.rpc_status)
            return False

    def stop_rpc(self) -> None:
        if self._rpc_runner is not None:
            self._rpc_runner.cancel()
            self._rpc_runner = None
        if self._rpc_server is not None:
            self._rpc_server.stop()
            self._rpc_server = None
        self.enable_rpc = False
        self.rpc_status = "Editor RPC disabled"

    def _on_store_changed(self, snapshot) -> None:
        if not self._closed and (snapshot is None or any(doc.document_id == snapshot.document_id for doc in self.documents)):
            if self.request_frame is not None:
                self.request_frame()

    def _sync_document_store(self, *, activate: bool = False) -> None:
        """Apply incoming RPC revisions and publish current native buffer snapshots."""
        if self._closed:
            return
        owned = {doc.document_id for doc in self.documents}
        for doc in list(self.documents):
            snapshot = self.document_store.get(document_id=doc.document_id)
            known_revision = self._store_revisions.get(doc.document_id)
            source = doc.text
            if snapshot is not None and known_revision is not None and snapshot.revision != known_revision:
                if doc.notebook is not None and doc.notebook.is_running:
                    continue
                if source != self._store_sources.get(doc.document_id) and source != snapshot.content:
                    conflict = EditorDocument(name=f"RPC_conflict_{doc.name}", content=snapshot.content)
                    conflict._initial_text = ""
                    self.documents.append(conflict)
                    self.log_output(f"Concurrent RPC and local changes: kept local {doc.name} and opened the RPC version in {conflict.name}.")
                else:
                    if doc.notebook is not None:
                        doc.text = snapshot.content
                    else:
                        from emtk.widgets.text_editor import Pos
                        previous = doc.editor.cursors.main.end
                        end = Pos(doc.editor.line_count - 1, len(doc.editor.document.lines[-1].text))
                        doc.editor.replace_section(Pos(0, 0), end, snapshot.content)
                        doc.editor.set_cursor(previous)
                    source = doc.text
            try:
                updated = self.document_store.upsert(document_id=doc.document_id, path=doc.path or "", name=doc.name,
                    language="Notebook" if doc.notebook is not None else doc.editor.language_name,
                    content=source, modified=doc.is_modified,
                    expected_revision=snapshot.revision if snapshot else None)
            except ValueError:
                continue  # Another RPC arrived; apply it on the next render instead of overwriting it.
            self._store_revisions[doc.document_id] = updated.revision
            self._store_sources[doc.document_id] = source
        if self.active_doc is not None and (activate or self.document_store.active_document_id is None
            or self.document_store.active_document_id in owned):
            self.document_store.active_document_id = self.active_doc.document_id

    def set_color_scheme(self, name: str) -> None:
        if name in COLOR_SCHEMES:
            self.color_scheme = name
            self.display_colors = dict(COLOR_SCHEMES[name])

    def set_display_color(self, name: str, value: str) -> bool:
        if name not in self.display_colors:
            return False
        try:
            rgba(value)
        except (ValueError, TypeError):
            self.log_output("Invalid editor color: use #aabbcc or #aabbccdd")
            return False
        self.display_colors[name] = value
        return True

    def apply_editor_preferences(self, editor: TextEditor, *, apply_language: bool = True) -> None:
        editor.config.show_line_numbers = self.show_line_numbers
        editor.config.show_spaces = self.show_whitespace
        editor.config.show_tabs = self.show_whitespace
        editor.config.tab_size = self.tab_size
        editor.config.insert_spaces_on_tabs = self.insert_spaces
        editor.config.background_color = rgba(self.display_colors["paper_color"])
        editor.config.margin_color = rgba(self.display_colors["margins_background_color"])
        editor.config.selection_color = rgba(self.display_colors["marker_background_color"])
        editor.config.current_line_color = rgba(self.display_colors["caret_line_background_color"])
        editor.config.caret_color = rgba(self.display_colors["default_color"])
        editor.config.line_number_color = rgba(self.display_colors["default_color"])
        editor.config.highlight_current_line = self.caret_line_visible
        editor.palette = palette_for(self.color_scheme, self.display_colors["default_color"])
        if apply_language:
            requested = self.language
            if requested == "Auto":
                owner = next((doc for doc in self.documents if doc.editor is editor), None)
                definition = _detect_language(owner.name) if owner is not None else None
            else:
                definition = language_for(requested)
            if editor.language_name != (definition.name if definition else "None"):
                editor.set_language(definition)

    def export_settings(self) -> dict:
        """Export declared preferences only; buffer content and secrets stay in memory."""
        return {"recent_files": list(self.recent_files[:20]), "project_root": str(self.project_root),
            "run_endpoint": self.run_endpoint, "font_scale": self.font_scale,
            "show_line_numbers": self.show_line_numbers, "show_whitespace": self.show_whitespace,
            "tab_size": self.tab_size, "insert_spaces": self.insert_spaces, "enable_lsp": self.enable_lsp,
            "enable_rpc": self.enable_rpc, "rpc_host": self.rpc_host,
            "rpc_cmd_port": self.rpc_cmd_port, "rpc_pub_port": self.rpc_pub_port,
            "font_family": self.font_family, "font_size": self.font_size, "language": self.language,
            "color_scheme": self.color_scheme, **self.display_colors, "caret_line_visible": self.caret_line_visible,
            "enable_ruff": self.enable_ruff, "run_ruff_on_save": self.run_ruff_on_save,
            "ruff_timeout_ms": self.ruff_timeout_ms, "ruff_extra_args": list(self.ruff_extra_args)}

    def restore_settings(self, settings: dict) -> None:
        if settings.get("color_scheme") in COLOR_SCHEMES:
            self.set_color_scheme(settings["color_scheme"])
        for name in self.display_colors:
            if isinstance(settings.get(name), str):
                self.set_display_color(name, settings[name])
        family = settings.get("font_family")
        if family in font_choices():
            self.font_family = family
        elif family is not None:
            self.log_output(f"Font family {family!r} is unavailable; keeping the native monospaced default.")
        size = settings.get("font_size")
        if isinstance(size, int) and not isinstance(size, bool) and 0 <= size <= 72:
            self.font_size = size
        language = settings.get("language")
        if language in LANGUAGES:
            self.language = language
        timeout = settings.get("ruff_timeout_ms")
        if isinstance(timeout, int) and not isinstance(timeout, bool) and 1000 <= timeout <= 60000:
            self.ruff_timeout_ms = timeout
        arguments = settings.get("ruff_extra_args")
        if isinstance(arguments, list) and all(isinstance(value, str) for value in arguments):
            self.ruff_extra_args = list(arguments)
        for name in ("caret_line_visible", "enable_ruff", "run_ruff_on_save"):
            if isinstance(settings.get(name), bool):
                setattr(self, name, settings[name])
        paths = settings.get("recent_files", [])
        if isinstance(paths, list):
            self.recent_files = list(dict.fromkeys(path for path in paths if isinstance(path, str)))[:20]
        root = settings.get("project_root")
        if isinstance(root, str) and pathlib.Path(root).is_dir():
            self.project_root = pathlib.Path(root)
        endpoint = settings.get("run_endpoint")
        if endpoint in ("console", "process"):
            self.run_endpoint = endpoint
        scale = settings.get("font_scale")
        if isinstance(scale, (float, int)) and not isinstance(scale, bool) and 0.5 <= scale <= 3:
            self.font_scale = float(scale)
        size = settings.get("tab_size")
        if isinstance(size, int) and not isinstance(size, bool) and 1 <= size <= 16:
            self.tab_size = size
        for name in ("show_line_numbers", "show_whitespace", "insert_spaces"):
            value = settings.get(name)
            if isinstance(value, bool):
                setattr(self, name, value)
        host = settings.get("rpc_host")
        if isinstance(host, str):
            self.rpc_host = host
        for name in ("rpc_cmd_port", "rpc_pub_port"):
            value = settings.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535:
                setattr(self, name, value)
        if settings.get("enable_rpc") is True:
            self.start_rpc()
        elif settings.get("enable_rpc") is False:
            self.stop_rpc()
        enabled = settings.get("enable_lsp")
        if enabled is True:
            self.start_lsp()
        elif enabled is False:
            self.stop_lsp()
        for doc in self.documents:
            editors = [cell.editor for cell in doc.notebook.cells] if doc.notebook else [doc.editor]
            for editor in editors:
                self.apply_editor_preferences(editor, apply_language=doc.notebook is None)

    def invoke(self, callback: Callable, *args, timeout: float = 30.0, **kwargs):
        """Run an editor operation on its render thread and return its result."""
        if self._closed:
            raise RuntimeError("The editor is closed")
        if threading.get_ident() == self._owner_thread:
            return callback(*args, **kwargs)
        ready = threading.Event()
        result = {}
        with self._call_lock:
            if self._closed:
                raise RuntimeError("The editor is closed")
            self._queued_calls[ready] = result
        def execute() -> None:
            if result.get("cancelled"):
                return
            try:
                if self._closed:
                    raise RuntimeError("The editor closed before the operation ran")
                result["value"] = callback(*args, **kwargs)
            except Exception as error:
                result["error"] = error
            finally:
                ready.set()
        self.event_queue.put(execute)
        if self.request_frame is not None:
            self.request_frame()
        try:
            if not ready.wait(timeout):
                result["cancelled"] = True
                raise TimeoutError("The editor did not process the queued operation")
            if "error" in result:
                raise result["error"]
            return result.get("value")
        finally:
            with self._call_lock:
                self._queued_calls.pop(ready, None)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.document_store.changed.disconnect(self._on_store_changed)
        self.request_frame = None
        with self._call_lock:
            for ready, result in self._queued_calls.items():
                result["cancelled"] = True
                result["error"] = RuntimeError("The editor closed before the operation ran")
                ready.set()
        self.stop_active_script()
        self.stop_rpc()
        self.stop_lsp()
        if self._ruff_runner is not None:
            self._ruff_runner.cancel()
        self._ruff_running = False
        from chisurf.emtk.code_links import unregister_emtk_editor
        unregister_emtk_editor(self)
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                break
        self.is_running_script = False
        for doc in self.documents:
            if doc.notebook is not None:
                doc.notebook.close()
            self.document_store.remove(doc.document_id)
            if self.document_store.active_document_id == doc.document_id:
                self.document_store.active_document_id = None
        self._store_revisions.clear()
        self._store_sources.clear()

    def process_events(self) -> None:
        if self._closed:
            return
        self._sync_document_store()
        while True:
            try:
                callback = self.event_queue.get_nowait()
            except queue.Empty:
                break
            callback()
        self._sync_document_store()
        self._sync_lsp_documents()

    @staticmethod
    def _lsp_index(line: str, character: int) -> int:
        return len(line.encode("utf-16-le")[:max(0, character) * 2].decode("utf-16-le", errors="ignore"))

    def _lsp_path(self, doc: EditorDocument) -> str:
        return doc.path or str(self.project_root / ".chisurf-unsaved" / f"{id(doc)}_{doc.name}")

    def _queue_lsp(self, callback) -> None:
        if not self._closed:
            self.event_queue.put(lambda: callback() if not self._closed else None)
            if self.request_frame is not None:
                self.request_frame()

    def start_lsp(self, command: list[str] | None = None) -> bool:
        if self._closed:
            return False
        self.stop_lsp()
        self.enable_lsp = True
        client = NativeLspClient(self.project_root, command)
        self.lsp_client = client
        def status(text):
            self._queue_lsp(lambda: setattr(self, "lsp_status", text) if self.lsp_client is client else None)
        def diagnostics(uri, values):
            self._queue_lsp(lambda: self._set_lsp_diagnostics(uri, values) if self.lsp_client is client else None)
        client.status_changed.connect(status)
        client.diagnostics_received.connect(diagnostics)
        return client.start()

    def stop_lsp(self) -> None:
        self.enable_lsp = False
        if self.lsp_client is not None:
            self.lsp_client.stop()
            self.lsp_client = None
        self._lsp_documents.clear()
        self.completions.clear()
        self.lsp_status = "LSP disabled"

    def _sync_lsp_documents(self) -> None:
        client = self.lsp_client
        if client is None or not client.is_ready:
            return
        documents = {self._lsp_path(doc): doc for doc in self.documents
            if doc.notebook is None and pathlib.Path(doc.name).suffix.lower() in (".py", ".pyw")}
        for path in self._lsp_documents.keys() - documents.keys():
            client.close_document(path)
        self._lsp_documents = documents
        for path, doc in documents.items():
            client.open_document(path, doc.text)

    def _set_lsp_diagnostics(self, uri: str, values: list[dict]) -> None:
        path = str(pathlib.Path(unquote(urlparse(uri).path)).resolve())
        doc = self._lsp_documents.get(path)
        if doc is None:
            return
        lines = doc.text.split("\n")
        normalized = []
        for item in values:
            position = item.get("range", {}).get("start", {})
            line = max(0, min(position.get("line", 0), len(lines) - 1))
            normalized.append({**item, "line": line + 1,
                "column": self._lsp_index(lines[line], position.get("character", 0)), "source": "LSP"})
        doc.lsp_diagnostics = normalized

    def request_lsp(self, action: str) -> None:
        doc = self.active_doc
        client = self.lsp_client
        if (doc is None or doc.notebook is not None or pathlib.Path(doc.name).suffix.lower() not in (".py", ".pyw")
            or client is None or not client.is_ready):
            self.lsp_status = "Enable an available Python LSP server and select a Python document first"
            return
        self._sync_lsp_documents()
        source = doc.text
        cursor = doc.editor.cursors.main.end
        lines = source.split("\n")
        line = max(0, min(cursor.line, len(lines) - 1))
        character = len(lines[line][:cursor.index].encode("utf-16-le")) // 2
        def receive(result):
            def apply():
                if doc not in self.documents or self.active_doc is not doc or doc.text != source:
                    return
                if action == "completion":
                    self.completions = result.get("items", []) if isinstance(result, dict) else (result or [])
                    self._completion_document = doc
                    self._completion_source = source
                elif action == "hover":
                    contents = result.get("contents", "") if isinstance(result, dict) else ""
                    if isinstance(contents, list):
                        self.hover_text = "\n\n".join(str(value.get("value", "")) if isinstance(value, dict) else str(value) for value in contents)
                    else:
                        self.hover_text = str(contents.get("value", "")) if isinstance(contents, dict) else str(contents)
                elif action == "definition":
                    location = result[0] if isinstance(result, list) and result else result
                    if isinstance(location, dict):
                        uri = location.get("uri") or location.get("targetUri")
                        position = location.get("range", location.get("targetSelectionRange", {})).get("start", {})
                        if uri and urlparse(uri).scheme == "file":
                            target_path = str(pathlib.Path(unquote(urlparse(uri).path)).resolve())
                            target = self._lsp_documents.get(target_path)
                            if target is not None:
                                self.active_index = self.documents.index(target)
                            else:
                                target = self.open_file(target_path, position.get("line", 0) + 1)
                            if target:
                                target_lines = target.text.splitlines() or [""]
                                number = max(0, min(position.get("line", 0), len(target_lines) - 1))
                                self.goto_line(number + 1, self._lsp_index(target_lines[number], position.get("character", 0)))
                        else:
                            self.lsp_status = "No file definition location was returned"
                    else:
                        self.lsp_status = "No definition was found"
            self._queue_lsp(apply)
        client.at_position(action, self._lsp_path(doc), line, character, receive)

    def apply_completion(self, item: dict) -> bool:
        from emtk.widgets.text_editor import Pos
        doc = self.active_doc
        if doc is None or (self._completion_document is not None and (
            doc is not self._completion_document or doc.text != self._completion_source)):
            self.lsp_status = "Completion discarded because the document changed"
            return False
        source = doc.text
        lines = source.splitlines(keepends=True) or [""]
        if source.endswith("\n"):
            lines.append("")
        def offset(position):
            line = max(0, min(position.get("line", 0), len(lines) - 1))
            return sum(len(value) for value in lines[:line]) + self._lsp_index(lines[line].rstrip("\r\n"), position.get("character", 0))
        edit = item.get("textEdit", {})
        value = edit.get("newText", item.get("insertText", item.get("label", "")))
        if item.get("insertTextFormat") == 2:
            value = re.sub(r"\$\{\d+:([^}]+)\}", r"\1", value)
            value = re.sub(r"\$\{\d+\}|\$\d+", "", value)
        range_ = edit.get("range", edit.get("replace"))
        cursor = doc.editor.cursors.main.end
        if range_:
            start, end = offset(range_["start"]), offset(range_["end"])
        else:
            end = sum(len(line) for line in lines[:cursor.line]) + cursor.index
            start = end
            while start > 0 and (source[start - 1].isalnum() or source[start - 1] == "_"):
                start -= 1
        edits = [(start, end, value)]
        for extra in item.get("additionalTextEdits", []):
            edits.append((offset(extra["range"]["start"]), offset(extra["range"]["end"]), extra.get("newText", "")))
        result = source
        for lower, upper, replacement in sorted(edits, reverse=True):
            result = result[:lower] + replacement + result[upper:]
        caret = start + len(value) + sum(len(replacement) - (upper - lower) for lower, upper, replacement in edits[1:] if upper <= start)
        end_position = Pos(doc.editor.line_count - 1, len(doc.editor.document.lines[-1].text))
        doc.editor.replace_section(Pos(0, 0), end_position, result)
        before = result[:max(0, caret)]
        doc.editor.set_cursor(Pos(before.count("\n"), len(before.rsplit("\n", 1)[-1])))
        self.completions.clear()
        return True

    def document_symbols(self):
        doc = self.active_doc
        if doc is None or pathlib.Path(doc.name).suffix.lower() not in (".py", ".pyw"):
            return []
        source = doc.text
        if doc._symbols_text != source:
            doc._symbols = extract_python_symbols(source, doc.path or doc.name)
            doc._symbols_text = source
        return doc._symbols

    def goto_line(self, line: int, column: int = 0) -> None:
        from emtk.widgets.text_editor import Pos
        doc = self.active_doc
        if doc is not None:
            target = max(0, int(line) - 1)
            doc.editor.set_cursor(Pos(target, max(0, int(column))))
            doc.editor.scroll_to_line(target, align="middle")

    def _apply_ruff(self, doc: EditorDocument, original: str, result: dict, fix: bool) -> dict:
        if doc not in self.documents:
            return result
        doc.diagnostics = result.get("diagnostics", [])
        if result.get("returncode", 0) > 1:
            result["ok"] = False
            result.setdefault("error", f"Ruff exited with code {result['returncode']}")
        if not result.get("ok"):
            self.log_output(f"Ruff unavailable or failed: {result.get('error', 'unknown error')}")
        else:
            fixed = result.get("fixed_content")
            if fix and fixed is not None:
                if doc.text == original:
                    doc.text = fixed
                else:
                    self.log_output("Ruff fixes were not applied because the document changed during the check.")
            self.log_output(f"Ruff: {len(doc.diagnostics)} diagnostic(s) for {doc.name}")
        return result

    def run_ruff(self, fix: bool = False) -> dict:
        doc = self.active_doc
        if not self.enable_ruff:
            self.log_output("Ruff checks are disabled in editor settings.")
            return {"ok": False, "error": "Ruff checks are disabled", "diagnostics": []}
        if doc is None:
            return {"ok": False, "error": "No active document", "diagnostics": []}
        original = doc.text
        runner = RuffRunner()
        action = runner.fix if fix else runner.check
        result = action(doc.path or str(self.project_root / doc.name), original, timeout_ms=self.ruff_timeout_ms, extra_args=self.ruff_extra_args)
        return self._apply_ruff(doc, original, result, fix)

    def start_ruff(self, fix: bool = False) -> None:
        doc = self.active_doc
        if doc is None or self._ruff_running or self._closed:
            return
        if not self.enable_ruff:
            self.log_output("Ruff checks are disabled in editor settings.")
            return
        original = doc.text
        path = doc.path or str(self.project_root / doc.name)
        self._ruff_running = True
        self._ruff_runner = CancellableRuffRunner()
        runner = self._ruff_runner

        def check() -> None:
            try:
                result = (runner.fix if fix else runner.check)(path, original, timeout_ms=self.ruff_timeout_ms, extra_args=self.ruff_extra_args)
            except Exception as error:
                result = {"ok": False, "error": str(error), "diagnostics": []}
            def finish() -> None:
                self._ruff_running = False
                self._ruff_runner = None
                self._apply_ruff(doc, original, result, fix)
            if not self._closed:
                self.event_queue.put(finish)
        threading.Thread(target=check, daemon=True).start()

    def _run_console(self, code: str, filename: str) -> None:
        """Execute on the render thread so macros can touch the application's state."""
        if self._script_stop.is_set():
            self.is_running_script = False
            self.log_output("--- Console execution cancelled before starting ---")
            return
        import chisurf
        from chisurf.core.console.history import HistoryManager
        from chisurf.core.console.shell import Shell
        if not SHELL_EXECUTION_LOCK.acquire(blocking=False):
            self.is_running_script = False
            self.log_output("An in-process notebook command is running; wait or stop it before running a console macro.")
            return
        try:
            shell = Shell(user_ns={"__name__": "__main__", "__file__": filename,
                "chisurf": chisurf, "cs": chisurf.cs, "np": __import__("numpy"), "os": os, "sys": sys},
                write=lambda stream, text: self.log_output(text.rstrip()),
                display=lambda data, meta, kind, count: self.log_output(data.get("text/plain", "")),
                history=HistoryManager(path=False))
            shell.run_cell(code, store_history=False, filename=filename)
        except Exception as error:
            self.log_output(f"Console execution error: {error}")
        finally:
            import builtins
            if "shell" in locals() and getattr(getattr(builtins, "get_ipython", None), "__self__", None) is shell:
                del builtins.get_ipython
            SHELL_EXECUTION_LOCK.release()
            self.is_running_script = False
            self.log_output("--- Console execution finished ---")

    # -- Script Execution ----------------------------------------------------

    def run_active_script(self) -> None:
        doc = self.active_doc
        if not doc or self.is_running_script or self._closed:
            return

        if doc.notebook is not None:
            doc.notebook.start_cell(doc.notebook.active_index)
            return
        code = doc.text
        name = doc.name
        self.log_output(f"--- Running {name} ---")
        self.is_running_script = True
        self._script_stop.clear()
        if self.run_endpoint == "console":
            filename = doc.path or str(self.project_root / doc.name)
            self.event_queue.put(lambda: self._run_console(code, filename))
            return

        def _execute():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", "-c",
                        "import os, sys; filename, source = sys.argv[1:3]; "
                        "sys.argv = [filename]; sys.path.insert(0, os.path.dirname(filename)); "
                        "exec(compile(source, filename, 'exec'), {'__name__': '__main__', '__file__': filename, '__package__': None})",
                        doc.path or str(self.project_root / doc.name), code],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self.project_root),
                )
                self._script_process = proc
                if self._script_stop.is_set():
                    proc.terminate()
                if proc.stdout:
                    for line in iter(proc.stdout.readline, ""):
                        self.log_output(line.rstrip())
                proc.wait()
                self.log_output(f"--- Process finished with exit code {proc.returncode} ---")
            except Exception as e:
                self.log_output(f"Execution error: {e}")
            finally:
                self._script_process = None
                self.is_running_script = False

        self._script_thread = threading.Thread(target=_execute, daemon=True)
        self._script_thread.start()

    def stop_active_script(self) -> None:
        """Stop the current subprocess, including a stop requested during startup."""
        self._script_stop.set()
        for doc in self.documents:
            if doc.notebook is not None and doc.notebook.is_running:
                doc.notebook.cancel_execution()
        proc = self._script_process
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        self.log_output("--- Stopping script ---")

        def ensure_stopped() -> None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

        threading.Thread(target=ensure_stopped, daemon=True).start()


class CodeEditorGui:
    """EMTK immediate-mode rendering and interaction for the multi-tab Code Editor."""

    def __init__(self, model: EditorModel | None = None) -> None:
        self.model = model or EditorModel()
        self.chat_model = ChatModel(editor_ref=self.model)
        self.chat_gui = ChatGui(model=self.chat_model, editor_ref=self.model)
        self.file_filter: str = ""
        self._file_dialog: FileDialog | None = None
        self._dialog_document: EditorDocument | None = None
        self._dialog_close_after = False
        self._dialog_error = ""
        self._overwrite_path: pathlib.Path | None = None
        self._dialog_operation = "save"
        self._pending_reload: EditorDocument | None = None
        self.settings_open = False
        self.settings_status = ""
        self.save_preferences: Callable[[], bool] | None = None
        self._displayed_doc: EditorDocument | None = None
        self._pending_close: EditorDocument | None = None
        self._tab_context: EditorDocument | None = None
        self._tab_context_pos = (0.0, 0.0)

        # Dock layout:
        # files (left) | (editor top / output bottom) (center) | agent (right)
        layout = Split(
            "h",
            0.21,
            Region("files"),
            Split(
                "v", 0.80, Region("editor"), Region("output"),
            ),
        )
        self.docks = DockManager(layout)
        self.docks.add_window("files", "📁 Project", self._draw_file_tree, dock="files", closable=True, scrollable=False)
        self.docks.add_window("editor", "📝 Editor", self._draw_editor_tabs, dock="editor", closable=True, scrollable=False)
        self.docks.add_window("output", "🖥️ Output", self._draw_output_console, dock="output", closable=True, scrollable=False)
        self.docks.add_window("agent", "🤖 AI Assistant", self._draw_agent_panel, dock="files", closable=True, scrollable=False)
        self.docks.add_window("diagnostics", "Diagnostics", self._draw_diagnostics, dock="output", closable=True, scrollable=False)
        self.docks.add_window("language", "Python", self._draw_lsp, dock="files", closable=True, scrollable=True)
        self.docks.add_window("editor_settings", "⚙️ Editor settings", self._draw_settings_content, dock="editor", closable=True, scrollable=True)
        self.docks.hide("editor_settings")

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1100.0)
        height = float(h or vp.size[1] or 720.0)

        # Cohesive dark chrome (same palette family as the burst shell): the
        # default gray read as unfinished next to the Qt editor.
        im.push_style_color(Col.WINDOW_BG, (24, 26, 32, 255))
        im.push_style_color(Col.FRAME_BG, (38, 41, 48, 255))
        im.push_style_color(Col.FRAME_BG_HOVERED, (48, 52, 62, 255))
        im.push_style_color(Col.FRAME_BG_ACTIVE, (35, 85, 140, 255))
        im.push_style_color(Col.BUTTON, (44, 48, 56, 255))
        im.push_style_color(Col.BUTTON_HOVERED, (55, 60, 72, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (35, 85, 140, 255))
        im.push_style_color(Col.HEADER, (44, 48, 56, 255))
        im.push_style_color(Col.HEADER_HOVERED, (55, 60, 72, 255))
        im.push_style_color(Col.TAB, (44, 48, 56, 255))
        im.push_style_color(Col.TAB_SELECTED, (35, 85, 140, 255))
        im.push_style_color(Col.BORDER, (55, 60, 72, 255))
        im.push_style_color(Col.TEXT, (240, 240, 240, 255))
        # Frame rounding and padding stay at the emtk defaults: the pushed
        # 4 px rounding turned every button into a rounded tile, and the
        # editor's chrome should look like the rest of the application's.
        try:
            self._draw_themed(width, height)
        finally:
            for _ in range(13):
                im.pop_style_color()

    def _draw_themed(self, width: float, height: float) -> None:
        self.model.process_events()
        self.chat_model.process_events()
        if self.chat_gui.provider_settings is not None:
            self.chat_gui.provider_settings.process_events()
        # Draw dock layout
        self.docks.draw((0.0, 0.0, width, height))
        self._draw_tab_context(width, height)
        self._draw_file_dialog()
        self._draw_reload_popup()
        self._draw_settings_window()
        if not self.docks.is_shown("agent"):
            self.chat_gui.draw_provider_settings()
        if self.chat_model.pending_permission is not None and not self.docks.is_shown("agent"):
            im.set_next_window_size((500, 260), im.Cond.FIRST_USE_EVER)
            if im.begin("Agent permission##editor_permission"):
                self.chat_gui._draw_permission_banner()
            im.end()

    def _request_open(self) -> None:
        self._dialog_document = None
        self._dialog_operation = "open"
        self._dialog_error = ""
        self._file_dialog = FileDialog("Open document", directory=str(self.model.project_root), multiselect=True)

    def _request_save(self, doc: EditorDocument | None, *, save_as: bool = False, close_after: bool = False) -> None:
        if doc not in self.model.documents:
            return
        if doc.path and not save_as:
            if self.model.save_document(self.model.documents.index(doc)) and close_after:
                self.model.close_document(self.model.documents.index(doc))
            return
        self._dialog_document = doc
        self._dialog_operation = "save"
        self._dialog_close_after = close_after
        self._dialog_error = ""
        self._overwrite_path = None
        self._file_dialog = FileDialog("Save document", mode="save", directory=str(pathlib.Path(doc.path).parent if doc.path else self.model.project_root), filename=doc.name)

    def _request_export_notebook(self, doc: EditorDocument) -> None:
        self._dialog_document = doc
        self._dialog_operation = "export"
        self._dialog_close_after = False
        self._dialog_error = ""
        self._overwrite_path = None
        self._file_dialog = FileDialog("Export notebook Python source", mode="save", directory=str(self.model.project_root),
            filename=str(pathlib.Path(doc.name).with_suffix(".py")), filters="Python (*.py)")

    def _request_reload(self, doc: EditorDocument) -> None:
        if doc.path is None:
            self.model.log_output("Save the notebook before reloading it from disk.")
        elif doc.is_modified:
            self._pending_reload = doc
            im.open_popup("reload_document")
        else:
            self.model.reload_document(self.model.documents.index(doc))

    def _draw_reload_popup(self) -> None:
        if im.begin_popup("reload_document"):
            doc = self._pending_reload
            if doc in self.model.documents:
                im.text_wrapped(f"Discard unsaved changes and reload {doc.name}?")
                if im.button("Reload and discard"):
                    if self.model.reload_document(self.model.documents.index(doc), discard_changes=True):
                        im.close_current_popup()
                im.set_item_tooltip("Replace this buffer with the file on disk")
                if im.button("Cancel reload"):
                    im.close_current_popup()
                im.set_item_tooltip("Keep your current notebook and unsaved changes")
            im.end_popup()

    def _finish_save(self, path: pathlib.Path) -> None:
        doc = self._dialog_document
        if doc not in self.model.documents:
            self._file_dialog = None
            return
        index = self.model.documents.index(doc)
        overwrite = bool(getattr(self._file_dialog, "overwrite_confirmed", False) or self._overwrite_path == path)
        saved = self.model.export_notebook(path, index, overwrite=overwrite) if self._dialog_operation == "export" else self.model.save_document(index, path=path, overwrite=overwrite)
        if saved:
            if self._dialog_close_after:
                self.model.close_document(self.model.documents.index(doc))
            self._file_dialog = None
            self._overwrite_path = None
        else:
            self._dialog_error = self.model.output_logs[-1]

    def _draw_file_dialog(self) -> None:
        if self._file_dialog is None:
            return
        im.set_next_window_size((640, 520), im.Cond.FIRST_USE_EVER)
        if im.begin("Choose document##editor_file_dialog"):
            if self._overwrite_path is not None:
                im.text_wrapped(f"Replace existing file {self._overwrite_path}?")
                if im.button("Replace file"):
                    self._finish_save(self._overwrite_path)
                im.set_item_tooltip("Replace the selected file with this document's contents")
                im.same_line()
                if im.button("Choose another path"):
                    self._overwrite_path = None
                im.set_item_tooltip("Return to choosing a destination")
            else:
                result = self._file_dialog.draw()
                if result is False:
                    self._file_dialog = None
                elif result:
                    if self._dialog_document is None:
                        for path in result:
                            self.model.open_file(path)
                        self._file_dialog = None
                    else:
                        original_path = pathlib.Path(result[0]).resolve()
                        path = original_path
                        if self._dialog_operation == "export":
                            path = path.with_suffix(".py")
                        confirmed = getattr(self._file_dialog, "overwrite_confirmed", False) and path == original_path
                        if path.exists() and not confirmed and (self._dialog_operation == "export" or str(path) != self._dialog_document.path):
                            self._overwrite_path = path
                        else:
                            self._finish_save(path)
            if self._dialog_error:
                im.text_wrapped(self._dialog_error)
        im.end()

    def _request_close(self, doc: EditorDocument) -> None:
        if doc not in self.model.documents:
            return
        if doc.is_modified:
            self._pending_close = doc
            im.open_popup("close_document")
        else:
            self.model.close_document(self.model.documents.index(doc))

    def _draw_tab_context(self, width: float, height: float) -> None:
        from emtk.im_core import get_current_context

        doc = self._tab_context
        if doc not in self.model.documents:
            self._tab_context = None
            return
        ctx = get_current_context()
        x, y = self._tab_context_pos
        box = (max(0.0, min(x, width - 240.0)), max(0.0, min(y, height - 130.0)), 240.0, 130.0)
        mx, my = ctx.io.mouse_pos
        if (ctx.io.mouse_clicked[0] or ctx.io.mouse_clicked[1]) and not (
            box[0] <= mx < box[0] + box[2] and box[1] <= my < box[1] + box[3]
        ):
            self._tab_context = None
            return
        ctx.begin("##document_tab_menu", box)
        if im.menu_item("Save document"):
            self._request_save(doc)
            self._tab_context = None
        im.set_item_tooltip('Save document')
        if im.menu_item("Save document as…"):
            self._request_save(doc, save_as=True)
            self._tab_context = None
        im.set_item_tooltip("Save this document to a chosen destination")
        if im.menu_item("Close document"):
            self._request_close(doc)
            self._tab_context = None
        im.set_item_tooltip('Close document')
        if im.menu_item("Copy file path", enabled=bool(doc.path)):
            im.set_clipboard_text(doc.path)
            self._tab_context = None
        im.set_item_tooltip('Copy file path')
        ctx.end()

    def _draw_file_tree(self, box: tuple[float, float, float, float]) -> None:
        """Render project directory files in an immediate-mode tree with filtering and scrolling."""
        im.text_disabled(f"Root: {self.model.project_root.name}")
        self._project_context_menu(self.model.project_root)
        if self.model.recent_files:
            if im.small_button("Recent files"):
                im.open_popup("recent_files")
            im.set_item_tooltip("Reopen a recently opened or saved document")
            if im.begin_popup("recent_files"):
                for index, path in enumerate(self.model.recent_files):
                    if im.menu_item(f"{path}##recent_{index}"):
                        self.model.open_file(path)
                        im.close_current_popup()
                    im.set_item_tooltip(path)
                im.end_popup()
        if self.model.project_root.parent != self.model.project_root:
            if im.small_button("↑ Parent"):
                self.model.project_root = self.model.project_root.parent
            im.set_item_tooltip('↑ Parent')

        avail_w = box[2]
        im.set_next_item_width(avail_w)
        _, self.file_filter = im.input_text("##file_filter", self.file_filter, hint="🔍 Filter files...")
        im.set_item_tooltip("Filter project files by name")
        im.separator()

        def _file_icon(name: str) -> str:
            low = name.lower()
            if low.endswith(".py"):
                return "🐍"
            if low.endswith((".json", ".toml", ".yaml", ".yml")):
                return "⚙️"
            if low.endswith((".md", ".txt", ".rst")):
                return "📝"
            if low.endswith((".png", ".jpg", ".jpeg", ".svg")):
                return "🖼️"
            if low.endswith((".h5", ".dat", ".csv", ".tsv", ".npz", ".npy")):
                return "📊"
            return "📄"

        curr_y = im.get_cursor_screen_pos()[1]
        avail_h = max(20.0, box[1] + box[3] - curr_y)
        im.begin_child((*im.get_cursor_screen_pos(), avail_w, avail_h))

        def draw_directory(directory: pathlib.Path) -> None:
            for entry in self._project_entries(directory):
                im.push_id(str(entry))
                if entry.is_dir() and not entry.is_symlink():
                    expanded = im.tree_node(f"📁 {entry.name}")
                    im.set_item_tooltip(str(entry))
                    self._project_context_menu(entry)
                    # Double-click promotes the folder to the project root,
                    # matching the context-menu action.
                    double_clicked = (im.is_item_hovered()
                                      and im.is_mouse_double_clicked(0))
                    if expanded:
                        draw_directory(entry)
                        im.tree_pop()
                    if double_clicked:
                        self.model.project_root = entry
                        return
                else:
                    active = self.model.active_doc
                    selected = bool(active and active.path == str(entry.resolve()))
                    if im.selectable(f"{_file_icon(entry.name)} {entry.name}", selected):
                        self.model.open_file(entry)
                    im.set_item_tooltip(str(entry))
                    self._project_context_menu(entry)
                im.pop_id()

        try:
            draw_directory(self.model.project_root)
        except Exception as e:
            im.text_colored((240, 100, 100, 255), f"Error listing files: {e}")

        im.end_child()

    def _project_entries(self, directory: pathlib.Path) -> list[pathlib.Path]:
        """Keep matching ancestor directories while avoiding symlink recursion."""
        query = self.file_filter.strip().lower()
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return []
        return [entry for entry in entries if not entry.name.startswith(".") and (
            not query or query in entry.name.lower() or (
                entry.is_dir() and not entry.is_symlink() and self._project_entries(entry)
            )
        )]

    def _project_context_menu(self, entry: pathlib.Path) -> None:
        if im.begin_popup_context_item(f"project_context_{entry}"):
            if entry.is_file() and im.menu_item("Open in editor"):
                self.model.open_file(entry)
                im.close_current_popup()
            im.set_item_tooltip('Open in editor')
            if entry.is_dir() and im.menu_item("Use as project root"):
                self.model.project_root = entry
                self.file_filter = ""
                im.close_current_popup()
            im.set_item_tooltip('Use as project root')
            if im.menu_item("Copy full path"):
                im.set_clipboard_text(str(entry.resolve()))
                im.close_current_popup()
            im.set_item_tooltip('Copy full path')
            if im.menu_item("Copy relative path"):
                im.set_clipboard_text(os.path.relpath(entry, self.model.project_root))
                im.close_current_popup()
            im.set_item_tooltip('Copy relative path')
            im.end_popup()

    def _draw_editor_tabs(self, box: tuple[float, float, float, float]) -> None:
        """Render editor tab bar, toolbar, active TextEditor widget, and status bar."""
        # Clicking this dock makes its selected document the public active buffer.
        io = im.get_io()
        mx, my = io.mouse_pos
        if io.mouse_clicked[0] and box[0] <= mx < box[0] + box[2] and box[1] <= my < box[1] + box[3]:
            self.model._sync_document_store(activate=True)
        # Menu bar: full commands; the icon row below stays one line tall.
        active_doc = self.model.active_doc
        notebook_running = any(doc.notebook is not None and doc.notebook.is_running for doc in self.model.documents)
        if im.begin_main_menu_bar():
            if im.begin_menu("File"):
                if im.menu_item("New"):
                    self.model.new_document()
                if im.menu_item("Open…"):
                    self._request_open()
                if im.menu_item("Save"):
                    self._request_save(self.model.active_doc)
                if im.menu_item("Save As…"):
                    self._request_save(self.model.active_doc, save_as=True)
                if self.model.documents and im.menu_item("Close"):
                    self._request_close(self.model.active_doc)
                im.separator()
                if im.menu_item("Settings…"):
                    self.settings_open = True
                    self.docks.focus("editor_settings")
                im.end_menu()
            if im.begin_menu("Run"):
                if self.model.is_running_script or notebook_running:
                    if im.menu_item("Stop"):
                        self.model.stop_active_script()
                elif im.menu_item("Run Script"):
                    self.model.run_active_script()
                im.separator()
                if im.menu_item("Ruff Check"):
                    self.model.start_ruff()
                if im.menu_item("Ruff Fix"):
                    self.model.start_ruff(fix=True)
                im.end_menu()
            if im.begin_menu("Notebook"):
                if im.menu_item("New notebook"):
                    self.model.new_document("Untitled.ipynb")
                nb = active_doc.notebook if active_doc is not None else None
                if nb is not None:
                    im.separator()
                    if im.menu_item("Run all"):
                        nb.run_all()
                    if im.menu_item("Clear outputs"):
                        nb.clear_outputs()
                    if im.menu_item("Restart shell"):
                        nb.restart_shell()
                    if im.menu_item("Reload notebook"):
                        self._request_reload(active_doc)
                    if im.menu_item("Export Python"):
                        self._request_export_notebook(active_doc)
                im.end_menu()
            if im.begin_menu("View"):
                if im.menu_item("Increase font size"):
                    self.model.font_scale = min(3.0, self.model.font_scale + 0.1)
                if im.menu_item("Decrease font size"):
                    self.model.font_scale = max(0.6, self.model.font_scale - 0.1)
                im.end_menu()
            if im.begin_menu("Help"):
                if im.menu_item("Editor settings…"):
                    self.settings_open = True
                    self.docks.focus("editor_settings")
                im.end_menu()
            im.end_main_menu_bar()

        # Slim action row: small buttons, one line tall, an emoticon beside
        # each label the way the Qt toolbar had icons beside text. Default
        # frame style -- the rounding that made them read as tiles is gone.
        if im.button("➕ New"):
            self.model.new_document()
        im.set_item_tooltip("New — create an empty document")
        im.same_line()
        if im.button("📂 Open"):
            self._request_open()
        im.set_item_tooltip("Open… — choose files to open in the editor")
        im.same_line()
        if im.button("💾 Save"):
            self._request_save(self.model.active_doc)
        im.set_item_tooltip("Save — save the active document to disk")
        im.same_line()
        if im.button("📝 Save As"):
            self._request_save(self.model.active_doc, save_as=True)
        im.set_item_tooltip("Save As… — save the active document under a chosen name")
        if self.model.documents:
            im.same_line()
            if im.button("✖ Close"):
                self._request_close(self.model.active_doc)
            im.set_item_tooltip("Close — close the active document; ask before discarding changes")
        im.same_line()
        if self.model.is_running_script or notebook_running:
            im.push_style_color(Col.BUTTON, (160, 60, 60, 255))
            if im.button("■ Stop"):
                self.model.stop_active_script()
            im.set_item_tooltip("Stop — stop the running script subprocess")
            im.pop_style_color()
        else:
            im.push_style_color(Col.BUTTON, (46, 140, 67, 255))
            if im.button("▶ Run"):
                self.model.run_active_script()
            im.set_item_tooltip("Run Script — run the active Python document and display its output")
            im.pop_style_color()
        im.same_line()
        im.set_next_item_width(150.0)
        changed, endpoint = im.combo("##run_endpoint", 1 if self.model.run_endpoint == "console" else 0,
            ["Separate process", "In ChiSurf console"])
        im.set_item_tooltip("Process: isolated, stoppable execution. Console: main-thread macros with access to ChiSurf state; long macros block interaction.")
        if changed:
            self.model.run_endpoint = "console" if endpoint == 1 else "process"
        im.same_line()
        if im.button("🧹 Check"):
            self.model.start_ruff()
        im.set_item_tooltip("Ruff Check — check the unsaved Python buffer using the optional Ruff executable")
        im.same_line()
        if im.button("🛠 Fix"):
            self.model.start_ruff(fix=True)
        im.set_item_tooltip("Ruff Fix — apply Ruff's safe fixes to the unsaved buffer; save explicitly afterwards")
        im.same_line()
        if im.button("📓 Notebook"):
            self.model.new_document("Untitled.ipynb")
        im.set_item_tooltip("New notebook — create an empty notebook with editable cells and a persistent ChiSurf shell")
        im.same_line()
        if im.button("⚙ Settings"):
            self.settings_open = True
            self.docks.focus("editor_settings")
        im.set_item_tooltip("Settings… — open the native editor appearance and diagnostics settings")
        symbols = self.model.document_symbols()
        if symbols:
            im.set_next_item_width(max(120.0, box[2]))
            changed, selected = im.combo("##python_symbol", 0, ["Jump to symbol…"] +
                [f"{symbol.display_name} · line {symbol.line}" for symbol in symbols])
            im.set_item_tooltip("Jump to a class, function, method or section in the unsaved Python source")
            if changed and selected > 0:
                symbol = symbols[selected - 1]
                self.model.goto_line(symbol.line, symbol.column)
        im.separator()
        if im.begin_popup("close_document"):
            pending = self._pending_close
            if pending in self.model.documents:
                im.text_wrapped(f"Save changes to {pending.name} before closing?")
                index = self.model.documents.index(pending)
                if im.button("Save and close"):
                    self._request_save(pending, close_after=True)
                    im.close_current_popup()
                im.set_item_tooltip('Save and close')
                if im.button("Discard changes"):
                    self.model.close_document(index)
                    im.close_current_popup()
                im.set_item_tooltip('Discard changes')
                if im.button("Cancel"):
                    im.close_current_popup()
                im.set_item_tooltip('Cancel')
            im.end_popup()

        if not self.model.documents:
            im.dummy(0.0, 40.0)
            im.text_disabled("No open documents. Click 'New' or pick a file on the left.")
            return

        # Tab bar
        if im.begin_tab_bar("editor_tabs"):
            requested_doc = self.model.active_doc
            request_activation = requested_doc is not self._displayed_doc
            for doc in list(self.model.documents):
                modified_marker = "*" if doc.is_modified else ""
                tab_title = f"  {doc.name}{modified_marker}  ###tab_{id(doc)}"
                flags = im.TabItemFlags.SET_SELECTED if request_activation and doc is requested_doc else 0
                if im.begin_tab_item(tab_title, flags=flags, on_close=lambda doc=doc: self._request_close(doc)):
                    if doc in self.model.documents:
                        self.model.active_index = self.model.documents.index(doc)
                    im.end_tab_item()
                im.set_item_tooltip(f"{doc.path or doc.name} — right-click for document actions")
                if im.is_item_hovered() and im.is_mouse_clicked(1):
                    from emtk.im_core import get_current_context

                    self._tab_context = doc
                    self._tab_context_pos = get_current_context().io.mouse_pos
            im.end_tab_bar()

        active = self.model.active_doc
        self._displayed_doc = active
        if active:
            avail_w = box[2]
            curr_y = im.get_cursor_screen_pos()[1]
            status_bar_h = 22.0
            editor_h = max(60.0, box[1] + box[3] - curr_y - status_bar_h)
            self.model.apply_editor_preferences(active.editor, apply_language=active.notebook is None)
            im.push_font({"family": self.model.font_family, "size": self.model.font_size})
            im.push_font_scale(self.model.font_scale * CODE_EDITOR_UI_SCALE)
            if active.notebook is not None:
                for cell in active.notebook.cells:
                    self.model.apply_editor_preferences(cell.editor, apply_language=False)
                active.notebook.draw(avail_w, editor_h,
                    on_reload=lambda: self._request_reload(active),
                    on_export=lambda: self._request_export_notebook(active),
                    ui_scale=CODE_EDITOR_UI_SCALE * self.model.font_scale,
                )
            else:
                im.text_editor(f"##editor_{id(active)}", active.editor, (avail_w, editor_h))
                im.set_item_tooltip("Edit the active document; use standard keyboard shortcuts for editing")
            im.pop_font_scale()
            im.pop_font()

            # Editor status bar
            im.separator()
            cur_line, cur_col = 1, 1
            try:
                if hasattr(active.editor, "cursors") and active.editor.cursors:
                    cur_line = active.editor.cursors.main.end.line + 1
                    cur_col = active.editor.cursors.main.end.index + 1
            except Exception:
                pass
            path_label = active.path if active.path else "Untitled"
            state = "Modified" if active.is_modified else ("Saved" if active.path else "Unsaved")
            im.text_disabled(f"{path_label}  ·  Ln {cur_line}, Col {cur_col}  |  UTF-8  |  {state}")

    def _draw_output_console(self, box: tuple[float, float, float, float]) -> None:
        """Render the execution logs and output terminal."""
        if im.button("🗑 Clear"):
            self.model.output_logs.clear()
        im.set_item_tooltip('🗑 Clear')
        im.same_line()
        if im.button("📋 Copy"):
            try:
                from emtk.clipboard import set_clipboard_text
                set_clipboard_text("\n".join(self.model.output_logs))
            except Exception:
                pass
        im.set_item_tooltip('📋 Copy')
        im.same_line()
        im.text_disabled(f"  {len(self.model.output_logs)} lines")
        im.separator()

        avail_w = box[2]
        curr_y = im.get_cursor_screen_pos()[1]
        avail_h = max(20.0, box[1] + box[3] - curr_y)
        im.begin_child((*im.get_cursor_screen_pos(), avail_w, avail_h))
        for line in self.model.output_logs:
            lower = line.lower()
            if any(k in lower for k in ("error", "exception", "traceback", "failed")):
                im.text_colored((245, 110, 110, 255), line)
            elif line.startswith("--- Running") or line.startswith("--- Process finished"):
                im.text_colored((110, 195, 255, 255), line)
            elif any(k in lower for k in ("saved", "success", "complete")):
                im.text_colored((130, 220, 140, 255), line)
            else:
                im.text_wrapped(line)
        im.end_child()

    def _draw_diagnostics(self, box: tuple[float, float, float, float]) -> None:
        doc = self.model.active_doc
        if self.model._ruff_running:
            im.text_disabled("Ruff is checking the document…")
        if doc is None or not (doc.diagnostics or doc.lsp_diagnostics):
            im.text_disabled("No diagnostics. Run Ruff Check on a Python document.")
            return
        im.begin_child((*im.get_cursor_screen_pos(), box[2], box[3]), child_id="ruff_diagnostics")
        for index, diagnostic in enumerate(doc.diagnostics + doc.lsp_diagnostics):
            line = diagnostic.get("line", 1)
            label = f"{diagnostic.get('code', '')}: {diagnostic.get('message', '')} (line {line})##diagnostic_{index}"
            if im.selectable(label):
                self.model.goto_line(line, diagnostic.get("column", 0))
            im.set_item_tooltip("Jump to the diagnostic's source location")
        im.end_child()

    def _draw_settings_window(self) -> None:
        """Keep the settings_open mirror in sync with the dock visibility.

        The panel is a dockable window now (registered as ``editor_settings``),
        not a modal overlay.
        """
        # A False mirror forces the panel closed (Close settings button);
        # a tab click or the dock's own close button rules otherwise — the
        # mirror follows the dock so the user stays in control.
        shown = self.docks.is_shown("editor_settings")
        if not self.settings_open and shown:
            self.docks.hide("editor_settings")
        self.settings_open = self.docks.is_shown("editor_settings")

    def _draw_settings_content(self, box=None) -> None:
        """The settings panel body, docked like the other editor panels."""
        if im.button("Apply & Save"):
            if self.save_preferences is not None and self.save_preferences():
                self.settings_status = "Editor settings saved."
            else:
                self.settings_status = "Could not save editor settings."
        im.set_item_tooltip("Apply and persist the declared editor preferences; no buffers or credentials are saved")
        im.same_line()
        if im.button("Close settings"):
            self.settings_open = False
            self.docks.hide("editor_settings")
            self.docks.hide("editor_settings")
        im.set_item_tooltip("Close this configuration panel")
        if self.settings_status:
            im.text_wrapped(self.settings_status)
        im.begin_child((*im.get_cursor_screen_pos(), *im.get_content_region_avail()), child_id="editor_settings_fields")
        self._draw_settings_panel()
        im.end_child()


    def _draw_settings_panel(self) -> None:
        languages = list(LANGUAGES)
        changed, selected = im.combo("Syntax language", languages.index(self.model.language), languages)
        im.set_item_tooltip("Choose highlighting or Auto to follow each document's file extension")
        if changed:
            self.model.language = languages[selected]
        families = list(font_choices())
        family_index = families.index(self.model.font_family) if self.model.font_family in families else 0
        changed, selected = im.combo("Font family", family_index, families)
        im.set_item_tooltip("Select an available monospaced font supported by the native renderer")
        if changed:
            self.model.font_family = families[selected]
        changed, size = im.slider_int("Font size (pt)", self.model.font_size, 0, 72)
        im.set_item_tooltip("Point size; 0 preserves the native baked font's default metrics")
        if changed:
            self.model.font_size = size
        schemes = list(COLOR_SCHEMES)
        changed, selected = im.combo("Color scheme", schemes.index(self.model.color_scheme), schemes)
        im.set_item_tooltip("Apply a preset editor palette, background, margins, selection and current-line colors")
        if changed:
            self.model.set_color_scheme(schemes[selected])
        for name, label in [("paper_color", "Paper"), ("default_color", "Text"), ("margins_background_color", "Margins"),
            ("marker_background_color", "Selection / marker"), ("caret_line_background_color", "Current line")]:
            color = rgba(self.model.display_colors[name])
            changed, value = im.color_edit3(label, color[:3])
            im.set_item_tooltip("Choose the editor color without changing the application's global theme")
            if changed:
                self.model.set_display_color(name, "#" + "".join(f"{max(0, min(255, int(channel))):02x}" for channel in value[:3]))
        changed, value = im.checkbox("Highlight current line", self.model.caret_line_visible)
        im.set_item_tooltip("Show or hide the configured background behind the caret's line")
        if changed:
            self.model.caret_line_visible = value
        changed, enabled = im.checkbox("Enable Ruff", self.model.enable_ruff)
        im.set_item_tooltip("Enable optional Ruff checks and fixes for editor buffers")
        if changed:
            self.model.enable_ruff = enabled
        changed, enabled = im.checkbox("Ruff after save", self.model.run_ruff_on_save)
        im.set_item_tooltip("Check the active document asynchronously after a successful save")
        if changed:
            self.model.run_ruff_on_save = enabled
        changed, timeout = im.slider_int("Ruff timeout (ms)", self.model.ruff_timeout_ms, 1000, 60000)
        im.set_item_tooltip("Maximum time allowed for the optional Ruff subprocess")
        if changed:
            self.model.ruff_timeout_ms = timeout
        changed, arguments = im.input_text("Ruff extra arguments", shlex.join(self.model.ruff_extra_args))
        im.set_item_tooltip("Extra Ruff command arguments; quoted values are supported")
        if changed:
            try:
                self.model.ruff_extra_args = shlex.split(arguments)
            except ValueError:
                self.model.log_output("Ruff arguments have an unterminated quote.")
        im.separator()
        changed, scale = im.slider_float("Text zoom", self.model.font_scale, 0.5, 3.0)
        im.set_item_tooltip("Adjust editor text size; saved as a native preference")
        if changed:
            self.model.font_scale = scale
        for label, name in [("Line numbers", "show_line_numbers"), ("Show whitespace", "show_whitespace"), ("Spaces for tabs", "insert_spaces")]:
            changed, value = im.checkbox(label, getattr(self.model, name))
            im.set_item_tooltip("Configure how editor source is displayed and indented")
            if changed:
                setattr(self.model, name, value)
        changed, size = im.slider_int("Tab width", self.model.tab_size, 1, 16)
        im.set_item_tooltip("Number of columns used for tab indentation")
        if changed:
            self.model.tab_size = size
        im.separator()
        im.begin_disabled(self.model.enable_rpc)
        _, self.model.rpc_host = im.input_text("RPC host", self.model.rpc_host)
        im.set_item_tooltip("Loopback host for the editor's optional JSON-RPC service")
        _, self.model.rpc_cmd_port = im.input_int("RPC command port", self.model.rpc_cmd_port)
        im.set_item_tooltip("Command port used by editor RPC clients")
        _, self.model.rpc_pub_port = im.input_int("RPC event port", self.model.rpc_pub_port)
        im.set_item_tooltip("Event port used by editor RPC clients")
        im.end_disabled()
        changed, enabled = im.checkbox("Enable editor RPC", self.model.enable_rpc)
        im.set_item_tooltip("Expose open-buffer operations through the existing local ZeroMQ service")
        if changed:
            self.model.start_rpc() if enabled else self.model.stop_rpc()
        im.text_wrapped(self.model.rpc_status)
        im.separator()

    def _draw_lsp(self, box) -> None:
        if im.button("Editor settings…"):
            self.settings_open = True
            self.docks.focus("editor_settings")
        im.set_item_tooltip("Configure font, colors, language, editing behavior, Ruff and the editor RPC service")
        im.text_wrapped(self.model.lsp_status)
        if self.model.lsp_client is None:
            if im.button("Enable Python LSP"):
                self.model.start_lsp()
            im.set_item_tooltip("Start an installed optional python-lsp-server; no packages are installed automatically")
        else:
            if im.button("Disable Python LSP"):
                self.model.stop_lsp()
            im.set_item_tooltip("Stop the language server and close its document sessions")
        for action, label, tip in [("completion", "Complete", "Ask for completions at the active editor cursor"),
            ("definition", "Go to definition", "Open the Python definition at the active cursor"),
            ("hover", "Documentation", "Show language-server documentation for the active cursor")]:
            if im.button(label):
                self.model.request_lsp(action)
            im.set_item_tooltip(tip)
        if self.model.hover_text:
            im.markdown(self.model.hover_text, max_width=box[2])
        for index, item in enumerate(self.model.completions):
            if im.selectable(f"{item.get('label', '')}##completion_{index}"):
                self.model.apply_completion(item)
            documentation = item.get("documentation", item.get("detail", "Apply this completion"))
            im.set_item_tooltip(documentation.get("value", "") if isinstance(documentation, dict) else str(documentation))

    def _draw_agent_panel(self, box: tuple[float, float, float, float]) -> None:
        """Render embedded EMTK AI Assistant chat panel."""
        self.chat_gui.draw(box[2], box[3])


class CodeEditorApp(ImApp):
    """EMTK Application for the complete Code Editor."""

    def __init__(self, project_root: str | pathlib.Path | None = None) -> None:
        self.model = EditorModel(project_root=project_root)
        self.editor_gui = CodeEditorGui(model=self.model)
        super().__init__(gui=self._render, continuous=False)
        self.model.request_frame = self.request_frame
        self.editor_gui.save_preferences = self.save_preferences

    def save_preferences(self) -> bool:
        from chisurf.emtk.state import save_settings
        return save_settings(getattr(self, "_native_state_id", "code_editor"), self.export_settings())

    def export_settings(self) -> dict:
        return {**self.model.export_settings(), "assistant": self.editor_gui.chat_model.export_settings()}

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)
        if isinstance(settings.get("assistant"), dict):
            self.editor_gui.chat_model.restore_settings(settings["assistant"])

    def close(self) -> None:
        self.model.close()
        self.editor_gui.chat_model.close()
        if self.editor_gui.chat_gui.provider_settings is not None:
            self.editor_gui.chat_gui.provider_settings.close()

    def animating(self) -> bool:
        if self.model._closed:
            return False
        return (super().animating() or self.model.is_running_script or self.model._ruff_running
            or not self.model.event_queue.empty() or self.editor_gui.chat_model.is_generating
            or not self.editor_gui.chat_model.event_queue.empty()
            or any(doc.notebook is not None and doc.notebook.is_running for doc in self.model.documents)
            or (self.editor_gui.chat_gui.provider_settings is not None and self.editor_gui.chat_gui.provider_settings.busy))

    def next_frame_in(self) -> float | None:
        delay = super().next_frame_in()
        if getattr(self, "_frame_request_callback", None) is None and not self.model._closed:
            # A manual embedding can still pump queued work without mouse motion.
            return min(delay, 0.2) if delay is not None else 0.2
        return delay

    def _render(self) -> None:
        im.push_font_scale(CODE_EDITOR_UI_SCALE)
        try:
            self.editor_gui.draw()
        finally:
            im.pop_font_scale()
        self.model._sync_document_store()


def make_editor_app(project_root: str | None = None) -> CodeEditorApp:
    """Factory for pure EMTK execution (e.g. via emtk.native or emtk.web)."""
    return CodeEditorApp(project_root=project_root)


def main() -> None:
    """Run Code Editor directly via pure EMTK without Qt."""
    from emtk.native import main as emtk_main

    emtk_main(["--app", "chisurf.plugins.core.code_editor.gui.editor_app:make_editor_app", "--size", "1200x800"])


if __name__ == "__main__":
    main()
