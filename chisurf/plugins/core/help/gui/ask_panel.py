"""The *Ask* panel: a conversation with the documentation, inside the browser.

The tree and the search box both assume the reader already knows roughly where
the answer lives. This panel is for when they do not: a question in ordinary
words, answered out of the pages, with the pages it used listed underneath as
links that open in the viewer beside it.

Two things it deliberately is not:

**It is not a general assistant.** The session behind it
(:mod:`chisurf.plugins.core.help.api.ask`) holds three read-only tools and
nothing else. It cannot load data or run a fit, so it cannot be talked into
doing so by a question that sounds like an instruction.

**It is not a black box.** Every answer is followed by the pages that were
actually read, taken from the tool calls rather than from the model's own
footnotes. Clicking one opens it — an answer is a way *into* the
documentation, not a replacement for reading it.

The call is slow (a model round trip plus several page reads), so it runs on a
worker thread; the panel stays responsive and the question can be abandoned by
closing the panel.
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chisurf.gui.glyphs import Glyphs
from chisurf.plugins.core.help.api import markdown as md_api

logger = logging.getLogger(__name__)

#: Questions offered on the empty panel. They are the ones the documentation
#: answers well, and they double as a statement of what the panel is for — a
#: blank box with a cursor tells a first-time user nothing.
EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "What does the gamma correction factor do?",
    "How do I fit a fluorescence decay with an instrument response?",
    "Which tool fuses bursts that one molecule produced?",
    "What file formats can ChiSurf read?",
)


#: A documentation path as a model writes it in prose, when it has not used
#: the link syntax. Only paths that resolve are linked — a fabricated one has
#: already been struck by ``ask.verify_citations`` before it gets here.
_BARE_PATH = re.compile(r"(?<!\()(?<!/)\b((?:docs|okf)/[\w./-]+\.md)(?:#([\w -]+))?\b(?!\))")


def linkify_pages(text: str) -> str:
    """Turn documentation paths in *text* into Markdown links.

    Parameters
    ----------
    text : str
        The answer, as the model wrote it.

    Returns
    -------
    str
        The same text with every resolvable bare page path replaced by a link
        carrying the page's own title. Paths already inside a Markdown link are
        left alone.
    """
    from chisurf.core.agent.doc_index import DocIndex

    try:
        index = DocIndex.load()
    except Exception:  # pragma: no cover - the index is a cache, not a hard dep
        return text

    def replace(match: re.Match[str]) -> str:
        document, section = match.group(1), match.group(2) or ""
        entry = index.get(document)
        if entry is None:
            return match.group(0)
        label = section or entry.title or document
        target = f"{document}#{section}" if section else document
        return f"[{label}]({target})"

    return _BARE_PATH.sub(replace, text)


class _AskThread(QThread):
    """Runs one question on a background thread."""

    answered = Signal(dict)

    def __init__(self, client, question: str):
        super().__init__()
        self._client = client
        self._question = question

    def run(self) -> None:
        """Ask, and emit whatever comes back — including the failure."""
        try:
            answer = self._client.ask(self._question)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("the documentation assistant failed")
            answer = {"ok": False, "error": str(exc), "text": "", "pages": []}
        self.answered.emit(dict(answer or {}))


class AskPanel(QWidget):
    r"""A question-and-answer transcript over ChiSurf's documentation.

    Parameters
    ----------
    client : HelpClient
        The plugin client the question is put through.
    parent : QWidget, optional
        Parent widget.
    math_provider : callable, optional
        ``provider(max_width) -> MathRenderer``, used to typeset formulas at
        the panel's own width. Without one the mathematics stays as its LaTeX
        source, which is what an answer full of ``$\\Delta G = \\ldots$``
        looks like.

    Attributes
    ----------
    pageRequested : Signal
        Emitted with ``(document, section)`` when the reader clicks one of the
        cited pages. The browser navigates; the panel does not.
    """

    pageRequested = Signal(str, str)

    def __init__(self, client, parent: QWidget | None = None, math_provider=None):
        super().__init__(parent)
        self._client = client
        # The browser's own renderer, so a formula is typeset once per session
        # and comes out in the same face and colour as the pages beside it.
        self._math_provider = math_provider
        self._thread: _AskThread | None = None
        self._turns: list[str] = []
        self._last_anchor = ""
        self.setMinimumWidth(300)
        self._build()
        self._render()

    # ── construction ──────────────────────────────────────────────────

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(4)
        title = QLabel(f"{Glyphs.BOOK if hasattr(Glyphs, 'BOOK') else '📖'} Ask the docs")
        title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        header.addWidget(title)
        header.addStretch(1)

        self.clear_btn = QToolButton()
        self.clear_btn.setText("🗑")
        self.clear_btn.setToolTip("Clear the conversation")
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setOpenExternalLinks(False)
        self.transcript.anchorClicked.connect(self._on_anchor)
        self.transcript.setFrameShape(QTextBrowser.NoFrame)
        layout.addWidget(self.transcript, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #8a8a8a; font-size: 9pt;")
        self.status.setVisible(False)
        layout.addWidget(self.status)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask a question about ChiSurf…")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self.submit)
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self.input, 1)

        self.send_btn = QToolButton()
        self.send_btn.setText("➤")
        self.send_btn.setToolTip("Ask (Enter)")
        self.send_btn.clicked.connect(self.submit)
        row.addWidget(self.send_btn)
        layout.addLayout(row)

    # ── conversation ──────────────────────────────────────────────────

    def clear(self) -> None:
        """Forget the conversation and show the empty state again."""
        self._turns = []
        self._last_anchor = ""
        self.status.setVisible(False)
        self._render()

    @property
    def busy(self) -> bool:
        """Whether a question is currently being answered."""
        return self._thread is not None and self._thread.isRunning()

    def submit(self) -> None:
        """Send whatever is in the input box."""
        question = self.input.text().strip()
        if not question or self.busy:
            return
        self.ask(question)

    def wait(self, timeout_ms: int = 5000) -> bool:
        """Wait for any running background worker thread to finish."""
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
            ok = self._thread.wait(timeout_ms)
            if not ok and self._thread.isRunning():
                self._thread.terminate()
                self._thread.wait(500)
            return ok
        return True

    def closeEvent(self, event) -> None:
        self.wait()
        super().closeEvent(event)

    def ask(self, question: str) -> None:
        """Put *question* to the documentation and show the answer.

        Parameters
        ----------
        question : str
            The question, in plain language.
        """
        if self.busy:
            return
        if self._thread is not None:
            self.wait(1000)
        self.input.clear()
        self._last_anchor = f"turn{len(self._turns)}"
        self._turns.append(self._question_html(question, len(self._turns)))
        self._render()
        self._set_busy(True, "Reading the documentation…")

        self._thread = _AskThread(self._client, question)
        self._thread.answered.connect(self._on_answer)
        self._thread.start()

    def _on_answer(self, answer: dict) -> None:
        """Append an answer (or the reason there is none) to the transcript."""
        self._set_busy(False, "")
        if answer.get("text"):
            self._turns.append(self._answer_html(answer))
        else:
            self._turns.append(self._error_html(answer))
        self._render()

    def _set_busy(self, busy: bool, message: str) -> None:
        """Show or hide the working indicator."""
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.status.setText(message)
        self.status.setVisible(bool(message))

    # ── rendering ─────────────────────────────────────────────────────

    def _render(self) -> None:
        """Redraw the transcript, showing the start of the newest exchange.

        Scrolling to the *bottom* is what a chat window does and it is wrong
        here: an answer with an equation and a list of terms is taller than the
        panel, so the bottom hides the question and the first paragraph — the
        part the reader wants. The view goes to the last question instead.
        """
        body = "\n".join(self._turns) if self._turns else self._empty_html()
        self.transcript.setHtml("<body style='font-size:10pt;'>" + body + "</body>")
        if self._last_anchor:
            self.transcript.scrollToAnchor(self._last_anchor)
        else:
            bar = self.transcript.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _empty_html(self) -> str:
        """Return the transcript shown before anything has been asked."""
        examples = "".join(
            f"<li style='margin-bottom:4px;'><a href='ask:{_html.escape(question)}'>"
            f"{_html.escape(question)}</a></li>"
            for question in EXAMPLE_QUESTIONS
        )
        return (
            "<p style='color:#8a8a8a;'>Ask about anything ChiSurf's documentation "
            "covers — what a method means, how to carry out an analysis, what a "
            "setting does. The answer names the pages it came from, and clicking "
            "one opens it.</p>"
            "<p style='color:#8a8a8a;'>The assistant only reads documentation. It "
            "cannot load data or run a fit.</p>"
            f"<p style='color:#8a8a8a;'>For example:</p><ul>{examples}</ul>"
        )

    @staticmethod
    def _question_html(question: str, turn: int = 0) -> str:
        """One question, anchored so the view can be scrolled to it."""
        return (
            f"<a name='turn{turn}'></a><p style='margin-top:10px;'><b>"
            + _html.escape(question)
            + "</b></p>"
        )

    def _math(self):
        """Return a math renderer sized to this panel, or ``None``.

        Sized to *this* column: a renderer built for the reading column draws
        a displayed equation wider than the panel, and it is clipped at the
        right edge with no scrollbar to reveal it.
        """
        if self._math_provider is None:
            return None
        try:
            width = self.transcript.viewport().width() or self.width()
            return self._math_provider(max(160, width - 16))
        except Exception:  # pragma: no cover - a missing renderer is not fatal
            logger.debug("no math renderer for the Ask panel", exc_info=True)
            return None

    def _answer_html(self, answer: dict) -> str:
        r"""One answer, followed by the pages it was actually taken from.

        The prose is rendered as Markdown rather than escaped, so a page the
        answer *mentions* is a link the reader can follow — an answer that
        names ``docs/concepts/accurate_fret.md`` and makes you go and find it
        has done half the job. Bare paths are linked too, because a model does
        not reliably write the link syntax even when told to. Mathematics goes
        through the browser's own renderer, so ``$\\kappa^2$`` is typeset
        rather than shown as its source.
        """
        text = linkify_pages(str(answer.get("text", "")))
        paragraphs = md_api.render_body(text, math=self._math()) or "".join(
            f"<p style='margin:6px 0;'>{_html.escape(block)}</p>"
            for block in text.split("\n\n")
            if block.strip()
        )
        pages = answer.get("pages") or []
        if pages:
            items = "".join(
                "<li><a href='doc:{document}#{section}'>{title}</a>"
                " <span style='color:#8a8a8a;'>{document}</span></li>".format(
                    document=_html.escape(str(page.get("document", ""))),
                    section=_html.escape(str(page.get("section", ""))),
                    title=_html.escape(str(page.get("title") or page.get("document", ""))),
                )
                for page in pages
            )
            sources = (
                "<p style='margin:8px 0 2px 0; color:#8a8a8a; font-size:9pt;'>"
                f"From {'this page' if len(pages) == 1 else 'these pages'}:</p>"
                f"<ul style='margin-top:0;'>{items}</ul>"
            )
        else:
            # No read means the model answered from itself, and the reader is
            # entitled to know that before trusting a menu path.
            sources = (
                "<p style='color:#a07000; font-size:9pt;'>No documentation page was "
                "opened for this answer — treat it as a suggestion and check it.</p>"
            )
        fabricated = answer.get("fabricated") or []
        if fabricated:
            # The path has already been struck from the text; saying so is what
            # stops the reader hunting for a page that was never there.
            sources += (
                "<p style='color:#b04040; font-size:9pt;'>It also named "
                + (
                    "a page that does not exist: "
                    if len(fabricated) == 1
                    else "pages that do not exist: "
                )
                + ", ".join(_html.escape(str(name)) for name in fabricated)
                + ". Do not trust the rest of this answer without checking it.</p>"
            )
        return paragraphs + sources

    @staticmethod
    def _error_html(answer: dict) -> str:
        reason = _html.escape(str(answer.get("error") or "no answer came back"))
        return "<p style='color:#b04040;'>Could not answer: " + reason + "</p>"

    # ── links ─────────────────────────────────────────────────────────

    def _on_anchor(self, url: Any) -> None:
        """Route a clicked link.

        Three shapes reach here: an example question (``ask:``), a source-list
        entry (``doc:``), and a link inside the answer's own prose, which is
        an ordinary Markdown link and therefore a bare ``docs/…md`` path. The
        last one is the point of rendering the answer as Markdown — a page the
        answer *mentions* has to be one click away, not something to go and
        look up.
        """
        target = url.toString() if hasattr(url, "toString") else str(url)
        if target.startswith("ask:"):
            self.ask(target[4:])
            return
        if target.startswith("doc:"):
            target = target[4:]
        elif target.startswith(("http://", "https://", "mailto:")):
            import webbrowser

            webbrowser.open(target)
            return
        document, _, section = target.partition("#")
        if document.startswith(("docs/", "okf/")):
            self.pageRequested.emit(document, section)
