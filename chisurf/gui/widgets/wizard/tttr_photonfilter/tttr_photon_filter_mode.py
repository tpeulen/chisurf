"""Drive the photon-filter wizard's burst-search selector from tttrlib.

Every burst search now comes from tttrlib's registry, so the wizard no longer
relabels a fixed pool of Designer spinboxes per mode. It embeds one
:class:`~chisurf.gui.widgets.burst_search_form.BurstSearchForm` — the same widget
that works standalone — which populates the wizard's existing ``Filter mode``
combobox and generates the selected search's parameter form. That widget is the
single "pick a burst search, edit its parameters" implementation; this module
only wires it into the page.
"""

from __future__ import annotations


def install_filter_mode_visibility(page, default_filter_mode: str) -> None:
    """Attach the registry-driven burst-search picker to ``page``.

    Populates ``page.comboBox_burst_filter`` from tttrlib's registry and places
    the generated parameter form in the right column of the filter-settings
    splitter, beside the settings shared by every search.
    """
    from chisurf.gui.widgets.burst_search_form import BurstSearchForm

    # BurstSearchForm drives the wizard's own combobox (kept in its layout row)
    # and lays out only the summary and the generated parameter form.
    form = BurstSearchForm(combo=page.comboBox_burst_filter, parent=page)
    page.burst_search_form = form
    # Retained for callers and tests that ask which searches are offered.
    page._tttrlib_algorithms = dict(form._algorithms)

    right_box = getattr(page, "_filter_settings_right_box", None)
    if right_box is not None:
        # Before the trailing stretch, so the panel stays top-aligned.
        right_box.insertWidget(max(0, right_box.count() - 1), form)
    else:  # pragma: no cover - the splitter is always built before this runs
        layout = page.comboBox_burst_filter.parentWidget().layout()
        if layout is not None:
            layout.addWidget(form)

    # A change of search, or of any parameter, refreshes the plots and the
    # marshalled settings -- the trigger the per-mode controls used to fire.
    form.parametersChanged.connect(page.actionUpdate_Values.trigger)

    # Kept as a no-op so code and tests that still call it keep working; the
    # generated form owns the whole parameter area now, so there is nothing
    # per-mode left to show or hide.
    page.update_parameter_visibility = lambda *args: None

    # Restore a saved default search when the project named one.
    if default_filter_mode in page._tttrlib_algorithms:
        try:
            form.set_state(default_filter_mode)
        except ValueError:
            pass
