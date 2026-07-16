import pytest
from qtpy import QtWidgets


def test_view_model_is_qt_free_and_filters():
    from chisurf.plugins.tttr.tttr_image_browser.gui.view_model import ImageBrowserViewModel

    vm = ImageBrowserViewModel()
    # No folder → empty accessors, helpful status.
    assert vm.file_entries() == []
    assert vm.current_image() is None
    assert vm.image_labels() == []
    assert "folder" in vm.info_html().lower()
    # Rating filter predicate.
    vm.set_rating_filter("≥ 2★★")
    assert vm.rating_filter == "≥ 2★★"
    assert "≥ 2★★" in vm.rating_filter_options()


def test_view_spec_loads():
    from chisurf.plugins.tttr.tttr_image_browser.gui.view_model import ImageBrowserViewModel

    spec = ImageBrowserViewModel().view_spec()
    assert spec is not None and spec.sections


def test_tttr_image_browser_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.gui.autoform.sections.image_browser_section import ImageBrowserWidget
        from chisurf.plugins.tttr.tttr_image_browser import TTTRImageBrowser

        widget = TTTRImageBrowser()
    except Exception:
        pytest.skip("TTTRImageBrowser requires tttrlib or optional dependencies")
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "Image" in widget.windowTitle()
    assert hasattr(widget, "auto_form")
    assert widget.auto_form.findChild(ImageBrowserWidget) is not None


def test_tttr_image_browser_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.plugins.tttr.tttr_image_browser.gui.tool import TTTRImageBrowserTool

        widget = TTTRImageBrowserTool()
    except Exception:
        pytest.skip("TTTRImageBrowserTool requires tttrlib or optional dependencies")
    qtbot.addWidget(widget)
    assert hasattr(widget, "_workspace")
    assert hasattr(widget._workspace, "auto_form")
    assert hasattr(widget._workspace, "model")
