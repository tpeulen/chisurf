"""The Ask panel in the help browser.

The interesting behaviour is not that the widget constructs — it is what the
panel does with an answer. A cited page has to become a link that *opens*, an
answer with no page read has to be marked as such, and a failure has to reach
the reader as words rather than as a traceback in the log. Each of those is
invisible to a construction test and each has been got wrong before.

The client is stubbed, so nothing here needs a language model.
"""

from __future__ import annotations

import pytest
from qtpy.QtCore import QUrl


class StubClient:
    """A HelpClient stand-in that returns a canned answer."""

    def __init__(self, answer: dict | None = None):
        self.answer = answer or {"ok": True, "text": "…", "pages": []}
        self.asked: list[str] = []

    def ask(self, question: str, model: str = "", provider: str = "") -> dict:
        self.asked.append(question)
        return dict(self.answer)


@pytest.fixture
def panel(qapp, qtbot):
    """Return an Ask panel wired to a stub client."""
    from chisurf.plugins.core.help.gui.ask_panel import AskPanel

    widget = AskPanel(StubClient())
    qtbot.addWidget(widget)
    return widget


def test_the_empty_panel_says_what_it_is_for(panel):
    """A blank box with a cursor teaches a first-time reader nothing."""
    html = panel.transcript.toHtml()
    assert "only reads documentation" in html
    assert "gamma" in html.lower()


def test_an_example_question_is_clickable(panel, qtbot):
    from chisurf.plugins.core.help.gui.ask_panel import EXAMPLE_QUESTIONS

    panel._on_anchor(QUrl(f"ask:{EXAMPLE_QUESTIONS[0]}"))
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    assert panel._client.asked == [EXAMPLE_QUESTIONS[0]]


def test_an_answer_lists_the_pages_it_came_from(panel, qtbot):
    panel._client.answer = {
        "ok": True,
        "text": "The gamma factor corrects detection efficiencies.",
        "pages": [
            {
                "document": "docs/concepts/accurate_fret.md",
                "title": "Accurate FRET",
                "type": "Concept",
                "section": "",
            }
        ],
    }
    panel.ask("what does gamma do?")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)

    html = panel.transcript.toHtml()
    assert "Accurate FRET" in html
    assert "docs/concepts/accurate_fret.md" in html


def test_an_answer_with_no_page_read_is_flagged(panel, qtbot):
    """An answer from the model's memory must not look like a cited one."""
    panel._client.answer = {"ok": True, "text": "Probably in the settings.", "pages": []}
    panel.ask("where is it?")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    assert "No documentation page was opened" in panel.transcript.toHtml()


def test_a_failure_reaches_the_reader(panel, qtbot):
    panel._client.answer = {"ok": False, "text": "", "pages": [], "error": "no API key"}
    panel.ask("anything")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    assert "no API key" in panel.transcript.toHtml()


# ── the answer's own links ────────────────────────────────────────────


def test_a_page_named_in_the_prose_becomes_a_link(panel, qtbot):
    """An answer that names a page and makes you go and find it is half done."""
    panel._client.answer = {
        "ok": True,
        "text": "The four factors are in docs/concepts/accurate_fret.md.",
        "pages": [{"document": "docs/concepts/accurate_fret.md", "title": "Accurate FRET",
                   "type": "Concept", "section": ""}],
    }
    panel.ask("where are the factors?")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    html = panel.transcript.toHtml()
    assert 'href="docs/concepts/accurate_fret.md"' in html


def test_a_markdown_link_the_model_wrote_is_rendered(panel, qtbot):
    panel._client.answer = {
        "ok": True,
        "text": "See [the four factors](docs/concepts/accurate_fret.md#The four factors).",
        "pages": [{"document": "docs/concepts/accurate_fret.md", "title": "Accurate FRET",
                   "type": "Concept", "section": "The four factors"}],
    }
    panel.ask("where?")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    html = panel.transcript.toHtml()
    assert "accurate_fret.md#The four factors" in html
    assert "[the four factors]" not in html, "the Markdown was not rendered"


def test_linkify_leaves_an_unknown_path_alone():
    """Only a page that exists becomes a link; a dead one stays plain text."""
    from chisurf.plugins.core.help.gui.ask_panel import linkify_pages

    out = linkify_pages("see docs/concepts/no_such_page.md for more")
    assert "](" not in out


def test_linkify_does_not_double_wrap_an_existing_link():
    from chisurf.plugins.core.help.gui.ask_panel import linkify_pages

    original = "see [FRET](docs/concepts/fret.md) for more"
    assert linkify_pages(original) == original


def test_clicking_a_link_in_the_prose_opens_the_page(panel, qtbot):
    """A Markdown link is a bare path, not the source list's `doc:` scheme."""
    from qtpy.QtCore import QUrl

    with qtbot.waitSignal(panel.pageRequested, timeout=2000) as blocker:
        panel._on_anchor(QUrl("docs/concepts/accurate_fret.md#The four factors"))
    assert blocker.args == ["docs/concepts/accurate_fret.md", "The four factors"]


def test_clicking_a_source_asks_the_browser_to_open_it(panel, qtbot):
    with qtbot.waitSignal(panel.pageRequested, timeout=2000) as blocker:
        panel._on_anchor(QUrl("doc:docs/concepts/fret.md#What it is"))
    assert blocker.args == ["docs/concepts/fret.md", "What it is"]


def test_the_input_is_disabled_while_it_is_thinking(panel):
    panel._set_busy(True, "Reading the documentation…")
    assert not panel.input.isEnabled()
    assert panel.status.isVisible() or panel.status.text()
    panel._set_busy(False, "")
    assert panel.input.isEnabled()


def test_clearing_returns_to_the_empty_state(panel, qtbot):
    panel.ask("something")
    qtbot.waitUntil(lambda: not panel.busy, timeout=5000)
    panel.clear()
    assert "only reads documentation" in panel.transcript.toHtml()


def test_an_empty_question_is_not_sent(panel):
    panel.input.setText("   ")
    panel.submit()
    assert panel._client.asked == []


# ── the browser around it ─────────────────────────────────────────────


def test_the_browser_offers_it_and_keeps_it_out_of_the_way(qapp, qtbot):
    """Hidden until asked for: the reading column is what the window is for."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    assert not widget.ask_panel.isVisible()
    assert not widget.ask_btn.isChecked()

    widget.show_ask_panel()
    assert widget.ask_btn.isChecked()
    assert widget.splitter.sizes()[2] > 0


def test_a_section_link_lands_on_the_heading(qapp, qtbot):
    """The slug the panel computes has to be the id the renderer emitted.

    When it is not, the viewer stays where it was and the link silently does
    nothing — the failure looks like a page that simply did not scroll.
    """
    import re

    from chisurf.core.agent import doc_index
    from chisurf.plugins.core.help.api import markdown as md_api
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)

    body = doc_index.read_body("docs/concepts/accurate_fret.md") or ""
    html = md_api.render_markdown(body) or ""
    ids = set(re.findall(r'id="([^"]+)"', html))
    for heading in ("The four factors", "Error bars", "See also"):
        assert md_api.slugify_heading(heading) in ids, heading

    widget._on_ask_page_requested("docs/concepts/accurate_fret.md", "The four factors")
    assert widget.current_path is not None
    assert widget.current_path.name == "accurate_fret.md"


def test_a_cited_page_opens_in_the_viewer(qapp, qtbot):
    """The identifier the assistant reports has to resolve to a real page."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget._on_ask_page_requested("docs/concepts/fret.md", "")
    assert widget.current_path is not None
    assert widget.current_path.name == "fret.md"


def test_an_unresolvable_citation_does_not_crash_the_browser(qapp, qtbot):
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget._on_ask_page_requested("docs/concepts/no_such_page.md", "")
