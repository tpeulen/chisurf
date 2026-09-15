from __future__ import annotations

import os
import time
import typing
import pathlib
import textwrap

import numpy as np
from qtpy import QtWidgets, uic, QtCore, QtGui
import matplotlib.colors as mcolors

import chisurf as cs
import chisurf.logging
import chisurf.core.data
import chisurf.core.fitting
import chisurf.core.support.decorators
import chisurf.gui.decorators
import chisurf.core.settings

import chisurf.gui.widgets
import chisurf.gui.widgets.experiments.widgets
from chisurf.gui.widgets.general import Controller
from chisurf.core.math.optimization import OptimizationCancelled
from chisurf.core.actions import record_action
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

#: ProteinMC drives the Sampling button itself and has no generic Fit, so this
#: controller has to recognise it. Matching on ``model.name`` is the primary
#: test; the class names are the fallback for a project pinning an older path.
_PROTEINMC_CLASS_NAMES = ("ProteinMCModel", "ProteinMCModelWidget")


class FittingControllerWidget(Controller):

    @staticmethod
    def _iter_fit_parameters_to_finalize(fit):
        """Yield parameters owned by the current fit or fit group."""
        local_fits = list(getattr(fit, "grouped_fits", []))
        if not local_fits:
            local_fits = [fit]
        for local_fit in local_fits:
            model = getattr(local_fit, "model", None)
            yield from getattr(model, "parameters_all", [])

    def _collect_parameter_snapshot(self) -> typing.List[typing.Dict[str, typing.Any]]:
        snapshot: typing.List[typing.Dict[str, typing.Any]] = []
        try:
            fit_group_name = str(getattr(self.fit, "name", ""))
            local_fits = list(getattr(self.fit, "grouped_fits", []))
            if not local_fits:
                local_fits = [self.fit]
            for local_fit in local_fits:
                local_fit_name = str(getattr(local_fit, "name", ""))
                model = getattr(local_fit, "model", None)
                if model is None:
                    continue
                for param in getattr(model, "parameters_all", []):
                    try:
                        bounds = getattr(param, "bounds", None)
                        if isinstance(bounds, (tuple, list)) and len(bounds) == 2:
                            lb = float(bounds[0])
                            ub = float(bounds[1])
                        else:
                            lb = None
                            ub = None
                    except Exception:
                        lb = None
                        ub = None
                    snapshot.append({
                        "fit_group": fit_group_name,
                        "local_fit": local_fit_name,
                        "parameter_name": str(getattr(param, "name", "")),
                        "value": float(getattr(param, "value", 0.0)),
                        "fixed": bool(getattr(param, "fixed", False)),
                        "bounds_on": bool(getattr(param, "bounds_on", False)),
                        "lower": lb,
                        "upper": ub,
                    })
        except Exception:
            return []
        return snapshot

    def _collect_fit_range_snapshot(self) -> typing.List[typing.Dict[str, typing.Any]]:
        snapshot: typing.List[typing.Dict[str, typing.Any]] = []
        try:
            fit_group_name = str(getattr(self.fit, "name", ""))
            local_fits = list(getattr(self.fit, "grouped_fits", []))
            if not local_fits:
                local_fits = [self.fit]
            for local_fit in local_fits:
                xmin, xmax = getattr(local_fit, "fit_range", (None, None))
                snapshot.append({
                    "fit_group": fit_group_name,
                    "local_fit": str(getattr(local_fit, "name", "")),
                    "xmin": int(xmin),
                    "xmax": int(xmax),
                })
        except Exception:
            return []
        return snapshot

    def _record_history(self, action_type: str, summary: str, payload: typing.Optional[typing.Dict[str, typing.Any]] = None) -> None:
        try:
            source_uid = str(getattr(self.fit, "unique_identifier", ""))
            if str(action_type) in {"fit_run_start", "fit_run_finish", "fit_run_abort"}:
                cs.core.actions.dispatch(
                    name=str(action_type).replace("_", "."),
                    payload=payload or {},
                )
                return
            record_action(
                action_type=action_type,
                summary=summary,
                payload=payload,
                source_uid=source_uid or None,
            )
            return
        except Exception:
            pass
        try:
            cs.logging.info(f"# HIST {action_type}: {summary}")
        except Exception:
            pass

    def _build_controls(self, dataset_labels):
        """Render the controls from the view spec and bind them to this widget.

        The layout, the labels and the tooltips come from
        ``fitting_controls.view.json``; the widgets AutoForm builds are then
        bound to the names the rest of this controller uses, so behaviour that
        was written against the designer file keeps working unchanged.

        Parameters
        ----------
        dataset_labels : list of (str, str)
            ``(display, full)`` dataset name pairs to offer in the combo.
        """
        from chisurf.gui.autoform import AutoForm
        from chisurf.gui.widgets.fitting.fitting_controls import FittingControlsModel

        try:
            chain_format = str(
                cs.core.settings.cs_settings['optimization']['sampling'].get(
                    'chain_format', 'er4'
                )
            )
        except (KeyError, TypeError, AttributeError):
            chain_format = 'er4'

        #: Controls lifted out of the form's grid, by attribute.
        self._moved_fields = {}
        self.controls = FittingControlsModel(
            self, dataset_labels=dataset_labels, chain_format=chain_format
        )
        self.form = AutoForm(self.controls, parent=self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.form)
        # These are controls, not a view: they must take the height they need
        # and no more. Left at the default the box grows into whatever room the
        # dock has spare, which is how a five-row panel ends up half empty above
        # the model editor.
        for widget in (self.form, self):
            widget.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum
            )

        # The names the rest of the controller was written against. Binding the
        # concrete editors keeps one source of truth for the layout (the spec)
        # without rewriting behaviour that is not being changed.
        self.comboBox = self._editor('dataset_index')
        self.spinBox_2 = self._editor('xmin')
        self.spinBox = self._editor('xmax')
        self.spinBox_4 = self._editor('xmin2')
        self.spinBox_6 = self._editor('xmax2')
        self.spinBox_3 = self._editor('result_index')
        self.checkBox = self._editor('local_first')

        self.button_fit = self._button('fit')
        self.button_mcts = self._button('mcts')
        self.button_sample = self._button('sample')
        self.button_auto_fit_range = self._button('auto_range')
        self.button_dataset_select = self._button('select_dataset')
        # One foldable box now, so the group the ProteinMC path used to hide is
        # gone; what it meant -- "this fit is not optimised from here" -- is the
        # Fit button and the two fields that belong to it.
        self.groupBox = self.form.section_widget(title="Fit")
        self.button_settings = self._button('settings')
        self._emphasise(self.button_fit)
        self._emphasise(self.button_sample)
        for button in (
            self.button_fit, self.button_mcts, self.button_sample,
            self.button_settings, self.button_auto_fit_range,
            self.button_dataset_select,
        ):
            if button is not None:
                button.setMinimumHeight(28)
        self._move_toggle_into_action_row('local_first')

        # The actions the designer file carried. Nothing outside this widget
        # triggers them, but the connections below are the widget's own vocabulary.
        for name in (
                "actionFit", "actionAutoFitRange", "actionFit_range_changed",
                "actionChange_dataset", "actionSelectionChanged", "actionErrorEstimate",
                "actionMCTS",
        ):
            setattr(self, name, QtWidgets.QAction(name, self))

        # The connections the designer file declared. The range boxes commit on
        # ``editingFinished`` rather than on every keystroke: a partly typed
        # number is not a fit range, and applying one re-runs the fit.
        if self.comboBox is not None:
            self.comboBox.currentIndexChanged.connect(
                lambda *_a: self.actionSelectionChanged.trigger()
            )
        for box in (self.spinBox, self.spinBox_2, self.spinBox_4, self.spinBox_6):
            if box is not None:
                box.editingFinished.connect(
                    lambda *_a: self.actionFit_range_changed.trigger()
                )

    def _field(self, attr: str):
        """Return the field container AutoForm built for one bound attribute.

        Parameters
        ----------
        attr : str
            The ``attr`` of a ``value``/``choice``/``toggle`` section.

        Returns
        -------
        QtWidgets.QWidget or None
            The container, whose ``_autoform_label`` is the label beside it.
        """
        moved = getattr(self, "_moved_fields", {}).get(attr)
        if moved is not None:
            return moved
        for widget in self.form.findChildren(QtWidgets.QWidget):
            section = getattr(widget, "_section", None)
            if section is not None and getattr(section, "attr", None) == attr:
                return widget
        cs.logging.warning("fitting controls: no field %r in the view spec", attr)
        return None

    @staticmethod
    def _emphasise(button) -> None:
        """Make an action button read as the action it is.

        The designer file gave Fit and Sample a bold font and let them span
        their group; rendered from a spec they come out the size of a
        text field's spin arrows, which is not what the panel is for.

        Parameters
        ----------
        button : QtWidgets.QAbstractButton or None
            The button to emphasise.
        """
        if button is None:
            return
        font = button.font()
        font.setBold(True)
        button.setFont(font)
        button.setMinimumHeight(28)
        button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)

    def _set_fitting_controls_visible(self, visible: bool) -> None:
        """Show or hide the controls that only make sense for a fitted model.

        A ProteinMC fit runs its own algorithm, so the optimiser button and the
        result selector do not apply to it -- but its *sampling* does, which is
        why this hides controls rather than the whole box.

        Parameters
        ----------
        visible : bool
            Whether the fitting controls should be shown.
        """
        if self.button_fit is not None:
            self.button_fit.setVisible(bool(visible))
        for attr in ('result_index', 'local_first'):
            self._set_field_visible(attr, visible)

    def _move_toggle_into_action_row(self, attr: str) -> None:
        """Put a toggle on the row of buttons instead of on a row of its own.

        A single checkbox occupies a whole two-column row, which is a lot of
        panel for one word. Beside the buttons it costs nothing and sits next
        to the action it qualifies.

        Parameters
        ----------
        attr : str
            The ``attr`` of the toggle to move.
        """
        field = self._field(attr)
        if field is None or self.button_fit is None:
            return
        # Remember where it went: the container is about to be destroyed, and
        # a later lookup by attribute must still find the control.
        self._moved_fields[attr] = self._editor(attr) or field
        row = self.button_fit.parent()
        layout = row.layout() if row is not None else None
        if layout is None:
            return
        label = getattr(field, "_autoform_label", None)
        if label is not None:
            label.setParent(None)
            label.deleteLater()
        editor = self._editor(attr)
        if editor is not None and editor is not field:
            # The checkbox alone, with the label it never had, so the row stays
            # one line high.
            editor.setText(getattr(field, "form_label", "") or editor.text())
            field.setParent(None)
            field.deleteLater()
            layout.addWidget(editor)
        else:
            layout.addWidget(field)

    def show_optimization_settings(self) -> None:
        """Open the sampling and fitting settings as a modal dialog.

        The settings a run is configured by -- which sampler, how it thins,
        where the chains go, the optimiser tolerances -- are shared by every
        fit, so they are edited once, in one place, and written to the user
        settings rather than held for the session.
        """
        from chisurf.gui.widgets.fitting.fitting_controls import (
            show_optimization_settings,
        )

        if not show_optimization_settings(self):
            return
        # The panel shows two of them; take the new values.
        try:
            sampling = cs.core.settings.cs_settings['optimization']['sampling']
            self.controls.chain_format = str(sampling.get('chain_format', 'er4'))
        except (KeyError, TypeError, AttributeError):
            pass

    def _editor(self, attr: str):
        """Return the Qt editor AutoForm built for one bound attribute.

        Parameters
        ----------
        attr : str
            The ``attr`` of a ``value``/``choice``/``toggle`` section.

        Returns
        -------
        QtWidgets.QWidget or None
            The spin box, combo or check box itself -- not its container -- or
            ``None`` when the spec has no such field.
        """
        widget = self._field(attr)
        if widget is None:
            return None
        for name in ("editor", "combo", "checkbox", "toggle"):
            inner = getattr(widget, name, None)
            # ``toggle`` is also QAbstractButton's *method*; only a widget is
            # the editor we are after.
            if isinstance(inner, QtWidgets.QWidget):
                return inner
        return widget

    def _set_field_visible(self, attr: str, visible: bool) -> None:
        """Show or hide a field *and its label*.

        Hiding only the editor leaves its label behind pointing at nothing,
        which is what a second fit-range row looks like on one-dimensional data.

        Parameters
        ----------
        attr : str
            The ``attr`` of the field.
        visible : bool
            Whether the field should be shown.
        """
        widget = self._field(attr)
        if widget is None:
            return
        widget.setVisible(bool(visible))
        label = getattr(widget, "_autoform_label", None)
        if label is not None:
            label.setVisible(bool(visible))

    def _button(self, action: str):
        """Return the button AutoForm built for one action.

        Parameters
        ----------
        action : str
            The ``action`` named in a ``button_row`` entry.

        Returns
        -------
        QtWidgets.QAbstractButton or None
            The button, or ``None`` when the spec declares no such action.
        """
        for widget in self.form.findChildren(QtWidgets.QAbstractButton):
            if getattr(widget, "_autoform_action", None) == action:
                return widget
        # Fall back to the label, which is what the spec pairs with the action.
        labels = {
            'fit': 'Fit', 'sample': 'Sample', 'auto_range': 'auto',
            'select_dataset': '…',
        }
        wanted = labels.get(action)
        for widget in self.form.findChildren(QtWidgets.QAbstractButton):
            if wanted is not None and widget.text() == wanted:
                return widget
        cs.logging.warning("fitting controls: no button for action %r", action)
        return None

    @property
    def chain_format(self) -> str:
        """Return the chain storage format chosen in the sampling panel.

        Falls back to the configured default when the controls are not built --
        a controller can be constructed without its widgets in tests.
        """
        try:
            return str(self.controls.chain_format)
        except (AttributeError, RuntimeError):
            pass
        try:
            return str(cs.core.settings.cs_settings['optimization']['sampling'].get(
                'chain_format', 'er4'
            ))
        except (KeyError, TypeError, AttributeError):
            return 'er4' 

    @property
    def selected_fit(self) -> int:
        return int(self.comboBox.currentIndex())

    @selected_fit.setter
    def selected_fit(
            self,
            v: int
    ):
        self.comboBox.setCurrentIndex(int(v))

    @property
    def current_fit_type(self) -> str:
        return str(self.comboBox.currentText())

    @property
    def local_first(self) -> bool:
        return self.checkBox.isChecked()

    def _sampling_setting(self, key: str, default):
        """Return one configured sampling setting.

        Steps and runs configure a *run*, not a fit, so they live with the rest
        of the sampling settings rather than in the fit's controls -- one place
        to set them, and the same value whether the run is started from the
        panel, a macro or the server.

        Parameters
        ----------
        key : str
            Setting name under ``optimization.sampling``.
        default : object
            Value to use when the setting is missing.

        Returns
        -------
        object
            The configured value, or ``default``.
        """
        try:
            return cs.core.settings.cs_settings['optimization']['sampling'].get(key, default)
        except (KeyError, TypeError, AttributeError):
            return default

    @property
    def n_steps(self) -> int:
        return int(self._sampling_setting('steps', 1000))

    @property
    def n_runs(self) -> int:
        return int(self._sampling_setting('n_runs', 10))

    def _format_dataset_label(self, name: str, max_length: int = 40) -> str:
        try:
            s = str(name)
        except Exception:
            return name
        if not s:
            return s
        try:
            max_len = int(max_length)
        except Exception:
            max_len = 40
        if max_len < 7 or len(s) <= max_len:
            return s
        keep_total = max_len - 4  # reserve 4 characters for '....'
        start_keep = keep_total // 2
        end_keep = keep_total - start_keep
        return f"{s[:start_keep]}....{s[-end_keep:]}"

    def _update_combo_tooltip(self, index: int) -> None:
        try:
            full_name = self.comboBox.itemData(index, QtCore.Qt.ToolTipRole)
        except Exception:
            full_name = None
        if not full_name:
            try:
                full_name = self.comboBox.itemText(index)
            except Exception:
                full_name = ""
        try:
            self.comboBox.setToolTip(str(full_name))
        except Exception:
            pass

    def change_dataset(self) -> None:
        dataset = self.curve_select.selected_dataset
        fc = get_fitting_client()
        if fc is not None:
            fit_index = int(getattr(self.fit, "fit_idx", 0))
            dataset_uid = str(getattr(dataset, "unique_identifier", "") or "")
            fc.set_fit_dataset(
                fit_index=fit_index,
                dataset_uid=dataset_uid,
            )
        full_name = os.path.basename(
            getattr(dataset, 'name', getattr(dataset, 'filename', ''))
        )
        display_name = self._format_dataset_label(full_name)
        idx = self.comboBox.currentIndex()
        self.comboBox.setItemText(idx, display_name)
        try:
            self.comboBox.setItemData(idx, full_name, QtCore.Qt.ToolTipRole)
        except Exception:
            pass
        self._update_combo_tooltip(idx)

    def show_selector(self):
        self.curve_select.show()
        self.curve_select.update()

    def __init__(
            self,
            fit: cs.core.fitting.fit.FitGroup = None,
            hide_fit_button: bool = False,
            hide_range: bool = False,
            hide_fitting: bool = False,
            *args,
            **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.fit = fit
        self.curve_select = cs.gui.widgets.experiments.widgets.ExperimentalDataSelector(
            parent=None,
            fit=fit,
            change_event=self.change_dataset,
            experiment=fit.data.experiment.__class__
        )

        labels = []
        if fit is not None:
            for f in fit:
                data = getattr(f, 'data', None)
                try:
                    base_name = os.path.basename(
                        getattr(data, 'name', getattr(data, 'filename', ''))
                    )
                except Exception:
                    base_name = getattr(data, 'name', 'Unknown')
                labels.append((self._format_dataset_label(base_name), base_name))
        self._build_controls(labels)

        # The view-model starts numeric fields at zero. Load the fit's actual
        # range before a plot can be constructed; an empty [0, 0] range makes
        # the first plot blank and leaves subsequent redraws with no data.
        if fit is not None:
            try:
                xmin, xmax = fit.fit_range
                for editor, value in ((self.spinBox_2, xmin), (self.spinBox, xmax)):
                    blocked = editor.blockSignals(True)
                    editor.setValue(int(value))
                    editor.blockSignals(blocked)
            except Exception:
                cs.logging.exception("could not initialise the fit-range controls")

        self.curve_select.hide()
        for idx, (_display, base_name) in enumerate(labels):
            try:
                self.comboBox.setItemData(idx, base_name, QtCore.Qt.ToolTipRole)
            except Exception:
                pass
        try:
            self.comboBox.currentIndexChanged.connect(self._update_combo_tooltip)
            self._update_combo_tooltip(self.comboBox.currentIndex())
        except Exception:
            pass

        # decorate the update method of the fit
        # after decoration it should also call the update of
        # the fitting widget
        def wrapper(f):

            def update_new(*args, **kwargs):
                f(*args, **kwargs)
                if kwargs.get("notify", True):
                    self.update()
            return update_new

        self.fit.run = wrapper(self.fit.run)

        self.actionFit.triggered.connect(self.onRunFit)
        self.actionAutoFitRange.triggered.connect(self.onAutoFitRange)
        self.actionFit_range_changed.triggered.connect(self.onFitRangeChanged)
        self.actionChange_dataset.triggered.connect(self.show_selector)
        self.actionSelectionChanged.triggered.connect(self.onDatasetChanged)
        self.actionErrorEstimate.triggered.connect(self.onErrorEstimate)
        self.actionMCTS.triggered.connect(self.onRunMCTS)
        self._refresh_mcts_availability()

        self.spinBox_3.valueChanged.connect(self._result_changed)

        # Detect whether the current dataset is intrinsically multidimensional
        # based on generic grid metadata (data.meta_data['grid']). For such
        # datasets we enable all four range spin boxes and interpret them as
        # 2D bounds; for purely 1D datasets we keep the original two spin
        # boxes and hide/disable the extra pair. This keeps the controller
        # agnostic of specific experiments/models.
        self._is_2d_dataset = False
        self._2d_shape = None
        self._grid_meta = {}
        self._grid_order = None
        self._init_dimensionality()

        if hide_fit_button:
            self.button_fit.hide()
        if hide_range:
            self.button_auto_fit_range.hide()
            self._set_field_visible('xmax', False)
            self._set_field_visible('xmin', False)
        if hide_fitting:
            self.hide()

        self._apply_proteinmc_controls()

        try:
            self.comboBox.currentIndexChanged.connect(lambda *_args: self._apply_proteinmc_controls())
        except Exception:
            pass

        try:
            self._install_code_badge()
        except Exception:
            pass

    def _apply_proteinmc_controls(self) -> None:
        """Disable generic fitting controls when this controller hosts ProteinMC."""

        if self._is_proteinmc_fit():
            self.actionFit.setEnabled(False)
            self._set_fitting_controls_visible(False)
        else:
            self._set_fitting_controls_visible(True)
            self.actionFit.setEnabled(True)
            self.button_fit.setEnabled(True)

        if self._model_sampling_handler() is not None or self._is_proteinmc_fit():
            self.button_sample.setToolTip(
                "Start model-defined sampling. For ProteinMC, run length is controlled "
                "by the MC trials, Save every, and Max frames fields below."
            )
        if self._is_proteinmc_fit():
            # ProteinMC reads the same steps/runs as everything else; they are
            # set with the other sampling settings, so there is nothing here to
            # enable or explain any more.
            pass
        else:
            # Steps and runs used to live here as spin boxes; they are sampling
            # settings now, so there is nothing left to re-enable.
            pass
    def _candidate_sampling_models(self) -> list:
        """Return models that may handle the Sampling button themselves."""

        models = []

        direct_model = getattr(self.fit, "model", None)
        if direct_model is not None:
            models.append(direct_model)
        selected_fit = getattr(self.fit, "selected_fit", None)
        selected_model = getattr(selected_fit, "model", None)
        if selected_model is not None and selected_model not in models:
            models.append(selected_model)

        fits = []
        grouped_fits = getattr(self.fit, "grouped_fits", None)
        if grouped_fits:
            try:
                fits.extend(list(grouped_fits))
            except Exception:
                pass
        if not fits:
            try:
                fits = list(self.fit)
            except Exception:
                fits = [self.fit]
        try:
            index = int(self.selected_fit)
        except Exception:
            index = 0
        if index < 0 or index >= len(fits):
            index = 0
        fit = fits[index] if fits else self.fit
        model = getattr(fit, "model", None)
        if model is not None and model not in models:
            models.append(model)
        for fit in fits:
            model = getattr(fit, "model", None)
            if model is not None and model not in models:
                models.append(model)
        return models

    def _model_sampling_handler(self):
        """Return a model-defined Sampling-button handler if one exists."""

        for model in self._candidate_sampling_models():
            for method_name in ("run_sampling", "sample", "on_sample", "start_sampling"):
                method = getattr(model, method_name, None)
                if callable(method):
                    return method
        return None

    def _is_proteinmc_fit(self) -> bool:
        """Return True if any candidate model is ProteinMC."""

        for model in self._candidate_sampling_models():
            model_name = str(getattr(model, "name", "") or getattr(model.__class__, "name", ""))
            class_name = str(getattr(model.__class__, "__name__", ""))
            if model_name == "ProteinMC" or class_name in _PROTEINMC_CLASS_NAMES:
                return True
        return False

    def _proteinmc_model_widget(self):
        """Return the active ProteinMC model widget, if this fit uses one."""

        for model in self._candidate_sampling_models():
            model_name = str(getattr(model, "name", "") or getattr(model.__class__, "name", ""))
            class_name = str(getattr(model.__class__, "__name__", ""))
            if model_name == "ProteinMC" or class_name in _PROTEINMC_CLASS_NAMES:
                return model
        return None

    def _install_code_badge(self):
        """Install a code badge for dev mode source jumping."""
        try:
            import chisurf.core.settings
            if not cs.core.settings.is_dev_mode():
                return
            if hasattr(self, '_chisurf_code_badge_installed'):
                return
            from chisurf.gui.widgets.code_badge import install_code_badge
            from chisurf.gui.devtools.source_jump import resolve_fit_window_source
            resolver = lambda: resolve_fit_window_source(self)
            install_code_badge(self, resolver, corner='top-right', margin=4)
            self._chisurf_code_badge_installed = True
        except Exception:
            pass

    def _result_changed(self):
        result_idx = self.spinBox_3.value() - 1
        fc = get_fitting_client()
        if fc is not None:
            fc.set_fit_result_idx(
                fit_index=getattr(self.fit, "fit_idx", 0),
                result_idx=result_idx,
            )

    def onDatasetChanged(self):
        index = self.selected_fit

        # Switch the locally selected group member so the model, data and
        # plots follow the combobox. We update the local object directly
        # instead of relying on the server round-trip, which may time out and
        # would otherwise leave the GUI showing the previous dataset.
        try:
            self.fit.selected_fit = index
            self.fit.update()
            try:
                self.fit.model.finalize()
            except Exception:
                pass
        except Exception:
            cs.logging.exception("onDatasetChanged: failed to select member %s", index)

        # Refresh plots, the model editor and the parameter widgets in the
        # active fit window so the change is visible.
        try:
            gui = getattr(cs, "cs", None)
            if gui is not None and hasattr(gui, "_refresh_selected_member_display"):
                gui._refresh_selected_member_display(self.fit)
        except Exception:
            pass

        # Keep the server session state in sync (best-effort).
        fc = get_fitting_client()
        if fc is not None:
            try:
                fc.group_select_member(
                    fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                    member_index=index,
                )
            except Exception:
                pass

    def onErrorEstimate(self):
        sampling_handler = self._model_sampling_handler()
        if sampling_handler is not None:
            target_dir, _ = cs.gui.widgets.get_directory(caption="Select Sampling Output Folder")
            if target_dir is None:
                cs.logging.info("Model-defined sampling canceled!")
                return
            # Model-specific sampling (e.g. ProteinMC) must run its own
            # algorithm instead of the generic ensemble server path, which
            # assumes a curve-based model.
            try:
                sampling_handler(
                    output_directory=target_dir,
                    run_count=self.n_runs,
                    n_iter=self.n_steps,
                )
                cs.logging.info("Model-defined sampling started.")
            except Exception:
                cs.logging.exception("Model-defined sampling failed")
            return
        if self._is_proteinmc_fit():
            cs.logging.warning("ProteinMC must handle Sampling itself; refusing to run generic ensemble sampling.")
            return

        fit_name = str(getattr(self.fit, "name", ""))
        cs.logging.info(f"Sampling analysis: {fit_name}")
        target_dir, _ = cs.gui.widgets.get_directory(caption="Select Target Folder for Sampling Results")
        if target_dir is None:
            cs.logging.info("Sampling canceled!")
            return
        
        target_dir_str = str(target_dir)
        
        kw = cs.core.settings.cs_settings['optimization']['sampling'].copy()
        kw['n_runs'] = self.n_runs
        kw['steps'] = self.n_steps
        # The panel's choice wins over the setting: it is the one the user just
        # made, and it decides whether the run leaves behind text or a table a
        # quarter of the size.
        kw['chain_format'] = self.chain_format
        
        fc = get_fitting_client()
        if fc is not None:
            # Forward the configured backend (``method``: blocked / collapsed /
            # ensemble / slice / mcmc) and the rest of ``optimization.sampling``. These used
            # to be assembled here and then dropped, so the choice of sampler
            # never left the GUI.
            extra = {
                k: v for k, v in kw.items()
                if k not in ('steps', 'n_runs')
            }
            result = fc.start_sampling(
                fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                n_steps=self.n_steps,
                n_runs=self.n_runs,
                target_directory=target_dir_str,
                **extra,
            )
            method = extra.get('method', 'ensemble')
            cs.logging.info(f"Sampling started on server (method={method}).")
            job_id = (result or {}).get("job_id")
            if job_id:
                self._watch_sampling_job(fc, str(job_id))

    def _watch_sampling_job(self, fitting_client, job_id: str, interval_ms: int = 1500):
        """Poll a server sampling job and report its convergence verdict.

        A finished run is not the same as a trustworthy one: a chain that never
        left its starting point completes just as happily as one that explored
        the posterior. The job carries the R-hat / effective-sample-size verdict,
        so the outcome is logged rather than left in ``diagnostics.json`` for
        someone to find later.

        Parameters
        ----------
        fitting_client : object
            Client exposing ``sampling_status(job_id)``.
        job_id : str
            Job to poll.
        interval_ms : int, optional
            Polling interval in milliseconds.
        """
        def _poll():
            try:
                status = fitting_client.sampling_status(job_id) or {}
            except Exception:
                cs.logging.warning("Sampling: lost contact with the job; stopping polling.")
                return
            state = str(status.get("status", ""))
            if state in ("queued", "running", "cancelling"):
                QtCore.QTimer.singleShot(interval_ms, _poll)
                return
            if state == "failed":
                cs.logging.error(f"Sampling failed: {status.get('error')}")
                return
            warnings = status.get("warnings") or []
            if warnings:
                cs.logging.warning("Sampling finished, but the chain is not usable:")
                for message in warnings:
                    cs.logging.warning(f"  {message}")
            else:
                report = status.get("diagnostics") or {}
                cs.logging.info(
                    "Sampling finished; no convergence problems detected "
                    f"({report.get('n_chains', '?')} chains x "
                    f"{report.get('n_draws', '?')} draws)."
                )

        QtCore.QTimer.singleShot(interval_ms, _poll)

    def _run_fit_impl(self):
        if self._proteinmc_model_widget() is not None:
            self._apply_proteinmc_controls()
            cs.logging.info("ProteinMC does not use generic Fit. Use Sampling to start ProteinMC.")
            return
        try:
            fit_name = str(getattr(self.fit, "name", ""))
        except Exception:
            fit_name = ""
        cs.logging.info(f"Please wait fitting: {fit_name}")

        # One line. This label goes to whichever host is rendering progress, and
        # for a fit started from the main window that is the status bar -- one
        # line high. A name wrapped to three lines grew it past the bottom of the
        # window and the whole read-out was clipped, which is indistinguishable
        # from having no progress bar. The full name is on the handle's tooltip.
        short_name = fit_name if len(fit_name) <= 44 else fit_name[:41] + "…"
        base_label = "Fitting"
        t0 = time.perf_counter()
        before_snapshot = self._collect_parameter_snapshot()
        before_fit_range = self._collect_fit_range_snapshot()
        self._record_history(
            action_type="fit_run_start",
            summary=f"start fit run: {fit_name}",
            payload={
                "fit_name": fit_name,
                "local_first": bool(self.local_first),
                "n_steps": int(self.n_steps),
                "n_runs": int(self.n_runs),
                "parameter_snapshot_before": before_snapshot,
                "fit_range_snapshot_before": before_fit_range,
            },
        )

        dialog = None
        success = False
        try:
            # One progress handle; where it renders (inline bar, status bar,
            # modal dialog, the log) is resolved from this widget.
            try:
                from chisurf.gui.progress import ChiSurfProgress

                dialog = ChiSurfProgress(self, base_label, 100, title="Fitting")
                dialog.update_progress(0)
            except Exception:
                dialog = None

            def _on_progress(
                done: int, total: int, chi2=None, chi2r=None,
                stage=None, n_stages=None, **_kwargs
            ) -> None:
                """Update the progress dialog from least-squares callbacks.

                The callback receives the number of completed residual
                evaluations (done) and an estimated total evaluation
                budget (total). It maps this to a 0–100 percentage.

                When the user presses the Cancel button on the progress
                dialog, this callback raises :class:`OptimizationCancelled`
                so that the optimizer aborts cleanly while keeping the
                current parameter values.
                """

                if dialog is None:
                    return

                # Honour user cancellation as soon as possible. The
                # least-squares wrapper treats this exception specially
                # and propagates it back to :meth:`onRunFit`.
                try:
                    if dialog.wasCanceled():
                        raise OptimizationCancelled()
                except OptimizationCancelled:
                    raise
                except Exception:
                    # Ignore unexpected UI errors when checking cancel state.
                    pass

                try:
                    total_val = float(total) if total else 0.0
                except Exception:
                    total_val = 0.0
                if total_val <= 0.0:
                    value = 0
                else:
                    try:
                        frac = float(done) / total_val
                    except Exception:
                        frac = 0.0
                    if frac < 0.0:
                        frac = 0.0
                    if frac > 1.0:
                        frac = 1.0
                    value = int(round(100.0 * frac))
                # Build an informative status line including objective values
                # when available. A group reports a *fraction* rather than an
                # evaluation count -- its stages have no common unit -- so
                # spelling it "eval 267/1000" would be a made-up number.
                if n_stages:
                    # A group reports a fraction, not evaluations.
                    parts = [f"{value}%"]
                    if int(n_stages) > 1:
                        parts.insert(0, f"fit {int(stage)}/{int(n_stages)}")
                else:
                    parts = [f"eval {done}/{int(total) if total else '?'}"]
                if done > 0 and total:
                    elapsed = time.perf_counter() - t0
                    remaining = (elapsed / float(done)) * (float(total) - done)
                    if remaining > 3600:
                        parts.append(f"ETA: {int(remaining // 3600)}h {int((remaining % 3600) // 60)}m")
                    elif remaining > 60:
                        parts.append(f"ETA: {int(remaining // 60)}m {int(remaining % 60)}s")
                    else:
                        parts.append(f"ETA: {int(remaining)}s")

                if chi2 is not None:
                    try:
                        parts.append(f"chi2={float(chi2):.3g}")
                    except Exception:
                        pass
                if chi2r is not None:
                    try:
                        parts.append(f"chi2r={float(chi2r):.3g}")
                    except Exception:
                        pass

                # One line, with the *name* last. Elision eats the tail, and what
                # is worth reading while a fit runs is how far along it is and
                # what chi2 is doing -- not which fit, which the user just
                # started. The full name stays on the tooltip.
                if short_name:
                    parts.append(short_name)
                label_text = base_label + " — " + " · ".join(parts)

                try:
                    dialog.update_progress(value, text=label_text)
                except Exception:
                    # Never let UI errors break the optimizer.
                    pass

            # Run the fit synchronously, allowing the optimizer to invoke
            # the progress callback from within the residual evaluations.
            #
            # The callback is installed *on the fit* rather than passed to
            # ``run_fit``: the call goes through the JSON-RPC facade, which
            # carries JSON and cannot carry a Qt closure, so the service calls
            # ``fit.run()`` with no arguments. Attaching it to the fit is what
            # makes the bar move at all.
            try:
                fc = get_fitting_client()
                with self.fit.reporting_progress(_on_progress):
                    if fc is not None:
                        fc.run_fit(
                            fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                        )
                    else:
                        # No transport: the fit itself is right here. The RPC
                        # facade is a routing choice, not a capability -- with
                        # it absent the button must still fit, not silently
                        # do nothing.
                        self.fit.run()
                if getattr(self.fit, "last_run_cancelled", False):
                    # The optimiser raised, ``Fit.run`` re-raised, and the
                    # service turned it into an error result -- so a
                    # cancelled fit arrives here looking like a clean one.
                    raise OptimizationCancelled()
            except OptimizationCancelled:
                cs.logging.info("Fitting cancelled by user.")
                success = False
            else:
                if fc is not None:
                    fc.model_finalize(
                        fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                    )
                else:
                    try:
                        self.fit.model.finalize()
                    except Exception:
                        pass
                    # `Fit.update()` publishes ``fit.updated``; that is what
                    # redraws the trace on the local path, exactly as the
                    # server's own publish does on the RPC path.
                    self.fit.update()
                for pa in self._iter_fit_parameters_to_finalize(self.fit):
                    controller = getattr(pa, "controller", None)
                    if controller is None:
                        continue
                    try:
                        controller.finalize()
                    except (AttributeError, RuntimeError, TypeError):
                        cs.logging.warning(
                            f"Fitting parameter {pa.name} failed to update its controller."
                        )
                cs.logging.info("Fitting finished!")
                success = True

                # Update fit result selector
                self.spinBox_3.setMaximum(len(self.fit.results))
                self.spinBox_3.setMinimum(1)
                self.spinBox_3.setValue(1)
        finally:
            if dialog is not None:
                try:
                    final_text = "Fitting finished!" if success else "Fitting aborted."
                    # Close immediately by default; user can override via settings.
                    try:
                        delay_ms = int(cs.core.settings.gui.get('fit_progress_close_delay_ms', 0))
                    except Exception:
                        delay_ms = 0
                    dialog.finish(final_text=final_text, auto_close=True, close_delay_ms=delay_ms)
                except Exception:
                    try:
                        dialog.finalize(force_auto_close=True)
                    except Exception:
                        pass

        elapsed_ms = int(round((time.perf_counter() - t0) * 1000.0))
        after_snapshot = self._collect_parameter_snapshot()
        after_fit_range = self._collect_fit_range_snapshot()
        self._record_history(
            action_type="fit_run_finish" if success else "fit_run_abort",
            summary=(
                f"fit {'finished' if success else 'aborted'}: {self.fit.name} "
                f"({elapsed_ms} ms)"
            ),
            payload={
                "fit_name": str(getattr(self.fit, "name", "")),
                "success": bool(success),
                "elapsed_ms": int(elapsed_ms),
                "result_count": int(len(getattr(self.fit, "results", []))),
                "parameter_snapshot_after": after_snapshot,
                "fit_range_snapshot_after": after_fit_range,
            },
        )

    def onRunFit(self):
        proteinmc_model = self._proteinmc_model_widget()
        if proteinmc_model is not None:
            self._apply_proteinmc_controls()
            cs.logging.info("ProteinMC does not use generic Fit. Use Sampling to start ProteinMC.")
            return
        # Unconditionally: `_run_fit_impl` routes through the RPC facade when
        # one is up and runs the fit in-process otherwise. Gating the button
        # on the client made a missing/late server disable fitting silently.
        self._run_fit_impl()

    def onRunMCTS(self):
        """Run the fit's declared model search through the native BFF engine."""
        from chisurf.core.fitting.mcts.dispatcher import prepare_model_search
        from chisurf.core.fitting.mcts.execution import (
            NativeSearchSettings,
            run_native_search,
        )
        from chisurf.gui.task import run_in_background

        fit = self.fit
        before_snapshot = self._collect_parameter_snapshot()
        try:
            prepared = prepare_model_search(fit)
        except Exception:
            cs.logging.exception("BFF model-search preparation failed")
            return
        if not prepared.supported:
            details = "; ".join(
                f"{reason.code}: {reason.message}"
                for reason in prepared.reasons
            ) or "the fit has no native model-search declaration"
            cs.logging.warning(
                f"BFF model search is unavailable for "
                f"{getattr(fit, 'name', 'this fit')!r}: {details}"
            )
            return

        optimization = cs.core.settings.cs_settings.get("optimization", {})
        values = dict(optimization.get("mcts", {}) or {})
        search_settings = NativeSearchSettings(
            simulations=int(values.get("n_simulations", 400)),
            c_puct=float(values.get("c_puct", 1.4)),
            reward_scale=float(values.get("reward_scale", 1.0)),
            dirichlet_alpha=float(values.get("dirichlet_alpha", 0.3)),
            # User-facing fitting is deterministic. Dirichlet noise belongs to
            # policy self-play and is never injected into an accepted fit.
            dirichlet_fraction=0.0,
            seed=int(values.get("seed", 7)),
        )

        def _search(task):
            return run_native_search(
                prepared.problem,
                search_settings,
                should_cancel=lambda: task.is_cancelled,
            )

        def _apply(result):
            restore = getattr(prepared.binding, "restore", None)
            if result.get_cancelled():
                # A search over a live model moved its ports while it ran.
                if callable(restore):
                    restore(prepared.problem)
                cs.logging.info("BFF model search cancelled; the fit was not changed.")
                return
            try:
                best_state = result.get_best_state()
                prepared.binding.apply_state(prepared.problem, best_state)
            except Exception:
                if callable(restore):
                    restore(prepared.problem)
                cs.logging.exception("BFF model-search result could not be applied")
                return
            after_snapshot = self._collect_parameter_snapshot()
            structure = str(best_state.get_structure_key())
            accepted = bool(result.get_acceptable())
            cs.logging.info(
                f"BFF model search selected {structure!r}; "
                f"reward={float(best_state.get_reward()):.6g}, "
                f"improvement={float(result.get_improvement()):.6g}, "
                f"acceptable={accepted}."
            )
            self._refresh_mcts_structure_ui(fit)
            self._record_history(
                action_type="fit_run_finish",
                summary=f"accepted BFF model search for {getattr(fit, 'name', '')}",
                payload={
                    "fit_name": str(getattr(fit, "name", "")),
                    "operation": "bff_model_search",
                    "capability_id": str(prepared.capability_id),
                    "structure": structure,
                    "acceptable": accepted,
                    "reward": float(best_state.get_reward()),
                    "improvement": float(result.get_improvement()),
                    "simulations": int(result.get_number_of_simulations()),
                    "states_evaluated": int(result.get_number_of_states_evaluated()),
                    "parameter_snapshot_before": before_snapshot,
                    "parameter_snapshot_after": after_snapshot,
                },
            )

        def _error(error):
            cs.logging.error(
                f"BFF model search failed for "
                f"{getattr(fit, 'name', 'fit')!r}: {error}"
            )

        run_in_background(
            self,
            "Searching model space…",
            _search,
            maximum=0,
            on_result=_apply,
            on_error=_error,
        )

    def _refresh_mcts_availability(self) -> None:
        """Offer model search only for a fit BFF can search; there is no other engine."""
        if self.button_mcts is None:
            return
        available = False
        if self.fit is not None:
            try:
                from chisurf.core.fitting.mcts.dispatcher import model_search_available

                available = model_search_available(self.fit)
            except Exception:
                cs.logging.exception("could not decide whether BFF can search this fit")
        self.button_mcts.setVisible(bool(available))
        self.actionMCTS.setEnabled(bool(available))

    def _refresh_mcts_structure_ui(self, fit) -> None:
        """Rebuild parameter rows and redraw once after native search."""
        try:
            from chisurf.gui.widgets.models.model_editor import model_editor_widget

            members = list(getattr(fit, "grouped_fits", []) or []) or [fit]
            for member in members:
                editor = model_editor_widget(member.model)
                rebuild = getattr(editor, "rebuild", None)
                if callable(rebuild):
                    rebuild()
            gui = getattr(cs, "cs", None)
            if gui is not None:
                show_selected = getattr(gui, "_show_only_selected_member_editor", None)
                if callable(show_selected):
                    show_selected(fit)
                for sub in gui.mdiarea.subWindowList():
                    if getattr(sub, "fit", None) is fit:
                        refresh = getattr(sub, "refresh_current_plot", None)
                        if callable(refresh):
                            refresh()
                        break
        except Exception:
            cs.logging.exception("could not refresh the UI after MCTS structure change")

    @property
    def xmin(self):
        return int(self.spinBox_2.value())

    @xmin.setter
    def xmin(self, v: int):
        self.spinBox_2.setValue(v)

    @property
    def xmax(self):
        return int(self.spinBox.value())

    @xmax.setter
    def xmax(self, v: int):
        self.spinBox.setValue(v)

    @property
    def xmin2(self) -> int:
        return int(self.spinBox_4.value())

    @xmin2.setter
    def xmin2(self, v: int):
        self.spinBox_4.setValue(v)

    @property
    def xmax2(self) -> int:
        return int(self.spinBox_6.value())

    @xmax2.setter
    def xmax2(self, v: int):
        self.spinBox_6.setValue(v)

    def onFitRangeChanged(self, event, xmin: int = None, xmax: int = None):
        cs.logging.info(f'onFitRangeChanged: {xmin, xmax}')
        if xmin is not None:
            self.xmin = xmin
        if xmax is not None:
            self.xmax = xmax
        fc = get_fitting_client()
        if fc is not None:
            fc.set_fit_range(
                fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                xmin=self.xmin,
                xmax=self.xmax,
            )
        if getattr(self, '_is_2d_dataset', False):
            try:
                self._update_2d_mask_from_spinboxes()
            except Exception as e:
                cs.logging.warning(f'Failed to update 2D mask from spinboxes: {e}')
        if getattr(self, '_auto_fit_range_in_progress', False):
            return
        if fc is not None:
            fc.update_fit(
                fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
            )
        else:
            # No transport: recompute locally. `Fit.update()` publishes
            # ``fit.updated`` itself, so the plot redraw follows on either
            # path -- this branch used to end after setting the range, which
            # left the displayed curve stale until something else updated.
            try:
                self.fit.update()
            except Exception as e:
                cs.logging.warning(f'fit update after range change failed: {e}')


    def onAutoFitRange(self):
        """Apply the reader-provided default fit range and update the fit."""
        try:
            fc = get_fitting_client()
            fit_uid_val = str(getattr(self.fit, "unique_identifier", "") or "")
            range_applied_by_rpc = False
            if fc is not None:
                result = fc.auto_fit_range(fit_uid=fit_uid_val)
                if result.get("ok"):
                    xmin_1d, xmax_1d = result.get("xmin", 0), result.get("xmax", 0)
                    range_applied_by_rpc = bool(result.get("applied"))
                else:
                    try:
                        xmin_1d, xmax_1d = self.fit.data.data_reader.autofitrange(self.fit.data)
                    except Exception:
                        return
            else:
                try:
                    xmin_1d, xmax_1d = self.fit.data.data_reader.autofitrange(self.fit.data)
                except Exception:
                    return

            cs.logging.info(f'onAutoFitRange: {xmin_1d, xmax_1d}')

            try:
                self._auto_fit_range_in_progress = True
            except Exception:
                pass

            deferred_update_scheduled = False
            blocked_widgets = []
            for widget in (self.spinBox_2, self.spinBox_4, self.spinBox, self.spinBox_6):
                try:
                    blocked_widgets.append((widget, widget.blockSignals(True)))
                except Exception:
                    pass

            try:
                if getattr(self, '_is_2d_dataset', False) and self._2d_shape is not None:
                    ny, nx = int(self._2d_shape[0]), int(self._2d_shape[1])
                    self.spinBox_2.setRange(0, max(0, nx - 1))
                    self.spinBox_4.setRange(0, max(0, nx - 1))
                    self.spinBox.setRange(0, max(0, ny - 1))
                    self.spinBox_6.setRange(0, max(0, ny - 1))
                    self.spinBox_2.setValue(0)
                    self.spinBox_4.setValue(max(0, nx - 1))
                    self.spinBox.setValue(0)
                    self.spinBox_6.setValue(max(0, ny - 1))
                    try:
                        n_flat = int(len(self.fit.data.y))
                    except Exception:
                        n_flat = max(0, int(xmax_1d))
                    if fc is not None:
                        fc.set_fit_range(fit_uid=fit_uid_val, xmin=0, xmax=n_flat)
                    else:
                        self.fit.fit_range = (0, n_flat)
                    try:
                        self._update_2d_mask_from_spinboxes()
                    except Exception as e:
                        cs.logging.warning(f'Failed to update 2D mask after 2D autofitrange: {e}')
                else:
                    self.xmin, self.xmax = (xmin_1d, xmax_1d)
                    if fc is not None and not range_applied_by_rpc:
                        fc.set_fit_range(fit_uid=fit_uid_val, xmin=xmin_1d, xmax=xmax_1d)
                    elif fc is None:
                        self.fit.fit_range = (int(xmin_1d), int(xmax_1d))

                fit = self.fit
                xmin_val = int(self.xmin)
                xmax_val = int(self.xmax)
                is_2d = bool(getattr(self, "_is_2d_dataset", False))
                xmin2_val = int(self.xmin2) if is_2d else 0
                xmax2_val = int(self.xmax2) if is_2d else 0

                def _do_deferred_update():
                    try:
                        if fc is None:
                            try:
                                fit.update()
                            except Exception as e:
                                cs.logging.warning(f"Local fit update after auto fit range failed: {e}")
                        try:
                            payload = {
                                "fit_group": str(getattr(fit, "name", "")),
                                "xmin": xmin_val,
                                "xmax": xmax_val,
                                "source": "auto_fit_range",
                                "is_2d": is_2d,
                            }
                            if is_2d:
                                payload.update({
                                    "x_min": xmin_val,
                                    "x_max": xmin2_val,
                                    "y_min": xmax_val,
                                    "y_max": xmax2_val,
                                })
                            self._record_history(
                                action_type="fit_range_set",
                                summary=f"auto fit range for '{getattr(fit, 'name', '')}' to [{xmin_val}, {xmax_val})",
                                payload=payload,
                            )
                        except Exception:
                            pass
                    finally:
                        try:
                            self._auto_fit_range_in_progress = False
                        except Exception:
                            pass

                QtCore.QTimer.singleShot(0, _do_deferred_update)
                deferred_update_scheduled = True
            finally:
                for widget, previous_state in reversed(blocked_widgets):
                    try:
                        widget.blockSignals(previous_state)
                    except Exception:
                        pass
                if not deferred_update_scheduled:
                    try:
                        self._auto_fit_range_in_progress = False
                    except Exception:
                        pass
        except Exception as e:
            cs.logging.warning(f"onAutoFitRange failed: {e}")
            try:
                self._auto_fit_range_in_progress = False
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Dimensionality and 2D mask helpers
    # ------------------------------------------------------------------

    def _init_dimensionality(self) -> None:
        """Detect whether the attached dataset exposes a generic grid.

        Detection is based solely on ``data.meta_data['grid']``, which is a
        dictionary with at least the following keys when present:

        - ``ndim``: int
            Number of logical grid dimensions. Only ``ndim == 2`` is
            currently supported by this widget.
        - ``shape``: tuple
            Grid shape ``(ny, nx)`` used when reconstructing 2D selections
            from the 1D flattened data arrays.
        - ``order``: str, optional
            NumPy-style memory order string used to map the 2D grid to the
            1D data vector. Known values are::

                'C'  # row-major flattening (default)
                'F'  # column-major flattening

            Some experiments may additionally provide explicit index arrays
            (e.g. ``row_indices`` / ``col_indices``) when the 1D vector is a
            sparse view of the grid. These are used by
            :meth:`_update_2d_mask_from_spinboxes` to translate 2D rectangles
            into 1D masks when present.

        Experiment-specific readers (e.g. PDA, RICS) are responsible for
        populating this metadata; the controller itself stays agnostic of the
        concrete experiment/model types.
        """

        data = None
        try:
            data = self.fit.data
        except Exception:
            pass

        # Reset cached dimensionality state
        self._is_2d_dataset = False
        self._2d_shape = None
        self._grid_meta = {}
        self._grid_flattening = None

        if data is None:
            return

        try:
            meta_all = getattr(data, 'meta_data', {}) or {}
        except Exception:
            meta_all = {}
        grid_meta = meta_all.get('grid', {}) or {}

        try:
            ndim = int(grid_meta.get('ndim', 1))
        except Exception:
            ndim = 1
        shape = grid_meta.get('shape', None)

        if ndim == 2 and shape is not None:
            try:
                ny, nx = int(shape[0]), int(shape[1])
                if ny > 0 and nx > 0:
                    self._is_2d_dataset = True
                    self._2d_shape = (ny, nx)
                    self._grid_meta = grid_meta
                    self._grid_order = grid_meta.get('order', 'C')
            except Exception:
                pass

        # Configure spin boxes according to dimensionality
        try:
            if self._is_2d_dataset and self._2d_shape is not None:
                ny, nx = int(self._2d_shape[0]), int(self._2d_shape[1])
                # x-axis: columns (0 .. nx-1)
                self.spinBox_2.setRange(0, max(0, nx - 1))
                self.spinBox_4.setRange(0, max(0, nx - 1))
                # y-axis: rows (0 .. ny-1)
                self.spinBox.setRange(0, max(0, ny - 1))
                self.spinBox_6.setRange(0, max(0, ny - 1))

                # Default to full extents if not yet initialized
                if self.spinBox_4.value() == 0:
                    self.spinBox_2.setValue(0)
                    self.spinBox_4.setValue(max(0, nx - 1))
                if self.spinBox_6.value() == 0:
                    self.spinBox.setValue(0)
                    self.spinBox_6.setValue(max(0, ny - 1))

                # Make sure the secondary spin boxes are visible and enabled
                self.spinBox_4.setEnabled(True)
                self.spinBox_6.setEnabled(True)
                self._set_field_visible('xmin2', True)
                self._set_field_visible('xmax2', True)

                # Update mask when any of the 2D range spin boxes changes.
                try:
                    self.spinBox_2.editingFinished.connect(lambda: self._update_2d_mask_from_spinboxes())
                    self.spinBox_4.editingFinished.connect(lambda: self._update_2d_mask_from_spinboxes())
                    self.spinBox.editingFinished.connect(lambda: self._update_2d_mask_from_spinboxes())
                    self.spinBox_6.editingFinished.connect(lambda: self._update_2d_mask_from_spinboxes())
                except Exception:
                    pass
            else:
                # 1D datasets: keep only the original two spin boxes active
                # for the fit range; the extra pair is disabled to avoid
                # suggesting a 2D selection.
                self.spinBox_4.setEnabled(False)
                self.spinBox_6.setEnabled(False)
                self._set_field_visible('xmin2', False)
                self._set_field_visible('xmax2', False)
        except Exception:
            pass

    def _update_2d_mask_from_spinboxes(self) -> None:
        if not getattr(self, '_is_2d_dataset', False):
            return

        try:
            data = self.fit.data
        except Exception:
            return

        x_min = int(self.xmin)
        x_max = int(self.xmin2)
        y_min = int(self.xmax)
        y_max = int(self.xmax2)

        if self._2d_shape is None:
            return
        ny, nx = int(self._2d_shape[0]), int(self._2d_shape[1])
        if ny <= 0 or nx <= 0:
            return

        x0 = max(0, min(x_min, x_max))
        x1 = min(nx - 1, max(x_min, x_max))
        y0 = max(0, min(y_min, y_max))
        y1 = min(ny - 1, max(y_min, y_max))

        if x1 < x0 or y1 < y0:
            fc = get_fitting_client()
            if fc is not None:
                fc.set_fit_mask(
                    mask=[],
                    fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                )
            return

        grid_meta = getattr(self, '_grid_meta', {}) or {}

        mask_data = None
        if 'row_indices' in grid_meta and 'col_indices' in grid_meta:
            try:
                row_indices = np.asarray(grid_meta.get('row_indices'), dtype=np.int64)
                col_indices = np.asarray(grid_meta.get('col_indices'), dtype=np.int64)
            except Exception:
                return
            if row_indices.size == 0 or col_indices.size == 0:
                return
            n = min(row_indices.size, col_indices.size)
            mask = (
                (col_indices[:n] >= x0) & (col_indices[:n] <= x1) &
                (row_indices[:n] >= y0) & (row_indices[:n] <= y1)
            )
            mask_data = mask.astype(float)
        else:
            try:
                ny_img, nx_img = int(ny), int(nx)
            except Exception:
                ny_img, nx_img = ny, nx
            yy, xx = np.indices((ny_img, nx_img))
            mask_2d = (
                (xx >= x0) & (xx <= x1) &
                (yy >= y0) & (yy <= y1)
            )
            mask_data = mask_2d.ravel().astype(float)

        if mask_data is not None:
            fc = get_fitting_client()
            if fc is not None:
                fc.set_fit_mask(
                    mask=mask_data.tolist(),
                    fit_uid=str(getattr(self.fit, "unique_identifier", "") or ""),
                )
