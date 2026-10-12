"""The Ask Docs answer is rendered Markdown, and its links open the documentation browser."""

from __future__ import annotations

import pytest

pytest.importorskip("emtk")

from emtk.testing import Driver  # noqa: E402

from chisurf.plugins.core.help.gui.help_app import HelpApp  # noqa: E402

ANSWER = (
    "The **gamma factor** corrects the green/red ratio. See "
    "[The four factors](docs/concepts/accurate_fret.md#The four factors).\n\n"
    "**Cited Documentation Pages:**\n"
    "- [Accurate FRET: automatic correction factors](docs/guides/41_accurate_fret.md)"
)


@pytest.fixture
def ask_app():
    app = HelpApp()
    app.help_gui.show_ask()
    history = app.model.chat_history
    history.add_message("user", "What does gamma do?")
    history.add_message("assistant", ANSWER)
    history.finish_generation("complete")
    driver = Driver(app, (1500, 900))
    driver.frame(6)
    yield app, driver
    close = getattr(app, "close", None)
    if callable(close):
        close()


def _drawn(driver) -> list[str]:
    return [t[5] for t in driver.frame(2).texts]


def test_answer_is_not_raw_markdown(ask_app):
    _app, driver = ask_app
    drawn = " ".join(_drawn(driver))
    assert "**" not in drawn
    assert "](" not in drawn
    assert "Accurate FRET: automatic correction factors" in drawn


def test_clicking_a_cited_page_opens_it_in_the_documentation_browser(ask_app):
    app, driver = ask_app
    driver.click("Accurate FRET: automatic correction factors")
    driver.frame(3)
    assert app.model.current_path is not None
    assert app.model.current_path.name == "41_accurate_fret.md"


def test_clicking_an_inline_heading_link_opens_the_section(ask_app):
    app, driver = ask_app
    # the narrow pane wraps the link, so click the piece that holds "four"
    piece = next(t[5] for t in driver.frame(2).texts if "four" in t[5] and t[5].startswith(("The", "four")))
    driver.click(piece)
    driver.frame(3)
    assert app.model.current_path.name == "accurate_fret.md"
