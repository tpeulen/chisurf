"""The emtk shell's Console dock: ChiSurf's Python console on emtk's TextEditor.

The console is the Qt-free engine :mod:`chisurf.core.console` (the interpreter, magics, completion,
history and output capture that chinsole draws in the Qt shell) under an emtk view. What it does is
what the Qt console does, behaviour for behaviour (the parity test drives both with the same keys,
``test/native_emtk/test_emtk_shell_console.py`` against ``shell_s4_qt_inventory.json``):

* **Run**: Enter runs the input when it is a complete statement and opens an indented continuation
  line when it is not (``for x in y:``); a blank continuation line ends a block. Shift+Enter always
  adds a line. Output, errors and tracebacks are written into the transcript as the cell runs; a
  trailing expression shows under ``Out[n]:``.
* **History**: Up on the input's first line and Down on its last walk the input history, filtered
  by what was typed when the walk began; Ctrl+R finds the newest entry containing what is typed.
  The history persists across sessions (``chinsole_history.txt`` in the settings folder).
* **Completion**: Tab completes from the live namespace (the common prefix first, a list when the
  matches differ); Tab in leading whitespace indents. Typing ``(`` or Shift+Tab shows the calltip.
  ``obj?`` opens the help in the pager below the transcript (Escape closes it).
* **Editing**: Ctrl+K / Ctrl+U cut to the end / start of the line, Ctrl+Y puts it back, Ctrl+A /
  Ctrl+E go to the start / end of the line, Ctrl+L clears the transcript, Ctrl+C without a selection
  abandons the input (with a selection it copies).
* **The macro channel**: while the console is open, ``chisurf.run(code)`` runs *code* here (from any
  thread: a worker's call is queued for the frame) and records it in the operation history as
  ``run command: …``; ``chisurf.log(code)`` records without running. Every command is appended to the
  session log (``settings.session_file``) and, while *Macro ▸ Record* is on, to the macro, which is
  saved as a ``.cm.py`` file and replayed with *Macro ▸ Run Macro…* (``%run -i``).

What runs here is ordinary Python in the console's namespace: ``cs`` (the package), ``gui`` (the
shell), ``api`` (the session's :class:`~chisurf.core.api.ChiSurfAPI`, once the session is up), ``np``
and ``os``. Fits and datasets are reached through ``api``, which goes through the session server
like every dock does. The cell runs on the frame thread, as the Qt console runs it on the GUI thread.

Deliberate differences from the Qt console: the input is its own box under the transcript (Qt types
at an inline prompt in one document); ``text/html`` is shown as its text; ``input()`` raises
``EOFError`` (a frame cannot wait for a line).

Images are drawn in the transcript as they are in the Qt console: a matplotlib figure after the cell
that drew it (or at ``plt.show()``), anything with ``_repr_png_`` / ``_repr_svg_`` (emtk figures,
PIL images), and ``display(array)`` for a numpy image. An image is narrowed to the console's width
with its aspect kept, scrolls with the text, and its right-click menu copies or saves it.
"""

from __future__ import annotations

import contextlib
import logging
import os
import pathlib
import threading
from collections import deque
from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.keys import (
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_HOME,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
    KEY_TAB,
    KEY_UP,
    letter_of,
)
from emtk.widgets.text_editor import DARK_PALETTE, LIGHT_PALETTE, Language, Pos, TextEditor, Token

_log = logging.getLogger("chisurf.emtk.console")

#: The Qt console's prompts (``ConsoleConfig.prompt`` / ``continuation``).
PROMPT = "In [{n}]: "
CONTINUATION = "   ...: "
#: The guided tour's target name for the console, shared with the Qt console's tour.
VIEW_KEY = "chinsole_view"
#: Help page and guided tour, shared with the Qt console (read as files: no Qt import).
_CHINSOLE = pathlib.Path(__file__).resolve().parents[1] / "core" / "console"
HELP_FILE = _CHINSOLE / "help.md"
GUIDE_FILE = _CHINSOLE / "guide.json"
#: The file filter of a saved macro.
MACRO_FILTER = (("Python macro", ("*.cm.py", "*.py")),)
#: Most input lines the input box grows to before it scrolls.
INPUT_LINES = 8
_ENTER = (KEY_RETURN, KEY_ENTER, 13)
#: Fitting an image to a short console never shrinks it below this height (pixels).
MIN_IMAGE_HEIGHT = 240.0

#: The transcript's colours: the editor's dark palette, errors readable on it.
_PALETTE = list(DARK_PALETTE)
_PALETTE[Token.BRACKET_ERROR] = (240, 120, 120)
OUTPUT_PALETTE = tuple(_PALETTE)
#: The same on a light window (emtk's light token palette, a darker error red).
_PALETTE = list(LIGHT_PALETTE)
_PALETTE[Token.BRACKET_ERROR] = (176, 36, 36)
OUTPUT_PALETTE_LIGHT = tuple(_PALETTE)


def output_palette() -> tuple:
    """The transcript's colours for the theme in effect (:mod:`emtk.theme`)."""
    from emtk import theme

    return OUTPUT_PALETTE_LIGHT if theme.is_light() else OUTPUT_PALETTE
#: Transcript line kind -> colour role.
_KIND_TOKEN = {
    "stdout": Token.TEXT,
    "result": Token.TEXT,
    "input": Token.KNOWN_IDENTIFIER,
    "prompt": Token.DECLARATION,
    "stderr": Token.BRACKET_ERROR,
    "message": Token.COMMENT,
}


class InlineImage:
    """An image in the transcript: a plot, a picture, anything ``display`` drew.

    Parameters
    ----------
    data : bytes
        The encoded image (PNG, JPEG): what *Copy image* and *Save image as…* hand on.
    fmt : str
        ``"png"`` or ``"jpeg"``, the extension a saved file gets.
    """

    def __init__(self, data: bytes, fmt: str = "png") -> None:
        from emtk.texture import Texture

        self.data = bytes(data)
        self.fmt = fmt
        #: The decoded pixels the painter draws (decoding fails loudly here, not mid-frame).
        self.texture = Texture.from_bytes(self.data)
        self.width, self.height = self.texture.width, self.texture.height

    def fitted(self, width: float, height: float | None = None) -> tuple[float, float]:
        """Its drawn size within *width* (and *height*): its own, or shrunk with the aspect kept."""
        scale = min(1.0, max(1.0, float(width)) / self.width)
        if height is not None:
            scale = min(scale, max(1.0, float(height)) / self.height)
        return self.width * scale, self.height * scale


class _ImageLine(list):
    """A transcript line that holds an :class:`InlineImage` (``[text, "image"]`` as a list)."""

    def __init__(self, image: InlineImage) -> None:
        super().__init__(["", "image"])
        self.image = image


class Transcript:
    """The console's scrollback: lines, each with the kind of output that started it.

    Parameters
    ----------
    max_lines : int
        Older lines are dropped beyond this (the ``max_blocks`` setting).
    """

    def __init__(self, max_lines: int = 5000) -> None:
        self.max_lines = max(10, int(max_lines))
        self.lines: list[list] = []
        #: Whether the last line is still open (output arrived without a newline).
        self.open = False
        self.revision = 0

    def append(self, text: str, kind: str = "stdout") -> None:
        """Add *text* of *kind*; a line that receives error output is drawn as an error."""
        from chisurf.core.console.ansi import strip_ansi

        text = strip_ansi(str(text)).replace("\r\n", "\n")
        if not text:
            return
        parts = text.split("\n")
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            if index == 0 and self.open and self.lines:
                line = self.lines[-1]
                line[0] += part
                if kind == "stderr":
                    line[1] = kind
            elif not (last and part == ""):
                self.lines.append([part, kind])
            if not last:
                self.open = False
            elif part:
                self.open = True
        if len(self.lines) > self.max_lines:
            del self.lines[: len(self.lines) - self.max_lines]
        self.revision += 1

    def append_image(self, image: InlineImage) -> None:
        """Add *image* on lines of its own."""
        self.open = False
        self.lines.append(_ImageLine(image))
        if len(self.lines) > self.max_lines:
            del self.lines[: len(self.lines) - self.max_lines]
        self.revision += 1

    @property
    def images(self) -> list[InlineImage]:
        """The images in the scrollback, oldest first."""
        return [line.image for line in self.lines if isinstance(line, _ImageLine)]

    def close_line(self) -> None:
        """End an open line, so what follows starts on a new one."""
        self.open = False

    def clear(self) -> None:
        """Forget everything."""
        self.lines = []
        self.open = False
        self.revision += 1

    def text(self) -> str:
        """The scrollback as one string."""
        return "\n".join(line[0] for line in self.lines)


class ConsoleControl:
    """The drawn console: transcript, pager, calltip, completion list and the input box.

    A retained control (:func:`emtk.im.host_control` hosts it): it draws into a box and takes the
    presses, keys and compositions of the input method, which go to the input box.
    """

    #: Tab completes and indents here; keyboard navigation must not take it.
    wants_tab = True

    def __init__(self, console: ShellConsole) -> None:
        self.console = console
        self.output = TextEditor("", read_only=True)
        self.input = TextEditor("", language=Language.python())
        self.pager = TextEditor("", read_only=True)
        for editor in (self.output, self.pager):
            editor.config.show_line_numbers = False
            editor.config.highlight_current_line = False
            editor.config.show_matching_brackets = False
            editor.config.carets_visible = False
            editor.palette = OUTPUT_PALETTE
        self.input.config.show_line_numbers = False
        self.input.config.highlight_current_line = False
        self.input.config.complete_paired_glyphs = False
        self.input.config.text_margin = 1
        self.has_focus = False
        #: Which box has the keys: "input", "output" or "pager".
        self.target = "input"
        self._revision = -1
        self._follow = True
        self.boxes: dict[str, tuple[float, float, float, float]] = {}
        self._line_h = 14.0
        #: ``(first document line, rows, image)`` of each image in the transcript editor.
        self.image_rows: list[tuple[int, int, InlineImage]] = []
        #: Where each visible image was last drawn: ``(x, y, w, h, image)``.
        self.image_boxes: list[tuple[float, float, float, float, InlineImage]] = []
        self._layout_key: tuple = ()

    # ── the transcript ────────────────────────────────────────────────────

    def _image_limit(self, w: float, h: float, line_h: float) -> tuple[float, float]:
        """The largest an image may be drawn in an output box *w* by *h*.

        As wide as the text, and no taller than the box less a row, so a whole plot is in
        view at once -- but never shrunk below :data:`MIN_IMAGE_HEIGHT` for a short dock (a
        thumbnail nobody can read); there it scrolls instead.
        """
        editor = self.output
        margin = editor.config.text_margin * max(editor._glyph_w, 1.0)
        return (
            max(16.0, w - 2.0 * margin - editor.vbar.width - 4.0),
            max(MIN_IMAGE_HEIGHT, h - line_h - 2.0),
        )

    def _sync_output(self, w: float = 0.0, line_h: float = 0.0, h: float = 0.0) -> None:
        """Rebuild the transcript editor when the transcript, the width or the font changed.

        An image is laid out as blank rows enough for its fitted height; :meth:`draw` paints it
        over them. So it scrolls, selects and clears with the text around it.
        """
        transcript = self.console.transcript
        line_h = line_h or self._line_h
        key = (
            (transcript.revision, round(w), round(h), round(line_h, 2))
            if transcript.images
            else (transcript.revision,)
        )
        if key == self._layout_key:
            return
        editor = self.output
        at_end = editor.first_visible_line + editor.visible_lines >= len(editor.document) - 1
        texts: list[str] = []
        kinds: list[str] = []
        self.image_rows = []
        for line in transcript.lines:
            if isinstance(line, _ImageLine):
                limit = self._image_limit(w, h, line_h) if w and h else (line.image.width, None)
                _dw, dh = line.image.fitted(*limit)
                rows = max(1, int(-(-dh // max(line_h, 1.0))))
                self.image_rows.append((len(texts), rows, line.image))
                texts.extend([""] * rows)
                kinds.extend(["image"] * rows)
            else:
                texts.append(line[0])
                kinds.append(line[1])
        editor.set_text("\n".join(texts))
        editor.colorizer.update(editor.config, editor.document)
        for line, kind in zip(editor.document.lines, kinds):
            line.paint(0, len(line.text), _KIND_TOKEN.get(kind, Token.TEXT))
            if kind == "input":
                prompt = line.text.find(": ")
                if prompt > 0:
                    line.paint(0, prompt + 2, Token.DECLARATION)
        editor.bracketeer.update(editor.config, editor.document)
        editor.document.updated = False
        self._revision = transcript.revision
        self._layout_key = key
        self._follow = self._follow or at_end
        if self._follow:
            editor.scroll_to_line(len(editor.document) - 1, align="bottom")

    def _draw_images(self, p, x: float, y: float, w: float, h: float) -> None:
        """Paint the transcript's images over their blank rows, clipped to the output box."""
        self.image_boxes = []
        if not self.image_rows:
            return
        from emtk.painter import image as draw_image

        editor = self.output
        line_h = editor._line_h
        first = editor.first_visible_line
        left = editor._text_x
        limit = self._image_limit(w, h, line_h)
        p.push_clip(x + 1.0, y + 1.0, max(1.0, w - 2.0), max(1.0, h - 2.0))
        for line, rows, image in self.image_rows:
            top = y + (line - first) * line_h
            if top + rows * line_h < y or top > y + h:
                continue
            dw, dh = image.fitted(*limit)
            draw_image(p, left, top, dw, dh, image.texture)
            self.image_boxes.append((left, top, dw, dh, image))
        p.pop_clip()

    def image_at(self, px: float, py: float) -> InlineImage | None:
        """The image drawn at ``(px, py)``, else ``None``."""
        out = self.boxes.get("output")
        if out is None or not (out[1] <= py < out[1] + out[3]):
            return None
        for bx, by, bw, bh, image in self.image_boxes:
            if bx <= px < bx + bw and by <= py < by + bh:
                return image
        return None

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        console = self.console
        palette = output_palette()
        for editor in (self.output, self.pager):
            editor.palette = palette
        line_h = max(float(p.line_height()), 1.0)
        self._line_h = line_h
        rows = max(1, min(INPUT_LINES, len(self.input.document)))
        input_h = rows * line_h + 6.0
        prompt = PROMPT.format(n=console.engine.execution_count)
        prompt_w = p.text_width(prompt) + 6.0
        body_h = max(line_h, h - input_h - 2.0)
        if console.pager_title:
            pager_h = max(3 * line_h, body_h * 0.5)
            out_h = max(line_h, body_h - pager_h - line_h - 2.0)
        else:
            pager_h = 0.0
            out_h = body_h
        self.boxes = {"output": (x, y, w, out_h)}
        self._sync_output(w, line_h * self.output.config.line_spacing, out_h)
        self.output.config.carets_visible = self.has_focus and self.target == "output"
        self.output.draw(p, x, y, w, out_h)
        self._draw_images(p, x, y, w, out_h)
        if console.pager_title:
            top = y + out_h + 2.0
            from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
            from emtk.style import FRAME_BG, TEXT

            p.fill_rect(x, top, w, line_h, FRAME_BG)
            p.text(
                x + 6.0,
                top,
                w - 30.0,
                line_h,
                ALIGN_LEFT | ALIGN_VCENTER,
                console.pager_title,
                palette[Token.DECLARATION],
            )
            self.boxes["pager.close"] = (x + w - 22.0, top, 22.0, line_h)
            p.text(x + w - 18.0, top, 18.0, line_h, ALIGN_LEFT | ALIGN_VCENTER, "✕", TEXT)
            self.boxes["pager"] = (x, top + line_h, w, pager_h)
            self.pager.draw(p, x, top + line_h, w, pager_h)
        iy = y + h - input_h
        self.boxes["prompt"] = (x, iy, prompt_w, input_h)
        self.boxes["input"] = (x + prompt_w, iy, max(1.0, w - prompt_w), input_h)
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
        from emtk.style import FRAME_BG

        p.fill_rect(x, iy, prompt_w, input_h, FRAME_BG)
        first = self.input.first_visible_line
        for row in range(rows):
            text = prompt if first + row == 0 else CONTINUATION
            p.text(
                x + 4.0,
                iy + row * line_h,
                prompt_w,
                line_h,
                ALIGN_LEFT | ALIGN_VCENTER,
                text,
                palette[Token.DECLARATION],
            )
        self.input.config.carets_visible = self.has_focus and self.target == "input"
        self.input.draw(p, *self.boxes["input"])
        self._draw_calltip(p, x, iy, w)
        self._draw_completions(p, x + prompt_w, iy, w - prompt_w)

    def _draw_calltip(self, p, x: float, iy: float, w: float) -> None:
        tip = self.console.calltip_text
        if not tip:
            return
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
        from emtk.style import BORDER, POPUP_BG, TEXT

        lines = tip.split("\n")[:4]
        height = len(lines) * self._line_h + 4.0
        width = min(w, max(p.text_width(line) for line in lines) + 12.0)
        top = iy - height - 2.0
        self.boxes["calltip"] = (x, top, width, height)
        p.fill_rect(x, top, width, height, POPUP_BG)
        p.stroke_rect(x, top, width, height, BORDER)
        for row, line in enumerate(lines):
            p.text(
                x + 6.0,
                top + 2.0 + row * self._line_h,
                width - 8.0,
                self._line_h,
                ALIGN_LEFT | ALIGN_VCENTER,
                line,
                TEXT,
            )

    def _draw_completions(self, p, x: float, iy: float, w: float) -> None:
        matches = self.console.completions
        if not matches:
            return
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
        from emtk.style import BORDER, HEADER_ACTIVE, POPUP_BG, TEXT

        shown = matches[:12]
        width = min(w, max(p.text_width(m) for m in shown) + 24.0)
        height = len(shown) * self._line_h + 4.0
        caret = self.input.ime_caret
        left = caret[0] if caret else x
        left = min(left, x + w - width)
        top = iy - height - 2.0
        self.boxes["completions"] = (left, top, width, height)
        p.fill_rect(left, top, width, height, POPUP_BG)
        p.stroke_rect(left, top, width, height, BORDER)
        for row, match in enumerate(shown):
            ry = top + 2.0 + row * self._line_h
            if row == self.console.completion_index:
                p.fill_rect(left + 1.0, ry, width - 2.0, self._line_h, HEADER_ACTIVE)
            self.boxes[f"completion.{row}"] = (left, ry, width, self._line_h)
            p.text(
                left + 8.0, ry, width - 10.0, self._line_h, ALIGN_LEFT | ALIGN_VCENTER, match, TEXT
            )

    # ── input ─────────────────────────────────────────────────────────────

    def _box_at(self, px: float, py: float) -> str | None:
        for name in ("completions", "pager.close", "input", "pager", "output", "prompt"):
            box = self.boxes.get(name)
            if box and box[0] <= px < box[0] + box[2] and box[1] <= py < box[1] + box[3]:
                return name
        return None

    def press(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0, modifiers=0, clicks=1):
        self.has_focus = True
        where = self._box_at(px, py)
        if where == "completions":
            for row in range(len(self.console.completions)):
                bx, by, bw, bh = self.boxes.get(f"completion.{row}", (0, 0, 0, 0))
                if by <= py < by + bh:
                    self.console.accept_completion(row)
                    break
            return where
        if where == "pager.close":
            self.console.close_pager()
            return where
        self.console.dismiss_popups()
        if where in ("input", "prompt"):
            self.target = "input"
            self.input.press(px, py, *self.boxes["input"], modifiers, clicks)
        elif where in ("output", "pager"):
            self.target = where
            editor = self.output if where == "output" else self.pager
            editor.press(px, py, *self.boxes[where], modifiers, clicks)
        return where

    def drag(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0):
        editor = self._editor()
        box = self.boxes.get(self.target)
        if box is not None:
            editor.drag(px, py, *box)

    def release(self) -> None:
        self._editor().release()

    def focus_lost(self) -> None:
        self.has_focus = False
        self.console.dismiss_popups()

    def scroll(self, rows: int) -> int:
        self._follow = False
        if self.console.pager_title and self.target == "pager":
            return self.pager.scroll(rows)
        result = self.output.scroll(rows)
        editor = self.output
        if editor.first_visible_line + editor.visible_lines >= len(editor.document):
            self._follow = True
        return result

    def _editor(self) -> TextEditor:
        return {"output": self.output, "pager": self.pager}.get(self.target, self.input)

    def compose(self, text: str, cursor: int) -> None:
        """The input method's composition goes to the input box (where typing goes)."""
        self.input.compose(text, cursor)

    @property
    def ime_caret(self):
        """Where the input box's caret is, for the input method's candidate window."""
        return self.input.ime_caret

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        self.has_focus = True
        console = self.console
        if console.handle_key(int(key), str(text or ""), int(modifiers)):
            return True
        editor = self._editor()
        if editor is not self.input and text and text.isprintable() and not _chord(modifiers):
            # Typing over the transcript types at the prompt, as in the Qt console.
            self.target = "input"
            editor = self.input
        editor.key(int(key), text, int(modifiers))
        if text == "(" and editor is self.input and not _chord(modifiers):
            console.show_calltip()
        elif text and console.calltip_text and editor is self.input and text in ")\n":
            console.calltip_text = ""
        return True


def _as_bytes(payload: Any) -> bytes:
    """An image payload as bytes: raw, or base64 text (as a Jupyter bundle carries it)."""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    import base64

    return base64.b64decode(str(payload))


def _html_as_text(html: Any) -> str:
    """``text/html`` with only its text: what a bundle with no ``text/plain`` shows here."""
    import html as html_module
    import re

    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])>", "\n", str(html))
    text = re.sub(r"<[^>]+>", "", text)
    return html_module.unescape(text).strip()


def _chord(modifiers: int) -> bool:
    from emtk.events import CONTROL_MODIFIER, META_MODIFIER

    return bool(int(modifiers) & (CONTROL_MODIFIER | META_MODIFIER))


class ShellConsole:
    """ChiSurf's console for the emtk shell: the engine, the transcript, the macro channel.

    Parameters
    ----------
    namespace : dict, optional
        Seeded into the console's namespace.
    history_path : path or bool, optional
        The input history file; ``False`` keeps none (tests), ``None`` the settings default.
    session_file : path, optional
        The session log every command is appended to; ``False`` for none, ``None`` for
        ``chisurf.core.settings.session_file``.
    wake : callable, optional
        Asks for a frame (a worker queued a command).
    record_command : callable, optional
        ``record_command(code)``: tells the operation history a command ran (the shell's undo).
    init_source : str, optional
        Run once, silently; ``None`` runs the ``gui.console_init`` setting.
    """

    def __init__(
        self,
        namespace: dict | None = None,
        *,
        history_path: Any = None,
        session_file: Any = None,
        wake: Callable[[], None] | None = None,
        record_command: Callable[[str], None] | None = None,
        init_source: str | None = None,
    ) -> None:
        from chisurf.core.console import Shell
        from chisurf.core.console.history import HistoryManager
        from chisurf.core.console.settings import console_init_source, console_settings

        self.settings = console_settings()
        self.wake = wake
        self.record_command = record_command
        self.transcript = Transcript(int(self.settings["max_blocks"]))
        self.engine = Shell(
            user_ns=dict(namespace or {}),
            write=self._write,
            display=self._display,
            read_input=None,
            clear=self.clear,
            edit_file=self._edit_file,
            history=HistoryManager(history_path, max_entries=int(self.settings["history_length"])),
        )
        self.control = ConsoleControl(self)
        self.recording = False
        self._macro = ""
        self.session_file = self._session_file(session_file)
        #: Completion matches shown in the list, the highlighted row and the span they replace.
        self.completions: list[str] = []
        self.completion_index = 0
        self._completion: Any = None
        self.calltip_text = ""
        self.pager_title = ""
        self._history_index: int | None = None
        self._history_prefix = ""
        self._history_stash = ""
        self._kill_ring: list[str] = []
        self._thread = threading.get_ident()
        self._queue: deque[tuple[str, str]] = deque()
        self._installed: dict[str, Any] | None = None
        #: Whether a command ran: only then is the history file written back.
        self._ran = False
        self._focus_requested = False
        self.item_rects: dict[str, tuple] = {}
        self._help = None
        self._tour = None
        #: The image the context menu was opened on, and the *Save image as…* dialog.
        self._menu_image: InlineImage | None = None
        self.file_dialog: Any = None
        self._file_window: Any = None
        self._saving: InlineImage | None = None
        # matplotlib figures land in the transcript, as in a notebook, without a %matplotlib
        # line first (chisurf.core.console.mpl_inline).
        self.engine.enable_inline_figures()
        if self.settings["banner"]:
            self.transcript.append(self._banner(), "message")
        source = console_init_source() if init_source is None else init_source
        if source and source.strip():
            self.execute(source, hidden=True)

    # ── settings and plumbing ─────────────────────────────────────────────

    @staticmethod
    def _session_file(session_file: Any) -> pathlib.Path | None:
        if session_file is False:
            return None
        if session_file is not None:
            return pathlib.Path(session_file)
        try:
            import chisurf.core.settings

            return pathlib.Path(chisurf.core.settings.session_file)
        except Exception:  # noqa: BLE001 - no settings, no session log
            return None

    @staticmethod
    def _banner() -> str:
        import sys

        try:
            import chisurf

            version = chisurf.__version__
        except Exception:  # noqa: BLE001
            version = "?"
        python = ".".join(str(part) for part in sys.version_info[:3])
        return (
            tr(
                "ChiSurf {version} console  |  Python {python}  |  "
                "%quickref for help, obj? for details"
            ).format(version=version, python=python)
            + "\n"
        )

    def _write(self, name: str, text: str) -> None:
        self.transcript.append(text, "stderr" if name == "stderr" else "stdout")

    def _display(self, data: dict, metadata: dict, kind: str, execution_count: int | None) -> None:
        text = data.get("text/plain")
        if kind == "page" and self.settings["paging"] != "none" and text is not None:
            self.open_pager(str(text), str((metadata or {}).get("title", "")))
            return
        if self.settings["images"] and kind != "page":
            image = self._image_of(data)
            if image is not None:
                self.transcript.close_line()
                if kind == "execute_result" and execution_count is not None:
                    self.transcript.append(f"Out[{execution_count}]:\n", "result")
                self.transcript.append_image(image)
                return
        if text is None and "text/html" in data:
            text = _html_as_text(data["text/html"])
        if text is None:
            mime = next(iter(data), "")
            text = f"<{mime}>" if mime else ""
        if not text:
            return
        self.transcript.close_line()
        if kind == "execute_result" and execution_count is not None:
            self.transcript.append(f"Out[{execution_count}]: {text}\n", "result")
        else:
            self.transcript.append(text + "\n", "stdout")

    def _image_of(self, data: dict) -> InlineImage | None:
        """The bundle's image, decoded: PNG, then JPEG, then SVG rasterised; else ``None``."""
        for mime, fmt in (("image/png", "png"), ("image/jpeg", "jpeg")):
            if mime in data:
                try:
                    return InlineImage(_as_bytes(data[mime]), fmt)
                except Exception as exc:  # noqa: BLE001 - say so, show the text form
                    self.transcript.append(
                        tr("could not decode the {fmt} image: {error}").format(fmt=fmt, error=exc)
                        + "\n",
                        "stderr",
                    )
                    return None
        if "image/svg+xml" in data:
            from emtk.svg import svg_to_png

            svg = data["image/svg+xml"]
            try:
                return InlineImage(svg_to_png(svg.encode("utf-8") if isinstance(svg, str) else svg))
            except Exception as exc:  # noqa: BLE001
                self.transcript.append(
                    tr("could not draw the SVG image: {error}").format(error=exc) + "\n", "stderr"
                )
        return None

    def copy_image(self, image: InlineImage) -> bool:
        """*Copy image*: put *image* on the system clipboard as a PNG."""
        from emtk import clipboard

        data = image.data
        if image.fmt != "png":
            from emtk.testing import png_encode

            data = png_encode(image.width, image.height, image.texture.px)
        return clipboard.copy_image(data)

    def save_image(self, image: InlineImage, path: str | os.PathLike | None = None) -> None:
        """*Save image as…*: write *image* to *path*, or ask where with a file dialog."""
        if path is not None:
            pathlib.Path(path).write_bytes(image.data)
            return
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title = tr("Save image")
        self.file_dialog = FileDialog(title, mode="save", filename=f"figure.{image.fmt}")
        self._file_window = DialogWindow(title, size=(760, 540))
        self._saving = image

    def _edit_file(self, path: str, line: int = 0) -> None:
        self.transcript.append(f"{path}:{line}\n", "message")

    # ── execution ─────────────────────────────────────────────────────────

    @property
    def input_text(self) -> str:
        """What is typed in the input box."""
        return self.control.input.text

    def set_input(self, text: str) -> None:
        """Replace the input with *text*, the caret at its end."""
        editor = self.control.input
        editor.set_text(str(text))
        editor.set_cursor(editor.document.bottom())

    def execute(self, source: str, *, echo: bool = True, hidden: bool = False):
        """Run *source* in the console's namespace; its output goes to the transcript.

        Parameters
        ----------
        source : str
        echo : bool, optional
            Write the source under the prompt first.
        hidden : bool, optional
            Neither record nor show it (the start-up snippet).

        Returns
        -------
        ExecutionResult
        """
        source = str(source)
        if echo and not hidden:
            self._echo(source)
        result = self.engine.run_cell(source, store_history=not hidden, silent=hidden)
        self._ran = self._ran or not hidden
        self.transcript.close_line()
        if not hidden and source.strip():
            self._log_code(source)
        self._history_index = None
        pending = getattr(self.engine, "_next_input", None)
        if pending:
            self.engine._next_input = None
            self.set_input(pending[0])
        if self._tour is not None and not hidden:
            self._tour.notify_used(VIEW_KEY)
        return result

    def _echo(self, source: str) -> None:
        self.transcript.close_line()
        prompt = PROMPT.format(n=self.engine.execution_count)
        lines = source.split("\n")
        self.transcript.append(prompt + lines[0] + "\n", "input")
        for line in lines[1:]:
            self.transcript.append(CONTINUATION + line + "\n", "input")

    def submit(self, *, force_newline: bool = False) -> None:
        """Enter: run a complete input, continue an incomplete one (indented)."""
        from chisurf.core.console.transform import indent_hint

        source = self.input_text
        if force_newline:
            self.control.input.insert("\n" + indent_hint(source))
            return
        status, indent = self.engine.check_complete(source)
        if status == "incomplete":
            editor = self.control.input
            editor.set_cursor(editor.document.bottom())
            editor.insert("\n" + indent)
            return
        self.set_input("")
        self.dismiss_popups()
        self.close_pager()
        self.execute(source)

    def _log_code(self, source: str) -> None:
        """Append *source* to the session log and, while recording, to the macro."""
        text = source if source.endswith("\n") else source + "\n"
        if self.session_file is not None:
            with contextlib.suppress(OSError):
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.session_file, "a+", encoding="utf-8", errors="ignore") as handle:
                    handle.write(text)
        if self.recording:
            self._macro += text

    # ── the macro channel (chisurf.run / chisurf.log) ─────────────────────

    def run_threadsafe(self, code: str | None = None):
        """``chisurf.run(code)``: record it in the history and run it here (queued from a worker)."""
        if code is None:
            return None
        code = str(code)
        if threading.get_ident() != self._thread:
            self._queue.append(("run", code))
            if self.wake is not None:
                self.wake()
            return None
        return self._run_recorded(code)

    def _run_recorded(self, code: str):
        first = (code.splitlines() or [code])[0]
        summary = f"run command: {first[:120]}"
        try:
            from chisurf.core.actions import record_action

            record_action(action_type="run_command", summary=summary, payload={"code": code})
        except Exception:  # noqa: BLE001 - a history that cannot record must not stop the command
            _log.debug("recording %r failed", summary, exc_info=True)
        if self.record_command is not None:
            with contextlib.suppress(Exception):
                self.record_command(summary)
        return self.execute(code)

    def log_threadsafe(self, code: str | None = None) -> None:
        """``chisurf.log(code)``: record *code* (session log, macro) without running it."""
        if not code:
            return
        if threading.get_ident() != self._thread:
            self._queue.append(("log", str(code)))
            if self.wake is not None:
                self.wake()
            return
        self._log_code(str(code))

    #: The Qt console's spellings, used across ChiSurf (``chisurf.console.execute_on_gui_thread``).
    execute_on_gui_thread = run_threadsafe
    execute_threadsafe = run_threadsafe
    log_on_gui_thread = log_threadsafe

    def poll(self) -> None:
        """Once per frame: run what workers queued through ``chisurf.run``."""
        while self._queue:
            kind, code = self._queue.popleft()
            if kind == "run":
                self._run_recorded(code)
            else:
                self._log_code(code)

    def install(self) -> None:
        """Make this console the process's ``chisurf.run`` / ``chisurf.log`` / ``chisurf.console``."""
        import chisurf

        if self._installed is None:
            self._installed = {
                name: getattr(chisurf, name, None) for name in ("run", "log", "console")
            }
        chisurf.run = self.run_threadsafe
        chisurf.log = self.log_threadsafe
        chisurf.console = self

    def uninstall(self) -> None:
        """Give ``chisurf.run`` / ``log`` / ``console`` back what they were (if they are still ours)."""
        import chisurf

        if self._installed is None:
            return
        ours = {"run": self.run_threadsafe, "log": self.log_threadsafe, "console": self}
        for name, previous in self._installed.items():
            if getattr(chisurf, name, None) != ours[name]:
                continue  # replaced since by someone else: theirs now
            if previous is None and name == "log":
                with contextlib.suppress(AttributeError):
                    delattr(chisurf, name)
            else:
                setattr(chisurf, name, previous)
        self._installed = None

    # ── macros ────────────────────────────────────────────────────────────

    def start_recording(self) -> None:
        """Begin collecting executed code into a macro."""
        self._macro = ""
        self.recording = True

    def stop_recording(self) -> None:
        """Stop collecting."""
        self.recording = False

    @property
    def macro(self) -> str:
        """The code recorded so far."""
        return self._macro

    def save_macro(self, filename: str | os.PathLike) -> str:
        """Write the recorded macro to *filename* (zipped when it ends in ``.zip``); its path."""
        import chisurf.core.fio as io

        self.stop_recording()
        with io.zipped.open_maybe_zipped(filename=str(filename), mode="w") as handle:
            handle.write(self._macro)
        return str(filename)

    def run_file(self, path: str | os.PathLike) -> Any:
        """Run a Python file in the console's namespace (``%run -i``), as *Run Macro…* does."""
        return self.execute(f"%run -i {pathlib.Path(path).as_posix()!r}")

    run_macro = run_file

    # ── keys ──────────────────────────────────────────────────────────────

    def claims(self, key: int, modifiers: int) -> bool:
        """Whether the console takes this chord before the shell's menu shortcuts (Ctrl+R, Ctrl+L, …)."""
        letter = letter_of(key, "")
        return _chord(modifiers) and letter in ("a", "c", "d", "e", "k", "l", "r", "u", "y")

    def handle_key(self, key: int, text: str, modifiers: int) -> bool:
        """The console's own keys; ``False`` lets the key edit the focused box."""
        from emtk.events import SHIFT_MODIFIER

        control = self.control
        shift = bool(modifiers & SHIFT_MODIFIER)
        chord = _chord(modifiers)
        letter = letter_of(key, text) if chord else ""
        if self.completions:
            if key in (KEY_UP, KEY_DOWN):
                step = -1 if key == KEY_UP else 1
                self.completion_index = (self.completion_index + step) % len(self.completions)
                return True
            if key in _ENTER or key == KEY_TAB:
                self.accept_completion(self.completion_index)
                return True
            if key == KEY_ESCAPE:
                self.completions = []
                return True
            self.completions = []
        if key == KEY_ESCAPE:
            if self.calltip_text:
                self.calltip_text = ""
            elif self.pager_title:
                self.close_pager()
            return True
        if letter == "c":
            target = control._editor()
            if target.selected_text():
                target.copy()
            else:
                self.interrupt()
            return True
        if letter == "l":
            self.clear()
            return True
        if letter == "r":
            self.search_history()
            return True
        if control.target != "input":
            if key in (KEY_PAGE_UP, KEY_PAGE_DOWN):
                control.scroll(-10 if key == KEY_PAGE_UP else 10)
                return True
            return False
        editor = control.input
        pos = editor.cursors.main.end
        if key in _ENTER:
            # Ctrl+Enter is Enter, as in the Qt console; Shift+Enter always adds a line.
            self.submit(force_newline=shift and not chord)
            return True
        if key == KEY_TAB:
            before = editor.document.get_line_text(pos.line)[: pos.index]
            if shift:
                if before and not before.strip():
                    editor.replace_section(Pos(pos.line, max(0, pos.index - 4)), pos, "")
                else:
                    self.show_calltip()
                return True
            if not before.strip():
                editor.insert(" " * (4 - len(before) % 4))
            else:
                self.show_completions()
            return True
        if key == KEY_UP and not shift and pos.line == 0:
            self.walk_history(-1)
            return True
        if key == KEY_DOWN and not shift and pos.line == len(editor.document) - 1:
            self.walk_history(+1)
            return True
        if key in (KEY_PAGE_UP, KEY_PAGE_DOWN):
            control.scroll(-10 if key == KEY_PAGE_UP else 10)
            return True
        line_text = editor.document.get_line_text(pos.line)
        if letter == "k":
            killed = line_text[pos.index :]
            if killed:
                self._kill_ring.append(killed)
                editor.replace_section(pos, Pos(pos.line, len(line_text)), "")
            return True
        if letter == "u":
            killed = line_text[: pos.index]
            if killed:
                self._kill_ring.append(killed)
                editor.replace_section(Pos(pos.line, 0), pos, "")
            return True
        if letter == "y":
            if self._kill_ring:
                editor.insert(self._kill_ring[-1])
            return True
        if letter == "a" or (key == KEY_HOME and not chord):
            editor.set_cursor(Pos(pos.line, 0)) if not shift else editor.move_home(select=True)
            return True
        if letter == "e" or (key == KEY_END and not chord):
            editor.set_cursor(Pos(pos.line, len(line_text))) if not shift else editor.move_end(
                select=True
            )
            return True
        if letter == "d":
            return not self.input_text.strip()
        return False

    def interrupt(self) -> None:
        """Ctrl+C without a selection: abandon the input (a cell runs on the frame, so none is running)."""
        if self.input_text.strip():
            self._echo(self.input_text)
            self.transcript.append("KeyboardInterrupt\n", "stderr")
        self.set_input("")
        self.dismiss_popups()

    # ── history ───────────────────────────────────────────────────────────

    def walk_history(self, direction: int) -> None:
        """Up (``-1``) / Down (``+1``) through the history, filtered by the prefix typed at the start."""
        entries = self.engine.history.entries
        if not entries:
            return
        if self._history_index is None:
            self._history_stash = self.input_text
            self._history_prefix = self.input_text
            self._history_index = len(entries)
        matches = [i for i, entry in enumerate(entries) if entry.startswith(self._history_prefix)]
        if not matches:
            matches = list(range(len(entries)))
        if direction < 0:
            earlier = [i for i in matches if i < self._history_index]
            position = earlier[-1] if earlier else None
        else:
            later = [i for i in matches if i > self._history_index]
            position = later[0] if later else None
        if position is None:
            if direction > 0:
                self._history_index = None
                self.set_input(self._history_stash)
            return
        self._history_index = position
        self.set_input(entries[position])

    def search_history(self) -> None:
        """Ctrl+R: the newest history entry containing what is typed."""
        needle = self.input_text.strip()
        matches = self.engine.history.search_substring(needle)
        if not matches:
            self.transcript.close_line()
            self.transcript.append(
                tr("(no history match for {needle})").format(needle=repr(needle)) + "\n", "stderr"
            )
            return
        self.set_input(matches[0])

    # ── completion, calltip, pager ────────────────────────────────────────

    def _line_and_cursor(self) -> tuple[str, int]:
        editor = self.control.input
        pos = editor.cursors.main.end
        return editor.document.get_line_text(pos.line), pos.index

    def show_completions(self) -> None:
        """Tab: complete what is typed; a list when the matches differ beyond their common prefix."""
        if self.settings["completion"] == "none":
            return
        line, cursor = self._line_and_cursor()
        result = self.engine.complete(line, cursor)
        if not result:
            return
        if result.common_prefix:
            typed = line[result.start : cursor]
            if len(result.common_prefix) > len(typed):
                self._replace(result.start, cursor, result.common_prefix)
                if len(result.matches) == 1:
                    return
                line, cursor = self._line_and_cursor()
        if len(result.matches) == 1:
            self._replace(result.start, cursor, result.matches[0])
            return
        self._completion = result
        self.completions = list(result.matches)
        self.completion_index = 0

    def accept_completion(self, index: int) -> None:
        """Put the completion at *index* in place of what it completes."""
        result = self._completion
        if result is None or not (0 <= index < len(self.completions)):
            self.completions = []
            return
        _line, cursor = self._line_and_cursor()
        self._replace(result.start, cursor, self.completions[index])
        self.completions = []
        self._completion = None

    def _replace(self, start: int, end: int, text: str) -> None:
        editor = self.control.input
        line = editor.cursors.main.end.line
        editor.replace_section(Pos(line, start), Pos(line, end), text)
        editor.set_cursor(Pos(line, start + len(text)))

    def show_calltip(self) -> None:
        """The signature of the call the caret is in, above the input."""
        if not self.settings["calltips"]:
            return
        from chisurf.core.console.introspect import calltip

        line, cursor = self._line_and_cursor()
        tip = calltip(line, cursor, self.engine.user_ns)
        if tip is None:
            self.calltip_text = ""
            return
        text = tip.signature or tip.name
        if tip.doc:
            text += "\n" + tip.doc.strip().split("\n\n")[0]
        self.calltip_text = text

    def dismiss_popups(self) -> None:
        """Close the completion list and the calltip."""
        self.completions = []
        self.calltip_text = ""

    def open_pager(self, text: str, title: str = "") -> None:
        """Show *text* in the pager under the transcript (``obj?``)."""
        from chisurf.core.console.ansi import strip_ansi

        self.pager_title = title or tr("Help")
        self.control.pager.set_text(strip_ansi(text))

    def close_pager(self) -> None:
        """Close the pager."""
        self.pager_title = ""
        if self.control.target == "pager":
            self.control.target = "input"

    # ── transcript and namespace ──────────────────────────────────────────

    def clear(self) -> None:
        """Clear the transcript (Ctrl+L, ``%clear``)."""
        self.transcript.clear()

    def push(self, variables: dict) -> None:
        """Add *variables* to the console's namespace."""
        self.engine.push(variables)

    pushVariables = push  # noqa: N815 - the Qt console's historic spelling

    def append_output(self, text: str, *, kind: str = "stdout") -> None:
        """Write *text* to the transcript."""
        self.transcript.append(str(text), kind)

    def append_message(self, text: str) -> None:
        """Write an informational line."""
        self.append_output(text if text.endswith("\n") else text + "\n", kind="message")

    def append_error(self, text: str) -> None:
        """Write an error line."""
        self.append_output(text if text.endswith("\n") else text + "\n", kind="stderr")

    printText = append_output  # noqa: N815 - historic spelling
    clearTerminal = clear  # noqa: N815 - historic spelling

    # ── the dock ──────────────────────────────────────────────────────────

    def _overlays(self):
        if self._help is None:
            from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

            self._help = EmTkHelpWindow(title=tr("ChiSurf console"), resource=HELP_FILE, owner=self)
            self._tour = EmTkGuidedTour(
                steps=GUIDE_FILE,
                owner=self,
                wait_for_controls=True,
                get_target_rect=lambda key: self.item_rects.get(key),
            )
        return self._help, self._tour

    def draw(self, box) -> None:
        """The Console dock: the ``?`` / *Guide* strip, then the console."""
        from chisurf.plugins.emtk_layout import action_button

        help_window, tour = self._overlays()
        if action_button("guide"):
            tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.host_control("##chinsole", self.control)
        self._image_menu()
        if self._focus_requested:
            # The keys come here from the next frame on, as a click on the console would do.
            self._focus_requested = False
            im.set_keyboard_focus_here(-1)
            self.control.has_focus = True
        self.item_rects[VIEW_KEY] = im.get_item_rect()
        for name in ("input", "output"):
            if name in self.control.boxes:
                self.item_rects[f"console.{name}"] = self.control.boxes[name]

    def _image_menu(self) -> None:
        """Right-click on an image: *Copy image*, *Save image as…*."""
        if im.is_item_hovered() and im.is_mouse_clicked(1):
            self._menu_image = self.control.image_at(*im.get_mouse_pos()[:2])
        image = self._menu_image
        if image is None or not im.begin_popup_context_item("##console.image"):
            return
        if im.menu_item(tr("Copy image")):
            self.copy_image(image)
            self._menu_image = None
        if im.menu_item(tr("Save image as…")):
            self.save_image(image)
            self._menu_image = None
        im.end_popup()

    def focus_input(self) -> None:
        """Give the console's input the keys (after *Macro ▸ Record*, a menu click took them)."""
        self._focus_requested = True
        self.control.target = "input"

    def draw_overlays(self, box) -> None:
        """The help window, the tour and the *Save image as…* dialog, over the whole shell."""
        if self.file_dialog is not None:
            closed = self._file_window.begin(box)
            paths = self.file_dialog.draw()
            self._file_window.end()
            if closed or paths is False:
                self.file_dialog = self._saving = None
            elif paths:
                image, self._saving, self.file_dialog = self._saving, None, None
                if image is not None:
                    try:
                        self.save_image(image, paths[0])
                    except OSError as exc:
                        self.append_error(tr("could not save the image: {error}").format(error=exc))
        if self._help is None:
            return
        self._help.draw(box)
        self._tour.draw(float(box[2]), float(box[3]))

    def close(self) -> None:
        """Save the history and give back ``chisurf.run``."""
        self.uninstall()
        if self._ran:
            with contextlib.suppress(Exception):
                self.engine.history.save()


__all__ = ["ConsoleControl", "InlineImage", "ShellConsole", "Transcript"]
