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


class _AskWorker(QObject):
    """Runs one question on a worker thread."""

    finished = Signal(dict)

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
        self.finished.emit(dict(answer or {}))


class AskPanel(QWidget):
    """A question-and-answer transcript over ChiSurf's documentation.

    Parameters
    ----------
    client : HelpClient
        The plugin client the question is put through.
    parent : QWidget, optional
        Parent widget.

    Attributes
    ----------
    pageRequested : Signal
        Emitted with ``(document, section)`` when the reader clicks one of the
        cited pages. The browser navigates; the panel does not.
    """

    pageRequested = Signal(str, str)

    def __init__(self, client, parent: QWidget | None = None):
        super().__init__(parent)
        self._client = client
        self._thread: QThread | None = None
        self._worker: _AskWorker | None = None
        self._turns: list[str] = []
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

    def ask(self, question: str) -> None:
        """Put *question* to the documentation and show the answer.

        Parameters
        ----------
        question : str
            The question, in plain language.
        """
        if self.busy:
            return
        self.input.clear()
        self._turns.append(self._question_html(question))
        self._render()
        self._set_busy(True, "Reading the documentation…")

        self._thread = QThread(self)
        self._worker = _AskWorker(self._client, question)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_answer)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
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
        """Redraw the transcript and scroll to the bottom."""
        body = "\n".join(self._turns) if self._turns else self._empty_html()
        self.transcript.setHtml(
            "<body style='font-size:10pt;'>" + body + "</body>"
        )
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
    def _question_html(question: str) -> str:
        return (
            "<p style='margin-top:10px;'><b>"
            + _html.escape(question)
            + "</b></p>"
        )

    @staticmethod
    def _answer_html(answer: dict) -> str:
        """One answer, followed by the pages it was actually taken from."""
        text = _html.escape(str(answer.get("text", "")))
        paragraphs = "".join(
            f"<p style='margin:6px 0;'>{block}</p>"
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
        return paragraphs + sources

    @staticmethod
    def _error_html(answer: dict) -> str:
        reason = _html.escape(str(answer.get("error") or "no answer came back"))
        return (
            "<p style='color:#b04040;'>Could not answer: "
            + reason
            + "</p>"
        )

    # ── links ─────────────────────────────────────────────────────────

    def _on_anchor(self, url: Any) -> None:
        """Route a clicked link: an example question, or a cited page."""
        target = url.toString() if hasattr(url, "toString") else str(url)
        if target.startswith("ask:"):
            self.ask(target[4:])
            return
        if target.startswith("doc:"):
            rest = target[4:]
            document, _, section = rest.partition("#")
            self.pageRequested.emit(document, section)
