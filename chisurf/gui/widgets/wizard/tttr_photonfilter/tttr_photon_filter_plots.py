import numpy as np
from emtk.colormaps import to_rgb

from chisurf.gui import chiplot as cp

#: Every plot of the page shares these two pens: the unselected photons faint, the selected ones solid.
COLOR_ALL = (255, 255, 0, 64)
COLOR_SELECTED = (0, 255, 255, 255)


def create_plots(page, colors):
    """Build the page's plots (chiplot panels) and the draggable dT region."""
    page.pw_burst_histogram = cp.Plot(parent=page, title="Burst histogram")
    page.pw_burst_histogram.set_labels(left="Counts", bottom="Burst size (Nbr. Photons)")
    page.pw_burst_histogram.resize(100, 80)

    pen_all = cp.to_pen(COLOR_ALL, width=1)
    pen_selected = cp.to_pen(COLOR_SELECTED, width=1)

    page.pw_dT = cp.Plot(parent=page, title="Delta macro-time")
    page.pw_dT.set_labels(left="dT (ms)", bottom="Photon Index")
    page.plot_unselected = page.pw_dT.line([1.0], [1.0], pen=pen_all)
    page.plot_selected = page.pw_dT.line([1.0], [1.0], pen=pen_selected)
    page.pw_dT.resize(200, 40)

    page.pw_mcs = cp.Plot(parent=page, title="Count rate display")
    page.pw_mcs.set_labels(left="Intensity (kHz)", bottom="Time (s)")
    page.plot_mcs_all = page.pw_mcs.line([1.0], [1.0], pen=pen_all)
    page.plot_mcs_selected = page.pw_mcs.line([1.0], [1.0], pen=pen_selected)
    page.pw_mcs.resize(200, 80)

    page.pw_decay = cp.Plot(parent=page, title="Microtime histogram")
    page.pw_decay.set_labels(left="Counts", bottom="Microtime (ns)")
    page.plot_decay_all = page.pw_decay.line([1.0], [1.0], pen=pen_all)
    page.plot_decay_selected = page.pw_decay.line([1.0], [1.0], pen=pen_selected)
    page.pw_decay.resize(200, 80)

    page.pw_filter = cp.Plot(parent=page, title="Filter/selection")
    page.pw_filter.set_labels(left="Selected (1) / Unselected (0)", bottom="Photon Index")
    page.pw_filter.link_x(page.pw_dT)
    page.pw_dT.set_interactive(mouse=False)
    page.pw_filter.set_interactive(mouse=False)
    page.plot_select = page.pw_filter.line([1.0], [1.0])
    page.pw_filter.resize(200, 20)

    #: The dT axis is logarithmic, so the region below lives in log10 units.
    page._dT_log = True
    page.pw_dT.set_log(y=True)
    page.pw_decay.set_log(y=True)

    # The three plots holding a raw per-photon series get the viewport's own
    # decimation. This is the single most expensive thing in the burst-selection
    # window: handed a full 1.8 M-photon dT trace, one repaint of this widget
    # measured **0.29 s** — and it is repainted on every settings change, every
    # tab switch and every resize. Measured in isolation, `auto`/`peak`
    # downsampling with `clipToView` takes a 660k-point curve from 0.121 s to
    # 0.009 s per paint and makes the cost nearly independent of the point
    # count, because the renderer then lays out what is *visible* rather than
    # everything. `peak` keeps each bin's extremes, for the same reason
    # `chisurf.core.fio.decimate.thin_for_plot` is min/max-per-bin: a stride
    # aliases the bursts away, which is worse than slow.
    for _plot in (page.pw_dT, page.pw_filter, page.pw_mcs):
        _plot.set_downsampling(auto=True, mode="peak")
        _plot.set_clip_to_view(True)

    ca = list(to_rgb(colors["region_selector"]))
    co = (ca[0] * 255, ca[1] * 255, ca[2] * 255, colors["region_selector_alpha"])
    page.region_selector = page.pw_dT.region(
        (np.log10(page._dT_min), np.log10(page._dT_max)),
        orientation="horizontal",
        brush=co,
    )

    def onRegionUpdate(lb, ub):
        lb, ub = 10**lb, 10**ub  # the region lives in log10 units
        page._dT_min = lb
        page._dT_max = ub
        page.doubleSpinBox_2.blockSignals(True)
        page.doubleSpinBox_3.blockSignals(True)
        page.doubleSpinBox_2.setValue(lb)
        page.doubleSpinBox_3.setValue(ub)
        page.doubleSpinBox_2.blockSignals(False)
        page.doubleSpinBox_3.blockSignals(False)
        # The macro-time bounds now live in the generated form's settings, which
        # is what the analysis marshals; writing only the old widgets left a
        # dragged region with no effect on the selection. Going through the
        # bound object also refreshes the form's own fields and mirrors the
        # values onward, so the region, the spin boxes and the analysis agree.
        model = getattr(page, "_filter_settings_model", None)
        if model is not None:
            page._region_is_updating = True
            try:
                model.settings.dt_min = float(lb)
                model.settings.dt_max = float(ub)
            finally:
                page._region_is_updating = False
        page.update_plots()
        page.update_output_path()

    page._on_region_finished = onRegionUpdate
    page.region_selector.on_change(onRegionUpdate, final=True)


def place_plots(page):
    # Place plots in layout
    page.gridLayout_6.addWidget(page.pw_dT, 0, 0, 1, 3)
    page.gridLayout_6.addWidget(page.pw_filter, 1, 0, 1, 3)
    page.gridLayout_6.addWidget(page.pw_mcs, 2, 0, 1, 1)
    page.gridLayout_6.addWidget(page.pw_decay, 2, 1, 1, 1)
    page.gridLayout_6.addWidget(page.pw_burst_histogram, 0, 1, 2, 1)
