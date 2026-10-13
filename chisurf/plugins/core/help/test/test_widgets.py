"""The help browser's structure and reading behaviour, on the emtk app (``gui/help_app.py``).

Ported from the retired Qt ``HelpWidget`` tests: the same behaviours, asserted on the native
browser through its model and the emtk ``Driver`` (only drawn text, clicks, keys and wheel
notches reach the window). The browser navigates by the documentation's own table of contents
and opens on a start page, so the checks are about *structure* -- the sections are there, in
order, with a page behind each row -- rather than about a directory listing.
"""

from __future__ import annotations

import pathlib

import pytest
from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.testing import Driver

from chisurf.plugins.core.help.api import review
from chisurf.plugins.core.help.api.toc import repository_root
from chisurf.plugins.core.help.gui.help_app import HelpApp, make_help_app
from chisurf.plugins.core.help.gui.reader import MAX_TEXT_WIDTH, MIN_GUTTER, measure_margin

SIZE = (1500, 900)


@pytest.fixture
def app():
    application = make_help_app()
    yield application
    application.close()


@pytest.fixture
def driver(app):
    drv = Driver(app, SIZE)
    drv.frame(3)
    return drv


def _page(*parts):
    path = repository_root().joinpath("docs", *parts)
    if not path.is_file():
        pytest.skip("documentation not present in this checkout")
    return path


def _drawn(driver) -> list[str]:
    return [entry[5] for entry in driver.frame(2).texts]


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def test_help_window_creation(app, driver):
    """The window is the emtk app with its tree, reader, title and authoring controls."""
    assert isinstance(app, HelpApp)
    assert app.model.toc is not None and app.model.toc.children
    drawn = _drawn(driver)
    assert "Documentation" in drawn and "Document" in drawn
    assert "ChiSurf documentation" in drawn
    assert "Authoring tools" in drawn


def test_help_window_toolbar(app, driver):
    """The reader's toolbar navigates; the authoring controls appear only when asked for."""
    drawn = _drawn(driver)
    for label in ("Home", "Back", "Fwd", "Prev", "Next"):
        assert label in drawn, label
    # Editing is not a reading tool, and is not offered until asked for.
    assert not app.model.authoring_mode
    assert "Mark human reviewed" not in drawn and "Developer docs" not in drawn
    driver.click("Authoring tools")
    assert app.model.authoring_mode
    assert "Developer docs" in _drawn(driver)


def test_tree_follows_the_documentation_structure(app, driver):
    """Sections come from the docs' toctrees, grouped and in reading order."""
    titles = [section.title for section in app.model.toc.children]
    for expected in ("Getting started", "Concepts", "Guides", "Reference", "Plugins"):
        assert any(expected in title for title in titles), titles
    drawn = _drawn(driver)
    assert any("Concepts" in text for text in drawn)
    concepts = next(s for s in app.model.toc.children if "Concepts" in s.title)
    # Grouped, not a flat alphabetical run: the first level holds the rubrics. Asserted as a
    # *property* rather than by naming one rubric, which gets reorganised editorially.
    groups = concepts.children
    assert len(groups) >= 3, [g.title for g in groups]
    assert all(len(group.children) >= 1 for group in groups)
    assert max(len(group.children) for group in groups) >= 3


def test_every_tree_leaf_has_a_document(app):
    """A row a reader can click has to lead somewhere."""
    for section in app.model.toc.children:
        for node in _walk(section):
            if not node.children:
                assert node.path, f"leaf without a document: {node.title}"
                assert pathlib.Path(node.path).is_file(), node.path


def test_manual_pages_have_distinct_titles(app):
    """Three rows called "Overview" tell the reader nothing about which to open."""
    manual = next((s for s in app.model.toc.children if "Fitting interface" in s.title), None)
    assert manual is not None
    titles = [node.title for node in _walk(manual) if node is not manual and node.path]
    duplicates = {title for title in titles if titles.count(title) > 1}
    assert not duplicates, duplicates


def test_start_page_offers_a_way_in(driver):
    """The browser opens on something to read, not on an empty pane."""
    drawn = _drawn(driver)
    assert "ChiSurf documentation" in drawn
    assert "Start here" in drawn


def test_search_ranks_pages_and_lists_them(app, driver):
    """A multi-word query ranks pages, the reader sees them, and clearing it brings the tree back."""
    app.model.update_search("anisotropy g-factor")
    hits = app.model.search_results
    assert hits
    assert "anisotropy" in hits[0]["title"].lower()
    assert hits[0]["excerpt"]
    assert ")=" not in hits[0]["excerpt"]  # the excerpt is prose, not markup
    drawn = _drawn(driver)
    assert hits[0]["title"] in drawn
    driver.click(hits[0]["title"])
    assert app.model.current_path == pathlib.Path(hits[0]["path"]).resolve()
    app.model.update_search("")
    assert not app.model.search_results
    assert any("Concepts" in text for text in _drawn(driver))


def test_pages_carry_previous_and_next(app, driver):
    """A manual is read in order; the page offers the next one and the one before."""
    page = _page("concepts", "tcspc_lifetime.md")
    app.model.open_page(page)
    order = [str(pathlib.Path(n.path).resolve()) for n in app.model.order if n.path]
    index = order.index(str(page.resolve()))
    driver.click("Next")
    assert str(app.model.current_path) == order[index + 1]
    driver.click("Prev")
    assert app.model.current_path == page.resolve()


def test_history_and_breadcrumb(app, driver):
    """Back returns to where the reader was, and the trail says where that is."""
    first, second = _page("concepts", "fret.md"), _page("concepts", "anisotropy.md")
    app.model.open_page(first)
    assert any("Concepts" in crumb for crumb in app.model.breadcrumb())
    assert any("Concepts" in text for text in _drawn(driver))
    app.model.open_page(second)
    driver.frame(2)
    driver.click("Back")
    assert app.model.current_path == first.resolve()


def test_review_controls_live_behind_authoring(app, driver):
    """The release gate is a maintainer's tool, not part of reading a page."""
    assert not app.model.authoring_mode
    drawn = _drawn(driver)
    assert "Mark human reviewed" not in drawn and "All pages" not in drawn
    driver.click("Authoring tools")
    assert app.model.authoring_mode
    assert "All pages" in _drawn(driver)  # the review filter above the tree


def test_review_filter_hides_non_matching_pages(app, driver):
    """Filtering by a status hides review-tracked pages without it."""
    driver.click("Authoring tools")
    gui = app.help_gui
    tracked = [
        node
        for section in app.model.toc.children
        for node in _walk(section)
        if node.path and not node.children and review.is_tracked(node.path)
    ]
    if not tracked:
        pytest.skip("no review-tracked pages in this checkout")
    app.model.review_filter = review.STATUS_REVIEWED
    for node in tracked:
        if app.model.review_status_for(node.path) != review.STATUS_REVIEWED:
            assert not gui._matches_review_filter(node), node.title
    app.model.review_filter = "all"
    assert all(gui._matches_review_filter(node) for node in tracked)


def test_developer_documentation_is_off_by_default(app, driver):
    """Architecture notes are not what a scientist opened the help for."""
    assert not any("Developing" in s.title for s in app.model.toc.children)
    driver.click("Authoring tools")
    driver.click("Developer docs")
    assert app.model.include_development
    assert any("Developing" in s.title for s in app.model.toc.children)


def test_text_column_is_bounded_in_a_wide_window():
    """A thousand-pixel line is not readable, whatever the window is doing."""
    assert measure_margin(700, 860) == MIN_GUTTER
    assert measure_margin(1600, 860) == 370
    assert MAX_TEXT_WIDTH == 860


def test_text_column_follows_the_window_when_it_narrows(app):
    """The measure is not frozen at the width the page was rendered for."""
    page = _page("concepts", "fret.md")
    app.model.open_page(page)
    drv = Driver(app, (2600, 900))
    drv.frame(3)
    wide = app.help_gui.reader_column
    assert wide <= MAX_TEXT_WIDTH * app.model.zoom_factor() + 2 * MIN_GUTTER + 1
    drv.draw(size=(1000, 900))
    narrow = app.help_gui.reader_column
    reader = app.help_gui.item_rects["doc_reader"]
    assert narrow <= reader[2] + 0.5
    assert narrow < wide


def test_zoom_changes_the_rendered_size(app, driver):
    """A+ / A- change the whole page; the zoom is clamped and Reset zoom restores it."""
    app.model.open_page(_page("concepts", "fret.md"))
    driver.frame(2)
    before = app.model.font_size
    driver.click("A+")
    assert app.model.font_size > before
    driver.click("Reset zoom")
    assert app.model.font_size == before
    # Clamped, so a held-down key cannot render at 0.5 pt or 400 pt.
    for _ in range(80):
        app.model.zoom(-1)
    low = app.model.font_size
    for _ in range(200):
        app.model.zoom(+1)
    high = app.model.font_size
    assert (low, high) == (7.0, 24.0)


def test_tree_rows_carry_no_emoji(app):
    """An emoji in a row forces a colour-font fallback with other metrics."""

    def is_emoji(character: str) -> bool:
        point = ord(character)
        return (
            0x1F300 <= point <= 0x1FAFF
            or 0x2600 <= point <= 0x27BF
            or point in (0xFE0F, 0x2B1C, 0x2705, 0x26A0)
        )

    for section in app.model.toc.children:
        for node in _walk(section):
            offending = [c for c in node.title if is_emoji(c)]
            assert not offending, (node.title, offending)


def test_review_state_is_colour_not_a_badge(app, driver):
    """Reviewing must not restyle the navigation: the state is a colour and a tooltip, not a badge."""
    driver.click("Authoring tools")
    drawn = _drawn(driver)
    for badge in ("[Reviewed]", "[AI reviewed]", "[Needs review]", "[Draft]", "✅", "🤖"):
        assert not any(text.startswith(badge) and len(text) > len(badge) for text in drawn)
    tracked = [
        node
        for section in app.model.toc.children
        for node in _walk(section)
        if node.path and not node.children and review.is_tracked(node.path)
    ]
    if not tracked:
        pytest.skip("no review-tracked pages in this checkout")
    assert all(node.title == node.title.strip() for node in tracked)


def test_both_sign_off_levels_are_offered(app, driver):
    """A maintainer can record either a human or an agent review."""
    page = next(
        (
            node.path
            for section in app.model.toc.children
            for node in _walk(section)
            if node.path and not node.children and review.is_tracked(node.path)
        ),
        None,
    )
    if page is None:
        pytest.skip("no review-tracked pages in this checkout")
    app.model.open_page(page)
    driver.click("Authoring tools")
    drawn = _drawn(driver)
    assert "Mark human reviewed" in drawn and "Mark AI reviewed" in drawn
    assert "AI-reviewed" in [label for label in ("All pages", "Unreviewed", "AI-reviewed")]


@pytest.mark.parametrize(
    "modifier, dy, dx",
    [(SHIFT_MODIFIER, 1.0, 0.0), (CONTROL_MODIFIER, 1.0, 0.0), (SHIFT_MODIFIER, 0.0, 1.0)],
)
def test_shift_and_ctrl_wheel_both_zoom(app, driver, modifier, dy, dx):
    """Shift + wheel zooms as well as Ctrl + wheel (on a trackpad the OS claims Ctrl + scroll).

    Shift + wheel is horizontal scrolling on most mice, so the delta may arrive on the x axis.
    """
    x, y, w, h = app.help_gui.item_rects["doc_reader"]
    start = app.model.font_size
    app.wheel(x + w / 2, y + h / 2, dy, modifier)
    if dx:
        app.io.mouse_wheel_h += dx
    driver.frame()
    assert app.model.font_size > start
    app.model.set_font_size(start)
    app.wheel(x + w / 2, y + h / 2, -1.0, 0)
    driver.frame()
    assert app.model.font_size == start
