"""Tests for the Help plugin widgets."""

from qtpy import QtWidgets


def test_help_widget_creation(qapp, qtbot):
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    widget = HelpWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "Help" in widget.windowTitle() or "Help" in widget.__class__.__name__
    assert hasattr(widget, "tree")
    assert hasattr(widget, "viewer")
    assert hasattr(widget, "title_label")
    assert hasattr(widget, "edit_btn")
    assert hasattr(widget, "save_btn")


def test_help_widget_toolbar(qapp, qtbot):
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    widget = HelpWidget()
    qtbot.addWidget(widget)
    toolbars = widget.findChildren(QtWidgets.QToolBar)
    assert len(toolbars) >= 1
    toolbar = toolbars[0]
    actions = toolbar.actions()
    assert len(actions) >= 5
    labels = [a.text() for a in actions]
    assert any("Edit" in label or "👁️" in label or "✏️" in label for label in labels)
    assert any("Save" in label or "💾" in label for label in labels)


def test_help_widget_has_review_controls(qapp, qtbot):
    """The browser exposes human-review sign-off and filtering."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    widget = HelpWidget()
    qtbot.addWidget(widget)
    assert hasattr(widget, "review_btn")
    assert hasattr(widget, "review_filter")
    assert hasattr(widget, "review_label")
    assert hasattr(widget, "review_summary_label")
    # Nothing open yet, so signing off must be impossible.
    assert not widget.review_btn.isEnabled()


def test_manual_branch_is_badged_with_review_status(qapp, qtbot):
    """The user-manual branch lists reStructuredText pages with status badges."""
    from qtpy.QtCore import Qt

    from chisurf.plugins.core.help.api import review
    from chisurf.plugins.core.help.gui.tool import REVIEW_BADGES, HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.populate_docs()

    root = widget.tree.topLevelItem(0)
    assert "User manual" in root.text(0)
    if root.childCount() == 0:
        import pytest

        pytest.skip("no user manual in this checkout")

    # Every child carries a known status badge and a real path.
    for i in range(root.childCount()):
        item = root.child(i)
        status = item.data(0, Qt.UserRole + 1)
        assert status in REVIEW_BADGES
        assert item.data(0, Qt.UserRole)
    # The manual is reStructuredText, which the browser could not read before.
    assert any(
        str(root.child(i).data(0, Qt.UserRole)).endswith(".rst")
        for i in range(root.childCount())
    )
    assert review.STATUS_UNREVIEWED in REVIEW_BADGES


def test_review_filter_hides_non_matching_pages(qapp, qtbot):
    """Filtering by a status hides manual pages that do not have it."""
    from qtpy.QtCore import Qt

    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.populate_docs()
    root = widget.tree.topLevelItem(0)
    if root.childCount() == 0:
        import pytest

        pytest.skip("no user manual in this checkout")

    index = widget.review_filter.findData("reviewed")
    widget.review_filter.setCurrentIndex(index)
    for i in range(root.childCount()):
        item = root.child(i)
        if item.data(0, Qt.UserRole + 1) != "reviewed":
            assert item.isHidden()

    widget.review_filter.setCurrentIndex(widget.review_filter.findData("all"))
    assert not any(root.child(i).isHidden() for i in range(root.childCount()))


def test_oversized_images_are_scaled_and_centred():
    """Manual screenshots must not blow up the layout."""
    import pathlib

    from chisurf.plugins.core.help.gui.tool import _constrain_image_widths

    html = '<p>text</p>\n<img alt="x" class="align-center" src="wide.png" />\n<p>more</p>'
    out = _constrain_image_widths(html, pathlib.Path("."), 400)
    # The unusable docutils class is dropped and the block image is centred.
    assert "align-center" not in out
    assert '<p align="center">' in out


def test_inline_images_are_not_wrapped():
    import pathlib

    from chisurf.plugins.core.help.gui.tool import _constrain_image_widths

    html = '<p>text <img alt="x" src="i.png" /> more</p>'
    out = _constrain_image_widths(html, pathlib.Path("."), 400)
    assert '<p align="center">' not in out
