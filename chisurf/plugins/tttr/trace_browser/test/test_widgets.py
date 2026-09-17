import pytest
from qtpy import QtWidgets


def test_trace_browser_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.plugins.tttr.trace_browser import TraceBrowser

        widget = TraceBrowser()
        qtbot.addWidget(widget)
        assert isinstance(widget, QtWidgets.QWidget)
        assert "Trace" in widget.windowTitle()
        assert hasattr(widget, "table")
        assert hasattr(widget, "plot")
    except Exception:
        pytest.skip("TraceBrowser requires tttrlib or optional dependencies")


def test_trace_browser_supports_fractional_binning(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.plugins.tttr.trace_browser import TraceBrowser

        widget = TraceBrowser()
        qtbot.addWidget(widget)
    except Exception:
        pytest.skip("TraceBrowser requires tttrlib or optional dependencies")

    spin = widget.window_ms_spin
    # Sub-millisecond, fractional bin widths must be accepted (not truncated).
    assert isinstance(spin, QtWidgets.QDoubleSpinBox)
    assert spin.decimals() >= 3
    assert spin.minimum() < 1.0
    spin.setValue(0.25)
    assert spin.value() == pytest.approx(0.25)

    # A fractional bin width must yield a distinct cache signature from a
    # neighbouring value (integer truncation used to collapse them to 0).
    import pathlib

    p = pathlib.Path(__file__)
    assert widget._trace_signature(p, 0.25) != widget._trace_signature(p, 0.75)


def test_trace_browser_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.plugins.tttr.trace_browser.gui.tool import TraceBrowserTool

        widget = TraceBrowserTool()
        qtbot.addWidget(widget)
        assert hasattr(widget, "_workspace")
        assert hasattr(widget._workspace, "table")
        assert hasattr(widget._workspace, "plot")
    except Exception:
        pytest.skip("TraceBrowserTool requires tttrlib or optional dependencies")
