"""Render an object's editor from its UI-agnostic :class:`DataSet`/``ModelView``.

:class:`AutoForm` walks the declarative spec (today: a model's ``view_spec()``)
and builds the control panel by composition — it *has a* bound object, it is not
one. Generic sections are drawn from the parameters themselves; bespoke ones are
looked up in the section registry by key. This is the single renderer that
replaces the per-domain hand-written widgets (PRD-40). ``AutoModelWidget`` is
kept as a backwards-compatible alias.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

import chisurf as cs
from chisurf import logging
from chisurf.core import dataspec as vs
from chisurf.gui.widgets.fitting import make_fitting_parameter_widget

from . import sections  # noqa: F401  (side effect: populate the registry)
from .sections.registry import get_section_factory

#: How many label/field pairs are packed onto one row of the compact field grid.
FIELDS_PER_ROW = 2

ADD_BUTTON_STYLE = (
    "QPushButton { background-color: #1f7a1f; color: white; border: 1px solid #166016; "
    "border-radius: 3px; padding: 2px 8px; }"
    "QPushButton:hover { background-color: #249124; }"
)
REMOVE_BUTTON_STYLE = (
    "QPushButton { background-color: #a82020; color: white; border: 1px solid #7d1717; "
    "border-radius: 3px; padding: 2px 8px; }"
    "QPushButton:hover { background-color: #bf2626; }"
)


def _make_field_shrinkable(field) -> None:
    """Let a field's editors shrink so the form scales to narrow docks/panels.

    Spin boxes and combo boxes default to a wide intrinsic minimum (the value text
    plus arrows, or the longest combo item), which forces the compact two-column
    grid to overflow horizontally instead of sharing the available width. Drop that
    floor and let the column stretch decide the width so the editors track the panel.
    """
    field.setMinimumWidth(0)
    editors = field.findChildren(
        (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox, QtWidgets.QLineEdit)
    )
    for editor in editors:
        editor.setMinimumWidth(0)
        editor.setSizePolicy(QtWidgets.QSizePolicy.Expanding, editor.sizePolicy().verticalPolicy())
        if isinstance(editor, QtWidgets.QComboBox):
            editor.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            editor.setMinimumContentsLength(3)


def _make_form_label(text: str) -> QtWidgets.QLabel:
    """Build the caption shown left of a field.

    The spec's ``label`` is the *plain* name — greppable, translatable, and what
    the generated documentation table prints. What the user sees is its typeset
    form, so ``"tau_D(0) (ns)"`` in the view spec renders as τ with a real
    subscript without anyone hand-writing HTML (see
    :mod:`chisurf.core.labels`). A label that already carries markup is passed
    through untouched.

    The plain text stays reachable as the tooltip and as
    ``label.property("plainLabel")``, so a caption that is typeset on screen can
    still be matched by tests and searched by the user.

    Parameters
    ----------
    text : str
        The spec label, plain or already marked up.

    Returns
    -------
    QtWidgets.QLabel
        A right-aligned rich-text label.
    """
    from chisurf.core.labels import to_plain, to_rich

    plain = to_plain(text)
    label = QtWidgets.QLabel(to_rich(text))
    label.setTextFormat(QtCore.Qt.RichText)
    label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    label.setProperty("plainLabel", plain)
    return label


def _align_label_columns(param_widgets):
    """Give a batch of fitting-parameter rows one shared label width.

    Each :class:`FittingParameterWidget` is a self-contained row, so without
    this their name labels self-size and the fix/link/value/error columns end up
    ragged from row to row. Setting every label to the widest label's width (up
    to a sane cap) lines the columns up cleanly; the full name stays available
    as the label tooltip.
    """
    labels = [getattr(pw, "label", None) for pw in param_widgets]
    labels = [lbl for lbl in labels if lbl is not None]
    if not labels:
        return
    width = min(max(lbl.sizeHint().width() for lbl in labels), 120)
    for lbl in labels:
        if not lbl.toolTip():
            lbl.setToolTip(lbl.text())
        lbl.setFixedWidth(width)


class AutoForm(QtWidgets.QWidget):
    """Build a bound object's control panel from its declarative spec.

    Parameters
    ----------
    model : chisurf.core.models.model.Model
        The pure object whose editor should be rendered (a model today).
    parent : QtWidgets.QWidget, optional
        Parent widget.
    """

    #: Emitted after :meth:`rebuild` has replaced the panel's widgets. A
    #: ``rebuild_on_change`` control (a colour count, a detector layout) deletes
    #: every widget a host grabbed out of a custom section, so a host that keeps
    #: references has to re-adopt them; without a signal it cannot know when.
    rebuilt = QtCore.Signal()

    @classmethod
    def from_parameter_group(cls, group, parent=None, **kwargs):
        """Render a ``FittingParameterGroup`` directly, without authored JSON.

        Thin convenience over :class:`chisurf.core.dataspec.ParameterGroupView`;
        ``kwargs`` (``title``/``n_col``/``collapsible``/``collapsed``) are
        forwarded to it.
        """
        from chisurf.core.dataspec import ParameterGroupView

        return cls(ParameterGroupView(group, **kwargs), parent=parent)

    @classmethod
    def from_rpc_method(cls, method, parent=None, **kwargs):
        """Render a parameter form for a plugin RPC method declaration.

        Thin convenience over :class:`chisurf.core.dataspec.RpcMethodView`:
        *method* is an ``RPCMethodSpec`` (or a raw ``rpc_methods`` manifest
        entry) and ``kwargs`` (``values``/``on_change``/``title``) are forwarded
        to the view. The method's ``description`` (falling back to ``summary``)
        and the JSON-Schema ``description`` of each parameter surface as Qt
        tooltips; read the entered values back via ``form.model.params()``.
        """
        from chisurf.core.dataspec import RpcMethodView

        return cls(RpcMethodView(method, **kwargs), parent=parent)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self._param_widgets = []
        self._dock_areas = []
        self._refresh_targets = []
        self._section_widgets = []
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rebuild()

    # -- public API ---------------------------------------------------------

    def state(self) -> dict:
        """The current value of every control bound to a model attribute.

        A form generated from a view spec already knows where its state lives,
        so capturing it needs no per-plugin code. See
        :mod:`chisurf.gui.autoform.state`.
        """
        from chisurf.gui.autoform import state as _state

        return _state.collect_state(self)

    def apply_state(self, values: dict, *, sync: bool = True):
        """Restore controls from a mapping produced by :meth:`state`.

        Lenient: unknown keys and rejected values are reported in the returned
        :class:`~chisurf.gui.autoform.state.StateResult` rather than raised, so
        a settings file from an older version restores what it still shares.
        """
        from chisurf.gui.autoform import state as _state

        return _state.apply_state(self, values, sync=sync)

    def save_state(self, path, **extra):
        """Write this form's settings to a JSON file."""
        from chisurf.gui.autoform import state as _state

        return _state.save_state(self, path, **extra)

    def load_state(self, path):
        """Restore this form's settings from a JSON file."""
        from chisurf.gui.autoform import state as _state

        return _state.load_state(self, path)

    def rebuild(self):
        """(Re)build the whole panel from the current view-spec."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._param_widgets = []
        self._dock_areas = []
        self._refresh_targets = []
        self._section_widgets = []

        view = self.model.view_spec()
        self._emit_sections(view.sections, self._layout.addWidget)
        # If the view contains an expanding widget (e.g. a dock area or plot), let it take
        # the spare vertical space; otherwise top-align the panels with a trailing stretch.
        expanding = False
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if w is not None and getattr(w, "_autoform_expanding", False):
                self._layout.setStretch(i, 1)
                expanding = True
        if not expanding:
            self._layout.addStretch(1)  # push panels to the top; prevent height distribution
        self.rebuilt.emit()

    def set_field_label(self, target: str, text: str = None, html: str = None) -> bool:
        """Retitle a field's caption at run time.

        The counterpart of a :class:`FittingParameterWidget`'s ``label_text``:
        the field keeps its programmatic identity (the model attribute it is
        bound to) while what the user reads changes — a channel called
        ``i_da`` shown as ``I_DA`` for one setup and ``F_D|A`` for another.

        Parameters
        ----------
        target : str
            The model attribute the field is bound to.
        text : str, optional
            New plain label; it is typeset with :func:`chisurf.core.labels.to_rich`.
        html : str, optional
            Ready-made markup, used verbatim in preference to ``text``.

        Returns
        -------
        bool
            Whether a field bound to ``target`` was found.
        """
        from chisurf.core.labels import to_plain, to_rich

        if html is None and text is None:
            return False
        markup = html if html is not None else to_rich(text)
        plain = to_plain(html) if html is not None else str(text)

        found = False
        for widget in self.findChildren(QtWidgets.QWidget):
            section = getattr(widget, "_section", None)
            if section is None:
                continue
            # Field sections bind through ``attr``; a few section types name the
            # same thing ``target``. Accept either rather than making the caller
            # know which kind of section it is retitling.
            bound = getattr(section, "attr", None) or getattr(section, "target", None)
            if bound != target:
                continue
            widget.form_label = plain
            label = getattr(widget, "_autoform_label", None)
            if label is not None:
                label.setText(markup)
                label.setProperty("plainLabel", plain)
            found = True
        return found

    def sync_fields(self):
        """Re-read model values into existing field widgets without rebuilding.

        Use this after changing model attributes programmatically so the controls reflect
        the new values *without* tearing down the layout (which would, e.g., reset a dock
        arrangement). Only widgets exposing a ``sync()`` method are updated.
        """
        for w in self.findChildren(QtWidgets.QWidget):
            # Form-field widgets sync via ``sync()``; full-width AUTOFORM_REFRESH
            # widgets (e.g. the parameter-group table) sync via ``sync``/``refresh``
            # too, so programmatic model changes reach both.
            if getattr(w, "is_form_field", False) or getattr(w, "AUTOFORM_REFRESH", False):
                fn = getattr(w, "sync", None) or getattr(w, "refresh", None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass

    def refresh_plots(self):
        """Re-read and redraw every inline :class:`PlotSection` in the form.

        Call this after the model's data changes (e.g. a recompute) so embedded
        plots update without rebuilding the whole editor.
        """
        from .sections.builtin import PlotWidget

        # Combine the live child tree with the tracked plot/refresh targets, so a
        # plot or table that a dock area reparented/floated (out of findChildren's
        # reach) still refreshes when the model changes.
        candidates = list(self.findChildren(PlotWidget))
        candidates += [w for w in self.findChildren(QtWidgets.QWidget)
                       if getattr(w, "AUTOFORM_REFRESH", False)]
        candidates += list(getattr(self, "_refresh_targets", []))
        seen = set()
        for w in candidates:
            if w is None or id(w) in seen:
                continue
            seen.add(id(w))
            refresh = getattr(w, "refresh", None)
            if not callable(refresh):
                continue
            try:
                refresh()
            except RuntimeError:
                # C++ object deleted (rebuilt) — drop it from the tracked list.
                continue
            except Exception:
                pass

    def _emit_sections(self, section_list, emit, fields_per_row=None):
        """Build sections, grouping consecutive simple fields into one form.

        Field sections (value / choice / toggle, marked ``is_form_field``) are
        accumulated and flushed into a single compact ``QGridLayout`` that packs
        ``fields_per_row`` label/field pairs per row (defaulting to
        ``FIELDS_PER_ROW``) to save vertical space; passing ``1`` gives a
        single-column form layout that saves horizontal space. Any other section
        (panel, parameter grid, curve input) flushes the run and is emitted
        full-width.
        """
        pending = []

        def flush():
            if not pending:
                return
            container = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(2)
            per_row = max(1, fields_per_row or FIELDS_PER_ROW)
            any_expanding = False
            for i, field in enumerate(pending):
                r, c = divmod(i, per_row)
                col = c * 2
                label = _make_form_label(getattr(field, "form_label", ""))
                tip = field.toolTip()
                if tip:
                    label.setToolTip(tip)
                # The field keeps a handle on its caption so a tool can retitle
                # it at run time (see AutoForm.set_field_label).
                field._autoform_label = label
                # Fields stretch horizontally to share the available width; the
                # field columns carry the stretch, the label columns stay fixed.
                # A field marked ``_autoform_expanding`` (e.g. a text preview) also
                # grows vertically and its grid row carries the stretch.
                expanding = bool(getattr(field, "_autoform_expanding", False))
                vpolicy = QtWidgets.QSizePolicy.Expanding if expanding else QtWidgets.QSizePolicy.Fixed
                field.setSizePolicy(QtWidgets.QSizePolicy.Expanding, vpolicy)
                _make_field_shrinkable(field)
                grid.addWidget(label, r, col)
                grid.addWidget(field, r, col + 1)
                grid.setColumnStretch(col + 1, 1)
                if expanding:
                    grid.setRowStretch(r, 1)
                    label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
                    any_expanding = True
            pending.clear()
            # Propagate expansion so the enclosing panel hands this form the spare
            # vertical space instead of appending a trailing stretch below it.
            if any_expanding:
                container._autoform_expanding = True
                container.setSizePolicy(
                    QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
                )
            emit(container)

        for section in section_list:
            try:
                widget = self._build_section(section)
            except Exception as exc:  # pragma: no cover - defensive
                logging.error(f"AutoForm: failed to build section {section}: {exc}")
                continue
            if widget is None:
                continue
            visible = bool(section.visible) and not self._collapsed_when(
                getattr(section, "hidden_when", None)
            )
            widget.setVisible(visible)
            # Default path for inline help: a section's ``description`` becomes
            # the widget's tooltip. Field widgets additionally set it on their
            # editor (Qt tooltips do not propagate to child widgets). Fold long
            # descriptions so the label column's tooltip does not render as one
            # very wide line.
            desc = getattr(section, "description", "")
            if desc:
                from chisurf.gui.tooltip import wrap_tooltip

                widget.setToolTip(wrap_tooltip(desc))
            if getattr(widget, "is_form_field", False):
                pending.append(widget)
            else:
                flush()
                emit(widget)
        flush()

    @property
    def parameter_widgets(self):
        """Flat list of parameter widgets currently rendered (for tests/sync)."""
        return list(self._param_widgets)

    # -- section dispatch ---------------------------------------------------
    def section_widget(self, title: str = "", key: str = ""):
        """Return the widget built for a section, found by its title and/or key.

        A tool sometimes has to reach one section from outside — to draw a
        region overlay on *this* canvas, to connect two panels. Doing that with
        ``findChild(SomeWidget)`` picks the first of its type, which is wrong the
        moment a tool has two: the phasor tool has a static plot and a movie
        plot, and the overlay silently attached to whichever came first.

        Parameters
        ----------
        title : str, optional
            The section's ``title`` in the view spec.
        key : str, optional
            The ``key`` of a ``custom`` section.

        Returns
        -------
        QWidget or None
            The first section matching every criterion given, or ``None``.
        """
        for section, widget in getattr(self, "_section_widgets", []):
            if title and str(getattr(section, "title", "") or "") != title:
                continue
            if key and str(getattr(section, "key", "") or "") != key:
                continue
            # A titled custom section is wrapped in a caption holder; the caller
            # wants what the factory built.
            return getattr(widget, "_autoform_inner", widget)
        return None

    def _build_section(self, section: vs.Section):
        widget = self._build_section_widget(section)
        if widget is not None:
            # Recorded so :meth:`section_widget` can find a built section by the
            # name the view spec gave it, rather than by widget type.
            if not hasattr(self, "_section_widgets"):
                self._section_widgets = []
            self._section_widgets.append((section, widget))
        return widget

    def _build_section_widget(self, section: vs.Section):
        if isinstance(section, vs.PanelSection):
            return self._build_panel(section)
        if isinstance(section, vs.DynamicGroupSection):
            return self._build_dynamic_group(section)
        if isinstance(section, vs.CurveInputSection):
            return self._build_curve_input(section)
        if isinstance(section, vs.ChoiceSection):
            from .sections.builtin import ChoiceWidget

            return ChoiceWidget(self.model, section)
        if isinstance(section, vs.ToggleSection):
            from .sections.builtin import ToggleWidget

            return ToggleWidget(self.model, section)
        if isinstance(section, vs.ToggleRowSection):
            from .sections.builtin import ToggleRowWidget

            return ToggleRowWidget(self.model, section)
        if isinstance(section, vs.ButtonRowSection):
            from .sections.builtin import ButtonRowWidget

            return ButtonRowWidget(self.model, section)
        if isinstance(section, vs.TableSection):
            from .sections.builtin import TableWidget

            return TableWidget(self.model, section)
        if isinstance(section, vs.ValueSection):
            from .sections.builtin import ValueWidget

            return ValueWidget(self.model, section)
        if isinstance(section, vs.PlotSection):
            from .sections.builtin import PlotWidget

            plot = PlotWidget(self.model, section)
            # Track it directly so refresh_plots() still reaches it after a dock
            # reparents/floats it (findChildren would then miss it).
            self._refresh_targets.append(plot)
            return plot
        if isinstance(section, vs.DockAreaSection):
            return self._build_dock_area(section)
        if isinstance(section, vs.WizardSection):
            return self._build_wizard(section)
        if isinstance(section, vs.InfoSection):
            from .sections.builtin import InfoWidget

            return InfoWidget(self.model, section)
        if isinstance(section, vs.ParameterGroupTableSection):
            return self._build_parameter_group_table(section)
        if isinstance(section, vs.ParameterGroupSection):
            return self._build_parameter_group(section)
        if isinstance(section, vs.CustomSection):
            return self._build_custom(section)
        logging.warning(f"AutoModelWidget: unknown section type {type(section).__name__}")
        return None

    def _resolve_group(self, target):
        obj = self.model
        for part in str(target).split("."):
            if obj is None:
                break
            obj = getattr(obj, part, None)
        if obj is None:
            logging.warning(f"AutoModelWidget: target {target!r} did not resolve")
        return obj

    def _make_fold_box(self, section, fallback_title: str = ""):
        """Build a :class:`CollapsibleBox` from a section's fold attributes.

        Honors ``collapsible`` / ``collapsed`` / ``collapsed_when`` when present
        (``PanelSection``, ``ParameterGroupSection``,
        ``ParameterGroupTableSection``, ``DynamicGroupSection``), falling back
        to an always-expanded box otherwise.
        """
        from chisurf.gui.widgets.collapsible_box import CollapsibleBox

        collapsed = bool(getattr(section, "collapsed", False)) or self._collapsed_when(
            getattr(section, "collapsed_when", None)
        )
        box = CollapsibleBox(section.title or fallback_title, expanded=not collapsed)
        # the header is purely cosmetic when not collapsible
        if not getattr(section, "collapsible", True):
            box._btn.setEnabled(False)
        return box

    def _build_parameter_group(self, section: vs.ParameterGroupSection):
        group = self._resolve_group(section.target)
        if group is None:
            return None
        # Groups that define their parameters as plain attributes
        # (``self._dt = FittingParameter(...)``) surface them on the first read of
        # ``parameters_all``, which walks the group itself — this section used to
        # have to ask for that walk explicitly or render empty.
        if section.exclude_source:
            try:
                excluded = {id(p) for p in getattr(group, section.exclude_source)()}
            except Exception:
                excluded = set()
            params = [p for p in getattr(group, "parameters_all", []) if id(p) not in excluded]
        else:
            params = list(getattr(group, "parameters_all", []))

        self._apply_section_priors(getattr(section, "priors", None), params)

        grid = self._build_param_grid(params, section.n_col)
        self._param_widgets.extend(self._collect_param_widgets(grid))

        if not getattr(section, "collapsible", True):
            # No wrapper box — used when nested inside a PanelSection
            return grid

        box = self._make_fold_box(section, fallback_title=getattr(group, "name", ""))
        box.add_widget(grid)
        return box

    @staticmethod
    def _apply_section_priors(priors, params):
        """Apply view-spec-declared priors to the matching parameters.

        ``priors`` maps a parameter name to a prior-state dict (or ``None`` to
        clear). Applied to the :class:`FittingParameter` objects before their
        widgets are built, so a model author can ship a default prior in the
        ``.view.json``. Invalid specs are skipped with a warning; a ``None``
        spec clears any existing prior.
        """
        if not priors:
            return
        from chisurf.core.fitting.priors import as_prior

        by_name = {getattr(p, "name", None): p for p in params}
        for name, spec in dict(priors).items():
            p = by_name.get(name)
            if p is None:
                logging.warning("AutoModelWidget: prior for unknown parameter %r ignored", name)
                continue
            if spec is None:
                prior = None
            else:
                try:
                    prior = as_prior(spec)
                except Exception:
                    prior = None
                if prior is None:
                    logging.warning("AutoModelWidget: invalid prior spec for %r ignored", name)
                    continue
            try:
                p.prior = prior
            except Exception as exc:  # pragma: no cover - defensive
                logging.warning("AutoModelWidget: failed to set prior for %r: %s", name, exc)

    def _build_param_grid(self, params, n_col=None):
        """Build a bare ``QWidget`` grid from a pre-filtered parameter list."""
        import chisurf.core.settings

        if n_col is None:
            n_col = chisurf.core.settings.gui["fit_models"]["n_columns"]
        n_col = max(1, int(n_col))
        container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        pws = []
        for i, p in enumerate(params):
            label_text = p.__dict__.get("label_text", p.name)
            pw = make_fitting_parameter_widget(fitting_parameter=p, label_text=label_text)
            grid.addWidget(pw, i // n_col, i % n_col)
            pws.append(pw)
        _align_label_columns(pws)
        return container

    def _build_parameter_group_table(self, section: vs.ParameterGroupTableSection):
        group = self._resolve_group(section.target)
        if group is None:
            return None

        if section.exclude_source:
            try:
                excluded = {id(p) for p in getattr(group, section.exclude_source)()}
            except Exception:
                excluded = set()
            params = [p for p in getattr(group, "parameters_all", []) if id(p) not in excluded]
        else:
            params = list(getattr(group, "parameters_all", []))

        if not params:
            return None

        from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget

        table = ParameterGroupTableWidget(
            params=params,
            section=section,
            on_change=self._dispatch_fit_update,
        )

        if not getattr(section, "collapsible", True):
            return table

        box = self._make_fold_box(section, fallback_title=getattr(group, "name", ""))
        box.add_widget(table)
        return box

    def _build_panel(self, section: vs.PanelSection):
        box = self._make_fold_box(section)
        self._emit_sections(section.sections, box.add_widget, fields_per_row=section.n_col)
        if getattr(section, "bounds_toggle", False):
            self._add_bounds_toggle(box)
        return box

    def _add_bounds_toggle(self, box):
        """Add a header toggle for the bounds columns of the panel's tables.

        Shows/hides the Lo / Hi / Bounds columns of every parameter table in
        ``box``; the columns start hidden to keep the tables narrow (bounds stay
        editable in the parameter details popup).
        """
        from chisurf.gui.autoform.sections.parameter_table import (
            PairedParameterTableWidget,
            ParameterGroupTableWidget,
        )

        tables = box.findChildren(ParameterGroupTableWidget) + box.findChildren(
            PairedParameterTableWidget
        )
        tables = [t for t in tables if t.has_bounds_columns()]
        if not tables:
            return

        btn = QtWidgets.QToolButton()
        btn.setCheckable(True)
        btn.setChecked(False)
        btn.setText("bounds")
        btn.setToolTip(
            "Show the Lo / Hi / Bounds columns\n"
            "(bounds are also editable in the parameter details popup)"
        )
        btn.setAutoRaise(True)
        btn.setFocusPolicy(QtCore.Qt.NoFocus)
        btn.setStyleSheet("QToolButton { font-size: 10px; padding: 0 4px; }")

        def _apply(checked: bool) -> None:
            for t in tables:
                t.set_bounds_visible(checked)

        btn.toggled.connect(_apply)
        _apply(False)  # start hidden
        box.add_header_widget(btn)

    def _build_dock_area(self, section: vs.DockAreaSection):
        """Render a declarative dock area: each child section becomes a dock tab.

        Uses the same ChiSurf ``DockArea`` the fit windows use, so the panels are
        rearrangeable / floatable but the layout is authored in the ``.view.json``.
        """
        from chisurf.gui.widgets.dock_area import DockArea

        area = DockArea()
        self._dock_areas.append(area)
        # Configure the ChiSurf dock the same way the fit windows / plugin panels
        # do, so it looks and behaves like every other ChiSurf dock area (styled
        # draggable tab bars, right-click menu) rather than a plain tab widget with
        # a "+" new-tab button.
        for setup in (
            lambda: area.setNewTabButtonVisible(False),
            lambda: area.setContextMenuEnabled(True),
            lambda: area.setContextMenuMode("basic"),
        ):
            try:
                setup()
            except Exception:
                pass
        # Let rebuild() give the dock area the spare vertical space instead of a trailing
        # stretch, so its panels fill the height.
        area._autoform_expanding = True
        area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        if getattr(section, "height", 0):
            area.setMinimumHeight(int(section.height))
        built: list[tuple[QtWidgets.QWidget, str]] = []
        for i, child in enumerate(section.sections):
            display_title = (
                getattr(child, "label", None) or getattr(child, "title", None) or f"Panel {i + 1}"
            )
            # Remove any raw attribute/fallback underscores from user-facing dock tab label
            display_title = str(display_title).replace("_", " ").strip()

            key_name = (
                getattr(child, "key", None) or getattr(child, "attr", None) or str(display_title).lower().replace(" ", "_")
            )
            try:
                if isinstance(child, vs.PanelSection):
                    # The dock tab already carries the panel's title, so render the panel's
                    # contents directly (no redundant outer collapsible) and wrap them in a
                    # scroll area so the tab expands vertically and scrolls when needed.
                    inner = QtWidgets.QWidget()
                    lay = QtWidgets.QVBoxLayout(inner)
                    lay.setContentsMargins(0, 0, 0, 0)
                    self._emit_sections(child.sections, lay.addWidget, fields_per_row=child.n_col)
                    # Give spare vertical space to an expanding child (a plot/image) if the
                    # panel has one; otherwise keep the fields top-aligned and compact with a
                    # trailing stretch (so form rows don't spread into large gaps).
                    expanding = False
                    for r in range(lay.count()):
                        w = lay.itemAt(r).widget()
                        if w is not None and getattr(w, "_autoform_expanding", False):
                            lay.setStretch(r, 1)
                            expanding = True
                    if not expanding:
                        lay.addStretch(1)
                    inner.setSizePolicy(
                        QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
                    )
                    widget = QtWidgets.QScrollArea()
                    widget.setWidgetResizable(True)
                    widget.setFrameShape(QtWidgets.QFrame.NoFrame)
                    widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
                    widget.setWidget(inner)
                else:
                    widget = self._build_section(child)
            except Exception:
                widget = None
            if widget is None:
                continue
            widget.setObjectName(str(key_name))
            built.append(
                (
                    widget,
                    str(display_title),
                    # Panels sharing a dock_group open as tabs in one split; a
                    # panel without one gets a split of its own, which is the
                    # behaviour every existing view already relies on.
                    str(getattr(child, "dock_group", "") or f"\0{i}"),
                    bool(getattr(child, "start_hidden", False)),
                )
            )

        groups: dict[str, list] = {}
        for widget, name, group_key, hidden in built:
            groups.setdefault(group_key, []).append((widget, name, hidden))

        split = (getattr(section, "split", "") or "").lower()
        if split in ("horizontal", "vertical") and len(groups) > 1:
            # Author-requested initial split: place the groups side-by-side (or
            # stacked) instead of tabbing them all. The user can still rearrange.
            zone = "right" if split == "horizontal" else "bottom"
            members = list(groups.values())

            def _attach(tab_widget, entries) -> None:
                """Add every panel of one group to the tab widget holding it."""
                for widget, name, _ in entries:
                    tab_widget.addTab(widget, name)
                    area._all_widgets.append(widget)
                    area._tab_names[widget] = name
                    try:
                        area.setTabCloseMode(widget, "hide")
                    except Exception:
                        pass

            first_widget, first_name, _ = members[0][0]
            area.addTab(first_widget, first_name)
            target_tw = area.find_main_tab_widget()
            _attach(target_tw, members[0][1:])
            for entries in members[1:]:
                new_tw = area._create_tab_widget()
                _attach(new_tw, entries)
                area.split_tab_widget(target_tw, new_tw, zone)
                target_tw = new_tw
            # Each split nests inside the previous one's second half, so group i
            # takes weights[i] against the sum of everything after it. Without
            # authored sizes an N-way split divides evenly, which beyond three
            # groups leaves every one of them too narrow to read.
            weights = [max(1, int(w)) for w in (getattr(section, "sizes", ()) or ())]
            if len(weights) != len(members):
                weights = [1] * len(members)
            splitter = getattr(area, "_root_widget", None)
            for i in range(len(members) - 1):
                if not isinstance(splitter, QtWidgets.QSplitter):
                    break
                rest = sum(weights[i + 1 :])
                try:
                    splitter.setSizes([weights[i], rest])
                    splitter.setStretchFactor(0, weights[i])
                    splitter.setStretchFactor(1, rest)
                except Exception:
                    break
                splitter = splitter.widget(1) if splitter.count() > 1 else None
        else:
            for widget, name, _, _ in built:
                try:
                    area.add_panel(widget, str(name))
                except Exception:
                    pass

        # Registered but out of the way: a panel that is reference material
        # rather than a working surface starts hidden and is one click away in
        # the dock's restore menu.
        for widget, _, _, hidden in built:
            if not hidden:
                continue
            try:
                index = area.indexOf(widget)
                if index >= 0:
                    area.hideTab(index)
            except Exception:
                pass
        # Remember the user's dock arrangement across sessions when the view asks
        # for it (all panels are added by now, so restore-on-show can find them).
        if getattr(section, "persist", ""):
            try:
                area.enable_persistence(section.persist)
            except Exception:
                pass
        return area

    def _build_wizard(self, section: vs.WizardSection):
        """Render a directed two-column wizard from a :class:`WizardSection`.

        Each step's body is built with the same ``_emit_sections`` used everywhere
        else, so the step controls bind to this form's model. The step-completion
        predicate reuses the ``{target, attr, equals}`` condition evaluator so a
        ``complete_when`` gates *Next* (in a linear wizard) and drives the ✓ mark.
        """
        from .sections.wizard_section import WizardWidget

        pages = []
        for step in section.steps:
            body = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(body)
            lay.setContentsMargins(0, 0, 0, 0)
            self._emit_sections(step.sections, lay.addWidget)
            # Give spare vertical space to an expanding child (an embedded editor
            # or plot); otherwise keep the fields top-aligned with a trailing stretch.
            expanding = False
            for r in range(lay.count()):
                w = lay.itemAt(r).widget()
                if w is not None and getattr(w, "_autoform_expanding", False):
                    lay.setStretch(r, 1)
                    expanding = True
            if not expanding:
                lay.addStretch(1)
            pages.append(body)

        def _is_complete(index, _steps=section.steps):
            cond = getattr(_steps[index], "complete_when", None)
            # A step with no explicit condition is treated as complete (an
            # informational step never blocks a linear wizard).
            return True if not cond else self._collapsed_when(cond)

        return WizardWidget(section, pages, _is_complete)

    def _collapsed_when(self, cond) -> bool:
        """Evaluate a ``{target, attr, equals|not_equals}`` condition against the model.

        Generic — used both for ``PanelSection.collapsed_when`` (fold) and
        ``PanelSection.hidden_when`` (fully hide); the truth value means "this
        condition is satisfied," the caller decides what that does.
        """
        if not cond:
            return False
        try:
            target = cond.get("target")
            group = getattr(self.model, target) if target else self.model
            value = getattr(group, cond["attr"])
            if "equals" in cond:
                return str(value).lower() == str(cond["equals"]).lower()
            if "not_equals" in cond:
                return str(value).lower() != str(cond["not_equals"]).lower()
            return False
        except Exception:
            return False

    def _build_curve_input(self, section: vs.CurveInputSection):
        from .sections.builtin import CurveInputWidget

        return CurveInputWidget(self.model, section)

    def _build_custom(self, section: vs.CustomSection):
        factory = get_section_factory(section.key)
        if factory is None:
            logging.warning(f"AutoModelWidget: no custom section registered for {section.key!r}")
            return None
        widget = factory(model=self.model, target=section.target, **dict(section.options))
        # Track AUTOFORM_REFRESH custom widgets (scalar/parameter tables, …) so
        # refresh_plots() still reaches them after a dock reparents/floats them.
        if widget is not None and getattr(widget, "AUTOFORM_REFRESH", False):
            self._refresh_targets.append(widget)
        if widget is None:
            return None
        # A custom section may carry a title like every other section; it used to
        # be silently dropped, so a panel with three `path_list`s showed three
        # unlabelled drop boxes and nothing said which took the IRF. The widget
        # supplies its own frame, so the caption is a plain label above it rather
        # than a second box around it.
        if not section.title:
            return widget
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        caption = QtWidgets.QLabel(section.title)
        caption.setStyleSheet("font-weight: bold;")
        # A label grows into spare vertical space like any other widget, and it
        # centres its text while doing so: next to a height-capped widget the
        # caption drifts into the middle of the panel, far from what it names.
        caption.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        if section.description:
            caption.setToolTip(section.description)
        layout.addWidget(caption)
        layout.addWidget(widget)
        # The hosting panel gives spare vertical space to expanding sections, and
        # that marker lives on the inner widget — carry it out to the wrapper.
        if getattr(widget, "_autoform_expanding", False):
            holder._autoform_expanding = True
        # ``section_widget`` must hand back the widget the factory built, not the
        # caption wrapper: a caller asking for a section by name wants the thing
        # with the API on it.
        holder._autoform_inner = widget
        return holder

    def _build_dynamic_group(self, section: vs.DynamicGroupSection):
        group = self._resolve_group(section.target)
        if group is None:
            return None

        # Outer container always holds header + rows (with or without CollapsibleBox)
        content = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(content)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(0)

        # header: add/del + any registered header widgets
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        add_btn = QtWidgets.QPushButton(section.add_label)
        add_btn.setStyleSheet(ADD_BUTTON_STYLE)
        del_btn = QtWidgets.QPushButton(section.remove_label)
        del_btn.setStyleSheet(REMOVE_BUTTON_STYLE)
        header.addWidget(add_btn)
        header.addWidget(del_btn)
        for key in section.header_keys:
            factory = get_section_factory(key)
            if factory is not None:
                try:
                    header.addWidget(factory(model=self.model, target=section.target))
                except Exception as exc:  # pragma: no cover - defensive
                    logging.warning(f"AutoModelWidget: header {key!r} failed: {exc}")
        outer.addLayout(header)

        def _row_params():
            if section.rows_source:
                fn = getattr(group, section.rows_source, None)
                return list(fn()) if callable(fn) else []
            return list(getattr(group, "parameters_all", []))

        # ``style: "table"`` renders the components as one paired QTableView (each
        # ``row_width`` group is a row with its columns side by side) instead of the
        # standalone spin-box grid. component_title (per-item fold boxes) keeps the
        # grid path since it is a fundamentally different layout.
        if getattr(section, "style", "grid") == "table" and not section.component_title:
            from chisurf.gui.autoform.sections.parameter_table import (
                PairedParameterTableWidget,
            )

            table = PairedParameterTableWidget(
                params=_row_params(),
                width=max(1, int(section.row_width)),
                on_change=self._dispatch_fit_update,
            )
            self._param_widgets.append(table)
            outer.addWidget(table)

            def on_add_table():
                add_fn = getattr(group, section.append_method, None)
                if callable(add_fn):
                    add_fn()
                self._dispatch_fit_update()
                table.set_params(_row_params())
                self.refresh_plots()

            def on_del_table():
                if len(_row_params()) // max(1, section.row_width) > section.min_rows:
                    del_fn = getattr(group, section.remove_method, None)
                    if callable(del_fn):
                        del_fn()
                        self._dispatch_fit_update()
                        table.set_params(_row_params())
                        self.refresh_plots()

            add_btn.clicked.connect(on_add_table)
            del_btn.clicked.connect(on_del_table)

            if not getattr(section, "collapsible", True):
                return content
            box = self._make_fold_box(section, fallback_title=getattr(group, "name", ""))
            box.add_widget(content)
            return box

        # rows host: VBox for per-component fold groups, Grid for flat params
        rows_host = QtWidgets.QWidget()
        if section.component_title:
            rows_layout = QtWidgets.QVBoxLayout(rows_host)
        else:
            rows_layout = QtWidgets.QGridLayout(rows_host)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)
        outer.addWidget(rows_host)

        def render_rows():
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
            params = _row_params()
            width = max(1, int(section.row_width))
            if section.component_title:
                # Each row_width chunk of params gets its own CollapsibleBox
                from chisurf.gui.widgets.collapsible_box import CollapsibleBox

                n = len(params) // width if width else 0
                for comp_idx in range(n):
                    chunk = params[comp_idx * width : (comp_idx + 1) * width]
                    comp_box = CollapsibleBox(
                        f"{section.component_title} {comp_idx + 1}", expanded=True
                    )
                    row_widget = QtWidgets.QWidget()
                    row_grid = QtWidgets.QGridLayout(row_widget)
                    row_grid.setContentsMargins(0, 0, 0, 0)
                    row_grid.setSpacing(0)
                    for j, p in enumerate(chunk):
                        label = p.__dict__.get("label_text", p.name)
                        pw = make_fitting_parameter_widget(fitting_parameter=p, label_text=label)
                        row_grid.addWidget(pw, 0, j)
                        self._param_widgets.append(pw)
                    comp_box.add_widget(row_widget)
                    rows_layout.addWidget(comp_box)
            else:
                batch = []
                for i, p in enumerate(params):
                    label = p.__dict__.get("label_text", p.name)
                    pw = make_fitting_parameter_widget(fitting_parameter=p, label_text=label)
                    rows_layout.addWidget(pw, i // width, i % width)
                    self._param_widgets.append(pw)
                    batch.append(pw)
                _align_label_columns(batch)

        def on_add():
            add_fn = getattr(group, section.append_method, None)
            if callable(add_fn):
                add_fn()
            self._dispatch_fit_update()
            render_rows()
            self.refresh_plots()

        def on_del():
            if len(_row_params()) // max(1, section.row_width) > section.min_rows:
                del_fn = getattr(group, section.remove_method, None)
                if callable(del_fn):
                    del_fn()
                    self._dispatch_fit_update()
                    render_rows()
                    self.refresh_plots()

        add_btn.clicked.connect(on_add)
        del_btn.clicked.connect(on_del)
        render_rows()

        if not getattr(section, "collapsible", True):
            # No wrapper box — used when section is already inside a PanelSection
            return content

        box = self._make_fold_box(section, fallback_title=getattr(group, "name", ""))
        box.add_widget(content)
        return box

    # -- helpers ------------------------------------------------------------
    def _dispatch_fit_update(self):
        try:
            fit = getattr(self.model, "fit", None)
            fits = cs.fits if hasattr(cs, "fits") else []
            idx = next((i for i, f in enumerate(fits) if f is fit), 0)
            cs.core.actions.dispatch(name="fit.update", payload={"fit_index": int(idx)})
        except Exception:  # pragma: no cover - dispatcher optional in tests
            pass
        callback = getattr(self.model, "_on_changed", None) or getattr(self.model, "on_changed", None)
        if callable(callback):
            try:
                callback()
            except Exception:
                pass
        self.refresh_plots()

    @staticmethod
    def _collect_param_widgets(group_widget):
        from chisurf.gui.widgets.fitting import FittingParameterWidget

        return group_widget.findChildren(FittingParameterWidget)


#: Backwards-compatible alias from the PRD-38 model-only name.
AutoModelWidget = AutoForm
