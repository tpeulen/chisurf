"""Steering: a message sent while the agent works reaches it after the next tool call.

The user types while a request runs (busy-input mode ``steer``); the message must
land in the conversation as a user turn before the next model call -- not
interrupt the run, not be lost when the run ends first.
"""

from __future__ import annotations

import threading

from chisurf.core.agent import AgentSession
from test.agent.test_grilling import ScriptedLLM


class SteeredLLM(ScriptedLLM):
    """Runs a hook before answering turn *at* (the user typing mid-run)."""

    def __init__(self, turns, at, hook):
        super().__init__(turns)
        self.at, self.hook = at, hook

    def complete(self, messages, tools=None):
        if len(self.prompts) == self.at:
            self.hook()
        return super().complete(messages, tools)


def test_a_steering_message_joins_the_run_after_the_tool_call(context):
    holder = {}
    model = SteeredLLM(
        [
            {"calls": [{"id": "t1", "name": "list_files", "arguments": {"directory": "."}}]},
            {"text": "Listed, and I will also export them."},
        ],
        at=0,
        # Sent from another thread while the first model call is in flight.
        hook=lambda: threading.Thread(target=holder["agent"].steer, args=("also export them",))
        .start(),
    )
    agent = holder["agent"] = AgentSession(model, context=context)
    events = []
    context.event_callback = lambda event, payload: events.append(event)

    result = agent.ask("list the files")

    assert result.ok
    second = model.prompts[1]
    roles = [m["role"] for m in second]
    steer_at = next(
        i for i, m in enumerate(second) if "also export them" in str(m.get("content"))
    )
    assert second[steer_at]["role"] == "user"
    assert roles[steer_at - 1] == "tool", "after the tool result, before the next model call"
    assert "agent.steered" in events
    assert agent.take_steering() == []


def test_a_message_that_arrives_too_late_is_handed_back(context):
    holder = {}
    model = SteeredLLM(
        [{"text": "Done."}], at=0, hook=lambda: holder["agent"].steer("one more thing")
    )
    agent = holder["agent"] = AgentSession(model, context=context)
    assert agent.ask("hello").ok
    assert agent.take_steering() == ["one more thing"], "the host sends it as the next request"
    assert agent.take_steering() == []


def test_the_session_says_while_it_runs(context):
    seen = {}
    holder = {}
    model = SteeredLLM(
        [{"text": "ok"}], at=0, hook=lambda: seen.setdefault("running", holder["a"].running)
    )
    agent = holder["a"] = AgentSession(model, context=context)
    assert not agent.running
    agent.ask("hi")
    assert seen["running"] and not agent.running
    assert not agent.steer("   "), "an empty message is not queued"
