"""Grilling: the agent interviews the user before an analysis, then acts.

An analysis request must stop the agent and come back as structured
questions; the user's answers must resume the plan in the same conversation;
grilling (the default) allows up to three rounds and then refuses, because an
assistant that keeps asking instead of analysing is its own failure mode; with
grilling off one round is all there is. The runtime owns all of it — the
tests drive it with a scripted model, exactly as a live one would behave.
"""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import AgentConfig, AgentSession, LLMClient, LLMSettings
from chisurf.core.agent.llm import LLMResponse, ToolCall
from chisurf.core.agent.prompt import SYSTEM_PROMPT, system_prompt
from chisurf.core.agent.runtime import GRILL_SKILL, is_informational, wants_grilling
from chisurf.core.agent.tools.clarify import ASK_USER, render_questions


class ScriptedLLM(LLMClient):
    """Replays scripted turns, recording what the runtime asked of it."""

    def __init__(self, turns):
        super().__init__(LLMSettings(base_url="http://test", model="m"))
        self.turns = list(turns)
        self.prompts: list[list[dict]] = []

    def complete(self, messages, tools=None):
        self.prompts.append([dict(m) for m in messages])
        turn = self.turns.pop(0)
        calls = [
            ToolCall(id=entry["id"], name=entry["name"], arguments=entry["arguments"])
            for entry in turn.get("calls", [])
        ]
        return LLMResponse(
            text=turn.get("text", ""),
            tool_calls=calls,
            raw_message=self._raw(turn, calls),
        )

    @staticmethod
    def _raw(turn, calls) -> dict:
        """The provider-shaped assistant message for *turn*."""
        message = {"role": "assistant", "content": turn.get("text", "") or None}
        if calls:
            message["content"] = None
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in calls
            ]
        return message


def _ask_user_call(call_id="q1", questions=None):
    """A scripted ``ask_user`` call with the owner-example's ambiguities."""
    return {
        "id": call_id,
        "name": ASK_USER,
        "arguments": {
            "questions": questions
            or [
                {
                    "id": "forster_radius",
                    "question": "Which Förster radius R0 applies to the dye pair?",
                    "options": ["52 A (ATTO 647N/Dy647)", "56 A (Alexa 647)"],
                    "default": "52 A",
                },
                {
                    "id": "n_gaussians",
                    "question": "How many Gaussian components should the distance distribution have?",
                    "options": ["1", "2"],
                    "default": "1",
                },
            ]
        },
    }


def test_an_ambiguous_request_stops_with_structured_questions(context):
    """The grilling round: no tool ran besides the questions; the run waits."""
    model = ScriptedLLM(
        [
            {"calls": [_ask_user_call()]},
        ]
    )
    agent = AgentSession(model, context=context)

    result = agent.ask("do a burstwise analysis of the data located in xy")

    assert result.stop_reason == "needs_input"
    assert not result.ok, "a clarification is not a finished answer"
    assert [q["id"] for q in result.clarifications] == ["forster_radius", "n_gaussians"]
    assert result.clarifications[0]["options"], "questions carry concrete options"
    assert result.clarifications[0]["default"] == "52 A"
    assert result.tool_names() == [ASK_USER], "nothing acted before the answers"
    # The user sees the questions as the run's text.
    assert "Förster radius" in result.text
    # The conversation stays valid: the questions are answered by a tool
    # message, so the provider accepts the resumed thread.
    tool_messages = [m for m in agent.messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0]["content"])
    assert payload["ok"] is True
    assert payload["status"].startswith("waiting for the user's answers")


def test_the_answers_resume_the_plan(context):
    """The user's answer continues the same conversation; the plan runs."""
    model = ScriptedLLM(
        [
            {"calls": [_ask_user_call()]},
            {"calls": [{"id": "t1", "name": "list_files", "arguments": {"directory": "xy"}}]},
            {"text": "Analysis complete: 38 bursts, R mean 43.4 A."},
        ]
    )
    agent = AgentSession(model, context=context)
    first = agent.ask("do a burstwise analysis of the data located in xy")
    assert first.stop_reason == "needs_input"

    second = agent.ask("R0 = 52 A, one Gaussian component.")

    assert second.ok, second.text
    assert second.stop_reason == "answer"
    assert "list_files" in second.tool_names()
    assert "38 bursts" in second.text
    # The resumed request saw the questions and their tool result, then the
    # answers: the thread is one conversation in the right order.
    resumed_prompt = model.prompts[-1]
    kinds = [m.get("role") for m in resumed_prompt]
    assert "tool" in kinds
    ask_user_result = next(i for i, m in enumerate(resumed_prompt) if m.get("role") == "tool")
    answers = next(
        i
        for i, m in enumerate(resumed_prompt)
        if m.get("role") == "user" and "R0 = 52 A" in str(m.get("content"))
    )
    assert answers == ask_user_result + 1, "the answers directly follow the questions"
    # And the whole thread is one conversation: the original request is still in it.
    assert any(
        "burstwise analysis" in str(m.get("content")) for m in resumed_prompt if m["role"] == "user"
    )


def test_without_grilling_a_second_round_is_refused(context):
    """Grilling off restores one round per request: after the answers, the model must act."""
    model = ScriptedLLM(
        [
            {"calls": [_ask_user_call()]},
            # The model tries to grill again instead of acting.
            {"calls": [_ask_user_call(call_id="q2")]},
            {"text": "Done with the stated assumptions."},
        ]
    )
    agent = AgentSession(model, context=context, config=AgentConfig(grill=False))
    first = agent.ask("do a burstwise analysis of the data located in xy")
    assert first.stop_reason == "needs_input"

    second = agent.ask("R0 = 52 A, one Gaussian.")
    assert second.ok
    refused = [i for i in second.invocations if i.name == ASK_USER]
    assert len(refused) == 1
    assert not refused[0].ok
    assert "already asked" in refused[0].error
    assert second.text == "Done with the stated assumptions."
    # A closed thread frees the round for the next request.
    assert not agent._clarification_pending


def test_grilling_keeps_asking_until_the_decisions_are_settled(context):
    """With grilling on, a follow-up round on what an answer opened up is allowed."""
    model = ScriptedLLM(
        [
            {"calls": [_ask_user_call()]},
            {"calls": [_ask_user_call("q2", [{"question": "Which gate for the FRET species?"}])]},
            {"calls": [{"id": "t1", "name": "list_files", "arguments": {"directory": "xy"}}]},
            {"text": "Analysis complete with R0 52 A, one Gaussian, gate S 0.3-0.7."},
        ]
    )
    agent = AgentSession(model, context=context)
    assert agent.config.grill and agent.config.clarification_rounds == 3
    assert agent.ask("do a burstwise analysis of the data located in xy").stop_reason == (
        "needs_input"
    )
    second = agent.ask("R0 = 52 A, one Gaussian.")
    assert second.stop_reason == "needs_input", "the second round is part of the interview"
    assert second.clarifications[0]["question"] == "Which gate for the FRET species?"
    third = agent.ask("S between 0.3 and 0.7.")
    assert third.ok, third.text
    assert "list_files" in third.tool_names()
    assert not agent._clarification_pending, "the answer closed the thread"


def test_grilling_is_capped_at_three_rounds(context):
    """The fourth ask_user of one request is refused; the model must act."""
    turns = [{"calls": [_ask_user_call(f"q{i}")]} for i in range(1, 4)]
    turns += [{"calls": [_ask_user_call("q4")]}, {"text": "Done with the stated choices."}]
    agent = AgentSession(ScriptedLLM(turns), context=context)
    for answer in ("analyse the bursts in xy", "52 A", "1"):
        assert agent.ask(answer).stop_reason == "needs_input"
    last = agent.ask("the default")
    assert last.ok
    refused = [i for i in last.invocations if i.name == ASK_USER]
    assert len(refused) == 1 and not refused[0].ok
    assert "3 of 3 round(s)" in refused[0].error


def test_the_interview_procedure_is_loaded_for_an_analysis_only(context):
    """The grill skill leads an analysis request; a question is answered directly."""
    agent = AgentSession(ScriptedLLM([{"text": "Two datasets."}]), context=context)
    agent.ask("what is loaded?")
    assert GRILL_SKILL not in agent.active_skills
    agent.reset()
    agent = AgentSession(ScriptedLLM([{"calls": [_ask_user_call()]}]), context=context)
    agent.ask("do a burstwise analysis of the data located in xy")
    assert agent.active_skills[0] == GRILL_SKILL, "the interview leads"
    assert "Settle the decisions before the analysis" in agent.messages[0]["content"]
    agent.reset()
    off = AgentSession(
        ScriptedLLM([{"text": "ok"}]), context=context, config=AgentConfig(grill=False)
    )
    off.ask("do a burstwise analysis of the data located in xy")
    assert GRILL_SKILL not in off.active_skills
    assert GRILL_SKILL not in off.messages[0]["content"], "not even offered in the catalogue"
    assert "ONE clarification round" in off.messages[0]["content"]


@pytest.mark.parametrize(
    ("request_text", "grill"),
    [
        ("what is loaded?", False),
        ("explain the gamma factor", False),
        ("how do I fit a decay?", False),
        ("which models exist for FCS?", False),
        ("do a burstwise analysis of the data located in xy", True),
        ("fit these decays with the IRF", True),
        ("write a script that processes multiple folders with burst analysis", True),
        ("open the FCS tool", False),
    ],
)
def test_which_requests_are_grilled(request_text, grill):
    assert wants_grilling(request_text) is grill
    if not grill and request_text.endswith("?"):
        assert is_informational(request_text)


def test_a_new_request_gets_its_own_round(context):
    """The limit is per request thread, not per session."""
    model = ScriptedLLM(
        [
            {"calls": [_ask_user_call()]},
            {"text": "Done."},
            {"calls": [_ask_user_call(call_id="q3", questions=[{"question": "Which folder?"}])]},
        ]
    )
    agent = AgentSession(model, context=context)
    assert agent.ask("first request").stop_reason == "needs_input"
    assert agent.ask("the answers").ok
    second = agent.ask("another request, different data")
    assert second.stop_reason == "needs_input"
    assert second.clarifications[0]["question"] == "Which folder?"


def test_reset_clears_an_open_round(context):
    model = ScriptedLLM([{"calls": [_ask_user_call()]}])
    agent = AgentSession(model, context=context)
    agent.ask("ambiguous request")
    assert agent._clarification_pending
    agent.reset()
    assert not agent._clarification_pending


def test_a_malformed_payload_is_an_error_the_model_can_fix(context):
    """Bad questions go back as a tool error, not as a stopped run."""
    model = ScriptedLLM(
        [
            {"calls": [{"id": "bad", "name": ASK_USER, "arguments": {"questions": []}}]},
            {"calls": [_ask_user_call()]},
        ]
    )
    agent = AgentSession(model, context=context)
    result = agent.ask("ambiguous request")
    assert result.stop_reason == "needs_input"
    first, second = [i for i in result.invocations if i.name == ASK_USER]
    assert not first.ok
    assert "non-empty" in first.error
    assert second.ok


@pytest.mark.parametrize(
    "arguments",
    [
        {"questions": [{"question": ""}]},
        {"questions": [{"question": "ok"}, {"no_question": True}]},
        {"questions": [{"question": "q", "options": "yes"}]},
    ],
)
def test_question_validation_rejects_unusable_payloads(arguments):
    from chisurf.core.agent.spec import ToolError
    from chisurf.core.agent.tools.clarify import _clean_questions

    with pytest.raises(ToolError):
        _clean_questions(arguments)


def test_questions_are_capped_so_a_questionnaire_stays_a_clarification():
    from chisurf.core.agent.spec import ToolError
    from chisurf.core.agent.tools.clarify import MAX_QUESTIONS, _clean_questions

    with pytest.raises(ToolError) as excinfo:
        _clean_questions([{"question": f"q{i}"} for i in range(MAX_QUESTIONS + 1)])
    assert "questionnaire" in str(excinfo.value)


def test_render_addresses_the_user():
    text = render_questions(
        [
            {"question": "Which R0?", "options": ["52 A", "56 A"], "default": "52 A"},
            {"question": "One or two Gaussians?"},
        ]
    )
    assert text.startswith("Before I continue")
    assert "1. Which R0?" in text
    assert "52 A | 56 A" in text
    assert "my default: 52 A" in text
    assert "2. One or two Gaussians?" in text


def test_the_tool_is_in_the_default_registry():
    from chisurf.core.agent import build_default_registry

    registry = build_default_registry()
    spec = registry.get(ASK_USER)
    assert spec is not None
    assert "ask" in spec.description.lower()


def test_the_system_prompt_carries_the_grilling_rule():
    lowered = SYSTEM_PROMPT.lower()
    assert "ask_user" in lowered
    assert "grill before you analyse" in lowered
    assert "at most three rounds" in lowered
    assert "förster radius" in lowered
    assert "what is loaded?" in lowered, "the never-grill examples are in the rule"
    one_round = system_prompt(grill=False).lower()
    assert "one clarification round" in one_round
    assert "three rounds" not in one_round
