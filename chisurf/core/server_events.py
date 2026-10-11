"""The ChiSurf server's event stream, received without a GUI toolkit.

The server publishes every state change on a ZMQ PUB socket (``fit.created``,
``fit.ran``, ``fit.updated``, ``parameter.changed``, ``dataset.added``,
``session.cleared``, ...). A front end has to hear them on the thread that owns
its views, and must not block that thread while it waits.

:class:`ServerEventSubscriber` splits the two halves: a worker thread owns the
SUB socket (a ZMQ socket belongs to one thread), receives, decodes and queues
each event, and calls ``wake()`` -- an immediate-mode app's thread-safe
``request_frame`` -- so the owner draws a frame; the owner then calls
:meth:`~ServerEventSubscriber.drain` from its own thread, which runs the
callbacks registered with :meth:`~ServerEventSubscriber.subscribe` there.
Nothing here imports a GUI toolkit; the Qt shell's ``ZmqSubscriberPoller`` (a
timer that drains the client's own socket) is the Qt-hosted equivalent.

Topic matching is ZMQ's: a callback registered for ``"fit."`` receives
``fit.created`` and ``fit.updated``; ``""`` receives everything.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

_log = logging.getLogger(__name__)

__all__ = ["ServerEventSubscriber"]


class ServerEventSubscriber:
    """Queue the server's PUB events on a worker; dispatch them on the owner's thread.

    Parameters
    ----------
    pub_port : int
        TCP port of the server's PUB socket.
    host : str
        Server address (loopback by default, as the server only binds there).
    wake : callable, optional
        Called from the worker after it queued one or more events; it must be
        thread-safe (an emtk app's ``request_frame`` is).
    poll_ms : int
        How long the worker waits on the socket before checking for :meth:`stop`.
    topics : sequence of str
        ZMQ subscription prefixes; ``("",)`` receives everything and leaves the
        filtering to :meth:`subscribe`.
    """

    def __init__(
        self,
        pub_port: int,
        host: str = "127.0.0.1",
        *,
        wake: Callable[[], None] | None = None,
        poll_ms: int = 50,
        topics: tuple[str, ...] = ("",),
    ) -> None:
        self.pub_port = int(pub_port)
        self.host = str(host)
        self.wake = wake
        self.poll_ms = int(poll_ms)
        self.topics = tuple(topics)
        self._queue: deque[tuple[str, dict[str, Any]]] = deque()
        self._lock = threading.Lock()
        self._callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._running = threading.Event()
        self._connected = threading.Event()
        self._thread: threading.Thread | None = None
        #: How many events the worker received (for tests and diagnostics).
        self.received = 0

    # -- the owner's side ---------------------------------------------------- #
    def subscribe(self, prefix: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Run ``callback(payload)`` in :meth:`drain` for every topic starting with *prefix*."""
        self._callbacks.setdefault(str(prefix).rstrip("*?"), []).append(callback)

    def unsubscribe(self, prefix: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Forget a callback registered with :meth:`subscribe`."""
        key = str(prefix).rstrip("*?")
        kept = [cb for cb in self._callbacks.get(key, []) if cb is not callback]
        if kept:
            self._callbacks[key] = kept
        else:
            self._callbacks.pop(key, None)

    @property
    def pending(self) -> int:
        """Events received and not yet drained."""
        with self._lock:
            return len(self._queue)

    def drain(self, limit: int | None = None) -> int:
        """Dispatch the queued events, oldest first, on the calling thread.

        Parameters
        ----------
        limit : int, optional
            Dispatch at most this many (the rest stay queued for the next call).

        Returns
        -------
        int
            How many events were dispatched.
        """
        done = 0
        while limit is None or done < limit:
            with self._lock:
                if not self._queue:
                    break
                topic, payload = self._queue.popleft()
            done += 1
            for prefix, callbacks in list(self._callbacks.items()):
                if not topic.startswith(prefix):
                    continue
                for callback in list(callbacks):
                    try:
                        callback(payload)
                    except Exception:  # noqa: BLE001 - one view failing must not starve the others
                        _log.exception("event callback for %r failed", topic)
        return done

    # -- the worker ---------------------------------------------------------- #
    @property
    def running(self) -> bool:
        """Whether the worker is receiving."""
        return self._thread is not None and self._thread.is_alive()

    def start(self, timeout: float = 5.0) -> ServerEventSubscriber:
        """Start the worker and wait until its socket is connected; returns ``self``."""
        if self.running:
            return self
        self._running.set()
        self._connected.clear()
        self._thread = threading.Thread(
            target=self._work, name=f"chisurf-events-{self.pub_port}", daemon=True
        )
        self._thread.start()
        self._connected.wait(timeout)
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the worker and close its socket; queued events stay drainable."""
        self._running.clear()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout)

    def _work(self) -> None:
        import zmq

        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.connect(f"tcp://{self.host}:{self.pub_port}")
            for topic in self.topics:
                socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            poller = zmq.Poller()
            poller.register(socket, zmq.POLLIN)
            self._connected.set()
            while self._running.is_set():
                try:
                    ready = dict(poller.poll(self.poll_ms))
                except zmq.ZMQError:
                    break
                if socket not in ready:
                    continue
                got = 0
                while True:
                    try:
                        frames = socket.recv_multipart(flags=zmq.NOBLOCK)
                    except zmq.Again:
                        break
                    event = self._decode(frames)
                    if event is None:
                        continue
                    with self._lock:
                        self._queue.append(event)
                    got += 1
                if got:
                    self.received += got
                    if self.wake is not None:
                        try:
                            self.wake()
                        except Exception:  # noqa: BLE001 - a wake hook must not kill the receiver
                            _log.exception("event wake callback failed")
        finally:
            self._connected.set()
            socket.close(linger=0)
            context.term()

    @staticmethod
    def _decode(frames: list[bytes]) -> tuple[str, dict[str, Any]] | None:
        """``(topic, payload)`` of one PUB message, ``None`` for a malformed one."""
        if len(frames) != 2:
            return None
        try:
            topic = frames[0].decode("utf-8")
            payload = json.loads(frames[1].decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            _log.warning("dropped a malformed server event")
            return None
        if not isinstance(payload, dict):
            payload = {"value": payload}
        payload.setdefault("topic", topic)
        return topic, payload
