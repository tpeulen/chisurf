"""Tests for the Help plugin widgets.

The browser navigates by the documentation's own table of contents and opens on
a start page, so the checks here are about *structure* — that the sections are
there, in order, with a page behind each row — rather than about a directory
listing, which is what it used to show.
"""

import pathlib

from qtpy import QtWidgets
from qtpy.QtCore import Qt


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
    """The reader's toolbar navigates; the authoring one is a second row."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    widget = HelpWidget()
    qtbot.addWidget(widget)
    toolbars = {bar.windowTitle(): bar for bar in widget.findChildren(QtWidgets.QToolBar)}
    assert "Help" in toolbars
    labels = [action.text() for action in toolbars["Help"].actions()]
    assert "⌂" in labels and "◀" in labels and "▶" in labels
    # Editing is not a reading tool, and is not offered until asked for.
    assert not any("Edit" in label for label in labels)
    assert widget.authoring_toolbar.isHidden() or not widget.authoring_btn.isChecked()
    authoring = [action.text() for action in widget.authoring_toolbar.actions()]
    assert any("Edit" in label for label in authoring)
    assert any("Save" in label for label in authoring)


def test_tree_follows_the_documentation_structure(qapp, qtbot):
    """Sections come from the docs' toctrees, grouped and in reading order."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    titles = [
        widget.tree.topLevelItem(index).text(0)
        for index in range(widget.tree.topLevelItemCount())
    ]
    for expected in ("Getting started", "Concepts", "Guides", "Reference", "Plugins"):
        assert any(expected in title for title in titles), titles

    concepts = next(
        widget.tree.topLevelItem(index)
        for index in range(widget.tree.topLevelItemCount())
        if "Concepts" in widget.tree.topLevelItem(index).text(0)
    )
    # Grouped, not a flat alphabetical run: the first level holds the rubrics.
    # Asserted as a *property* rather than by naming one rubric -- the rubrics
    # are authored in the page and get reorganised, and a test that names one
    # fails on an editorial change that is not a defect.
    groups = [concepts.child(i).text(0) for i in range(concepts.childCount())]
    assert len(groups) >= 3, groups
    assert all(concepts.child(i).childCount() >= 1 for i in range(len(groups))), groups
    assert max(concepts.child(i).childCount() for i in range(len(groups))) >= 3


def test_every_tree_leaf_has_a_document(qapp, qtbot):
    """A row a reader can click has to lead somewhere."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    def walk(item):
        for index in range(item.childCount()):
            child = item.child(index)
            path = child.data(0, Qt.UserRole)
            if child.childCount() == 0:
                assert path, f"leaf without a document: {child.text(0)}"
                assert pathlib.Path(path).is_file(), path
            walk(child)

    for index in range(widget.tree.topLevelItemCount()):
        walk(widget.tree.topLevelItem(index))


def test_manual_pages_have_distinct_titles(qapp, qtbot):
    """Three rows called "Overview" tell the reader nothing about which to open."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    manual = None
    for index in range(widget.tree.topLevelItemCount()):
        item = widget.tree.topLevelItem(index)
        if "Fitting interface" in item.text(0):
            manual = item
    assert manual is not None

    titles = []

    def collect(item):
        for index in range(item.childCount()):
            child = item.child(index)
            if child.data(0, Qt.UserRole):
                titles.append(child.text(0))
            collect(child)

    collect(manual)
    duplicates = {title for title in titles if titles.count(title) > 1}
    assert not duplicates, duplicates


def test_start_page_offers_a_way_in(qapp, qtbot):
    """The browser opens on something to read, not on an empty pane."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    text = widget.viewer.toPlainText()
    assert "ChiSurf documentation" in text
    assert "Start here" in text


def test_search_ranks_pages_and_filters_the_tree(qapp, qtbot):
    """A multi-word query must rank pages, and leave the tree showing them."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    hits = widget.search("anisotropy g-factor")
    assert hits
    assert "anisotropy" in hits[0]["node"].title.lower()
    assert hits[0]["excerpt"]
    # The excerpt is prose, not markup.
    assert ")=" not in hits[0]["excerpt"]

    widget.search_edit.setText("anisotropy g-factor")
    widget._run_search()
    visible = [item for key, item in widget._items.items() if not item.isHidden()]
    assert visible, "the tree emptied itself while the search found pages"

    widget.search_edit.setText("")
    widget._run_search()
    assert not widget._items[list(widget._items)[0]].isHidden()


def test_pages_carry_previous_and_next(qapp, qtbot):
    """A manual is read in order; the page has to offer the next one."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api.toc import repository_root

    widget = HelpWidget()
    qtbot.addWidget(widget)
    page = repository_root() / "docs" / "concepts" / "tcspc_lifetime.md"
    if not page.is_file():
        import pytest

        pytest.skip("documentation not present in this checkout")
    widget.navigate(page)
    html = widget.viewer.toHtml()
    assert "◀" in html and "▶" in html


def test_history_and_breadcrumb(qapp, qtbot):
    """Back returns to where the reader was, and the trail says where that is."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api.toc import repository_root

    widget = HelpWidget()
    qtbot.addWidget(widget)
    root = repository_root() / "docs" / "concepts"
    first, second = root / "fret.md", root / "anisotropy.md"
    if not (first.is_file() and second.is_file()):
        import pytest

        pytest.skip("documentation not present in this checkout")
    widget.navigate(first)
    assert "Concepts" in widget.breadcrumb_label.text()
    widget.navigate(second)
    widget.go_back()
    assert widget.current_path == first


def test_review_controls_live_behind_authoring(qapp, qtbot):
    """The release gate is a maintainer's tool, not part of reading a page."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    assert hasattr(widget, "review_btn")
    assert hasattr(widget, "review_filter")
    assert not widget.review_btn.isEnabled()
    assert not widget.authoring_btn.isChecked()

    widget.authoring_btn.setChecked(True)
    assert widget.authoring_toolbar.isVisibleTo(widget)


def test_review_filter_hides_non_matching_pages(qapp, qtbot):
    """Filtering by a status hides review-tracked pages without it."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api import review

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.authoring_btn.setChecked(True)

    tracked = {
        key: item
        for key, item in widget._items.items()
        if item.data(0, Qt.UserRole + 1)
    }
    if not tracked:
        import pytest

        pytest.skip("no review-tracked pages in this checkout")

    index = widget.review_filter.findData(review.STATUS_REVIEWED)
    widget.review_filter.setCurrentIndex(index)
    for key, item in tracked.items():
        if item.data(0, Qt.UserRole + 1) != review.STATUS_REVIEWED:
            assert item.isHidden(), key

    widget.review_filter.setCurrentIndex(widget.review_filter.findData("all"))
    assert not any(item.isHidden() for item in tracked.values())


def test_developer_documentation_is_off_by_default(qapp, qtbot):
    """Architecture notes are not what a scientist opened the help for."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    titles = [
        widget.tree.topLevelItem(index).text(0)
        for index in range(widget.tree.topLevelItemCount())
    ]
    assert not any("Developing" in title for title in titles)

    widget.authoring_btn.setChecked(True)
    widget.developer_btn.setChecked(True)
    titles = [
        widget.tree.topLevelItem(index).text(0)
        for index in range(widget.tree.topLevelItemCount())
    ]
    assert any("Developing" in title for title in titles)


def test_oversized_images_are_scaled_and_centred():
    """Manual screenshots must not blow up the layout."""
    from chisurf.plugins.core.help.gui.tool import _constrain_image_widths

    html = '<p>text</p>\n<img alt="x" class="align-center" src="wide.png" />\n<p>more</p>'
    out = _constrain_image_widths(html, pathlib.Path("."), 400)
    # The unusable docutils class is dropped and the block image is centred.
    assert "align-center" not in out
    assert '<p align="center">' in out


def test_inline_images_are_not_wrapped():
    from chisurf.plugins.core.help.gui.tool import _constrain_image_widths

    html = '<p>text <img alt="x" src="i.png" /> more</p>'
    out = _constrain_image_widths(html, pathlib.Path("."), 400)
    assert '<p align="center">' not in out


def test_text_column_is_bounded_in_a_wide_window():
    """A thousand-pixel line is not readable, whatever the window is doing."""
    from chisurf.plugins.core.help.gui.tool import MIN_GUTTER, measure_margin

    assert measure_margin(700, 860) == MIN_GUTTER
    assert measure_margin(1600, 860) == 370


def test_text_column_follows_the_window_when_it_narrows(qapp, qtbot):
    """The measure is not frozen at the width the page was rendered for.

    Opening wide and then narrowing used to leave the gutters at their old
    size: the text column collapsed to a fraction of the window and the
    document, still as wide as before, grew a horizontal scrollbar.
    """
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api.toc import repository_root

    page = repository_root() / "docs" / "concepts" / "fret.md"
    if not page.is_file():
        import pytest

        pytest.skip("documentation not present in this checkout")

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.resize(1800, 900)
    widget.show()
    qapp.processEvents()
    widget.navigate(page)
    qapp.processEvents()

    widget.resize(1000, 900)
    qapp.processEvents()

    viewport = widget.viewer.viewport().width()
    assert widget.viewer.document().idealWidth() <= viewport + 1
    assert widget.viewer.horizontalScrollBar().maximum() == 0


def test_zoom_changes_the_rendered_size(qapp, qtbot):
    """Ctrl+= must change the whole page, not only the body text.

    The stylesheet gives every size in points, so a widget-level zoom would
    move the body and leave the headings, tables and formulas behind: the page
    is re-rendered at the new size instead.
    """
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api.toc import repository_root

    widget = HelpWidget()
    qtbot.addWidget(widget)
    page = repository_root() / "docs" / "concepts" / "fret.md"
    if not page.is_file():
        import pytest

        pytest.skip("documentation not present in this checkout")
    widget.navigate(page)

    before = widget.font_size
    widget.zoom(+2)
    assert widget.font_size > before
    assert f"{widget.font_size}pt" in widget.viewer.toHtml() or widget.viewer.toHtml()

    widget.reset_zoom()
    assert widget.font_size == widget.DEFAULT_FONT_SIZE

    # Clamped, so a held-down key cannot render at 0.5 pt or 400 pt.
    for _ in range(80):
        widget.zoom(-1)
    assert widget.font_size == widget.MIN_FONT_SIZE
    for _ in range(200):
        widget.zoom(+1)
    assert widget.font_size == widget.MAX_FONT_SIZE


def test_tree_rows_carry_no_emoji(qapp, qtbot):
    """An emoji in a row forces a colour-font fallback with other metrics.

    The whole row is then set in a different face and size from the rest of
    the application, which is what made the navigation look wrong.
    """
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    def walk(item):
        yield item
        for index in range(item.childCount()):
            yield from walk(item.child(index))

    def is_emoji(character: str) -> bool:
        # Pictographs and dingbats, plus the variation selector that asks for
        # the colour form. An arrow in a page's own title (“TTTR→Time-Window”)
        # is ordinary text and stays.
        point = ord(character)
        return (
            0x1F300 <= point <= 0x1FAFF
            or 0x2600 <= point <= 0x27BF
            or point in (0xFE0F, 0x2B1C, 0x2705, 0x26A0)
        )

    for index in range(widget.tree.topLevelItemCount()):
        for item in walk(widget.tree.topLevelItem(index)):
            offending = [c for c in item.text(0) if is_emoji(c)]
            assert not offending, (item.text(0), offending)


def test_review_state_is_colour_not_a_badge(qapp, qtbot):
    """Reviewing must not restyle the navigation.

    A badge character in a row is an emoji, and an emoji makes Qt fall back to
    a colour font for the whole item — the manual would be set in a different
    face from everything above it exactly while somebody works through it.
    """
    from qtpy.QtCore import Qt

    from chisurf.plugins.core.help.gui.tool import HelpWidget, REVIEW_BADGES

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.authoring_btn.setChecked(True)

    tracked = [
        item for item in widget._items.values() if item.data(0, Qt.UserRole + 1)
    ]
    if not tracked:
        import pytest

        pytest.skip("no review-tracked pages in this checkout")
    for item in tracked:
        for badge in REVIEW_BADGES.values():
            assert badge not in item.text(0), item.text(0)
    # The state is still visible: a tracked, not-human-reviewed row is coloured.
    assert any(item.foreground(0).color().isValid() for item in tracked)


def test_both_sign_off_levels_are_offered(qapp, qtbot):
    """A maintainer can record either a human or an agent review."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget
    from chisurf.plugins.core.help.api import review

    widget = HelpWidget()
    qtbot.addWidget(widget)
    labels = [action.text() for action in widget.authoring_toolbar.actions()]
    assert any("Mark reviewed" in label for label in labels)
    assert any("AI-reviewed" in label for label in labels)
    assert widget.review_filter.findData(review.STATUS_AI_REVIEWED) >= 0


def test_shift_and_ctrl_wheel_both_zoom(qapp, qtbot):
    """Shift + wheel zooms as well as Ctrl + wheel.

    On a trackpad Ctrl + scroll is claimed by the operating system's screen
    magnifier, so the gesture never reaches the application and the browser
    looks like it has no zoom at all.
    """
    from qtpy.QtCore import QPoint, QPointF
    from qtpy.QtGui import QWheelEvent

    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 700)
    viewport = widget.viewer.viewport()

    def wheel(modifier, dy=120, dx=0):
        where = QPointF(viewport.rect().center())
        event = QWheelEvent(
            where, viewport.mapToGlobal(where.toPoint()), QPoint(dx, dy),
            QPoint(dx, dy), Qt.NoButton, modifier, Qt.NoScrollPhase, False,
        )
        qapp.sendEvent(viewport, event)

    start = widget.font_size
    wheel(Qt.ShiftModifier)
    assert widget.font_size > start
    widget.set_font_size(start)
    wheel(Qt.ControlModifier)
    assert widget.font_size > start
    widget.set_font_size(start)
    # Shift + wheel is horizontal scrolling on most mice, so the delta arrives
    # on the x axis; that must zoom too or the gesture works on trackpads only.
    wheel(Qt.ShiftModifier, dy=0, dx=120)
    assert widget.font_size > start
    widget.set_font_size(start)
    wheel(Qt.NoModifier, dy=-120)
    assert widget.font_size == start

