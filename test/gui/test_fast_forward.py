"""Fast-forward walks the pipeline one step at a time, never two at once.

Each step's run is asynchronous, and starting the next before the previous has
finished is the crash the armed-advance design exists to avoid. Fast-forward is
that same armed advance, kept armed — so what these pin is the *chaining*, not
the computing.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")


@pytest.fixture
def shell(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.widgets.navigation import NavigationPanelTool

    panels = [
        {"name": f"{i}. Step", "factory": (lambda p, i=i: QtWidgets.QLabel(f"p{i}", p)),
         "role": f"s{i}"}
        for i in range(1, 4)
    ]
    panels.append({"name": "────", "separator": True, "role": "sep"})
    panels.append({"name": "Extra", "factory": (lambda p: QtWidgets.QLabel("x", p)),
                   "role": "extra"})
    tool = NavigationPanelTool(panels=panels, title="FF test")
    yield tool
    tool.close()


def test_fast_forward_runs_the_numbered_steps_and_stops_at_the_separator(
    shell, monkeypatch
):
    """One click walks the pipeline — and only the pipeline.

    What follows the separator are tools you reach *with* the result, or that
    feed the pipeline from the raw files. They are not steps of the walk, and
    running them unasked is not what "fast-forward" means.
    """
    processed: list = []
    monkeypatch.setattr(type(shell), "process_current_step",
                        lambda self: processed.append(self.nav_list.currentRow()) or True)

    shell.nav_list.setCurrentRow(0)
    shell._on_fast_forward_clicked()

    assert processed == [0, 1, 2], processed
    assert shell.nav_list.currentRow() == 2, "it ends on the last numbered step"
    assert not shell._fast_forward, "it stops itself at the end"
    assert shell._btn_ff.text() == "⏩"


def test_the_queue_is_decided_at_the_click(shell, monkeypatch):
    """The walk is a stack of steps taken one at a time, fixed when it starts."""
    monkeypatch.setattr(type(shell), "process_current_step", lambda self: True)
    monkeypatch.setattr(type(shell), "_step_is_busy", lambda self: True)

    shell.nav_list.setCurrentRow(1)
    shell._on_fast_forward_clicked()

    # Row 1 was taken off the queue and is running; rows 2 and onwards wait.
    # Nothing after the separator is in it.
    assert shell._ff_queue == [2], shell._ff_queue
    assert shell._ff_total == 2


def test_the_last_step_runs_once_when_it_works_asynchronously(shell, monkeypatch):
    """The last queued step is processed exactly once, and its end ends the walk.

    Its "done" signal comes back to the same place that starts a step, so an
    empty queue has to mean *stop* rather than "run this one again".

    Started below the separator, the walk also covers only that group — row 4 is
    a tool, not part of the numbered pipeline, so it is a queue of one.
    """
    processed: list = []
    busy = {"value": False}

    def _process(self):
        processed.append(self.nav_list.currentRow())
        busy["value"] = True  # the run goes to a worker, as a real step's does
        return True

    monkeypatch.setattr(type(shell), "process_current_step", _process)
    monkeypatch.setattr(type(shell), "_step_is_busy", lambda self: busy["value"])

    shell.nav_list.setCurrentRow(4)  # the last panel
    shell._on_fast_forward_clicked()
    # It starts the step, then waits for it rather than finishing on the spot.
    assert processed == [4]
    assert shell._fast_forward and shell._pending_advance

    shell._on_task_finished(object())  # still busy: nothing happens
    assert processed == [4]
    assert shell._fast_forward

    busy["value"] = False
    shell._on_task_finished(object())
    assert processed == [4], "the last step must not be run a second time"
    assert not shell._fast_forward
    assert shell._btn_ff.text() == "⏩"


def test_a_second_click_stops_it(shell, monkeypatch):
    """The button is its own cancel — a long pipeline must be interruptible."""
    monkeypatch.setattr(type(shell), "process_current_step", lambda self: True)
    # Pretend the step is working, so the advance stays armed rather than
    # completing synchronously.
    monkeypatch.setattr(type(shell), "_step_is_busy", lambda self: True)

    shell.nav_list.setCurrentRow(0)
    shell._on_fast_forward_clicked()
    assert shell._fast_forward and shell._pending_advance
    assert shell._btn_ff.text() == "⏸", "it shows that it can be stopped"

    shell._on_fast_forward_clicked()
    assert not shell._fast_forward
    assert not shell._pending_advance, "the armed advance is disarmed too"
    assert shell._btn_ff.text() == "⏩"


def test_going_back_ends_it(shell, monkeypatch):
    """Back is a change of mind, so it must not be undone by the next step."""
    monkeypatch.setattr(type(shell), "process_current_step", lambda self: True)
    monkeypatch.setattr(type(shell), "_step_is_busy", lambda self: True)

    shell.nav_list.setCurrentRow(1)
    shell._on_fast_forward_clicked()
    assert shell._fast_forward

    shell.goto_prev_step()
    assert not shell._fast_forward


def test_it_never_starts_a_step_while_one_is_running(shell, monkeypatch):
    """The whole point: one step in flight at a time."""
    starts: list = []
    busy = {"value": True}
    monkeypatch.setattr(type(shell), "process_current_step",
                        lambda self: starts.append(1) or True)
    monkeypatch.setattr(type(shell), "_step_is_busy", lambda self: busy["value"])

    shell.nav_list.setCurrentRow(0)
    shell._on_fast_forward_clicked()
    # Busy on entry: the click arms the advance and starts nothing.
    assert starts == []
    assert shell._pending_advance

    busy["value"] = False
    shell._on_task_finished(object())
    assert shell.nav_list.currentRow() > 0, "it advanced when the work finished"
