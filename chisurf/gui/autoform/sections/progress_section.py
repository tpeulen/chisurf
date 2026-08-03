"""General ``progress`` AutoForm section — the inline progress bar.

Every long-running plugin used to hand-roll the same widget: a
``QProgressBar`` next to a run button, a ``setValue`` call in a callback, and a
``processEvents()`` to make it repaint. Four copies of that had four different
behaviours (no label, no cancel, never hidden, never reset).

Declare it once instead::

    {"type": "custom", "key": "progress", "title": "Progress",
     "options": {"cancellable": true}}

and drive it from anywhere with :class:`~chisurf.gui.progress.ChiSurfProgress`::

    with ChiSurfProgress(self, "Splitting…", n_files) as bar:
        ...

The section registers itself as a *progress host* (it implements
``begin_task``), and ``ChiSurfProgress`` resolves the **nearest** host by
walking up from the widget it was given. So a run button inside the same form
lands in this bar automatically — no wiring, no reference passing — while the
identical code in a standalone window opens a modal dialog and headless writes
to the log.

Options
-------
``cancellable`` : bool, default ``True``
    Show a Cancel button while a task runs.
``hide_when_idle`` : bool, default ``True``
    Take the bar out of the layout between tasks instead of leaving an empty
    trough sitting in the panel.
``show_text`` : bool, default ``True``
    Show the task message in a label above the bar.
``target`` : str, optional
    Model attribute holding a completion fraction (0–1) or percent (0–100),
    polled on every AutoForm refresh. Use it for progress a *model* owns (a
    background job) rather than progress a GUI loop drives.
``handle`` : str, optional
    Attribute name under which the widget is published on the model
    (``model.<handle> = widget``), for code that cannot reach a parent widget.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


class _InlineTask:
    """Handle for one task rendered by an :class:`InlineProgressWidget`.

    Duck-types the ``QProgressDialog`` surface (``setValue`` / ``setLabelText``
    / ``setRange`` / ``wasCanceled`` / ``close``) so it is interchangeable with
    the status-bar task and the modal dialog behind
    :class:`~chisurf.gui.progress.ChiSurfProgress`.
    """

    def __init__(self, widget: InlineProgressWidget, message: str, maximum: int, cancel) -> None:
        self._widget = widget
        self._cancel_cb = cancel
        self._canceled = False
        widget._activate(self, message, maximum, cancel is not None)

    def setLabelText(self, text: str) -> None:  # noqa: N802 (Qt-style)
        self._widget._set_message(self, str(text))

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        self._widget._set_range(self, int(minimum), int(maximum))

    def setValue(self, value: int) -> None:  # noqa: N802
        self._widget._set_value(self, int(value))

    def value(self) -> int:
        return int(self._widget.bar.value())

    def maximum(self) -> int:
        return int(self._widget.bar.maximum())

    def update_progress(self, value: int, text: str | None = None) -> None:
        if text is not None:
            self.setLabelText(text)
        self.setValue(value)

    def wasCanceled(self) -> bool:  # noqa: N802
        return self._canceled

    def cancel(self) -> None:
        """Mark canceled and fire the cancel callback (Cancel-button path)."""
        self._canceled = True
        if callable(self._cancel_cb):
            try:
                self._cancel_cb()
            except Exception:
                logger.debug("progress cancel callback failed", exc_info=True)

    def finish(self, *args, **kwargs) -> None:
        self.close()

    def close(self) -> None:
        self._widget._deactivate(self)


class InlineProgressWidget(QtWidgets.QWidget):
    """Progress bar embedded in a form, shared by everything inside it.

    Obtained declaratively from a ``.view.json`` (``{"type": "custom", "key":
    "progress"}``) and driven through :class:`~chisurf.gui.progress.ChiSurfProgress`,
    which finds it by walking up the widget tree. See the module docstring for
    the available options.

    Parameters
    ----------
    model : object
        The view model; only used for ``target`` polling and ``handle``
        publication.
    target : str, optional
        Model attribute holding a completion fraction or percent.
    **options
        See the module docstring.
    """

    #: AutoForm refreshes this widget along with plots/tables (for ``target``).
    AUTOFORM_REFRESH = True

    def __init__(self, model=None, target: str | None = None, **options) -> None:
        super().__init__()
        self._model = model
        self._target = target or None
        self._cancellable = bool(options.get("cancellable", True))
        self._hide_when_idle = bool(options.get("hide_when_idle", True))
        self._show_text = bool(options.get("show_text", True))
        self._task: _InlineTask | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.label = QtWidgets.QLabel("")
        self.label.setWordWrap(True)
        self.label.setTextFormat(QtCore.Qt.PlainText)
        self.label.setVisible(False)
        layout.addWidget(self.label)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        row.addWidget(self.bar, 1)

        self.cancel_button = QtWidgets.QToolButton()
        self.cancel_button.setText("✖")
        self.cancel_button.setToolTip("Cancel the running operation.")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.cancel_button.setVisible(False)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        if self._hide_when_idle and self._target is None:
            self.bar.setVisible(False)

        if self._target is not None:
            self.refresh()
        if options.get("handle"):
            try:
                setattr(model, str(options["handle"]), self)
            except Exception:
                logger.debug("progress: could not publish handle on the model", exc_info=True)

    # ── progress-host contract ──────────────────────────────────────────────
    def begin_task(self, message: str = "", maximum: int = 0, cancel=None) -> _InlineTask:
        """Start a task in this bar and return a dialog-compatible handle.

        This is the method that makes the widget a *progress host*: any
        :class:`~chisurf.gui.progress.ChiSurfProgress` created from a widget
        inside this form renders here.

        Parameters
        ----------
        message : str
            What the operation is doing.
        maximum : int
            Number of steps; ``0`` shows a busy indicator.
        cancel : callable, optional
            Called when the user presses Cancel.

        Returns
        -------
        _InlineTask
            The task handle.
        """
        return _InlineTask(self, message, maximum, cancel if self._cancellable else None)

    # ── task rendering ──────────────────────────────────────────────────────
    def _activate(self, task: _InlineTask, message: str, maximum: int, cancellable: bool) -> None:
        """Take over the bar for *task* (the most recent task owns it)."""
        self._task = task
        self.bar.setRange(0, int(maximum))
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.cancel_button.setVisible(bool(cancellable))
        self._set_message(task, message)
        self._repaint()

    def _is_current(self, task: _InlineTask) -> bool:
        """Whether *task* still owns the bar (a later task may have taken it)."""
        return self._task is task

    def _set_message(self, task: _InlineTask, text: str) -> None:
        if not self._is_current(task):
            return
        self.label.setText(str(text))
        self.label.setVisible(self._show_text and bool(text))

    def _set_range(self, task: _InlineTask, minimum: int, maximum: int) -> None:
        if self._is_current(task):
            self.bar.setRange(int(minimum), int(maximum))

    def _set_value(self, task: _InlineTask, value: int) -> None:
        if self._is_current(task):
            self.bar.setValue(int(value))
            self._repaint()

    def _deactivate(self, task: _InlineTask) -> None:
        """Release the bar when *task* finishes."""
        if not self._is_current(task):
            return
        self._task = None
        self.cancel_button.setVisible(False)
        self.label.setVisible(False)
        self.label.setText("")
        if self._target is not None:
            self.refresh()
        elif self._hide_when_idle:
            self.bar.setVisible(False)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        self._repaint()

    def _on_cancel_clicked(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.cancel_button.setEnabled(False)

    def _repaint(self) -> None:
        """Repaint during a busy loop that never returns to the event loop."""
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents()

    # ── QProgressBar-compatible surface ─────────────────────────────────────
    #
    # A widget declared in a ``.ui`` file is driven with plain ``QProgressBar``
    # calls from code that has no idea a task abstraction exists. Answering
    # those directly is what lets :func:`adopt_progress_bar` swap this widget in
    # underneath such a tool without touching a single call site.

    def setValue(self, value: int) -> None:  # noqa: N802
        """Set the bar's value, revealing it if it was idle-hidden."""
        self.bar.setValue(int(value))
        self.bar.setVisible(True)
        self._repaint()

    def value(self) -> int:
        """Return the bar's current value."""
        return int(self.bar.value())

    def setMinimum(self, minimum: int) -> None:  # noqa: N802
        """Set the low end of the range."""
        self.bar.setMinimum(int(minimum))

    def setMaximum(self, maximum: int) -> None:  # noqa: N802
        """Set the high end of the range (``0`` with minimum ``0`` = busy)."""
        self.bar.setMaximum(int(maximum))

    def minimum(self) -> int:
        """Return the low end of the range."""
        return int(self.bar.minimum())

    def maximum(self) -> int:
        """Return the high end of the range."""
        return int(self.bar.maximum())

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        """Set both ends of the range."""
        self.bar.setRange(int(minimum), int(maximum))

    def reset(self) -> None:
        """Return the bar to its idle state."""
        self.bar.reset()
        if self._hide_when_idle and self._task is None:
            self.bar.setVisible(False)

    def setTextVisible(self, visible: bool) -> None:  # noqa: N802
        """Show or hide the percentage text inside the bar."""
        self.bar.setTextVisible(bool(visible))

    def setFormat(self, text: str) -> None:  # noqa: N802
        """Set the bar's own text format (``%p%`` and friends)."""
        self.bar.setFormat(str(text))

    # ── model-driven mode ───────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-read the ``target`` attribute and show it (AutoForm refresh hook).

        A value in ``0..1`` is read as a fraction, anything larger as a percent,
        and ``None`` hides the bar. Ignored while a :meth:`begin_task` task owns
        the bar, so a live loop is never overwritten by a stale model value.
        """
        if self._target is None or self._task is not None:
            return
        value = getattr(self._model, self._target, None)
        if value is None:
            self.bar.setVisible(not self._hide_when_idle)
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        percent = number * 100.0 if 0.0 <= number <= 1.0 else number
        self.bar.setRange(0, 100)
        self.bar.setValue(max(0, min(100, int(round(percent)))))
        self.bar.setVisible(True)


def adopt_progress_bar(owner, name: str = "progressBar", **options) -> InlineProgressWidget | None:
    """Replace a ``.ui``-declared ``QProgressBar`` with the shared inline bar.

    Tools whose layout comes from Qt Designer cannot declare a
    :class:`InlineProgressWidget` in their ``.ui`` file without a promotion, so
    they get the shared bar here instead: the named child is swapped in place,
    keeping its position in the layout and its attribute name. Because the
    replacement answers the ``QProgressBar`` calls (``setValue``, ``setRange``,
    …), the tool's existing code keeps working untouched — and it also becomes a
    *progress host*, so :class:`~chisurf.gui.progress.ChiSurfProgress` started
    from anywhere in that window renders here.

    Parameters
    ----------
    owner : QWidget
        The widget that loaded the ``.ui`` file.
    name : str
        Object name of the ``QProgressBar`` to replace.
    **options
        Forwarded to :class:`InlineProgressWidget` (e.g. ``cancellable``).

    Returns
    -------
    InlineProgressWidget or None
        The replacement, or ``None`` when no such bar was found (a ``.ui`` file
        may legitimately have none).

    Examples
    --------
    >>> uic.loadUi(ui_file, self)                      # doctest: +SKIP
    >>> adopt_progress_bar(self)                       # doctest: +SKIP
    >>> self.progressBar.setValue(40)   # unchanged    # doctest: +SKIP
    """
    old = owner.findChild(QtWidgets.QProgressBar, name)
    if old is None:
        return None
    options.setdefault("hide_when_idle", False)
    options.setdefault("show_text", False)
    replacement = InlineProgressWidget(**options)
    replacement.setObjectName(name)
    replacement.bar.setRange(old.minimum(), old.maximum())
    replacement.bar.setValue(old.value())

    _put_where(old, replacement)
    old.setParent(None)
    old.deleteLater()
    setattr(owner, name, replacement)
    return replacement


def _put_where(old: QtWidgets.QWidget, new: QtWidgets.QWidget) -> None:
    """Place *new* exactly where *old* sits in its parent's layout.

    Designer files use box, grid and form layouts interchangeably, and only the
    box layouts have ``insertWidget`` — a grid needs the cell it occupied and a
    form needs its row and role, or the replacement lands in the wrong place (or
    silently at the end).

    Parameters
    ----------
    old : QWidget
        The widget being replaced; still in its layout when called.
    new : QWidget
        The replacement.
    """
    parent = old.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is None:  # no layout: keep the geometry the designer gave it
        new.setParent(parent)
        new.setGeometry(old.geometry())
        new.show()
        return
    index = layout.indexOf(old)
    if isinstance(layout, QtWidgets.QGridLayout) and index >= 0:
        row, column, row_span, column_span = layout.getItemPosition(index)
        layout.removeWidget(old)
        layout.addWidget(new, row, column, row_span, column_span)
    elif isinstance(layout, QtWidgets.QFormLayout) and index >= 0:
        row, role = layout.getWidgetPosition(old)
        layout.removeWidget(old)
        layout.setWidget(row, role, new)
    elif isinstance(layout, QtWidgets.QBoxLayout) and index >= 0:
        layout.insertWidget(index, new)
    else:
        layout.addWidget(new)


@register_section("progress")
def _progress_section_factory(model=None, target: str | None = None, **options):
    """Custom-section factory for the general inline progress bar."""
    return InlineProgressWidget(model, target, **options)


__all__ = ["InlineProgressWidget", "adopt_progress_bar"]
