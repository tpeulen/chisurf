"""The Ask Docs pane of the help browser (emtk app), ported from the retired Qt ``AskPanel`` tests.

The interesting behaviour is not that the pane draws -- it is what it does with an answer. A cited
page has to become a link that *opens*, an answer with no page read has to be marked as such, and
a failure has to reach the reader as words rather than as a traceback in the log. Each of those is
invisible to a construction test and each has been got wrong before.

The assistant is stubbed (``help.api.ask.ask``), so nothing here needs a language model. Only
drawn text, clicks and keys reach the window (emtk ``Driver``).
"""

from __future__ import annotations

import re
import time

import pytest
from emtk.testing import Driver

from chisurf.plugins.core.help.api import ask as ask_api
from chisurf.plugins.core.help.gui import ask_text
from chisurf.plugins.core.help.gui.ask_text import NO_PAGE_READ, compose_answer, linkify_pages
from chisurf.plugins.core.help.gui.help_app import QUICK_QUESTIONS, HelpApp

SIZE = (1500, 900)
ACCURATE = {
    "document": "docs/concepts/accurate_fret.md",
    "title": "Accurate FRET",
    "type": "Concept",
    "section": "",
}


class Stub:
    """Stands in for ``help.api.ask.ask``: returns a canned answer and records the questions."""

    def __init__(self) -> None:
        self.answer = ask_api.Answer(text="…", pages=[], ok=True)
        self.asked: list[str] = []

    def __call__(self, question, **_kwargs):
        self.asked.append(question)
        return self.answer


@pytest.fixture
def stub(monkeypatch):
    fake = Stub()
    monkeypatch.setattr(ask_api, "ask", fake)
    return fake


@pytest.fixture
def pane(stub):
    app = HelpApp()
    app.help_gui.show_ask()
    driver = Driver(app, SIZE)
    driver.frame(4)
    yield app, driver
    app.close()


def _drawn(driver) -> str:
    return " ".join(entry[5] for entry in driver.frame(2).texts)


def _answer(app, driver, question: str, timeout: float = 5.0) -> None:
    app.model.ask(question)
    end = time.monotonic() + timeout
    while app.model.is_asking and time.monotonic() < end:
        driver.frame()
        time.sleep(0.01)
    driver.frame(3)
    assert not app.model.is_asking


def _answer_obj(**fields):
    return ask_api.Answer(**{"ok": True, "text": "", "pages": [], **fields})


def test_the_empty_pane_says_what_it_is_for(pane):
    """A blank box with a cursor teaches a first-time reader nothing."""
    _app, driver = pane
    drawn = _drawn(driver)
    assert "only reads documentation" in drawn
    assert "gamma" in drawn.lower()


def test_provider_settings_open_the_ai_settings_form(pane):
    """The Ask pane's Provider settings… hosts the AI settings form (it raised ImportError)."""
    app, driver = pane
    driver.click("Provider settings…")
    drawn = _drawn(driver)
    assert app.help_gui.provider_settings_open and app.help_gui.provider_settings is not None
    assert "Provider settings" in drawn


def test_an_example_question_is_clickable(pane, stub):
    app, driver = pane
    driver.click(QUICK_QUESTIONS[0])
    end = time.monotonic() + 5.0
    while app.model.is_asking and time.monotonic() < end:
        driver.frame()
        time.sleep(0.01)
    assert stub.asked == [QUICK_QUESTIONS[0]]


def test_an_answer_lists_the_pages_it_came_from(pane, stub):
    app, driver = pane
    stub.answer = _answer_obj(
        text="The gamma factor corrects detection efficiencies.", pages=[ACCURATE]
    )
    _answer(app, driver, "what does gamma do?")
    drawn = _drawn(driver)
    assert "Accurate FRET" in drawn
    assert "docs/concepts/accurate_fret.md" in drawn


def test_an_answer_with_no_page_read_is_flagged(pane, stub):
    """An answer from the model's memory must not look like a cited one."""
    app, driver = pane
    stub.answer = _answer_obj(text="Probably in the settings.")
    _answer(app, driver, "where is it?")
    assert "No documentation page was opened" in _drawn(driver)
    assert NO_PAGE_READ in app.model.chat_history.messages[-1].content


def test_a_failure_reaches_the_reader(pane, stub):
    app, driver = pane
    stub.answer = _answer_obj(ok=False, error="no API key")
    _answer(app, driver, "anything")
    assert "no API key" in _drawn(driver)
    assert app.model.chat_history.messages[-1].role == "error"


def test_a_named_page_that_does_not_exist_is_called_out():
    role, text = compose_answer(_answer_obj(text="See it.", pages=[ACCURATE], fabricated=["docs/x.md"]))
    assert role == "assistant" and "does not exist: docs/x.md" in text


# -- the answer's own links ----------------------------------------------------------------------- #


def test_a_page_named_in_the_prose_becomes_a_link(pane, stub):
    """An answer that names a page and makes you go and find it is half done."""
    app, driver = pane
    stub.answer = _answer_obj(
        text="The four factors are in docs/concepts/accurate_fret.md.", pages=[ACCURATE]
    )
    _answer(app, driver, "where are the factors?")
    assert "](docs/concepts/accurate_fret.md)" in app.model.chat_history.messages[-1].content
    assert "](" not in _drawn(driver)  # drawn as a link, not as Markdown source


def test_a_markdown_link_the_model_wrote_is_rendered(pane, stub):
    app, driver = pane
    stub.answer = _answer_obj(
        text="See [the four factors](docs/concepts/accurate_fret.md#The four factors).",
        pages=[{**ACCURATE, "section": "The four factors"}],
    )
    _answer(app, driver, "where?")
    content = app.model.chat_history.messages[-1].content
    assert "accurate_fret.md#The four factors" in content
    assert "[the four factors]" not in _drawn(driver), "the Markdown was not rendered"


def test_linkify_leaves_an_unknown_path_alone():
    """Only a page that exists becomes a link; a dead one stays plain text."""
    out = linkify_pages("see docs/concepts/no_such_page.md for more")
    assert "](" not in out


def test_linkify_does_not_double_wrap_an_existing_link():
    original = "see [FRET](docs/concepts/fret.md) for more"
    assert linkify_pages(original) == original


def test_clicking_a_link_in_the_prose_opens_the_page(pane):
    """A Markdown link is a bare path; clicking it opens the page at its section."""
    app, _driver = pane
    app.help_gui._handle_link_click("docs/concepts/accurate_fret.md#The four factors")
    assert app.model.current_path.name == "accurate_fret.md"
    assert app.model.current_anchor == "The four factors"


def test_clicking_a_cited_source_opens_it(pane, stub):
    app, driver = pane
    stub.answer = _answer_obj(text="See the page.", pages=[ACCURATE])
    _answer(app, driver, "which page?")
    driver.click("Accurate FRET")
    driver.frame(2)
    assert app.model.current_path is not None
    assert app.model.current_path.name == "accurate_fret.md"


def test_a_second_question_is_not_sent_while_it_is_thinking(pane, stub):
    app, _driver = pane
    app.model.is_asking = True
    app.model.ask("another question")
    assert stub.asked == []
    app.model.is_asking = False


def test_clearing_returns_to_the_empty_state(pane, stub):
    app, driver = pane
    _answer(app, driver, "something")
    assert "only reads documentation" not in _drawn(driver)
    app.model.chat_history.clear()
    assert "only reads documentation" in _drawn(driver)


def test_an_empty_question_is_not_sent(pane, stub):
    app, _driver = pane
    app.model.ask("   ")
    assert stub.asked == [] and not app.model.chat_history.messages


# -- the browser around it ------------------------------------------------------------------------ #


def test_the_browser_offers_it_and_keeps_it_out_of_the_way(stub):
    """A tab beside the tree, not in front until asked for: the reading column is what the window is for."""
    app = HelpApp()
    try:
        driver = Driver(app, SIZE)
        drawn = _drawn(driver)
        assert "Ask Docs" in drawn
        assert "only reads documentation" not in drawn
        driver.click("Ask Docs")
        assert "only reads documentation" in _drawn(driver)
    finally:
        app.close()


def test_a_section_link_lands_on_the_heading(pane):
    """The slug the pane computes has to be the id the renderer emitted."""
    from chisurf.core.agent import doc_index
    from chisurf.plugins.core.help.api import markdown as md_api

    body = doc_index.read_body("docs/concepts/accurate_fret.md") or ""
    html = md_api.render_markdown(body) or ""
    ids = set(re.findall(r'id="([^"]+)"', html))
    for heading in ("The four factors", "Error bars", "See also"):
        assert md_api.slugify_heading(heading) in ids, heading
    app, _driver = pane
    assert app.model.open_page("docs/concepts/accurate_fret.md", anchor="The four factors")
    assert app.model.current_path.name == "accurate_fret.md"
    assert app.model.target_anchor == "The four factors"


def test_a_cited_page_opens_in_the_viewer(pane):
    """The identifier the assistant reports has to resolve to a real page."""
    app, _driver = pane
    app.help_gui._handle_link_click("docs/concepts/fret.md")
    assert app.model.current_path is not None
    assert app.model.current_path.name == "fret.md"


def test_an_unresolvable_citation_does_not_crash_the_browser(pane):
    app, driver = pane
    app.help_gui._handle_link_click("docs/concepts/no_such_page.md")
    driver.frame(2)


def test_the_empty_state_text_is_the_qt_panels():
    assert any("only reads documentation" in p for p in ask_text.EMPTY_STATE)
