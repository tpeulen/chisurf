import os
import pathlib
import threading
import time
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtWidgets  # noqa: E402

import chisurf as cs  # noqa: E402
import chisurf.gui  # noqa: E402
from chisurf.core.actions._infra import ActionDispatcher, ActionRegistry, ActionSpec  # noqa: E402


def _pump(app, predicate, timeout_s: float = 3.0) -> bool:
    """Spin the Qt event loop until *predicate* holds or *timeout_s* elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    app.processEvents()
    return predicate()


class TestGuiSchedulerRunsOffThreadCalls(unittest.TestCase):
    """The GUI scheduler has to work from the thread the dispatcher uses.

    Debounced actions defer their trailing edge onto a ``threading.Timer``
    thread and call the scheduler from there.  That thread runs no Qt event
    loop, so a ``QTimer`` started on it never fires — and because nothing
    raises, the scheduler's own ``except`` fallback never triggers either and
    the deferred action is dropped without a trace.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        chisurf.gui.initialize_gui_executors()

    def _scheduler(self):
        scheduler = cs.action_dispatcher._scheduler
        self.assertIsNotNone(scheduler, "the GUI scheduler was not installed")
        return scheduler

    def test_scheduler_called_off_the_gui_thread_runs_on_the_gui_thread(self):
        scheduler = self._scheduler()
        ran = []

        def callback(**kwargs):
            ran.append((QtCore.QThread.currentThread(), kwargs))

        worker = threading.Thread(target=lambda: scheduler(callback, value=1.0))
        worker.start()
        worker.join()

        self.assertTrue(_pump(self.app, lambda: bool(ran)), "the scheduled call never ran")
        thread, kwargs = ran[0]
        self.assertIs(thread, self.app.thread())
        self.assertEqual({"value": 1.0}, kwargs)

    def test_scheduler_called_on_the_gui_thread_still_defers(self):
        scheduler = self._scheduler()
        ran = []
        scheduler(lambda **kw: ran.append(kw), value=2.0)
        self.assertEqual([], ran, "a scheduled call must not run synchronously")
        self.assertTrue(_pump(self.app, lambda: bool(ran)), "the scheduled call never ran")
        self.assertEqual([{"value": 2.0}], ran)

    def test_debounced_trailing_edge_reaches_the_handler(self):
        """A repeat inside the debounce window is deferred, not lost."""
        calls = []
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
        dispatcher.set_scheduler(self._scheduler())
        self.addCleanup(self._cancel_pending, dispatcher)

        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 1.0})
        dispatcher.execute(name="test.debounced", payload={"target": "tau1", "value": 2.0})
        self.assertEqual([{"target": "tau1", "value": 1.0}], calls)

        self.assertTrue(
            _pump(self.app, lambda: len(calls) == 2),
            "the trailing edge of the debounced action was dropped",
        )
        self.assertEqual({"target": "tau1", "value": 2.0}, calls[1])

    @staticmethod
    def _cancel_pending(dispatcher: ActionDispatcher) -> None:
        """Cancel the trailing-edge timers a debounced call leaves behind."""
        for timer in list(dispatcher._pending_timers.values()):
            timer.cancel()


if __name__ == "__main__":
    unittest.main()
