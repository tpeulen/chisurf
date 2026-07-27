"""Running work off the GUI thread against the progress seam.

The contract is small and each clause exists because its absence is a defect
that only shows up under a fast double-click or a slow file.
"""

import concurrent.futures
import threading

import pytest

from chisurf.gui import QtWidgets
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.task import run_in_background


@pytest.fixture
def owner(qtbot) -> QtWidgets.QWidget:
    """A widget to own the tasks (and to key the one-run-at-a-time rule)."""
    w = QtWidgets.QWidget()
    qtbot.addWidget(w)
    return w


def _adder(a, b, task):
    """Trivial worker: the handle is the last positional argument."""
    return a + b


class TestResults:

    def test_the_return_value_reaches_on_result(self, owner):
        got = []
        run_in_background(owner, "Adding", _adder, args=(2, 3),
                          on_result=got.append).wait()
        assert got == [5]

    def test_keyword_arguments_pass_through(self, owner):
        def work(a, task, *, b):
            return a * b

        got = []
        run_in_background(owner, "Multiplying", work, args=(3,), kwargs={"b": 4},
                          on_result=got.append).wait()
        assert got == [12]

    def test_on_done_runs_after_success(self, owner):
        calls = []
        run_in_background(owner, "Adding", _adder, args=(1, 1),
                          on_result=lambda r: calls.append("result"),
                          on_done=lambda: calls.append("done")).wait()
        assert calls == ["result", "done"]

    def test_the_task_records_the_outcome(self, owner):
        task = run_in_background(owner, "Adding", _adder, args=(1, 2)).wait()
        assert task.result == 3
        assert task.exception is None
        assert not task.is_running


class TestFailures:

    def test_an_exception_reaches_on_error_not_on_result(self, owner):
        def boom(task):
            raise ValueError("no good")

        errors, results = [], []
        run_in_background(owner, "Failing", boom,
                          on_result=results.append, on_error=errors.append).wait()
        assert results == []
        assert isinstance(errors[0], ValueError)
        assert str(errors[0]) == "no good"

    def test_on_done_still_runs_after_a_failure(self, owner):
        def boom(task):
            raise ValueError

        calls = []
        run_in_background(owner, "Failing", boom, on_error=lambda e: None,
                          on_done=lambda: calls.append("done")).wait()
        assert calls == ["done"]

    def test_a_failure_without_a_handler_is_logged_not_raised(self, owner, caplog):
        def boom(task):
            raise ValueError("unhandled")

        task = run_in_background(owner, "Failing", boom).wait()
        assert isinstance(task.exception, ValueError)
        assert "background task failed" in caplog.text


class TestPartialResults:

    def test_partials_arrive_in_order_before_the_result(self, owner):
        def streaming(task):
            for i in range(4):
                task.set_partial(i)
            return "done"

        seen = []
        run_in_background(owner, "Streaming", streaming,
                          on_partial=seen.append,
                          on_result=lambda r: seen.append(r)).wait()
        assert seen == [0, 1, 2, 3, "done"]

    def test_a_raising_partial_handler_does_not_kill_the_task(self, owner):
        def streaming(task):
            task.set_partial(1)
            return "finished"

        def bad(_value):
            raise RuntimeError("plotting blew up")

        task = run_in_background(owner, "Streaming", streaming, on_partial=bad).wait()
        assert task.result == "finished"
        assert task.exception is None


class TestProgress:

    def test_progress_drives_the_display(self, owner):
        def counting(task):
            for i in range(1, 4):
                task.set_progress(i, f"step {i}")
            return None

        task = run_in_background(owner, "Counting", counting, maximum=3).wait()
        assert task.progress.value() == 3

    def test_a_repeated_value_is_not_re_emitted(self, owner):
        """A tight loop reporting the same number must not flood the queue."""
        from chisurf.gui.task import TaskHandle, _Bridge

        emitted = []
        bridge = _Bridge()
        bridge.progressed.connect(lambda v, t: emitted.append((v, t)))
        handle = TaskHandle(bridge, threading.Event(), 10)
        for _ in range(5):
            handle.set_progress(3)
        handle.set_progress(4)
        assert emitted == [(3, None), (4, None)]

    def test_set_fraction_scales_to_the_maximum(self, owner):
        def counting(task):
            task.set_fraction(0.5)

        task = run_in_background(owner, "Counting", counting, maximum=200).wait()
        assert task.progress.value() == 100


class TestCancellation:

    def test_cancel_is_visible_to_the_worker(self, owner):
        started, may_finish = threading.Event(), threading.Event()

        def slow(task):
            started.set()
            may_finish.wait(5.0)
            return "cancelled" if task.is_cancelled else "completed"

        task = run_in_background(owner, "Slow", slow, synchronous=False)
        assert started.wait(5.0)
        task.cancel()
        may_finish.set()
        task.wait()
        assert task.result == "cancelled"

    def test_a_cancelled_task_does_not_report_a_result_or_an_error(self, owner):
        def slow(task):
            task.raise_if_cancelled()
            return "value"

        results, errors = [], []
        task = run_in_background(owner, "Slow", slow, synchronous=False)
        task.cancel()
        task.wait()
        assert results == [] and errors == []

    def test_cancelling_before_the_work_starts_still_completes_the_task(self, owner):
        """A future cancelled while queued never runs, so it never emits.

        Without completing it by hand the task stays "running" forever: no
        `on_done`, no bookkeeping, and anything awaiting it blocks. The symptom
        is a hang, not a failure, which is why it is pinned here.
        """
        blocker = threading.Event()
        hog = QtWidgets.QWidget()
        first = run_in_background(hog, "Blocking", lambda task: blocker.wait(5.0),
                                  synchronous=False)
        calls = []
        queued = run_in_background(owner, "Queued", _adder, args=(1, 1),
                                   synchronous=False,
                                   on_done=lambda: calls.append("done"))
        queued.cancel()
        queued.wait(timeout=5.0)
        blocker.set()
        first.wait(timeout=5.0)
        assert not queued.is_running
        assert calls == ["done"]

    def test_raise_if_cancelled_is_not_an_error(self, owner):
        def worker(task):
            raise concurrent.futures.CancelledError()

        errors = []
        run_in_background(owner, "Slow", worker, on_error=errors.append).wait()
        assert errors == []


class TestOneRunPerOwner:

    def test_a_new_run_supersedes_the_previous_one(self, owner):
        """A superseded run's result must not land in the GUI after a newer one."""
        first_started, first_may_finish = threading.Event(), threading.Event()

        def slow(task):
            first_started.set()
            first_may_finish.wait(5.0)
            return "stale"

        results = []
        stale = run_in_background(owner, "First", slow, synchronous=False,
                                  on_result=results.append)
        assert first_started.wait(5.0)
        fresh = run_in_background(owner, "Second", _adder, args=(1, 1),
                                  synchronous=False, on_result=results.append)
        first_may_finish.set()
        fresh.wait()
        stale.wait()
        assert results == [2]
        assert stale.is_cancelled

    def test_a_superseded_task_still_finishes_its_bookkeeping(self, owner):
        """Silencing a superseded run must not also silence its completion.

        Disconnecting the whole bridge stops the stale result reaching the GUI
        — and stops the task ever finishing, so `on_done` never runs and the
        owner's button stays disabled forever.
        """
        started, may_finish = threading.Event(), threading.Event()
        calls = []

        def slow(task):
            started.set()
            may_finish.wait(5.0)
            return "stale"

        stale = run_in_background(owner, "First", slow, synchronous=False,
                                  on_result=lambda r: calls.append(r),
                                  on_done=lambda: calls.append("done"))
        assert started.wait(5.0)
        fresh = run_in_background(owner, "Second", _adder, args=(1, 1),
                                  synchronous=False)
        may_finish.set()
        fresh.wait(timeout=5.0)
        stale.wait(timeout=5.0)
        assert not stale.is_running
        assert calls == ["done"]        # on_done ran; the stale result did not

    def test_distinct_owners_do_not_cancel_each_other(self, qtbot):
        a, b = QtWidgets.QWidget(), QtWidgets.QWidget()
        qtbot.addWidget(a)
        qtbot.addWidget(b)
        results = []
        t1 = run_in_background(a, "A", _adder, args=(1, 1), on_result=results.append)
        t2 = run_in_background(b, "B", _adder, args=(2, 2), on_result=results.append)
        t1.wait()
        t2.wait()
        assert sorted(results) == [2, 4]

    def test_starting_a_task_from_a_callback_is_refused(self, owner):
        """The teardown that is still running would cancel the new task."""
        raised = []

        def restart(_result):
            try:
                run_in_background(owner, "Again", _adder, args=(1, 1))
            except RuntimeError as exc:
                raised.append(exc)

        run_in_background(owner, "First", _adder, args=(1, 1),
                          on_result=restart).wait()
        assert raised and "completion callback" in str(raised[0])


class TestStatusBarDisplay:
    """A standalone tool window shows the run in its own status bar.

    Falling through to a modal dialog would take back everything moving the work
    off the GUI thread just bought.
    """

    def test_a_main_window_gets_a_status_bar_host_not_a_modal(self, qtbot):
        from chisurf.gui.widgets.progress import StatusBarProgressHost

        window = QtWidgets.QMainWindow()
        qtbot.addWidget(window)
        blocker = threading.Event()
        task = run_in_background(window, "Working…", lambda t: blocker.wait(5.0),
                                 synchronous=False)
        host = window._chisurf_status_progress
        assert isinstance(host, StatusBarProgressHost)
        assert task.progress.backend.__class__.__name__ == "_StatusBarTask"
        blocker.set()
        task.wait(timeout=5.0)

    def test_the_bar_appears_while_running_and_goes_away_after(self, qtbot):
        window = QtWidgets.QMainWindow()
        qtbot.addWidget(window)
        window.show()
        blocker = threading.Event()
        task = run_in_background(window, "Working…", lambda t: blocker.wait(5.0),
                                 synchronous=False)
        for _ in range(200):
            QtWidgets.QApplication.instance().processEvents()
            if window._chisurf_status_progress.isVisible():
                break
        assert window._chisurf_status_progress.isVisible()
        blocker.set()
        task.wait(timeout=5.0)
        assert not window._chisurf_status_progress.isVisible()

    def test_the_cancel_button_reaches_the_worker(self, qtbot):
        window = QtWidgets.QMainWindow()
        qtbot.addWidget(window)
        started, may_finish = threading.Event(), threading.Event()

        def slow(task):
            started.set()
            may_finish.wait(5.0)
            return "cancelled" if task.is_cancelled else "completed"

        task = run_in_background(window, "Working…", slow, synchronous=False)
        assert started.wait(5.0)
        window._chisurf_status_progress._on_cancel()
        may_finish.set()
        task.wait(timeout=5.0)
        assert task.result == "cancelled"


class TestExecutionMode:

    def test_synchronous_runs_inline_and_in_order(self, owner):
        order = []

        def work(task):
            order.append("work")
            task.set_partial("partial")
            return "result"

        run_in_background(owner, "Inline", work, synchronous=True,
                          on_partial=lambda v: order.append(v),
                          on_result=lambda v: order.append(v))
        assert order == ["work", "partial", "result"]

    def test_the_alias_on_the_progress_class_is_the_same_function(self, owner):
        got = []
        ChiSurfProgress.run(owner, "Adding", _adder, args=(4, 4),
                            on_result=got.append).wait()
        assert got == [8]
