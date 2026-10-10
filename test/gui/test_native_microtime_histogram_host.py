"""The histogram app's Qt host keeps its parent and native surface."""


def test_lifetime_microtime_factory_preserves_parent_and_native_surface(qapp, qtbot):
    """Retiring the wizard cannot remove the existing toolbox's histogram panel."""
    from qtpy import QtWidgets

    from chisurf.plugins.tttr.microtime_histogram.gui.app import HistogramApp, create_host

    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    widget = create_host(parent=parent)
    qtbot.addWidget(widget)
    try:
        assert isinstance(widget, QtWidgets.QWidget)
        assert widget.parent() is parent
        assert isinstance(getattr(widget, "control", None), HistogramApp)
    finally:
        widget.close()


def test_lifetime_host_closes_its_original_native_app_once(qapp, qtbot, monkeypatch):
    """Closing the child and its owning legacy parent cannot close the worker twice."""
    from qtpy import QtWidgets

    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_host

    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    widget = create_host(parent=parent)
    calls = []
    close = widget.control.close

    def close_app():
        """Observe the real close operation without replacing its cleanup."""
        calls.append(widget.control)
        close()

    monkeypatch.setattr(widget.control, "close", close_app)
    widget.show()
    widget.close()
    parent.close()
    widget.close()
    qapp.processEvents()
    assert calls == [widget.control]
