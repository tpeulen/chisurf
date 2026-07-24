from qtpy import QtWidgets


def test_background_estimator_widget(qapp, qtbot):
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    widget = BurstBackgroundEstimator()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert widget.windowTitle() == "Burst Background Estimation"
    # Shell API used by _burst_background / _apply_context_to_background.
    assert widget.detector_wizard_page is not None
    assert widget.tttr_files == []


def test_background_estimator_embedded_drops_channel_dock(qapp, qtbot):
    """Embedded mode drops the channels dock but keeps the file/estimate API."""
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    widget = BurstBackgroundEstimator(show_channel_definition=False)
    qtbot.addWidget(widget)
    assert widget.detector_wizard_page is not None
    widget._add_tttr_files(["/nonexistent/a.spc", "/nonexistent/a.spc"])
    assert widget.tttr_files == ["/nonexistent/a.spc"]  # de-duplicated


def test_background_view_model_estimate_reports_reason(qapp):
    """The Qt-free view-model refuses to estimate without files/detectors."""
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    model = BackgroundViewModel()
    assert model.can_estimate() is not None  # no files yet
    model.add_files(["/nonexistent/a.spc"])
    model.channels_provider = lambda: {}
    assert "detector" in (model.can_estimate() or "").lower()
    model.channels_provider = lambda: {"green": {"chs": [0, 8]}}
    assert model.can_estimate() is None
