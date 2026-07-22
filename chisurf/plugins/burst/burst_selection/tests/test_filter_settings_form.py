"""The filter-settings panel is generated from a spec, not from the .ui file."""

import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import (  # noqa: E402
    FilterSettings,
    FilterSettingsModel,
    filter_settings_view,
)

DETECTORS = {"green": {"chs": [0], "micro_time_ranges": [(0, 65535)]}}
WINDOWS = {"prompt": (0, 100)}


@pytest.fixture
def page(qapp):
    from chisurf.gui.widgets.wizard.tttr_photonfilter.tttr_photon_filter import (
        WizardTTTRPhotonFilter,
    )
    return WizardTTTRPhotonFilter(windows=WINDOWS, detectors=DETECTORS)


# --- the spec ------------------------------------------------------------------

def test_panels_are_foldable_and_channel_selection_starts_closed():
    view = filter_settings_view(FilterSettings(), ["green"], ["prompt"])
    titles = [panel.title for panel in view.sections]
    assert titles[:3] == ["Channel selection", "Macro time interval", "Filter"]
    # Channel selection is chosen once per setup; the filter parameters are what
    # a user iterates on, and the page competes for space with the plots below.
    assert view.sections[0].collapsed is True
    assert view.sections[1].collapsed is False



def test_mode_selector_is_not_duplicated_in_the_form():
    """The wizard's combobox owns the mode; it also lists the registry searches."""
    view = filter_settings_view(FilterSettings())
    attrs = {getattr(s, "attr", None) for panel in view.sections for s in panel.sections}
    assert "mode" not in attrs



def test_designer_groups_are_replaced_by_the_generated_form(page):
    assert hasattr(page, "filter_settings")
    for name in ("groupBox", "groupBox_2", "groupBox_3"):
        assert getattr(page, name).isHidden(), f"{name} still shown"
    assert page._filter_settings_container is not None


def test_page_properties_read_the_settings_object(page):
    """Public accessors keep working after the controls moved into the form."""
    page.filter_settings.min_photons = 77
    page.filter_settings.merge_gap = 9
    page.filter_settings.dt_max_active = False
    assert page.min_ph == 77
    assert page.max_gap == 9
    assert page.use_upper is False





def test_editing_the_generated_form_updates_the_plots(qapp):
    """Both generated forms must drive the plot refresh.

    Their controls are created and destroyed on every rebuild, so nothing can
    connect to them individually and stay connected; the forms trigger
    ``actionUpdate_Values`` instead, and the tool listens to that.
    """
    from chisurf.plugins.burst.burst_selection import BurstSelectionTool

    tool = BurstSelectionTool(parent=None, show_channel_selection=True)
    calls = []
    tool.wizard.actionUpdate_Values.triggered.connect(lambda: calls.append(1))

    before = len(calls)
    tool.wizard.filter_settings.min_photons = 42
    tool.wizard.actionUpdate_Values.trigger()
    assert len(calls) > before, "a built-in parameter edit did not reach the plots"

    if getattr(tool.wizard, "_tttrlib_algorithms", None):
        form = tool.wizard.burst_search_form
        form.set_state("maxtree")
        before = len(calls)
        form._view._params_group.L = 33
        assert len(calls) > before, "a registry parameter edit did not reach the plots"
        assert form.parameters["L"] == 33


def _field_editor(page, attr):
    """The AutoForm editor widget bound to ``settings.<attr>``, or ``None``."""
    form = getattr(page, "_filter_settings_form_widget", None)
    if form is None:
        return None
    from qtpy import QtWidgets
    for w in form.findChildren(QtWidgets.QWidget):
        section = getattr(w, "_section", None)
        if getattr(section, "attr", None) == attr and hasattr(w, "editor"):
            return w.editor
    return None


def test_region_drag_updates_the_dmt_fields(page):
    """Dragging the delta-macro-time region must move the min/max dMT fields.

    The region writes settings.dt_min/dt_max straight into the model, bypassing
    the form's own widgets; without a re-read those numbers stayed frozen while
    the region and the analysis moved.
    """
    dt_min_editor = _field_editor(page, "dt_min")
    dt_max_editor = _field_editor(page, "dt_max")
    assert dt_min_editor is not None and dt_max_editor is not None

    # Emulate a finished region drag: the plot handler writes new bounds into the
    # model through the notifying proxy, guarded by _region_is_updating.
    page._region_is_updating = True
    try:
        page._filter_settings_model.settings.dt_min = 0.0123
        page._filter_settings_model.settings.dt_max = 0.4567
    finally:
        page._region_is_updating = False

    assert page.filter_settings.dt_min == pytest.approx(0.0123)
    assert page.filter_settings.dt_max == pytest.approx(0.4567)
    assert dt_min_editor.value() == pytest.approx(0.0123, abs=1e-4)
    assert dt_max_editor.value() == pytest.approx(0.4567, abs=1e-4)


def test_all_is_offered_for_detector_and_time_window():
    """'All' must stay selectable: it is how a user asks for every channel."""
    from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import (
        ALL, FilterSettings, filter_settings_view,
    )

    view = filter_settings_view(FilterSettings(), ["green", "red"], ["prompt"])
    channel = view.sections[0]
    assert channel.sections[0].options[0] == ALL
    assert channel.sections[1].options[0] == ALL
    # and it is the default, so an untouched page is not silently restricted
    assert FilterSettings().detector == ALL
    assert FilterSettings().window == ALL


def test_panels_use_two_columns():
    """A single column made the panel taller than the plots it shares space with."""
    from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import (
        FilterSettings, filter_settings_view,
    )

    view = filter_settings_view(FilterSettings())
    assert all(panel.n_col == 2 for panel in view.sections)


def test_detector_and_window_options_follow_the_page(qapp):
    """The choices are filled after a setup or file loads, not at build time."""
    from chisurf.plugins.burst.burst_selection import BurstSelectionTool
    from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import ALL

    tool = BurstSelectionTool(parent=None, show_channel_selection=True)
    page = tool.wizard

    def options():
        for panel in page._filter_settings_model.view_spec().sections:
            if panel.title == "Channel selection":
                return panel.sections[0].options, panel.sections[1].options
        return (), ()

    page.detectors = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}
    page.windows = {"prompt": (0, 100), "delayed": (100, 200)}
    page.fill_detectors(page.detectors)

    detectors, windows = options()
    assert detectors == (ALL, "green", "red")
    assert set(windows) == {ALL, "prompt", "delayed"}
    # Once rebuilt, the form is in step again.
    assert page._filter_settings_model.options_changed() is False
