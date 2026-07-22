"""Populate the photon-filter wizard's burst-search combobox from tttrlib.

The wizard's built-in modes each own a slice of a fixed set of Qt Designer
spinboxes, which ``tttr_photon_filter_mode.update_parameter_visibility`` relabels,
re-ranges and re-tooltips whenever the mode changes. Adding an algorithm means
editing the .ui file, that relabelling code, a settings dataclass and the
marshalling code, and the algorithm-to-widget mapping lives implicitly in widget
names like ``doubleSpinBox_7``.

tttrlib publishes its burst searches — names, labels, summaries and a JSON Schema
of each one's parameters — through ``TTTR.burst_search_algorithms()``. This module
turns that description into combobox entries and into the parameter widgets
themselves, using chisurf's existing JSON-Schema form generator
(:class:`~chisurf.core.dataspec.rpc.RpcMethodView` + :class:`AutoForm`). A burst
search added to tttrlib therefore appears in this wizard, with correct labels,
ranges, units, tooltips and defaults, without touching this file or the .ui.

The wizard's own modes are left exactly as they are: they include algorithms
tttrlib does not implement (count rate, BOCPD, Kalman), and existing projects
store their names.
"""

from __future__ import annotations

import logging
import sys
import typing

from chisurf.gui import QtCore, QtWidgets

from chisurf.core import tttrlib_registry
from chisurf.core.fluorescence.burst import tttrlib_search
from chisurf.gui.autoform import AutoForm

logger = logging.getLogger(__name__)

#: Item-data role holding the tttrlib algorithm name on registry-backed entries.
#: The name is carried as data rather than matched from the visible text so that
#: a label change in tttrlib cannot silently break mode resolution.
ALGORITHM_ROLE = QtCore.Qt.UserRole + 101

#: Widgets the wizard reuses across its built-in modes. All are hidden while a
#: registry-backed algorithm is selected, because its parameters are generated
#: instead. Named here rather than derived, since the .ui offers nothing to
#: distinguish "burst parameter widget" from any other spinbox on the page.
_BUILTIN_PARAMETER_WIDGETS = (
    "label", "label_2", "label_11", "label_12", "label_13", "label_14",
    "label_15", "label_16", "label_17", "label_18",
    "spinBox", "spinBox_7", "spinBox_8", "spinBox_9",
    "doubleSpinBox", "doubleSpinBox_5", "doubleSpinBox_6", "doubleSpinBox_7",
    "doubleSpinBox_8", "doubleSpinBox_9", "doubleSpinBox_10",
)


def install(page) -> bool:
    """Append tttrlib's burst searches to the combobox and prepare their form.

    Returns
    -------
    bool
        Whether any algorithm was added — ``False`` on a tttrlib too old to
        publish a registry, in which case the wizard keeps its built-in modes
        only and nothing else here applies.
    """
    algorithms = tttrlib_search.algorithms()
    page._tttrlib_algorithms = algorithms
    page._tttrlib_view = None
    page._tttrlib_form = None
    page._tttrlib_container = None
    page._tttrlib_current = None
    page._tttrlib_pending_values = None
    if not algorithms:
        # Degrading silently here is what makes "the dropdown has no new entries"
        # impossible to tell apart from "the GUI code never ran": both look
        # identical. Say which tttrlib was loaded and what it lacked, because the
        # cause is almost always a second interpreter or an out-of-date build
        # rather than anything about this page.
        import tttrlib
        logger.warning(
            "no tttrlib burst-search registry: the built-in filter modes are the "
            "only ones offered. Loaded tttrlib is %s (has registry(): %s, has "
            "TTTR.burst_search_algorithms(): %s); rebuild or upgrade tttrlib in "
            "the interpreter running chisurf (%s).",
            getattr(tttrlib, "__file__", "?"),
            hasattr(tttrlib, "registry"),
            hasattr(tttrlib.TTTR, "burst_search_algorithms"),
            sys.executable,
        )
        return False
    logger.info(
        "tttrlib burst-search registry: added %d search(es) to the filter modes "
        "(%s) from %s",
        len(algorithms), ", ".join(sorted(algorithms)),
        getattr(__import__("tttrlib"), "__file__", "?"),
    )

    combo = page.comboBox_burst_filter
    combo.blockSignals(True)
    # The hand-written modes are gone: every burst search now comes from
    # tttrlib's registry, so the list is cleared rather than appended to. Keeping
    # both sets meant two implementations of the same searches, two parameter
    # editors, and two dispatch paths -- which is where most of the recent bugs
    # came from.
    combo.clear()
    for name, spec in algorithms.items():
        combo.addItem(spec.get("label", name))
        index = combo.count() - 1
        combo.setItemData(index, name, ALGORITHM_ROLE)
        combo.setItemData(index, spec.get("summary", ""), QtCore.Qt.ToolTipRole)
    combo.blockSignals(False)

    # The generated widgets go in their own container, so showing or hiding the
    # whole generated form is one call and never disturbs the built-in widgets.
    container = QtWidgets.QWidget(page)
    box = QtWidgets.QVBoxLayout(container)
    box.setContentsMargins(0, 0, 0, 0)
    container.setVisible(False)
    # Sit inside the generated filter-settings container, below the mode
    # selector both editors share, so exactly one parameter editor occupies one
    # place. Parenting it elsewhere left the panel blank whenever a registry
    # search was selected.
    # Right column of the splitter: the selected search's parameters sit beside
    # the settings that apply to every search, rather than below them.
    host = getattr(page, "_filter_settings_right", None)
    if host is None:
        host = getattr(page, "_filter_settings_container", None)
    layout = host.layout() if host is not None else None
    if layout is None:
        layout = combo.parentWidget().layout() if combo.parentWidget() else None
    if layout is not None:
        # Before the trailing stretch, so the panels stay top-aligned.
        layout.insertWidget(max(0, layout.count() - 1), container)
    page._tttrlib_container = container
    return True


def selected_algorithm(page) -> typing.Optional[str]:
    """Name of the selected tttrlib algorithm, or ``None`` for a built-in mode."""
    combo = getattr(page, "comboBox_burst_filter", None)
    if combo is None:
        return None
    return combo.itemData(combo.currentIndex(), ALGORITHM_ROLE)


def parameters(page) -> typing.Dict[str, typing.Any]:
    """Current values of the generated parameter form.

    Falls back to the algorithm's registry defaults when the form has not been
    built yet, so a caller reading settings before the page is shown still gets a
    complete, valid parameter set.
    """
    view = getattr(page, "_tttrlib_view", None)
    if view is not None:
        return view.params()
    algorithm = selected_algorithm(page)
    if algorithm is None:
        return {}
    return tttrlib_search.defaults(algorithm)


def select(page, algorithm: str, values: typing.Optional[typing.Mapping] = None) -> bool:
    """Select ``algorithm`` in the combobox and load ``values`` into its form.

    Returns whether the algorithm was found, so callers restoring a saved project
    can fall back when it names a search this tttrlib does not have.
    """
    combo = getattr(page, "comboBox_burst_filter", None)
    if combo is None:
        return False
    for index in range(combo.count()):
        if combo.itemData(index, ALGORITHM_ROLE) == algorithm:
            page._tttrlib_pending_values = dict(values or {})
            combo.setCurrentIndex(index)
            apply_visibility(page)
            return True
    return False


def apply_visibility(page) -> bool:
    """Show the generated form for a registry algorithm, hiding the built-ins.

    Returns
    -------
    bool
        ``True`` when a registry algorithm is selected and this module has taken
        over the parameter area — the caller should then skip its own per-mode
        widget handling entirely.
    """
    container = getattr(page, "_tttrlib_container", None)
    if container is None:
        return False

    algorithm = selected_algorithm(page)
    if algorithm is None:
        container.setVisible(False)
        return False

    # The generated form is no longer hidden here. It used to hold the built-in
    # searches' parameters, which a registry search replaces; now it holds only
    # settings that apply whichever search runs -- channel selection, the
    # macro-time interval, enable/invert -- so hiding it took away controls the
    # user still needs.
    for name in _BUILTIN_PARAMETER_WIDGETS:
        widget = getattr(page, name, None)
        if widget is not None:
            widget.setVisible(False)

    _rebuild_form(page, algorithm)
    container.setVisible(True)
    return True


def _rebuild_form(page, algorithm: str) -> None:
    """Build the generated form for ``algorithm``, if it is not already current.

    ``apply_visibility`` runs on every mode change and on page initialisation, so
    rebuilding unconditionally would discard whatever the user had typed each
    time. Rebuild only when the algorithm actually changed, or when values are
    waiting to be loaded into it.
    """
    spec = page._tttrlib_algorithms.get(algorithm)
    if spec is None:
        return
    # Values are per algorithm, so a switch starts from that algorithm's defaults
    # rather than carrying over values that may not even apply to it.
    values = getattr(page, "_tttrlib_pending_values", None)
    page._tttrlib_pending_values = None
    if values is None and algorithm == getattr(page, "_tttrlib_current", None):
        if getattr(page, "_tttrlib_view", None) is not None:
            return

    notify = getattr(getattr(page, "actionUpdate_Values", None), "trigger", None)

    def on_change():
        if notify is not None:
            notify()
        # A composite entry's nested panel is built from whichever inner entry
        # its selector names, so changing that selector makes the panel stale.
        # The rebuild is deferred: this runs from inside a widget's own signal,
        # and tearing that widget down synchronously is not safe.
        view = getattr(page, "_tttrlib_view", None)
        should = getattr(view, "should_rebuild", None)
        if should is not None and should(getattr(page, "_tttrlib_selector", None)):
            QtCore.QTimer.singleShot(0, lambda: _rebuild_nested(page, algorithm))

    # Built through the generic registry helper, so the same call renders any
    # registry category rather than only burst searches, and an entry that
    # delegates part of its schema to another entry (the coincident search runs
    # whichever search you name inside each detector group) gets that entry's
    # parameters as a nested panel instead of a JSON text box.
    view = tttrlib_registry.entry_form_view_auto(
        tttrlib_registry.BURST_SEARCH, algorithm,
        values=values or None, on_change=on_change,
    )
    form = AutoForm(view)
    page._tttrlib_selector = getattr(view, "selector_value", None)

    box = page._tttrlib_container.layout()
    while box.count():
        item = box.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
    box.addWidget(form)
    page._tttrlib_view = view
    page._tttrlib_form = form
    page._tttrlib_current = algorithm


def _rebuild_nested(page, algorithm: str) -> None:
    """Rebuild a composite form after its inner selection changed.

    The values already entered are carried across, so switching the inner search
    does not discard the outer settings (the detector grouping above all, which
    is tedious to retype and cannot be defaulted).
    """
    view = getattr(page, "_tttrlib_view", None)
    if view is None or not hasattr(view, "should_rebuild"):
        return
    page._tttrlib_pending_values = view.params()
    page._tttrlib_current = None      # force the guard in _rebuild_form to pass
    _rebuild_form(page, algorithm)
