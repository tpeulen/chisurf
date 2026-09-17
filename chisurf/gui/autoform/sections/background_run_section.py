"""Reusable AutoForm section: start/stop a model's background job and watch it.

A model that samples, simulates or scans runs its work in a thread and reports
progress on itself. Every such editor then needs the same three things — a start
button, a stop button, and something that repaints while the job runs — and
hand-rolling them is how the ProteinMC editor ended up with a Qt worker, two
throttling timers and a modal progress dialog inside the model class.

Declare it instead::

    {"type": "custom", "key": "background_run", "options": {
        "start_action": "start_sampling",
        "stop_action": "stop_sampling",
        "running_attr": "is_sampling",
        "progress_attr": "sampling_progress",
        "status_attr": "sampling_status",
        "start_label": "▶ Sample",
        "interval_ms": 500}}

The model stays Qt-free: it exposes two zero-arg methods and up to three
read-only attributes. This section owns the timer, and while the job runs it
refreshes the hosting form *and* the fit's plots at ``interval_ms`` — throttling
that repaint is the whole reason a timer is used rather than a signal per frame,
because the plots redraw in O(frames) and a sampler emits far faster than a
screen refreshes.

Options
-------
``start_action`` / ``stop_action`` : str
    Zero-arg model methods. ``stop_action`` may be omitted for a job that cannot
    be interrupted; its button is then not shown.
``running_attr`` : str
    Model attribute (or zero-arg method) that is true while the job runs. Drives
    which button is enabled and whether the timer keeps ticking.
``progress_attr`` : str, optional
    Completion as a fraction (0–1) or a percentage (0–100).
``status_attr`` : str, optional
    A line of text shown under the bar.
``interval_ms`` : int, default 500
    How often the view is re-read while the job runs.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf import logging

from .registry import register_section


def _read(model, name: str, default=None):
    """Return ``model.name``, calling it when it is a method."""
    if not name:
        return default
    value = getattr(model, name, None)
    if value is None:
        return default
    try:
        return value() if callable(value) else value
    except Exception as exc:  # pragma: no cover - model-defined
        logging.warning(f"background_run: reading {name!r} failed: {exc}")
        return default


@register_section("background_run")
class BackgroundRunWidget(QtWidgets.QWidget):
    """Start/stop buttons, a progress bar and a status line for a model's job."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options):
        """Build the run controls for *model* from the section options."""
        super().__init__()
        self._model = getattr(model, target) if target else model
        self._opts = options
        self._start_action = str(options.get("start_action", ""))
        self._stop_action = str(options.get("stop_action", ""))
        self._running_attr = str(options.get("running_attr", ""))
        self._progress_attr = str(options.get("progress_attr", ""))
        self._status_attr = str(options.get("status_attr", ""))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(4)
        self.start_button = QtWidgets.QToolButton()
        self.start_button.setText(str(options.get("start_label", "▶ Run")))
        self.start_button.setToolTip(
            str(options.get("start_description", "Start the run in the background."))
        )
        self.start_button.clicked.connect(self._on_start)
        buttons.addWidget(self.start_button)

        self.stop_button = None
        if self._stop_action:
            self.stop_button = QtWidgets.QToolButton()
            self.stop_button.setText(str(options.get("stop_label", "■ Stop")))
            self.stop_button.setToolTip(
                str(options.get("stop_description", "Ask the run to stop."))
            )
            self.stop_button.clicked.connect(self._on_stop)
            buttons.addWidget(self.stop_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        layout.addWidget(self.bar)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.status)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(50, int(options.get("interval_ms", 500))))
        self._timer.timeout.connect(self._tick)
        self.refresh()

    # -- actions -------------------------------------------------------

    def _call(self, action: str) -> None:
        """Invoke a zero-arg model method named by an option."""
        method = getattr(self._model, action, None)
        if not callable(method):
            logging.warning(
                f"background_run: {action!r} is not a method of {type(self._model).__name__}"
            )
            return
        method()

    def _on_start(self) -> None:
        """Start the job and begin watching it."""
        self._call(self._start_action)
        self._timer.start()
        self.refresh()

    def _on_stop(self) -> None:
        """Ask the job to stop; the timer keeps running until it actually does."""
        self._call(self._stop_action)
        self.refresh()

    # -- watching ------------------------------------------------------

    def _tick(self) -> None:
        """Re-read the model and repaint the editor and the fit's plots."""
        self.refresh()
        self._refresh_views()
        if not self._running():
            self._timer.stop()
            # One last repaint after the job ends, so the final frame is the one
            # left on screen rather than the second-to-last.
            self._refresh_views()

    def _running(self) -> bool:
        """Whether the model reports the job as in flight."""
        return bool(_read(self._model, self._running_attr, False))

    def _refresh_views(self) -> None:
        """Repaint the hosting form and the fit's plot tabs."""
        form = self.parent()
        while form is not None and not hasattr(form, "refresh_plots"):
            form = form.parent()
        if form is not None:
            try:
                form.refresh_plots()
            except Exception as exc:  # pragma: no cover - defensive
                logging.debug(f"background_run: form refresh failed: {exc}")
        fit = getattr(self._model, "fit", None)
        for plot in list(getattr(fit, "plots", []) or []):
            try:
                plot.update()
            except Exception as exc:  # pragma: no cover - plot-defined
                logging.debug(f"background_run: plot refresh failed: {exc}")

    def refresh(self) -> None:
        """Re-read the run state into the buttons, the bar and the status line."""
        running = self._running()
        self.start_button.setEnabled(not running)
        if self.stop_button is not None:
            self.stop_button.setEnabled(running)
        fraction = _read(self._model, self._progress_attr, 0.0)
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            fraction = 0.0
        # Accept a fraction or a percentage: a model that reports 0-100 and one
        # that reports 0-1 must both fill the bar rather than pin it at 1 %.
        percent = fraction * 100.0 if fraction <= 1.0 else fraction
        self.bar.setValue(int(max(0.0, min(100.0, percent))))
        self.status.setText(str(_read(self._model, self._status_attr, "") or ""))
        if running and not self._timer.isActive():
            self._timer.start()
