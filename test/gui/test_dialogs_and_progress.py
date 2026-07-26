"""The one message box and the one progress reporter, exercised head-lessly.

Both classes exist because the Qt originals block a run with nobody at the
keyboard, so the properties worth pinning down are the head-less ones: a box
that logs and returns a declared safe answer instead of waiting for a click, and
a progress handle that picks a display from where the work was started.
"""

from __future__ import annotations

import logging

import pytest
from qtpy import QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform.sections.progress_section import InlineProgressWidget
from chisurf.gui.progress import ChiSurfProgress, find_progress_host

# ── message boxes ───────────────────────────────────────────────────────────


def test_headless_report_logs_and_does_not_block(qapp, caplog):
    """An error on a failure path is reported to the log, not to a modal box."""
    with caplog.at_level(logging.ERROR, logger="chisurf.gui.dialogs"):
        shown = dialogs.error(None, "Read failed", "Could not read the file.")
    assert shown is False, "a modal box was raised where nobody could dismiss it"
    assert "Could not read the file." in caplog.text


def test_headless_question_answers_with_the_declared_default(qapp):
    """Head-less, a question returns *default* — never a click that never comes."""
    assert dialogs.question(None, "Delete", "Delete it?") == dialogs.ChiSurfMessageBox.No
    answer = dialogs.question(
        None, "Overwrite", "Overwrite it?",
        buttons=dialogs.ChiSurfMessageBox.Yes | dialogs.ChiSurfMessageBox.Cancel,
        default=dialogs.ChiSurfMessageBox.Cancel,
    )
    assert answer == dialogs.ChiSurfMessageBox.Cancel


def test_confirm_declines_by_default(qapp):
    """An unattended run must never confirm a destructive action by accident."""
    assert dialogs.confirm(None, "Delete", "Delete the dataset?") is False
    assert dialogs.confirm(None, "Keep", "Keep going?", default=True) is True


def test_choice_returns_no_key_when_nobody_can_choose(qapp):
    """A custom-button box yields ``None`` head-lessly unless a default is named."""
    answer = dialogs.choice(
        None, "Folder exists", "'out/' already exists.",
        {"overwrite": "Overwrite", "skip": "Skip", "cancel": "Cancel"},
    )
    assert answer.key is None
    assert not answer
    assert answer.checked is False

    answer = dialogs.choice(
        None, "Folder exists", "'out/' already exists.",
        {"overwrite": "Overwrite", "skip": "Skip"}, default="skip",
    )
    assert answer.key == "skip"
    assert answer


def test_auto_answer_scripts_a_confirmation(qapp):
    """A confirmation-guarded path is testable without a human or a fake loop."""
    with dialogs.auto_answer(question=dialogs.ChiSurfMessageBox.Yes):
        assert dialogs.confirm(None, "Delete", "Delete it?") is True
    # …and the scripted answer does not leak out of the block.
    assert dialogs.confirm(None, "Delete", "Delete it?") is False


def test_module_functions_dispatch_through_the_class(qapp, monkeypatch):
    """Patching the class must intercept the ``dialogs.warning(...)`` spelling.

    Call sites use the module function; tests patch the class. Aliasing the two
    would silently break every such test, so the module functions delegate at
    call time.
    """
    seen = []
    monkeypatch.setattr(
        dialogs.ChiSurfMessageBox, "warning", lambda *a, **k: seen.append(a) or True
    )
    dialogs.warning(None, "Title", "Body")
    assert seen == [(None, "Title", "Body")]


def test_exception_report_carries_the_traceback(qapp, caplog):
    """A caught exception is reported with its traceback, not just its message."""
    try:
        raise ValueError("bad channel number")
    except ValueError as exc:
        with caplog.at_level(logging.ERROR, logger="chisurf.gui.dialogs"):
            dialogs.report_exception(None, "Read failed", exc)
    assert "bad channel number" in caplog.text
    assert "ValueError" in caplog.text


# ── progress ────────────────────────────────────────────────────────────────


def test_progress_without_a_gui_reports_to_the_log(caplog):
    """With no display at all the work still leaves a trace of how far it got."""
    with caplog.at_level(logging.INFO, logger="chisurf.gui.progress"):
        with ChiSurfProgress(None, "Correlating", 10) as bar:
            for _ in bar.iterate(range(10)):
                pass
    assert "Correlating" in caplog.text
    assert bar.value() == 10


def test_progress_renders_in_a_sibling_bar(qapp):
    """A run button finds the bar beside it — the layout every plugin uses.

    The bar is a *sibling* of the button, never an ancestor, so resolution has to
    look inside each ancestor as it climbs. Without that the work would silently
    open a modal dialog (or go to the log) while an empty bar sat in the panel.
    """
    section = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(section)
    button = QtWidgets.QToolButton(section)
    row.addWidget(button)
    bar = InlineProgressWidget(hide_when_idle=False)
    row.addWidget(bar)

    assert find_progress_host(button) is bar

    progress = ChiSurfProgress(button, "Splitting…", 4)
    progress.update_progress(3, "Splitting file 3 of 4")
    assert bar.bar.value() == 3
    assert bar.bar.maximum() == 4
    assert bar.label.text() == "Splitting file 3 of 4"
    progress.close()
    # The bar releases itself when the task ends.
    assert bar.label.text() == ""


def test_progress_prefers_the_nearest_bar(qapp):
    """An inline bar in the panel that started the work beats an outer one."""
    outer = QtWidgets.QWidget()
    outer_layout = QtWidgets.QVBoxLayout(outer)
    outer_bar = InlineProgressWidget(hide_when_idle=False)
    outer_layout.addWidget(outer_bar)

    inner = QtWidgets.QWidget(outer)
    inner_layout = QtWidgets.QVBoxLayout(inner)
    inner_bar = InlineProgressWidget(hide_when_idle=False)
    inner_layout.addWidget(inner_bar)
    button = QtWidgets.QToolButton(inner)
    inner_layout.addWidget(button)
    outer_layout.addWidget(inner)

    assert find_progress_host(button) is inner_bar


def test_progress_cancel_stops_the_loop(qapp):
    """Pressing Cancel makes the loop stop; nothing is interrupted behind it."""
    bar = InlineProgressWidget(hide_when_idle=False)
    processed = []
    progress = ChiSurfProgress(bar, "Working", 100)
    for index in progress.iterate(range(100)):
        processed.append(index)
        if index == 4:
            bar.cancel_button.click()
    assert processed == [0, 1, 2, 3, 4], "the loop kept running after Cancel"
    assert progress.was_canceled() is True


def test_progress_cancel_callback_reaches_threaded_work(qapp):
    """Work in a thread cannot poll, so Cancel has to be pushed to it.

    Every threaded run (fitting, docking, H2MM, staged loading) hands
    ``ChiSurfProgress`` a stop callback; without it the Cancel button would set
    a flag nobody reads and the run would carry on to the end.
    """
    import threading

    stop = threading.Event()
    bar = InlineProgressWidget(hide_when_idle=False)
    progress = ChiSurfProgress(bar, "Fitting", 100, cancel=stop.set)

    assert not stop.is_set()
    bar.cancel_button.click()
    assert stop.is_set(), "Cancel never reached the running thread"
    assert progress.was_canceled() is True


def test_progress_finish_and_finalize_accept_the_dialog_contract(qapp):
    """The call sites migrated off the modal dialog keep their own spelling.

    ``finish(final_text=…, auto_close=…, close_delay_ms=…)`` and
    ``finalize(force_auto_close=…)`` come from the popup this class replaced;
    accepting them is what made those migrations one-line changes.
    """
    bar = InlineProgressWidget(hide_when_idle=False)
    progress = ChiSurfProgress(bar, "Fitting", 100)
    progress.update_progress(40)
    progress.finish(final_text="Fitting finished!", auto_close=True, close_delay_ms=0)
    # Both spellings release the bar rather than leaving a task owning it, and
    # an inline bar goes back to idle instead of lingering on the last message.
    assert bar._task is None
    assert bar.label.text() == ""

    progress = ChiSurfProgress(bar, "Fitting", 100)
    progress.finalize(force_auto_close=True)
    assert bar._task is None


def test_progress_survives_a_raising_body(qapp):
    """The display comes down even when the work blows up mid-loop."""
    bar = InlineProgressWidget(hide_when_idle=True)
    with pytest.raises(RuntimeError):
        with ChiSurfProgress(bar, "Working", 3):
            raise RuntimeError("kaboom")
    assert bar.bar.isVisibleTo(bar) is False


def test_progress_section_reads_a_model_attribute(qapp):
    """``target`` binds the bar to progress a model owns (0–1 or 0–100)."""

    class _Model:
        completion = 0.25

    model = _Model()
    bar = InlineProgressWidget(model, "completion", hide_when_idle=False)
    assert bar.bar.value() == 25

    model.completion = 80.0  # percent, not a fraction
    bar.refresh()
    assert bar.bar.value() == 80

    # A live task owns the bar; a stale model value must not overwrite it.
    task = bar.begin_task("Running", 10)
    task.setValue(3)
    model.completion = 0.99
    bar.refresh()
    assert bar.bar.value() == 3


def test_progress_section_is_registered_for_view_json(qapp):
    """``{"type": "custom", "key": "progress"}`` resolves to the shared bar."""
    from chisurf.gui.autoform.sections import get_section_factory

    factory = get_section_factory("progress")
    assert factory is not None
    assert isinstance(factory(model=None, target=None), InlineProgressWidget)
