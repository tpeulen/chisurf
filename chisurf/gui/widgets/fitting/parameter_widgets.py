from __future__ import annotations

import os
import typing
import pathlib
import textwrap

import numpy as np
from qtpy import QtWidgets, uic, QtCore, QtGui
from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox
import matplotlib.colors as mcolors

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting
import chisurf.core.decorators
import chisurf.gui.decorators
import chisurf.core.settings

import chisurf.gui.widgets
import chisurf.gui.widgets.experiments.widgets
from chisurf.gui.widgets.general import Controller
from chisurf.core.math.optimization.leastsqbound import OptimizationCancelled
from chisurf.core.actions import record_action
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client
from chisurf.macros.core_fit import link_fit_group

parameter_settings = chisurf.core.settings.parameter


#: Smooth-prior families offered by the advanced prior editor. Each entry maps a
#: display label to the prior ``kind`` (see :mod:`chisurf.core.fitting.priors`)
#: and its editable parameters ``(key, label, default)``. Box/uniform bounds are
#: the degenerate uniform prior and are edited through the radio selector's
#: inline bound spinboxes, not here.
_PRIOR_FAMILY_SPECS = [
    ("Gaussian", "normal", [("mu", "Mean μ", 0.0), ("sigma", "Std σ", 1.0)]),
    ("Truncated Gaussian", "truncated_normal",
     [("mu", "Mean μ", 0.0), ("sigma", "Std σ", 1.0), ("lb", "Lower", 0.0), ("ub", "Upper", 1.0)]),
    ("Log-normal", "lognormal", [("mu", "Mean of ln x", 0.0), ("sigma", "Std of ln x", 0.5)]),
    ("Half-normal", "half_normal", [("sigma", "Std σ", 1.0), ("loc", "Edge", 0.0)]),
    ("Exponential", "exponential", [("scale", "Mean scale", 1.0), ("loc", "Edge", 0.0)]),
    ("Gamma", "gamma", [("alpha", "Shape α", 2.0), ("beta", "Rate β", 1.0), ("loc", "Edge", 0.0)]),
    ("Beta", "beta", [("alpha", "Shape α", 2.0), ("beta", "Shape β", 2.0)]),
]
_PRIOR_KIND_TO_SPEC = {kind: (label, params) for (label, kind, params) in _PRIOR_FAMILY_SPECS}

#: Combo entry for the uniform/box prior, i.e. "no smooth prior, just bounds".
_PRIOR_KIND_BOX = "box"

#: Combo entry standing in for a prior this editor cannot express (callback and
#: product priors, typically attached from a script). Selecting it is a no-op;
#: it exists so the combo can *report* such a prior instead of silently showing
#: an unrelated family.
_PRIOR_KIND_OTHER = "__other__"


def _controller_decimals(controller, editor_name: str, default: int = 6) -> int:
    """Decimals of a controller's editor, falling back when it has none.

    :class:`FittingParameterProxyController` carries no editors, so the popup
    uses ``default`` for those controllers.
    """
    editor = getattr(controller, editor_name, None)
    opts = getattr(editor, "opts", None)
    if isinstance(opts, dict):
        return opts.get("decimals", default)
    return default


class FittingParameterDetailPopup(QtWidgets.QDialog):

    def __init__(self, controller: 'FittingParameterWidget'):
        super().__init__(controller)
        # Use Popup flag so clicks outside cause deactivation; we then hide on focus loss
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Popup)
        self.controller = controller
        self.setObjectName('FittingParameterDetailPopup')
        # Ensure we hide if the window deactivates (extra safety beyond Qt.Popup)
        self.installEventFilter(self)
        # Ensure the popup can take focus and is activated when shown
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, False)
        # Counter to temporarily suspend auto-hide on focus loss (e.g., while link menu is open)
        self._suspend_auto_hide = 0
        # The popup is a dense inspector: rows are merged where they read
        # naturally together (title+link, value+fixed, lower+upper) so it stays
        # small enough to sit next to the parameter it edits.
        self.setStyleSheet(
            "#FittingParameterDetailPopup QLabel,"
            "#FittingParameterDetailPopup QCheckBox,"
            "#FittingParameterDetailPopup QRadioButton { font-size: 10pt }"
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Header: name, link state and the link actions share one row.
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(4)
        self.lbl_title = QtWidgets.QLabel(f"{controller.fitting_parameter.name}")
        font = self.lbl_title.font()
        font.setBold(True)
        self.lbl_title.setFont(font)
        self.lbl_link = QtWidgets.QLabel("")
        self.lbl_link.setStyleSheet("color: gray; font-size: 9pt")
        self.btn_change_link = QtWidgets.QToolButton()
        self.btn_change_link.setText("🔗 Link…")
        self.btn_change_link.setToolTip("Link this parameter to another parameter")
        self.btn_unlink = QtWidgets.QToolButton()
        self.btn_unlink.setText("✂️ Unlink")
        self.btn_unlink.setToolTip("Detach this parameter from the one it is linked to")
        header_row.addWidget(self.lbl_title)
        header_row.addWidget(self.lbl_link, 1)
        header_row.addWidget(self.btn_change_link)
        header_row.addWidget(self.btn_unlink)
        layout.addLayout(header_row)

        # Optional human-readable description of the parameter, taken from
        # the underlying Parameter/FittingParameter "description" attribute.
        self.lbl_description = QtWidgets.QLabel("")
        self.lbl_description.setWordWrap(True)
        self.lbl_description.setStyleSheet("color: gray; font-size: 9pt")
        layout.addWidget(self.lbl_description)

        # Value editor and the "fixed" flag share one row.
        val_row = QtWidgets.QHBoxLayout()
        val_row.setSpacing(4)
        val_row.addWidget(QtWidgets.QLabel("Value:"))
        self.sb_value = ScientificDoubleSpinBox(
            dec=True,
            decimals=_controller_decimals(controller, 'widget_value'),
            finite=False,
        )
        self.sb_value.setMaximumWidth(140)
        val_row.addWidget(self.sb_value, 1)
        self.cb_fixed = QtWidgets.QCheckBox("Fixed")
        val_row.addWidget(self.cb_fixed)
        layout.addLayout(val_row)

        # Prior row. A parameter's prior generalises its bounds: the "Box" choice
        # is the uniform prior (the usual lower/upper bounds), while the other
        # choices attach a smooth prior that pulls the fit toward a value
        # (maximum-a-posteriori). One combo selects among all of them — a radio
        # row covering only the common families alongside a family combo meant
        # the same state was shown twice.
        prior_row = QtWidgets.QHBoxLayout()
        prior_row.setSpacing(4)
        prior_row.addWidget(QtWidgets.QLabel("Prior:"))
        self.cb_prior_family = QtWidgets.QComboBox()
        self.cb_prior_family.addItem("Box (bounds only)", _PRIOR_KIND_BOX)
        for label, kind, _ in _PRIOR_FAMILY_SPECS:
            self.cb_prior_family.addItem(label, kind)
        self.cb_prior_family.setToolTip(
            "Box keeps the plain lower/upper bounds; the other families attach a "
            "smooth prior pulling the fit toward a value"
        )
        prior_row.addWidget(self.cb_prior_family, 1)
        layout.addLayout(prior_row)

        # Box/uniform sub-widgets (shown only when "Box" is selected): the
        # enable flag and both bounds fit on a single row.
        self._bounds_box = QtWidgets.QWidget()
        b_layout = QtWidgets.QHBoxLayout(self._bounds_box)
        b_layout.setContentsMargins(0, 0, 0, 0)
        b_layout.setSpacing(4)
        self.cb_bounds_on = QtWidgets.QCheckBox("Bounds")
        b_layout.addWidget(self.cb_bounds_on)
        self.sb_lb = ScientificDoubleSpinBox(
            dec=True, decimals=_controller_decimals(controller, 'widget_lower_bound')
        )
        self.sb_lb.setToolTip("Lower bound")
        self.sb_ub = ScientificDoubleSpinBox(
            dec=True, decimals=_controller_decimals(controller, 'widget_upper_bound')
        )
        self.sb_ub.setToolTip("Upper bound")
        for lbl, sb in (("Low:", self.sb_lb), ("High:", self.sb_ub)):
            b_layout.addWidget(QtWidgets.QLabel(lbl))
            sb.setMaximumWidth(110)
            b_layout.addWidget(sb, 1)
        layout.addWidget(self._bounds_box)

        # Smooth-prior parameters, inline. They are edited here rather than
        # behind a second modal: this popup *is* the parameter editor, and
        # pushing two clicks and another window in front of "set sigma" made a
        # routine edit feel like an advanced feature.
        self._prior_box = QtWidgets.QWidget()
        p_layout = QtWidgets.QVBoxLayout(self._prior_box)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(4)

        self._prior_form_host = QtWidgets.QWidget()
        self._prior_form = QtWidgets.QFormLayout(self._prior_form_host)
        self._prior_form.setContentsMargins(0, 0, 0, 0)
        self._prior_form.setSpacing(4)
        p_layout.addWidget(self._prior_form_host)

        #: One spin box per parameter of the selected family, keyed as in
        #: :data:`_PRIOR_FAMILY_SPECS`.
        self._prior_spins: typing.Dict[str, ScientificDoubleSpinBox] = {}

        #: Shown instead of the form for families this editor cannot express
        #: (callback and product priors), which stay read-only.
        self.lbl_prior_summary = QtWidgets.QLabel("")
        self.lbl_prior_summary.setStyleSheet("color: gray; font-size: 9pt")
        self.lbl_prior_summary.setWordWrap(True)
        p_layout.addWidget(self.lbl_prior_summary)

        layout.addWidget(self._prior_box)

        #: Guard so programmatic combo/spin updates in ``refresh_from_model`` do
        #: not re-trigger the change handlers.
        self._prior_refreshing = False

        # Connections
        self.btn_change_link.clicked.connect(self._on_change_link)
        self.btn_unlink.clicked.connect(self._on_unlink)
        self.cb_fixed.toggled.connect(self._on_fixed_toggled)
        self.cb_bounds_on.toggled.connect(self._on_bounds_on_toggled)
        self.sb_lb.editingFinished.connect(self._on_bounds_changed)
        self.sb_ub.editingFinished.connect(self._on_bounds_changed)
        self.sb_value.editingFinished.connect(self._on_value_changed)
        self.cb_prior_family.currentIndexChanged.connect(self._on_prior_family_changed)

        self.refresh_from_model()

    def _begin_suspend_auto_hide(self):
        try:
            self._suspend_auto_hide += 1
        except Exception:
            self._suspend_auto_hide = 1

    def _end_suspend_auto_hide(self):
        try:
            self._suspend_auto_hide -= 1
            if self._suspend_auto_hide < 0:
                self._suspend_auto_hide = 0
        except Exception:
            self._suspend_auto_hide = 0

    def _owns(self, widget) -> bool:
        """Whether ``widget`` belongs to this popup, across window boundaries.

        ``QWidget.isAncestorOf`` is confined to a single window, so it reports
        False for a combo box's drop-down or a menu — those live in their own
        top-level window even though they are parented to one of our children.
        Walking ``parentWidget()`` does cross that boundary, which is what makes
        "is the user still interacting with this popup?" answerable.
        """
        while widget is not None:
            if widget is self:
                return True
            widget = widget.parentWidget()
        return False

    def _child_window_is_open(self) -> bool:
        """Whether one of the popup's own windows — a drop-down, a menu — is up.

        Such a window both takes the focus and deactivates this one, so without
        this test the popup dismisses itself the moment the prior drop-down is
        opened.
        """
        return any(
            w is not self and w.isWindow() and w.isVisible() and self._owns(w)
            for w in QtWidgets.QApplication.topLevelWidgets()
        )

    def _may_auto_hide(self) -> bool:
        """Common precondition of both dismissal paths."""
        if getattr(self, '_suspend_auto_hide', 0) > 0 or not self.isVisible():
            return False
        return not self._child_window_is_open()

    def _hide_if_focus_left(self):
        """Hide unless focus is still on one of the popup's own widgets.

        The popup receives a ``FocusOut`` whenever one of its children takes
        focus — clicking the value spin box raises one — so hiding on the event
        itself closed the popup on the very interactions it exists for. The
        check is deferred to the event loop because the incoming focus widget is
        only settled once the transition completes.
        """
        if self._may_auto_hide() and not self._owns(QtWidgets.QApplication.focusWidget()):
            self.hide()

    def _hide_if_window_deactivated(self):
        """Hide when another window took over.

        Deliberately does not consult the focus widget: Qt keeps pointing it at
        this popup's last-focused child while the application is in the
        background, so consulting it would keep the popup alive after the user
        switched away.
        """
        if self._may_auto_hide():
            self.hide()

    def eventFilter(self, obj, event):
        if event is not None:
            et = int(event.type())
            # Both are deferred: opening our own drop-down raises them too, and
            # only once the transition settles can it be told from an unrelated
            # window taking over.
            if et == int(QtCore.QEvent.WindowDeactivate):
                QtCore.QTimer.singleShot(0, self._hide_if_window_deactivated)
                return False
            if et == int(QtCore.QEvent.FocusOut):
                QtCore.QTimer.singleShot(0, self._hide_if_focus_left)
                return False
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        QtCore.QTimer.singleShot(0, self._hide_if_focus_left)
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Close on a click outside the popup.

        ``Qt.Popup`` grabs the mouse, so clicks anywhere on screen arrive here;
        those landing outside the popup's own rectangle dismiss it.
        """
        if not self.rect().contains(event.pos()):
            self.hide()
            return
        super().mousePressEvent(event)

    def _on_change_link(self):
        menu = self.controller.build_link_menu()
        # Show menu under the button
        pos = self.btn_change_link.mapToGlobal(QtCore.QPoint(0, self.btn_change_link.height()))
        # While the menu is open and linking occurs, do not auto-hide the popup
        self._begin_suspend_auto_hide()
        try:
            menu.exec_(pos)
            # After possible changes, refresh UI/model
            self.controller.finalize()
            self.refresh_from_model()
        finally:
            self._end_suspend_auto_hide()
            # Keep the popup open and focused after linking
            try:
                self.raise_()
                self.activateWindow()
                self.setFocus(QtCore.Qt.PopupFocusReason)
            except Exception:
                pass

    def _on_unlink(self):
        fp = self.controller.fitting_parameter
        source = self.controller._parameter_context(fp)
        fc = get_fitting_client()
        if fc is not None:
            fc.unlink_parameter(
                parameter_name=str(fp.name),
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_unlink",
            f"unlink parameter '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                **source,
            },
        )
        self.controller.finalize()
        self.controller._update_linked_parameters()
        self.refresh_from_model()

    def _on_fixed_toggled(self):
        fp = self.controller.fitting_parameter
        new_fixed = self.cb_fixed.isChecked()
        source = self.controller._parameter_context(fp)
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_fixed(
                parameter_name=str(fp.name),
                fixed=new_fixed,
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_fixed",
            f"set fixed={new_fixed} for parameter '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "fixed": bool(new_fixed),
                **source,
            },
        )
        self.controller.finalize()
        self.refresh_from_model()

    def _on_bounds_on_toggled(self):
        fp = self.controller.fitting_parameter
        checked = self.cb_bounds_on.isChecked()
        source = self.controller._parameter_context(fp)
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_bounds_on(
                parameter_name=str(fp.name),
                bounds_on=checked,
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_bounds_on",
            f"set bounds_on={checked} for parameter '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "bounds_on": bool(checked),
                **source,
            },
        )
        self.sb_lb.setEnabled(checked)
        self.sb_ub.setEnabled(checked)
        if checked:
            bounds_valid = False
            try:
                b = getattr(fp, 'bounds', None)
                bounds_valid = isinstance(b, (tuple, list)) and len(b) == 2
            except Exception:
                bounds_valid = False
            if not bounds_valid:
                if fc is not None:
                    fc.set_parameter_bounds(
                        parameter_name=str(fp.name),
                        bounds=(self.sb_lb.value(), self.sb_ub.value()),
                        fit_uid=source.get("fit_uid"),
                    )
                self.controller._trace_operation(
                    "parameter_bounds_set",
                    f"initialize bounds for parameter '{fp.name}' to ({self.sb_lb.value()}, {self.sb_ub.value()})",
                    {
                        "parameter_name": str(fp.name),
                        "lower": float(self.sb_lb.value()),
                        "upper": float(self.sb_ub.value()),
                        **source,
                    },
                )
        self.controller.finalize()
        self.refresh_from_model()

    def _on_bounds_changed(self):
        fp = self.controller.fitting_parameter
        source = self.controller._parameter_context(fp)
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_bounds(
                parameter_name=str(fp.name),
                bounds=(self.sb_lb.value(), self.sb_ub.value()),
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_bounds_set",
            f"set bounds for parameter '{fp.name}' to ({self.sb_lb.value()}, {self.sb_ub.value()}) in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "lower": float(self.sb_lb.value()),
                "upper": float(self.sb_ub.value()),
                **source,
            },
        )
        self.controller.finalize()
        self.refresh_from_model()

    def _apply_prior(self, state):
        """Set (or clear) a smooth prior via local echo + RPC.

        ``state`` is a prior state dict (``{"kind": ..}``) or ``None`` to clear
        it. The local echo keeps the widget consistent in every API mode; the
        RPC applies it on the backend when a fitting client is installed.
        """
        fp = self.controller.fitting_parameter
        source = self.controller._parameter_context(fp)
        try:
            fp.prior = state
        except Exception as e:
            cs.logging.warning(f"Could not set prior for '{fp.name}': {e}")
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_prior(
                parameter_name=str(fp.name),
                prior=state,
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_prior_set",
            f"set prior={state} for parameter '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "prior": state,
                **source,
            },
        )
        self.controller.finalize()
        self.refresh_from_model()

    def _on_prior_family_changed(self, *args):
        """Apply the family chosen in the combo, seeding its default parameters."""
        if self._prior_refreshing:
            return
        kind = self.cb_prior_family.currentData()
        if kind is None or kind == _PRIOR_KIND_OTHER:
            # The "other" entry only reports a script-attached prior; selecting
            # it must not overwrite that prior with a guess.
            return
        if kind == _PRIOR_KIND_BOX:
            # Box == uniform prior: clear any smooth prior; bounds are edited via
            # the inline "Bounds" + low/high widgets.
            self._apply_prior(None)
            return
        self._apply_prior(self._seeded_prior_state(kind))

    def _on_prior_param_changed(self):
        """Apply the prior after one of its parameter spin boxes was edited."""
        if self._prior_refreshing:
            return
        kind = self.cb_prior_family.currentData()
        if kind not in _PRIOR_KIND_TO_SPEC:
            return
        state = {"kind": kind}
        for key, sb in self._prior_spins.items():
            state[key] = float(sb.value())
        self._apply_prior(state)

    def _seeded_prior_state(self, kind: str) -> dict:
        """Default state for ``kind``, with location parameters at the current value.

        A width defaults to a tenth of the parameter's magnitude rather than to a
        flat 1.0: a prior on a rate of 1e-3 and one on a lifetime of 4 ns need
        very different scales, and an absolute default would pin the first and
        barely constrain the second.
        """
        import math
        try:
            seed = float(self.controller.fitting_parameter.value)
        except Exception:
            seed = 1.0
        scaled_sigma = abs(seed) * 0.1
        _, params = _PRIOR_KIND_TO_SPEC[kind]
        state = {"kind": kind}
        for key, _label, default in params:
            value = default
            if key in ("mu", "loc") and kind != "lognormal":
                value = seed
            elif key == "mu" and kind == "lognormal" and seed > 0:
                value = math.log(seed)
            elif key == "sigma" and kind != "lognormal" and scaled_sigma > 0:
                value = scaled_sigma
            state[key] = value
        return state

    def _rebuild_prior_form(self, kind: str, state: dict):
        """Rebuild the parameter spin boxes for ``kind``, filled from ``state``."""
        while self._prior_form.rowCount():
            self._prior_form.removeRow(0)
        self._prior_spins = {}
        spec = _PRIOR_KIND_TO_SPEC.get(kind)
        if spec is None:
            return
        _, params = spec
        for key, label, default in params:
            sb = ScientificDoubleSpinBox(dec=True, decimals=6, finite=False)
            try:
                sb.setValue(float(state.get(key, default)))
            except Exception:
                sb.setValue(float(default))
            sb.editingFinished.connect(self._on_prior_param_changed)
            self._prior_spins[key] = sb
            self._prior_form.addRow(label, sb)

    def _on_value_changed(self):
        fp = self.controller.fitting_parameter
        old_value = float(fp.value)
        source = self.controller._parameter_context(fp)
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_value(
                parameter_name=str(fp.name),
                value=self.sb_value.value(),
                fit_uid=source.get("fit_uid"),
            )
        self.controller._trace_operation(
            "parameter_value",
            f"set value for parameter '{fp.name}' from {old_value} to {self.sb_value.value()} in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "old_value": float(old_value),
                "new_value": float(self.sb_value.value()),
                **source,
            },
        )
        self.controller.finalize()
        self.controller._update_linked_parameters()
        self.controller._trigger_model_update()

    def refresh_from_model(self):
        fp = self.controller.fitting_parameter
        # Description text (may be empty)
        try:
            desc = getattr(fp, 'description', "")
        except Exception:
            desc = ""
        self.lbl_description.setVisible(bool(desc))
        if desc:
            self.lbl_description.setText(str(desc))
        # Update link label
        if getattr(fp, 'link', None) is not None:
            target_group, target_local = self.controller._locate_parameter(fp.link)
            # Keep the header row narrow: the short form goes on the label, the
            # full origin of the link into its tooltip.
            self.lbl_link.setText(f"→ {fp.link.name}")
            self.lbl_link.setToolTip(
                f"Linked to: {fp.link.name} ({target_group} / {target_local})"
            )
            self.btn_unlink.setEnabled(True)
        else:
            self.lbl_link.setText("Not linked")
            self.lbl_link.setToolTip("")
            self.btn_unlink.setEnabled(False)
        # Value
        try:
            v = float(fp.value)
        except Exception:
            v = self.sb_value.value()
        self.sb_value.setValue(v)
        # Fixed
        self.cb_fixed.blockSignals(True)
        self.cb_fixed.setChecked(bool(fp.fixed))
        self.cb_fixed.blockSignals(False)
        # Bounds
        self.cb_bounds_on.blockSignals(True)
        self.sb_lb.blockSignals(True)
        self.sb_ub.blockSignals(True)
        self.cb_bounds_on.setChecked(bool(fp.bounds_on))
        # Enable/disable editors based on bounds_on
        self.sb_lb.setEnabled(bool(fp.bounds_on))
        self.sb_ub.setEnabled(bool(fp.bounds_on))
        try:
            b = getattr(fp, 'bounds', None)
            if isinstance(b, (tuple, list)) and len(b) == 2 and b[0] is not None and b[1] is not None:
                lb, ub = b
                if np.isfinite(float(lb)):
                    self.sb_lb.setValue(float(lb))
                if np.isfinite(float(ub)):
                    self.sb_ub.setValue(float(ub))
        except Exception:
            pass
        self.cb_bounds_on.blockSignals(False)
        self.sb_lb.blockSignals(False)
        self.sb_ub.blockSignals(False)

        self._refresh_prior_selector(fp)

    def _refresh_prior_selector(self, fp):
        """Sync the prior combo, bounds visibility and summary from ``fp.prior``.

        A uniform/absent prior selects "Box" and shows the inline bound editors;
        any family this editor knows selects its own entry and shows its
        parameter spin boxes; a prior it cannot express (callback, product)
        selects the read-only "other" entry and shows a summary instead.
        """
        from chisurf.core.fitting.priors import UniformPrior
        try:
            prior = getattr(fp, "prior", None)
        except Exception:
            prior = None

        is_box = prior is None or isinstance(prior, UniformPrior)

        # Which family is actually attached, and with what parameters.
        state = {}
        try:
            st = prior.get_state() if prior is not None else None
            if isinstance(st, dict):
                state = st
        except Exception:
            state = {}
        kind = state.get("kind")
        editable = kind in _PRIOR_KIND_TO_SPEC

        self._prior_refreshing = True
        try:
            self._set_prior_combo_kind(
                _PRIOR_KIND_BOX if is_box else (kind if editable else _PRIOR_KIND_OTHER),
                summary="" if (is_box or editable) else repr(prior),
            )
            self._bounds_box.setVisible(is_box)
            self._prior_box.setVisible(not is_box)
            if is_box:
                return
            self._prior_form_host.setVisible(editable)
            self.lbl_prior_summary.setVisible(not editable)
            if editable:
                self._rebuild_prior_form(kind, state)
            else:
                # Callback and product priors have no editable parameter list;
                # show what they are rather than pretending they are editable.
                self.lbl_prior_summary.setText(repr(prior))
        finally:
            self._prior_refreshing = False

    def _set_prior_combo_kind(self, kind: str, summary: str = ""):
        """Select ``kind`` in the family combo, materialising the "other" entry.

        The read-only entry for script-attached priors is added on demand and
        removed again once a real family is selected, so the dropdown only ever
        offers it while it applies.
        """
        other_idx = self.cb_prior_family.findData(_PRIOR_KIND_OTHER)
        if kind == _PRIOR_KIND_OTHER:
            label = f"Other: {summary}" if summary else "Other (not editable here)"
            if other_idx < 0:
                self.cb_prior_family.addItem(label, _PRIOR_KIND_OTHER)
                other_idx = self.cb_prior_family.count() - 1
            else:
                self.cb_prior_family.setItemText(other_idx, label)
            self.cb_prior_family.setCurrentIndex(other_idx)
            return
        if other_idx >= 0:
            self.cb_prior_family.removeItem(other_idx)
        idx = self.cb_prior_family.findData(kind)
        if idx >= 0:
            self.cb_prior_family.setCurrentIndex(idx)




class ParameterActionsMixin:
    """Parameter-centric actions shared by every parameter editor.

    Provides the fit/local-fit lookup helpers, the provenance trace hook, and
    the link menu for a single :class:`~chisurf.core.fitting.parameter.FittingParameter`
    exposed as ``self.fitting_parameter``.  It is mixed into
    :class:`FittingParameterWidget` (the per-parameter row widget) and into
    :class:`FittingParameterProxyController`, which lets views without a row
    widget — such as the AutoForm parameter table — offer the same linking and
    detail-popup behaviour.
    """

    def _locate_parameter(self, parameter) -> typing.Tuple[str, str]:
        fit_group_label = "?"
        local_fit_label = "?"
        try:
            fits = getattr(chisurf, "fits", [])
            for fit_group_idx, fit_group in enumerate(fits):
                group_name = str(getattr(fit_group, "name", f"fit_group_{fit_group_idx}"))
                for local_idx, local_fit in enumerate(fit_group):
                    local_name = str(getattr(local_fit, "name", f"local_fit_{local_idx}"))
                    model = getattr(local_fit, "model", None)
                    if model is None:
                        continue
                    params = getattr(model, "parameters_all", [])
                    for p in params:
                        if p is parameter:
                            return group_name, local_name
                        try:
                            if getattr(p, "_port", None) is getattr(parameter, "_port", object()):
                                return group_name, local_name
                        except Exception:
                            pass
            return fit_group_label, local_fit_label
        except Exception:
            return fit_group_label, local_fit_label

    def _locate_parameter_uids(self, parameter) -> typing.Tuple[str, str, str]:
        fit_uid = ""
        local_fit_uid = ""
        parameter_uid = str(getattr(parameter, "unique_identifier", ""))
        try:
            fits = getattr(chisurf, "fits", [])
            for fit_group in fits:
                fg_uid = str(getattr(fit_group, "unique_identifier", ""))
                for local_fit in fit_group:
                    lf_uid = str(getattr(local_fit, "unique_identifier", ""))
                    model = getattr(local_fit, "model", None)
                    if model is None:
                        continue
                    params = getattr(model, "parameters_all", [])
                    for p in params:
                        if p is parameter:
                            return fg_uid, lf_uid, parameter_uid
                        try:
                            if getattr(p, "_port", None) is getattr(parameter, "_port", object()):
                                return fg_uid, lf_uid, parameter_uid
                        except Exception:
                            pass
            return fit_uid, local_fit_uid, parameter_uid
        except Exception:
            return fit_uid, local_fit_uid, parameter_uid

    def _parameter_indices(self, parameter) -> typing.Tuple[int, int]:
        """Return (fit_group_idx, local_idx) for the given parameter."""
        fit_objects = get_fitting_client().get_fit_objects()
        for fit_group_idx, fit_group in enumerate(fit_objects):
            for local_idx, local_fit in enumerate(fit_group):
                local_fit_model = getattr(local_fit, "model", None)
                if local_fit_model is None:
                    continue
                params = getattr(local_fit_model, "parameters_all", [])
                for p in params:
                    if p is parameter:
                        return fit_group_idx, local_idx
        for fit_group_idx, fit_group in enumerate(fit_objects):
            for local_idx, local_fit in enumerate(fit_group):
                local_fit_model = getattr(local_fit, "model", None)
                if local_fit_model is None:
                    continue
                params = getattr(local_fit_model, "parameters_all", [])
                for p in params:
                    try:
                        if getattr(p, "_port", None) is getattr(parameter, "_port", object()):
                            return fit_group_idx, local_idx
                    except Exception:
                        pass
        return -1, -1

    def _parameter_context(self, parameter) -> typing.Dict[str, str]:
        group_name, local_name = self._locate_parameter(parameter)
        group_uid, local_uid, param_uid = self._locate_parameter_uids(parameter)
        return {
            "fit_group": str(group_name),
            "local_fit": str(local_name),
            "fit_uid": str(group_uid),
            "local_fit_uid": str(local_uid),
            "parameter_uid": str(param_uid),
        }

    def _trace_operation(self, action_type: str, summary: str, payload: typing.Dict[str, typing.Any] = None) -> None:
        payload_data = payload or {}
        try:
            source_uid = str(getattr(self.fitting_parameter, "unique_identifier", ""))
            event = record_action(
                action_type=str(action_type),
                summary=str(summary),
                payload=payload_data,
                source_uid=source_uid,
            )
            if event is not None:
                return
        except Exception:
            pass
        line = f"# HIST {str(action_type)}: {str(summary)}"
        try:
            log_fn = getattr(chisurf, "log", None)
            if callable(log_fn):
                log_fn(line)
            else:
                chisurf.logging.info(line)
        except Exception:
            pass

    def _build_details_tooltip_text(self) -> str:
        fp = self.fitting_parameter
        source_group, source_local = self._locate_parameter(fp)
        lines = [str(getattr(fp, 'name', ''))+":"]
        lines.append(f"Fit: {source_group}")
        lines.append(f"Local fit: {source_local}")

        try:
            desc = getattr(fp, 'description', "")
        except Exception:
            desc = ""
        if desc:
            desc_lines = []
            for para in str(desc).splitlines():
                wrapped = textwrap.wrap(para, width=30)
                if wrapped:
                    desc_lines.extend(wrapped)
                else:
                    desc_lines.append("")
            lines.append("\n".join(desc_lines).strip())

        # Link info
        link_param = getattr(fp, 'link', None)
        if bool(getattr(fp, 'is_linked', False)) and link_param is not None:
            target_param_name = getattr(link_param, 'name', "?")
            target_group, target_local = self._locate_parameter(link_param)
            lines.append("")
            lines.append(textwrap.fill(
                f"Linked to fit '{target_group}', local fit '{target_local}', parameter '{target_param_name}'",
                width=60
            ))
        else:
            lines.append("")
            lines.append("Not linked")

        # Value / fixed
        try:
            v = float(getattr(fp, 'value', float('nan')))
        except Exception:
            v = float('nan')
        lines.append(f"Value: {v}")
        lines.append(f"Fixed: {bool(getattr(fp, 'fixed', False))}")

        # Bounds
        if bool(getattr(fp, 'bounds_on', False)):
            b = getattr(fp, 'bounds', None)
            if isinstance(b, (tuple, list)) and len(b) == 2:
                lines.append(f"Bounds: ({b[0]}, {b[1]})")
            else:
                lines.append("Bounds: on (unset)")
        else:
            lines.append("Bounds: off")

        return "\n".join([l for l in lines if l is not None])

    def make_linkcall(self, target_parameter: chisurf.core.fitting.parameter.FittingParameter):
        def linkcall():
            try:
                self.blockSignals(True)

                param_self = self.fitting_parameter
                param_other = target_parameter

                if param_other is param_self:
                    return

                # Check for recursion using the Parameter class method
                if param_self.check_recursive_link(param_other, param_self):
                    QtWidgets.QMessageBox.warning(
                        self,  # Parent widget
                        "Linking Error",
                        "Recursion detected: Cannot link a parameter to itself or create a cyclic dependency.",
                        QtWidgets.QMessageBox.Ok
                    )
                else:
                    tooltip = " linked to " + str(getattr(param_other, "name", "?"))
                    source_group, source_local = self._locate_parameter(param_self)
                    target_group, target_local = self._locate_parameter(param_other)
                    source_group_uid, source_local_uid, source_param_uid = self._locate_parameter_uids(param_self)
                    target_group_uid, target_local_uid, target_param_uid = self._locate_parameter_uids(param_other)
                    source_fit_idx, source_local_idx = self._parameter_indices(param_self)
                    target_fit_idx, target_local_idx = self._parameter_indices(param_other)
                    get_fitting_client().link_parameters(
                        parameter_name=str(param_self.name),
                        target_parameter_name=str(param_other.name),
                        fit_uid=source_group_uid,
                        target_fit_uid=target_group_uid,
                        local_idx=source_local_idx if source_local_idx >= 0 else None,
                        target_local_idx=target_local_idx if target_local_idx >= 0 else None,
                    )
                    self._trace_operation(
                        "parameter_link",
                        (
                            f"link '{param_self.name}' ({source_group}/{source_local}) -> "
                            f"'{param_other.name}' ({target_group}/{target_local})"
                        ),
                        {
                            "source_parameter": str(param_self.name),
                            "target_parameter": str(param_other.name),
                            "source_fit_group": source_group,
                            "source_local_fit": source_local,
                            "target_fit_group": target_group,
                            "target_local_fit": target_local,
                            "source_fit_uid": source_group_uid,
                            "source_local_fit_uid": source_local_uid,
                            "source_parameter_uid": source_param_uid,
                            "target_fit_uid": target_group_uid,
                            "target_local_fit_uid": target_local_uid,
                            "target_parameter_uid": target_param_uid,
                        },
                    )

                    # Refresh this widget from the underlying parameter so it
                    # reflects the follower/linked role. The target parameter
                    # (master) remains visually unchanged (no check mark), so
                    # the user can always use this row's checkbox to unlink.
                    link_cb = getattr(self, "widget_link", None)
                    if link_cb is not None:
                        link_cb.setToolTip(tooltip)
                    try:
                        self.finalize()
                        # Update the linked parameter to show master's value
                        self._update_linked_parameters()
                    except Exception:
                        pass

            finally:
                self.blockSignals(False)

        return linkcall

    def build_link_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self)
        menu.setTitle(
            "Link " + self.fitting_parameter.name + " to:"
        )

        fc = get_fitting_client()
        if fc is not None:
            # Build menu from DTOs via RPC
            fits_data = fc.list_fits()
            for fit_dto in fits_data:
                fit_uid = fit_dto.get("uid", "")
                fit_detail = fc.get_fit(fit_uid=fit_uid)
                model_data = fit_detail.get("model", {})
                params = model_data.get("parameters_all", [])
                submenu = QtWidgets.QMenu(menu)
                submenu.setTitle(fit_dto.get("name", "Fit"))
                action_submenu = QtWidgets.QMenu(submenu)
                action_submenu.setTitle("All parameters")
                for p in params:
                    pname = p.get("name", "")
                    if pname != self.fitting_parameter.name:
                        Action = action_submenu.addAction(pname)
                        Action.triggered.connect(
                            self.make_linkcall_by_name(pname, fit_dto)
                        )
                submenu.addMenu(action_submenu)
                menu.addMenu(submenu)
        return menu

    def make_linkcall_by_name(self, target_name: str, target_fit_dto: dict):
        """Create a closure that links this parameter to a target by name."""
        param_self = self.fitting_parameter

        def linkcall():
            fc = get_fitting_client()
            if fc is not None:
                fc.link_parameters(
                    parameter_name=str(param_self.name),
                    target_parameter_name=target_name,
                    fit_uid=target_fit_dto.get("uid"),
                )
            self.finalize()
            self._update_linked_parameters()

        return linkcall

    def _update_linked_parameters(self):
        try:
            if not self.fitting_parameter.is_linked:
                master_param = self.fitting_parameter
                fc = get_fitting_client()
                if fc is not None:
                    # Update via RPC - fit.model.finalize will handle linked params
                    fit_uid = getattr(master_param, "fit_uid", None) or (
                        self._parameter_context(master_param).get("fit_uid"))
                    if fit_uid:
                        fc.model_finalize(fit_uid=fit_uid)
        except Exception:
            pass

    def _trigger_model_update(self):
        """Recompute the owning fit and refresh visible output parameters."""
        try:
            fc = get_fitting_client()
            if fc is not None:
                fit_uid = self._parameter_context(self.fitting_parameter).get("fit_uid")
                if fit_uid:
                    fc.update_fit(fit_uid=fit_uid)
                    fc.model_finalize(fit_uid=fit_uid)
            # ``fc.update_fit`` publishes ``fit.updated``, which the main window
            # turns into a single ``_refresh_fit_display`` (trace redraw) on the
            # next subscriber poll. Do not redraw here as well — one refresh per
            # value change is enough.
            # Fallback (UI-scoped): refresh visible output parameter widgets
            try:
                root = self.window()
                if root is not None:
                    for w in root.findChildren(QtWidgets.QWidget):
                        try:
                            if not bool(getattr(w, "_is_output_param", False)):
                                continue
                            if hasattr(w, "finalize"):
                                w.finalize()
                        except Exception:
                            continue
            except Exception:
                pass
        except Exception:
            pass


class FittingParameterProxyController(ParameterActionsMixin, QtWidgets.QWidget):
    """Minimal stand-in for :class:`FittingParameterWidget` around one parameter.

    Views that render parameters themselves (e.g. the AutoForm parameter table)
    have no per-parameter row widget, yet the link menu and
    :class:`FittingParameterDetailPopup` are written against a controller.  This
    proxy supplies exactly that contract — ``fitting_parameter`` plus a
    :meth:`finalize` that notifies the owning view — without building any of the
    row's editors.

    Parameters
    ----------
    fitting_parameter : chisurf.core.fitting.parameter.FittingParameter
        The parameter the actions operate on.
    parent : QtWidgets.QWidget or None
        Parent widget; also the parent of popups and menus created from here.
    on_change : callable or None
        Called with no arguments whenever :meth:`finalize` runs, i.e. after any
        edit made through the popup or the link menu.
    """

    def __init__(
        self,
        fitting_parameter: chisurf.core.fitting.parameter.FittingParameter,
        parent: typing.Optional[QtWidgets.QWidget] = None,
        on_change: typing.Optional[typing.Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.setVisible(False)
        self.fitting_parameter = fitting_parameter
        self._on_change = on_change

    def finalize(self, *args) -> None:
        """Notify the owning view that the parameter changed."""
        cb = self._on_change
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

    def set_linked(self, is_linked: bool) -> None:
        """Absorb the link-state notification and repaint the owning view.

        ``Parameter.link``'s setter calls this on the controller. The row widget
        uses it to retitle its link checkbox and disable the value editor, but a
        proxy owns no editors — the view draws the parameter itself — so there is
        nothing to update beyond telling that view to redraw. Without this method
        the call raised ``AttributeError`` and linking a parameter from any
        AutoForm parameter table failed outright.
        """
        self.finalize()


class FittingParameterWidget(ParameterActionsMixin, Controller):

    def contextMenuEvent(self, event: QtGui.QCloseEvent):

        menu = self.build_link_menu()
        menu.exec_(event.globalPos())

    def __str__(self):
        return ""

    def _build_layout(self) -> None:
        """Build the two-row compact layout in Python (replaces variable_widget.ui)."""
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_row = QtWidgets.QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(2)

        self.label = QtWidgets.QLabel("name")
        self.label.setMinimumWidth(40)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        main_row.addWidget(self.label)

        compact_cb_style = "QCheckBox { spacing: 0px; min-height: 14px; max-height: 16px; }"

        self.widget_fix = QtWidgets.QCheckBox()
        self.widget_fix.setToolTip("fix value")
        self.widget_fix.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.widget_fix.setStyleSheet(compact_cb_style)
        main_row.addWidget(self.widget_fix)

        self.widget_link = QtWidgets.QCheckBox()
        self.widget_link.setTristate(True)
        self.widget_link.setToolTip("link — right-click to link, uncheck to unlink")
        self.widget_link.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.widget_link.setStyleSheet(compact_cb_style)
        main_row.addWidget(self.widget_link)

        self.widget_bounds_on = QtWidgets.QCheckBox()
        self.widget_bounds_on.setToolTip("enable bounds")
        self.widget_bounds_on.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.widget_bounds_on.setStyleSheet(compact_cb_style)
        main_row.addWidget(self.widget_bounds_on)

        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSpacing(0)
        main_row.addLayout(self.horizontalLayout, 1)

        self.lineEdit = QtWidgets.QLineEdit()
        self.lineEdit.setMaximumWidth(36)
        self.lineEdit.setReadOnly(True)
        self.lineEdit.setPlaceholderText("NA")
        self.lineEdit.setToolTip("estimated error of fit — click to run support-plane analysis")
        self.lineEdit.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        main_row.addWidget(self.lineEdit)
        outer.addLayout(main_row)

        self.widget = QtWidgets.QWidget()
        self.widget.setVisible(False)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.widget)
        self.horizontalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout_2.setSpacing(2)
        outer.addWidget(self.widget)

        self.widget_bounds_on.toggled.connect(self.widget.setVisible)

    def __init__(
            self,
            fitting_parameter: chisurf.core.fitting.parameter.FittingParameter,
            layout: QtWidgets.QLayout = None,
            decimals: int = None,
            hide_label: bool = None,
            hide_error: bool = None,
            fixable: bool = None,
            hide_bounds: bool = None,
            name: str = None,
            label_text: str = None,
            hide_link: bool = None,
            suffix: str = "",
            label_width: int = None,
            callback: typing.Callable = None
    ):
        super().__init__()
        try:
            cs.core.base.Base.__init__(self)
        except Exception:
            pass
        self._build_layout()
        if hide_link is None:
            hide_link = parameter_settings.get('hide_link', False)
        if hide_bounds is None:
            hide_bounds = parameter_settings.get('hide_bounds', False)
        if name is None:
            name = self.__class__.__name__
        if label_text is None:
            label_text = name
        if fixable is None:
            fixable = True
        if hide_error is None:
            hide_error = parameter_settings.get('hide_error', False)
        if hide_label is None:
            hide_label = parameter_settings.get('hide_label', False)
        if decimals is None:
            decimals = parameter_settings.get('decimals', 3)

        self.callback = callback
        self.name = fitting_parameter.name
        self.fitting_parameter = fitting_parameter
        self._details_popup = None  # created lazily on first label click
        self._is_output_param = bool(getattr(fitting_parameter, "is_output", False))
        
        # Capture absolute fit index at creation time to avoid dynamic lookup issues
        try:
            self._absolute_fit_idx = fitting_parameter.fit_idx
            if not isinstance(self._absolute_fit_idx, int) or self._absolute_fit_idx < 0:
                fc = get_fitting_client()
                n_fits = fc.fit_count() if fc is not None else 0
                if self._absolute_fit_idx == -1 and n_fits > 0:
                    self._absolute_fit_idx = 0
        except Exception:
            self._absolute_fit_idx = 0
        self._absolute_fit_idx = self._resolve_fit_idx(default=self._absolute_fit_idx)

        # Allow HTML/RichText labels (e.g. "cpm<sub>all</sub>") so that
        # parameter names can be decorated with subscripts/superscripts
        # while keeping the underlying parameter name unchanged.
        try:
            self.label.setTextFormat(QtCore.Qt.RichText)
        except Exception:
            pass

        self.widget_value = ScientificDoubleSpinBox(
            dec=True,
            decimals=decimals,
            suffix=suffix,
            finite=False,
            compactHeight=True,
        )
        self.widget_value.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.horizontalLayout.addWidget(self.widget_value)

        self.widget_lower_bound = ScientificDoubleSpinBox(
            dec=True, decimals=decimals, compactHeight=True,
        )
        self.horizontalLayout_2.addWidget(self.widget_lower_bound)

        self.widget_upper_bound = ScientificDoubleSpinBox(
            dec=True, decimals=decimals, compactHeight=True,
        )
        self.horizontalLayout_2.addWidget(self.widget_upper_bound)

        # Hide and disable widgets
        self.label.setVisible(not hide_label)
        if label_width is not None:
            self.label.setMinimumWidth(label_width)
        self.lineEdit.setVisible(not hide_error)
        self._hide_bounds = bool(hide_bounds)
        self.widget_bounds_on.setDisabled(hide_bounds)
        self.widget_bounds_on.setVisible(not hide_bounds)
        self.widget_fix.setVisible(fixable)
        self.widget_link.setDisabled(hide_link)
        self.widget_link.setVisible(not hide_link)

        if hide_error:
            try:
                self.label.setMinimumWidth(80)
                sp = self.label.sizePolicy()
                sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Preferred)
                self.label.setSizePolicy(sp)
            except Exception:
                pass
            try:
                self.lineEdit.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
                self.lineEdit.setMinimumSize(0, 0)
                self.lineEdit.setMaximumSize(0, 0)
            except Exception:
                pass

        if self._is_output_param:
            # Output parameters are displayed as read-only result cells.
            # Keep the row layout identical (checkboxes stay visible) but
            # prevent any user interaction and remove spin buttons so the
            # value looks like a plain, non-editable field.
            self.widget_fix.setVisible(False)
            self.widget_bounds_on.setVisible(False)
            self.widget_link.setVisible(False)
            try:
                self.label.setMinimumWidth(80)
                sp = self.label.sizePolicy()
                sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Preferred)
                self.label.setSizePolicy(sp)
            except Exception:
                pass
            self.widget_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            try:
                self.widget_value.setReadOnly(True)
            except Exception:
                pass
            try:
                # Avoid focus so wheel / keyboard cannot change the value.
                self.widget_value.setFocusPolicy(QtCore.Qt.NoFocus)
            except Exception:
                pass
            try:
                self.widget_fix.setEnabled(False)
            except Exception:
                pass
            try:
                self.widget_bounds_on.setEnabled(False)
            except Exception:
                pass
            try:
                self.widget_link.setEnabled(False)
            except Exception:
                pass
        # Make label interactive: clicking opens a details popup
        try:
            self.label.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            try:
                self.label.setToolTip(self._build_details_tooltip_text() + "\n\nClick to view and edit details")
            except Exception:
                try:
                    self.label.setToolTip(f"{getattr(self.fitting_parameter, 'name', '')}\n\nClick to view and edit details")
                except Exception:
                    self.label.setToolTip("Click to view and edit details")
            # install a mousePress handler
            self.label.mousePressEvent = self._on_label_mouse_press  # type: ignore
        except Exception:
            pass

        try:
            self.lineEdit.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            self.lineEdit.mousePressEvent = self._on_error_field_mouse_press  # type: ignore
        except Exception:
            pass

        # Display of values
        try:
            _init_v = float(fitting_parameter.value)
        except Exception:
            _init_v = self.widget_value.value() if hasattr(self, 'widget_value') else 0.0
        self.widget_value.setValue(_init_v)
        # Do not left-pad HTML labels with spaces; this breaks rich text.
        # For plain-text labels we keep the original padding.
        try:
            if "<" in label_text or ">" in label_text:
                self.label.setText(label_text)
            else:
                self.label.setText(label_text.ljust(5))
        except Exception:
            self.label.setText(label_text)

        # variable bounds — reflect bounds_on in the checkbox, but keep the
        # second (bounds-editing) row collapsed at init to stay compact. The
        # row only expands when the user clicks the checkbox; we block signals
        # here so programmatic setCheckState does not auto-expand it.
        bounds_on_init = bool(fitting_parameter.bounds_on) and not hide_bounds
        self.widget_bounds_on.blockSignals(True)
        self.widget_bounds_on.setCheckState(
            QtCore.Qt.Checked if bounds_on_init else QtCore.Qt.Unchecked
        )
        self.widget_bounds_on.blockSignals(False)
        self.widget.setVisible(False)

        # variable fixed
        if fitting_parameter.fixed:
            self.widget_fix.setCheckState(QtCore.Qt.Checked)
        else:
            self.widget_fix.setCheckState(QtCore.Qt.Unchecked)

        # The variable value
        self.widget_value.editingFinished.connect(self._on_main_value_changed)
        if callback:
            self.widget_value.editingFinished.connect(self.callback)

        self.widget_fix.toggled.connect(self._on_main_fixed_toggled)

        # Variable is bounded
        self.widget_bounds_on.toggled.connect(self._on_main_bounds_on_toggled)

        self.widget_lower_bound.editingFinished.connect(self._on_main_bounds_changed)

        self.widget_upper_bound.editingFinished.connect(self._on_main_bounds_changed)

        self.widget_link.clicked.connect(self.onLinkFitGroup)

        if isinstance(layout, QtWidgets.QLayout):
            layout.addWidget(self)
        try:
            self._update_role_visuals()
        except Exception:
            pass

        try:
            self._install_code_badge()
        except Exception:
            pass

    def _install_code_badge(self):
        """Install a code badge for dev mode source jumping."""
        try:
            import chisurf.core.settings
            if not chisurf.core.settings.is_dev_mode():
                return
            if hasattr(self, '_chisurf_code_badge_installed'):
                return
            from chisurf.gui.widgets.code_badge import install_code_badge
            from chisurf.gui.devtools.source_jump import resolve_parameter_group_source
            resolver = lambda: resolve_parameter_group_source(self)
            install_code_badge(self, resolver, corner='top-right', margin=4)
            self._chisurf_code_badge_installed = True
        except Exception:
            pass

    def _on_error_field_mouse_press(self, event: QtGui.QMouseEvent) -> None:
        """Run support-plane analysis when the error field is clicked.

        Parameters
        ----------
        event : QtGui.QMouseEvent
            Mouse event delivered to the read-only error field.

        Returns
        -------
        None
            Left-click starts the adaptive scan; other clicks keep the default
            line-edit behavior.
        """
        if event.button() == QtCore.Qt.LeftButton and not getattr(self, "_is_output_param", False):
            self._run_support_plane_scan()
            event.accept()
            return
        QtWidgets.QLineEdit.mousePressEvent(self.lineEdit, event)

    def _run_support_plane_scan(self) -> None:
        """Run adaptive support-plane analysis for this parameter.

        Returns
        -------
        None
            The scan result and derived error estimate are stored on the
            fitting parameter, then the widget and plots are refreshed.
        """
        fp = self.fitting_parameter
        parameter_name = str(getattr(fp, "name", ""))
        fit_index = self._resolve_fit_idx(default=getattr(fp, "fit_idx", self._absolute_fit_idx))
        self.lineEdit.setEnabled(False)
        try:
            if fit_index is None:
                raise ValueError("No active fit is available for support-plane analysis.")
            fit_obj = get_fitting_client().get_fit_objects()[int(fit_index)]

            def run_scan_directly() -> None:
                """Run the scan without the action controller.

                Returns
                -------
                None
                    The fit stores the full scan result on the parameter.
                """
                fit_obj.adaptive_chi2_scan(
                    parameter_name=parameter_name,
                    scan_range=(None, None),
                    p_value=0.99,
                    max_points_per_side=50,
                )

            controller = getattr(chisurf, "action_controller", None)
            if controller is not None:
                try:
                    controller.execute(
                        name="parameter.adaptive_scan",
                        payload={
                            "parameter_name": parameter_name,
                            "fit_index": int(fit_index),
                            "scan_range": (None, None),
                            "p_value": 0.99,
                            "max_points_per_side": 50,
                        },
                    )
                except Exception:
                    run_scan_directly()
            else:
                run_scan_directly()

            scanned_parameter = fit_obj.model.parameters_all_dict.get(parameter_name, fp)
            self._update_error_estimate_from_scan(scanned_parameter)
            try:
                fit_obj.model.update_plots()
            except Exception:
                pass
            self.finalize()
        except Exception as exc:
            try:
                chisurf.logging.warning(
                    f"FittingParameterWidget: support-plane scan failed for '{parameter_name}': {exc}"
                )
            except Exception:
                pass
            QtWidgets.QMessageBox.warning(
                self,
                "Support-plane analysis failed",
                f"Could not run support-plane analysis for '{parameter_name}'.\n\n{exc}",
                QtWidgets.QMessageBox.Ok,
            )
        finally:
            if not getattr(self, "_is_output_param", False):
                self.lineEdit.setEnabled(True)

    def _update_error_estimate_from_scan(self, parameter) -> None:
        """Update a parameter's scalar error estimate from scan crossings.

        Parameters
        ----------
        parameter : object
            Fitting parameter with a ``scan_result`` dictionary.

        Returns
        -------
        None
            ``parameter.error_estimate`` is updated when at least one finite
            support-plane crossing exists.
        """
        result = getattr(parameter, "scan_result", None)
        if result is None:
            return
        v0 = result.get("v0", getattr(parameter, "value", None))
        crossings = result.get("crossings", ())
        errors = []
        for crossing in crossings:
            try:
                if crossing is not None and np.isfinite(float(crossing)) and np.isfinite(float(v0)):
                    errors.append(abs(float(crossing) - float(v0)))
            except Exception:
                continue
        if errors:
            parameter.error_estimate = float(max(errors))


    def _on_label_mouse_press(self, event: QtGui.QMouseEvent):
        try:
            if event.button() == QtCore.Qt.LeftButton:
                self._open_details_popup()
            else:
                # fall back to default behavior
                super().mousePressEvent(event)
        except Exception:
            pass

    def _open_details_popup(self):
        if getattr(self, "_is_output_param", False):
            return
        # Lazy-create popup
        if self._details_popup is None or not isinstance(self._details_popup, FittingParameterDetailPopup):
            self._details_popup = FittingParameterDetailPopup(self)
        # Position popup under the label
        try:
            global_pos = self.label.mapToGlobal(self.label.rect().bottomLeft())
        except Exception:
            global_pos = QtGui.QCursor.pos()
        self._details_popup.move(global_pos)
        self._details_popup.refresh_from_model()
        self._details_popup.show()
        # Ensure the popup gains focus and is on top
        try:
            self._details_popup.raise_()
            self._details_popup.activateWindow()
            self._details_popup.setFocus(QtCore.Qt.PopupFocusReason)
            # Some platforms need delayed activation
            QtCore.QTimer.singleShot(0, self._details_popup.activateWindow)
        except Exception:
            pass

    def _on_label_mouse_press(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self._open_details_popup()
        else:
            # For other buttons, fall back to default behavior (e.g., open context menu on right click)
            super().mousePressEvent(event)

    def _update_role_visuals(self):
        try:
            if getattr(self, "_is_output_param", False):
                role = "output"
            elif getattr(self.fitting_parameter, "is_linked", False):
                role = "linked"
            else:
                role = "input"
            bg_color = None
            if role == "output":
                bg_color = parameter_settings.get("role_color_output")
            elif role == "linked":
                bg_color = parameter_settings.get("role_color_linked")
            else:
                bg_color = parameter_settings.get("role_color_input")

            value_parts = []
            label_parts = []

            # Output parameters should be visually distinct even when no color
            # is configured in settings.
            if role == "output":
                # Only highlight text (not the whole cell background) to avoid
                # overly strong emphasis in dense parameter tables.
                text_color = bg_color if bg_color else "#caa200"
                value_parts.append(f"color: {text_color};")
                value_parts.append("font-weight: 600;")
                label_parts.append(f"color: {text_color};")
                label_parts.append("font-weight: 600;")
            elif role == "linked":
                if bg_color:
                    value_parts.append(f"background-color: {bg_color};")
                value_parts.append("text-decoration: underline;")
            else:
                if bg_color:
                    value_parts.append(f"background-color: {bg_color};")

            self.widget_value.setStyleSheet(" ".join(value_parts))
            try:
                self.label.setStyleSheet(" ".join(label_parts))
            except Exception:
                pass
        except Exception:
            pass

    def set_linked(self, is_linked: bool):
        if getattr(self, "_is_output_param", False):
            self.widget_link.setCheckState(QtCore.Qt.Unchecked)
            return
        # Interpret linking state in terms of three visual roles:
        #   - Unchecked: not linked at all.
        #   - PartiallyChecked: this parameter follows another one (slave).
        #   - Checked: this parameter is the master within a fit group.
        is_master = bool(getattr(self.fitting_parameter, "is_link_master", False))

        if is_linked:
            # Follower: value is controlled by the master; disable editing
            # and show a partially-checked box.
            self.widget_link.setCheckState(QtCore.Qt.PartiallyChecked)
            self.widget_value.setEnabled(False)
        else:
            if is_master:
                # Master within the fit group: keep value editable but mark
                # the checkbox as fully checked so the user sees it as the
                # source of the group link.
                self.widget_link.setCheckState(QtCore.Qt.Checked)
                self.widget_value.setEnabled(True)
            else:
                # Not linked at all.
                self.widget_link.setCheckState(QtCore.Qt.Unchecked)
                self.widget_value.setEnabled(True)

        try:
            self._update_role_visuals()
        except Exception:
            pass

    def onLinkFitGroup(self):
        # Clicking the link checkbox should have intuitive semantics:
        #
        # - If this parameter is currently a *follower* (linked to some
        #   master), a click unlinks **only this parameter**.
        # - Otherwise (unlinked or acting as fit-group master), we delegate
        #   to the group-level macro so the user can establish or remove a
        #   fit-group link.
        fp = self.fitting_parameter
        if getattr(self, "_is_output_param", False):
            return

        is_linked = bool(getattr(fp, "is_linked", False))
        is_master = bool(getattr(fp, "is_link_master", False))

        self.blockSignals(True)
        try:
            if is_linked and not is_master:
                # Per-parameter unlink: this row was following another
                # parameter via ``fp.link``. Clear the link so only this
                # parameter becomes free again.
                try:
                    source_group, source_local = self._locate_parameter(fp)
                    source_group_uid, source_local_uid, source_param_uid = self._locate_parameter_uids(fp)
                    _, source_local_idx = self._parameter_indices(fp)
                    old_link = getattr(fp, "link", None)
                    old_target_parameter = str(getattr(old_link, "name", "")) if old_link is not None else ""
                    old_target_group, old_target_local = self._locate_parameter(old_link) if old_link is not None else ("", "")
                    old_target_group_uid, old_target_local_uid, old_target_param_uid = self._locate_parameter_uids(old_link) if old_link is not None else ("", "", "")
                    get_fitting_client().unlink_parameter(
                        parameter_name=str(fp.name),
                        fit_uid=source_group_uid,
                        local_idx=source_local_idx if source_local_idx >= 0 else None,
                    )
                    self._trace_operation(
                        "parameter_unlink",
                        f"unlink parameter '{fp.name}' in fit '{source_group}' / local '{source_local}'",
                        {
                            "parameter_name": str(fp.name),
                            "fit_group": source_group,
                            "local_fit": source_local,
                            "fit_uid": source_group_uid,
                            "local_fit_uid": source_local_uid,
                            "parameter_uid": source_param_uid,
                            "old_target_parameter": old_target_parameter,
                            "old_target_fit_group": old_target_group,
                            "old_target_local_fit": old_target_local,
                            "old_target_fit_uid": old_target_group_uid,
                            "old_target_local_fit_uid": old_target_local_uid,
                            "old_target_parameter_uid": old_target_param_uid,
                        },
                    )
                    # Update link/value state and role visuals for all related rows.
                    self._update_linked_parameters()
                    self._refresh_group_link_visuals()
                except Exception:
                    try:
                        chisurf.logging.warning(
                            f"FittingParameterWidget: failed to unlink parameter '{getattr(fp, 'name', '?')}'."
                        )
                    except Exception:
                        pass
            else:
                # Group-level behaviour: link/unlink the whole fit group for
                # this parameter name. The checkbox is tristate, so a user
                # left-click cycles Unchecked -> PartiallyChecked -> Checked;
                # reading the raw post-click state would land an unlinked
                # parameter on PartiallyChecked (== 1), which ``link_fit_group``
                # treats as a no-op. Derive the intent from the parameter's
                # logical role instead: a master toggles the group off (0),
                # anything else toggles it on (2 == establish the group link).
                state = 0 if is_master else 2
                source_group, source_local = self._locate_parameter(fp)
                self._trace_operation(
                    "fit_group_link_toggle",
                    (
                        f"toggle fit-group linking for parameter '{fp.name}' to state={state} "
                        f"from fit '{source_group}' / local '{source_local}'"
                    ),
                    {
                        "parameter_name": str(fp.name),
                        "state": int(state),
                        "fit_group": source_group,
                        "local_fit": source_local,
                    },
                )
                link_fit_group(fp.name, int(state))
                # After group linking/unlinking, update all affected parameters.
                QtCore.QTimer.singleShot(100, self._update_linked_parameters)
                QtCore.QTimer.singleShot(100, self._refresh_group_link_visuals)

            try:
                self.finalize()
            except Exception:
                pass
        finally:
            self.blockSignals(False)

    def setValue(self, v):
        self.widget_value.setValue(v)

    def _refresh_group_link_visuals(self):
        """Refresh link-role visuals for same-named parameters in current fit group."""
        try:
            fp_name = getattr(self.fitting_parameter, "name", None)
            cs = getattr(chisurf, "cs", None)
            current_fit = getattr(cs, "current_fit", None) if cs is not None else None
            if not fp_name or current_fit is None:
                return

            for local_fit in current_fit:
                try:
                    params = getattr(getattr(local_fit, "model", None), "parameters_all_dict", None)
                    if not isinstance(params, dict):
                        continue
                    p = params.get(fp_name)
                    if p is None:
                        continue
                    controller = getattr(p, "controller", None)
                    if controller is not None and hasattr(controller, "finalize"):
                        controller.finalize()
                except Exception:
                    continue
        except Exception:
            pass

    def _on_main_value_changed(self):
        if getattr(self, "_is_output_param", False):
            return
        fp = self.fitting_parameter
        value = self.widget_value.value()
        old_value = float(fp.value)
        source = self._parameter_context(fp)
        try:
            fp.value = value
        except Exception:
            pass
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_value(
                parameter_name=str(fp.name),
                value=value,
                fit_uid=source.get("fit_uid"),
            )
        self._trace_operation(
            "parameter_value",
            f"set value for '{fp.name}' from {old_value} to {value} in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "old_value": float(old_value),
                "new_value": float(value),
                **source,
            },
        )
        self.finalize()
        self._update_linked_parameters()
        self._trigger_model_update()

    def _on_main_bounds_on_toggled(self):
        if getattr(self, "_is_output_param", False):
            return
        fp = self.fitting_parameter
        checked = self.widget_bounds_on.isChecked()
        source = self._parameter_context(fp)
        try:
            fp.bounds_on = checked
        except Exception:
            pass
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_bounds_on(
                parameter_name=str(fp.name),
                bounds_on=checked,
                fit_uid=source.get("fit_uid"),
            )
        self._trace_operation(
            "parameter_bounds_on",
            f"set bounds_on={checked} for '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "bounds_on": bool(checked),
                **source,
            },
        )
        if checked:
            bounds_valid = False
            try:
                b = getattr(fp, 'bounds', None)
                bounds_valid = isinstance(b, (tuple, list)) and len(b) == 2
            except Exception:
                bounds_valid = False
            if not bounds_valid:
                if fc is not None:
                    fc.set_parameter_bounds(
                        parameter_name=str(fp.name),
                        bounds=(self.widget_lower_bound.value(), self.widget_upper_bound.value()),
                        fit_uid=source.get("fit_uid"),
                    )
                self._trace_operation(
                    "parameter_bounds_set",
                    f"initialize bounds for '{fp.name}' to ({self.widget_lower_bound.value()}, {self.widget_upper_bound.value()})",
                    {
                        "parameter_name": str(fp.name),
                        "lower": float(self.widget_lower_bound.value()),
                        "upper": float(self.widget_upper_bound.value()),
                        **source,
                    },
                )
        self.finalize()

    def _resolve_fit_idx(self, default: int = 0):
        fc = get_fitting_client()
        n_fits = fc.fit_count() if fc is not None else 0
        if n_fits <= 0:
            return None

        idx = getattr(self, "_absolute_fit_idx", default)
        if isinstance(idx, int) and 0 <= idx < n_fits:
            return idx

        if not isinstance(idx, int) or idx < 0 or idx >= n_fits:
            idx = 0

        self._absolute_fit_idx = idx
        return idx

    def _on_main_fixed_toggled(self):
        if getattr(self, "_is_output_param", False):
            return
        fp = self.fitting_parameter
        new_fixed = self.widget_fix.isChecked()
        source = self._parameter_context(fp)
        try:
            fp.fixed = new_fixed
        except Exception:
            pass
        fc = get_fitting_client()
        if fc is not None:
            fc.set_parameter_fixed(
                parameter_name=str(fp.name),
                fixed=new_fixed,
                fit_uid=source.get("fit_uid"),
            )
        self._trace_operation(
            "parameter_fixed",
            f"set fixed={new_fixed} for '{fp.name}' in fit '{source['fit_group']}' / local '{source['local_fit']}'",
            {
                "parameter_name": str(fp.name),
                "fixed": bool(new_fixed),
                **source,
            },
        )
        self.finalize()

    def _on_main_bounds_changed(self):
        if getattr(self, "_is_output_param", False):
            return
        fp = self.fitting_parameter
        source = self._parameter_context(fp)
        fc = get_fitting_client()
        try:
            fp.bounds = (self.widget_lower_bound.value(), self.widget_upper_bound.value())
        except Exception:
            pass
        if fc is not None:
            fc.set_parameter_bounds(
                parameter_name=str(fp.name),
                bounds=(self.widget_lower_bound.value(), self.widget_upper_bound.value()),
                fit_uid=source.get("fit_uid"),
            )
        self._trace_operation(
            "parameter_bounds_set",
            (
                f"set bounds for '{fp.name}' to "
                f"({self.widget_lower_bound.value()}, {self.widget_upper_bound.value()}) "
                f"in fit '{source['fit_group']}' / local '{source['local_fit']}'"
            ),
            {
                "parameter_name": str(fp.name),
                "lower": float(self.widget_lower_bound.value()),
                "upper": float(self.widget_upper_bound.value()),
                **source,
            },
        )
        self.finalize()

    def finalize(self, *args):
        # Ensure execution on the widget's thread (GUI thread). If called from another thread,
        # reschedule finalize to run on the correct thread and return immediately.
        if QtCore.QThread.currentThread() is not self.thread():
            QtCore.QTimer.singleShot(0, lambda: self.finalize())
            return
        #super().update(*args)
        self.blockSignals(True)

        # Sync link UI state first
        try:
            self.set_linked(self.fitting_parameter.is_linked)
        except Exception:
            pass

        # Update value of widget - for linked parameters, show master's value
        try:
            if self.fitting_parameter.is_linked and hasattr(self.fitting_parameter, 'link') and self.fitting_parameter.link is not None:
                # This is a linked parameter - show the master's value
                _v = float(self.fitting_parameter.link.value)
            else:
                # This is a master or unlinked parameter - show its own value
                _v = float(self.fitting_parameter.value)
        except Exception:
            _v = self.widget_value.value()
        self.widget_value.setValue(_v)
        self.widget_fix.setCheckState(QtCore.Qt.Checked if self.fitting_parameter.fixed else QtCore.Qt.Unchecked)

        # Sync bounds UI safely (no unpack unless valid)
        try:
            self.widget_bounds_on.blockSignals(True)
            self.widget_lower_bound.blockSignals(True)
            self.widget_upper_bound.blockSignals(True)
            bounds_on = bool(getattr(self.fitting_parameter, 'bounds_on', False))
            self.widget_bounds_on.setCheckState(QtCore.Qt.Checked if bounds_on else QtCore.Qt.Unchecked)
            # Do not force the bounds-editing row open here: its visibility is
            # driven by the user toggling the checkbox (compact by default).

            # Default to current UI values; replace with model values only if valid
            lb_val = self.widget_lower_bound.value()
            ub_val = self.widget_upper_bound.value()
            b = getattr(self.fitting_parameter, 'bounds', None)
            if isinstance(b, (tuple, list)) and len(b) == 2:
                try:
                    lb_val = float(b[0])
                    ub_val = float(b[1])
                except Exception:
                    pass
            self.widget_lower_bound.setValue(lb_val)
            self.widget_upper_bound.setValue(ub_val)
        except Exception:
            pass
        finally:
            try:
                self.widget_bounds_on.blockSignals(False)
                self.widget_lower_bound.blockSignals(False)
                self.widget_upper_bound.blockSignals(False)
            except Exception:
                pass

        # Tooltip (guard against invalid bounds)
        if getattr(self.fitting_parameter, 'bounds_on', False):
            b = getattr(self.fitting_parameter, 'bounds', None)
            if isinstance(b, (tuple, list)) and len(b) == 2:
                lower, upper = b
                tooltip_text = f"bound: ({lower}, {upper})\n"
            else:
                tooltip_text = "bounds: on (unset)\n"
        else:
            tooltip_text = "bounds: off\n"

        link_param = getattr(self.fitting_parameter, 'link', None)
        if self.fitting_parameter.is_linked and link_param is not None:
            target_param_name = getattr(link_param, 'name', "?")
            source_group, source_local = self._locate_parameter(self.fitting_parameter)
            target_group, target_local = self._locate_parameter(link_param)
            tooltip_text += (
                f"source: fit '{source_group}', local '{source_local}', parameter '{self.fitting_parameter.name}'\n"
                f"linked to: fit '{target_group}', local '{target_local}', parameter '{target_param_name}'"
            )
        else:
            source_group, source_local = self._locate_parameter(self.fitting_parameter)
            tooltip_text += (
                f"source: fit '{source_group}', local '{source_local}', parameter '{self.fitting_parameter.name}'"
            )
        self.widget_value.setToolTip(tooltip_text)

        try:
            try:
                details = self._build_details_tooltip_text()
            except Exception:
                details = ""
            if details:
                self.label.setToolTip(details + "\n\nClick to view and edit details")
            else:
                try:
                    self.label.setToolTip(f"{getattr(self.fitting_parameter, 'name', '')}\n\nClick to view and edit details")
                except Exception:
                    self.label.setToolTip("Click to view and edit details")
        except Exception:
            pass

        # Error-estimate
        error_estimate = float('nan')
        rel_error = float('nan')
        try:
            value = float(self.fitting_parameter.value)
            error_estimate = self.fitting_parameter.error_estimate
            if np.isfinite(value):
                rel_error = abs(error_estimate / (value + 1e-12) * 100.0)
        except Exception:
            pass

        scan_result = getattr(self.fitting_parameter, 'scan_result', None)

        if self.fitting_parameter.fixed or not np.isfinite(error_estimate):
            self.lineEdit.setText("NA")
            self.lineEdit.setStyleSheet("background-color: #d0d0d0; color: #666666;")
        else:
            self.lineEdit.setText("NA" if np.isnan(rel_error) else f"{rel_error:.0f}%")

            # Set background color based on relative error
            if not np.isnan(rel_error):
                # Create a colormap from error_color_small to error_color_large
                # Use default values if settings are not found
                error_color_small = parameter_settings.get('error_color_small', 'green')
                error_color_large = parameter_settings.get('error_color_large', 'magenta')
                error_threshold_small = parameter_settings.get('error_threshold_small', 20)
                error_threshold_large = parameter_settings.get('error_threshold_large', 100)

                cmap = mcolors.LinearSegmentedColormap.from_list(
                    'error_color_gradient',
                    [(0, error_color_small), (1, error_color_large)]
                )

                # Normalize error value: error_threshold_small -> error_color_small, error_threshold_large -> error_color_large
                error_range = error_threshold_large - error_threshold_small
                norm_error = min(1.0, max(0.0, (rel_error - error_threshold_small) / error_range))

                # Get RGB color from colormap
                rgb_color = cmap(norm_error)

                # Convert RGB to hex for stylesheet
                if scan_result is not None:
                    bg_color = mcolors.rgb2hex(tuple(c * 0.65 for c in rgb_color[:3]))
                    self.lineEdit.setStyleSheet(f"background-color: {bg_color}; color: white;")
                else:
                    text_color = mcolors.rgb2hex(rgb_color)
                    self.lineEdit.setStyleSheet(f"background-color: #d0d0d0; color: {text_color};")

        try:
            source_text = "support-plane error" if scan_result is not None else "covariance/error estimate"
            self.lineEdit.setToolTip(
                f"{source_text}\n"
                f"Click to run support-plane analysis for '{self.fitting_parameter.name}'."
            )
        except Exception:
            pass

        # Link
        if link_param is not None:
            target_param_name = getattr(link_param, 'name', "?")
            target_group, target_local = self._locate_parameter(link_param)
            tooltip = (
                f"source parameter '{self.fitting_parameter.name}'\n"
                f"linked to fit '{target_group}', local fit '{target_local}', parameter '{target_param_name}'"
            )
            self.widget_link.setToolTip(tooltip)
            self.widget_value.setEnabled(False)
        else:
            source_group, source_local = self._locate_parameter(self.fitting_parameter)
            self.widget_link.setToolTip(
                f"source fit '{source_group}', local fit '{source_local}', parameter '{self.fitting_parameter.name}'"
            )

        # If the details popup is open, refresh its contents to reflect latest model state
        try:
            if getattr(self, '_details_popup', None) is not None and self._details_popup.isVisible():
                self._details_popup.refresh_from_model()
        except Exception:
            pass

        # If the details popup is open, refresh its contents to reflect latest model state
        try:
            if getattr(self, '_details_popup', None) is not None and self._details_popup.isVisible():
                self._details_popup.refresh_from_model()
        except Exception:
            pass

        try:
            self._update_role_visuals()
        except Exception:
            pass

        self.blockSignals(False)


class FittingParameterGroupWidget(QtWidgets.QGroupBox):

    def __init__(
            self,
            parameter_group: chisurf.core.fitting.parameter.FittingParameterGroup,
            n_col: int = None,
            layout: QtWidgets.QVBoxLayout = None,
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)

        if n_col is None:
            n_col = chisurf.core.settings.gui['fit_models']['n_columns']

        self.parameter_group = parameter_group
        self.n_col = n_col
        self.n_row = 0

        self.setTitle(parameter_group.name)
        if layout is None:
            layout = QtWidgets.QGridLayout()
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)
        for i, p in enumerate(parameter_group.parameters_all):
            label_text = p.__dict__.get('label_text', p.name)
            pw = make_fitting_parameter_widget(
                fitting_parameter=p,
                label_text=label_text
            )
            col = i % self.n_col
            row = i // self.n_col
            layout.addWidget(pw, row, col)


def make_fitting_parameter_widget(
        fitting_parameter: chisurf.core.fitting.parameter.FittingParameter,
        label_text: str = None,
        layout: QtWidgets.QLayout = None,
        decimals: int = None,
        hide_label: bool = None,
        hide_error: bool = None,
        fixable: bool = None,
        hide_bounds: bool = None,
        name: str = None,
        hide_link: bool = None,
        suffix: str = "",
        label_width: int = None,
        callback: typing.Callable = None
) -> FittingParameterWidget:
    if label_text is None:
        # Safely get label_text from parameter's __dict__ or use name as fallback
        label_text = fitting_parameter.__dict__.get('label_text', fitting_parameter.name)
    # If no explicit suffix was provided, infer simple unit suffixes from the
    # parameter name (e.g. *_nm -> " nm", *_um -> " µm"). This keeps
    # backwards compatibility while improving readability for standard unit
    # conventions used throughout ChiSurf.
    auto_suffix = suffix
    if not auto_suffix:
        n = str(fitting_parameter.name)
        if n.endswith("_nm"):
            auto_suffix = " nm"
        elif n.endswith("_um"):
            auto_suffix = " µm"
        elif n.endswith("_ms"):
            auto_suffix = " ms"
        elif n.endswith("_us"):
            auto_suffix = " µs"
        elif n.endswith("_ns"):
            auto_suffix = " ns"
        elif n.endswith("_K"):
            auto_suffix = " K"

    widget = FittingParameterWidget(
        fitting_parameter,
        hide_label=hide_label,
        layout=layout,
        decimals=decimals,
        hide_error=hide_error,
        fixable=fixable,
        hide_bounds=hide_bounds,
        name=name,
        hide_link=hide_link,
        label_text=label_text,
        suffix=auto_suffix,
        label_width=label_width,
        callback=callback
    )
    fitting_parameter.controller = widget
    return widget


def make_fitting_parameter_group_widget(
        fitting_parameter_group: chisurf.core.fitting.parameter.FittingParameterGroup,
        *args,
        **kwargs
):
    return FittingParameterGroupWidget(
        fitting_parameter_group,
        *args,
        **kwargs
    )
