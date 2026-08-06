"""Asking the documentation a question, and getting a cited answer back.

The help browser can already find a page if you know which page you want. A
question is not a page: *"why is my FRET efficiency above one"* is answered by
one paragraph of one concept page, and finding it means knowing that the page
exists, that it is called *Accurate FRET*, and that the paragraph is under a
heading about correction factors. Search does not close that gap — it matches
words, and the user's words are usually not the page's words.

So this module puts a reader between the question and the corpus. It is the
ChiSurf agent with everything taken away except three tools: browse the
documentation by kind and subject, search it, read one page or one section of
one. It cannot load data, run a fit, execute code or write a file, and that is
enforced by the registry it is given rather than by asking it nicely.

Two properties matter more than the answer's prose:

**It is grounded.** The agent is told, and the tools are shaped so, that a
claim about ChiSurf comes from a page. What was actually read is recorded from
the tool invocations — not from the model's own footnotes, which it can invent
— so :attr:`Answer.pages` is a fact about the run.

**It is transport-free.** Nothing here imports Qt. The GUI client calls it over
JSON-RPC, the CLI calls it in-process, and the tests call it directly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: The only tools the documentation assistant may use. Everything that changes
#: the session, the disk or the machine is absent — a reader must not be able
#: to start a fit because a page mentioned one.
DOC_TOOLS: tuple[str, ...] = (
    "browse_documentation",
    "search_documentation",
    "read_documentation",
)

#: Model turns one question may take. Browsing, reading one page and answering
#: is three; the ceiling leaves room to follow a cross-reference and no more.
MAX_STEPS = 8

#: Skill carrying the procedure — browse by kind, read the page, cite it.
SKILL = "answer-from-docs"

#: What to say when the model answered without opening anything. Observed
#: against a real provider: asked whether ChiSurf can simulate a photon stream,
#: it answered from the *search excerpts* and invented an API call to go with
#: it — the pages that would have answered it properly were right there and it
#: never opened one. Prompting alone does not fix this, so the run is sent back
#: once with the omission named.
READ_FIRST = (
    "You have not opened a documentation page, so that answer is not grounded "
    "in anything. Open the most relevant page with read_documentation and "
    "answer from what it says. If, having read it, the documentation genuinely "
    "does not cover the question, say so plainly and name the nearest page you "
    "did read."
)

#: A path to a documentation page as a model writes it in prose.
_CITED_PATH = re.compile(r"\b((?:docs|okf)/[\w./-]+\.md)\b")

INSTRUCTIONS = """\
You are ChiSurf's documentation assistant. The person asking is using the
program, not writing it.

You answer **only** from ChiSurf's own documentation, which you reach with
`browse_documentation`, `search_documentation` and `read_documentation`. You
have no other tools: you cannot load data, run a fit or execute code, so do
not offer to. If the user wants something done rather than explained, say
which tool in ChiSurf does it and point at the guide.

Rules:

* Read before you answer. An answer with no `read_documentation` call behind
  it is a guess, however confident it sounds.
* **Write every page you mention as a Markdown link**, so the reader can jump
  straight to it: `[Accurate FRET](docs/concepts/accurate_fret.md)`. Link to a
  heading with `#`, spelled exactly as the heading is:
  `[the four factors](docs/concepts/accurate_fret.md#The four factors)`. Link
  the page at the point in the sentence where you use it, not only at the end
  — "the γ factor is defined in [Accurate FRET](…)" is worth more than a
  footnote. Use only paths you actually opened; `read_documentation` reports
  the page's headings, so a section link is checkable before you write it.
* End with the page you used, as a link.
* If the documentation does not cover it, say so and link the nearest page.
  Never invent a menu path, a control, a setting name or a file format, and
  never write a page path you have not opened.
* **Write mathematics as LaTeX**, inline `$\\kappa^2$` or displayed
  `$$\\Delta G = E(D^+/D) - E(A/A^-) - \\Delta G_{00}$$`. It is typeset for
  the reader. Plain text like "DG = E(D+/D) - ..." is not.
* Markdown is rendered: use **bold**, `code`, lists and tables where they help.
* **Never tell the user a term does not exist** because a search missed it.
  Search the words they typed; if that finds nothing the tool tells you the
  near spelling the documentation uses — search again with it. Substituting a
  different subject for the one they asked about is the worst possible answer,
  because it reads as a correction.
* Be brief. Two or three paragraphs, and a list of steps if the question was
  "how do I".
"""


@dataclass
class Answer:
    """What the documentation assistant produced for one question.

    Attributes
    ----------
    text : str
        The answer.
    pages : list of dict
        The pages actually read, each ``{"document", "title", "type"}``. Taken
        from the tool calls, so it cannot include a page the model imagined.
    searched : list of str
        The queries it tried, which is what to show when it found nothing.
    fabricated : list of str
        Page paths the answer *named* that do not exist. Empty is the normal
        case; a non-empty list means the model wrote itself a citation, and the
        paths have been struck from :attr:`text` before it reaches anybody.
    steps : int
        Model turns used.
    ok : bool
        Whether the run produced an answer rather than hitting a budget.
    error : str
        Set when the run failed — no provider configured, no key, a transport
        error. The GUI shows this instead of an answer.
    """

    text: str = ""
    pages: list[dict[str, Any]] = field(default_factory=list)
    searched: list[str] = field(default_factory=list)
    fabricated: list[str] = field(default_factory=list)
    steps: int = 0
    ok: bool = False
    error: str = ""

    @property
    def grounded(self) -> bool:
        """Whether the answer rests on a page that was actually opened."""
        return bool(self.pages)

    def to_dict(self) -> dict[str, Any]:
        """Return the answer as a JSON-RPC-safe mapping."""
        return {
            "text": self.text,
            "pages": self.pages,
            "searched": self.searched,
            "fabricated": self.fabricated,
            "grounded": self.grounded,
            "steps": self.steps,
            "ok": self.ok,
            "error": self.error,
        }


def is_available() -> tuple[bool, str]:
    """Return whether a language model is configured, and why not if it is not.

    Returns
    -------
    tuple
        ``(available, reason)``. The reason is empty when available and is a
        sentence to show the user otherwise.
    """
    try:
        from chisurf.core.agent.llm import LLMSettings

        settings = LLMSettings.from_provider()
    except Exception as exc:  # pragma: no cover - depends on user settings
        return False, f"the AI settings could not be read ({exc})"
    if not getattr(settings, "base_url", ""):
        return False, "no AI provider is configured (Settings → AI)"
    if not getattr(settings, "api_key", "") and "localhost" not in settings.base_url:
        return False, (
            f"no API key for {settings.base_url}. Set one in Settings → AI, or "
            f"use a local provider, which needs none."
        )
    return True, ""


def build_registry():
    """Return a registry holding only the documentation tools.

    Returns
    -------
    ToolRegistry
        A fresh registry; the caller may not reach anything else through it.
    """
    from chisurf.core.agent.spec import ToolRegistry
    from chisurf.core.agent.tools import documentation

    registry = ToolRegistry()
    for name in DOC_TOOLS:
        spec = documentation.registry.tools.get(name)
        if spec is not None:
            registry.register(spec)
    return registry


def build_session(model: str = "", provider: str = "", **overrides: Any):
    """Create the restricted session the documentation assistant runs in.

    Parameters
    ----------
    model : str
        Model identifier override; the configured default when empty.
    provider : str
        Provider key override.
    **overrides
        Further LLM settings overrides.

    Returns
    -------
    AgentSession
    """
    from chisurf.core.agent.llm import LLMClient, LLMSettings
    from chisurf.core.agent.runtime import AgentConfig, AgentSession
    from chisurf.core.agent.skills import SkillLibrary
    from chisurf.core.agent.spec import SAFETY_READ

    settings = LLMSettings.from_provider(provider or None, model=model or None, **overrides)
    config = AgentConfig(
        max_steps=MAX_STEPS,
        max_tool_calls=MAX_STEPS * 2,
        max_safety=SAFETY_READ,
        # The procedure is the point of this session, so it is loaded up front
        # rather than left to a trigger word in the question.
        auto_load_skills=False,
    )
    library = SkillLibrary.discover()
    skill = library.get(SKILL)
    instructions = INSTRUCTIONS
    if skill is not None:
        instructions = f"{INSTRUCTIONS}\n{skill.rendered()}"
    return AgentSession(
        LLMClient(settings),
        registry=build_registry(),
        config=config,
        extra_instructions=instructions,
        skills=library,
    )


def _pages_read(result) -> list[dict[str, Any]]:
    """Return the pages a run actually opened, in the order it opened them."""
    pages: list[dict[str, Any]] = []
    seen: set[str] = set()
    for invocation in result.invocations:
        if invocation.name != "read_documentation" or not invocation.ok:
            continue
        payload = invocation.result or {}
        document = str(payload.get("document", ""))
        if not document or document in seen:
            continue
        seen.add(document)
        pages.append(
            {
                "document": document,
                "title": str(payload.get("title", "")),
                "type": str(payload.get("type", "")),
                "section": str(payload.get("section", "")),
            }
        )
    return pages


def _dedup(pages) -> list[dict[str, Any]]:
    """Return the pages in order, one entry per document."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for page in pages:
        document = page.get("document", "")
        if document and document not in seen:
            seen.add(document)
            unique.append(page)
    return unique


def verify_citations(text: str) -> tuple[str, list[str]]:
    """Strike page paths the answer names that do not exist.

    A model that has not opened anything will still write itself a source line,
    and it will look exactly like a real one. Observed against a real provider:
    an answer closed with "— *Python scripting in ChiSurf*
    (`docs/guides/10_python_scripting.md`)" for a page that has never existed.
    That is worse than an unsourced answer, because the citation is what a
    reader checks the answer *by*.

    Every path is therefore resolved against the documentation index. The check
    is cheap, it is decisive — a page either exists or it does not — and it
    cannot be talked out of by a confident tone.

    Parameters
    ----------
    text : str
        The answer as the model wrote it.

    Returns
    -------
    tuple
        ``(text, fabricated)``. The text has each unresolvable path replaced by
        a marker; *fabricated* lists them.
    """
    from chisurf.core.agent import doc_index

    fabricated: list[str] = []
    for path in dict.fromkeys(_CITED_PATH.findall(text or "")):
        if doc_index.resolve(path) is None:
            fabricated.append(path)
    for path in fabricated:
        text = text.replace(path, "[no such page]")
    return text, fabricated


def _queries(result) -> list[str]:
    """Return the search queries a run tried."""
    return [
        str(invocation.arguments.get("query", ""))
        for invocation in result.invocations
        if invocation.name == "search_documentation" and invocation.arguments.get("query")
    ]


def ask(question: str, *, model: str = "", provider: str = "", session=None) -> Answer:
    """Answer a question from ChiSurf's documentation.

    Parameters
    ----------
    question : str
        The user's question, in plain language.
    model : str
        Model identifier override.
    provider : str
        Provider key override.
    session : AgentSession, optional
        Reuse an existing session, which is what keeps a conversation's
        follow-up questions in context. One is built when omitted.

    Returns
    -------
    Answer
        The answer, the pages it was taken from, and whether it succeeded.

    Examples
    --------
    >>> answer = ask("what does the gamma factor correct for?")  # doctest: +SKIP
    >>> answer.pages[0]["document"]  # doctest: +SKIP
    'docs/concepts/accurate_fret.md'
    """
    text = str(question or "").strip()
    if not text:
        return Answer(error="ask a question")

    available, reason = is_available()
    if not available and session is None:
        return Answer(error=reason)

    try:
        session = session or build_session(model=model, provider=provider)
        result = session.ask(text)
        runs = [result]
        # One push, not a loop: a model that will not open a page after being
        # told to is not going to on the third ask, and the user is waiting.
        if result.ok and not _pages_read(result):
            second = session.ask(READ_FIRST)
            runs.append(second)
            if _pages_read(second) or second.ok:
                result = second
        # Both turns are one answer as far as the caller is concerned, so what
        # was read and searched accumulates over them; only the *text* comes
        # from the turn that produced it.
        pages = _dedup(page for run in runs for page in _pages_read(run))
        searched = list(dict.fromkeys(query for run in runs for query in _queries(run)))
        steps = sum(run.steps for run in runs)
    except Exception as exc:
        logger.exception("the documentation assistant failed")
        return Answer(error=str(exc))

    answer_text, fabricated = verify_citations(result.text)
    if fabricated:
        logger.warning("the assistant cited pages that do not exist: %s", fabricated)

    return Answer(
        text=answer_text,
        pages=pages,
        searched=searched,
        fabricated=fabricated,
        steps=steps,
        ok=result.ok,
        error=result.error or ("" if result.ok else f"stopped: {result.stop_reason}"),
    )
