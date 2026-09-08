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


def test_the_estimate_button_is_the_shells_run_action(qapp, qtbot):
    """The shell drives a step through the child named ``toolAction_run``.

    Without the name, *Next* and the fast-forward found no action on the
    background step and walked straight past it — so the later steps corrected
    with backgrounds nobody had estimated, and nothing said so.
    """
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    widget = BurstBackgroundEstimator(show_channel_definition=False)
    qtbot.addWidget(widget)
    button = widget.findChild(QtWidgets.QToolButton, "toolAction_run")
    assert button is not None and button.isEnabled()


def test_files_pushed_by_the_shell_appear_in_the_list(qapp, qtbot):
    """An embedded panel shows the measurements the workflow handed it.

    The list read the model once, when it was built. A workflow pushes its
    files in afterwards, so the dock stayed empty while the estimate ran on
    files it did not show — which reads as "the tool has no data".
    """
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    widget = BurstBackgroundEstimator(show_channel_definition=False)
    qtbot.addWidget(widget)
    widget._add_tttr_files(["/nonexistent/pushed_by_the_shell.ptu"])

    listed = [
        w.item(row).text()
        for w in widget.findChildren(QtWidgets.QListWidget)
        for row in range(w.count())
    ]
    assert "/nonexistent/pushed_by_the_shell.ptu" in listed
