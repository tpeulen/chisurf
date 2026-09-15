"""Built-in registrations mapping view-spec keys to ChiSurf widgets/plots.

Importing this module wires the standard plot keys (``line``, ``residual``,
``distribution`` ...) and standard custom sections into the registry. The model
layer references these by string only; the concrete classes live here.
"""

from __future__ import annotations

import math

from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
import chisurf.core.math.datatools
from chisurf import logging
from chisurf.gui.glyphs import Glyphs

from .registry import register_plot, register_section


def _wrap_tooltip(text: str, width: int | None = None) -> str:
    """Word-wrap a tooltip so long descriptions break over several lines.

    Thin delegate to the shared, YAML-configurable
    :func:`chisurf.gui.tooltip.wrap_tooltip` (``gui.tooltip.wrap_width``).
    """
    from chisurf.gui.tooltip import wrap_tooltip

    return wrap_tooltip(text, width)


# --- plots -----------------------------------------------------------------
# Registered as zero-arg factories so chisurf.gui.plots is only imported when a
# plot is actually resolved.
def _plots():
    import chisurf.gui.plots as _p

    return _p


register_plot("line", lambda: _plots().LinePlot)
register_plot("residual", lambda: _plots().ResidualPlot)
register_plot("fit_info", lambda: _plots().FitInfo)
register_plot("fit_table", lambda: _plots().FitTablePlot)
register_plot("parameter_scan", lambda: _plots().ParameterScanPlot)
register_plot("distribution", lambda: _plots().DistributionPlot)
register_plot("residual2d", lambda: _plots().Residual2DPlot)
register_plot("mfd_2d", lambda: _plots().MfdMarginalPlot)
register_plot("mfd_marginals", lambda: _plots().MfdMarginalPlot)
register_plot("mfd_map", lambda: _plots().MfdMapPlot)
register_plot("lcurve", lambda: _plots().LCurvePlot)
register_plot("pr_ci", lambda: _plots().DeerPrCIPlot)


def _proteinmc_plots():
    import chisurf.gui.plots.proteinMC as _p

    return _p


register_plot("proteinmc_structure", lambda: _proteinmc_plots().ProteinMCStructurePlot)
register_plot("proteinmc_network", lambda: _proteinmc_plots().ProteinMCDistanceNetworkPlot)
register_plot("proteinmc_traces", lambda: _proteinmc_plots().ProteinMCPlot)


def resolve_distribution_options(options: dict) -> dict:
    """Resolve string accessors in distribution-plot options to callables.

    The view-spec keeps accessors as names (e.g. ``"interleaved_to_two_columns"``)
    so the model stays GUI-free; here they are mapped back to the actual
    functions from :mod:`chisurf.core.math.datatools`.
    """
    resolved = dict(options)
    dist = resolved.get("distribution_options")
    if isinstance(dist, dict):
        new_dist = {}
        for name, cfg in dist.items():
            cfg = dict(cfg)
            accessor = cfg.get("accessor")
            if isinstance(accessor, str):
                cfg["accessor"] = _resolve_accessor(accessor)
            new_dist[name] = cfg
        resolved["distribution_options"] = new_dist
    return resolved


def _resolve_accessor(accessor: str):
    """Resolve a distribution-plot accessor name to a callable.

    Bare names (e.g. ``"interleaved_to_two_columns"``) resolve against
    :mod:`chisurf.core.math.datatools`. A dotted or ``module:function`` path
    (e.g. ``"chisurf.core.models.pda2c.common:get_pda_distribution"``) is imported
    directly, so model-specific Qt-free accessors stay authorable in JSON.
    """
    if ":" in accessor or "." in accessor:
        import importlib

        if ":" in accessor:
            mod_name, _, func_name = accessor.partition(":")
        else:
            mod_name, _, func_name = accessor.rpartition(".")
        try:
            return getattr(importlib.import_module(mod_name), func_name, None)
        except Exception:
            return None
    return getattr(chisurf.core.math.datatools, accessor, None)


# --- curve inputs ----------------------------------------------------------
class CurveInputWidget(QtWidgets.QWidget):
    """Generic data-curve picker for a :class:`CurveInputSection`.

    Renders a label, a read-only name field, a "Select…" button (opening an
    :class:`ExperimentalDataSelector`) and an optional "Unload" button. Selecting
    a curve dispatches ``section.select_action`` with the chosen curve's index
    and name (under ``section.index_key`` / ``section.name_key``) plus
    ``fit_index``; unloading dispatches ``section.unload_action``. This is the
    one widget behind every curve input (IRF, background, linearization table),
    so those inputs stay authorable in ``.view.json``.
    """

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        self._section = section
        self._selector = None

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QtWidgets.QLabel(section.label)
        layout.addWidget(lbl)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setReadOnly(True)
        self.name_edit.setPlaceholderText(f"load {section.label} →")
        layout.addWidget(self.name_edit, 1)

        # compact icon-style buttons matching the hand-written widgets
        self.select_btn = QtWidgets.QToolButton()
        self.select_btn.setText("…")  # ellipsis
        self.select_btn.setToolTip(f"Select {section.label}")
        self.select_btn.clicked.connect(self._open_selector)
        layout.addWidget(self.select_btn)

        self.unload_btn = QtWidgets.QToolButton()
        self.unload_btn.setText(Glyphs.CLOSE)  # ✕
        self.unload_btn.setToolTip(f"Unload {section.label}")
        self.unload_btn.clicked.connect(self._unload)
        self.unload_btn.setVisible(bool(section.unload_action))
        layout.addWidget(self.unload_btn)

        # inline FWHM readout for the IRF, like the legacy convolve widget
        self.fwhm_label = None
        if section.name_attr == "irf":
            layout.addWidget(QtWidgets.QLabel("FWHM"))
            self.fwhm_label = QtWidgets.QLineEdit()
            self.fwhm_label.setReadOnly(True)
            self.fwhm_label.setMaximumWidth(64)
            layout.addWidget(self.fwhm_label)

        self._refresh_name()
        self._refresh_fwhm()

    def _own_fit_index(self) -> int:
        """Return the index of this model's fit in ``chisurf.fits``, or ``-1``.

        ``-1`` means the bound model's fit is not registered with the fit
        machinery — a scripted or headless fit, or a tool with no fit at all.
        This used to answer ``0``, which is not "unknown" but *another fit*:
        against an empty list it raised, and against a populated one it would
        have dispatched the edit at whichever fit happened to be first.
        Fit-targeted dispatch is skipped for a negative index instead.
        """
        try:
            fit = getattr(self._model, "fit", None)
            for i, fg in enumerate(cs.fits):
                if fg is fit or fit in list(fg):
                    return i
        except Exception:
            pass
        return -1

    def _open_selector(self):
        from chisurf.gui.widgets.experiments import ExperimentalDataSelector

        fit = getattr(self._model, "fit", None)
        try:
            experiment = fit.data.experiment.__class__
        except Exception:
            experiment = None
        self._selector = ExperimentalDataSelector(
            parent=None, change_event=self._on_change, fit=fit, experiment=experiment
        )
        self._selector.show()

    def _on_change(self):
        sel = self._selector
        if sel is None:
            return
        section = self._section
        try:
            idx = int(sel.selected_curve_index)
            name = str(sel.curve_name)
        except Exception as exc:
            logging.warning(f"CurveInputWidget: could not read selection: {exc}")
            return
        fit_index = self._own_fit_index()
        payload = dict(getattr(section, "action_fixed", {}) or {})
        payload.update({section.index_key: idx, section.name_key: name, "fit_index": int(fit_index)})
        try:
            if section.select_action and fit_index >= 0:
                cs.core.actions.dispatch(name=section.select_action, payload=payload)
            _dispatch_fit_update(fit_index)
        except Exception as exc:
            logging.warning(f"CurveInputWidget: select dispatch failed: {exc}")
        self.name_edit.setText(name)
        self._refresh_fwhm()

    def _unload(self):
        section = self._section
        if not section.unload_action:
            return
        fit_index = self._own_fit_index()
        try:
            if fit_index >= 0:
                payload = dict(getattr(section, "action_fixed", {}) or {})
                payload["fit_index"] = int(fit_index)
                cs.core.actions.dispatch(name=section.unload_action, payload=payload)
            _dispatch_fit_update(fit_index)
        except Exception as exc:
            logging.warning(f"CurveInputWidget: unload dispatch failed: {exc}")
        self.name_edit.clear()
        self._refresh_fwhm()

    def _refresh_name(self):
        section = self._section
        if not (section.name_attr and section.target):
            return
        group = getattr(self._model, section.target, None)
        curve = getattr(group, section.name_attr, None) if group is not None else None
        name = getattr(curve, "name", None) or getattr(curve, "filename", None)
        if name:
            self.name_edit.setText(str(name))

    def _refresh_fwhm(self):
        if self.fwhm_label is None:
            return
        group = getattr(self._model, self._section.target, None)
        curve = getattr(group, self._section.name_attr, None) if group is not None else None
        fwhm = getattr(curve, "fwhm", None)
        try:
            self.fwhm_label.setText(f"{float(fwhm):.3f}" if fwhm is not None else "")
        except Exception:
            self.fwhm_label.setText("")


# --- choice / toggle inputs ------------------------------------------------
def _resolve_options_source(name: str, model=None):
    """Resolve a named option list.

    Prefers a model-backed source — an attribute or zero-arg method named *name*
    on *model* returning a list (so tool view-models can drive dynamic combos);
    otherwise falls back to the built-in named sources. A dotted *name* is
    followed through sub-groups, matching how ``attr`` and ``target`` resolve.
    """
    if model is not None:
        src = model
        try:
            for part in str(name).split("."):
                src = getattr(src, part)
        except AttributeError:
            src = None
        if src is not None:
            try:
                return list(src() if callable(src) else src)
            except Exception as exc:  # pragma: no cover - defensive
                logging.warning(f"ChoiceWidget: model options_source {name!r} failed: {exc}")
                return []
    sources = {
        "window_function_types": lambda: list(chisurf.core.math.signal.window_function_types),
    }
    factory = sources.get(name)
    if factory is None:
        logging.warning(f"ChoiceWidget: unknown options_source {name!r}")
        return []
    try:
        return factory()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning(f"ChoiceWidget: options_source {name!r} failed: {exc}")
        return []


def _dispatch_fit_update(fit_index: int) -> None:
    """Ask the fit machinery to recompute, unless the fit is unregistered.

    A negative index comes from :meth:`_own_fit_index` and means the bound
    model's fit is not in ``chisurf.fits`` — scripted, headless, or a tool with
    no fit. Dispatching anyway would target fit 0, which is somebody else's.
    """
    if int(fit_index) < 0:
        return
    cs.core.actions.dispatch(name="fit.update", payload={"fit_index": int(fit_index)})


class _BoundControlMixin:
    """Shared get/set/dispatch for attribute- or action-bound controls."""

    def _apply_tooltip(self, *widgets):
        """Set the effective description as the tooltip on the given widgets.

        Qt does not propagate a parent widget's tooltip to its children, so the
        interactive editor needs its own copy for the help to show on hover.
        The section's own ``description`` wins; when it is empty the bound
        attribute (``section.attr``) is looked up in the shared parameter
        registry so authored view specs get inline help for free.
        """
        desc = _wrap_tooltip(self._effective_description())
        if not desc:
            return
        for w in widgets:
            if w is not None:
                w.setToolTip(desc)

    def _effective_description(self) -> str:
        """Resolve the section description, falling back to the registry.

        Returns ``section.description`` verbatim when set. Otherwise the bound
        attribute name is resolved against
        :func:`chisurf.core.settings.describe_parameter`, scoped by the target
        group's class so a bare name maps to the right entry.
        """
        desc = getattr(self._section, "description", "")
        if desc:
            return desc
        attr = getattr(self._section, "attr", None)
        if not attr:
            return ""
        try:
            import chisurf.core.settings

            group = self._group()
            owner = type(group).__name__ if group is not None else None
            return chisurf.core.settings.describe_parameter(attr, owner=owner)
        except Exception:
            return ""

    def _group(self):
        """Return the object this control reads and writes.

        A ``target`` names a parameter group on the model. **Omitting it means the
        model itself**, which is what a model-level flag needs (the worm-like
        chain's dye-linker switch is an attribute of the model, not of any
        group). Before that, a section without a target bound to nothing: the
        control rendered, accepted clicks, and wrote them nowhere.
        """
        target = getattr(self._section, "target", None)
        if not target:
            return self._model
        return getattr(self._model, target, None)

    def _refresh_host_form(self) -> None:
        """Walk up to the hosting AutoForm and refresh its dependent widgets.

        Duck-typed (an AutoForm exposes ``sync_fields`` + ``refresh_plots``) to
        avoid importing AutoForm here. ``refresh_plots`` also re-runs every
        ``AUTOFORM_REFRESH`` custom widget (rate-matrix, channel tables, …).
        """
        widget = self.parentWidget() if hasattr(self, "parentWidget") else None
        while widget is not None:
            if hasattr(widget, "sync_fields") and hasattr(widget, "refresh_plots"):
                try:
                    widget.sync_fields()
                    widget.refresh_plots()
                except Exception:
                    pass
                return
            widget = widget.parentWidget()

    def _maybe_rebuild_host(self) -> None:
        """Deferred full rebuild of the hosting AutoForm, opt-in via ``rebuild_on_change``.

        Generalizes the combo-driven ``QTimer.singleShot(0, form.rebuild)``
        pattern already used by several tool-specific hosts (e.g. the PCH
        detector/setup combos) so any ``choice`` section can ask for it
        declaratively. Deferred so the rebuild does not tear down widgets while
        still inside the ``toggled``/``currentIndexChanged`` signal that
        triggered it. A full ``rebuild()`` re-evaluates every ``collapsed_when``
        (including ``not_equals``), so sibling panels bound to this section's
        attribute re-fold immediately instead of only on the next manual
        rebuild.
        """
        if not getattr(self._section, "rebuild_on_change", False):
            return
        widget = self.parentWidget() if hasattr(self, "parentWidget") else None
        while widget is not None:
            if hasattr(widget, "rebuild") and hasattr(widget, "sync_fields"):
                QtCore.QTimer.singleShot(0, widget.rebuild)
                return
            widget = widget.parentWidget()

    def _own_fit_index(self) -> int:
        """Return the index of this model's fit in ``chisurf.fits``, or ``-1``.

        ``-1`` means the bound model's fit is not registered with the fit
        machinery — a scripted or headless fit, or a tool with no fit at all.
        This used to answer ``0``, which is not "unknown" but *another fit*:
        against an empty list it raised, and against a populated one it would
        have dispatched the edit at whichever fit happened to be first.
        Fit-targeted dispatch is skipped for a negative index instead.
        """
        try:
            fit = getattr(self._model, "fit", None)
            for i, fg in enumerate(cs.fits):
                if fg is fit or fit in list(fg):
                    return i
        except Exception:
            pass
        return -1

    def _current_value(self):
        """Read the bound attribute, following a dotted path if the spec uses one.

        ``_commit`` walks ``a.b.c``, so reading must too: a widget that writes
        through a dotted path but reads back ``None`` silently displays its
        minimum instead of the model's value.
        """
        section = self._section
        if section.attr:
            group = self._group()
            obj = group if group is not None else self._model
            if obj is not None:
                try:
                    for part in str(section.attr).split("."):
                        obj = getattr(obj, part)
                    return obj
                except Exception:
                    return None
        return None

    def _commit(self, value):
        """Apply a new value via action dispatch or direct attribute set."""
        section = self._section
        fit_index = self._own_fit_index()
        try:
            if section.set_action and fit_index >= 0:
                payload = dict(section.action_fixed)
                payload[section.value_key] = value
                payload["fit_index"] = int(fit_index)
                cs.core.actions.dispatch(name=section.set_action, payload=payload)
            elif section.attr:
                group = self._group()
                obj = group if group is not None else self._model
                if obj is not None:
                    if "." in section.attr:
                        parts = section.attr.split(".")
                        curr = obj
                        for p in parts[:-1]:
                            curr = getattr(curr, p)
                        setattr(curr, parts[-1], value)
                    else:
                        setattr(obj, section.attr, value)
            # Tool view-models (not in the action registry) can request a direct
            # model-method call with the new value.
            call = getattr(section, "call", "")
            if call:
                fn = getattr(self._model, call, None)
                if callable(fn):
                    fn(value)
                # A ``call`` may change state other widgets depend on (e.g. a
                # species/state count that resizes a rate-matrix or table). Refresh
                # the hosting form's dependent widgets so this works in any context
                # (standalone tool or embedded settings page), without the model
                # needing a reference to the form.
                self._refresh_host_form()
            # Only nudge the fit machinery when the bound object actually belongs
            # to a fit the machinery knows about. Generic AutoForm consumers
            # (settings/tool dialogs) have no ``fit``, and a scripted fit has one
            # that was never registered -- neither must trigger a recompute.
            if getattr(self._model, "fit", None) is not None:
                _dispatch_fit_update(fit_index)
            else:
                self._refresh_host_form()
            self._maybe_rebuild_host()
        except Exception as exc:
            logging.warning(f"bound control commit failed ({section.label}): {exc}")


class ChoiceWidget(_BoundControlMixin, QtWidgets.QWidget):
    """One-of-N selector for a :class:`ChoiceSection`.

    Renders inline radio buttons when ``section.style == "radio"`` (compact, like
    the hand-written convolution-type control), otherwise a combo box.
    """

    is_form_field = True

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        self._section = section
        self.form_label = section.label

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._options = self._resolve_opts()
        current = self._current_value()

        self.combo = None
        self._radios = []
        if section.style == "radio":
            self._button_group = QtWidgets.QButtonGroup(self)
            _labels = self._labels()
            for i, opt in enumerate(self._options):
                rb = QtWidgets.QRadioButton(_labels[i])
                if current is not None and str(opt) == str(current):
                    rb.setChecked(True)
                rb.toggled.connect(lambda checked, v=opt: self._commit(v) if checked else None)
                self._button_group.addButton(rb)
                self._radios.append(rb)
                layout.addWidget(rb)
            layout.addStretch(1)
            self._apply_tooltip(self, *self._radios)
        else:
            self.combo = QtWidgets.QComboBox()
            if section.editable:
                self.combo.setEditable(True)
                self.combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
                # Qt's default completer matches on the *prefix*, which is no help
                # in a list of several hundred entries where the distinguishing
                # part is in the middle ("647" in "Alexa Fluor 647"). Match on any
                # substring, case-insensitively, and pop the filtered list up.
                completer = QtWidgets.QCompleter(self.combo.model(), self.combo)
                completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
                completer.setFilterMode(QtCore.Qt.MatchContains)
                completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
                self.combo.setCompleter(completer)
            self._populate_combo(current)
            self.combo.currentIndexChanged.connect(self._on_index_changed)
            if section.editable:
                # Commit free-typed text (not necessarily among the options) on
                # focus-out / Enter, so a hand-entered model id is preserved.
                self.combo.lineEdit().editingFinished.connect(
                    lambda: self._commit(self.combo.currentText().strip())
                )
            layout.addWidget(self.combo, 1)
            self._apply_tooltip(self, self.combo)
            # Optional +/- buttons for managed (dynamic) combos driven by model methods.
            if section.add_action:
                add_btn = QtWidgets.QToolButton()
                add_btn.setText(section.add_label)
                add_btn.clicked.connect(self._on_add)
                layout.addWidget(add_btn)
            if section.remove_action:
                del_btn = QtWidgets.QToolButton()
                del_btn.setText(section.remove_label)
                del_btn.clicked.connect(self._on_remove)
                layout.addWidget(del_btn)

    def _resolve_opts(self) -> list:
        """Return the option *values*.

        A ``options_source`` may yield either a flat list of values or a list of
        ``(value, label)`` pairs; in the latter case the display labels are kept
        in ``self._dynamic_labels`` (consumed by :meth:`_labels`) so dynamic
        combos can show a human-readable label while committing the raw value —
        e.g. a foreign-key dropdown showing ``"3 — Alexa 488"`` but storing ``3``.
        """
        section = self._section
        self._dynamic_labels = None
        options = list(section.options)
        if not options and section.options_source:
            resolved = _resolve_options_source(section.options_source, self._model)
            values, labels, paired = [], [], False
            for item in resolved:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    paired = True
                    values.append(item[0])
                    labels.append(item[1])
                else:
                    values.append(item)
                    labels.append(item)
            options = values
            if paired:
                self._dynamic_labels = [str(x) for x in labels]
        return options

    def _labels(self) -> list:
        dyn = getattr(self, "_dynamic_labels", None)
        if dyn and len(dyn) == len(self._options):
            return dyn
        labels = list(getattr(self._section, "labels", ()))
        if labels and len(labels) == len(self._options):
            return [str(x) for x in labels]
        return [str(o) for o in self._options]

    def _populate_combo(self, current) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        for label in self._labels():
            self.combo.addItem(label)
        matched = False
        if current is not None:
            for i, opt in enumerate(self._options):
                if str(opt) == str(current):
                    self.combo.setCurrentIndex(i)
                    matched = True
                    break
        # An editable combo may hold a value the option list does not contain
        # (a hand-typed model id); show it verbatim in the line edit.
        if not matched and current is not None and self.combo.isEditable():
            self.combo.setEditText(str(current))
        self.combo.blockSignals(False)

    def _on_index_changed(self, idx) -> None:
        if 0 <= idx < len(self._options):
            self._commit(self._options[idx])

    def _on_add(self) -> None:
        fn = getattr(self._model, self._section.add_action, None)
        if callable(fn):
            fn()
        self._rebuild_options()

    def _on_remove(self) -> None:
        fn = getattr(self._model, self._section.remove_action, None)
        if callable(fn):
            fn(self._current_value())
        self._rebuild_options()

    def _rebuild_options(self) -> None:
        """Re-read the model-backed option list and restore the current value."""
        self._options = self._resolve_opts()
        if self.combo is not None:
            self._populate_combo(self._current_value())

    def sync(self) -> None:
        """Re-read the model value (and dynamic options) without firing signals."""
        if self._section.options_source:
            self._rebuild_options()
        cur = self._current_value()
        if cur is None:
            return
        if self.combo is not None:
            if self.combo.isEditable():
                self._populate_combo(cur)
            else:
                for i, opt in enumerate(self._options):
                    if str(opt) == str(cur):
                        self.combo.blockSignals(True)
                        self.combo.setCurrentIndex(i)
                        self.combo.blockSignals(False)
                        break
        else:
            for opt, rb in zip(self._options, self._radios):
                if str(opt) == str(cur):
                    rb.blockSignals(True)
                    rb.setChecked(True)
                    rb.blockSignals(False)
                    break


class ToggleWidget(_BoundControlMixin, QtWidgets.QWidget):
    """Boolean checkbox for a :class:`ToggleSection`."""

    is_form_field = True

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        self._section = section
        self.form_label = section.label

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        # label moves to the form's label column; checkbox sits in the field column
        self.checkbox = QtWidgets.QCheckBox()
        current = self._current_value()
        if current is not None:
            self.checkbox.setChecked(bool(current))
        self.checkbox.toggled.connect(lambda checked: self._commit(bool(checked)))
        layout.addWidget(self.checkbox)
        layout.addStretch(1)
        self._apply_tooltip(self, self.checkbox)

    def sync(self) -> None:
        """Re-read the model value into the checkbox without firing signals."""
        cur = self._current_value()
        if cur is None:
            return
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(bool(cur))
        self.checkbox.blockSignals(False)


class ToggleRowWidget(QtWidgets.QWidget):
    """Multiple boolean checkboxes on a single horizontal line.

    Used for ``ToggleRowSection`` (e.g. Pile-up / DNL / Reverse in corrections).
    Each item dict has keys ``target``, ``attr``, ``label``.
    """

    is_form_field = False

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for item in section.items:
            target = item.get("target")
            attr = item.get("attr", "")
            label = item.get("label", attr)
            group = getattr(model, target, model) if target else model
            cb = QtWidgets.QCheckBox(label)
            desc = _wrap_tooltip(item.get("description", ""))
            if desc:
                cb.setToolTip(desc)
            cb.setChecked(bool(getattr(group, attr, False)))

            def _on_toggle(checked, g=group, a=attr, m=model):
                setattr(g, a, bool(checked))
                try:
                    m.update()
                except Exception:
                    pass

            cb.toggled.connect(_on_toggle)
            layout.addWidget(cb)
        layout.addStretch(1)


class ButtonRowWidget(QtWidgets.QWidget):
    """A horizontal row of action buttons for a :class:`ButtonRowSection`.

    Each button dict has keys ``label``, ``action`` (a zero-arg model method) and
    optional ``description``. Lets tool toolbars be authored declaratively.
    """

    is_form_field = False

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if getattr(section, "menu", ""):
            self._build_menu(section, layout)
        else:
            for item in section.buttons:
                btn = QtWidgets.QToolButton()
                btn.setText(item.get("label", ""))
                desc = _wrap_tooltip(item.get("description", ""))
                if desc:
                    btn.setToolTip(desc)
                action = item.get("action", "")
                # Name the button after what it does, so a host that has to
                # reach one (to emphasise it, hide it, drive it from a test)
                # can ask for it by action instead of by its label -- a label
                # is a translation and a decoration away from changing.
                btn._autoform_action = action
                btn.setObjectName(f"button_{action}" if action else "")
                btn.clicked.connect(lambda checked=False, a=action: self._call(a))
                layout.addWidget(btn)
        layout.addStretch(1)

    def _build_menu(self, section, layout) -> None:
        """Collapse the buttons into a single popup ``QToolButton`` menu."""
        tool = QtWidgets.QToolButton()
        tool.setText(section.menu)
        tool.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        tool.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        menu = QtWidgets.QMenu(tool)
        menu.setToolTipsVisible(True)
        for item in section.buttons:
            act = menu.addAction(item.get("label", ""))
            desc = _wrap_tooltip(item.get("description", ""))
            if desc:
                act.setToolTip(desc)
            action = item.get("action", "")
            act.triggered.connect(lambda checked=False, a=action: self._call(a))
        tool.setMenu(menu)
        layout.addWidget(tool)

    def _call(self, action: str) -> None:
        # Flush an in-progress field edit before running the action. Fields commit
        # on focus-out (``editingFinished``), but a NoFocus tool button does not
        # blur the editor on click, so a value typed and not yet committed (e.g. an
        # API key) would otherwise be missed. Clearing focus fires that commit
        # synchronously before the action reads the model.
        focused = QtWidgets.QApplication.focusWidget()
        if focused is not None and focused is not self and self.isAncestorOf(focused) is False:
            focused.clearFocus()
        fn = getattr(self._model, action, None)
        if callable(fn):
            fn()


class TableWidget(QtWidgets.QTableWidget):
    """Record table for a :class:`TableSection`, optionally editable."""

    AUTOFORM_REFRESH = True

    def __init__(self, model, section, parent=None):
        super().__init__(0, len(section.columns), parent)
        self._model = model
        self._section = section
        self._columns = tuple(dict(c) for c in section.columns)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        if getattr(section, "editable", False):
            self.setEditTriggers(
                QtWidgets.QAbstractItemView.DoubleClicked
                | QtWidgets.QAbstractItemView.EditKeyPressed
                | QtWidgets.QAbstractItemView.SelectedClicked
            )
        else:
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        # Central table formatting: the same monospace table font + compact row
        # heights as the log and parameter tables (chisurf.gui.widgets.general).
        try:
            from chisurf.gui.widgets.general import (
                table_font,
                table_header_height,
                table_row_height,
            )

            self.setFont(table_font())
            self.horizontalHeader().setFont(table_font())
            self.verticalHeader().setDefaultSectionSize(table_row_height())
            self.horizontalHeader().setFixedHeight(table_header_height())
        except Exception:
            pass
        self.setHorizontalHeaderLabels(
            [str(c.get("label") or c.get("key") or "") for c in self._columns]
        )
        # ``stretchLastSection`` only ever *grows* the last column, so with a
        # column left unsized it cannot pull the total back inside a narrow
        # viewport. Where the spec leaves any column unsized, those columns are
        # put in Stretch mode instead — which both grows and shrinks — and the
        # last-section stretch is switched off so the two do not fight over it.
        unsized = [i for i, column in enumerate(self._columns) if not column.get("width")]
        self.horizontalHeader().setStretchLastSection(not unsized)
        for i, column in enumerate(self._columns):
            if column.get("description"):
                item = self.horizontalHeaderItem(i)
                if item is not None:
                    item.setToolTip(_wrap_tooltip(str(column.get("description"))))
            if column.get("width"):
                self.setColumnWidth(i, int(column["width"]))
            else:
                # A column the spec did not size shares whatever the sized ones
                # leave. Keeping Qt's default 100 px instead made the declared
                # widths add up past the viewport in a narrow panel, so a table
                # that fits perfectly well grew a horizontal scroll bar and hid
                # its last column behind it.
                try:
                    self.horizontalHeader().setSectionResizeMode(
                        i, QtWidgets.QHeaderView.Stretch
                    )
                except Exception:
                    pass
        if getattr(section, "height", 0):
            self.setMinimumHeight(int(section.height))
        if getattr(section, "expand", False):
            # Fill the panel's spare vertical space (the form layout reads
            # ``_autoform_expanding``) instead of leaving a gap below the rows.
            self._autoform_expanding = True
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemDoubleClicked.connect(lambda _item: self._activate_current_row())
        self.itemChanged.connect(self._on_item_changed)
        self.refresh()

    def _rows(self) -> list:
        source = getattr(self._section, "source", "")
        if not source:
            return []
        value = getattr(self._model, source, None)
        try:
            value = value() if callable(value) else value
        except Exception as exc:
            logging.warning(f"TableWidget: source {source!r} failed: {exc}")
            return []
        return list(value or [])

    @staticmethod
    def _row_value(row, key: str):
        if isinstance(row, dict):
            return row.get(key, "")
        return getattr(row, key, "")

    def _row_dict(self, row_index: int) -> dict:
        item = self.item(row_index, 0)
        data = item.data(QtCore.Qt.UserRole) if item is not None else None
        if isinstance(data, dict):
            return dict(data)
        return {}

    def refresh(self):
        """Re-read rows from the model source."""
        self.blockSignals(True)
        rows = self._rows()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            row_dict = dict(row) if isinstance(row, dict) else {
                str(c.get("key")): self._row_value(row, str(c.get("key")))
                for c in self._columns
            }
            for c, column in enumerate(self._columns):
                key = str(column.get("key") or "")
                value = self._row_value(row, key)
                text = "" if value is None else str(value)
                item = QtWidgets.QTableWidgetItem(text)
                if c == 0:
                    item.setData(QtCore.Qt.UserRole, row_dict)
                self.setItem(r, c, item)
        self.blockSignals(False)
        self._fit_height(len(rows))

    def _fit_height(self, n_rows: int) -> None:
        """Size the table to its rows so it does not leave a large empty area.

        An explicit ``height`` on the section is treated as a fixed/scroll height;
        otherwise the table hugs its content (header + rows) and does not expand
        vertically to fill the panel.

        A section that declared ``expand`` is the exception, and it has to be
        handled here rather than only in ``__init__``: this runs on every
        refresh, so pinning the height would silently undo the expansion the
        constructor asked for — and would pin it to the row count the table had
        when it was *built*, which for a results table is zero. The panel then
        handed the spare space to whatever else was in it (a row of spin boxes,
        spread over the height of the dock) while the table stayed one header
        tall no matter how many rows arrived.
        """
        row_h = self.verticalHeader().defaultSectionSize() or 20
        header_h = self.horizontalHeader().height() or 22
        explicit = int(getattr(self._section, "height", 0) or 0)
        if getattr(self._section, "expand", False):
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            # Qt's "no maximum" sentinel; a previous non-expanding refresh may
            # have pinned one.
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(explicit or (header_h + row_h * 3 + 4))
            return
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        if explicit:
            self.setMinimumHeight(explicit)
            self.setMaximumHeight(explicit)
        else:
            self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.setFixedHeight(header_h + row_h * max(1, n_rows) + 4)

    def _on_item_changed(self, item) -> None:
        if not getattr(self._section, "editable", False):
            return
        call = getattr(self._section, "update_call", "")
        fn = getattr(self._model, call, None) if call else None
        if callable(fn):
            key = str(self._columns[item.column()].get("key") or "")
            fn(item.row(), key, item.text())
            # An edited cell may drive derived widgets (a preview plot, a status
            # panel, dependent fields). Refresh the hosting form so those update,
            # mirroring the value/toggle/button-row behaviour.
            self._refresh_host_form()

    def _refresh_host_form(self) -> None:
        """Walk up to the hosting AutoForm and refresh its dependent widgets."""
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, "sync_fields") and hasattr(widget, "refresh_plots"):
                try:
                    widget.sync_fields()
                    widget.refresh_plots()
                except Exception:
                    pass
                return
            widget = widget.parent()

    def _on_selection_changed(self) -> None:
        row = self.currentRow()
        payload = self._row_dict(row) if row >= 0 else {}
        attr = getattr(self._section, "selected_attr", "")
        if attr:
            setattr(self._model, attr, payload)
        call = getattr(self._section, "selected_call", "")
        if call:
            fn = getattr(self._model, call, None)
            if callable(fn):
                fn(payload)
            else:
                logging.warning(f"TableWidget: model has no callable {call!r}")

    def _activate_current_row(self) -> None:
        call = getattr(self._section, "activated_call", "")
        if not call:
            return
        fn = getattr(self._model, call, None)
        if callable(fn):
            fn(self._row_dict(self.currentRow()))


class InfoWidget(QtWidgets.QTextBrowser):
    """Read-only rich-text (HTML/Markdown) block for an :class:`InfoSection`.

    Shows the section's static ``text`` or, when ``source`` is set, the string
    returned by that zero-arg model method — re-read on :meth:`refresh` so live
    status panels update with the model. Opts into ``AUTOFORM_REFRESH`` so
    ``AutoForm.refresh_plots()`` keeps it current.
    """

    is_form_field = False
    AUTOFORM_REFRESH = True

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        self._section = section
        self.setOpenExternalLinks(False)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        if getattr(section, "height", 0):
            self.setMinimumHeight(int(section.height))
        if getattr(section, "max_height", 0):
            # A short status line must not grow into the panel's spare space.
            self.setMaximumHeight(int(section.max_height))
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self.refresh()

    def _content(self) -> str:
        """Resolve the text to show: the section's ``source``, else its ``text``.

        A ``source`` may name a **method or a plain attribute/property**. Requiring
        a method was a standing trap: naming a property rendered an empty box with
        no error, which reads as "there is nothing to say" rather than "this was
        wired wrong". A name that resolves to nothing at all is now logged.
        """
        source = getattr(self._section, "source", "")
        if source:
            value = getattr(self._model, source, None)
            if value is None and not hasattr(self._model, source):
                logging.warning(
                    f"InfoWidget: source {source!r} not found on "
                    f"{type(self._model).__name__}"
                )
            else:
                try:
                    return str((value() if callable(value) else value) or "")
                except Exception:  # pragma: no cover - defensive
                    logging.warning(f"InfoWidget: source {source!r} failed", exc_info=True)
                    return ""
        return str(getattr(self._section, "text", "") or "")

    def refresh(self) -> None:
        """Re-read the content (static or from ``source``) and re-render it."""
        content = self._content()
        if getattr(self._section, "is_markdown", False):
            # Rendered like every other help page, so an `info` section written
            # in MyST does not show its own markup.
            from chisurf.gui.widgets.tools.help_render import show_in_browser

            show_in_browser(self, content)
        else:
            self.setHtml(content)


class _FocusOutPlainTextEdit(QtWidgets.QPlainTextEdit):
    """Multi-line editor that emits ``editingFinished`` on focus-out.

    Mirrors :class:`QtWidgets.QLineEdit`'s commit-on-focus-out semantics so a
    ``ValueSection`` of ``kind="text"`` commits once the user leaves the field
    rather than on every keystroke.
    """

    editingFinished = QtCore.Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().focusOutEvent(event)
        self.editingFinished.emit()


class ValueWidget(_BoundControlMixin, QtWidgets.QWidget):
    """Scalar field for a :class:`ValueSection`.

    Supported ``kind`` values: ``int`` / ``float`` (spin boxes), ``str`` (line
    edit), ``text`` (multi-line plain-text edit) and ``date`` (date edit).

    ``style="slider"`` pairs the spin box with a slider and applies to ``int``
    and ``float`` alike.
    """

    is_form_field = True

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        self._model = model
        self._section = section
        self.form_label = section.label

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        current = self._current_value()
        # A read-only field must never write back — its value (which may be a
        # non-editable object such as a callable) is displayed but left untouched.
        read_only = bool(getattr(section, "read_only", False))
        # The slider branch is tested FIRST. It handles both kinds, so a plain
        # ``kind == "int"`` test ahead of it swallows every integer slider and
        # renders a bare spin box -- no error, no warning, just a control the
        # spec asked for and did not get.
        wants_slider = (
            section.kind in ("float", "int")
            and (getattr(section, "style", "") == "slider"
                 or getattr(section, "slider", False))
        )
        if wants_slider:
            min_val = float(section.minimum) if section.minimum is not None else 0.0
            max_val = float(section.maximum) if section.maximum is not None else 100.0
            is_float = (section.kind == "float")
            self.editor = QtWidgets.QDoubleSpinBox() if is_float else QtWidgets.QSpinBox()
            if is_float:
                self.editor.setDecimals(int(section.decimals))
                self.editor.setMinimum(min_val)
                self.editor.setMaximum(max_val)
                if section.step:
                    self.editor.setSingleStep(float(section.step))
            else:
                self.editor.setMinimum(int(min_val))
                self.editor.setMaximum(int(max_val))
                if section.step:
                    self.editor.setSingleStep(int(section.step))
            if section.suffix:
                self.editor.setSuffix(section.suffix)

            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(1000)

            # A range spanning decades needs a logarithmic mapping: linear travel
            # over 0.01…100 spends 99 % of the slider above 1, where nothing
            # interesting happens. Falls back to linear when the low end is not
            # strictly positive, since log(0) has no place to sit.
            log_scale = str(getattr(section, "scale", "")).lower() == "log" and min_val > 0.0
            if log_scale:
                log_lo, log_hi = math.log10(min_val), math.log10(max_val)

            def _to_ratio(v: float) -> float:
                clamped = max(min_val, min(max_val, v))
                if log_scale:
                    return ((math.log10(clamped) - log_lo) / (log_hi - log_lo)
                            if log_hi > log_lo else 0.0)
                return (clamped - min_val) / (max_val - min_val) if max_val > min_val else 0.0

            def _from_ratio(ratio: float) -> float:
                if log_scale:
                    return 10.0 ** (log_lo + ratio * (log_hi - log_lo))
                return min_val + ratio * (max_val - min_val)

            def spin_to_slider(v: float):
                slider.blockSignals(True)
                slider.setValue(int(round(_to_ratio(v) * 1000)))
                slider.blockSignals(False)

            def slider_to_spin(pos: int):
                val = _from_ratio(pos / 1000.0)
                self.editor.blockSignals(True)
                self.editor.setValue(val if is_float else int(val))
                self.editor.blockSignals(False)
                self._commit(val if is_float else int(val))

            if current is not None:
                c_val = float(current)
                self.editor.setValue(c_val if is_float else int(c_val))
                spin_to_slider(c_val)

            if not read_only:
                self.editor.valueChanged.connect(lambda v: (spin_to_slider(float(v)), self._commit(float(v) if is_float else int(v))))
                slider.valueChanged.connect(slider_to_spin)

            # Kept so :meth:`sync` can move the handle. Without it a value the
            # MODEL changed -- a playback tick, a fit result -- updates the spin
            # box and leaves the slider sitting where the user last dragged it,
            # and the two then disagree about the same number.
            self.slider = slider
            self._sync_slider = spin_to_slider

            layout.addWidget(slider, 1)
        elif section.kind == "int":
            self.editor = QtWidgets.QSpinBox()
            self.editor.setMinimum(
                int(section.minimum) if section.minimum is not None else -2_147_483_648
            )
            self.editor.setMaximum(
                int(section.maximum) if section.maximum is not None else 2_147_483_647
            )
            if section.step:
                self.editor.setSingleStep(int(section.step))
            if section.suffix:
                self.editor.setSuffix(section.suffix)
            if current is not None:
                self.editor.setValue(int(current))
            if not read_only:
                self.editor.valueChanged.connect(lambda v: self._commit(int(v)))
        elif section.kind == "float":
            use_scientific = (getattr(section, "style", "") == "scientific" or getattr(section, "scientific", False))
            if use_scientific:
                from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox
                min_v = float(section.minimum) if section.minimum is not None else 0.0
                max_v = float(section.maximum) if section.maximum is not None else 1e9
                step_v = float(section.step) if section.step else None
                dec_v = int(section.decimals) if section.decimals is not None else 4
                self.editor = ScientificDoubleSpinBox(
                    decimals=dec_v,
                    suffix=section.suffix or "",
                    value=float(current) if current is not None else 0.0,
                    bounds=[min_v, max_v],
                    step=step_v,
                )
                if not read_only:
                    self.editor.sigValueChanged.connect(lambda obj: self._commit(float(obj.value())))
            else:
                self.editor = QtWidgets.QDoubleSpinBox()
                self.editor.setDecimals(int(section.decimals))
                self.editor.setMinimum(
                    float(section.minimum) if section.minimum is not None else -1e308
                )
                self.editor.setMaximum(float(section.maximum) if section.maximum is not None else 1e308)
                if section.step:
                    self.editor.setSingleStep(float(section.step))
                if section.suffix:
                    self.editor.setSuffix(section.suffix)
                if current is not None:
                    self.editor.setValue(float(current))
                if not read_only:
                    self.editor.valueChanged.connect(lambda v: self._commit(float(v)))
        elif section.kind == "text":
            self.editor = _FocusOutPlainTextEdit()
            self.editor.setMinimumHeight(54)
            if section.placeholder:
                self.editor.setPlaceholderText(section.placeholder)
            if current is not None:
                self.editor.setPlainText(str(current))
            if not read_only:
                self.editor.editingFinished.connect(lambda: self._commit(self.editor.toPlainText()))
        elif section.kind == "date":
            self.editor = QtWidgets.QDateEdit()
            self.editor.setCalendarPopup(True)
            self.editor.setDisplayFormat("yyyy-MM-dd")
            self._set_date_from(current)
            if not read_only:
                self.editor.dateChanged.connect(lambda d: self._commit(d.toString("yyyy-MM-dd")))
        elif section.kind in ("password", "secret"):
            self.editor = QtWidgets.QLineEdit()
            self.editor.setEchoMode(QtWidgets.QLineEdit.Password)
            if section.placeholder:
                self.editor.setPlaceholderText(section.placeholder)
            if current is not None:
                self.editor.setText(str(current))
            if not read_only:
                self.editor.editingFinished.connect(lambda: self._commit(self.editor.text()))
        elif section.kind in ("file", "directory"):
            # ``directory`` differs from ``file`` only in which dialog the browse
            # button opens; both commit the typed path, so a folder can be pasted
            # in as well as picked.
            self.editor = QtWidgets.QLineEdit()
            if section.placeholder:
                self.editor.setPlaceholderText(section.placeholder)
            if current is not None:
                self.editor.setText(str(current))
            if not read_only:
                self.editor.editingFinished.connect(lambda: self._commit_file(self.editor.text()))
        elif section.kind == "expression":
            # A one-line equation, rendered by the shared ``ExpressionInput``:
            # the safe-AST validity badge, the reason in a tooltip, the typeset
            # preview and the names-and-functions reference. Those are exactly the
            # controls the hand-written parse editor had and no generated editor
            # did -- and reusing that widget is why the two cannot drift.
            from chisurf.gui.widgets.expression_input import ExpressionInput

            self.editor = ExpressionInput(
                placeholder=section.placeholder or "e.g.  a1*exp(-x/tau1)",
            )
            if current is not None:
                self.editor.set_text_silently(str(current))
            self.editor.setEnabled(not read_only)
            if not read_only:
                # Commit on Return (when valid) and on focus-out, matching every
                # other field: an equation half-typed must not reach the model.
                self.editor.committed.connect(self._commit)
                self.editor.installEventFilter(self)
        else:  # "str"
            self.editor = QtWidgets.QLineEdit()
            if section.placeholder:
                self.editor.setPlaceholderText(section.placeholder)
            if current is not None:
                self.editor.setText(str(current))
            if not read_only:
                self.editor.editingFinished.connect(lambda: self._commit(self.editor.text()))
        if read_only and section.kind != "expression":
            # ``expression`` is a composite widget, not an editor with a
            # ``setReadOnly``; it was disabled where it was built.
            self.editor.setReadOnly(True)
            if isinstance(self.editor, QtWidgets.QAbstractSpinBox):
                self.editor.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        # A ``text`` field flagged ``expand`` fills spare vertical space (e.g. a
        # JSON/log preview) instead of staying at its compact minimum height; the
        # form layout reads ``_autoform_expanding`` to hand it the stretch.
        if section.kind == "text" and getattr(section, "expand", False):
            self._autoform_expanding = True
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.editor.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
        if section.kind == "expression":
            # The pair takes a whole form row: packed two-up beside another field
            # the editor shrinks to showing its last few characters, which is not
            # a field anyone can read what they typed in.
            self._autoform_full_row = True
            layout.addWidget(self.editor, 1)
        else:
            layout.addWidget(self.editor, 1)
        if section.kind in ("file", "directory") and not read_only:
            browse = QtWidgets.QToolButton()
            browse.setText("…")
            browse.setToolTip("Browse…")
            browse.clicked.connect(self._browse_file)
            layout.addWidget(browse)
        # A "secret" field is a masked input with a reveal toggle (e.g. API keys),
        # while a plain "password" field stays masked with no reveal affordance.
        if section.kind == "secret":
            self.reveal = QtWidgets.QToolButton()
            self.reveal.setCheckable(True)
            self.reveal.setText(Glyphs.EYE)
            self.reveal.setToolTip("Show / hide")
            self.reveal.toggled.connect(self._toggle_secret)
            layout.addWidget(self.reveal)
        self._apply_tooltip(self, self.editor)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        """Commit an ``expression`` field when it loses focus.

        ``ExpressionInput`` emits ``committed`` on Return only. Without this a
        user who types an equation and clicks elsewhere loses it, which is not
        how any other field in the form behaves.
        """
        if (
            self._section.kind == "expression"
            and event.type() == QtCore.QEvent.FocusOut
            and not getattr(self._section, "read_only", False)
            and self.editor.is_valid()
        ):
            self._commit(self.editor.text())
        return super().eventFilter(obj, event)

    def _toggle_secret(self, checked: bool) -> None:
        """Reveal or mask a ``kind="secret"`` field's contents."""
        mode = QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        self.editor.setEchoMode(mode)

    def _commit_file(self, path: str) -> None:
        """Commit a file path only when it actually changed (avoids reloads)."""
        if path and path != str(self._current_value() or ""):
            self._commit(path)

    def _browse_file(self) -> None:
        if self._section.kind == "directory":
            path = QtWidgets.QFileDialog.getExistingDirectory(
                self, self._section.label or "Select folder"
            )
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, self._section.label or "Open file"
            )
        if path:
            self.editor.setText(path)
            self._commit_file(path)

    def _set_date_from(self, value) -> None:
        """Set the QDateEdit from an ISO ``yyyy-MM-dd`` string (or leave default)."""
        if not value:
            return
        date = QtCore.QDate.fromString(str(value)[:10], "yyyy-MM-dd")
        if date.isValid():
            self.editor.setDate(date)

    def sync(self) -> None:
        """Re-read the model value into the editor without firing signals."""
        cur = self._current_value()
        if cur is None:
            return
        self.editor.blockSignals(True)
        if isinstance(self.editor, QtWidgets.QSpinBox):
            self.editor.setValue(int(cur))
        elif isinstance(self.editor, QtWidgets.QDoubleSpinBox):
            self.editor.setValue(float(cur))
        elif isinstance(self.editor, QtWidgets.QPlainTextEdit):
            self.editor.setPlainText(str(cur))
        elif isinstance(self.editor, QtWidgets.QDateEdit):
            self._set_date_from(cur)
        elif isinstance(self.editor, QtWidgets.QLineEdit):
            self.editor.setText(str(cur))
        self.editor.blockSignals(False)
        sync_slider = getattr(self, "_sync_slider", None)
        if sync_slider is not None:
            sync_slider(float(cur))


# --- custom sections -------------------------------------------------------
@register_section("lifetime_amplitude_options")
class LifetimeAmplitudeOptions(QtWidgets.QWidget):
    """Header controls for a lifetime group: normalize / absolute amplitudes.

    This is the bespoke escape-hatch widget for the dynamic lifetime section.
    It edits the model's amplitude options through the action dispatcher, so the
    model remains the single source of truth and no widget reaches into compute.
    """

    def __init__(self, model=None, target: str = "lifetimes", parent=None, **options):
        super().__init__(parent)
        self._model = model
        self._group = getattr(model, target, None)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.absolute = QtWidgets.QCheckBox("Abs.")
        self.absolute.setToolTip("Take absolute value of amplitudes (no negative amplitudes).")
        self.absolute.setChecked(bool(getattr(self._group, "absolute_amplitudes", True)))
        self.absolute.clicked.connect(self._on_changed)

        self.normalize = QtWidgets.QCheckBox("Norm.")
        self.normalize.setToolTip("Normalize amplitudes so they sum to one.")
        self.normalize.setChecked(bool(getattr(self._group, "normalize_amplitudes", True)))
        self.normalize.clicked.connect(self._on_changed)

        # read/link menus (port of the legacy LifetimeWidget header controls).
        self.read_btn = QtWidgets.QToolButton()
        self.read_btn.setText("read")
        self.read_btn.setToolTip("Copy parameter values from another lifetime group.")
        self.read_menu = QtWidgets.QMenu(self.read_btn)
        self.read_menu.aboutToShow.connect(
            lambda: self._build_target_menu(self.read_menu, self._read_values)
        )
        self.read_btn.setMenu(self.read_menu)
        self.read_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        self.link_btn = QtWidgets.QToolButton()
        self.link_btn.setText("link")
        self.link_btn.setToolTip("Link this lifetime group to another (shared spectrum).")
        self.link_menu = QtWidgets.QMenu(self.link_btn)
        self.link_menu.aboutToShow.connect(
            lambda: self._build_target_menu(self.link_menu, self._link_to)
        )
        self.link_btn.setMenu(self.link_menu)
        self.link_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        layout.addWidget(self.absolute)
        layout.addWidget(self.normalize)
        layout.addWidget(self.read_btn)
        layout.addWidget(self.link_btn)

    # -- read / link ---------------------------------------------------------
    def _lifetime_groups(self):
        """Yield ``(fit_index, fit, group)`` for every lifetime group in all fits.

        Operates on parameter groups that carry amplitude and lifetime
        parameters (not widgets). ChiSurf's classic ``Lifetime`` group was the
        one kind; TCSPC models are now BFF-described views, whose lifetimes are
        description parameters, so an application-side group is recognised by
        what it holds rather than by a class that no longer exists.
        """
        try:
            from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

            fit_groups = get_fitting_client().get_fit_objects()
        except Exception:
            fit_groups = []
        idx = 0
        for fg in fit_groups:
            for fit in fg:
                for a in getattr(fit.model, "aggregated_parameters", []):
                    if hasattr(a, "_amplitudes") and hasattr(a, "_lifetimes"):
                        yield idx, fit, a
            idx += 1

    def _build_target_menu(self, menu, on_pick):
        """Populate ``menu`` with selectable target lifetime groups."""
        menu.clear()
        for _idx, fit, group in self._lifetime_groups():
            if group is self._group:
                continue
            action = menu.addAction(f"{fit.name}: {group.name}")
            action.triggered.connect(lambda _checked=False, g=group: on_pick(g))

    def _own_fit_index(self) -> int:
        """Return the index of this model's fit in ``chisurf.fits``, or ``-1``.

        ``-1`` means the bound model's fit is not registered with the fit
        machinery — a scripted or headless fit, or a tool with no fit at all.
        This used to answer ``0``, which is not "unknown" but *another fit*:
        against an empty list it raised, and against a populated one it would
        have dispatched the edit at whichever fit happened to be first.
        Fit-targeted dispatch is skipped for a negative index instead.
        """
        try:
            fit = getattr(self._model, "fit", None)
            for i, fg in enumerate(cs.fits):
                if fg is fit or fit in list(fg):
                    return i
        except Exception:
            pass
        return -1

    def _read_values(self, target):
        """Copy parameter values from ``target`` into this group via dispatch."""
        group = self._group
        if group is None:
            return
        fit_index = self._own_fit_index()
        try:
            target_params = target.parameters_all_dict
            for key in group.parameter_dict:
                if key in target_params:
                    cs.core.actions.dispatch(
                        name="parameter.value",
                        payload={
                            "parameter_name": str(key),
                            "value": float(target_params[key].value),
                            "fit_index": int(fit_index),
                        },
                    )
            _dispatch_fit_update(fit_index)
        except Exception as exc:
            logging.warning(f"Failed to read lifetime values: {exc}")

    def _link_to(self, target):
        """Link this group's spectrum to ``target`` and refresh the fit."""
        group = self._group
        if group is None:
            return
        try:
            group.link = target
            _dispatch_fit_update(self._own_fit_index())
        except Exception as exc:
            logging.warning(f"Failed to link lifetime group: {exc}")

    def _on_changed(self, *_):
        """Push amplitude-option changes to the model via the dispatcher."""
        group = self._group
        if group is None:
            return
        name = str(getattr(group, "name", "lifetimes"))
        try:
            cs.core.actions.dispatch(
                name="model.normalize_amplitudes",
                payload={"component_name": name, "normalize": bool(self.normalize.isChecked())},
            )
            cs.core.actions.dispatch(
                name="model.absolute_amplitudes",
                payload={"component_name": name, "absolute": bool(self.absolute.isChecked())},
            )
        except Exception as exc:  # pragma: no cover - dispatcher optional in tests
            logging.warning(f"Failed to dispatch amplitude options: {exc}")
            # Fallback: set directly on the model group.
            group.normalize_amplitudes = bool(self.normalize.isChecked())
            group.absolute_amplitudes = bool(self.absolute.isChecked())


class PlotWidget(QtWidgets.QWidget):
    """Inline plot section rendered from a declarative :class:`PlotSection`.

    Reads the data by calling ``getattr(model, section.source)()``, which must
    return a list of series mappings (``{"x", "y", "name", "color", "width",
    "style"}``, plus ``symbol``/``symbol_size``/``no_line`` for markers). Call
    :meth:`refresh` (e.g. via ``AutoForm.refresh_plots``) to re-read the source
    after the model changes.

    Rendering goes through :mod:`chisurf.gui.chiplot`, so every declarative plot
    in ChiSurf follows the backend seam rather than importing a plotting library
    (PRD-64). Anything chiplot cannot express belongs *in* chiplot: reaching
    past the seam here would silently opt every plugin's plot out of the
    migration at once.

    A section without an explicit ``height`` marks itself
    ``_autoform_expanding``, which is how the hosting panel knows to give it the
    spare vertical space. Without that marker the panel adds a trailing stretch
    that wins over the plot's own size policy and leaves it a few dozen pixels
    tall next to a form.
    """

    is_form_field = False

    def __init__(self, model, section, parent=None):
        super().__init__(parent)
        from chisurf.gui import chiplot as cp

        self._model = model
        self._section = section

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = cp.Plot()
        if section.height:
            self.plot.setMaximumHeight(int(section.height))
            self.plot.setMinimumHeight(int(section.height))
        else:
            # Without this, a panel mixing plots with form rows or info blocks
            # adds a trailing stretch that wins over the plot's own expanding
            # policy, leaving the plot a few dozen pixels tall.
            self._autoform_expanding = True
        self.plot.set_labels(left=section.y_label or None, bottom=section.x_label or None)
        if getattr(section, "log_x", False) or section.log_y:
            try:
                log_x = bool(getattr(section, "log_x", False))
                self.plot.set_log(x=log_x, y=bool(section.log_y))
                self._log_axes = tuple(
                    (("bottom",) if log_x else ()) + (("left",) if section.log_y else ())
                )
                self._thin_log_ticks()
                # Re-evaluate on zoom and pan: the right tick density depends on
                # how much of the axis is showing, not on how it was declared.
                self.plot.on_range_changed(lambda *_: self._thin_log_ticks())
            except Exception:
                pass
        if getattr(section, "invert_y", False):
            # Image coordinates: row 0 is the top row.
            self.plot.invert_y(True)
        if section.legend:
            self.plot.legend(offset=(-5, 5))
        self._apply_ranges()
        # Right-click menu (per-axis log/linear toggle, autoscale, export) is
        # on by default; a section can opt out with "context_menu": false.
        self.plot.set_menu_enabled(bool(getattr(section, "context_menu", True)))
        layout.addWidget(self.plot)
        if getattr(section, "description", ""):
            self.setToolTip(section.description)
        self.refresh()

    #: Log axes ("bottom" / "left") whose tick density is managed adaptively.
    _log_axes: tuple = ()

    def _thin_log_ticks(self) -> None:
        """Label a log axis once per decade while it spans several decades.

        pyqtgraph labels every minor tick (1, 2, 3 … 9 per decade) whenever it
        believes there is room, and its width estimate is wrong for the
        ``n·10^k`` strings: across three decades the ~27 labels overlap into an
        unreadable smear. Ticking once per decade is readable and is the natural
        unit of a log axis.

        It has to be conditional. Forcing decade ticks permanently would leave
        an axis zoomed into less than one decade with no ticks at all, so the
        automatic spacing is restored as soon as the view is that narrow — which
        is why this is re-run on every range change rather than set once.
        """
        try:
            x_range, y_range = self.plot.get_range()
            for name in self._log_axes:
                lo, hi = x_range if name == "bottom" else y_range
                decades = abs(float(hi) - float(lo))  # already in log10 units
                if decades >= 2.0:
                    self.plot.set_tick_spacing(name, major=1.0, minor=1.0)
                else:
                    self.plot.set_tick_spacing(name)  # back to automatic
        except Exception:  # pragma: no cover - cosmetic only, never fatal
            pass

    def _apply_ranges(self) -> None:
        """Pin the axes to the ranges the spec declares (if any).

        A declared range keeps the view on the quantity's natural domain — an
        efficiency lives in 0…1 — so a few divide-by-almost-zero outliers cannot
        squeeze the interesting data into a line.
        """
        for axis, bounds in (("x", getattr(self._section, "x_range", ())),
                             ("y", getattr(self._section, "y_range", ()))):
            if bounds and len(bounds) == 2:
                try:
                    setter = self.plot.set_xlim if axis == "x" else self.plot.set_ylim
                    setter(float(bounds[0]), float(bounds[1]), padding=0.0)
                except Exception:
                    pass

    def refresh(self) -> None:
        """Re-read the section's source method and redraw all series."""
        source = getattr(self._model, self._section.source, None)
        if source is None:
            return
        try:
            series = (source() if callable(source) else source) or []
        except Exception as exc:  # pragma: no cover - source is model-defined
            logging.warning(f"PlotWidget: source {self._section.source!r} failed: {exc}")
            return
        self.plot.clear()
        for s in series:
            color = s.get("color", "y")
            kw = {
                "pen": color,
                "width": int(s.get("width", 1)),
                "style": s.get("style", "solid"),
                "name": s.get("name", "") or None,
            }
            if s.get("symbol"):
                kw["symbol"] = s["symbol"]
                kw["symbol_brush"] = color
                kw["symbol_size"] = int(s.get("symbol_size", 9))
                if s.get("no_line"):
                    # Markers only: a transparent pen leaves the points unjoined.
                    kw["pen"] = (0, 0, 0, 0)
            self.plot.line(s.get("x", []), s.get("y", []), **kw)
        self._apply_axes()
        self._apply_ranges()

    def _apply_axes(self) -> None:
        """Apply the data-dependent axis labels and scales, when declared.

        A plot whose source can hand back different *quantities* — one artifact a
        correlation in milliseconds, the next a decay in nanoseconds — cannot
        state its axes in the spec, and labelling both "x" is exactly how a lag
        axis gets read as a time axis.
        """
        name = getattr(self._section, "axes_source", "")
        if not name:
            return
        source = getattr(self._model, name, None)
        if source is None:
            logging.warning(f"PlotWidget: axes_source {name!r} is not on the model")
            return
        try:
            axes = (source() if callable(source) else source) or {}
        except Exception as exc:  # pragma: no cover - source is model-defined
            logging.warning(f"PlotWidget: axes_source {name!r} failed: {exc}")
            return
        if not isinstance(axes, dict):
            return
        if "x_label" in axes or "y_label" in axes:
            self.plot.set_labels(
                bottom=axes.get("x_label") or self._section.x_label or None,
                left=axes.get("y_label") or self._section.y_label or None,
            )
        if "log_x" in axes or "log_y" in axes:
            log_x = bool(axes.get("log_x", getattr(self._section, "log_x", False)))
            log_y = bool(axes.get("log_y", self._section.log_y))
            self.plot.set_log(x=log_x, y=log_y)
            self._log_axes = tuple((("bottom",) if log_x else ()) + (("left",) if log_y else ()))
            self._thin_log_ticks()

class LCurveWidget(QtWidgets.QWidget):
    """Reusable L-curve view (residual vs solution norm, log-log, corner marked).

    The general, declarative L-curve component: any model holding a
    :class:`chisurf.core.math.regularization.LCurveData` (as an attribute or a
    zero-arg method named by ``target``) can show it with a ``custom`` section::

        {"type": "custom", "key": "lcurve", "target": "lcurve_data", "title": "L-curve"}

    The corner (auto-selected regularization weight) is highlighted.

    A model that can *sample* its own L-curve adds the sweep controls
    declaratively, so picking the weight happens where the curve is drawn rather
    than in a bespoke plot class::

        {"type": "custom", "key": "lcurve", "target": "l_curve", "options": {
            "compute_action": "compute_l_curve",
            "select_action": "set_reg_from_lcurve_index",
            "log10_min": -6.0, "log10_max": 3.0, "n_points": 32}}

    ``compute_action`` names a model method taking ``n_points``/``log10_min``/
    ``log10_max``; ``select_action`` names one taking the index of a swept point,
    which is what a click on the curve commits. Without either option the widget
    is the read-only view it has always been.
    """

    #: marker so :meth:`AutoForm.refresh_plots` re-reads this widget.
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str, **options):
        from chisurf.gui import chiplot as cp

        super().__init__()
        self._model = model
        self._target = target
        self._opts = options
        self._plot = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._plot = cp.Plot()
        self._plot.set_log(x=True, y=True)
        self._plot.set_labels(
            bottom=options.get("x_label", "residual norm"),
            left=options.get("y_label", "solution norm"),
        )
        # An L-curve descends left to right, so a top-left legend lands on it.
        self._plot.legend(offset=(-30, 30))
        # Both axes are decades already; an SI multiplier on top of that prints
        # "chi2r (x0.001)" over ticks that read 0.001 … 10 and contradicts them.
        self._plot.set_si_prefix(x=False, y=False)
        # An empty L-curve is a large black rectangle; capped, it stays a panel
        # in a stack of parameter tables rather than pushing them off screen.
        self._plot.setMinimumHeight(int(options.get("min_height", 160)))
        self._plot.setMaximumHeight(int(options.get("max_height", 260)))
        lay.addWidget(self._plot)

        if options.get("compute_action") or options.get("select_action"):
            lay.addWidget(self._build_controls())
        if options.get("select_action"):
            self._plot.clicked.connect(self._on_plot_clicked)

        self.refresh()

    def _build_controls(self) -> QtWidgets.QWidget:
        """Build the sweep window + compute row shown when the model can sample."""
        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        def _spin(value, lo, hi, step, decimals=None):
            box = (
                QtWidgets.QSpinBox() if decimals is None else QtWidgets.QDoubleSpinBox()
            )
            if decimals is not None:
                box.setDecimals(decimals)
            box.setRange(lo, hi)
            box.setSingleStep(step)
            box.setValue(value)
            return box

        self._sb_min = _spin(float(self._opts.get("log10_min", -3.0)), -12.0, 12.0, 0.5, 2)
        self._sb_max = _spin(float(self._opts.get("log10_max", 0.0)), -12.0, 12.0, 0.5, 2)
        self._sb_n = _spin(int(self._opts.get("n_points", 32)), 2, 256, 2)
        for label, box in (("min", self._sb_min), ("max", self._sb_max), ("N", self._sb_n)):
            lay.addWidget(QtWidgets.QLabel(label))
            lay.addWidget(box)

        if self._opts.get("compute_action"):
            btn = QtWidgets.QToolButton()
            btn.setText("⟳ sweep")
            btn.setToolTip(
                "Sample the regularization weight over the range above and redraw the "
                "L-curve. The corner is the weight balancing misfit against smoothness."
            )
            btn.clicked.connect(self._on_compute)
            lay.addWidget(btn)

            corner_btn = QtWidgets.QToolButton()
            corner_btn.setText("⌾ corner")
            corner_btn.setToolTip("Adopt the weight at the detected corner.")
            corner_btn.clicked.connect(self._on_use_corner)
            lay.addWidget(corner_btn)
        lay.addStretch(1)
        return row

    def _data(self):
        obj = getattr(self._model, self._target, None)
        return obj() if callable(obj) else obj

    def _on_compute(self) -> None:
        """Run the model's sweep over the window in the controls, then redraw."""
        fn = getattr(self._model, str(self._opts.get("compute_action")), None)
        if not callable(fn):
            logging.warning(
                f"LCurveWidget: compute_action {self._opts.get('compute_action')!r} "
                f"is not a method of {type(self._model).__name__}"
            )
            return
        lo, hi = float(self._sb_min.value()), float(self._sb_max.value())
        fn(n_points=int(self._sb_n.value()), log10_min=min(lo, hi), log10_max=max(lo, hi))
        self.refresh()

    def _on_use_corner(self) -> None:
        """Commit the detected corner through ``select_action``."""
        data = self._data()
        idx = getattr(data, "corner_index", None) if data is not None else None
        if idx is not None:
            self._select(int(idx))

    def _select(self, idx: int) -> None:
        """Commit a swept point by index and redraw the selection marker."""
        fn = getattr(self._model, str(self._opts.get("select_action")), None)
        if callable(fn):
            fn(int(idx))
        self.refresh()

    def _on_plot_clicked(self, x: float, y: float) -> None:
        """Commit the swept point nearest the click, in log-log screen terms.

        The axes are logarithmic, so nearest must be measured in decades — in
        linear distance the low-misfit end of the curve swallows every click.
        """
        import numpy as np

        data = self._data()
        if data is None or len(getattr(data, "reg", ())) == 0:
            return
        rho = np.asarray(data.residual_norm, dtype=float)
        eta = np.asarray(data.solution_norm, dtype=float)
        ok = np.isfinite(rho) & np.isfinite(eta) & (rho > 0) & (eta > 0)
        if not ok.any() or x <= 0 or y <= 0:
            return
        d = np.full(rho.shape, np.inf)
        d[ok] = (np.log10(rho[ok]) - np.log10(x)) ** 2 + (
            np.log10(eta[ok]) - np.log10(y)
        ) ** 2
        self._select(int(np.argmin(d)))

    def refresh(self) -> None:
        """Re-read the model's :class:`LCurveData` and redraw."""
        import numpy as np

        from chisurf.gui import chiplot as cp

        if self._plot is None:
            return
        self._plot.clear()
        data = self._data()
        if data is None or getattr(data, "reg", None) is None or len(data.reg) == 0:
            return
        self._plot.line(
            np.asarray(data.residual_norm, dtype=float),
            np.asarray(data.solution_norm, dtype=float),
            pen=cp.to_pen("c", width=2),
            symbol="o",
            symbol_size=5,
            symbol_brush="c",
            name="L-curve",
        )
        corner = getattr(data, "corner_point", None)
        if corner is not None:
            self._plot.scatter(
                [corner[0]], [corner[1]], symbol="o", size=12, brush="r", pen="r",
                name="chosen",
            )


@register_section("lcurve")
def _lcurve_section_factory(model, target: str, **options):
    """Custom-section factory rendering a model's ``LCurveData`` (see :class:`LCurveWidget`)."""
    return LCurveWidget(model, target, **options)


#: Matplotlib colormaps offered by the general image widget's colour selector.
IMAGE_COLORMAPS = ["viridis", "magma", "inferno", "plasma", "cividis", "turbo", "gray"]


def apply_colormap(image_view, name: str) -> None:
    """Apply a (matplotlib) colormap by name to a pyqtgraph ImageView, best-effort.

    Reusable by any pyqtgraph image plot (AutoForm or not) so the colour handling is
    consistent across tools (2D-FLC, RICS, PDA, ...).
    """
    try:
        import pyqtgraph as pg

        try:
            cmap = pg.colormap.get(name, source="matplotlib")
        except Exception:
            cmap = pg.colormap.get(name)
        image_view.setColorMap(cmap)
    except Exception:  # pragma: no cover - colormap optional
        pass


class ImageMapWidget(QtWidgets.QWidget):
    """General image dock bound to ``model.<target>()``.

    Optional colour selection, brush/draw, 3D stack browsing and click-to-pick
    selection.

    Declare it in a view.json as a ``custom`` section so any tool can show a map::

        {"type": "custom", "key": "image", "target": "spectrum_image", "title": "Map",
         "options": {"colormap": true, "colormap_attr": "colormap"}}

    The image source may be 2D ``(y, x)`` or 3D ``(z, y, x)``; a 3D array is shown
    with pyqtgraph's built-in z-slider (axis 0 = slice) and the current slice is
    preserved across refreshes.

    The colour control lives *in the plot* (a small combo above the image), so it is
    portable and needs no separate settings panel. Colour ``options``:

    * ``colormap`` (bool) — show the embedded colormap selector (default ``False``).
    * ``default_colormap`` (str) — initial colormap (default ``"viridis"``).
    * ``colormap_attr`` (str) — optional model attribute to read/write the chosen colormap,
      so it persists and can be shared between several image docks.

    Detector-channel ``options`` add an in-plot selector so one map dock can switch
    between detector windows / channels (green/red/…) without a separate panel:

    * ``channel_source`` (str) — model method returning the list of channel/window names.
    * ``channel_attr`` (str) — model attribute that receives the picked name.
    * ``channel_call`` (str) — model method called after a pick (e.g. ``refresh_display``);
      called as ``fn(name)`` when it accepts an argument, else ``fn()``. Several docks
      bound to the same attr stay in sync (each re-syncs its combo on refresh).

    Movie ``options`` add frame-playback controls for a 3D ``(frame, y, x)`` stack
    (the existing z-slider scrubs; these animate it):

    * ``movie`` (bool) — show play/pause + loop + stop buttons and an fps selector
      (default ``False``). The controls auto-disable when the current image is 2D.
    * ``movie_fps`` (int) — initial playback speed (default ``10``).
      ``False`` keeps the ``{x:2, y:1}`` mapping the PSF stack picker relies on).

    Brush / draw ``options`` turn the dock into a paintable pixel selector (e.g. for
    CLSM pixel selection, FLIM masks, ROI painting). Brush mode is enabled when
    ``selection_attr`` is given:

    * ``selection_attr`` (str) — model attribute holding the 2D selection mask; the
      widget reads it on refresh and writes it back while painting.
    * ``brush_kernel_source`` (str) — model method returning the draw kernel (so the
      tool owns brush size/shape/erase); falls back to a 1×1 kernel.
    * ``on_draw`` (str) — model method called after a stroke (e.g. to recompute a decay).
    * ``live_attr`` (str) — model attribute (bool) gating ``on_draw`` during a drag.

    Point-pick / overlay ``options`` (independent of brush mode) let a tool select a
    single point in the image (e.g. a bead in a PSF stack) and draw overlays:

    * ``select_attr`` (str) — model attribute that receives the picked ``(z, y, x)``
      tuple on a left-click (``z`` is the current slice; ``0`` for a 2D image). A red
      marker is drawn at the pick.
    * ``on_pick`` (str) — model method called after a pick (e.g. to fit the bead).
    * ``markers_source`` (str) — model method returning a list of ``(z, y, x)``
      points; those on the current slice are drawn as green square markers.
    * ``extent_source`` (str) — model method returning ``(x0, x1, y0, y1)``, the
      real-world span the image covers. Without it the axes are pixel indices;
      with it they carry the quantity, so a region drawn on the plane is already
      in the units the analysis gates with.
    * ``roi_source`` (str) — model method returning ``{"x", "y", "r", "z"}`` (or
      ``None``); draws a non-interactive yellow circle of radius ``r`` at ``(x, y)``
      when the current slice matches ``z``.

    Rectangle-gate ``options`` add a *draggable, resizable* rectangle on the image
    (e.g. gating a population in a 2-D intensity histogram):

    * ``region_call`` (str) — model method called ``fn(roi)`` with a
      :class:`~chisurf.core.roi.RectangleROI` in image index coordinates
      whenever the user finishes moving or resizing the rectangle. Setting this
      option is what enables the rectangle. Handing over a region rather than
      four floats is what lets the model store it, serialise it, combine it with
      other selections, or use it to mask an image — a gate drawn on a 2-D
      histogram and a region drawn on a frame are the same object.
    * ``region_source`` (str) — model method returning a
      :class:`~chisurf.core.roi.ROI` (or ``None``) used to place the rectangle;
      any region works, its bounding box is taken. Without it the rectangle
      starts on the central quarter of the image.

    Axis ``options``:

    * ``invert_y`` (bool) — keep the image convention with the origin at the top
      left (default ``True``). Set ``False`` for images that are really plots
      (e.g. a 2-D intensity histogram), so the second axis grows upwards.
    * ``aspect_locked`` (bool) — keep square pixels (default ``True``). Set
      ``False`` for images that are really plots: a 2-D histogram whose axes are a
      probability and a nanosecond has no reason to be square, and locking it
      renders the map as a narrow strip in an otherwise empty panel.
    * ``axes_visible`` (bool) — draw ticks and labels (default ``False``). The
      renderer's image view has no axes at all by default, which is fine for a
      picture of a detector and useless for a map whose axes carry the quantities
      being fitted.
    * ``x_label`` / ``y_label`` (str) — axis labels, used with ``axes_visible``.
    """

    #: marker so :meth:`AutoForm.refresh_plots` re-reads this widget.
    AUTOFORM_REFRESH = True

    def __init__(
        self,
        model,
        target: str,
        *,
        colormap: bool = False,
        default_colormap: str = "viridis",
        colormap_attr: str | None = None,
        channel_source: str | None = None,
        channel_attr: str | None = None,
        channel_call: str | None = None,
        movie: bool = False,
        movie_fps: int = 10,
        selection_attr: str | None = None,
        brush_kernel_source: str | None = None,
        on_draw: str | None = None,
        live_attr: str | None = None,
        select_attr: str | None = None,
        on_pick: str | None = None,
        markers_source: str | None = None,
        extent_source: str | None = None,
        labels_source: str | None = None,
        roi_source: str | None = None,
        region_call: str | None = None,
        region_source: str | None = None,
        invert_y: bool = True,
        aspect_locked: bool = True,
        axes_visible: bool = False,
        x_label: str = "",
        y_label: str = "",
        **options,
    ):
        super().__init__()
        self._model = model
        self._target = target
        self._cmap_attr = colormap_attr
        self._cmap = default_colormap
        self._image = None
        self._combo = None
        # detector-channel / window selector (in-plot combo)
        self._channel_source = channel_source
        self._channel_attr = channel_attr
        self._channel_call = channel_call
        self._channel_combo = None
        # movie / frame playback (for 3D stacks)
        self._movie = bool(movie)
        self._movie_fps = int(movie_fps)
        # When True, a 3D stack uses the SAME axis mapping as the 2D path, so a
        # movie dock and its sibling 2D map docks render at identical orientation
        # (the default {x:2,y:1} transposes the frame vs the 2D default {x:0,y:1}).
        self._play_btn = None
        self._loop_btn = None
        self._stop_btn = None
        self._fps_spin = None
        self._playing = False
        self._play_timer = None  # looping playback timer (wrap-around)
        # brush state
        self._selection_attr = selection_attr
        self._brush_kernel_source = brush_kernel_source
        self._on_draw = on_draw
        self._live_attr = live_attr
        self._overlay = None
        # point-pick / overlay state
        self._select_attr = select_attr
        self._on_pick = on_pick
        self._markers_source = markers_source
        self._labels_source = labels_source
        self._roi_source = roi_source
        self._pick_marker = None
        self._marker_items = []
        self._label_items = []
        self._roi_item = None
        self._extent_source = extent_source
        self._applied_extent = None
        # interactive rectangle gate
        self._region_call = region_call
        self._region_source = region_source
        self._rect_roi = None
        self._rect_placed = False
        self._ndim = 2
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        if colormap or self._channel_source or self._movie:
            lay.addLayout(self._build_bar(colormap))
        try:
            import pyqtgraph as pg

            # A plot needs readable axes. ``pg.ImageView`` defaults to a bare
            # ViewBox, which has none — fine for a picture of a detector, useless
            # for a 2-D histogram whose axes carry the quantities being fitted.
            # Hosting a ``PlotItem`` gives it ticks and labels; the rest of this
            # widget works against ``getView()`` either way.
            self._image = pg.ImageView(view=pg.PlotItem()) if axes_visible else pg.ImageView()
            # pyqtgraph's default for a 2-D array maps axis 0 to *x*, i.e. it
            # draws the transpose of what numpy holds — while everything else in
            # this widget is written the other way round: markers are placed at
            # ``(x, y) = (col, row)``, clicks are bounds-checked against
            # ``shape[:2]`` as ``(ny, nx)``, the rectangle gate builds a
            # ``RectangleROI`` whose x is a column, and the 3-D path already
            # passes ``axes={'x': 2, 'y': 1}``. Only the 2-D display disagreed,
            # so markers and picks landed transposed on every 2-D map. Row-major
            # makes the widget agree with itself, with numpy and with the ROI
            # subsystem.
            self._image.getImageItem().setOpts(axisOrder="row-major")
            self._image.ui.roiBtn.hide()
            self._image.ui.menuBtn.hide()
            if not invert_y:
                # Plot-like images (2-D histograms) read bottom-up, not top-down.
                self._image.getView().invertY(False)
            if axes_visible:
                view = self._image.getView()
                if x_label:
                    view.setLabel("bottom", x_label)
                if y_label:
                    view.setLabel("left", y_label)
                for side in ("bottom", "left"):
                    axis = view.getAxis(side)
                    if axis is not None:
                        # A ratio and a nanosecond have no unit to prefix, so an
                        # automatic SI prefix relabels a 0-to-1 axis "(x0.001)".
                        axis.enableAutoSIPrefix(False)
            if not aspect_locked:
                # A picture of something has square pixels; a *plot* does not. A
                # 2-D histogram whose axes are a probability (0 to 1) and a
                # nanosecond (0 to 8) drawn with a locked aspect comes out as a
                # narrow vertical strip in the middle of an empty panel.
                self._image.getView().setAspectLocked(False)
            lay.addWidget(self._image, 1)
            if self._selection_attr:
                self._setup_brush(pg)
            if self._select_attr or self._on_pick:
                self._image.getView().scene().sigMouseClicked.connect(self._on_clicked)
            if self._region_call:
                self._setup_rect_roi(pg)
            if self._markers_source or self._roi_source or self._labels_source:
                self._connect_slice_changed()
        except Exception:  # pragma: no cover - pyqtgraph optional
            lay.addWidget(QtWidgets.QLabel("pyqtgraph not available"))

    # ── top control bar (channel selector · movie · colormap) ──────────
    def _build_bar(self, colormap: bool) -> QtWidgets.QHBoxLayout:
        """Build the in-plot control bar (detector channel · movie · colormap)."""
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        # left: detector-channel / window selector
        if self._channel_source:
            bar.addWidget(QtWidgets.QLabel("channel"))
            self._channel_combo = QtWidgets.QComboBox()
            self._channel_combo.setToolTip("Detector channel / window shown in this map")
            self._reload_channels()
            self._channel_combo.currentTextChanged.connect(self._on_channel)
            bar.addWidget(self._channel_combo)
        bar.addStretch(1)
        # middle: movie / frame playback (enabled only for 3D stacks)
        if self._movie:
            self._play_btn = QtWidgets.QToolButton()
            self._play_btn.setText("▶")
            self._play_btn.setToolTip("Play the frame stack (stops at the last frame)")
            self._play_btn.clicked.connect(self._on_play_clicked)
            bar.addWidget(self._play_btn)
            self._loop_btn = QtWidgets.QToolButton()
            self._loop_btn.setText(Glyphs.LOOP)
            self._loop_btn.setCheckable(True)
            self._loop_btn.setChecked(True)  # loop by default
            self._loop_btn.setToolTip("Loop playback (wrap around at the end)")
            bar.addWidget(self._loop_btn)
            self._stop_btn = QtWidgets.QToolButton()
            self._stop_btn.setText("⏹")
            self._stop_btn.setToolTip("Stop and return to the first frame")
            self._stop_btn.clicked.connect(self._on_stop_clicked)
            bar.addWidget(self._stop_btn)
            self._fps_spin = QtWidgets.QSpinBox()
            self._fps_spin.setRange(1, 120)
            self._fps_spin.setValue(self._movie_fps)
            self._fps_spin.setSuffix(" fps")
            self._fps_spin.setToolTip("Playback speed (frames per second)")
            self._fps_spin.valueChanged.connect(self._on_fps)
            bar.addWidget(self._fps_spin)
            self._set_movie_enabled(False)
        # right: colormap selector
        if colormap:
            bar.addWidget(QtWidgets.QLabel("colormap"))
            self._combo = QtWidgets.QComboBox()
            self._combo.addItems(IMAGE_COLORMAPS)
            self._combo.setToolTip("Colormap for this image")
            cur = self._current_cmap()
            idx = self._combo.findText(cur)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
            self._combo.currentTextChanged.connect(self._on_cmap)
            bar.addWidget(self._combo)
        return bar

    # ── detector-channel / window selector ─────────────────────────────
    def _channel_names(self) -> list[str]:
        """Return the selectable channel/window names from the model source."""
        fn = getattr(self._model, self._channel_source, None) if self._channel_source else None
        try:
            names = list(fn()) if callable(fn) else []
        except Exception:  # pragma: no cover - model-defined
            names = []
        return [str(n) for n in names]

    def _reload_channels(self) -> None:
        """(Re)populate the channel combo from the model, syncing to the bound attr."""
        if self._channel_combo is None:
            return
        names = self._channel_names()
        cur = str(getattr(self._model, self._channel_attr, "")) if self._channel_attr else ""
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        self._channel_combo.addItems(names)
        i = self._channel_combo.findText(cur)
        if i >= 0:
            self._channel_combo.setCurrentIndex(i)
        self._channel_combo.blockSignals(False)

    def _on_channel(self, name: str) -> None:
        """Write the picked channel to the model and trigger its refresh."""
        if self._channel_attr and hasattr(self._model, self._channel_attr):
            setattr(self._model, self._channel_attr, name)
        if self._channel_call:
            fn = getattr(self._model, self._channel_call, None)
            if callable(fn):
                try:
                    fn(name)
                except TypeError:
                    fn()
                except Exception:  # pragma: no cover - model-defined
                    logging.warning(f"ImageMapWidget: channel_call {self._channel_call!r} failed")
        # Redraw. The widget has just changed *what it should be showing*, so
        # keeping the old picture on screen is its own bug — it does not depend on
        # whether the model happens to have a hook that repaints. Tools whose
        # ``channel_call`` already refreshes simply refresh twice, which is cheap
        # and idempotent; without this, a model that only stores the choice (a
        # fitting model, say, which cannot reach the widget at all) left the
        # selector showing one channel and the image showing another.
        try:
            self.refresh()
        except Exception:  # pragma: no cover - defensive
            logging.warning("ImageMapWidget: refresh after a channel change failed")

    # ── movie / frame playback ─────────────────────────────────────────
    def _set_movie_enabled(self, on: bool) -> None:
        for w in (self._play_btn, self._loop_btn, self._stop_btn, self._fps_spin):
            if w is not None:
                w.setEnabled(bool(on))
        if not on:
            self._stop_play()

    def _toggle_play(self) -> None:
        self._stop_play() if self._playing else self._start_play()

    def _on_play_clicked(self) -> None:
        """Play/pause the frame stack."""
        self._stop_play() if self._playing else self._start_play()

    def _on_stop_clicked(self) -> None:
        """Stop playback and return to the first frame."""
        self._stop_play()
        if self._image is not None:
            try:
                self._image.setCurrentIndex(0)
            except Exception:  # pragma: no cover - pyqtgraph optional
                pass

    def _start_play(self) -> None:
        # Own timer (not ImageView.play) so playback loops (wrap-around) instead
        # of stopping at the last frame.
        if self._image is None:
            return
        fps = int(self._fps_spin.value()) if self._fps_spin else self._movie_fps
        if fps <= 0:
            return
        if self._play_timer is None:
            self._play_timer = QtCore.QTimer(self)
            self._play_timer.timeout.connect(self._advance_frame)
        self._play_timer.start(int(1000 / max(fps, 1)))
        self._playing = True
        if self._play_btn is not None:
            self._play_btn.setText("⏸")

    def _advance_frame(self) -> None:
        """Advance one frame; wrap to the start when Loop is on, else stop at the end."""
        if self._image is None:
            return
        try:
            data = getattr(self._image, "image", None)
            n = int(data.shape[0]) if data is not None and getattr(data, "ndim", 0) >= 3 else 0
            if n <= 1:
                return
            idx = int(self._image.currentIndex) + 1
            loop = self._loop_btn.isChecked() if self._loop_btn is not None else True
            if idx >= n:
                if not loop:
                    self._stop_play()
                    return
                idx = 0
            self._image.setCurrentIndex(idx)
        except Exception:  # pragma: no cover - pyqtgraph optional
            pass

    def _stop_play(self) -> None:
        if self._play_timer is not None:
            self._play_timer.stop()
        self._playing = False
        if self._play_btn is not None:
            self._play_btn.setText("▶")

    def _on_fps(self, value: int) -> None:
        if self._playing:
            self._start_play()  # restart at the new rate

    # ── colormap ───────────────────────────────────────────────────────
    def _current_cmap(self) -> str:
        if self._cmap_attr:
            return str(getattr(self._model, self._cmap_attr, self._cmap))
        return self._cmap

    def _on_cmap(self, name: str) -> None:
        self._cmap = name
        if self._cmap_attr and hasattr(self._model, self._cmap_attr):
            setattr(self._model, self._cmap_attr, name)
        if self._image is not None:
            apply_colormap(self._image, name)

    # ── brush / draw ───────────────────────────────────────────────────
    def _setup_brush(self, pg) -> None:
        """Add a paintable selection overlay on top of the image."""
        self._overlay = pg.ImageItem()
        # Same axis order as the image underneath, or a stroke would land on the
        # transposed pixel. The mask handed to ``selection_attr`` is the item's
        # own array either way, so its ``(row, col)`` meaning is unchanged.
        self._overlay.setOpts(axisOrder="row-major")
        self._overlay.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        self._image.getView().addItem(self._overlay)
        self._overlay.hoverEvent = self._hover_event
        self._overlay.mouseDragEvent = self._draw_event
        self._apply_kernel()

    def _apply_kernel(self) -> None:
        if self._overlay is None:
            return
        import numpy as np

        kernel = None
        if self._brush_kernel_source:
            fn = getattr(self._model, self._brush_kernel_source, None)
            if callable(fn):
                try:
                    kernel = np.asarray(fn())
                except Exception:  # pragma: no cover - defensive
                    kernel = None
        if kernel is None:
            kernel = np.ones((1, 1))
        cx, cy = kernel.shape[0] // 2, kernel.shape[1] // 2
        self._overlay.setDrawKernel(kernel, mask=kernel, center=(cx, cy), mode="add")

    def _live(self) -> bool:
        if self._live_attr:
            return bool(getattr(self._model, self._live_attr, True))
        return True

    def _hover_event(self, event) -> None:
        if self._image is None:
            return
        base = self._image.getImageItem().image
        if base is None or event.isExit():
            self._image.getView().setToolTip("")
            return
        pos = event.pos()
        i = int(max(0, min(pos.y(), base.shape[0] - 1)))
        j = int(max(0, min(pos.x(), base.shape[1] - 1)))
        self._image.getView().setToolTip(f"pixel ({i}, {j}) = {base[i, j]:g}")

    def _draw_event(self, event) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        event.accept()
        if event.isStart():
            self._apply_kernel()
        self._overlay.drawAt(event.pos(), event)
        if self._selection_attr:
            import numpy as np

            setattr(self._model, self._selection_attr, np.asarray(self._overlay.image))
        if self._on_draw and self._live():
            fn = getattr(self._model, self._on_draw, None)
            if callable(fn):
                fn()

    # ── point pick / overlays ──────────────────────────────────────────
    def _current_z(self) -> int:
        """Return the currently displayed slice index (0 for a 2D image)."""
        if self._ndim < 3 or self._image is None:
            return 0
        try:
            return int(self._image.currentIndex)
        except Exception:
            return 0

    def _connect_slice_changed(self) -> None:
        """Redraw per-slice markers/ROI when the z-slider moves."""
        try:
            self._image.timeLine.sigPositionChanged.connect(self._redraw_overlays)
        except Exception:
            try:
                self._image.sigTimeChanged.connect(self._redraw_overlays)
            except Exception:
                pass

    def _on_clicked(self, event) -> None:
        """Left-click in the image → write ``(z, y, x)`` and call ``on_pick``."""
        if self._image is None:
            return
        item = self._image.getImageItem()
        scene_pos = event.scenePos()
        if not item.sceneBoundingRect().contains(scene_pos):
            return
        point = item.mapFromScene(scene_pos)
        x, y = int(point.x()), int(point.y())
        z = self._current_z()
        base = item.image
        if base is not None:
            ny, nx = base.shape[:2]
            if not (0 <= x < nx and 0 <= y < ny):
                return
        if self._select_attr:
            try:
                setattr(self._model, self._select_attr, (z, y, x))
            except Exception:  # pragma: no cover - defensive
                logging.warning(f"ImageMapWidget: could not set {self._select_attr!r}")
        if self._on_pick:
            fn = getattr(self._model, self._on_pick, None)
            if callable(fn):
                try:
                    fn()
                except Exception:  # pragma: no cover - model-defined
                    logging.warning(f"ImageMapWidget: on_pick {self._on_pick!r} failed")
        self._redraw_overlays()

    def _redraw_overlays(self, *args) -> None:
        """Redraw pick marker, per-slice detected-point markers and the ROI circle."""
        if self._image is None:
            return
        import pyqtgraph as pg

        view = self._image.getView()
        z = self._current_z()

        # detected-point markers (green squares) on the current slice
        for m in self._marker_items:
            view.removeItem(m)
        self._marker_items = []
        if self._markers_source:
            fn = getattr(self._model, self._markers_source, None)
            pts = fn() if callable(fn) else None
            if pts:
                xs = [int(p[2]) for p in pts if int(p[0]) == z]
                ys = [int(p[1]) for p in pts if int(p[0]) == z]
                if xs:
                    marker = pg.ScatterPlotItem(
                        xs,
                        ys,
                        pen=pg.mkPen("g", width=1),
                        brush=pg.mkBrush(0, 255, 0, 120),
                        size=8,
                        symbol="s",
                    )
                    marker.setZValue(5)
                    view.addItem(marker)
                    self._marker_items.append(marker)

        # free text labels (e.g. mosaic tile names) on the current slice
        for m in self._label_items:
            view.removeItem(m)
        self._label_items = []
        if self._labels_source:
            fn = getattr(self._model, self._labels_source, None)
            labels = fn() if callable(fn) else None
            for lab in labels or []:
                if isinstance(lab, dict):
                    lz, ly, lx = int(lab.get("z", 0)), float(lab["y"]), float(lab["x"])
                    text = str(lab.get("text", ""))
                elif len(lab) == 4:
                    lz, ly, lx, text = int(lab[0]), float(lab[1]), float(lab[2]), str(lab[3])
                else:
                    lz, ly, lx, text = 0, float(lab[0]), float(lab[1]), str(lab[2])
                if lz != z:
                    continue
                item = pg.TextItem(text=text, color=(255, 255, 255))
                item.setAnchor((0, 0))
                item.setPos(lx, ly)
                item.setZValue(6)
                view.addItem(item)
                self._label_items.append(item)

        # selected-point marker (red circle)
        if self._pick_marker is not None:
            view.removeItem(self._pick_marker)
            self._pick_marker = None
        if self._select_attr:
            sel = getattr(self._model, self._select_attr, None)
            if sel is not None and int(sel[0]) == z:
                self._pick_marker = pg.ScatterPlotItem(
                    [int(sel[2])],
                    [int(sel[1])],
                    pen=pg.mkPen("r", width=2),
                    brush=None,
                    size=15,
                    symbol="o",
                )
                self._pick_marker.setZValue(9)
                view.addItem(self._pick_marker)

        # fitted lateral-FWHM circle (yellow)
        if self._roi_item is not None:
            view.removeItem(self._roi_item)
            self._roi_item = None
        if self._roi_source:
            fn = getattr(self._model, self._roi_source, None)
            roi = fn() if callable(fn) else None
            if roi and int(roi.get("z", z)) == z:
                r = float(roi["r"])
                cx, cy = float(roi["x"]), float(roi["y"])
                try:
                    self._roi_item = pg.CircleROI(
                        [cx - r, cy - r],
                        [2 * r, 2 * r],
                        pen=pg.mkPen("y", width=2),
                        movable=False,
                        resizable=False,
                    )
                    self._roi_item.setZValue(10)
                    view.addItem(self._roi_item)
                except Exception:  # pragma: no cover - CircleROI optional
                    self._roi_item = None


    def _apply_extent(self) -> None:
        """Place the image on real axes when the model supplies an extent.

        Without this an image is drawn in *pixel* coordinates, so a histogram
        reads in bin indices and anything overlaid on it — a gate, a cursor —
        has to be converted bin-by-bin at every call site. Given
        ``extent_source`` the axes carry the quantity itself, and a region drawn
        on the plane is in the same units the analysis gates with.
        """
        if self._image is None or not self._extent_source:
            return
        fn = getattr(self._model, self._extent_source, None)
        extent = fn() if callable(fn) else fn
        if extent is None or len(extent) != 4:
            return
        x0, x1, y0, y1 = (float(v) for v in extent)
        if x1 <= x0 or y1 <= y0:
            return
        self._image.getImageItem().setRect(QtCore.QRectF(x0, y0, x1 - x0, y1 - y0))
        # Range to it only when the span itself changed. The view is still in
        # pixel coordinates until something tells it otherwise — the image lands
        # in a corner and everything drawn on it looks like a speck — but
        # re-ranging on every refresh would undo the user's zoom.
        # Re-range when the span changed, and also when the view is no longer on
        # it at all. ``setImage`` resets the view to the image's *pixel* box, so
        # swapping the displayed array — a channel selector switching between a
        # measured map and a residual, say — left the axes reading 0 to 41 with the
        # image a speck in the corner, even though its rect was correct.
        view = self._image.getView()
        changed = extent != getattr(self, "_applied_extent", None)
        off_extent = False
        if not changed:
            try:
                (vx0, vx1), (vy0, vy1) = view.viewRange()
                span_x, span_y = x1 - x0, y1 - y0
                off_extent = (
                    vx1 - vx0 > 10.0 * span_x or vy1 - vy0 > 10.0 * span_y
                )
            except Exception:
                off_extent = False
        if changed or off_extent:
            self._applied_extent = tuple(extent)
            view.autoRange()

    # ── surface for the shared region overlay ──────────────────────────
    def add_roi(self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0),
                pen="y", movable=True, rotatable=False, points=None):
        """Add a draggable region shape, returning a chiplot ROI handle.

        This is the whole surface
        :class:`~chisurf.gui.widgets.roi.overlay.RegionOverlay` needs, so any
        tool whose canvas is this section can show and edit a shared region
        collection on it. Implemented here rather than in chiplot because this
        widget owns the pyqtgraph image view; handing the raw view out would put
        the coupling somewhere it could rot unnoticed.

        Parameters
        ----------
        kind : str
            ``"rect"``, ``"circle"``, ``"ellipse"`` or ``"polygon"``.
        pos, size : tuple of float
            Corner and extent in image coordinates.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it.
        rotatable : bool
            Whether a rectangle may be rotated.
        points : sequence of (float, float), optional
            Vertices for ``kind="polygon"``.

        Returns
        -------
        chisurf.gui.chiplot.handles.Roi

        Raises
        ------
        RuntimeError
            If there is no image view (pyqtgraph missing).
        """
        if self._image is None:
            raise RuntimeError("no image view to draw a region on")
        from chisurf.gui.chiplot import style as S
        from chisurf.gui.chiplot.backends import pyqtgraph_backend as B

        # Through the backend's own constructor, not `__new__`: building the
        # canvas by hand skipped `__init__` and therefore every attribute it
        # sets, which broke the moment the canvas started tracking what it had
        # added. (This whole method reaches past the chiplot seam; it belongs
        # on a chiplot canvas this widget owns — see the chiplot concept.)
        surface = B._PgImageView.wrap(self._image)
        return surface.add_roi(
            kind=kind, pos=tuple(pos), size=tuple(size), pen=S.to_pen(pen),
            movable=movable, rotatable=rotatable, points=points,
        )

    # ── refresh ────────────────────────────────────────────────────────
    # ── interactive rectangle gate ────────────────────────────────────
    def _setup_rect_roi(self, pg) -> None:
        """Add the draggable/resizable rectangle used as an image gate."""
        pen = pg.mkPen((80, 170, 255), width=2)
        roi = pg.RectROI([0, 0], [1, 1], pen=pen, hoverPen=pg.mkPen((120, 200, 255), width=3))
        roi.addScaleHandle([1, 1], [0, 0])
        roi.addScaleHandle([0, 0], [1, 1])
        roi.setZValue(20)
        self._image.getView().addItem(roi)
        roi.sigRegionChangeFinished.connect(self._on_rect_roi)
        self._rect_roi = roi

    def _on_rect_roi(self) -> None:
        """Report the drawn rectangle to the model as a region."""
        if self._rect_roi is None or not self._region_call:
            return
        fn = getattr(self._model, self._region_call, None)
        if not callable(fn):
            return
        from chisurf.core.roi import RectangleROI

        pos = self._rect_roi.pos()
        size = self._rect_roi.size()
        x0, y0 = float(pos.x()), float(pos.y())
        try:
            fn(RectangleROI(x0, y0, x0 + float(size.x()), y0 + float(size.y()),
                            name="gate"))
        except Exception:
            logging.debug("region callback failed", exc_info=True)

    def _place_rect_roi(self, data) -> None:
        """Place the rectangle from the model's region, or on the image centre once."""
        if self._rect_roi is None:
            return
        region = None
        if self._region_source:
            src = getattr(self._model, self._region_source, None)
            try:
                region = src() if callable(src) else src
            except Exception:
                region = None
        if region is None:
            if self._rect_placed:
                return
            nx, ny = float(data.shape[0]), float(data.shape[1])
            rect = (0.25 * nx, 0.25 * ny, 0.75 * nx, 0.75 * ny)
        else:
            # Analytic regions bound themselves exactly; anything else is
            # rasterised. Snapping a rectangle's handles to pixel edges on every
            # redraw would make it creep.
            found = region.bounds((int(data.shape[1]), int(data.shape[0])), image=data)
            if found is None:
                return
            rect = tuple(float(v) for v in found)
        x0, y0, x1, y1 = (float(v) for v in rect)
        self._rect_roi.blockSignals(True)
        self._rect_roi.setPos(x0, y0)
        self._rect_roi.setSize((max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)))
        self._rect_roi.blockSignals(False)
        self._rect_placed = True

    def refresh(self) -> None:
        """Re-read the model image (and selection) and redraw with the colormap."""
        if self._image is None:
            return
        import numpy as np

        obj = getattr(self._model, self._target, None)
        img = obj() if callable(obj) else obj
        if img is None:
            return
        # keep the combo in sync if the colormap is model-backed
        if self._combo is not None:
            cur = self._current_cmap()
            if cur != self._combo.currentText():
                self._combo.blockSignals(True)
                i = self._combo.findText(cur)
                if i >= 0:
                    self._combo.setCurrentIndex(i)
                self._combo.blockSignals(False)
        # keep the detector-channel combo in sync (options + current selection)
        if self._channel_combo is not None:
            self._reload_channels()
        data = np.asarray(img, dtype=float)
        self._ndim = data.ndim
        # movie controls are meaningful only for a 3D (frame, y, x) stack
        if self._movie:
            self._set_movie_enabled(data.ndim == 3)
        if data.ndim == 3:
            # Preserve the current slice across refreshes. The frame is
            # ``(row, column)`` like any 2-D map, so x is the last axis and y the
            # middle one; the opposite mapping renders every frame 90° off from
            # the 2-D map docked beside it, which is what the removed ``match_2d``
            # flag did while claiming the reverse.
            try:
                prev = int(self._image.currentIndex)
            except Exception:
                prev = 0
            axes = {"t": 0, "x": 2, "y": 1}
            self._image.setImage(data, autoLevels=True, axes=axes)
            if 0 <= prev < data.shape[0]:
                self._image.setCurrentIndex(prev)
        else:
            self._image.setImage(data, autoLevels=True)
        self._apply_extent()
        apply_colormap(self._image, self._current_cmap())
        if self._overlay is not None and self._selection_attr:
            sel = getattr(self._model, self._selection_attr, None)
            sel = (
                np.zeros_like(data)
                if sel is None or np.shape(sel) != data.shape
                else np.asarray(sel)
            )
            self._overlay.setImage(sel)
        if self._rect_roi is not None and data.ndim == 2:
            self._place_rect_roi(data)
        if self._markers_source or self._roi_source or self._select_attr or self._labels_source:
            self._redraw_overlays()


@register_section("image")
def _image_section_factory(model, target: str, **options):
    """Custom-section factory for a general 2D image dock (see :class:`ImageMapWidget`)."""
    return ImageMapWidget(model, target, **options)


# --- fit mixer (LifetimeMixtureModel AutoForm section) ---------------------
@register_section("fit_mixer")
class FitMixerWidget(QtWidgets.QWidget):
    """Fit-selector and fraction-parameter UI for the LifetimeMixture AutoForm section.

    Provides a combo box of existing lifetime fits, add/remove controls, a list
    of added components, and inline fraction-parameter widgets. Register it in a
    ``.view.json`` as::

        {"type": "custom", "key": "fit_mixer"}

    The model must expose the ``LifetimeMixtureModel`` API:
    ``lifetime_fits``, ``append_model(model, name)``, ``pop_model(idx)``,
    ``_fractions`` and ``model_names``.
    """

    def __init__(self, model=None, target=None, parent=None, **options):
        super().__init__(parent)
        self._model = model

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # Toolbar: combo + refresh + name field + "all" checkbox + add button
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(2)

        self.cb = QtWidgets.QComboBox()
        self.cb.setToolTip("Select a lifetime fit to add to the mixture.")
        toolbar.addWidget(self.cb, 2)

        refresh_btn = QtWidgets.QToolButton()
        refresh_btn.setText(Glyphs.REFRESH)
        refresh_btn.setToolTip("Refresh the list of available lifetime fits.")
        refresh_btn.clicked.connect(self._refresh_fit_list)
        toolbar.addWidget(refresh_btn)

        toolbar.addWidget(QtWidgets.QLabel("Name"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("fraction name…")
        self.name_edit.setMaximumWidth(90)
        self.name_edit.setToolTip("Name for the fraction parameter (default: x_N).")
        toolbar.addWidget(self.name_edit)

        self.all_cb = QtWidgets.QCheckBox("all")
        self.all_cb.setToolTip("Add all listed fits at once.")
        toolbar.addWidget(self.all_cb)

        add_btn = QtWidgets.QToolButton()
        add_btn.setText("add")
        add_btn.setToolTip("Add the selected fit to the mixture.")
        add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(add_btn)

        outer.addLayout(toolbar)

        # Current component list (double-click removes)
        self.fit_list = QtWidgets.QListWidget()
        self.fit_list.setMaximumHeight(80)
        self.fit_list.setToolTip("Mixture components. Double-click a row to remove it.")
        self.fit_list.doubleClicked.connect(self._on_remove)
        outer.addWidget(self.fit_list)

        # Fraction parameter widgets (rebuilt after each add/remove)
        self._fractions_container = QtWidgets.QWidget()
        self._fractions_layout = QtWidgets.QGridLayout(self._fractions_container)
        self._fractions_layout.setContentsMargins(0, 0, 0, 0)
        self._fractions_layout.setSpacing(2)
        outer.addWidget(self._fractions_container)

        self._refresh_fit_list()
        self._rebuild_fractions()

    # -- helpers ---------------------------------------------------------------

    def _own_fit_index(self) -> int:
        """Return the index of this model's fit in ``chisurf.fits``, or ``-1``.

        ``-1`` means the bound model's fit is not registered with the fit
        machinery — a scripted or headless fit, or a tool with no fit at all.
        This used to answer ``0``, which is not "unknown" but *another fit*:
        against an empty list it raised, and against a populated one it would
        have dispatched the edit at whichever fit happened to be first.
        Fit-targeted dispatch is skipped for a negative index instead.
        """
        try:
            import chisurf as cs

            fit = getattr(self._model, "fit", None)
            for i, fg in enumerate(cs.fits):
                if fg is fit or fit in list(fg):
                    return i
        except Exception:
            pass
        return -1

    def _dispatch_update(self) -> None:
        try:
            import chisurf as cs

            index = self._own_fit_index()
            if index >= 0:
                cs.core.actions.dispatch("fit.update", {"fit_index": int(index)})
        except Exception:
            pass

    # -- slots -----------------------------------------------------------------

    def _refresh_fit_list(self) -> None:
        """Populate the combo box from the model's available lifetime fits."""
        self.cb.clear()
        for f in getattr(self._model, "lifetime_fits", []):
            self.cb.addItem(f.name)

    def _on_add(self) -> None:
        """Add the selected fit(s) to the mixture."""
        fits = getattr(self._model, "lifetime_fits", [])
        if not fits:
            return
        idxs = list(range(len(fits))) if self.all_cb.isChecked() else [self.cb.currentIndex()]
        for idx in idxs:
            if not (0 <= idx < len(fits)):
                continue
            f = fits[idx]
            i = self.fit_list.count() + 1
            name = self.name_edit.text().strip() or f"x_{i}"
            try:
                self._model.append_model(f.model, name)
            except Exception as error:
                # Listing a model the mixture refused would show a mixture
                # that is not the one being fitted.
                import chisurf as cs
                cs.logging.warning(f"could not add {f.name!r} to the mixture: {error}")
                continue
            self.fit_list.addItem(f"{i}: {f.name}")
        self._dispatch_update()
        self._rebuild_fractions()

    def _on_remove(self) -> None:
        """Remove the double-clicked fit from the mixture."""
        idx = self.fit_list.currentRow()
        if idx < 0:
            return
        self.fit_list.takeItem(idx)
        try:
            self._model.pop_model(idx)
        except Exception:
            pass
        # Renumber remaining items to keep indices consistent
        for i in range(self.fit_list.count()):
            item = self.fit_list.item(i)
            rest = item.text().split(": ", 1)[1] if ": " in item.text() else item.text()
            item.setText(f"{i + 1}: {rest}")
        self._dispatch_update()
        self._rebuild_fractions()

    def _rebuild_fractions(self) -> None:
        """Recreate the fraction-parameter widget grid from the model's state."""
        from chisurf.gui.widgets.fitting.parameter_widgets import make_fitting_parameter_widget

        layout = self._fractions_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        fractions = getattr(self._model, "_fractions", [])
        model_names = getattr(
            self._model, "model_names", [f"x{i + 1}" for i in range(len(fractions))]
        )
        if not fractions:
            return

        layout.addWidget(QtWidgets.QLabel("Fraction"), 0, 0)
        layout.addWidget(QtWidgets.QLabel("Model"), 0, 1)
        for row, (frac, name) in enumerate(zip(fractions, model_names), start=1):
            layout.addWidget(make_fitting_parameter_widget(frac, label_text=""), row, 0)
            layout.addWidget(QtWidgets.QLabel(name), row, 1)


@register_section("kappa2_controls")
class Kappa2Controls(QtWidgets.QWidget):
    """The orientation-factor (κ²) mode row for a FRET model's editor.

    Dynamic/static κ² radios, the fast-convolution toggle, and the three
    dialog buttons (show κ², compute κ², calc R0). This is a bespoke
    escape-hatch section rather than declarative vocabulary because the buttons
    open interactive dialogs and the radios drive
    ``model.orientation_parameter.mode`` -- neither is a parameter a table cell
    can hold.

    The controls themselves are the *same* implementation the hand-written FRET
    widgets use (``kappa2_helpers.setup_kappa2_controls``), so the two paths
    cannot drift apart; this widget only supplies the Qt parent while the model
    stays the single source of truth.
    """

    def __init__(self, model=None, target: str = "", parent=None, **options):
        """Build the κ² control row for `model`.

        Parameters
        ----------
        model : optional
            The FRET model whose orientation parameter the controls edit.
        target : str
            Unused; accepted because every section receives it.
        parent : optional
            Qt parent widget.
        **options
            Unused view-spec options.
        """
        super().__init__(parent)
        self._model = model
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        from chisurf.gui.widgets.models.tcspc import kappa2_helpers

        kappa2_helpers.setup_kappa2_controls(self, layout, fret_model=model)
