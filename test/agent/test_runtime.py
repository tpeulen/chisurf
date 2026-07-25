"""Runtime tests: the agent loop driven by a scripted model.

A :class:`ScriptedLLM` replaces the network call with a fixed sequence of
responses, so the loop's behaviour — multi-tool turns, error recovery,
budgets, cancellation, protocol fallback — is tested deterministically and
without an API key.
"""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import (
    AgentConfig,
    AgentContext,
    AgentSession,
    LLMClient,
    LLMError,
    LLMSettings,
    build_default_registry,
)
from chisurf.core.agent.llm import LLMResponse, ToolCall


class ScriptedLLM(LLMClient):
    """An :class:`LLMClient` that replays a fixed list of responses.

    Parameters
    ----------
    script : list
        Each entry is either a string (a final prose answer), a
        ``(tool_name, arguments)`` tuple, a list of such tuples (one turn
        requesting several tools), or an exception instance to raise.
    """

    def __init__(self, script, supports_tools: bool = True):
        super().__init__(
            LLMSettings(base_url="http://test", model="test-model", supports_tools=supports_tools)
        )
        self.script = list(script)
        self.calls: list = []

    def complete(self, messages, tools=None):
        """Return the next scripted response."""
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.script:
            return LLMResponse(text="(script exhausted)")
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, str):
            return LLMResponse(text=step, raw_message={"role": "assistant", "content": step})
        entries = step if isinstance(step, list) else [step]
        calls = [
            ToolCall(id=f"call_{index}", name=name, arguments=arguments)
            for index, (name, arguments) in enumerate(entries)
        ]
        return LLMResponse(
            text="",
            tool_calls=calls,
            raw_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in calls
                ],
            },
        )


@pytest.fixture()
def session(context):
    """Return a factory for agent sessions whose model is scripted."""

    def _build(script, supports_tools=True, config=None, ctx=None):
        return AgentSession(
            ScriptedLLM(script, supports_tools=supports_tools),
            context=ctx or context,
            registry=build_default_registry(),
            config=config or AgentConfig(),
        )

    return _build


TCSPC = "tcspc/EasyTau300"
MODEL = "Lifetime (new)"


# ── the headline workflow ─────────────────────────────────────────────


def test_full_load_fit_report_workflow(session):
    agent = session(
        [
            ("list_files", {"directory": TCSPC, "pattern": "*.dat"}),
            ("load_data", {"directory": TCSPC, "pattern": "*.dat"}),
            ("create_fit", {"model_name": MODEL}),
            ("run_fit", {}),
            "Fitted 4 decays; reduced chi2 between 1 and 30.",
        ]
    )
    result = agent.ask("fit every decay in the EasyTau300 folder")

    assert result.ok
    assert result.tool_names() == ["list_files", "load_data", "create_fit", "run_fit"]
    assert all(invocation.ok for invocation in result.invocations)
    assert len(agent.context.fits) == 4
    assert result.text.startswith("Fitted 4 decays")


def test_several_tool_calls_in_one_turn(session):
    agent = session(
        [
            [
                ("list_files", {"directory": TCSPC}),
                ("list_experiments", {"experiment": "TCSPC"}),
            ],
            "Both listings done.",
        ]
    )
    result = agent.ask("what data and models are available?")
    assert result.tool_names() == ["list_files", "list_experiments"]
    assert result.steps == 2


# ── error recovery ────────────────────────────────────────────────────


def test_a_failing_tool_is_reported_back_and_the_run_continues(session):
    agent = session(
        [
            ("load_data", {"paths": ["does_not_exist.dat"]}),
            ("load_data", {"directory": TCSPC, "pattern": "*.dat"}),
            "Recovered and loaded the folder.",
        ]
    )
    result = agent.ask("load the data")

    assert result.ok
    assert [invocation.ok for invocation in result.invocations] == [False, True]
    failed_result = json.loads(agent.messages[3]["content"])
    assert failed_result["ok"] is False
    assert "does not exist" in failed_result["error"]


def test_an_unknown_tool_name_lists_the_real_ones(session):
    agent = session([("fit_everything", {}), "Understood, using the real tools."])
    result = agent.ask("do it all")
    assert result.invocations[0].ok is False
    assert "load_data" in result.invocations[0].error


def test_unparsable_tool_arguments_are_reported_as_such(context):
    agent = AgentSession(ScriptedLLM([]), context=context)
    call = ToolCall(id="1", name="run_fit", arguments={}, raw_arguments="{not json")
    invocation = agent._execute(call)
    assert invocation.ok is False
    assert "not a JSON object" in invocation.error


def test_repeated_identical_failures_stop_the_run(session):
    agent = session([("load_data", {"paths": ["nope.dat"]})] * 6 + ["never reached"])
    result = agent.ask("load nope.dat")
    assert result.stop_reason == "repeated_failures"
    assert len(result.invocations) < 6
    assert "kept failing" in result.text


def test_a_model_error_is_surfaced_not_swallowed(session):
    agent = session([LLMError("HTTP 401: bad key")])
    result = agent.ask("hello")
    assert result.stop_reason == "error"
    assert "401" in result.error
    assert "language model" in result.text


# ── budgets and cancellation ──────────────────────────────────────────


def test_step_budget_stops_a_runaway_loop(session):
    agent = session([("list_fits", {})] * 20, config=AgentConfig(max_steps=3))
    result = agent.ask("keep going")
    assert result.stop_reason == "step_budget"
    assert result.steps == 3


def test_tool_call_budget_is_enforced(session):
    agent = session(
        [[("list_fits", {}), ("list_datasets", {}), ("describe_session", {})]],
        config=AgentConfig(max_tool_calls=2),
    )
    result = agent.ask("look around")
    assert result.stop_reason == "tool_budget"
    assert len(result.invocations) == 2


def test_cancel_stops_the_loop(session):
    agent = session([("list_fits", {})] * 5)

    original = agent._execute

    def cancel_after_first(call):
        """Run the tool, then cancel the session."""
        invocation = original(call)
        agent.cancel()
        return invocation

    agent._execute = cancel_after_first
    result = agent.ask("list them")
    assert result.stop_reason == "cancelled"
    assert len(result.invocations) == 1


# ── safety policy ─────────────────────────────────────────────────────


def test_dangerous_tools_are_hidden_below_their_safety_tier(session):
    agent = session(
        [("run_python", {"code": "print(1)"}), "done"], config=AgentConfig(max_safety="write")
    )
    result = agent.ask("run some python")
    assert result.invocations[0].ok is False
    assert "not permitted" in result.invocations[0].error
    exposed = {tool["function"]["name"] for tool in agent.llm.calls[0]["tools"]}
    assert "run_python" not in exposed


def test_a_declined_confirmation_blocks_the_call(clean_session, tmp_path):
    asked = []

    def deny(name, arguments):
        """Record and refuse every confirmation request."""
        asked.append(name)
        return False

    context = AgentContext(working_directory=str(tmp_path), confirm=deny)
    agent = AgentSession(
        ScriptedLLM([("run_python", {"code": "print(1)"}), "I did not run it."]),
        context=context,
    )
    result = agent.ask("run some python")
    assert asked == ["run_python"]
    assert result.invocations[0].ok is False
    assert "declined" in result.invocations[0].error


def test_confirmation_is_not_asked_for_ordinary_tools(clean_session, tmp_path):
    asked = []
    context = AgentContext(
        working_directory=str(tmp_path),
        confirm=lambda name, arguments: asked.append(name) or True,
    )
    agent = AgentSession(ScriptedLLM([("list_fits", {}), "none"]), context=context)
    agent.ask("list fits")
    assert asked == []


# ── conversation handling ─────────────────────────────────────────────


def test_the_system_prompt_carries_the_live_session_state(session, context):
    from chisurf.core.agent.tools import data as data_tools

    data_tools.load_data(context, directory=TCSPC, pattern="*.dat")
    agent = session(["nothing to do"], ctx=context)
    agent.ask("status?")
    system_prompt = agent.llm.calls[0]["messages"][0]["content"]
    assert "Datasets: 4" in system_prompt
    assert "215-268 D0.dat" in system_prompt


def test_tool_schemas_are_sent_to_the_model(session):
    agent = session(["hi"])
    agent.ask("hello")
    tools = agent.llm.calls[0]["tools"]
    names = {tool["function"]["name"] for tool in tools}
    assert {"load_data", "create_fit", "run_fit"} <= names
    load_data = next(t for t in tools if t["function"]["name"] == "load_data")
    assert "directory" in load_data["function"]["parameters"]["properties"]


def test_follow_up_questions_keep_the_conversation(session):
    agent = session(["first answer", "second answer"])
    agent.ask("one")
    result = agent.ask("two")
    assert result.text == "second answer"
    roles = [message["role"] for message in agent.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant"]


def test_reset_clears_the_conversation(session):
    agent = session(["a", "b"])
    agent.ask("one")
    agent.reset()
    agent.ask("two")
    assert [m["role"] for m in agent.messages] == ["system", "user", "assistant"]


def test_history_is_trimmed_without_orphaning_tool_results(session):
    agent = session([("list_fits", {})] * 8 + ["done"], config=AgentConfig(max_history_messages=6))
    agent.ask("look repeatedly")
    assert len(agent.messages) <= 10
    assert agent.messages[0]["role"] == "system"
    assert agent.messages[1]["role"] != "tool"


def test_events_are_emitted_for_the_ui(clean_session, tmp_path):
    events = []
    context = AgentContext(
        working_directory=str(tmp_path),
        event_callback=lambda name, payload: events.append(name),
    )
    agent = AgentSession(ScriptedLLM([("list_fits", {}), "done"]), context=context)
    agent.ask("list fits")
    assert events == [
        "agent.started",
        "tool.started",
        "tool.completed",
        "message.completed",
        "agent.completed",
    ]


# ── text-protocol fallback ────────────────────────────────────────────


def test_text_protocol_drives_the_same_tools(context):
    agent = AgentSession(
        ScriptedLLM(
            [
                f'{{"tool": "load_data", "arguments": {{"directory": "{TCSPC}", "pattern": "*.dat"}}}}',
                f'```json\n{{"tool": "create_fit", "arguments": {{"model_name": "{MODEL}"}}}}\n```',
                '{"answer": "Created the fits."}',
            ],
            supports_tools=False,
        ),
        context=context,
    )
    result = agent.ask("load and fit the folder")
    assert result.tool_names() == ["load_data", "create_fit"]
    assert result.text == "Created the fits."
    assert agent.llm.calls[0]["tools"] is None
    assert "## Tools" in agent.llm.calls[0]["messages"][0]["content"]


def test_text_protocol_treats_prose_as_the_answer(context):
    agent = AgentSession(
        ScriptedLLM(["Just a plain sentence."], supports_tools=False), context=context
    )
    result = agent.ask("hi")
    assert result.text == "Just a plain sentence."
