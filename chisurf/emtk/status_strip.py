"""The emtk shell's status strip: the line at the bottom of the main window.

It is the emtk side of the Qt main window's status bar (``chisurf/gui/main.py``) and shows the
same things, fed by the same sources:

* on the left, the **message**: the newest ChiSurf log record that passes the log level, or
  the newest status line of the shell, its data docks or its project; with no message, the
  persistent label *Ready*. Messages go through ``tr`` and are cut with an ellipsis, the whole
  text on the tooltip (the Qt bar cuts in the middle, ``TruncatingStatusBar``);
* on the right, the **operation under way**: its text, a bar (a sliding segment while its size is
  unknown) and, when it can be cancelled, ✕. Hosts the progress-host contract: :meth:`begin_task`
  returns a handle with ``setLabelText`` / ``setRange`` / ``setValue`` / ``wasCanceled`` /
  ``finish`` / ``close``; the newest operation is the one shown.

The shell feeds it once per frame (:meth:`chisurf.emtk.main_app.EmtkShellApp.feed_status_strip`):
an API call under way on the data docks' worker, a sampling job on the server (with its
percentage and a ✕ that asks the server to stop) and the session's startup stages.

Log records arrive on any thread; the handler only assigns a string and asks for a frame.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from emtk import im
from emtk.i18n import mark, tr

#: Height of the strip, in logical pixels.
HEIGHT = 18.0
#: The persistent label (the Qt bar's ``status_label``).
READY = mark("Ready")
#: Width of the operation's text before it is cut (the Qt host's label keeps 240 px).
TASK_TEXT_WIDTH = 200.0
#: Width and height of the operation's bar (the Qt host's: 140 x 12).
BAR_SIZE = (120.0, 10.0)
#: How fast a busy bar's segment slides (bar widths per second).
BUSY_SPEED = 0.6


class StripTask:
    """One operation on the strip, driven through the progress-host contract.

    Parameters
    ----------
    strip : StatusStrip
        The strip showing it.
    message : str
        What the operation is doing.
    maximum : int
        Number of steps; ``0`` is unknown (a busy bar).
    cancel : callable, optional
        Called when the user presses ✕; without it no ✕ is drawn.
    """

    def __init__(
        self, strip: StatusStrip, message: str, maximum: int = 0, cancel: Callable | None = None
    ):
        self._strip = strip
        self.text = str(message)
        self._maximum = int(maximum)
        self._value = 0
        self._cancel = cancel
        self._cancelled = False

    @property
    def cancellable(self) -> bool:
        """Whether ✕ is offered."""
        return self._cancel is not None

    def setLabelText(self, text: str) -> None:  # noqa: N802 (the Qt progress surface)
        """Change the text beside the bar."""
        self.text = str(text)
        self._strip.wake()

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        """Set the step range; ``(0, 0)`` is a busy bar."""
        self._maximum = int(maximum)
        self._strip.wake()

    def setValue(self, value: int) -> None:  # noqa: N802
        """Report that *value* steps are done."""
        self._value = int(value)
        self._strip.wake()

    def value(self) -> int:
        """Steps reported so far."""
        return self._value

    def maximum(self) -> int:
        """Steps the operation declared (``0``: unknown)."""
        return self._maximum

    def wasCanceled(self) -> bool:  # noqa: N802
        """Whether the user pressed ✕."""
        return self._cancelled

    def finish(self, *_args, **_kwargs) -> None:
        """Take the operation off the strip."""
        self._strip._end(self)

    def close(self) -> None:
        """Take the operation off the strip."""
        self._strip._end(self)

    def request_cancel(self) -> None:
        """What ✕ does: record it and tell the work."""
        self._cancelled = True
        if callable(self._cancel):
            self._cancel()


class _StripLogHandler(logging.Handler):
    """Writes the newest record's message on the strip (any thread)."""

    def __init__(self, strip: StatusStrip) -> None:
        super().__init__(level=logging.INFO)
        self.strip = strip
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record).splitlines()[0] if record.getMessage() else ""
        except Exception:  # noqa: BLE001 - a log handler never raises
            return
        if text:
            self.strip.show_message(text)


class StatusStrip:
    """The message, the label and the operation under way; drawn by :meth:`draw`.

    Parameters
    ----------
    wake : callable, optional
        Asks the host for a frame (a log record or a task's progress arrived).
    """

    def __init__(self, wake: Callable[[], None] | None = None) -> None:
        self._wake = wake
        self._lock = threading.Lock()
        #: The persistent label shown when there is no message.
        self.label = READY
        self._message = ""
        self._deadline: float | None = None
        #: ``source -> text`` of the status lines followed, as of the last frame.
        self._followed: dict[str, str] = {}
        self._tasks: list[StripTask] = []
        self._handler: _StripLogHandler | None = None
        #: The controls drawn last frame: ``[{"kind", "text", "tooltip", ...}]``, left to right.
        self.drawn: list[dict] = []
        #: ``key -> (x, y, w, h)`` of what was drawn last frame (``status.message``, ``status.task``,
        #: ``status.bar``, ``status.cancel``).
        self.item_rects: dict[str, tuple] = {}

    # -- sources ------------------------------------------------------------ #
    def wake(self) -> None:
        """Ask for a frame."""
        if callable(self._wake):
            self._wake()

    def install(self) -> None:
        """Show log records on the strip (the root logger, as the Qt shell's status bar does)."""
        if self._handler is None:
            self._handler = _StripLogHandler(self)
            logging.getLogger().addHandler(self._handler)

    def close(self) -> None:
        """Stop showing log records."""
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    def show_message(self, text: str, timeout: int = 0) -> None:
        """Show *text* until the next message (or *timeout* ms); the Qt bar's ``showMessage``."""
        with self._lock:
            self._message = str(text)
            self._deadline = time.monotonic() + timeout / 1000.0 if timeout > 0 else None
        self.wake()

    def clear_message(self) -> None:
        """Back to the label."""
        with self._lock:
            self._message = ""
            self._deadline = None

    def follow(self, source: str, text: str) -> None:
        """A status line the shell keeps: when *source*'s *text* changed, it is the message."""
        text = str(text or "")
        if self._followed.get(source) != text:
            self._followed[source] = text
            if text in (self.label, tr(self.label)):
                # "Ready" is the label the strip falls back to, not news.
                self.clear_message()
            elif text:
                self.show_message(text)

    @property
    def message(self) -> str:
        """The message shown now (``""`` once its timeout passed)."""
        with self._lock:
            if self._deadline is not None and time.monotonic() > self._deadline:
                self._message, self._deadline = "", None
            return self._message

    # -- operations ---------------------------------------------------------- #
    def begin_task(self, message: str, maximum: int = 0, cancel: Callable | None = None) -> StripTask:
        """Start showing an operation; returns its handle. The newest one is shown."""
        task = StripTask(self, message, maximum, cancel)
        self._tasks.append(task)
        self.wake()
        return task

    def _end(self, task: StripTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
            self.wake()

    @property
    def task(self) -> StripTask | None:
        """The operation shown (the newest under way)."""
        return self._tasks[-1] if self._tasks else None

    def animating(self) -> bool:
        """Whether a busy bar is sliding (frames must keep coming)."""
        task = self.task
        return task is not None and task.maximum() <= 0

    # -- drawing -------------------------------------------------------------- #
    def controls(self) -> list[dict]:
        """What a user sees on the strip, as the Qt before-half records it (``kind``, ``text``, ...)."""
        message = self.message
        found = [
            {"kind": "message", "text": tr(message), "tooltip": ""}
            if message
            else {"kind": "label", "text": tr(self.label), "tooltip": ""}
        ]
        task = self.task
        if task is not None:
            found.append({"kind": "label", "text": tr(task.text), "tooltip": tr(task.text)})
            found.append(
                {
                    "kind": "progress",
                    "text": "",
                    "tooltip": "",
                    "value": task.value(),
                    "maximum": task.maximum(),
                }
            )
            if task.cancellable:
                found.append({"kind": "button", "text": "✕", "tooltip": tr("Cancel")})
        return found

    def draw(self, box) -> None:
        """Draw the strip into the current window, whose content region is *box* ``(x, y, w, h)``."""
        x, y, width, height = (float(v) for v in box)
        self.item_rects = {}
        self.drawn = self.controls()
        task = self.task
        spacing = 8.0
        task_width = 0.0
        if task is not None:
            task_width = TASK_TEXT_WIDTH + spacing + BAR_SIZE[0] + spacing
            task_width += im.get_frame_height() if task.cancellable else 0.0
        # The line centred in the strip, a gutter in from the window's left edge.
        im.set_cursor_screen_pos((x + 8.0, y + max(0.0, (height - im.get_frame_height()) * 0.5)))
        im.align_text_to_frame_padding()
        message = self.message
        shown = tr(message) if message else tr(self.label)
        im.text_ellipsis(shown, max(40.0, width - task_width - 3 * spacing))
        self.item_rects["status.message"] = im.get_item_rect()
        if task is None:
            return
        left = x + width - task_width
        im.same_line()
        im.set_cursor_screen_pos((left, im.get_cursor_screen_pos()[1]))
        text = " · ".join(part.strip() for part in tr(task.text).splitlines() if part.strip())
        im.text_ellipsis(text, TASK_TEXT_WIDTH)
        im.set_item_tooltip(text)
        self.item_rects["status.task"] = im.get_item_rect()
        im.same_line(0.0, spacing)
        # Centre the thin bar on the text line.
        _cx, cy = im.get_cursor_screen_pos()
        offset = max(0.0, (im.get_frame_height() - BAR_SIZE[1]) * 0.5)
        im.set_cursor_screen_pos((left + TASK_TEXT_WIDTH + spacing, cy + offset))
        if task.maximum() > 0:
            fraction = task.value() / float(task.maximum())
        else:
            fraction = -BUSY_SPEED * time.monotonic()
        im.progress_bar(fraction, BAR_SIZE)
        self.item_rects["status.bar"] = im.get_item_rect()
        if task.cancellable:
            im.same_line(0.0, spacing)
            im.set_cursor_screen_pos((im.get_cursor_screen_pos()[0], cy))
            if im.small_button("✕##status.cancel"):
                task.request_cancel()
            im.set_item_tooltip(tr("Cancel"))
            self.item_rects["status.cancel"] = im.get_item_rect()


def strip_rect(width: float, height: float) -> tuple[float, float, float, float]:
    """Where the strip sits in a *width* x *height* window: along the bottom edge."""
    return (0.0, max(0.0, height - HEIGHT), width, HEIGHT)


def draw_strip(strip: StatusStrip, width: float, height: float) -> None:
    """Draw *strip* as its own undecorated window along the bottom of the viewport."""
    x, y, w, h = strip_rect(width, height)
    im.set_next_window_pos((x, y), im.Cond.ALWAYS)
    im.set_next_window_size((w, h), im.Cond.ALWAYS)
    flags = (
        im.WindowFlags.NO_TITLE_BAR
        | im.WindowFlags.NO_RESIZE
        | im.WindowFlags.NO_SCROLLBAR
        | im.WindowFlags.NO_SCROLL_WITH_MOUSE
        | im.WindowFlags.NO_SAVED_SETTINGS
    )
    if im.begin("shell status", flags=flags):
        strip.draw((x, y, w, h))
    im.end()


def stage_task_text(payload: dict[str, Any]) -> str:
    """The text of a startup stage on the strip (its label, untranslated)."""
    return str(payload.get("label") or payload.get("id") or "")
