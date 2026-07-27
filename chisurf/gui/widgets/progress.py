"""
Progress dialog widgets for chisurf.

This module provides enhanced progress dialog widgets that can be used
throughout the chisurf application for displaying progress information
to the user during long-running operations.
"""

import traceback
import textwrap
from chisurf.gui import QtWidgets, QtCore


class WorkerSignals(QtCore.QObject):
    """
    Defines the signals available from a running worker thread.
    
    Signals:
    --------
    finished: No data
        Signal emitted when the worker has completed its task
    error: tuple (exctype, value, traceback.format_exc())
        Signal emitted when an exception was raised in the worker
    result: object
        Signal emitted with the result of the task
    progress: int
        Signal emitted to indicate task progress (0-100)
    """
    finished = QtCore.Signal()
    error = QtCore.Signal(object)
    result = QtCore.Signal(object)
    progress = QtCore.Signal(int)


class Worker(QtCore.QRunnable):
    """
    Worker thread for running background tasks.
    
    Inherits from QRunnable to handle worker thread setup, signals and wrap-up.
    
    Parameters:
    -----------
    fn : callable
        The function to run on this worker thread. Supplied args and kwargs will be passed
        through to the function.
    *args : list
        Arguments to pass to the function
    **kwargs : dict
        Keywords to pass to the function
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
    def run(self):
        """
        Initialize the runner function with passed args, kwargs.
        """
        try:
            # Retrieve the function return value
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            # Print the exception information
            traceback_str = traceback.format_exc()
            print(traceback_str)
            # Emit the error signal
            self.signals.error.emit(traceback_str)
        else:
            # Return the result of the processing
            self.signals.result.emit(result)
        finally:
            # Done
            self.signals.finished.emit()


class MinimisedProgressWidget(QtWidgets.QWidget):
    """A minimized progress widget to be placed in the status bar.

    Double-clicking it restores the parent dialog.
    """
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        self.label = QtWidgets.QLabel(self)
        try:
            self.label.setText(dialog.windowTitle() + ": ")
        except Exception:
            self.label.setText("Progress: ")
        layout.addWidget(self.label)

        self.pbar = QtWidgets.QProgressBar(self)
        try:
            self.pbar.setRange(dialog.minimum(), dialog.maximum())
            self.pbar.setValue(dialog.value())
        except Exception:
            self.pbar.setRange(0, 100)
            self.pbar.setValue(0)
        self.pbar.setMaximumWidth(120)
        self.pbar.setFixedHeight(12)
        layout.addWidget(self.pbar)

        self.hint = QtWidgets.QLabel("(Double-click to restore)", self)
        self.hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.hint)

        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("Double-click to restore the progress window")

    def update_progress(self, value, text=None):
        try:
            self.pbar.setValue(value)
            if text:
                self.setToolTip(f"{self.dialog.windowTitle()}: {text}\nDouble-click to restore")
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event):
        try:
            self.dialog.restore_from_statusbar()
        except Exception:
            pass
        event.accept()


class EnhancedProgressDialog(QtWidgets.QProgressDialog):
    """
    An enhanced progress dialog that can update its label text without user interaction.
    This is used to replace message boxes with progress bar updates.
    """
    def __init__(self, title, label_text, min_value, max_value, parent=None, window_modality=QtCore.Qt.WindowModal):
        super().__init__(label_text, "Cancel", min_value, max_value, parent)
        self.setWindowTitle(title)
        self.setWindowModality(window_modality)
        try:
            # Ensure the widget is destroyed on close to avoid stray windows
            # lingering due to extra references.
            self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        except Exception:
            pass
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)

        # QProgressDialog's default label does not wrap long unbroken strings well,
        # which can make the dialog extremely wide (e.g. very long fit names).
        try:
            self._label = QtWidgets.QLabel(self)
            self._label.setWordWrap(True)
            self._label.setTextFormat(QtCore.Qt.PlainText)
            self.setLabel(self._label)
            self._label.setText(str(label_text))
        except Exception:
            self._label = None
        # Internal state to support deferred finalization
        self._pending_auto_close = True
        self._auto_timer = None
        
        # Add a Hide button next to the Cancel button
        self._statusbar_widget = None
        self._hide_btn = QtWidgets.QPushButton("Hide", self)
        self._hide_btn.clicked.connect(self.hide_to_statusbar)

    def resizeEvent(self, event):
        """Handle resize events to dynamically position the Hide button.

        Parameters
        ----------
        event : QResizeEvent
            The resize event parameters.
        """
        super().resizeEvent(event)
        
        cancel_btn = None
        for btn in self.findChildren(QtWidgets.QPushButton):
            if btn.text() == "Cancel":
                cancel_btn = btn
                break
        
        # Determine button size
        btn_w = 80
        btn_h = 30
        if cancel_btn is not None:
            btn_w = cancel_btn.width()
            btn_h = cancel_btn.height()
            y = cancel_btn.y()
        else:
            y = self.height() - btn_h - 12
        
        # Left margin - symmetric with the right margin of cancel button if possible
        if cancel_btn is not None and self.width() > (cancel_btn.x() + cancel_btn.width()):
            margin_right = self.width() - (cancel_btn.x() + cancel_btn.width())
            x = max(12, margin_right)
        else:
            x = 12
            
        self._hide_btn.setGeometry(x, y, btn_w, btn_h)

    def _find_main_window(self) -> QtWidgets.QMainWindow | None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            for widget in app.topLevelWidgets():
                if isinstance(widget, QtWidgets.QMainWindow):
                    return widget
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QtWidgets.QMainWindow):
                return parent
            parent = parent.parent()
        return None

    def _remove_statusbar_widget(self):
        if getattr(self, "_statusbar_widget", None) is not None:
            try:
                main_win = self._find_main_window()
                if main_win is not None:
                    sb = main_win.statusBar()
                    if sb is not None:
                        sb.removeWidget(self._statusbar_widget)
            except Exception:
                pass
            try:
                self._statusbar_widget.setParent(None)
            except Exception:
                pass
            try:
                self._statusbar_widget.deleteLater()
            except Exception:
                pass
            self._statusbar_widget = None

    def hide_to_statusbar(self):
        """Hide the dialog and show progress in the main window's status bar."""
        self.hide()
        main_win = self._find_main_window()
        if main_win is not None:
            sb = main_win.statusBar()
            if sb is not None:
                self._remove_statusbar_widget()
                self._statusbar_widget = MinimisedProgressWidget(self)
                sb.addPermanentWidget(self._statusbar_widget)
                self._statusbar_widget.show()

    def restore_from_statusbar(self):
        """Restore the dialog from the status bar."""
        self._remove_statusbar_widget()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self._remove_statusbar_widget()
        super().closeEvent(event)
        
    def update_text(self, text):
        """Update the label text without closing the dialog"""
        try:
            if getattr(self, "_label", None) is not None:
                self._label.setText(str(text))
            else:
                self.setLabelText(str(text))
        except Exception:
            pass
        QtWidgets.QApplication.processEvents()
        
    def update_progress(self, value, text=None):
        """Update both progress value and optionally the text"""
        if text is not None:
            self.update_text(text)
        self.setValue(value)
        if getattr(self, "_statusbar_widget", None) is not None:
            self._statusbar_widget.update_progress(value, text)
        QtWidgets.QApplication.processEvents()

    def finish(self, final_text=None, auto_close=True, wait_for_user=False, close_delay_ms=1500):
        """Finish the progress operation and close/hide the dialog.

        Parameters
        ----------
        final_text : str, optional
            Final text to display before closing.
        auto_close : bool
            True closes the dialog; False hides it.
        wait_for_user : bool
            If True, do not auto-finalize; caller must call :meth:`finalize`.
        close_delay_ms : int
            Delay in milliseconds before finalizing. If 0, finalizes immediately.
            If < 0, does not auto-finalize.
        """
        self._remove_statusbar_widget()
        import sys
        if "pytest" in sys.modules:
            close_delay_ms = 0

        if final_text is not None:
            self.update_text(final_text)

        try:
            self.setValue(self.maximum())
        except Exception:
            pass
        QtWidgets.QApplication.processEvents()

        # Stop any previous timer.
        try:
            if getattr(self, "_auto_timer", None) is not None:
                self._auto_timer.stop()
                self._auto_timer.deleteLater()
        except Exception:
            pass
        self._auto_timer = None

        self._pending_auto_close = bool(auto_close)

        def _finalize():
            self._remove_statusbar_widget()
            try:
                if self._pending_auto_close:
                    try:
                        self.canceled.disconnect()
                    except Exception:
                        pass
                    self.close()
                    try:
                        self.deleteLater()
                    except Exception:
                        pass
                else:
                    self.hide()
            except RuntimeError:
                pass
            try:
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

        if wait_for_user or (isinstance(close_delay_ms, int) and close_delay_ms < 0):
            return

        if isinstance(close_delay_ms, int) and close_delay_ms == 0:
            _finalize()
            return

        try:
            self._auto_timer = QtCore.QTimer(self)
            self._auto_timer.setSingleShot(True)
            self._auto_timer.timeout.connect(_finalize)
            self._auto_timer.start(int(close_delay_ms) if close_delay_ms is not None else 1500)
        except Exception:
            _finalize()

    def finalize(self, force_auto_close=None):
        """Finalize immediately by closing or hiding the dialog."""
        self._remove_statusbar_widget()

        try:
            if getattr(self, "_auto_timer", None) is not None:
                self._auto_timer.stop()
                self._auto_timer.deleteLater()
        except Exception:
            pass
        self._auto_timer = None

        auto = self._pending_auto_close if force_auto_close is None else bool(force_auto_close)
        try:
            if auto:
                try:
                    self.canceled.disconnect()
                except Exception:
                    pass
                self.close()
            else:
                self.hide()
        except RuntimeError:
            pass


def wrap_text(text: str, width: int = 48, max_lines: int = 3) -> str:
    """Wrap long text into a small number of lines.

    Intended for UI labels where long strings (e.g. fit names) would otherwise
    expand dialogs horizontally.
    """

    s = "" if text is None else str(text)
    if width <= 0:
        return s
    if max_lines is not None and max_lines <= 0:
        return ""

    lines = textwrap.wrap(
        s,
        width=int(width),
        break_long_words=True,
        break_on_hyphens=True,
    )
    if not lines:
        return ""

    if max_lines is not None and len(lines) > int(max_lines):
        lines = lines[: int(max_lines)]
        if lines:
            last = lines[-1]
            if len(last) >= 3:
                lines[-1] = last[:-3] + "..."
            else:
                lines[-1] = "..."

    return "\n".join(lines)


class ProgressDialog:
    """
    A context manager for progress dialogs.
    
    This class provides a convenient way to use progress dialogs in a with statement.
    It automatically creates and shows the dialog when entering the context,
    and closes it when exiting the context.
    
    Example:
    --------
    with ProgressDialog("Processing", "Processing files...", 0, 100) as progress:
        for i in range(100):
            # Do some work
            progress.update_progress(i, f"Processing file {i}")
            
    # Or with a worker thread:
    with ProgressDialog("Processing", "Processing files...") as progress:
        worker = Worker(my_function, arg1, arg2)
        progress.start_worker(worker)
    """
    def __init__(self, title, label_text, min_value=0, max_value=100, parent=None):
        self.dialog = EnhancedProgressDialog(title, label_text, min_value, max_value, parent)
        self.thread_pool = QtCore.QThreadPool()
        
    def __enter__(self):
        self.dialog.show()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dialog.finish()
        return False  # Don't suppress exceptions
        
    def update_progress(self, value, text=None):
        """Update the progress dialog"""
        self.dialog.update_progress(value, text)
        
    def update_text(self, text):
        """Update the dialog text"""
        self.dialog.update_text(text)
        
    def start_worker(self, worker):
        """
        Start a worker in a background thread.
        
        Parameters:
        -----------
        worker : Worker
            The worker to start
        """
        # Connect worker signals to dialog updates
        worker.signals.progress.connect(self.dialog.setValue)
        
        # Start the worker
        self.thread_pool.start(worker)


class _StatusBarTask:
    """One operation's slice of a window's status bar.

    Duck-types the surface :class:`chisurf.gui.progress.ChiSurfProgress` drives
    (``setLabelText`` / ``setRange`` / ``setValue`` / ``wasCanceled`` /
    ``finish`` / ``close``), so it is interchangeable with the modal dialog and
    the inline AutoForm bar.
    """

    def __init__(self, host: "StatusBarProgressHost", message: str, maximum: int, cancel=None):
        self._host = host
        self._cancel = cancel
        self._cancelled = False
        self._value = 0
        self._maximum = int(maximum)
        host._begin(self, message, self._maximum, cancel is not None)

    # -- the QProgressDialog surface -----------------------------------------

    def setLabelText(self, text: str) -> None:  # noqa: N802 (Qt-style)
        """Change the message beside the bar."""
        self._host._set_text(self, str(text))

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802
        """Set the step range; ``(0, 0)`` renders a busy indicator."""
        self._maximum = int(maximum)
        self._host._set_range(self, int(minimum), int(maximum))

    def setValue(self, value: int) -> None:  # noqa: N802
        """Report that *value* steps are done."""
        self._value = int(value)
        self._host._set_value(self, self._value)

    def value(self) -> int:
        """Steps reported so far."""
        return self._value

    def maximum(self) -> int:
        """Steps the operation declared."""
        return self._maximum

    def wasCanceled(self) -> bool:  # noqa: N802
        """Whether the user pressed Cancel."""
        return self._cancelled

    def finish(self, *_args, **_kwargs) -> None:
        """Release the status bar."""
        self._host._end(self)

    def close(self) -> None:
        """Release the status bar."""
        self._host._end(self)

    # -- from the Cancel button ----------------------------------------------

    def _request_cancel(self) -> None:
        """Record the request and push it to the work, if it asked to know."""
        self._cancelled = True
        if callable(self._cancel):
            self._cancel()


class StatusBarProgressHost(QtWidgets.QWidget):
    """Renders a tool window's running operation in its own status bar.

    Attached lazily to any ``QMainWindow`` that starts progress without an
    inline ``progress`` section — see
    :func:`chisurf.gui.progress.find_progress_host`. A standalone tool would
    otherwise get a **modal** dialog, which is the wrong answer for work that
    was moved off the GUI thread to keep the window usable.

    Only the most recent operation is shown; the widget hides itself when none
    is running, so a tool that never starts one looks unchanged.
    """

    def __init__(self, window: QtWidgets.QMainWindow):
        super().__init__()
        self._task = None
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self._label = QtWidgets.QLabel(self)
        layout.addWidget(self._label)

        self._bar = QtWidgets.QProgressBar(self)
        self._bar.setMaximumWidth(140)
        self._bar.setFixedHeight(12)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._cancel_button = QtWidgets.QToolButton(self)
        self._cancel_button.setText("✕")
        self._cancel_button.setAutoRaise(True)
        self._cancel_button.setToolTip("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_button)

        window.statusBar().addPermanentWidget(self)
        self.setVisible(False)

    # -- the host contract ----------------------------------------------------

    def begin_task(self, message: str, maximum: int = 0, cancel=None) -> _StatusBarTask:
        """Start showing an operation. Returns its handle."""
        return _StatusBarTask(self, message, maximum, cancel)

    # -- driven by the task ---------------------------------------------------

    def _begin(self, task, message: str, maximum: int, cancellable: bool) -> None:
        self._task = task
        self._label.setText(message)
        self._bar.setRange(0, int(maximum))
        self._bar.setValue(0)
        self._cancel_button.setVisible(bool(cancellable))
        self.setVisible(True)

    def _set_text(self, task, text: str) -> None:
        if task is self._task:
            self._label.setText(text)

    def _set_range(self, task, minimum: int, maximum: int) -> None:
        if task is self._task:
            self._bar.setRange(int(minimum), int(maximum))

    def _set_value(self, task, value: int) -> None:
        if task is self._task:
            self._bar.setValue(int(value))

    def _end(self, task) -> None:
        # A superseded task's `close` must not blank the bar of the one that
        # replaced it.
        if task is self._task:
            self._task = None
            self._label.clear()
            self.setVisible(False)

    def _on_cancel(self) -> None:
        if self._task is not None:
            self._task._request_cancel()
