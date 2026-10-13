"""The emtk help browser at parity with the Qt HelpWidget: start page, tree, breadcrumb, labels.

The Qt facts are ``qt_reference.json``, recorded from the legacy ``HelpWidget`` and frozen as a rule
over the docs tree (see ``QT`` below), so this file imports no Qt.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.help.gui.help_app import make_help_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PAGE = REPO / "docs" / "concepts" / "fret.md"
EMOJI = re.compile("[\U0001f000-\U0001ffff☀-➿️]")

#: The legacy Qt ``HelpWidget``'s facts, recorded from the live widget (offscreen) and frozen.
#: Its start page and breadcrumb are a *function of the docs tree*, so what is frozen is the rule:
#: ``qt_home_links`` / ``qt_breadcrumb`` below restate it Qt-free, and the record holds the live
#: widget's output next to the rule's output on the same tree (``rule_*``), which were equal at
#: ``_recorded.source_commit``. A docs edit then moves both sides together instead of going stale.
QT = json.loads((HERE / "qt_reference.json").read_text(encoding="utf-8"))


def qt_home_links(toc, root: Path) -> list[tuple[str, str]]:
    """The Qt start page's links ``(file name, title)``: *Start here*, then one per top section.

    Parameters
    ----------
    toc : Node
        The documentation's table of contents (``app.model.toc``).
    root : Path
        The repository root the *Start here* paths are relative to.

    Returns
    -------
    list of tuple of str
    """
    from chisurf.plugins.core.help.api import toc as help_toc

    links = []
    for relative, _description in QT["start_here"]:
        path = root / relative
        if path.is_file():
            links.append((path.name, help_toc.page_title(path) or path.stem))
    for section in toc.children if toc else []:
        target = section.path or (section.children[0].path if section.children else None)
        if target is not None:
            links.append((Path(str(target)).name, section.title))
    return links


def qt_breadcrumb(toc, page: Path) -> str:
    """The Qt breadcrumb of *page*: the titles of the sections above it, joined by `` › ``.

    Parameters
    ----------
    toc : Node
        The documentation's table of contents.
    page : Path
        An open documentation page.

    Returns
    -------
    str
    """
    target = str(page.resolve())

    def walk(node, trail):
        for child in node.children:
            here = trail + [child.title]
            if child.path and str(Path(str(child.path)).resolve()) == target:
                return here
            found = walk(child, here)
            if found is not None:
                return found
        return None

    trail = walk(toc, []) or []
    return " › ".join(part for part in trail[:-1] if part)


@pytest.fixture
def app():
    app = make_help_app()
    yield app
    app.close()


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


# 0. the record: the live Qt widget's output was the rule's output on the same docs tree
def test_the_recorded_qt_facts_are_the_rule():
    assert [tuple(x) for x in QT["home_links"]] == [tuple(x) for x in QT["rule_home_links"]]
    assert QT["breadcrumb"] == QT["rule_breadcrumb"] and QT["breadcrumb"]
    from chisurf.plugins.core.help.gui.help_app import HelpModel

    assert [(f"{stem}.md", text) for stem, text in HelpModel.START_HERE] == [
        tuple(x) for x in QT["start_here"]
    ]


# 1. the start page lists the same pages, with the same titles, as the Qt start page
def test_start_page_matches_the_qt_start_page(app):
    from chisurf.plugins.core.help.api import toc as help_toc

    home = app.model._build_home_content()
    ours = [
        (Path(target).name, title) for title, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", home)
    ]
    assert ours == qt_home_links(app.model.toc, help_toc.repository_root())
    assert "Welcome to ChiSurf Documentation" not in home  # the earlier hard-coded page


# 1b. the breadcrumb of an open page is the Qt one
def test_breadcrumb_matches_the_qt_window(app):
    app.model.open_page(PAGE)
    painter = _draw(app)
    crumb = " › ".join(app.model.breadcrumb())
    assert crumb and crumb == qt_breadcrumb(app.model.toc, PAGE)
    assert crumb in painter.strings


# 2. the tree opens to the page that is shown, once, and can be collapsed again
def _drawn(title, strings):
    """*title* drawn whole, or shortened to a prefix plus "…" in a row narrower than it."""
    return any(
        text == title
        or (text.endswith("…") and len(text) > 4 and title.startswith(text[:-1].rstrip()))
        for text in strings
    )


def test_tree_opens_to_the_open_page(app):
    target = str(PAGE.resolve())

    def parent_of(node):
        for child in node.children:
            if child.path and str(Path(child.path).resolve()) == target:
                return node
            found = parent_of(child)
            if found is not None:
                return found
        return None

    group = parent_of(app.model.toc)
    # a sibling's title is drawn only by the tree (the page's own title is also its heading)
    sibling = next(
        c.title for c in group.children if not (c.path and str(Path(c.path).resolve()) == target)
    )
    painter = _draw(app)
    assert not _drawn(sibling, painter.strings)
    app.model.open_page(PAGE)
    painter = _draw(app)
    assert _drawn(sibling, painter.strings)
    assert app.help_gui._reveal_keys == set()  # revealed once, not forced open


# 2b. back/forward are disabled, not recoloured, when there is nowhere to go
def test_navigation_actions(app):
    app.model.open_page(PAGE)
    assert app.model.history_idx == 1
    app.model.go_back()
    assert app.model.current_path is None
    app.model.go_forward()
    assert app.model.current_path == PAGE.resolve()
    assert app.model.navigate_address("docs/no/such/page.md") in (True, False)  # never raises


# 4. draws, home and page, at both sizes, with no pictogram in any label
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_home_and_page_without_pictograms(app, size):
    painter = _draw(app, size)
    assert "ChiSurf documentation" in painter.strings
    assert "Online docs" in painter.strings
    app.model.open_page(PAGE)
    painter = _draw(app, size)
    assert any("Förster resonance energy transfer" in s for s in painter.strings)
    # The only pictograms are the shared action vocabulary's own (Help, Guide, ...): the same action looks the
    # same in every window; labels of the documentation itself carry none.
    from chisurf.plugins.emtk_layout import action_caption

    canonical = {action_caption(key) for key in ("help", "guide", "close", "copy", "open", "save")}
    pictured = sorted({s for s in painter.strings if EMOJI.search(s)} - canonical)
    assert pictured == []


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("help")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("help"))
    assert inv["controls_without_tooltip"] == []
    assert {"onlinedocs", "videos", "home", "back", "fwd"} <= set(inv["controls"])  # normalised


# 8. persistence
def test_settings_round_trip(app):
    app.model.zoom(2)
    saved = app.export_settings()
    other = make_help_app()
    try:
        other.restore_settings(json.loads(json.dumps(saved)))
        assert other.model.font_size == app.model.font_size != 12.0
    finally:
        other.close()


# 2c. Developer docs (Qt authoring toolbar) adds the development section to the tree
def test_developer_docs_toggle_lists_development_pages(app):
    titles = [n.title for n in app.model.toc.children]
    assert "Developing ChiSurf" not in titles
    app.model.authoring_mode = True
    painter = _draw(app)
    assert "Developer docs" in painter.strings
    app.model.set_include_development(True)
    assert "Developing ChiSurf" in [n.title for n in app.model.toc.children]
    app.model.set_include_development(False)
    assert [n.title for n in app.model.toc.children] == titles
