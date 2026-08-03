"""Guard tests for the re-entrancy flag of the ``@action`` decorator.

The flag exists so that a handler calling its own action again runs the plain
body instead of dispatching a second time.  It must be *thread-local*: when it
lived on the wrapper function it was shared by every thread, so a concurrent
call to the same action from another thread silently took the re-entrant
shortcut and mutated state without payload validation, debouncing or a history
record (finding RF-179).
"""

import pathlib
import threading
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf as cs
from chisurf.core.actions._decorator import action
from chisurf.core.actions._infra import ActionDispatcher, ActionRegistry
from chisurf.history import OperationHistory


class TestActionReentrancyGuard(unittest.TestCase):
    """Re-entrancy shortcut on the same thread, full dispatch on another."""

    def setUp(self):
        # Register the probe actions in a scratch registry so the process-wide
        # action vocabulary (which the dictionary pins) stays untouched.
        self.history = OperationHistory()
        self.dispatcher = ActionDispatcher(
            registry=ActionRegistry(), history_provider=lambda: self.history
        )
        self._saved = (
            getattr(cs, "action_dispatcher", None),
            getattr(cs, "action_registry", None),
        )
        cs.action_dispatcher = self.dispatcher
        cs.action_registry = self.dispatcher.registry

    def tearDown(self):
        cs.action_dispatcher, cs.action_registry = self._saved

    def test_nested_call_on_same_thread_takes_the_shortcut(self):
        depths = []

        @action("test.reentrancy_nested", schema={"depth": int})
        def nested(depth: int):
            depths.append(depth)
            if depth == 0:
                return nested(1)
            return depth

        self.assertEqual(nested(0), 1)
        self.assertEqual(depths, [0, 1])
        # Only the outer call is dispatched; the nested one runs the bare body.
        self.assertEqual(len(self.history.list_events()), 1)

    def test_concurrent_call_on_another_thread_is_still_validated(self):
        entered = threading.Event()
        release = threading.Event()

        @action("test.reentrancy_concurrent", schema={"x": int})
        def slow(x: int):
            entered.set()
            release.wait(10.0)
            return x

        holder = threading.Thread(target=lambda: slow(1), daemon=True)
        holder.start()
        try:
            self.assertTrue(entered.wait(10.0), "handler thread never started")
            # While the other thread is inside the handler this call must still
            # go through dispatch — i.e. be rejected by the schema, not run.
            with self.assertRaises(TypeError):
                slow("not-an-int")
        finally:
            release.set()
            holder.join(10.0)


if __name__ == "__main__":
    unittest.main()
