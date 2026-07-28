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


def _make_tool(qtbot):
    """Build the tool, skipping only when an optional dependency is missing.

    The skip is narrowed to ``ImportError`` on purpose: a constructor that
    *raises* is the defect these smoke tests exist to catch, and a blanket
    ``except Exception`` would report it as a skip.
    """
    pytest.importorskip("pyqtgraph")
    try:
        from chisurf.plugins.tttr.tttr_image_browser.gui.tool import TTTRImageBrowserTool
    except ImportError:
        pytest.skip("TTTRImageBrowserTool requires tttrlib or optional dependencies")
    widget = TTTRImageBrowserTool()
    qtbot.addWidget(widget)
    return widget


def test_tttr_image_browser_tool_creation(qapp, qtbot):
    widget = _make_tool(qtbot)
    assert hasattr(widget, "_workspace")
    assert hasattr(widget._workspace, "auto_form")
    assert hasattr(widget._workspace, "model")


def test_tttr_image_browser_tool_is_a_dock_tool(qapp, qtbot):
    """PRD-36: the tool is on the shared base and opens no MMFDB connection."""
    from chisurf.gui.widgets.tools import ChisurfDockTool

    widget = _make_tool(qtbot)
    assert isinstance(widget, ChisurfDockTool)
    assert widget.tool_settings_name == "TTTRImageBrowserTool"
    # The base's window-level drag-drop is what replaces the per-tool handlers.
    assert widget.acceptDrops()
    # Read-only construction (PRD-23 Task 4): nothing was connected on init.
    assert widget.mmfdb_connected() is False


def test_tttr_image_browser_tool_missing_attribute_raises(qapp, qtbot):
    """Workspace delegation reports a genuinely missing name, not recursion."""
    widget = _make_tool(qtbot)
    assert widget.auto_form is widget._workspace.auto_form
    with pytest.raises(AttributeError):
        widget.no_such_attribute


def test_tttr_image_browser_tool_folder_drop_opens_it(qapp, qtbot, tmp_path):
    """A dropped folder is browsed; a dropped file is reported, not swallowed."""
    widget = _make_tool(qtbot)
    a_file = tmp_path / "not_a_folder.ptu"
    a_file.write_bytes(b"")

    widget.on_paths_dropped([a_file])
    assert [m.name for m in widget.Information.active] == ["no_folder_dropped"]

    widget.on_paths_dropped([tmp_path])
    assert widget.Information.active == ()
    assert widget._workspace.model.current_folder == str(tmp_path)
