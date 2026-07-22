"""Filter settings as a generated form rather than a Qt Designer page.

Scope note: the burst-search parameters are **not** here. They come from
tttrlib's registry and are rendered from the JSON Schema it publishes, so there
is one implementation of each search and one editor for its parameters. This
module covers the settings that are not part of any search -- channel selection,
the macro-time interval, and the enable/invert switches.


The photon-filter page was authored in Qt Designer, and the burst-search
parameters were a fixed pool of spinboxes (``doubleSpinBox_5`` … ``_10``) that
``tttr_photon_filter_mode`` relabelled, re-ranged and re-tooltipped whenever the
mode changed. The mapping from algorithm to widget lived implicitly in those
names, so adding a search meant editing the ``.ui``, the relabelling code, a
settings dataclass and the marshalling code — four places, none of which the
compiler or the tests could keep in step.

This module states the same controls as **data**: a settings object plus a
:class:`~chisurf.core.dataspec.ModelView` describing how to edit it, rendered by
:class:`~chisurf.gui.autoform.AutoForm`. Labels, ranges, units, tooltips and fold
state come from the spec, so a control is declared once and the widget for it is
generated. The panels are :class:`PanelSection`, which is foldable, so the page
gets the same collapsible sections as the light-path simulator without any
hand-written show/hide logic.

The registry-driven searches already render this way, from the JSON Schema
tttrlib publishes. Describing the built-in modes here means *every* filter mode
now reaches the screen through one renderer, from one kind of declaration.

Scope: this covers the filter-settings controls — channel selection, the macro
time interval and the filter parameters. The plots and file handling on the
wizard page are untouched.
"""

from __future__ import annotations

import dataclasses
import typing

from chisurf.core.dataspec import (
    ChoiceSection,
    ModelView,
    PanelSection,
    ToggleSection,
    ValueSection,
)

#: Selection meaning "do not restrict to one detector / time window". The
#: Designer combo offered this as an explicit entry and the page's sync methods
#: already understand it, so it is spelled the same way here.
ALL = "All"

#: Built-in filter modes, as (value written to the model, label shown).
BUILTIN_MODES: typing.Tuple[typing.Tuple[str, str], ...] = (
    ("count_rate", "Count rate"),
    ("burst", "Burst"),
    ("kalman", "Kalman Burst"),
    ("cusum", "CUSUM Burst"),
)


@dataclasses.dataclass
class FilterSettings:
    """The values the filter-settings panel edits.

    A plain dataclass so the settings can be read, saved and tested without Qt;
    the form is only a view of it.
    """

    # -- channel selection ----------------------------------------------------
    detector: str = ALL
    window: str = ALL

    # -- macro time interval --------------------------------------------------
    dt_min: float = 0.001
    dt_max: float = 0.150
    dt_min_active: bool = False
    dt_max_active: bool = True
    merge_gap: int = 3
    use_gap_fill: bool = True

    # -- filter ---------------------------------------------------------------
    #: Time window in **milliseconds**, matching the label on the control.
    #: Consumers want seconds; use :meth:`time_window_seconds` rather than
    #: reading this directly, or the threshold is off by a factor of 1000.
    mode: str = "burst"
    filter_active: bool = True
    invert: bool = False
    min_photons: int = 60
    photon_window: int = 5
    time_window: float = 0.5

    # -- CUSUM ----------------------------------------------------------------
    background_rate: float = 2000.0
    sb_ratio: float = 30.0
    alpha: float = 0.05
    beta: float = 0.05

    # -- Kalman ---------------------------------------------------------------
    kalman_q: float = 0.01
    kalman_r_scale: float = 0.1
    kalman_z_thresh: float = 3.0
    kalman_min_len: int = 2
    kalman_merge_gap: int = 5

    def time_window_seconds(self) -> float:
        """The burst time window in seconds.

        The control is labelled and edited in milliseconds; every consumer of it
        works in seconds. Converting here keeps the one conversion in one place.
        """
        return float(self.time_window) * 1e-3


def _mode_panel(settings: FilterSettings) -> PanelSection:
    """The parameter panel for the currently selected built-in mode.

    Each mode gets its *own* panel containing only its parameters, rather than
    every mode borrowing from one pool of spinboxes. That is what removes the
    relabelling: switching mode rebuilds this panel instead of rewriting a
    widget's text, range and tooltip in place.
    """
    common = (
        ValueSection(
            target="settings", attr="min_photons", label="Min photons", kind="int",
            minimum=1, maximum=100000,
            description="Bursts with fewer photons than this are discarded.",
        ),
    )
    if settings.mode == "count_rate":
        sections = common + (
            ValueSection(
                target="settings", attr="photon_window", label="Photons / window",
                kind="int", minimum=1, maximum=10000,
                description="Photons used to compute the local count rate.",
            ),
            ValueSection(
                target="settings", attr="time_window", label="Time window",
                kind="float", minimum=1e-6, maximum=1000.0, decimals=4, suffix=" ms",
                description="Window length for the count-rate threshold.",
            ),
        )
    elif settings.mode == "burst":
        sections = common + (
            ValueSection(
                target="settings", attr="photon_window", label="Window size",
                kind="int", minimum=2, maximum=1000,
                description="Consecutive photons used for the rate (m).",
            ),
            ValueSection(
                target="settings", attr="time_window", label="Window duration",
                kind="float", minimum=1e-6, maximum=1000.0, decimals=4, suffix=" ms",
                description="Maximum separation of m photons inside a burst (T).",
            ),
        )
    elif settings.mode == "cusum":
        sections = common + (
            ValueSection(
                target="settings", attr="background_rate", label="Background rate",
                kind="float", minimum=0.0, maximum=1e9, decimals=1, suffix=" cps",
                description="Background count rate; 0 estimates it from the data.",
            ),
            ValueSection(
                target="settings", attr="sb_ratio", label="Signal / background",
                kind="float", minimum=0.0, maximum=1000.0, decimals=2,
                description="Burst brightness relative to background; 0 auto-estimates.",
            ),
            ValueSection(
                target="settings", attr="alpha", label="False-positive rate",
                kind="float", minimum=1e-6, maximum=0.5, decimals=4,
                description="Probability of calling background a burst.",
            ),
            ValueSection(
                target="settings", attr="beta", label="False-negative rate",
                kind="float", minimum=1e-6, maximum=0.5, decimals=4,
                description="Probability of missing a real burst.",
            ),
        )
    elif settings.mode == "kalman":
        sections = common + (
            ValueSection(
                target="settings", attr="kalman_q", label="Process noise",
                kind="float", minimum=0.0, maximum=1e6, decimals=4,
                description="How fast the filter believes the rate itself changes.",
            ),
            ValueSection(
                target="settings", attr="kalman_r_scale", label="Measurement noise",
                kind="float", minimum=1e-6, maximum=1000.0, decimals=4,
                description="Scale on the Poisson measurement variance.",
            ),
            ValueSection(
                target="settings", attr="kalman_z_thresh", label="Z threshold",
                kind="float", minimum=0.0, maximum=100.0, decimals=2,
                description="Innovation distance above which a bin is in a burst.",
            ),
            ValueSection(
                target="settings", attr="kalman_min_len", label="Min length",
                kind="int", minimum=1, maximum=10000,
                description="Minimum consecutive bins over threshold.",
            ),
            ValueSection(
                target="settings", attr="kalman_merge_gap", label="Merge gap",
                kind="int", minimum=0, maximum=10000,
                description="Merge bursts separated by at most this many bins.",
            ),
        )
    else:
        sections = common

    label = dict(BUILTIN_MODES).get(settings.mode, settings.mode)
    return PanelSection(
        title=f"{label} parameters", n_col=2, sections=sections,
    )


def filter_settings_view(
    settings: FilterSettings,
    detectors: typing.Sequence[str] = (),
    windows: typing.Sequence[str] = (),
) -> ModelView:
    """Describe the filter-settings editor for ``settings``.

    Panels fold, and channel selection starts folded: it is chosen once per
    setup, whereas the filter parameters are what a user iterates on. The page
    competes for vertical space with the plots below it, so defaulting the
    rarely-touched panel closed is worth more than it costs.
    """
    channel = PanelSection(
        title="Channel selection", collapsed=True, n_col=2,
        sections=(
            ChoiceSection(
                target="settings", attr="detector", label="Detector",
                options=(ALL,) + tuple(d for d in detectors if d != ALL),
                description="Detector definition applied to the photon stream. "
                            "'All' uses every channel.",
            ),
            ChoiceSection(
                target="settings", attr="window", label="Time window",
                options=(ALL,) + tuple(w for w in windows if w != ALL),
                description="Named micro-time window applied to the photon "
                            "stream. 'All' uses the full micro-time range.",
            ),
        ),
    )
    # Two columns throughout: a single column made the panel taller than the
    # plots it shares the page with, and these are short labelled fields that
    # pair naturally.
    macro_time = PanelSection(
        title="Macro time interval", n_col=2,
        sections=(
            ToggleSection(
                target="settings", attr="dt_min_active", label="Use lower bound"),
            ValueSection(
                target="settings", attr="dt_min", label="min dMT", kind="float",
                minimum=0.0, maximum=1e6, decimals=4, suffix=" ms",
                description="Discard photons closer together than this.",
            ),
            ToggleSection(
                target="settings", attr="dt_max_active", label="Use upper bound"),
            ValueSection(
                target="settings", attr="dt_max", label="max dMT", kind="float",
                minimum=0.0, maximum=1e6, decimals=4, suffix=" ms",
                description="Discard photons further apart than this.",
            ),
            ValueSection(
                target="settings", attr="merge_gap", label="Merge gap", kind="int",
                minimum=0, maximum=100000,
                description="Bridge gaps of at most this many photons inside a burst.",
            ),
        ),
    )
    # The mode itself is chosen by the wizard's combobox, which also lists the
    # registry-driven searches; duplicating it here would give two controls for
    # one setting.
    filter_panel = PanelSection(
        title="Filter", n_col=2,
        sections=(
            ToggleSection(target="settings", attr="filter_active", label="Enable"),
            ToggleSection(target="settings", attr="invert", label="Invert"),
        ),
    )
    # No per-mode parameter panel any more: the burst-search parameters come
    # from tttrlib's registry and are rendered from its JSON Schema. What is left
    # here is what is *not* a burst-search parameter -- the channel selection,
    # the macro-time interval and the enable/invert switches.
    return ModelView(sections=(channel, macro_time, filter_panel))


class _NotifyingSettings:
    """Attribute proxy over :class:`FilterSettings` that reports every edit.

    AutoForm commits a widget's value with ``setattr`` on the object a section
    targets. A plain dataclass accepts that silently, so every edit in the
    generated form changed the value and told nobody — the plots did not
    refresh and no downstream recompute ran. The registry-driven form never had
    this problem because its binding group notifies on write; this gives the
    built-in form the same behaviour.

    Reads and writes pass straight through, so the dataclass stays the single
    source of truth and the page's properties keep reading it directly.
    """

    def __init__(self, settings: "FilterSettings", on_change=None):
        object.__setattr__(self, "_settings", settings)
        object.__setattr__(self, "_on_change", on_change)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_settings"), name)

    def __setattr__(self, name, value):
        settings = object.__getattribute__(self, "_settings")
        previous = getattr(settings, name, object())
        setattr(settings, name, value)
        if previous == value:
            return          # a widget re-emitting its own value is not an edit
        callback = object.__getattribute__(self, "_on_change")
        if callback is not None:
            callback()


class FilterSettingsModel:
    """AutoForm model wrapping :class:`FilterSettings`.

    ``AutoForm`` resolves each section's ``target`` with ``getattr``, so the
    settings object is exposed as ``settings``. Changing the mode changes which
    parameter panel applies, so callers rebuild the form on
    :meth:`mode_changed`; the settings object survives, and with it every value
    already entered.
    """

    def __init__(
        self,
        settings: typing.Optional[FilterSettings] = None,
        detectors: typing.Union[typing.Sequence[str], typing.Callable] = (),
        windows: typing.Union[typing.Sequence[str], typing.Callable] = (),
        on_change: typing.Optional[typing.Callable] = None,
    ):
        raw = settings if settings is not None else FilterSettings()
        #: The dataclass itself, for callers that read values directly.
        self.filter_settings = raw
        #: What the form binds to: the same values, but reporting every edit.
        self.settings = _NotifyingSettings(raw, on_change)
        # Accept callables as well as sequences: detectors and time windows are
        # filled after a setup or a file is loaded, so a list captured at
        # construction would leave the choices empty for the rest of the session.
        self._detectors = detectors
        self._windows = windows
        self._on_change = on_change
        self._built_for = self.settings.mode
        self._built_options = self.options()

    @staticmethod
    def _resolve(source) -> typing.Tuple[str, ...]:
        if callable(source):
            try:
                source = source()
            except Exception:
                source = ()
        return tuple(source or ())

    def options(self) -> typing.Tuple[typing.Tuple[str, ...], typing.Tuple[str, ...]]:
        """The detector and time-window choices as they stand right now."""
        return self._resolve(self._detectors), self._resolve(self._windows)

    def options_changed(self) -> bool:
        """Whether the available choices moved on since the form was built."""
        return self._built_options != self.options()

    def view_spec(self) -> ModelView:
        self._built_for = self.filter_settings.mode
        self._built_options = self.options()
        detectors, windows = self._built_options
        return filter_settings_view(self.filter_settings, detectors, windows)

    def mode_changed(self) -> bool:
        """Whether the mode moved away from the one the form was built for."""
        return self._built_for != self.filter_settings.mode


def install_filter_settings_form(page) -> None:
    """Replace the page's Designer filter groups with the generated form.

    The three group boxes authored in Qt Designer — channel selection, macro time
    interval and filter — are hidden and a single :class:`AutoForm` built from
    :func:`filter_settings_view` takes their place. The widgets are hidden rather
    than deleted: the wizard and the burst-selection tool still reference several
    of them by Designer name for plots and file handling, and deleting them would
    break those before the rest of the page has been converted.

    ``page.filter_settings`` becomes the source of truth for every value the form
    edits; the page's properties read it, so a control moved into the form keeps
    its public accessor unchanged.
    """
    from chisurf.gui.autoform import AutoForm
    from qtpy import QtCore, QtWidgets

    settings = FilterSettings()
    # Seed from the Designer defaults so the converted page starts where the old
    # one did rather than at this module's own defaults.
    for attr, widget_name, cast in (
        ("merge_gap", "spinBox_7", int),
        ("min_photons", "spinBox", int),
        ("photon_window", "spinBox_8", int),
        ("background_rate", "doubleSpinBox_5", float),
        ("sb_ratio", "doubleSpinBox_6", float),
        ("alpha", "doubleSpinBox_7", float),
        ("beta", "doubleSpinBox_8", float),
        ("kalman_r_scale", "doubleSpinBox_9", float),
        ("kalman_z_thresh", "doubleSpinBox_10", float),
        ("kalman_min_len", "spinBox_9", int),
    ):
        widget = getattr(page, widget_name, None)
        if widget is not None:
            try:
                setattr(settings, attr, cast(widget.value()))
            except Exception:
                pass
    for attr, widget_name in (
        ("dt_min_active", "checkBox_2"),
        ("dt_max_active", "checkBox_3"),
        ("use_gap_fill", "checkBox_5"),
        ("filter_active", "checkBox_4"),
        ("invert", "checkBox"),
    ):
        widget = getattr(page, widget_name, None)
        if widget is not None:
            try:
                setattr(settings, attr, bool(widget.isChecked()))
            except Exception:
                pass
    # `enable` and `invert` are marshalled from the page's settings dict, not
    # from those checkboxes, and the page writes that dict after the widgets are
    # built - so the checkbox and the value the analysis uses can disagree. Seed
    # from the dict, which is the one that decides.
    page_settings = getattr(page, "settings", None)
    if isinstance(page_settings, dict):
        if "invert_filter" in page_settings:
            settings.invert = bool(page_settings["invert_filter"])
        if "filter_active" in page_settings:
            settings.filter_active = bool(page_settings["filter_active"])
    settings.dt_min = float(getattr(page, "_dT_min", settings.dt_min))
    settings.dt_max = float(getattr(page, "_dT_max", settings.dt_max))

    page.filter_settings = settings
    notify = getattr(getattr(page, "actionUpdate_Values", None), "trigger", None)

    def on_change():
        # dT is read from private attributes elsewhere on the page, so keep them
        # in step rather than hunting down every reader during the conversion.
        page._dT_min = page.filter_settings.dt_min
        page._dT_max = page.filter_settings.dt_max
        # Detector and time window feed the channel and micro-time-range fields
        # the rest of the page reads. Rather than reimplement that mapping, drive
        # the original combos: they still carry the page's own sync handlers, so
        # one assignment updates every element that depended on them.
        _mirror_selection(page, "comboBox_2", page.filter_settings.detector)
        _mirror_selection(page, "comboBox_3", page.filter_settings.window)
        # Restore the millisecond -> second conversion the Designer path applied
        # on read. Without it a window labelled "0.5 ms" reaches the search as
        # 0.5 s, i.e. a ~10 Hz threshold, and the whole trace becomes one burst.
        try:
            page.settings["count_rate_filter"]["time_window"] = \
                page.filter_settings.time_window_seconds()
        except (AttributeError, KeyError, TypeError):
            pass
        # Push into the Designer widgets *before* notifying: the update the
        # notification triggers rebuilds the settings dict from exactly those
        # widgets, so this is what makes an edit survive.
        _mirror_to_widgets(page)
        _mirror_region(page)
        # Re-read the model into the generated form's own controls. An edit that
        # originates outside the form — dragging the delta-macro-time region,
        # which writes settings.dt_min/dt_max straight into the model — otherwise
        # never reaches the "min dMT"/"max dMT" fields, so the numbers stayed
        # frozen while the region and the analysis moved. sync() blocks signals,
        # so refreshing the field a user is editing is a harmless no-op.
        _sync_form_fields(page)
        if notify is not None:
            notify()
        if page._filter_settings_model.mode_changed():
            QtCore.QTimer.singleShot(0, lambda: _rebuild_filter_form(page))

    page._filter_settings_model = FilterSettingsModel(
        settings,
        detectors=lambda: list(getattr(page, "detectors", {}) or {}),
        windows=lambda: list(getattr(page, "windows", {}) or {}),
        on_change=on_change,
    )

    container = QtWidgets.QWidget(page)
    box = QtWidgets.QVBoxLayout(container)
    box.setContentsMargins(0, 0, 0, 0)
    page._filter_settings_container = container

    # The mode selector lives inside the filter group box in the .ui, so hiding
    # that group would hide the one control the whole page is steered by. Move it
    # (with its label) to the top of the generated form, above the panels whose
    # contents it decides.
    mode_row = QtWidgets.QWidget(container)
    mode_layout = QtWidgets.QHBoxLayout(mode_row)
    mode_layout.setContentsMargins(0, 0, 0, 0)
    mode_label = getattr(page, "label_10", None)
    if mode_label is None:
        mode_label = QtWidgets.QLabel("Filter mode", mode_row)
    mode_layout.addWidget(mode_label)
    mode_layout.addWidget(page.comboBox_burst_filter, 1)
    box.addWidget(mode_row)
    page._filter_mode_row = mode_row

    # Two resizable columns instead of one tall stack: the settings that apply to
    # every search on the left, the selected search's own parameters on the
    # right. Stacked vertically these ran past the bottom of the panel and stole
    # height from the plots; side by side they fit, and the splitter lets a user
    # give whichever side they are working on more room.
    splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, container)
    splitter.setChildrenCollapsible(True)

    left = QtWidgets.QWidget(splitter)
    left_box = QtWidgets.QVBoxLayout(left)
    left_box.setContentsMargins(0, 0, 0, 0)
    left_box.addStretch(1)          # keeps panels top-aligned as they fold
    splitter.addWidget(left)

    right = QtWidgets.QWidget(splitter)
    right_box = QtWidgets.QVBoxLayout(right)
    right_box.setContentsMargins(0, 0, 0, 0)
    right_box.addStretch(1)
    splitter.addWidget(right)

    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)
    page._filter_settings_right_box = right_box
    box.addWidget(splitter, 1)
    page._filter_settings_splitter = splitter
    page._filter_settings_left = left
    page._filter_settings_right = right

    # A generated form is taller than the compact Designer panel it replaces, and
    # a search with a dozen parameters would otherwise squeeze the delta
    # macro-time plot below it down to a sliver. Bounding the height and letting
    # the form scroll keeps the plot usable whichever mode is selected.
    scroller = QtWidgets.QScrollArea(page)
    scroller.setWidgetResizable(True)
    scroller.setFrameShape(QtWidgets.QFrame.NoFrame)
    scroller.setMaximumHeight(320)
    scroller.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    scroller.setWidget(container)
    page._filter_settings_scroller = scroller

    replaced = False
    for name in ("groupBox_3", "groupBox_2", "groupBox"):
        group = getattr(page, name, None)
        if group is None:
            continue
        if not replaced:
            parent_layout = group.parentWidget().layout() if group.parentWidget() else None
            index = parent_layout.indexOf(group) if parent_layout else -1
            if parent_layout is not None and index >= 0:
                if isinstance(parent_layout, QtWidgets.QGridLayout):
                    row, column, row_span, column_span = \
                        parent_layout.getItemPosition(index)
                    parent_layout.addWidget(scroller, row, column, row_span, column_span)
                else:
                    parent_layout.insertWidget(index, scroller)
                replaced = True
        group.hide()
    if not replaced:
        # No layout to graft onto (a stripped-down page in a test): the form is
        # still built and bound, it simply has nowhere to be shown.
        scroller.setParent(page)

    _rebuild_filter_form(page)


#: Every generated control and the Designer widget that still backs it.
#: (attribute on FilterSettings, widget name, kind)
_WIDGET_MIRROR = (
    ("invert", "checkBox", "check"),
    ("filter_active", "checkBox_4", "check"),
    ("dt_min_active", "checkBox_2", "check"),
    ("dt_max_active", "checkBox_3", "check"),
    ("use_gap_fill", "checkBox_5", "check"),
    ("min_photons", "spinBox", "int"),
    ("photon_window", "spinBox_8", "int"),
    ("merge_gap", "spinBox_7", "int"),
    ("time_window", "doubleSpinBox", "float"),
    # The macro-time bounds have their own spin boxes, and the page has a second
    # onRegionUpdate() that resets the region *from* them. Leaving them stale
    # made a dragged region snap straight back to the old bounds.
    ("dt_min", "doubleSpinBox_2", "float"),
    ("dt_max", "doubleSpinBox_3", "float"),
    ("background_rate", "doubleSpinBox_5", "float"),
    ("sb_ratio", "doubleSpinBox_6", "float"),
    ("alpha", "doubleSpinBox_7", "float"),
    ("beta", "doubleSpinBox_8", "float"),
    ("kalman_r_scale", "doubleSpinBox_9", "float"),
    ("kalman_z_thresh", "doubleSpinBox_10", "float"),
    ("kalman_min_len", "spinBox_9", "int"),
)


def _mirror_to_widgets(page) -> None:
    """Push the form's values into the Designer widgets that still back them.

    ``update_parameter()`` rebuilds the page's ``settings`` dict from those
    widgets, and it runs on every value change. Anything the generated form
    wrote straight into that dict was therefore overwritten a moment later by
    whatever the (now hidden) widget still held -- which is why editing the form
    changed nothing at all downstream: the widgets always won.

    Writing through them instead of around them means the existing marshalling
    keeps working unchanged, and there is still exactly one source of truth --
    the widgets are a mirror, never read back by this module.

    Signals are blocked: these widgets are also connected to the update path, and
    letting them re-emit would recurse through on_change.
    """
    settings = getattr(page, "filter_settings", None)
    if settings is None:
        return
    for attr, widget_name, kind in _WIDGET_MIRROR:
        widget = getattr(page, widget_name, None)
        if widget is None:
            continue
        value = getattr(settings, attr, None)
        if value is None:
            continue
        blocked = widget.blockSignals(True)
        try:
            if kind == "check":
                widget.setChecked(bool(value))
            elif kind == "int":
                widget.setValue(int(value))
            else:
                widget.setValue(float(value))
        except Exception:
            pass
        finally:
            widget.blockSignals(blocked)


def adopt_info_panel(page) -> bool:
    """Move the burst Info panel into the right column of the splitter.

    The Info panel sat in its own column with a large empty area beneath it,
    while the search's parameters were squeezed into a narrow middle column. Put
    together they share one resizable side: Info on top, the selected search's
    parameters under it, with the splitter separating that whole column from the
    settings that apply to every search.

    Called after the panel exists -- it is built later in the page's
    construction than this module's install step.
    """
    info = getattr(page, "burst_info_group", None)
    right_box = getattr(page, "_filter_settings_right_box", None)
    if info is None or right_box is None:
        return False
    if info.parentWidget() is page._filter_settings_right:
        return True                      # already adopted
    previous = info.parentWidget()
    if previous is not None and previous.layout() is not None:
        previous.layout().removeWidget(info)
    info.setParent(page._filter_settings_right)
    right_box.insertWidget(0, info)      # above the search parameters
    info.show()
    return True


def _sync_form_fields(page) -> None:
    """Re-read the model into the generated form's field widgets.

    ``AutoForm`` binds widget -> model on edit, but a change made to the model
    from elsewhere (the region drag) does not flow back to the widgets on its
    own. ``sync_fields`` re-reads every field with signals blocked, so the
    visible controls follow the model without a rebuild and without recursing
    through ``on_change``.
    """
    form = getattr(page, "_filter_settings_form_widget", None)
    sync = getattr(form, "sync_fields", None)
    if callable(sync):
        try:
            sync()
        except Exception:
            pass


def _mirror_region(page) -> None:
    """Move the delta-macro-time region to match the current bounds.

    The region and the two number fields edit the same pair of values, so
    editing either has to move the other; without this the region kept showing
    the bounds it was built with while the analysis used different ones.

    Skipped while the region itself is the thing driving the change, which would
    otherwise feed its own value back and fight the drag.
    """
    if getattr(page, "_region_is_updating", False):
        return
    region = getattr(page, "region_selector", None)
    settings = getattr(page, "filter_settings", None)
    if region is None or settings is None:
        return
    import numpy as np

    low, high = float(settings.dt_min), float(settings.dt_max)
    try:
        if page.pw_dT.getAxis("left").logMode:
            if low <= 0.0 or high <= 0.0:
                return          # a log axis cannot show a non-positive bound
            low, high = np.log10(low), np.log10(high)
        blocked = region.blockSignals(True)
        try:
            region.setRegion((low, high))
        finally:
            region.blockSignals(blocked)
    except Exception:
        pass


def _mirror_selection(page, combo_name: str, value: str) -> None:
    """Point one of the page's original combos at ``value``, if it offers it."""
    combo = getattr(page, combo_name, None)
    if combo is None or not value:
        return
    index = combo.findText(value)
    if index >= 0 and index != combo.currentIndex():
        combo.setCurrentIndex(index)


def _rebuild_filter_form(page) -> None:
    """(Re)build the generated form, e.g. after the mode changed."""
    from chisurf.gui.autoform import AutoForm

    # Remove only the form this function created last time, tracked by reference.
    # Sweeping the layout and skipping widgets to keep does not work: PyQt can
    # hand back a different Python wrapper for the same underlying widget, so an
    # identity test silently fails and orphans the registry-driven form that
    # shares this container.
    previous = getattr(page, "_filter_settings_form_widget", None)
    if previous is not None:
        box.removeWidget(previous)
        previous.setParent(None)
        previous.deleteLater()
    form = AutoForm(page._filter_settings_model)
    # Left column: the settings that apply whichever search is chosen. Inserted
    # before the trailing stretch so the panels stay top-aligned.
    left_box = page._filter_settings_left.layout()
    left_box.insertWidget(max(0, left_box.count() - 1), form)
    page._filter_settings_form_widget = form


def refresh_filter_options(page) -> bool:
    """Rebuild the form if the detector or time-window choices changed.

    Called after the page fills those dictionaries, which happens when a setup is
    chosen or a file is loaded — i.e. always after the form was first built.

    Returns whether a rebuild was needed.
    """
    model = getattr(page, "_filter_settings_model", None)
    if model is None or not model.options_changed():
        return False
    _rebuild_filter_form(page)
    return True


def set_filter_mode(page, mode: str) -> None:
    """Point the generated form at a built-in mode's parameters."""
    if getattr(page, "_filter_settings_model", None) is None:
        return
    page.filter_settings.mode = mode
    _rebuild_filter_form(page)
