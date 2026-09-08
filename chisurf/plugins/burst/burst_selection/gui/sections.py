"""Custom AutoForm sections for the burst-selection display settings.

One section, ``burst_time_window``: the viewport the diagnostic plots draw.

It exists because the plots were unreadable by default. Every file in the
selection is concatenated and drawn at once, so a six-file measurement puts
eleven million photons and half an hour of acquisition into one trace — an
envelope with no bursts visible in it, and no way to get at one except by
typing photon indices.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform.sections.registry import register_section

logger = logging.getLogger(__name__)

#: How much of the measurement the plots show by default, in seconds. Ten
#: seconds of a single-molecule measurement is a few hundred bursts: enough to
#: judge a threshold by eye, few enough that individual bursts are resolved.
DEFAULT_WINDOW_S = 10.0

#: Steps of the position slider. Fine enough that one step is a fraction of a
#: window on any measurement, coarse enough to drag smoothly.
_SLIDER_STEPS = 1000


@register_section("burst_time_window")
def burst_time_window(model, target=None, **options):
    """The time viewport: window length, position slider, and what is on screen."""
    return _TimeWindowSection(model)


class _TimeWindowSection(QtWidgets.QWidget):
    """Window length + a position slider over the concatenated timeline.

    The slider is the answer to "which file am I looking at": its label names
    the file under the current position and its place in the selection, because
    on a concatenated timeline a position in seconds is otherwise not something
    anyone can map back to a measurement.

    Everything here writes the tool's existing photon-index range, which is what
    the plots already draw — so this is a second, humane way to say the same
    thing rather than a second mechanism.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._updating = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.enabled_box = QtWidgets.QCheckBox("Show a window of", self)
        self.enabled_box.setChecked(True)
        self.enabled_box.setToolTip(
            "Draw only part of the measurement.\n\nUnchecked, the plots draw "
            "every photon of every file at once — which on a multi-file "
            "measurement is millions of photons in a plot a thousand pixels "
            "wide, where no individual burst can be seen."
        )
        self.enabled_box.toggled.connect(self._on_changed)
        row.addWidget(self.enabled_box)

        self.length_spin = QtWidgets.QDoubleSpinBox(self)
        self.length_spin.setRange(0.01, 100000.0)
        self.length_spin.setDecimals(2)
        self.length_spin.setSingleStep(1.0)
        self.length_spin.setSuffix(" s")
        self.length_spin.setValue(DEFAULT_WINDOW_S)
        self.length_spin.setToolTip(
            "Length of the visible window, in seconds. Ten seconds is a few "
            "hundred bursts: enough to judge a threshold by eye, few enough "
            "that individual bursts are resolved."
        )
        self.length_spin.valueChanged.connect(self._on_changed)
        row.addWidget(self.length_spin)
        row.addStretch(1)
        layout.addLayout(row)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setRange(0, _SLIDER_STEPS)
        self.slider.setToolTip(
            "Move the visible window through the measurement. The label below "
            "says which file it has reached."
        )
        self.slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self.slider)

        # Dragging the slider emits a value per pixel of travel. Re-filtering the
        # photons for each of those is tens of milliseconds of work thrown away
        # -- the queue simply grows behind the mouse and the control feels stuck.
        # The caption and the photon range follow the handle immediately; the
        # re-filter waits for the drag to settle.
        self._reload_timer = QtCore.QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(120)
        self._reload_timer.timeout.connect(self._apply_window)

        self.caption = QtWidgets.QLabel("Run a burst search to see the trace.", self)
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)

        model.add_display_observer(self._refresh)
        self._refresh()

    # -- state ----------------------------------------------------------

    def _position_s(self, span: float) -> float:
        """Where the window starts, from the slider's fraction of the span."""
        length = float(self.length_spin.value())
        travel = max(0.0, span - length)
        return travel * (self.slider.value() / _SLIDER_STEPS)

    def _on_changed(self, *_args) -> None:
        """Apply the viewport, then relabel it."""
        if self._updating:
            return
        span = float(self._model.timeline_span())
        if span <= 0.0:
            return
        self.length_spin.setEnabled(self.enabled_box.isChecked())
        self.slider.setEnabled(self.enabled_box.isChecked())
        self._relabel()
        self._reload_timer.start()

    def _apply_window(self) -> None:
        """Re-filter the diagnostics for where the handle came to rest."""
        span = float(self._model.timeline_span())
        if span <= 0.0:
            return
        if not self.enabled_box.isChecked():
            # Whole measurement: the diagnostics must cover it before the plots
            # are told to draw it, or the trace is empty outside the last window.
            self._model.set_diagnostic_window(None, 0.0)
            self._model.show_whole_timeline()
            return
        start = self._position_s(span)
        length = float(self.length_spin.value())
        self._model.set_diagnostic_window(length, start)
        self._model.show_time_window(start, length)

    def _refresh(self) -> None:
        """Re-read the timeline after a search (its span and files changed)."""
        if self._updating:
            return
        self._updating = True
        try:
            span = float(self._model.timeline_span())
            self.setEnabled(span > 0.0)
            if span > 0.0 and self.length_spin.value() > span:
                self.length_spin.setValue(span)
        finally:
            self._updating = False
        if span > 0.0 and self.enabled_box.isChecked():
            self._on_changed()
        else:
            self._relabel()

    def _relabel(self) -> None:
        """Say what is on screen: the seconds, the file, and its place."""
        span = float(self._model.timeline_span())
        if span <= 0.0:
            self.caption.setText("Run a burst search to see the trace.")
            return
        if not self.enabled_box.isChecked():
            self.caption.setText(
                f"Whole measurement — {span:.1f} s, "
                f"{self._model.timeline_file_count()} file(s)."
            )
            return
        start = self._position_s(span)
        stop = min(span, start + float(self.length_spin.value()))
        name, position, total = self._model.timeline_file_at(start)
        where = f" · {name} ({position}/{total})" if name else ""
        self.caption.setText(f"{start:.1f}–{stop:.1f} s of {span:.1f} s{where}")
