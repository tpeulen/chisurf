"""A debounced action's trailing edge must reach its handler.

Debounced actions defer their trailing edge onto a ``threading.Timer`` thread and call the
scheduler (when one is installed) from there. The deferred action must not be dropped.
"""

import threading
import time
import unittest

from chisurf.core.actions._infra import ActionDispatcher, ActionRegistry, ActionSpec


def _wait(predicate, timeout_s: float = 3.0) -> bool:
    """Poll until *predicate* holds or *timeout_s* elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class TestDebouncedTrailingEdge(unittest.TestCase):
    """The dispatcher's deferred call reaches the handler via the scheduler."""

    def _dispatcher(self, calls, scheduler):
        registry = ActionRegistry()
        registry.register(
            ActionSpec(
                name="test.debounced",
                schema={"target": str, "value": float},
                debounce_ms=50,
                debounce_keys=("target",),
                handler=lambda **kw: calls.append(kw),
            )
        )
        dispatcher = ActionDispatcher(registry=registry, history_provider=lambda: None)
        dispatcher.set_scheduler(scheduler)
        self.addCleanup(self._cancel_pending, dispatcher)
        return dispatcher

    def test_debounced_trailing_edge_reaches_the_handler(self):
        """A repeat inside the debounce window is deferred, not lost."""
        calls = []
        scheduled_from = []

        def scheduler(callback, **kwargs):
            """Record the calling thread, then run the callback."""
            scheduled_from.append(threading.current_thread())
            return callback(**kwargs)

        dispatcher = self._dispatcher(calls, scheduler)
        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 1.0})
        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 2.0})
        self.assertEqual([{"target": "tau1", "value": 1.0}], calls)

        self.assertTrue(
            _wait(lambda: len(calls) == 2),
            "the trailing edge of the debounced action was dropped",
        )
        self.assertEqual({"target": "tau1", "value": 2.0}, calls[1])

    def test_debounced_trailing_edge_reaches_the_handler_without_a_scheduler(self):
        """With no scheduler installed the trailing edge still runs."""
        calls = []
        dispatcher = self._dispatcher(calls, None)
        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 1.0})
        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 2.0})
        self.assertTrue(_wait(lambda: len(calls) == 2), "the trailing edge was dropped")

    @staticmethod
    def _cancel_pending(dispatcher: ActionDispatcher) -> None:
        """Cancel the trailing-edge timers a debounced call leaves behind."""
        for timer in list(dispatcher._pending_timers.values()):
            timer.cancel()


if __name__ == "__main__":
    unittest.main()
