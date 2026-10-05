"""The fit window's Code face, drawn by emtk.

"Code" in a fit window's title bar turns the window over: instead of the plots
it shows the source of the fit's model and its ``view.json``, editable, with
"Save/Apply" writing the file and re-executing the model module so the change
takes effect in the open fit. This module is that face as part of the window's
one emtk surface:

* a toolbar -- the assistant toggle, back/forward through the places the caret
  jumped to, the model files in the model's folder, the definitions in the open
  file, and Save/Apply;
* a tab per open file, each an emtk :class:`~emtk.widgets.text_editor.TextEditor`
  with Python/JSON highlighting and line numbers, and a find bar (Ctrl+F);
* the coding assistant beside the editor when toggled, the same chat the Code
  Editor tool carries, reading and editing the open files through this face.

It holds no Qt. What "apply" means for a model is the window's business and is
handed in as ``on_apply(path, text)``.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["FitCodeFace", "CodeDocument"]


def _language(path: str):
    from emtk.widgets.text_editor import Language

    suffix = pathlib.Path(path).suffix.lower()
    if suffix in (".py", ".pyw"):
        return Language.python()
    if suffix in (".json", ".ipynb"):
        return Language.json()
    if suffix in (".yaml", ".yml"):
        return Language.yaml()
    return None


@dataclass
class CodeDocument:
    """One open file: its path and its editor."""

    path: str
    editor: Any = field(repr=False)

    @property
    def name(self) -> str:
        return pathlib.Path(self.path).name


class FitCodeFace:
    """Model source editing for one fit window, drawn with :mod:`emtk.im`.

    Parameters
    ----------
    on_apply : callable, optional
        ``on_apply(path, text)`` -- save the text and apply it to the fit. The
        status line shows what it returns (a string) or raises.
    request_frame : callable, optional
        Wakes the surface when something changes outside a frame (a file
        opened from the window's code).
    """

    def __init__(
        self,
        on_apply: Callable[[str, str], Any] | None = None,
        request_frame: Callable[[], None] | None = None,
    ) -> None:
        self.on_apply = on_apply
        self.request_frame = request_frame or (lambda: None)
        #: The files offered in "File:", as paths.
        self.files: list[str] = []
        self.documents: list[CodeDocument] = []
        self.active: int = -1
        self.symbols: list[Any] = []
        self.history: list[tuple[str, int]] = []
        self.history_index: int = -1
        self.agent_open = False
        self._chat_model = None
        self._chat_gui = None
        self.find_open = False
        self.find_text = ""
        self.status = ""
        #: Rectangles of the named controls drawn last frame (tours, tests).
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self._select_tab: int | None = None

    # -- documents ----------------------------------------------------------- #
    @property
    def active_doc(self) -> CodeDocument | None:
        if 0 <= self.active < len(self.documents):
            return self.documents[self.active]
        return None

    def set_files(self, paths) -> None:
        """Offer *paths* in the "File:" list."""
        self.files = [str(p) for p in paths]

    def find_document(self, path: str) -> int:
        """Index of the open document for *path*, or -1."""
        target = str(pathlib.Path(path))
        for index, doc in enumerate(self.documents):
            if str(pathlib.Path(doc.path)) == target:
                return index
        return -1

    def open_file(self, path: str, line: int = 0, *, record: bool = True) -> CodeDocument:
        """Open *path* in a tab (or bring its tab forward) and go to *line* (0-based)."""
        from emtk.widgets.text_editor import Pos, TextEditor

        path = str(path)
        index = self.find_document(path)
        if index < 0:
            text = pathlib.Path(path).read_text(encoding="utf-8")
            editor = TextEditor(text, _language(path))
            self.documents.append(CodeDocument(path, editor))
            index = len(self.documents) - 1
        self.active = index
        self._select_tab = index
        doc = self.documents[index]
        if line > 0:
            doc.editor.set_cursor(Pos(int(line), 0))
            doc.editor.scroll_to_line(int(line), "middle")
        self.refresh_symbols()
        if record:
            self._record(path, line)
        self.request_frame()
        return doc

    def close_document(self, index: int) -> None:
        """Close a tab; the one to its left becomes active."""
        if 0 <= index < len(self.documents):
            del self.documents[index]
            self.active = min(max(index - 1, 0), len(self.documents) - 1)
            self._select_tab = self.active if self.documents else None
            self.refresh_symbols()

    def refresh_symbols(self) -> list[Any]:
        """Re-read the definitions of the active Python file for "Jump to:"."""
        doc = self.active_doc
        self.symbols = []
        if doc is not None and doc.path.endswith(".py"):
            try:
                from chisurf.plugins.core.code_editor.symbols import extract_python_symbols

                self.symbols = list(extract_python_symbols(doc.editor.text))
            except Exception:
                self.symbols = []
        return self.symbols

    def goto_line(self, line: int) -> None:
        """Put the caret on *line* (0-based) of the active file and remember the jump."""
        doc = self.active_doc
        if doc is None:
            return
        from emtk.widgets.text_editor import Pos

        doc.editor.set_cursor(Pos(int(line), 0))
        doc.editor.scroll_to_line(int(line), "middle")
        self._record(doc.path, int(line))

    # -- navigation history -------------------------------------------------- #
    def _record(self, path: str, line: int) -> None:
        entry = (str(path), int(line))
        if 0 <= self.history_index < len(self.history) and self.history[self.history_index] == entry:
            return
        del self.history[self.history_index + 1:]
        self.history.append(entry)
        self.history_index = len(self.history) - 1

    def can_go_back(self) -> bool:
        return self.history_index > 0

    def can_go_forward(self) -> bool:
        return self.history_index < len(self.history) - 1

    def back(self) -> None:
        """Return to the previous place the caret jumped from."""
        if self.can_go_back():
            self.history_index -= 1
            self._visit(self.history[self.history_index])

    def forward(self) -> None:
        """Redo a jump undone by :meth:`back`."""
        if self.can_go_forward():
            self.history_index += 1
            self._visit(self.history[self.history_index])

    def _visit(self, entry: tuple[str, int]) -> None:
        path, line = entry
        self.open_file(path, line, record=False)
        if line <= 0:
            from emtk.widgets.text_editor import Pos

            self.active_doc.editor.set_cursor(Pos(0, 0))
            self.active_doc.editor.scroll_to_line(0, "top")

    # -- apply ----------------------------------------------------------------- #
    def apply(self) -> None:
        """Hand the active file's text to ``on_apply``; show the outcome."""
        doc = self.active_doc
        if doc is None or self.on_apply is None:
            return
        try:
            result = self.on_apply(doc.path, doc.editor.text)
        except Exception as problem:  # the status line is where this is read
            self.status = f"Failed to save and apply: {problem}"
        else:
            doc.editor.mark_saved()
            self.status = str(result) if isinstance(result, str) else f"Saved {doc.name}"

    # -- what the assistant reads and edits --------------------------------- #
    def get_file_content(self, path: str) -> str | None:
        index = self.find_document(path)
        if index >= 0:
            return self.documents[index].editor.text
        try:
            return pathlib.Path(path).read_text(encoding="utf-8")
        except OSError:
            return None

    def set_file_content(self, path: str, content: str) -> bool:
        index = self.find_document(path)
        if index < 0:
            self.open_file(path)
            index = self.find_document(path)
        self.documents[index].editor.set_text(str(content))
        self.request_frame()
        return True

    def insert_code_at_cursor(self, code: str) -> None:
        doc = self.active_doc
        if doc is not None:
            doc.editor.insert(str(code))
            self.request_frame()

    def replace_selected_code(self, code: str) -> None:
        self.insert_code_at_cursor(code)

    def toggle_agent(self) -> bool:
        """Show or hide the coding assistant beside the editor."""
        self.agent_open = not self.agent_open
        if self.agent_open and self._chat_gui is None:
            try:
                from chisurf.plugins.core.code_editor.gui.chat_app import ChatGui, ChatModel

                self._chat_model = ChatModel(editor_ref=self)
                self._chat_gui = ChatGui(model=self._chat_model, editor_ref=self)
            except Exception as problem:
                self.agent_open = False
                self.status = f"Assistant unavailable: {problem}"
        return self.agent_open

    def busy(self) -> bool:
        """Whether the assistant is working (the surface keeps drawing frames)."""
        model = self._chat_model
        return bool(model is not None and self.agent_open and (
            getattr(model, "is_generating", False)
            or getattr(model, "event_queue", None) is not None and not model.event_queue.empty()))

    def close(self) -> None:
        """Stop the assistant, if it was started."""
        model = self._chat_model
        close = getattr(model, "close", None)
        if callable(close):
            close()

    # -- drawing -------------------------------------------------------------- #
    def _remember(self, name: str) -> None:
        from emtk import im

        rect = im.get_item_rect()
        if rect is not None:
            self.item_rects[name] = tuple(float(v) for v in rect)

    def draw(self, box: tuple[float, float, float, float]) -> None:
        """Draw the face into *box* (inside an emtk frame)."""
        from emtk import im

        x, y, w, h = box
        flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_MOVE
                 | im.WindowFlags.NO_SCROLLBAR | im.WindowFlags.NO_SAVED_SETTINGS)
        im.begin("##fit-code-face", (x, y, w, h), flags=flags)
        try:
            self._draw_toolbar()
            if self.find_open:
                self._draw_find_bar()
            avail_w, avail_h = im.get_content_region_avail()[:2]
            status_h = im.get_text_line_height() + 6.0
            body_h = max(avail_h - status_h, 40.0)
            agent_w = min(max(avail_w * 0.34, 260.0), 420.0) if self.agent_open else 0.0
            if self.agent_open and self._chat_gui is not None:
                im.begin_child("##code-editor-col", (avail_w - agent_w - 6.0, body_h))
                self._draw_documents()
                im.end_child()
                im.same_line()
                im.begin_child("##code-agent-col", (agent_w, body_h))
                if self._chat_model is not None:
                    self._chat_model.process_events()
                self._chat_gui.draw(agent_w, body_h)
                im.end_child()
            else:
                im.begin_child("##code-editor-col", (avail_w, body_h))
                self._draw_documents()
                im.end_child()
            im.text_disabled(self.status or self._caret_text())
        finally:
            im.end()

    def _caret_text(self) -> str:
        doc = self.active_doc
        if doc is None:
            return "No file open."
        try:
            line, column = doc.editor.cursors.main.end.line, doc.editor.cursors.main.end.column
        except Exception:
            return doc.path
        return f"{doc.path}   Ln {line + 1}, Col {column + 1}"

    #: Toolbar columns: 🤖, ←, →, "File:", the file list (stretch 2), "Jump to:",
    #: the definitions (stretch 1), Save/Apply. 0 fits its content.
    TOOLBAR_COLUMNS = (0, 0, 0, 0, 2, 0, 1, 0)

    def _draw_toolbar(self) -> None:
        from emtk import im

        if not im.begin_grid("##code-toolbar", self.TOOLBAR_COLUMNS):
            return
        if im.small_button(("● " if self.agent_open else "") + "🤖"):
            self.toggle_agent()
        im.set_item_tooltip("Show or hide the coding assistant beside the editor.")
        self._remember("agent")
        im.next_cell()
        im.begin_disabled(not self.can_go_back())
        if im.small_button("←"):
            self.back()
        im.end_disabled()
        im.set_item_tooltip("Back to where the caret was before the last jump.")
        self._remember("back")
        im.next_cell()
        im.begin_disabled(not self.can_go_forward())
        if im.small_button("→"):
            self.forward()
        im.end_disabled()
        im.set_item_tooltip("Forward again, after going back.")
        self._remember("forward")
        im.next_cell()
        im.align_text_to_frame_padding()
        im.text("File:")
        im.next_cell()
        names = [pathlib.Path(p).name for p in self.files]
        doc = self.active_doc
        current = self.files.index(doc.path) if doc is not None and doc.path in self.files else -1
        changed, picked = im.combo("##code-file", current, names or ["(no files)"])
        im.set_item_tooltip("The model's source files and view.json specs; pick one to open it.")
        self._remember("file")
        if changed and 0 <= picked < len(self.files):
            self.open_file(self.files[picked])
        im.next_cell()
        im.align_text_to_frame_padding()
        im.text("Jump to:")
        im.next_cell()
        labels = ["Select..."] + [
            ("  " if getattr(s, "kind", "") == "method" else "")
            + str(getattr(s, "display_name", getattr(s, "name", "")))
            for s in self.symbols
        ]
        changed, picked = im.combo("##code-jump", 0, labels)
        im.set_item_tooltip("The classes and functions in the open file; pick one to go to it.")
        self._remember("jump")
        if changed and picked > 0:
            symbol = self.symbols[picked - 1]
            self.goto_line(max(0, int(getattr(symbol, "line", 1)) - 1))
        im.next_cell()
        if im.small_button("Save/Apply"):
            self.apply()
        im.set_item_tooltip(
            "Write the file and apply it: the model module is re-executed so the open fit "
            "uses the edited code. A read-only installation saves a copy in the settings folder."
        )
        self._remember("apply")
        im.end_grid()

    def _draw_find_bar(self) -> None:
        from emtk import im

        if not im.begin_grid("##code-find-bar", (0, 1, 0, 0)):
            return
        im.align_text_to_frame_padding()
        im.text("Find:")
        im.next_cell()
        changed, value = im.input_text("##code-find", self.find_text)
        doc = self.active_doc
        if changed:
            self.find_text = value
            if doc is not None:
                doc.editor.set_find_text(value)
        im.next_cell()
        if im.small_button("Next") and doc is not None:
            doc.editor.set_find_text(self.find_text)
            doc.editor.find_next()
        im.set_item_tooltip("Go to the next match in the open file.")
        im.next_cell()
        if im.small_button("×##close-find"):
            self.find_open = False
        im.set_item_tooltip("Close the find bar (Escape).")
        im.end_grid()

    def _draw_documents(self) -> None:
        from emtk import im

        if not self.documents:
            im.text_disabled("Open a file from the list above.")
            return
        if im.begin_tab_bar("##code-tabs"):
            for index, doc in enumerate(list(self.documents)):
                flags = 0
                if self._select_tab == index:
                    flags = im.TabItemFlags.SET_SELECTED
                label = ("● " if doc.editor.modified else "") + doc.name + f"##{doc.path}"
                if im.begin_tab_item(label, flags, on_close=lambda i=index: self.close_document(i)):
                    if self.active != index:
                        self.active = index
                        self.refresh_symbols()
                    self._remember(f"tab:{doc.name}")
                    io = im.get_io()
                    definition = (io.mouse_clicked[0] and (io.key_ctrl or io.key_super))
                    im.text_editor(f"##editor-{doc.path}", doc.editor)
                    self._remember("editor")
                    if definition and im.is_item_hovered():
                        # Ctrl/Cmd-click: the editor has put the caret on the word.
                        self.jump_to_definition(self.word_at_caret())
                    im.end_tab_item()
            self._select_tab = None
            im.end_tab_bar()

    # -- go to definition --------------------------------------------------- #
    def word_at_caret(self) -> str:
        """The identifier under the active editor's caret."""
        doc = self.active_doc
        if doc is None:
            return ""
        try:
            return doc.editor.document.word_at(doc.editor.cursors.main.end)
        except Exception:
            return ""

    def jump_to_definition(self, word: str) -> bool:
        """Go to where *word* is defined: in this file, else in a module it imports.

        Returns whether a definition was found. Each jump is recorded, so Back
        returns to the call site.
        """
        import importlib
        import inspect
        import re

        word = str(word or "").strip()
        doc = self.active_doc
        if not word or doc is None:
            return False
        for symbol in self.refresh_symbols():
            if getattr(symbol, "name", None) == word:
                self._record(doc.path, doc.editor.cursors.main.end.line)
                self.goto_line(max(0, int(symbol.line) - 1))
                return True
        modules = set()
        for line in doc.editor.text.split("\n"):
            match = re.match(r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))", line)
            if match:
                modules.add(match.group(1) or match.group(2))
        for name in sorted(modules):
            try:
                target = getattr(importlib.import_module(name), word, None)
                if target is None:
                    continue
                source = inspect.getsourcefile(target)
                _, first = inspect.getsourcelines(target)
            except Exception:
                continue
            if source:
                self._record(doc.path, doc.editor.cursors.main.end.line)
                self.open_file(source, max(0, int(first) - 1))
                return True
        self.status = f"No definition found for {word!r}."
        return False

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Ctrl+F find, Ctrl+S apply, F12 go to definition, Escape closes the find bar."""
        from emtk.events import CONTROL_MODIFIER
        from emtk.keys import KEY_ESCAPE, KEY_F12, letter_of

        if key == KEY_F12 and self.active_doc is not None:
            self.jump_to_definition(self.word_at_caret())
            return True
        if modifiers & CONTROL_MODIFIER:
            letter = letter_of(key, text)
            if letter == "f" and self.active_doc is not None:
                self.find_open = True
                selected = self.active_doc.editor.selected_text()
                if selected and "\n" not in selected:
                    self.find_text = selected
                return True
            if letter == "s":
                self.apply()
                return True
        if key == KEY_ESCAPE and self.find_open:
            self.find_open = False
            return True
        return False
