"""The one progress reporter in ChiSurf: :class:`ChiSurfProgress`.

Long operations used to report progress four different ways — a modal
``QProgressDialog``, a hand-rolled ``QProgressBar`` wired into a run button, the
navigation shell's shared status bar, or nothing at all — so the same
computation looked different depending on which window it was started from, and
headless it either popped an un-dismissable modal or went silent.

:class:`ChiSurfProgress` is the single entry point. The *caller* says what it is
doing; **where** that shows up is resolved from the widget it was given:

1. an inline AutoForm ``progress`` section (or any host exposing ``begin_task``)
   found by walking up from *parent* — the bar sits in the panel that started
   the work;
2. the navigation shell's shared status bar, when the tool is embedded in one;
3. a modal :class:`~chisurf.gui.widgets.progress.EnhancedProgressDialog`, when
   the tool runs standalone in its own window;
4. plain logging, when there is no GUI at all — so headless runs report
   progress in the log instead of blocking on a dialog nobody can close.

The handle duck-types the ``QProgressDialog`` surface (``setValue``,
``setLabelText``, ``setRange``, ``wasCanceled``, ``close``) *and* the status-bar
task surface (``set_value``, ``update_progress``, ``finish``), so migrating a
call site is a one-line change of where the handle comes from.

Examples
--------
Wrap a loop — the bar closes itself, even if the body raises::

    from chisurf.gui.progress import ChiSurfProgress

    with ChiSurfProgress(self, "Correlating…", len(files)) as bar:
        for i, path in enumerate(files):
            if bar.wasCanceled():
                break
            correlate(path)
            bar.update_progress(i + 1, f"Correlating {path}")

Or let it count for you::

    for path in ChiSurfProgress(self, "Correlating…").iterate(files):
        correlate(path)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["ChiSurfProgress", "progress", "find_progress_host"]


def find_progress_host(widget):
    """Return the nearest host that can render progress for *widget*.

    A host is any object with a ``begin_task(message, maximum, cancel)`` method:
    the AutoForm ``progress`` section, the navigation shell's status bar, or a
    tool implementing the same contract.

    The search climbs the parent chain and, at **each** level, also looks for a
    progress bar *inside* that level. That second step is what makes the common
    layout work without wiring: a run button and its bar are siblings in the same
    section, so the bar is never an ancestor of the button — it is found as a
    child of their shared parent. Climbing outward from there, the nearest
    enclosing section wins over the panel, which wins over the window-wide status
    bar.

    Parameters
    ----------
    widget : QWidget or None
        Widget the work was started from.

    Returns
    -------
    object or None
        The host, or ``None`` when the widget is not inside one.
    """
    from chisurf.gui.autoform.sections.progress_section import InlineProgressWidget

    node = widget
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if callable(getattr(node, "begin_task", None)):
            return node
        finder = getattr(node, "findChild", None)
        if callable(finder):
            try:
                bar = finder(InlineProgressWidget)
            except Exception:
                bar = None
            if bar is not None:
                return bar
        node = getattr(node, "parent", lambda: None)()
    try:
        window = widget.window() if widget is not None else None
    except Exception:
        window = None
    if window is not None and id(window) not in seen:
        if callable(getattr(window, "begin_task", None)):
            return window
    return _status_bar_host(window)


def _status_bar_host(window):
    """Return a lazily-created status-bar progress host for a tool *window*.

    Without this, a standalone tool window — one that is not embedded in the
    navigation shell and has no inline ``progress`` section — falls all the way
    through to a **modal dialog**. That is the right answer for work that runs
    on the GUI thread and blocks it anyway, and the wrong one for work moved off
    the GUI thread precisely so the window stays usable: the modal takes back
    everything the threading just bought. A ``QMainWindow`` already has a status
    bar, so progress lands there instead, beside the tool's declared messages.

    Parameters
    ----------
    window : QWidget or None
        The tool's top-level window.

    Returns
    -------
    object or None
        A host exposing ``begin_task``, or ``None`` when *window* is not a
        ``QMainWindow``.
    """
    from chisurf.gui import QtWidgets

    if not isinstance(window, QtWidgets.QMainWindow):
        return None
    host = getattr(window, "_chisurf_status_progress", None)
    if host is None:
        from chisurf.gui.widgets.progress import StatusBarProgressHost

        try:
            host = StatusBarProgressHost(window)
        except Exception:
            logger.debug("could not attach a status-bar progress host", exc_info=True)
            return None
        window._chisurf_status_progress = host
    return host


class _LoggingBackend:
    """Progress "display" for runs with no GUI: the log.

    Emits a record whenever the reported percentage crosses a whole ten percent,
    so a headless batch leaves a trace of how far it got without flooding the
    log with one line per item.
    """

    def __init__(self, message: str, maximum: int) -> None:
        self._message = str(message)
        self._maximum = int(maximum)
        self._value = 0
        self._last_decile = -1
        logger.info("%s (0/%s)", self._message, self._maximum or "?")

    def setLabelText(self, text: str) -> None:  # noqa: N802 (Qt-style)
        self._message = str(text)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        self._maximum = int(maximum)

    def setValue(self, value: int) -> None:  # noqa: N802
        self._value = int(value)
        if self._maximum <= 0:
            return
        decile = int(10 * self._value / self._maximum)
        if decile != self._last_decile:
            self._last_decile = decile
            logger.info("%s (%d/%d)", self._message, self._value, self._maximum)

    def value(self) -> int:
        return self._value

    def maximum(self) -> int:
        return self._maximum

    def wasCanceled(self) -> bool:  # noqa: N802
        return False

    def close(self) -> None:
        logger.info("%s — done", self._message)

    def finish(self, *args, **kwargs) -> None:
        self.close()


class ChiSurfProgress:
    """Report the progress of a long operation, wherever it is running.

    Parameters
    ----------
    parent : QWidget or None
        Widget the work was started from. Decides *where* progress is rendered
        (see the module docstring); ``None`` forces the standalone/headless
        path.
    text : str
        What the operation is doing, shown beside the bar.
    maximum : int
        Number of steps. ``0`` means "unknown" and renders a busy indicator.
    title : str
        Window caption, used only by the standalone modal dialog.
    cancellable : bool
        Whether the user is offered a Cancel button. When ``False`` the loop's
        :meth:`wasCanceled` never becomes ``True``.
    cancel : callable, optional
        Called when the user cancels. For work that runs in a *thread* this is
        how the stop is delivered (e.g. ``threading.Event().set``); a loop on the
        GUI thread can just poll :meth:`wasCanceled` instead. Passing it also
        implies ``cancellable``.
    autoclose : bool
        Close the display when the context manager exits (default ``True``).

    Attributes
    ----------
    backend : object
        The concrete display in use — a status-bar task, an inline AutoForm
        bar's task, an ``EnhancedProgressDialog``, or a :class:`_LoggingBackend`.
    """

    def __init__(self, parent=None, text: str = "", maximum: int = 0, *,
                 title: str = "Progress", cancellable: bool = True,
                 cancel=None, autoclose: bool = True) -> None:
        self._text = str(text)
        self._maximum = int(maximum)
        self._autoclose = bool(autoclose)
        self._cancel_cb = cancel
        self._canceled = False
        self._closed = False
        self._value = 0
        self.backend = self._make_backend(parent, title, cancellable or cancel is not None)

    # ── backend selection ───────────────────────────────────────────────────
    def _make_backend(self, parent, title: str, cancellable: bool):
        """Pick the most local display available for *parent*.

        Parameters
        ----------
        parent : QWidget or None
            Widget the work was started from.
        title : str
            Caption for the standalone dialog.
        cancellable : bool
            Whether to offer a Cancel button.

        Returns
        -------
        object
            The display backend.
        """
        host = find_progress_host(parent)
        if host is not None:
            try:
                cancel = self._request_cancel if cancellable else None
                return host.begin_task(self._text, self._maximum, cancel=cancel)
            except TypeError:
                # Hosts predating the ``cancel`` keyword (plain status bars).
                try:
                    return host.begin_task(self._text, self._maximum)
                except Exception:
                    logger.debug("progress host %r rejected begin_task", host, exc_info=True)
            except Exception:
                logger.debug("progress host %r failed", host, exc_info=True)

        from chisurf.gui.dialogs import is_interactive

        if is_interactive():
            from chisurf.gui.widgets.progress import EnhancedProgressDialog

            dialog = EnhancedProgressDialog(
                title, self._text, 0, self._maximum, parent if parent is not None else None
            )
            if not cancellable:
                dialog.setCancelButton(None)
            else:
                # The dialog's own Cancel only flips wasCanceled(); routing it
                # here is what delivers the stop to threaded work.
                try:
                    dialog.canceled.connect(self._request_cancel)
                except Exception:
                    logger.debug("progress dialog has no canceled signal", exc_info=True)
            dialog.show()
            return dialog
        return _LoggingBackend(self._text, self._maximum)

    def _request_cancel(self) -> None:
        """Mark the operation canceled and tell the work, if it asked to know."""
        self._canceled = True
        if callable(self._cancel_cb):
            try:
                self._cancel_cb()
            except Exception:
                logger.warning("progress cancel callback failed", exc_info=True)

    def _call(self, name: str, *args) -> None:
        """Invoke *name* on the backend when it has it, ignoring failures.

        Backends implement overlapping but not identical surfaces, and a Qt
        display can be deleted underneath a still-running loop; neither is worth
        aborting the computation for.

        Parameters
        ----------
        name : str
            Method to call on :attr:`backend`.
        *args
            Positional arguments for that method.
        """
        method = getattr(self.backend, name, None)
        if not callable(method):
            return
        try:
            method(*args)
        except RuntimeError:  # the Qt object was deleted
            self._closed = True
        except Exception:
            logger.debug("progress backend %s(%r) failed", name, args, exc_info=True)

    # ── driving the bar ─────────────────────────────────────────────────────
    def set_text(self, text: str) -> None:
        """Change the message shown beside the bar."""
        self._text = str(text)
        self._call("setLabelText", self._text)

    def set_range(self, minimum: int, maximum: int) -> None:
        """Set the step range; ``(0, 0)`` renders a busy indicator."""
        self._maximum = int(maximum)
        self._call("setRange", int(minimum), int(maximum))

    def set_maximum(self, maximum: int) -> None:
        """Set the number of steps."""
        self.set_range(0, int(maximum))

    def set_value(self, value: int) -> None:
        """Report that *value* steps are done."""
        self._value = int(value)
        self._call("setValue", self._value)
        self._process_events()

    def value(self) -> int:
        """Return the number of steps reported so far."""
        return self._value

    def maximum(self) -> int:
        """Return the number of steps the operation was declared to have."""
        return self._maximum

    def step(self, count: int = 1, text: str | None = None) -> None:
        """Advance by *count* steps, optionally changing the message.

        Parameters
        ----------
        count : int
            How many steps to advance.
        text : str, optional
            New message.
        """
        self.update_progress(self._value + int(count), text)

    def update_progress(self, value: int, text: str | None = None) -> None:
        """Set the value and (optionally) the message in one call."""
        if text is not None:
            self.set_text(text)
        self.set_value(value)

    def update_text(self, text: str) -> None:
        """Alias of :meth:`set_text` (``EnhancedProgressDialog`` spelling)."""
        self.set_text(text)

    def was_canceled(self) -> bool:
        """Whether the user asked to stop.

        Returns
        -------
        bool
            ``True`` once Cancel was pressed. Loops should check it each
            iteration and break; nothing is interrupted for them.
        """
        if self._canceled:
            return True
        checker = getattr(self.backend, "wasCanceled", None)
        if callable(checker):
            try:
                self._canceled = bool(checker())
            except Exception:
                return False
        return self._canceled

    def cancel(self) -> None:
        """Mark the operation canceled from code (as if Cancel were pressed)."""
        self._request_cancel()

    def close(self) -> None:
        """Take the progress display down. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        for name in ("finish", "close"):
            if callable(getattr(self.backend, name, None)):
                self._call(name)
                break

    def finish(self, final_text: str | None = None, **options) -> None:
        """Fill the bar, show a closing message, and take the display down.

        Parameters
        ----------
        final_text : str, optional
            Last message to show before the display goes away.
        **options
            ``auto_close`` / ``wait_for_user`` / ``close_delay_ms``, forwarded to
            a modal dialog backend that can linger on the final message. The
            inline and status-bar displays release immediately — a bar sitting in
            a panel has nothing to linger for — and ignore them.
        """
        if final_text is not None:
            self.set_text(final_text)
        if self._maximum:
            self.set_value(self._maximum)
        if self._closed:
            return
        self._closed = True
        backend_finish = getattr(self.backend, "finish", None)
        if not callable(backend_finish):
            self._call("close")
            return
        try:
            backend_finish(**options) if options else backend_finish()
        except TypeError:
            # A backend with the simpler finish() signature.
            self._call("finish")
        except RuntimeError:
            pass
        except Exception:
            logger.debug("progress backend finish failed", exc_info=True)

    def finalize(self, force_auto_close=None) -> None:
        """Close the display right now, cancelling any pending linger timer.

        Parameters
        ----------
        force_auto_close : bool, optional
            Forwarded to a modal dialog backend; ignored by the others.
        """
        self._closed = True
        backend_finalize = getattr(self.backend, "finalize", None)
        if callable(backend_finalize):
            try:
                backend_finalize(force_auto_close)
                return
            except TypeError:
                pass
            except RuntimeError:
                return
        self._closed = False
        self.close()

    # ── Qt-compatible spellings, so migrated call sites need no edits ───────
    setValue = set_value  # noqa: N815
    setLabelText = set_text  # noqa: N815
    setRange = set_range  # noqa: N815
    setMaximum = set_maximum  # noqa: N815
    wasCanceled = was_canceled  # noqa: N815

    def setMinimumDuration(self, *args) -> None:  # noqa: N802, D102
        """Accept (and ignore) the ``QProgressDialog`` call; shown immediately."""

    def setWindowTitle(self, title: str) -> None:  # noqa: N802
        """Retitle the standalone dialog; ignored by inline/status displays."""
        self._call("setWindowTitle", str(title))

    def setWindowModality(self, *args) -> None:  # noqa: N802
        """Accept (and ignore) the ``QProgressDialog`` call."""

    def setAutoClose(self, *args) -> None:  # noqa: N802
        """Accept (and ignore) the ``QProgressDialog`` call."""

    def setAutoReset(self, *args) -> None:  # noqa: N802
        """Accept (and ignore) the ``QProgressDialog`` call."""

    def setCancelButton(self, button=None) -> None:  # noqa: N802
        """Hide the Cancel button when passed ``None``; otherwise ignored."""
        if button is None:
            self._call("setCancelButton", None)

    def raise_(self) -> None:
        """Accept (and ignore) the ``QProgressDialog`` call; inline bars do not float."""

    def show(self) -> None:
        """Accept (and ignore) the ``QProgressDialog`` call; shown on creation."""

    # ── ergonomics ──────────────────────────────────────────────────────────
    def _process_events(self) -> None:
        """Let the display repaint during a busy loop, if there is one.

        Never re-enters itself: a pump delivers queued work — a worker thread's
        log record, another tool's progress update — which can call straight
        back in here. Each nested pump adds a Python-slot frame to the C stack,
        and a deep enough chain crashed inside ``QCoreApplication::postEvent``.
        Input stays enabled so the Cancel button remains clickable.
        """
        if isinstance(self.backend, _LoggingBackend):
            return
        from chisurf.gui.event_pump import pump_ui

        pump_ui()

    def iterate(self, iterable, text=None):
        """Yield from *iterable*, advancing the bar and stopping on Cancel.

        The range is taken from ``len(iterable)`` when it has one, so the common
        "loop over files" case needs no bookkeeping at the call site.

        Parameters
        ----------
        iterable : iterable
            Items to process.
        text : str or callable, optional
            A message, or ``f(item, index) -> str`` called per item to build one.

        Yields
        ------
        object
            Each item of *iterable*, until it is exhausted or Cancel is pressed.

        Examples
        --------
        >>> for path in ChiSurfProgress(self, "Reading…").iterate(files):  # doctest: +SKIP
        ...     read(path)
        """
        try:
            total = len(iterable)
        except TypeError:
            total = 0
        if total and total != self._maximum:
            self.set_range(0, total)
        try:
            for index, item in enumerate(iterable):
                if self.was_canceled():
                    break
                if callable(text):
                    self.set_text(text(item, index))
                elif text is not None:
                    self.set_text(str(text))
                yield item
                self.set_value(index + 1)
        finally:
            self.close()

    @staticmethod
    def run(*args, **kwargs):
        """Run work off the GUI thread against this progress seam.

        Convenience alias for :func:`chisurf.gui.task.run_in_background`, so the
        threaded form is discoverable from the class that reports it. See that
        function for the full contract.

        Examples
        --------
        ::

            ChiSurfProgress.run(
                self, "Correlating…", correlate_all, args=(paths,),
                maximum=len(paths), on_result=self._show_result,
            )
        """
        from chisurf.gui.task import run_in_background

        return run_in_background(*args, **kwargs)

    def __enter__(self) -> ChiSurfProgress:
        """Enter the context, returning the handle."""
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Close the display on the way out; never swallows an exception."""
        if self._autoclose:
            self.close()
        return False


def progress(parent=None, text: str = "", maximum: int = 0, **kwargs) -> ChiSurfProgress:
    """Create a :class:`ChiSurfProgress` — the function spelling of the class.

    Parameters
    ----------
    parent : QWidget or None
        Widget the work was started from.
    text : str
        What the operation is doing.
    maximum : int
        Number of steps (``0`` = unknown).
    **kwargs
        Forwarded to :class:`ChiSurfProgress`.

    Returns
    -------
    ChiSurfProgress
        A live progress handle.
    """
    return ChiSurfProgress(parent, text, maximum, **kwargs)
