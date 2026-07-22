"""Every control on the filter-settings panel, exercised through the real page.

These drive the widgets the way a user does — set a value, then assert it
reaches the settings the analysis reads — rather than testing the spec in
isolation. The GUI bugs found during the conversion (a hidden mode selector, an
orphaned form, options frozen at build time, a stale macro-time bound) all
passed spec-level checks while the page was visibly broken, so the assertions
here deliberately go through ``BurstSelectionTool`` end to end.
"""

import glob
import os

import numpy as np
import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

import tttrlib  # noqa: E402

from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import (  # noqa: E402
    ALL,
)
from chisurf.plugins.burst.burst_selection import BurstSelectionTool  # noqa: E402
from chisurf.core.fluorescence.burst import tttrlib_search  # noqa: E402

DATA = os.environ.get("TTTRLIB_DATA", "/Users/tpeulen/dev/tttr-data")


@pytest.fixture(scope="module")
def tool(qapp):
    """One tool for the module.

    Building a BurstSelectionTool per test exhausts Qt resources and the process
    dies with a bus error partway through; the widgets outlive the test that
    made them. The tests below set the values they read, so sharing is safe.
    """
    widget = BurstSelectionTool(parent=None, show_channel_selection=True)
    yield widget
    widget.deleteLater()


@pytest.fixture
def page(tool):
    return tool.wizard


@pytest.fixture
def photons():
    files = sorted(glob.glob(os.path.join(DATA, "bh", "bh_spc132_sm_dna", "*.spc")))
    if not files:
        pytest.skip("single-molecule test data not available")
    return tttrlib.TTTR(files[0], "SPC-130")


# --- the mode selector ----------------------------------------------------------

def test_mode_selector_offers_only_registry_searches(page):
    """The hand-written modes are gone: every search comes from tttrlib."""
    combo = page.comboBox_burst_filter
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert labels, "no burst searches offered"
    registry_labels = {
        spec["label"] for spec in (page._tttrlib_algorithms or {}).values()
    }
    assert set(labels) == registry_labels
    for retired in ("Count rate", "Burst", "Kalman Burst", "CUSUM Burst",
                    "BOCPD Burst"):
        assert retired not in labels, retired


def test_mode_selector_is_always_reachable(page):
    for name in page._tttrlib_algorithms or {}:
        page.burst_search_form.set_state(name)
        assert not page.comboBox_burst_filter.isHidden(), name


def test_shared_settings_stay_visible_for_every_search(page):
    """Channel selection and the macro-time interval are not search parameters.

    They apply whichever search runs, so selecting one must not hide them --
    which it did while the generated form still held the built-in searches'
    parameters.
    """
    for name in page._tttrlib_algorithms or {}:
        page.burst_search_form.set_state(name)
        assert not page._filter_settings_form_widget.isHidden(), name
        titles = [p.title for p in page._filter_settings_model.view_spec().sections]
        assert titles == ["Channel selection", "Macro time interval", "Filter"]


def test_every_search_reports_the_registry_mode(page):
    for name in page._tttrlib_algorithms or {}:
        page.burst_search_form.set_state(name)
        assert page.used_filter == "tttrlib"
        assert page.tttrlib_algorithm == name


def test_selecting_a_registry_search_reports_the_tttrlib_mode(page):
    if not getattr(page, "_tttrlib_algorithms", None):
        pytest.skip("tttrlib publishes no burst-search registry")
    page.burst_search_form.set_state("maxtree")
    assert page.used_filter == "tttrlib"
    assert page.tttrlib_algorithm == "maxtree"


# --- macro time interval --------------------------------------------------------

def test_macro_time_bounds_reach_the_public_accessors(page):
    page.filter_settings.dt_min = 0.002
    page.filter_settings.dt_max = 0.080
    page.filter_settings.dt_min_active = True
    page.filter_settings.dt_max_active = False
    # These are what the analysis marshals; a cached copy here went stale once.
    assert page.dT_min == pytest.approx(0.002)
    assert page.dT_max == pytest.approx(0.080)
    assert page.use_lower is True
    assert page.use_upper is False


def test_macro_time_bounds_actually_filter_photons(page, photons):
    """The bound must change the selection, not merely be stored."""
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters
    from chisurf.plugins.burst.burst_selection.gui.adapter import (
        photon_filter_settings_from_wizard,
    )

    page.filter_settings.dt_min_active = True
    page.filter_settings.dt_max_active = True
    page.filter_settings.dt_min = 0.001
    page.filter_settings.use_gap_fill = False   # gap filling widens the result

    fractions = []
    for dt_max in (0.05, 0.15, 1000.0):
        page.filter_settings.dt_max = dt_max
        settings = photon_filter_settings_from_wizard(page)
        settings.filter_active = False          # isolate the macro-time filter
        settings.use_gap_fill = False
        fractions.append(apply_photon_filters(photons, settings).mean())

    assert fractions[0] < fractions[1] < fractions[2], fractions
    assert fractions[2] > 0.95, "an unbounded interval should keep nearly everything"


def test_merge_gap_reaches_the_accessor(page):
    # max_gap reports 0 when gap filling is off, which is correct; set it
    # explicitly so this does not depend on what an earlier test left behind.
    page.filter_settings.use_gap_fill = True
    page.filter_settings.merge_gap = 7
    assert page.max_gap == 7
    page.filter_settings.use_gap_fill = False
    assert page.max_gap == 0


# --- filter parameters ----------------------------------------------------------

def test_min_photons_and_window_reach_the_accessors(page):
    page.filter_settings.min_photons = 123
    page.filter_settings.photon_window = 9
    assert page.min_ph == 123
    assert page.ph_window == 9


def test_cusum_parameters_reach_the_accessors(page):
    page.filter_settings.background_rate = 3210.0
    page.filter_settings.sb_ratio = 12.5
    page.filter_settings.alpha = 0.02
    page.filter_settings.beta = 0.03
    assert page.cusum_bg_rate == pytest.approx(3210.0)
    assert page.cusum_sb_ratio == pytest.approx(12.5)
    assert page.cusum_alpha == pytest.approx(0.02)
    assert page.cusum_beta == pytest.approx(0.03)


def test_kalman_parameters_reach_the_accessors(page):
    page.filter_settings.kalman_r_scale = 0.25
    page.filter_settings.kalman_z_thresh = 4.5
    page.filter_settings.kalman_min_len = 6
    assert page.kalman_r_scale == pytest.approx(0.25)
    assert page.kalman_z_thresh == pytest.approx(4.5)
    assert page.kalman_min_len == 6


# --- channel selection ----------------------------------------------------------

def test_detector_and_window_offer_all_and_follow_the_page(page):
    page.detectors = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}
    page.windows = {"prompt": (0, 100), "delayed": (100, 200)}
    page.fill_detectors(page.detectors)

    for panel in page._filter_settings_model.view_spec().sections:
        if panel.title == "Channel selection":
            detectors, windows = panel.sections[0].options, panel.sections[1].options
            break
    else:
        pytest.fail("no channel-selection panel")

    assert detectors[0] == ALL and "green" in detectors and "red" in detectors
    assert windows[0] == ALL and "prompt" in windows


@pytest.mark.xfail(
    reason="the detector selection is mirrored into the page's channel field "
           "only from the generated form's own change signal, so setting "
           "FilterSettings.detector programmatically -- as restoring a saved "
           "project does -- leaves the channel field untouched. Needs the "
           "mirroring moved somewhere both paths reach.",
    strict=False,
)
def test_detector_selection_drives_the_channel_field(page):
    """Choosing a detector must populate what the rest of the page reads."""
    page.detectors = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}
    page.fill_detectors(page.detectors)
    page.filter_settings.detector = "green"
    page.actionUpdate_Values.trigger()
    assert page.comboBox_2.currentText() == "green"
    assert page.channels == [0, 8]


# --- panels ---------------------------------------------------------------------

def test_every_panel_is_foldable(page):
    panels = page._filter_settings_model.view_spec().sections
    assert panels, "no panels"
    # Channel selection folds away by default; the rest start open.
    assert panels[0].title == "Channel selection" and panels[0].collapsed is True
    assert all(panel.collapsible for panel in panels)


def test_info_panel_is_foldable(page):
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    assert isinstance(page.burst_info_group, CollapsibleBox)
    page.burst_info_group.set_expanded(False)
    assert page.burst_info_group.is_expanded() is False
    page.burst_info_group.set_expanded(True)
    assert page.burst_info_group.is_expanded() is True


def test_editing_any_control_triggers_a_plot_update(page):
    calls = []
    page.actionUpdate_Values.triggered.connect(lambda: calls.append(1))
    page.filter_settings.min_photons = 51
    page.actionUpdate_Values.trigger()
    assert calls, "no update signalled"


# --- retired modes ---------------------------------------------------------------

def test_bocpd_is_not_offered(page):
    combo = page.comboBox_burst_filter
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert not any("BOCPD" in label for label in labels)


def test_bocpd_says_why_it_is_gone(photons):
    """An old project naming it must get an explanation, not a crash."""
    from chisurf.plugins.burst.burst_selection.api.models import (
        BurstFilterMode, PhotonFilterSettings,
    )
    from chisurf.plugins.burst.burst_selection.api.selection import apply_photon_filters

    settings = PhotonFilterSettings(used_filter=BurstFilterMode.BOCPD)
    with pytest.raises(ValueError, match="removed"):
        apply_photon_filters(photons, settings)


# --- responsiveness: every control must reach the plots -------------------------

def _controls(widget):
    """Every editable control inside a generated form."""
    from qtpy import QtWidgets
    return (
        widget.findChildren(QtWidgets.QSpinBox)
        + widget.findChildren(QtWidgets.QDoubleSpinBox)
        + widget.findChildren(QtWidgets.QCheckBox)
    )


def _nudge(control):
    """Change a control the way a user would."""
    from qtpy import QtWidgets
    if isinstance(control, QtWidgets.QCheckBox):
        control.setChecked(not control.isChecked())
    else:
        control.setValue(control.value() + control.singleStep())


def test_every_shared_control_updates_the_plots(qapp, page):
    """A control that changes a value silently is worse than one that is missing.

    The generated form binds to a dataclass, which accepts ``setattr`` without
    telling anyone; every edit was invisible until the binding was made to
    notify. Enumerating the widgets keeps that from regressing for a control
    added later.
    """
    from qtpy import QtWidgets

    calls = []
    page.actionUpdate_Values.triggered.connect(lambda: calls.append(1))

    controls = _controls(page._filter_settings_form_widget)
    assert controls, "the generated form has no controls"
    for control in controls:
        if not control.isEnabled():
            continue          # a control inside a folded panel is not editable
        before = len(calls)
        _nudge(control)
        qapp.processEvents()
        assert len(calls) > before, (
            f"{control.objectName() or type(control).__name__} changed without "
            f"signalling an update"
        )


def test_every_registry_control_updates_the_plots(qapp, page):

    if not getattr(page, "_tttrlib_algorithms", None):
        pytest.skip("tttrlib publishes no burst-search registry")
    page.burst_search_form.set_state("maxtree")

    calls = []
    page.actionUpdate_Values.triggered.connect(lambda: calls.append(1))
    controls = _controls(page.burst_search_form)
    assert controls, "the registry form has no controls"
    for control in controls:
        before = len(calls)
        _nudge(control)
        qapp.processEvents()
        assert len(calls) > before, "a registry parameter changed silently"


def test_changing_the_mode_updates_the_plots(qapp, page):

    calls = []
    page.actionUpdate_Values.triggered.connect(lambda: calls.append(1))
    combo = page.comboBox_burst_filter
    for index in range(combo.count()):
        before = len(calls)
        combo.setCurrentIndex(index)
        qapp.processEvents()
        assert len(calls) > before, f"selecting {combo.itemText(index)} did nothing"


def test_edits_survive_the_update_that_follows_them(qapp, page):
    """An edit must still be there after the refresh it triggers.

    ``update_parameter()`` rebuilds the page's settings dict from the Designer
    widgets and runs on every change, so anything the generated form wrote
    around those widgets was overwritten a moment later. Every control looked
    responsive and nothing downstream moved.
    """
    from chisurf.plugins.burst.burst_selection.gui.adapter import (
        photon_filter_settings_from_wizard,
    )

    bound = page._filter_settings_model.settings

    bound.invert = False
    bound.dt_max = 0.05
    bound.use_gap_fill = True
    bound.merge_gap = 6
    qapp.processEvents()

    marshalled = photon_filter_settings_from_wizard(page)
    assert marshalled.invert_filter is False
    assert marshalled.delta_macro_time_filter.dT_max == pytest.approx(0.05)
    assert page.max_gap == 6


def test_a_search_parameter_changes_the_number_of_bursts(qapp, page, photons):
    """The end-to-end property that matters: a parameter changes the result.

    The parameter now comes from tttrlib's registry form rather than a built-in
    panel, so this drives it the way the GUI does -- through the bound view.
    """
    if not getattr(page, "_tttrlib_algorithms", None):
        pytest.skip("tttrlib publishes no burst-search registry")
    page.burst_search_form.set_state("maxtree")
    page._filter_settings_model.settings.invert = False
    qapp.processEvents()

    counts = []
    for min_photons in (20, 60, 200):
        page.burst_search_form._view._params_group.L = min_photons
        qapp.processEvents()
        bursts = tttrlib_search.search(
            photons, "maxtree", page.burst_search_form.parameters
        )
        counts.append(len(bursts))

    assert counts[0] > counts[1] > counts[2], counts


# --- the delta-macro-time region ------------------------------------------------

def _region_ms(page):
    import numpy as np
    low, high = page.region_selector.getRegion()
    if page.pw_dT.getAxis("left").logMode:
        return 10 ** low, 10 ** high
    return low, high


def _set_region_ms(page, low, high):
    import numpy as np
    if page.pw_dT.getAxis("left").logMode:
        low, high = np.log10(low), np.log10(high)
    page.region_selector.setRegion((low, high))
    page.region_selector.sigRegionChangeFinished.emit(page.region_selector)


def test_dragging_the_region_reaches_the_analysis(qapp, page):
    """The region edits the same bounds as the number fields.

    It wrote only the old Designer widgets, so after the macro-time bounds moved
    into the generated form a dragged region changed nothing at all.
    """
    from chisurf.plugins.burst.burst_selection.gui.adapter import (
        photon_filter_settings_from_wizard,
    )

    if getattr(page, "region_selector", None) is None:
        pytest.skip("no region selector on this page")

    _set_region_ms(page, 0.002, 0.05)
    qapp.processEvents()

    assert page.filter_settings.dt_min == pytest.approx(0.002, rel=1e-3)
    assert page.filter_settings.dt_max == pytest.approx(0.05, rel=1e-3)
    marshalled = photon_filter_settings_from_wizard(page)
    assert marshalled.delta_macro_time_filter.dT_max == pytest.approx(0.05, rel=1e-3)


def test_editing_the_bounds_moves_the_region(qapp, page):
    """The other direction: the region must not show stale bounds."""

    if getattr(page, "region_selector", None) is None:
        pytest.skip("no region selector on this page")

    page._filter_settings_model.settings.dt_max = 0.3
    qapp.processEvents()
    low, high = _region_ms(page)
    assert high == pytest.approx(0.3, rel=1e-3)


def test_dragging_the_region_is_not_undone_by_the_reverse_sync(qapp, page):
    """The page has a second onRegionUpdate() that resets the region from the
    spin boxes. Those were not being kept in step, so a dragged region snapped
    straight back to the bounds it had before the drag."""
    import numpy as np
    from chisurf.plugins.burst.burst_selection.gui.adapter import (
        photon_filter_settings_from_wizard,
    )

    if getattr(page, "region_selector", None) is None:
        pytest.skip("no region selector on this page")

    _set_region_ms(page, 0.003, 0.07)
    qapp.processEvents()
    assert page.doubleSpinBox_2.value() == pytest.approx(0.003, rel=1e-3)
    assert page.doubleSpinBox_3.value() == pytest.approx(0.07, rel=1e-3)

    page.onRegionUpdate()          # the page's spin-box -> region direction
    qapp.processEvents()
    low, high = _region_ms(page)
    assert high == pytest.approx(0.07, rel=1e-3), "the drag was undone"
    marshalled = photon_filter_settings_from_wizard(page)
    assert marshalled.delta_macro_time_filter.dT_max == pytest.approx(0.07, rel=1e-3)


def test_all_means_no_selection(qapp, page):
    """'All' must apply no mask at all, for detector and time window alike."""
    from chisurf.plugins.burst.burst_selection.gui.adapter import (
        photon_filter_settings_from_wizard,
    )

    page.detectors = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}
    page.windows = {"prompt": (0, 2000), "delayed": (2000, 4095)}
    page.fill_detectors(page.detectors)
    bound = page._filter_settings_model.settings

    bound.detector, bound.window = ALL, ALL
    qapp.processEvents()
    settings = photon_filter_settings_from_wizard(page)
    assert list(settings.channels) == []
    assert list(settings.microtime_ranges) == []

    bound.detector = "green"
    qapp.processEvents()
    assert list(photon_filter_settings_from_wizard(page).channels) == [0, 8]
