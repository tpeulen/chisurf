"""The agent panel: a prompt, a transcript, and the live session behind it.

The ask runs on a worker thread and marshals its outcome back through a
queue the render loop drains — the same discipline the Ask-Docs dock uses —
because a model turn takes seconds and the GUI must not freeze under it.
Everything the thread produces lands in plain state (``transcript``,
``busy``, ``error``) that the render draws and the tests can read without a
running application.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

ROLE_USER = "user"
ROLE_AGENT = "agent"
ROLE_ERROR = "error"


class AgentApp:
    """The panel's state machine, independent of the drawing layer.

    Parameters
    ----------
    session_factory : callable
        Builds the :class:`AgentSession` on first use; injectable so tests
        drive the flow with a scripted session.
    """

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        from chisurf.plugins.core.agent.api.session import build_session

        self._session_factory = session_factory or build_session
        self._session: Any = None
        self._thread: threading.Thread | None = None
        self._events: queue.Queue = queue.Queue()
        self.transcript: list[dict[str, str]] = []
        self.input = ""
        self.busy = False
        self.error = ""
        self._generation = 0

    # ── the flow ──────────────────────────────────────────────────────────

    def submit(self, text: str) -> bool:
        """Send one user message to the session; the answer arrives via ``poll``.

        A clarification round is just another message: the questions come back
        as the agent's turn, and the user's next submit answers them in the
        same conversation.
        """
        text = str(text).strip()
        if not text or self.busy:
            return False
        self.transcript.append({"role": ROLE_USER, "text": text})
        self.error = ""
        self.busy = True
        self._generation += 1
        generation = self._generation
        self._thread = threading.Thread(
            target=self._run, args=(text, generation), daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Cancel the running turn; the session stops at the next tool call."""
        if self._session is not None:
            self._session.cancel()
        self._generation += 1
        self.busy = False
        self.transcript.append({"role": ROLE_AGENT, "text": "Cancelled."})

    def poll(self) -> None:
        """Drain the worker's events; the render loop calls this every frame."""
        while True:
            try:
                kind, payload, generation = self._events.get_nowait()
            except queue.Empty:
                return
            if generation != self._generation:
                continue
            if kind == "answer":
                self.transcript.append({"role": ROLE_AGENT, "text": payload})
                self.busy = False
            elif kind == "error":
                self.error = payload
                self.transcript.append({"role": ROLE_ERROR, "text": payload})
                self.busy = False

    # ── internals ─────────────────────────────────────────────────────────

    def _run(self, text: str, generation: int) -> None:
        try:
            if self._session is None:
                self._session = self._session_factory()
            result = self._session.ask(text)
            # A clarification round is the agent's turn: the questions are the
            # text, and the user's next submit answers them in the thread.
            self._events.put(("answer", result.text, generation))
        except Exception as err:  # noqa: BLE001 - the panel shows the reason
            self._events.put(("error", f"The agent failed: {err}", generation))


def make_app(*, session_factory: Callable[[], Any] | None = None) -> AgentApp:
    """The plugin's entrypoint: the panel state with the live session.

    The returned object is both the emtk-drawn panel's state and the
    testable flow; wiring it to ``ImApp`` stays here so the flow is
    exercisable headless.
    """
    app = AgentApp(session_factory=session_factory)
    try:
        from emtk.i18n import install

        install()
    except Exception:  # noqa: BLE001 - headless/test environments
        pass
    return app
