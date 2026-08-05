"""Move output from whatever thread produced it onto the GUI thread, in bounded batches.

Two problems are solved here, and both are what stops a console wedging the
application.

The first is threading: a background thread that calls ``print`` must not touch
a ``QTextDocument``. Writes are queued under a lock and the GUI thread is woken
once, on the empty-to-non-empty edge, rather than once per write -- so a tight
print loop does not also produce a signal storm.

The second is volume. ``while True: print(i)`` produces output faster than any
widget can render it. Draining a bounded amount per timer tick keeps the event
loop alive, and a per-cell budget stops the document growing without limit.
"""

from __future__ import annotations

import collections
import threading
import typing

from qtpy import QtCore

__all__ = ["OutputPump"]


class OutputPump(QtCore.QObject):
    """Batches console output and delivers it on the GUI thread.

    Parameters
    ----------
    sink : callable
        ``sink(stream_name, text)``, called on the GUI thread.
    interval_ms : int, optional
        How often the queue is drained.
    max_chunk : int, optional
        Characters delivered per tick.
    max_per_cell : int, optional
        Characters accepted from one cell before the rest is dropped. ``0``
        disables the limit.
    """

    #: Emitted on the GUI thread when a batch has been delivered.
    flushed = QtCore.Signal()
    #: Emitted with the number of characters dropped when a cell overruns.
    truncated = QtCore.Signal(int)

    _wake = QtCore.Signal()

    def __init__(
            self,
            sink: typing.Callable[[str, str], None],
            *,
            interval_ms: int = 30,
            max_chunk: int = 16_384,
            max_per_cell: int = 500_000,
            parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sink = sink
        self._max_chunk = max_chunk
        self._max_per_cell = max_per_cell

        self._queue: collections.deque[tuple[str, str]] = collections.deque()
        self._lock = threading.Lock()
        self._cell_chars = 0
        self._dropped = 0
        self._reported = False

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._drain)
        self._wake.connect(self._start_timer, QtCore.Qt.QueuedConnection)

    # ------------------------------------------------------------------
    # producer side -- any thread
    # ------------------------------------------------------------------

    def write(self, name: str, text: str) -> None:
        """Queue *text*. Safe to call from any thread.

        Parameters
        ----------
        name : str
            ``"stdout"`` or ``"stderr"``.
        text : str
        """
        if not text:
            return
        with self._lock:
            if self._max_per_cell and self._cell_chars >= self._max_per_cell:
                self._dropped += len(text)
                return
            self._cell_chars += len(text)
            was_empty = not self._queue
            self._queue.append((name, text))
        if was_empty:
            # Waking only on the edge is what keeps a tight print loop from
            # emitting one queued signal per write.
            self._wake.emit()

    # ------------------------------------------------------------------
    # consumer side -- GUI thread only
    # ------------------------------------------------------------------

    @QtCore.Slot()
    def _start_timer(self) -> None:
        """Start the drain timer, and drain once immediately."""
        self._drain()
        if not self._timer.isActive():
            self._timer.start()

    @QtCore.Slot()
    def _drain(self) -> None:
        """Deliver at most ``max_chunk`` characters to the sink."""
        delivered = 0
        batch: list[tuple[str, str]] = []
        with self._lock:
            while self._queue and delivered < self._max_chunk:
                name, text = self._queue.popleft()
                delivered += len(text)
                batch.append((name, text))
            empty = not self._queue

        # Coalesce runs from the same stream into one insertion; a line-buffered
        # writer otherwise produces one document edit per line.
        merged: list[tuple[str, str]] = []
        for name, text in batch:
            if merged and merged[-1][0] == name:
                merged[-1] = (name, merged[-1][1] + text)
            else:
                merged.append((name, text))

        for name, text in merged:
            self._sink(name, text)

        if merged:
            self.flushed.emit()
        if empty and self._timer.isActive():
            self._timer.stop()

    def flush_now(self) -> None:
        """Deliver everything queued, regardless of the chunk limit."""
        while True:
            with self._lock:
                if not self._queue:
                    break
            self._drain()

    # ------------------------------------------------------------------
    # cell boundaries
    # ------------------------------------------------------------------

    def begin_cell(self) -> None:
        """Reset the per-cell budget."""
        with self._lock:
            self._cell_chars = 0
            self._dropped = 0
            self._reported = False

    def end_cell(self) -> None:
        """Flush, and report anything the budget dropped."""
        self.flush_now()
        with self._lock:
            dropped = self._dropped
            report = dropped and not self._reported
            self._reported = True
        if report:
            self.truncated.emit(dropped)

    def drop_pending(self) -> int:
        """Discard queued output, for a Stop button.

        Returns
        -------
        int
            Characters discarded.
        """
        with self._lock:
            dropped = sum(len(text) for _name, text in self._queue)
            self._queue.clear()
        return dropped
