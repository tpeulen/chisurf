"""Run work off the GUI thread against the existing progress seam.

:class:`~chisurf.gui.progress.ChiSurfProgress` already answers "where does this
show up" — an inline AutoForm ``progress`` section, the shell's status bar, a
modal dialog, or the log when there is no GUI — and it already carries
cancellation. What it does not do is *run* anything: it assumes the caller
drives a loop on the GUI thread, or has already started a thread and marshals
updates itself. So every long operation that wanted to stay responsive grew its
own executor, its own cancel flag and its own way of getting results back, and
none of them agreed.

:func:`run_in_background` is the missing half, and it reuses the display seam
rather than adding a fifth one. The caller says what to run and what to do with
the answer; the worker gets one object to report through:

    def correlate_all(paths, task):
        out = []
        for i, path in enumerate(paths):
            if task.is_cancelled:
                break
            out.append(correlate(path))
            task.set_progress(i + 1, f"Correlating {path.name}")
            task.set_partial(out[-1])          # the plot fills in as it goes
        return out

    run_in_background(
        self, "Correlating…", correlate_all, args=(paths,), maximum=len(paths),
        on_partial=self._append_curve,
        on_result=self._show_result,
        on_error=self.Error.correlation_failed,
    )

What the caller gets for free, and what each of these is worth:

* **Every callback runs on the GUI thread.** The worker's updates cross back
  through a queued signal, so a worker may touch neither widgets nor plots and
  the caller need not care that it is on another thread.
* **Partial results.** A long computation streams what it has, so the plot fills
  in progressively instead of freezing and then jumping.
* **One run per owner.** Starting a task cancels the owner's previous one and
  disconnects it first, so a late result from a superseded run cannot land in
  the GUI after a newer one — the defect that makes double-clicking a Compute
  button show the wrong answer.
* **Cancellation is pushed, not polled.** The progress display's Cancel sets the
  task's flag; the worker sees it in ``is_cancelled``. A flag the worker never
  reads would let the run continue to the end, so cooperative checks stay the
  worker's job — but there is exactly one flag to check.
* **Headless is the same code.** With no ``QApplication`` the work runs inline
  and the callbacks fire in order, so a CLI or a test exercises the call site
  rather than a mock of it.

Starting a task from ``on_result``/``on_error``/``on_done`` is refused: the
handler runs while the finishing task is still being torn down, and the usual
consequence is that the new task is cancelled by the very teardown that started
it. Schedule it with a zero-timer instead.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
import typing
import weakref

from chisurf.gui import QtCore, QtWidgets
from chisurf.gui.progress import ChiSurfProgress

__all__ = ["TaskHandle", "Task", "run_in_background"]

logger = logging.getLogger(__name__)

#: One worker: these tasks are user-facing operations, not a compute pool. Work
#: that wants many cores parallelises inside its own function.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="chisurf-task"
)

#: owner widget -> its running task, so a new run supersedes the old one.
_RUNNING: "weakref.WeakKeyDictionary[object, Task]" = weakref.WeakKeyDictionary()


class _Bridge(QtCore.QObject):
    """Carries a worker's updates to the GUI thread.

    Every signal is connected queued, which is what makes the callbacks safe to
    touch widgets from: the emit returns immediately in the worker and the slot
    runs in the thread that owns this object.
    """

    progressed = QtCore.Signal(int, object)
    ranged = QtCore.Signal(int, int)
    texted = QtCore.Signal(str)
    partial = QtCore.Signal(object)
    completed = QtCore.Signal(object, object)  # (result, exception)


class TaskHandle:
    """What the worker function is handed: progress out, cancellation in.

    The worker receives it as its **last positional argument**. Every method is
    safe to call from the worker thread.
    """

    def __init__(self, bridge: _Bridge, cancelled: threading.Event, maximum: int):
        self._bridge = bridge
        self._cancelled = cancelled
        self._maximum = int(maximum)
        self._last_value = -1

    @property
    def is_cancelled(self) -> bool:
        """Whether the user asked to stop.

        Nothing is interrupted for the worker; it decides where stopping is
        safe. Check it at the top of each iteration.
        """
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        """Abandon the work at this point if the user cancelled.

        The resulting :class:`CancelledError` is swallowed by the task — no
        ``on_error`` fires — so this is the terse alternative to threading a
        ``break`` out of nested loops.
        """
        if self.is_cancelled:
            raise concurrent.futures.CancelledError()

    def set_progress(self, value: int, text: str | None = None) -> None:
        """Report *value* steps done, optionally changing the message.

        A repeated value is dropped rather than emitted: a tight loop reporting
        the same number thousands of times floods the event queue and makes the
        GUI *less* responsive than reporting nothing.
        """
        value = int(value)
        if value == self._last_value and text is None:
            return
        self._last_value = value
        self._bridge.progressed.emit(value, text)

    def set_fraction(self, fraction: float, text: str | None = None) -> None:
        """Report progress as a fraction in ``[0, 1]`` of the declared maximum."""
        if self._maximum:
            self.set_progress(round(fraction * self._maximum), text)
        elif text is not None:
            self.set_text(text)

    def set_range(self, minimum: int, maximum: int) -> None:
        """Re-scale the bar, for work that runs in phases of different length.

        ``(0, 0)`` is a busy indicator. A multi-phase run — read, then compute,
        then write — announces each phase's own length rather than inventing a
        common scale for all three.
        """
        self._maximum = int(maximum)
        self._last_value = -1
        self._bridge.ranged.emit(int(minimum), int(maximum))

    def set_text(self, text: str) -> None:
        """Change the message beside the bar without moving it."""
        self._bridge.texted.emit(str(text))

    def set_partial(self, value: typing.Any) -> None:
        """Hand an intermediate result to ``on_partial`` on the GUI thread."""
        self._bridge.partial.emit(value)

    def progress_window(self, label: str = "") -> "_ProgressWindowAdapter":
        """Return an object with the ``progress_window`` surface some cores take.

        Several Qt-free computation cores accept a "progress window" and call
        ``set_value(i)`` on it — written when the caller was a `QProgressDialog`
        on the GUI thread. Handing them this adapter moves the loop into a worker
        with no change to the core, and gives it cancellation it did not have:
        each ``set_value`` also checks whether the user asked to stop.
        """
        return _ProgressWindowAdapter(self, label)


class _ProgressWindowAdapter:
    """The ``set_value``/``setValue`` surface a core's ``progress_window`` needs."""

    def __init__(self, task: TaskHandle, label: str = ""):
        self._task = task
        self._label = label

    def set_value(self, value: int) -> None:
        """Report progress and check for cancellation."""
        self._task.raise_if_cancelled()
        self._task.set_progress(int(value), self._label or None)

    #: `QProgressDialog` spelling, for a core that uses it instead.
    setValue = set_value  # noqa: N815

    def set_text(self, text: str) -> None:
        """Change the message."""
        self._label = str(text)
        self._task.set_text(self._label)

    setLabelText = set_text  # noqa: N815

    def wasCanceled(self) -> bool:  # noqa: N802
        """Whether the user asked to stop (for a core that polls instead)."""
        return self._task.is_cancelled


class Task:
    """A running (or finished) background operation.

    Returned by :func:`run_in_background`. Callers rarely need it beyond
    :meth:`cancel` and, in tests, :meth:`wait`.
    """

    def __init__(self, progress: ChiSurfProgress, bridge: _Bridge,
                 cancelled: threading.Event, owner: object):
        self.progress = progress
        self._bridge = bridge
        self._cancelled = cancelled
        self._owner = owner
        self._future: concurrent.futures.Future | None = None
        self._done = threading.Event()
        #: True while the completion callbacks are running, which is what makes
        #: "no starting a task from on_done" detectable rather than mysterious.
        self._finishing = False
        self.result: typing.Any = None
        self.exception: BaseException | None = None

    @property
    def is_running(self) -> bool:
        """Whether the work is still going."""
        return not self._done.is_set()

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation was requested."""
        return self._cancelled.is_set()

    def cancel(self) -> None:
        """Ask the work to stop and take the progress display down."""
        self._cancelled.set()
        never_ran = self._future is not None and self._future.cancel()
        self.progress.close()
        if never_ran and not self._done.is_set():
            # The future was still queued, so `_work` will never run and would
            # never emit — leaving the task running forever: no `on_done`, no
            # bookkeeping, and anything awaiting it blocked forever. Complete it
            # here instead.
            self._bridge.completed.emit(None, concurrent.futures.CancelledError())

    def wait(self, timeout: float = 30.0) -> "Task":
        """Block until the task has finished *and* its callbacks have run.

        For tests and for CLI paths. Qt events are processed while waiting, so
        the queued callbacks actually arrive — a plain ``future.result()`` would
        return before ``on_result`` had been delivered.

        Parameters
        ----------
        timeout : float
            Seconds to wait before giving up.

        Returns
        -------
        Task
            This task, so ``run_in_background(...).wait().result`` reads well.
        """
        deadline = time.monotonic() + timeout
        app = QtWidgets.QApplication.instance()
        while not self._done.is_set() and time.monotonic() < deadline:
            if app is not None:
                app.processEvents()
            else:
                time.sleep(0.005)
        if app is not None:
            app.processEvents()  # drain the callbacks queued by the last emit
        return self

    def _record(self, result, exception) -> None:
        """Store the outcome; called on the GUI thread before the callbacks."""
        self.result = result
        self.exception = exception


def _disconnect(bridge: _Bridge, *signals) -> None:
    """Drop connections on *bridge*, ignoring an already-clean one.

    With no *signals* every connection goes.
    """
    for signal in signals or (
            bridge.progressed, bridge.ranged, bridge.texted, bridge.partial,
            bridge.completed):
        try:
            signal.disconnect()
        except (TypeError, RuntimeError):
            pass


def _disconnect_updates(bridge: _Bridge) -> None:
    """Silence a superseded task's updates but leave its completion connected.

    Its progress, text and partial results must stop reaching the GUI — that is
    the whole point of superseding it — but its completion still has to run, or
    the task never finishes its own bookkeeping and anything awaiting it blocks
    forever. The completion handler drops the *result* itself, because the task
    is cancelled.
    """
    _disconnect(bridge, bridge.progressed, bridge.ranged, bridge.texted, bridge.partial)


def run_in_background(
        parent,
        text: str,
        func: typing.Callable[..., typing.Any],
        *,
        args: tuple = (),
        kwargs: dict | None = None,
        maximum: int = 0,
        on_partial: typing.Callable[[typing.Any], None] | None = None,
        on_result: typing.Callable[[typing.Any], None] | None = None,
        on_error: typing.Callable[[BaseException], None] | None = None,
        on_done: typing.Callable[[], None] | None = None,
        title: str = "Progress",
        cancellable: bool = True,
        owner: object = None,
        synchronous: bool | None = None,
) -> Task:
    """Run *func* off the GUI thread, reporting through the progress seam.

    Parameters
    ----------
    parent : QWidget or None
        Widget the work was started from. Decides where progress is rendered —
        see :class:`~chisurf.gui.progress.ChiSurfProgress`.
    text : str
        What the operation is doing.
    func : callable
        The work. It is called as ``func(*args, task, **kwargs)`` — the
        :class:`TaskHandle` is the **last positional argument**, so a plain
        function keeps its own signature and simply grows one parameter.
    args, kwargs : tuple, dict
        Passed through to *func*.
    maximum : int
        Number of steps; ``0`` renders a busy indicator.
    on_partial : callable, optional
        Called on the GUI thread with each value the worker passes to
        :meth:`TaskHandle.set_partial`.
    on_result : callable, optional
        Called on the GUI thread with the return value, unless the work raised
        or was cancelled.
    on_error : callable, optional
        Called on the GUI thread with the exception. A declared message —
        ``self.Error.compute_failed`` — is exactly the right shape for this.
        Without one the traceback is logged.
    on_done : callable, optional
        Called on the GUI thread after the run, whatever the outcome, including
        cancellation. For re-enabling buttons.
    title : str
        Caption for the standalone modal display.
    cancellable : bool
        Whether the user is offered Cancel.
    owner : object, optional
        Key for the one-run-at-a-time rule; defaults to *parent*. Two unrelated
        operations in one panel that may legitimately overlap should pass
        distinct owners.
    synchronous : bool, optional
        Force inline execution (``True``) or threading (``False``). The default
        threads when a ``QApplication`` exists and runs inline when it does not,
        so headless callers exercise the same call site.

    Returns
    -------
    Task
        The running task.

    Raises
    ------
    RuntimeError
        If called from a completion callback (see the module docstring).
    """
    kwargs = dict(kwargs or {})
    owner = parent if owner is None else owner

    try:
        previous = _RUNNING.get(owner) if owner is not None else None
    except TypeError:
        # An owner that cannot be weak-referenced (a plain string key, say):
        # no single-flight for it, rather than a crash at the call site.
        previous = None
    if previous is not None:
        if getattr(previous, "_finishing", False):
            raise RuntimeError(
                "cannot start a task from a completion callback; the task being "
                "torn down would cancel it. Schedule it with QTimer.singleShot(0, ...)"
            )
        previous.cancel()
        _disconnect_updates(previous._bridge)

    cancelled = threading.Event()
    progress = ChiSurfProgress(
        parent, text, maximum,
        title=title, cancellable=cancellable, cancel=cancelled.set,
    )
    bridge = _Bridge()
    task = Task(progress, bridge, cancelled, owner)
    handle = TaskHandle(bridge, cancelled, maximum)

    def _on_progressed(value, message):
        if message is not None:
            progress.set_text(str(message))
        progress.set_value(int(value))

    def _on_ranged(minimum, maximum):
        progress.set_range(int(minimum), int(maximum))

    def _on_texted(message):
        progress.set_text(message)

    def _on_partial(value):
        if on_partial is not None:
            try:
                on_partial(value)
            except Exception:
                logger.exception("on_partial callback failed")

    def _on_completed(result, exception):
        task._finishing = True
        try:
            progress.close()
            task._record(result, exception)
            if isinstance(exception, concurrent.futures.CancelledError) or cancelled.is_set():
                pass
            elif exception is not None:
                if on_error is not None:
                    on_error(exception)
                else:
                    logger.error("background task failed: %s", exception, exc_info=exception)
            elif on_result is not None:
                on_result(result)
            if on_done is not None:
                on_done()
        finally:
            # The owner's slot is released only after its callbacks have run, so
            # a callback that tries to start the next task is caught rather than
            # started and then cancelled by this very teardown.
            task._finishing = False
            try:
                if owner is not None and _RUNNING.get(owner) is task:
                    del _RUNNING[owner]
            except TypeError:
                pass
            task._done.set()
            _disconnect(bridge)

    connection = QtCore.Qt.QueuedConnection
    bridge.progressed.connect(_on_progressed, connection)
    bridge.ranged.connect(_on_ranged, connection)
    bridge.texted.connect(_on_texted, connection)
    bridge.partial.connect(_on_partial, connection)
    bridge.completed.connect(_on_completed, connection)

    if owner is not None:
        try:
            _RUNNING[owner] = task
        except TypeError:  # an owner that cannot be weak-referenced
            pass

    def _work():
        try:
            value = func(*args, handle, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — reported, not swallowed
            bridge.completed.emit(None, exc)
        else:
            bridge.completed.emit(value, None)

    if synchronous is None:
        synchronous = QtWidgets.QApplication.instance() is None
    if synchronous:
        # No event loop to marshal through: connect directly so the callbacks
        # still fire, in order, on this thread.
        _disconnect(bridge)
        bridge.progressed.connect(_on_progressed)
        bridge.ranged.connect(_on_ranged)
        bridge.texted.connect(_on_texted)
        bridge.partial.connect(_on_partial)
        bridge.completed.connect(_on_completed)
        _work()
    else:
        task._future = _EXECUTOR.submit(_work)
    return task
