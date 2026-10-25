"""The tool that lets the model ask the user before it acts.

A workflow request is often underspecified in ways the model must not guess:
which file a pronoun refers to, how many components a fit should use, which
correction factors apply to the dye pair. Guessing silently turns the agent
into a confident wrong analysis; asking turns it into a consultation. The
runtime enforces the shape of this: the questions come back structured to the
caller (``AgentResult.clarifications``), the run stops until the user answers,
and one request gets **one** clarification round — a second ``ask_user`` in
the same thread is refused, because an assistant that keeps asking instead of
analysing is its own failure mode. The rule lives here so every host
(GUI panel, CLI, ACP) gets the same behaviour.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, ToolError, ToolRegistry

__all__ = ["ASK_USER", "render_questions", "registry"]

ASK_USER = "ask_user"

#: A request may carry at most this many questions; a questionnaire is not a
#: focused clarification.
MAX_QUESTIONS = 5

registry = ToolRegistry()


def _clean_questions(raw: Any) -> list[dict[str, Any]]:
    """Validate and normalise the *questions* payload of ``ask_user``.

    Parameters
    ----------
    raw : object
        What the model sent.

    Returns
    -------
    list of dict
        One ``{"id", "question", "options", "default"}`` per question, with
        everything optional normalised to its empty form.

    Raises
    ------
    ToolError
        When nothing usable was sent; the error goes back to the model, which
        can then fix the payload.
    """
    if isinstance(raw, dict):
        # ``{"questions": [...]} is the schema; a bare question object is
        # accepted as a one-question shorthand.
        raw = raw.get("questions", [raw] if "question" in raw else [])
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ToolError(
            "ask_user needs a non-empty 'questions' list — each entry an object "
            "with a 'question' (and optionally 'options' and 'default')"
        )
    if len(raw) > MAX_QUESTIONS:
        raise ToolError(
            f"{len(raw)} questions is a questionnaire, not a clarification: "
            f"ask at most {MAX_QUESTIONS}, the ones that change what you would do"
        )
    cleaned: list[dict[str, Any]] = []
    for position, entry in enumerate(raw, 1):
        if isinstance(entry, str):
            entry = {"question": entry}
        if not isinstance(entry, dict) or not str(entry.get("question", "")).strip():
            raise ToolError(
                f"question {position} has no text — every entry needs a 'question'"
            )
        options = entry.get("options") or []
        if not isinstance(options, (list, tuple)):
            raise ToolError(f"question {position}: 'options' must be a list of strings")
        cleaned.append(
            {
                "id": str(entry.get("id") or f"q{position}"),
                "question": str(entry["question"]).strip(),
                "options": [str(option) for option in options],
                "default": str(entry["default"]) if entry.get("default") is not None else "",
            }
        )
    return cleaned


@registry.add(
    name=ASK_USER,
    description=(
        "Ask the user focused clarifying questions before acting, when a request "
        "is ambiguous in a way that changes the analysis: which file is meant, "
        "which species gate, how many fit components, which correction factors. "
        "Each question carries concrete options (mark the one you would pick as "
        "'default'). Ask ONCE per request — the runtime refuses a second round; "
        "after the answers arrive, proceed and state the choices you used. Never "
        "call this for something the tools can find out themselves."
    ),
    parameters={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Short stable identifier, e.g. 'forster_radius'.",
                        },
                        "question": {
                            "type": "string",
                            "description": "The question, concrete enough to answer in one line.",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Concrete answers to pick from; include units and values "
                                "where they matter."
                            ),
                        },
                        "default": {
                            "type": "string",
                            "description": "The option you would use if the user does not mind.",
                        },
                    },
                    "required": ["question"],
                },
                "description": "1-5 focused questions.",
            },
        },
        "required": ["questions"],
    },
    safety=SAFETY_READ,
)
def ask_user(context: AgentContext, questions: Any = None, **_: Any) -> dict[str, Any]:
    """Hand structured questions back to the user; the runtime stops the run.

    Parameters
    ----------
    context : AgentContext
        Execution context (unused; the tool acts on nothing).
    questions : list of dict
        The questions, validated and normalised.

    Returns
    -------
    dict
        The cleaned questions, with a status telling the model what happens
        next: the run stops here and the user's next message carries the
        answers.
    """
    cleaned = _clean_questions(questions)
    return {
        "ok": True,
        "status": (
            "waiting for the user's answers — the run stops here; the user's "
            "next message answers these questions, then continue the task with "
            "the answers and state the choices you used"
        ),
        "questions": cleaned,
    }


def render_questions(questions: list[dict[str, Any]]) -> str:
    """Return the questions as the user-facing text of a stopped run.

    Parameters
    ----------
    questions : list of dict
        Normalised questions, as returned by :func:`ask_user`.

    Returns
    -------
    str
    """
    lines = ["Before I continue I need a few answers:"]
    for position, question in enumerate(questions, 1):
        lines.append(f"{position}. {question.get('question', '')}")
        options = question.get("options") or []
        if options:
            lines.append("   Options: " + " | ".join(str(option) for option in options))
        if question.get("default"):
            lines.append(f"   (my default: {question['default']})")
    return "\n".join(lines)
