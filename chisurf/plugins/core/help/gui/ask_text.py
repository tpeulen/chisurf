"""What the *Ask Docs* pane says: the empty-state text and the text of an answer.

Toolkit-free, so the emtk pane draws it and a test reads it. The behaviour is the one the
retired Qt ``AskPanel`` had, and each rule has been got wrong before:

* the empty pane says what it is for, and that the assistant only *reads* documentation;
* an answer lists the pages it was actually taken from, as links that open them;
* a page path the model wrote in prose (not as a link) becomes a link when the page exists;
* an answer for which no page was opened says so, because it came from the model's memory;
* a page the model named but that does not exist is called out;
* a failure reaches the reader as words, with its reason.
"""

from __future__ import annotations

import re
from typing import Any

#: The empty pane's explanation, one paragraph per entry (drawn above the example questions).
EMPTY_STATE: tuple[str, ...] = (
    "Ask about anything ChiSurf's documentation covers: what a method means, how to carry out "
    "an analysis, what a setting does. The answer names the pages it came from, and clicking "
    "one opens it.",
    "The assistant only reads documentation. It cannot load data or run a fit.",
    "For example, what does the gamma correction factor do?",
)

#: Said under an answer for which no documentation page was opened.
NO_PAGE_READ = (
    "No documentation page was opened for this answer: treat it as a suggestion and check it."
)

#: A documentation path as a model writes it in prose, when it has not used the link syntax.
#: Only paths that resolve are linked -- a fabricated one has already been struck by
#: ``ask.verify_citations`` before it gets here.
_BARE_PATH = re.compile(
    r"(?<!\()(?<!/)\b((?:docs|okf)/[\w./-]+\.md)(?:#([\w -]+))?\b(?!\))"
)


def linkify_pages(text: str) -> str:
    """Turn documentation paths in *text* into Markdown links.

    Parameters
    ----------
    text : str
        The answer, as the model wrote it.

    Returns
    -------
    str
        The same text with every resolvable bare page path replaced by a link carrying the
        page's own title. Paths already inside a Markdown link are left alone.
    """
    from chisurf.core.agent.doc_index import DocIndex

    try:
        index = DocIndex.load()
    except Exception:  # pragma: no cover - the index is a cache, not a hard dependency
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


def _field(answer: Any, name: str, default: Any = None) -> Any:
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def compose_answer(answer: Any) -> tuple[str, str]:
    """The transcript entry for one answer: ``(role, markdown)``.

    Parameters
    ----------
    answer : help.api.ask.Answer or dict
        ``ok``, ``text``, ``pages`` (each ``document``, ``title``, ``section``), ``fabricated``
        and ``error``.

    Returns
    -------
    tuple of str
        ``("assistant", text)`` for an answer, ``("error", text)`` for a failure.
    """
    if not _field(answer, "ok", False):
        reason = str(_field(answer, "error", "") or "no answer came back")
        return "error", f"Could not answer: {reason}"
    text = linkify_pages(str(_field(answer, "text", "") or ""))
    pages = list(_field(answer, "pages", None) or [])
    if pages:
        lines = [f"**From {'this page' if len(pages) == 1 else 'these pages'}:**"]
        for page in pages:
            document = str(page.get("document", ""))
            section = str(page.get("section", "") or "")
            title = str(page.get("title") or document or "Doc")
            target = f"{document}#{section}" if section else document
            lines.append(f"- [{title}]({target}) `{document}`")
        text += "\n\n" + "\n".join(lines)
    else:
        text += "\n\n*" + NO_PAGE_READ + "*"
    fabricated = [str(name) for name in (_field(answer, "fabricated", None) or [])]
    if fabricated:
        what = "a page that does not exist: " if len(fabricated) == 1 else "pages that do not exist: "
        text += (
            "\n\n**It also named "
            + what
            + ", ".join(fabricated)
            + ". Do not trust the rest of this answer without checking it.**"
        )
    return "assistant", text
