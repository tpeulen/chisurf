from __future__ import annotations

import math

from qtpy import QtCore, QtGui, QtWidgets


class ScientificDoubleSpinBox(QtWidgets.QAbstractSpinBox):
    """Qt-native numeric spinbox with scientific-notation display.

    A self-contained ``QAbstractSpinBox`` — the canonical numeric input used
    across ChiSurf — with no third-party dependencies. It supports:

    * constructor kwargs ``value``, ``dec``, ``decimals``, ``suffix``,
      ``finite``, ``int``, ``step``, ``bounds`` (``[lo, hi]``; either entry may
      be ``None``), ``min`` and ``max``;
    * methods ``value()`` / ``setValue()`` / ``setRange()`` / ``setDecimals()``;
    * signals ``editingFinished`` (Qt-native) plus ``sigValueChanged(self)`` and
      ``sigValueChanging(self, value)``.

    ``int=True`` forces integer values (``value()`` returns ``int``) and additive
    stepping; ``dec=True`` uses ±1% multiplicative stepping, otherwise stepping
    is additive by ``step``. ``finite=False`` permits ``±inf``.
    """

    #: value-change signals (``self``) and (``self``, ``value``)
    sigValueChanged = QtCore.Signal(object)  # (self,)
    sigValueChanging = QtCore.Signal(object, object)  # (self, value)

    def __init__(
        self,
        parent=None,
        *,
        dec: bool = True,
        decimals: int = 4,
        suffix: str = "",
        finite: bool = True,
        value: float = 0.0,
        int: bool = False,
        step: float | None = None,
        bounds=None,
        min=None,
        max=None,
        compactHeight=False,
    ):
        super().__init__(parent)
        self._is_int = bool(int)
        # Integer mode steps additively; decimal mode is meaningless there.
        self._dec = False if self._is_int else dec
        self._decimals = decimals
        self._suffix = suffix
        self._finite = finite
        self._step_factor = 0.01  # 1% per step in dec mode

        if step is not None:
            self._step = float(step)
        elif self._is_int:
            self._step = 1.0
        else:
            self._step = None

        lo = hi = None
        if bounds is not None:
            lo, hi = bounds[0], bounds[1]
        if min is not None:
            lo = min
        if max is not None:
            hi = max
        self._min = float(lo) if lo is not None else None
        self._max = float(hi) if hi is not None else None

        self._compactHeight = bool(compactHeight)

        # Backwards-compat dict read by FittingParameterDetailPopup
        self.opts: dict = {"decimals": decimals, "compactHeight": self._compactHeight}

        self._value = self._clamp(self._coerce(value))
        self._refresh_display()
        self.lineEdit().editingFinished.connect(self._commit_text)

    # --------------------------------------------------------- value coercion
    def _coerce(self, v: float) -> float:
        v = float(v)
        if self._is_int and math.isfinite(v):
            v = float(round(v))
        return v

    def _clamp(self, v: float) -> float:
        if math.isnan(v):
            return v
        if self._min is not None and v < self._min:
            v = self._min
        if self._max is not None and v > self._max:
            v = self._max
        return v

    # ------------------------------------------------------------------ value
    def value(self):
        if self._is_int and math.isfinite(self._value):
            return int(self._value)
        return self._value

    def setValue(self, v: float) -> None:
        v = self._clamp(self._coerce(v))
        if v == self._value:
            return
        self._value = v
        self._refresh_display()
        self._emit_changed()

    def setRange(self, lo, hi) -> None:
        self._min = float(lo) if lo is not None else None
        self._max = float(hi) if hi is not None else None
        clamped = self._clamp(self._value)
        if clamped != self._value:
            self.setValue(clamped)

    def setDecimals(self, decimals: int) -> None:
        self._decimals = int(decimals)
        self.opts["decimals"] = int(decimals)
        self._refresh_display()

    # ---------------------------------------------------------------- size hint
    def sizeHint(self):
        hint = super().sizeHint()
        if self._compactHeight:
            return QtCore.QSize(hint.width(), 20)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        if self._compactHeight:
            return QtCore.QSize(hint.width(), 20)
        return hint

    # ---------------------------------------------------------- display helpers
    def _format(self, v: float) -> str:
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        if self._is_int:
            return f"{int(v)}"
        if self._decimals <= 0:
            return f"{v:.0f}"
        return f"{v:.{self._decimals}g}"

    def _refresh_display(self) -> None:
        le = self.lineEdit()
        le.blockSignals(True)
        le.setText(self._format(self._value) + self._suffix)
        le.blockSignals(False)

    def _emit_changed(self) -> None:
        self.sigValueChanging.emit(self, self._value)
        self.sigValueChanged.emit(self)

    # ------------------------------------------------------------ input commit
    def interpretText(self) -> None:  # noqa: N802 (Qt naming)
        """Adopt the text currently in the line edit as this widget's value.

        Qt's item delegates call ``interpretText()`` on a spin-box editor before
        reading its value, because a spin box only turns typed text into a value
        when it is committed.  ``QAbstractSpinBox::interpretText`` is not virtual
        and knows nothing about the value *this* subclass manages, so this
        override is what a delegate has to call (see
        :class:`chisurf.gui.autoform.sections.parameter_table._FloatEditDelegate`).
        Without it, a number typed into a parameter-table cell was thrown away on
        commit and the cell snapped back to its previous value.

        Unparsable text (an aborted entry such as ``"1e"``) leaves the value
        untouched and restores the display.
        """
        text = self.lineEdit().text().strip()
        if self._suffix and text.endswith(self._suffix):
            text = text[: -len(self._suffix)].strip()
        try:
            v = float(text)
        except ValueError:
            self._refresh_display()
            return
        v = self._clamp(self._coerce(v))
        changed = v != self._value
        self._value = v
        self._refresh_display()
        if changed:
            self._emit_changed()

    def _commit_text(self) -> None:
        self.interpretText()
        # The inner QLineEdit's editingFinished is a *different signal object*
        # from this widget's own, and QAbstractSpinBox does not forward it for a
        # subclass that manages its own value -- so it has to be re-emitted here.
        # Without it, typing a value and pressing Enter (or clicking away)
        # updated the display and emitted sigValueChanged but never reached
        # consumers listening on editingFinished, which is what every
        # FittingParameterWidget connects to: the number changed on screen and
        # the model, the fit and the plots kept the old one. Stepping with the
        # arrows worked, because stepBy() emits it explicitly -- hence "the plot
        # updates sometimes".
        self.editingFinished.emit()

    # ------------------------------------------------ QAbstractSpinBox contract
    def stepBy(self, steps: int) -> None:
        if self._dec and self._value != 0.0 and math.isfinite(self._value):
            v = self._value * (1.0 + self._step_factor) ** steps
        elif self._step is not None:
            v = self._value + self._step * steps
        else:
            v = self._value + float(steps)
        v = self._clamp(self._coerce(v))
        changed = v != self._value
        self._value = v
        self._refresh_display()
        if changed:
            self._emit_changed()
        self.editingFinished.emit()

    def stepEnabled(self) -> QtWidgets.QAbstractSpinBox.StepEnabled:
        return self.StepUpEnabled | self.StepDownEnabled

    def validate(self, text: str, pos: int):
        stripped = text.strip()
        if self._suffix and stripped.endswith(self._suffix):
            stripped = stripped[: -len(self._suffix)].strip()
        if stripped in ("", "-", "+", "inf", "-inf", "+inf"):
            return (QtGui.QValidator.Intermediate, text, pos)
        if stripped and stripped[-1] in ("e", "E"):
            return (QtGui.QValidator.Intermediate, text, pos)
        if len(stripped) >= 2 and stripped[-2:] in ("e-", "e+", "E-", "E+"):
            return (QtGui.QValidator.Intermediate, text, pos)
        try:
            float(stripped)
            return (QtGui.QValidator.Acceptable, text, pos)
        except ValueError:
            return (QtGui.QValidator.Invalid, text, pos)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self.isEnabled() or self.isReadOnly():
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        self.stepBy(steps)
        event.accept()
