"""Native notebook cells and persistent ChiSurf shell, without Qt or Jupyter."""
from __future__ import annotations

import base64
import builtins
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import traceback
import uuid
from typing import Any
from urllib.parse import unquote, unquote_to_bytes, urlparse

from emtk import im
from emtk.texture import Texture
from emtk.widgets.text_editor import Language, TextEditor

from .html_output import html_blocks

SHELL_EXECUTION_LOCK = threading.Lock()

def _source(value: Any) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def _json_mime_data(data: dict) -> dict:
    """Normalize display formatter bytes to notebook-safe MIME strings."""
    normalized = {}
    for mime, value in data.items():
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
            is_text = (
                mime.startswith("text/")
                or mime == "image/svg+xml"
                or mime.endswith(("+json", "+xml"))
                or mime in {"application/json", "application/xml"}
            )
            value = (
                raw.decode("utf-8", errors="replace")
                if is_text
                else base64.b64encode(raw).decode("ascii")
            )
        normalized[mime] = value
    return normalized


class NativeCell:
    def __init__(self, node: dict) -> None:
        self.node = copy.deepcopy(node)
        self.node.setdefault("id", uuid.uuid4().hex[:8])
        self.cell_type = node.get("cell_type", "code")
        self.editor = TextEditor(_source(node.get("source")), language=Language.python() if self.cell_type == "code" else None)
        self._source = self.editor.text
        self.outputs = copy.deepcopy(node.get("outputs", []))
        self.execution_count = node.get("execution_count")
        self.edit_markdown = False
        self._textures: dict[str, Texture] = {}
        self._html_cache: dict[str, list] = {}

    def to_dict(self) -> dict:
        node = copy.deepcopy(self.node)
        node["cell_type"] = self.cell_type
        node.setdefault("id", uuid.uuid4().hex[:8])
        node.setdefault("metadata", {})
        if self.editor.text != self._source or "source" not in node:
            node["source"] = self.editor.text
        if self.cell_type == "code":
            node["outputs"] = copy.deepcopy(self.outputs)
            node["execution_count"] = self.execution_count
        else:
            node.pop("outputs", None)
            node.pop("execution_count", None)
        return node

    def set_type(self, cell_type: str) -> None:
        self.cell_type = cell_type
        self.editor.set_language(Language.python() if cell_type == "code" else None)


class NativeNotebook:
    def __init__(self, data: dict, path: str | None = None) -> None:
        if not isinstance(data, dict) or data.get("nbformat") != 4 or not isinstance(data.get("cells"), list):
            raise ValueError("Expected a version 4 notebook with a cells list")
        if any(not isinstance(cell, dict) or cell.get("cell_type") not in ("code", "markdown", "raw") for cell in data["cells"]):
            raise ValueError("Notebook contains an invalid cell")
        self.data = copy.deepcopy(data)
        self.cells = [NativeCell(node) for node in data["cells"]]
        self.path = path
        self.active_index = 0
        self.shell = None
        self._active_cell: NativeCell | None = None
        self.terminal_output: list[str] = []
        self.terminal_input = ""
        self.show_terminal = False
        self.error = ""
        self.is_running = False
        self._closed = False
        self._cancelled = threading.Event()
        self._execution_thread: threading.Thread | None = None
        self.pending_input: dict | None = None
        self.input_response = ""
        self._change_revision = 0
        self._serialized_revision = None
        self._serialized_value = ""
        self._pending_advance: int | None = None
        if not self.cells:
            self.add_cell()

    @classmethod
    def from_json(cls, content: str, path: str | None = None):
        return cls(json.loads(content), path)

    @classmethod
    def new(cls):
        return cls({"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "language": "python", "display_name": "Python 3"}, "language_info": {"name": "python"}},
            "cells": [{"id": uuid.uuid4().hex[:8], "cell_type": "code", "metadata": {}, "source": "", "outputs": [], "execution_count": None}]})

    @property
    def active_cell(self) -> NativeCell:
        self.active_index = max(0, min(self.active_index, len(self.cells) - 1))
        return self.cells[self.active_index]

    def to_dict(self) -> dict:
        data = copy.deepcopy(self.data)
        data["cells"] = [cell.to_dict() for cell in self.cells]
        return data

    def dumps(self) -> str:
        revision = (self._change_revision, tuple((id(cell), cell.cell_type, cell.editor.revision,
            cell.execution_count, len(cell.outputs)) for cell in self.cells))
        if revision != self._serialized_revision:
            self._serialized_value = json.dumps(self.to_dict(), indent=1, ensure_ascii=False) + "\n"
            self._serialized_revision = revision
        return self._serialized_value

    def add_cell(self, cell_type: str = "code", source: str = "", index: int | None = None) -> NativeCell:
        if self.is_running:
            self.error = "Stop notebook execution before adding cells."
            return self.active_cell
        cell = NativeCell({"id": uuid.uuid4().hex[:8], "cell_type": cell_type, "metadata": {}, "source": source})
        position = len(self.cells) if index is None else max(0, min(index, len(self.cells)))
        self.cells.insert(position, cell)
        self.active_index = position
        return cell

    def move_cell(self, index: int, direction: int) -> None:
        if self.is_running:
            self.error = "Stop notebook execution before changing its cells or outputs."
            return
        target = index + direction
        if 0 <= index < len(self.cells) and 0 <= target < len(self.cells):
            cell = self.active_cell
            self.cells[index], self.cells[target] = self.cells[target], self.cells[index]
            self.active_index = self.cells.index(cell)

    def remove_cell(self, index: int) -> None:
        if self.is_running:
            self.error = "Stop notebook execution before changing its cells or outputs."
            return
        if 0 <= index < len(self.cells):
            active = self.active_cell
            self.cells.pop(index)
            if not self.cells:
                self.add_cell()
            self.active_index = self.cells.index(active) if active in self.cells else min(index, len(self.cells) - 1)

    def clear_outputs(self) -> None:
        if self.is_running:
            self.error = "Stop notebook execution before changing its cells or outputs."
            return
        self._change_revision += 1
        for cell in self.cells:
            cell.outputs.clear()
            cell.execution_count = None
            cell._textures.clear()
            cell._html_cache.clear()

    def close(self) -> None:
        self._closed = True
        self.cancel_execution()
        if getattr(getattr(builtins, "get_ipython", None), "__self__", None) is self.shell and self.shell is not None:
            del builtins.get_ipython
        self.shell = None

    def restart_shell(self) -> None:
        if self.is_running:
            self.error = "Stop the running cell before restarting its shell."
            return
        self.close()
        self._closed = False
        self._cancelled.clear()
        self.terminal_output.append("Shell restarted; variables and execution count reset.")

    def reload(self, content: str) -> None:
        if self.is_running:
            raise RuntimeError("Stop notebook execution before reloading")
        replacement = NativeNotebook.from_json(content, self.path)
        self.data, self.cells = replacement.data, replacement.cells
        self._change_revision += 1
        self.active_index = 0

    def export_python(self) -> str:
        parts = []
        for cell in self.cells:
            if cell.cell_type == "code":
                parts.append("# %%\n" + cell.editor.text)
            else:
                parts.append(f"# %% [{cell.cell_type}]\n" + "\n".join("# " + line for line in cell.editor.text.splitlines()))
        return "\n\n".join(parts) + "\n"

    def _read_input(self, prompt: str, password: bool = False) -> str:
        if self._closed or self._cancelled.is_set():
            raise KeyboardInterrupt("Notebook execution cancelled")
        ready = threading.Event()
        request = {"prompt": prompt or "Input:", "password": password, "ready": ready, "response": ""}
        if prompt:
            self._write("stdout", prompt)
        self.input_response = ""
        self.pending_input = request
        ready.wait()
        if self._closed or self._cancelled.is_set():
            raise KeyboardInterrupt("Notebook execution cancelled")
        return request["response"]

    def respond_input(self, value: str) -> None:
        request = self.pending_input
        if request is not None:
            request["response"] = value
            self.pending_input = None
            request["ready"].set()

    def cancel_execution(self) -> None:
        self._cancelled.set()
        if self.pending_input is not None:
            self.respond_input("")

    def _start_execution(self, action) -> bool:
        if self.is_running or self._closed:
            self.error = "Notebook is busy or closed."
            return False
        self.error = ""
        self._cancelled.clear()
        self.is_running = True
        def execute() -> None:
            def trace(frame, event, arg):
                if self._cancelled.is_set() and frame.f_code.co_filename.startswith(self.path or "Untitled.ipynb"):
                    raise KeyboardInterrupt("Notebook execution cancelled")
                return trace
            try:
                sys.settrace(trace)
                action()
            except Exception as error:
                self.error = str(error)
            finally:
                sys.settrace(None)
                self.is_running = False
        self._execution_thread = threading.Thread(target=execute, daemon=True)
        self._execution_thread.start()
        return True

    def start_cell(self, index: int) -> bool:
        return self._start_execution(lambda: self.run_cell(index))

    def run_and_advance(self, index: int) -> bool:
        """Run one cell, then focus the following cell (creating one at EOF)."""
        if not self.start_cell(index):
            return False
        self._pending_advance = index + 1
        return True

    def _finish_pending_advance(self) -> None:
        if self._pending_advance is None or self.is_running:
            return
        index, self._pending_advance = self._pending_advance, None
        if index >= len(self.cells):
            cell = self.add_cell("code", index=len(self.cells))
        else:
            self.active_index = index
            cell = self.cells[index]
        from emtk.im_core import get_current_context

        get_current_context().state(("focus",))["notebook_focus_cell"] = cell.node.get("id")

    @staticmethod
    def _take_cell_shortcut(context, *, shift_only: bool) -> bool:
        """Consume Shift+Enter or Ctrl+Enter only while a cell editor is focused."""
        item_id = context.get_id("##cell_source")
        if context.state(("focus",)).get("id") != item_id and not context.is_nav_focused(item_id):
            return False
        from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER

        io = context.io
        events = list(io.key_events)
        if not events and (io.key or io.text):
            modifiers = ((SHIFT_MODIFIER if io.key_shift else 0)
                         | (CONTROL_MODIFIER if io.key_ctrl else 0))
            events = [(io.key, io.text, modifiers)]
        for index, (key, _text, modifiers) in enumerate(events):
            if key not in (13, 0x01000004, 0x01000005):
                continue
            shift = bool(modifiers & SHIFT_MODIFIER)
            control = bool(modifiers & CONTROL_MODIFIER)
            if shift_only and not (shift and not control):
                continue
            if not shift_only and not (control and not shift):
                continue
            if io.key_events:
                io.key_events.pop(index)
            if io.key == key:
                io.key = 0
                io.text = ""
            return True
        return False

    def start_all(self) -> bool:
        return self._start_execution(self.run_all)

    def start_terminal(self, source: str) -> bool:
        return self._start_execution(lambda: self.run_terminal(source))

    def _write(self, name: str, text: str) -> None:
        if self._active_cell is None:
            self.terminal_output.append(text)
            return
        self._change_revision += 1
        outputs = self._active_cell.outputs
        if outputs and outputs[-1].get("output_type") == "stream" and outputs[-1].get("name") == name:
            outputs[-1]["text"] += text
        else:
            outputs.append({"output_type": "stream", "name": name, "text": text})

    def _display(self, data: dict, metadata: dict, kind: str, count: int | None) -> None:
        if self._active_cell is None:
            self.terminal_output.append(_source(data.get("text/plain", "")))
            return
        output = {
            "output_type": kind,
            "data": _json_mime_data(copy.deepcopy(data)),
            "metadata": copy.deepcopy(metadata),
        }
        if kind == "execute_result":
            output["execution_count"] = count
        self._active_cell.outputs.append(output)
        self._change_revision += 1

    def _ensure_shell(self):
        if self.shell is None:
            import chisurf
            from chisurf.core.console.history import HistoryManager
            from chisurf.core.console.shell import Shell
            self.shell = Shell(user_ns={"__name__": "__main__", "__file__": self.path or "", "chisurf": chisurf,
                "cs": chisurf.cs, "np": __import__("numpy"), "os": os, "sys": sys},
                write=self._write, display=self._display, read_input=self._read_input, history=HistoryManager(path=False))
            self.shell.user_ns["input"] = lambda prompt="": self._read_input(str(prompt))
            try:
                self.shell.enable_matplotlib("inline")
            except Exception as error:
                self.terminal_output.append(f"Inline plotting unavailable: {error}")
        self.shell.user_ns["__file__"] = self.path or ""
        return self.shell

    def run_cell(self, index: int) -> None:
        with SHELL_EXECUTION_LOCK:
            self._run_cell(index)

    def _run_cell(self, index: int) -> None:
        cell = self.cells[index]
        self.active_index = index
        if cell.cell_type == "markdown":
            cell.edit_markdown = False
            return
        if cell.cell_type != "code":
            return
        cell.outputs.clear()
        cell._textures.clear()
        cell._html_cache.clear()
        self._active_cell = cell
        try:
            shell = self._ensure_shell()
            cell.execution_count = shell.execution_count
            result = shell.run_cell(cell.editor.text, store_history=True, filename=f"{self.path or 'Untitled.ipynb'}#cell-{index + 1}")
            error = result.error_before_exec or result.error_in_exec
            if error is not None:
                cell.outputs.append({"output_type": "error", "ename": type(error).__name__, "evalue": str(error),
                    "traceback": traceback.format_exception(error)})
        except Exception as error:
            cell.outputs.append({"output_type": "error", "ename": type(error).__name__, "evalue": str(error), "traceback": traceback.format_exception(error)})
        finally:
            self._change_revision += 1
            self._active_cell = None

    def run_all(self) -> None:
        for index in range(len(self.cells)):
            if self._cancelled.is_set():
                break
            self.run_cell(index)

    def run_terminal(self, source: str) -> None:
        with SHELL_EXECUTION_LOCK:
            self._run_terminal(source)

    def _run_terminal(self, source: str) -> None:
        if not source.strip():
            return
        self.terminal_output.append(f">>> {source}")
        try:
            self._ensure_shell().run_cell(source, store_history=True, filename=f"{self.path or 'Untitled.ipynb'}#terminal")
        except Exception as error:
            self.terminal_output.append(f"{type(error).__name__}: {error}")

    def _open_link(self, target: str) -> None:
        from chisurf.emtk.doc_links import open_link
        base = pathlib.Path(self.path).parent if self.path else pathlib.Path.cwd()
        open_link(target, base)

    def _draw_html(self, cell: NativeCell, source: str, width: float) -> None:
        blocks = cell._html_cache.get(source)
        if blocks is None:
            blocks = html_blocks(source)
            cell._html_cache[source] = blocks
        for index, (kind, content) in enumerate(blocks):
            if kind == "markdown":
                im.markdown(content, on_link=self._open_link, max_width=width)
            elif kind == "table" and content:
                columns = max(len(row) for row in content)
                widths = [max(im.calc_text_size(row[column] if column < len(row) else "")[0] for row in content) + 24 for column in range(columns)]
                table_width = min(width, sum(widths))
                if im.begin_table(f"html_table_{id(cell)}_{index}", columns, flags=im.TableFlags.BORDERS | im.TableFlags.ROW_BG, size=(table_width, 0)):
                    for column, column_width in enumerate(widths):
                        im.table_setup_column(str(column), flags=im.TableColumnFlags.WIDTH_FIXED,
                            init_width_or_weight=column_width * table_width / max(1, sum(widths)))
                    for row in content:
                        im.table_next_row()
                        for column in range(columns):
                            im.table_next_column()
                            im.markdown(row[column] if column < len(row) else "", on_link=self._open_link)
                    im.end_table()
            elif kind == "image":
                target = content.get("src", "")
                try:
                    if target.startswith("data:"):
                        header, _, payload = target.partition(",")
                        mime = header[5:].split(";", 1)[0]
                        raw = base64.b64decode(payload) if ";base64" in header else unquote_to_bytes(payload)
                    else:
                        parsed = urlparse(target)
                        if parsed.scheme not in ("", "file"):
                            im.text_disabled(content.get("alt", "External image") + " (external image link)")
                            continue
                        path = pathlib.Path(unquote(parsed.path))
                        if not path.is_absolute():
                            path = (pathlib.Path(self.path).parent if self.path else pathlib.Path.cwd()) / path
                        raw = path.read_bytes()
                        mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
                    payload = raw.decode("utf-8") if mime == "image/svg+xml" else base64.b64encode(raw).decode("ascii")
                    self._draw_output(cell, {"output_type": "display_data", "data": {mime: payload}, "metadata": {}}, width)
                except Exception as error:
                    im.text_wrapped(f"Could not display HTML image: {error}")

    def _draw_output(self, cell: NativeCell, output: dict, width: float) -> None:
        kind = output.get("output_type")
        if kind == "stream":
            im.text_wrapped(_source(output.get("text")))
        elif kind == "error":
            im.text_colored((245, 110, 110, 255), f"{output.get('ename', 'Error')}: {output.get('evalue', '')}")
            im.text_wrapped(_source(output.get("traceback", [])))
        else:
            data = output.get("data", {})
            for mime in ("image/png", "image/jpeg", "image/svg+xml"):
                if mime not in data:
                    continue
                payload = _source(data[mime])
                try:
                    texture = cell._textures.get(payload)
                    if texture is None:
                        if mime == "image/svg+xml":
                            converter = shutil.which("rsvg-convert")
                            if not converter:
                                raise RuntimeError("SVG preview requires an available Qt-free rsvg-convert executable; the original output remains saved")
                            result = subprocess.run([converter], input=payload.encode("utf-8"), capture_output=True, timeout=5, check=True)
                            texture = Texture.from_bytes(result.stdout)
                        else:
                            texture = Texture.from_bytes(base64.b64decode(payload))
                        cell._textures[payload] = texture
                    dimensions = (output.get("metadata") or {}).get(mime) or {}
                    if not isinstance(dimensions, dict):
                        dimensions = {}
                    requested_width = dimensions.get("width", texture.width)
                    if not isinstance(requested_width, (int, float)) or requested_width <= 0:
                        requested_width = texture.width
                    requested_height = dimensions.get("height", texture.height * requested_width / texture.width)
                    if not isinstance(requested_height, (int, float)) or requested_height <= 0:
                        requested_height = texture.height * requested_width / texture.width
                    scale = min(1.0, max(1.0, width) / requested_width)
                    im.image(texture, (requested_width * scale, requested_height * scale))
                    return
                except Exception as error:
                    im.text_wrapped(f"Could not render {mime}: {error}")
            if "text/markdown" in data:
                im.markdown(_source(data["text/markdown"]), on_link=self._open_link, max_width=width)
            elif "text/html" in data:
                self._draw_html(cell, _source(data["text/html"]), width)
            elif "text/plain" in data:
                im.text_wrapped(_source(data["text/plain"]))
            else:
                im.text_disabled(f"Saved output: {', '.join(data)} (preserved in notebook)")

    def draw(
        self, width: float, height: float, on_reload=None, on_export=None,
        ui_scale: float = 1.0,
    ) -> None:
        ui_scale = max(0.5, float(ui_scale))
        self._finish_pending_advance()
        if self.is_running:
            if im.button("■  Stop execution"):
                self.cancel_execution()
            im.set_item_tooltip("Interrupt the running cell or cancel its input prompt")
            im.same_line()
            im.text_colored((235, 190, 105, 255), "Executing notebook…")
        else:
            if im.button("▶ Run all"):
                self.start_all()
            im.set_item_tooltip("Run every code cell in order (Ctrl+Shift+Enter)")
            im.same_line()
            if im.button("＋ Code cell"):
                self.add_cell("code")
            im.set_item_tooltip("Append a Python code cell")
            im.same_line()
            if im.button("＋ Markdown"):
                self.add_cell("markdown")
            im.set_item_tooltip("Append a Markdown cell")
            im.same_line()
            if im.button("↻ Restart"):
                self.restart_shell()
            im.set_item_tooltip("Reset notebook variables; saved cell outputs remain")
            im.same_line()
            if im.button("Clear outputs"):
                self.clear_outputs()
            im.set_item_tooltip("Remove all cell outputs and execution counts")
            im.same_line()
            if im.button("Hide terminal" if self.show_terminal else "Terminal"):
                self.show_terminal = not self.show_terminal
            im.set_item_tooltip("Show or hide a command terminal sharing the notebook shell")
        if on_reload is not None:
            im.same_line()
            if im.button("Reload notebook"):
                on_reload()
            im.set_item_tooltip("Reload this notebook from disk; confirm before discarding unsaved changes")
            im.same_line()
        if on_export is not None:
            if im.button("Export Python"):
                on_export()
            im.set_item_tooltip("Export cell source to a Python script without changing the notebook's save path")
        if self.error:
            im.text_wrapped(self.error)
        im.separator()
        im.begin_child(
            (*im.get_cursor_screen_pos(), width, max(60.0 * ui_scale, height - 74.0 * ui_scale)),
            child_id=f"notebook_{id(self)}",
        )
        for cell in list(self.cells):
            index = self.cells.index(cell)
            im.push_id(cell.node.get("id", str(id(cell))))
            ctx = im.get_current_context()
            header = im.get_cursor_screen_pos()
            # The strip hugs the row's real height: every control in it is at
            # the default frame height, so the header reads as the same line
            # of chrome as the toolbars above it instead of a taller band.
            frame_h = im.get_frame_height()
            header_height = frame_h + 4.0
            ctx.draw.add_rect_filled(header, (header[0] + width, header[1] + header_height),
                                     (36, 41, 50, 255) if index == self.active_index else (33, 35, 41, 255), 0)
            ctx.draw.add_rect_filled(header, (header[0] + 4, header[1] + header_height),
                                     (82, 170, 228, 255) if index == self.active_index else (64, 68, 78, 255), 2)
            count = str(cell.execution_count) if cell.execution_count is not None else " "
            if im.button(
                f"In [{count}] · Cell {index + 1}",
                size=(126.0 * ui_scale, 0.0),
            ):
                self.active_index = index
            im.set_item_tooltip("Select this cell for Run Script and code insertion")
            im.same_line()
            if im.button(
                "▶ Run · Shift+Enter",
                size=(146.0 * ui_scale, 0.0),
            ):
                self.start_cell(index)
            im.set_item_tooltip("Execute this cell; Shift+Enter runs it and moves to the next cell")
            im.same_line()
            if im.button("↑"):
                self.move_cell(index, -1)
            im.set_item_tooltip("Move this cell up")
            im.same_line()
            if im.button("↓"):
                self.move_cell(index, 1)
            im.set_item_tooltip("Move this cell down")
            im.same_line()
            if im.button("×"):
                self.remove_cell(index)
            im.set_item_tooltip("Delete this cell and its outputs")
            im.same_line()
            if im.button("＋"):
                self.add_cell(index=index + 1)
            im.set_item_tooltip("Insert an empty code cell below this one")
            im.same_line()
            im.set_next_item_width(112.0 * ui_scale)
            types = ["code", "markdown", "raw"]
            changed, selected = im.combo("##cell_type", types.index(cell.cell_type), types)
            im.set_item_tooltip("Change the cell type between Python, Markdown and raw source")
            if changed and not self.is_running:
                cell.set_type(types[selected])
            if cell.cell_type == "markdown":
                im.same_line()
                if im.button("Preview" if cell.edit_markdown else "Edit Markdown"):
                    cell.edit_markdown = not cell.edit_markdown
                im.set_item_tooltip("Switch this Markdown cell between source and formatted preview")
            if cell.cell_type == "markdown" and not cell.edit_markdown:
                im.markdown(cell.editor.text, on_link=self._open_link, max_width=width)
            else:
                lines = len(cell.editor.text.splitlines()) or 1
                read_only = cell.editor.config.read_only
                cell.editor.config.read_only = read_only or self.is_running
                if self.active_index == index and ctx.state(("focus",)).pop("notebook_focus_cell", None) == cell.node.get("id"):
                    item_id = ctx.get_id("##cell_source")
                    ctx.state(("focus",))["id"] = item_id
                    im.set_nav_id(item_id)
                if self._take_cell_shortcut(ctx, shift_only=True):
                    self.run_and_advance(index)
                elif self._take_cell_shortcut(ctx, shift_only=False):
                    self.start_cell(index)
                indent = 18.0 * ui_scale
                im.indent(indent)
                editor_height = min(
                    280.0 * ui_scale,
                    max(40.0 * ui_scale, lines * 20.0 * ui_scale + 14.0 * ui_scale),
                )
                im.text_editor(
                    "##cell_source", cell.editor,
                    (max(100.0 * ui_scale, width - indent), editor_height),
                )
                im.unindent(indent)
                cell.editor.config.read_only = read_only
                im.set_item_tooltip("Edit this cell; Shift+Enter runs it and moves to the next cell")
                if im.is_item_active():
                    self.active_index = self.cells.index(cell) if cell in self.cells else self.active_index
            for output in list(cell.outputs):
                self._draw_output(cell, output, width)
            im.separator()
            im.pop_id()
        if self.show_terminal:
            im.text("Notebook terminal")
            for line in self.terminal_output[-200:]:
                im.text_wrapped(line)
            _, self.terminal_input = im.input_text("##notebook_terminal", self.terminal_input, hint="Python command…")
            im.set_item_tooltip("Enter a Python command using the same variables as notebook cells")
            if im.button("Run command"):
                self.start_terminal(self.terminal_input)
                self.terminal_input = ""
            im.set_item_tooltip("Execute the terminal command in the notebook's persistent shell")
        im.end_child()
        if self.pending_input is not None:
            request = self.pending_input
            im.set_next_window_size((480, 180), im.Cond.FIRST_USE_EVER)
            if im.begin(f"Notebook input##{id(self)}"):
                im.text_wrapped(request["prompt"])
                flags = im.InputTextFlags.PASSWORD if request["password"] else 0
                _, self.input_response = im.input_text("##input_response", self.input_response, flags=flags)
                im.set_item_tooltip("Enter the value requested by the running notebook cell")
                if im.button("Submit input"):
                    self.respond_input(self.input_response)
                im.set_item_tooltip("Resume notebook execution with this value")
                im.same_line()
                if im.button("Cancel execution"):
                    self.cancel_execution()
                im.set_item_tooltip("Cancel the input request and interrupt the running cell")
            im.end()
