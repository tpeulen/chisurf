"""Tool focus: a small model is sent the tools its request needs, and can reach the rest."""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import (
    AgentConfig,
    AgentSession,
    LLMSettings,
    build_default_registry,
    tool_focus,
)
from chisurf.core.agent.llm import LLMResponse, ToolCall


class Recorder:
    """A model that records the tools it was offered and replays scripted turns."""

    def __init__(self, turns, focus=True):
        self.settings = LLMSettings(base_url="http://test", model="m", focus_tools=focus)
        self.turns = list(turns)
        self.offered: list[list[str]] = []

    def complete(self, messages, tools=None):
        """Record the offer, return the next turn."""
        self.offered.append([t["function"]["name"] for t in tools or []])
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            return LLMResponse(text=turn, raw_message={"role": "assistant", "content": turn})
        name, arguments = turn
        call = ToolCall(id=f"c{len(self.offered)}", name=name, arguments=arguments)
        raw = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }
        return LLMResponse(tool_calls=[call], raw_message=raw)


def session(context, llm):
    return AgentSession(llm, context=context, config=AgentConfig(max_steps=8))


def test_every_named_tool_exists():
    """The topic table drifts silently if a tool is renamed; this pins it."""
    known = set(build_default_registry().names()) | set(tool_focus.registry.names())
    known |= {"list_windows", "open_window", "show_fit", "open_in_code_editor"}
    named = set(tool_focus.CORE_TOOLS)
    for _words, tools in tool_focus.TOPICS:
        named.update(tools)
    assert named <= known, sorted(named - known)


def test_a_decay_fit_is_offered_a_fraction_of_the_catalogue(context):
    llm = Recorder(["done"])
    session(context, llm).ask("fit the decay in tcspc/EasyTau300")
    offered = llm.offered[0]
    assert {"load_data", "auto_fit_decay", "run_fit", "find_tools"} <= set(offered)
    assert "run_burst_analysis" not in offered
    assert len(offered) < 30
    full = build_default_registry().to_openai_tools()
    sent = [t for t in full if t["function"]["name"] in offered]
    assert len(json.dumps(sent)) < 0.6 * len(json.dumps(full))


def test_the_request_names_its_topic(context):
    llm = Recorder(["done"])
    session(context, llm).ask("run a burst analysis of the PIE measurement")
    assert {"detect_smfret", "run_burst_analysis", "select_species"} <= set(llm.offered[0])


def test_find_tools_enables_a_tool_from_the_next_step(context):
    llm = Recorder([("find_tools", {"query": "link parameters for a global fit"}), "done"])
    session(context, llm).ask("fit the decay")
    assert "link_parameters" not in llm.offered[0]
    assert "link_parameters" in llm.offered[1]


def test_the_offer_only_grows_so_the_prompt_cache_survives(context):
    llm = Recorder(["one", "two"])
    agent = session(context, llm)
    agent.ask("run a burst analysis")
    agent.ask("now fit the decay")
    assert set(llm.offered[0]) <= set(llm.offered[1])


def test_an_unoffered_known_tool_still_runs_and_joins(context):
    llm = Recorder([("list_skills", {}), "done"])
    result = session(context, llm).ask("fit the decay")
    assert "list_skills" not in llm.offered[0]
    assert result.invocations[0].ok
    assert "list_skills" in llm.offered[1]


def test_a_hosted_model_gets_the_whole_catalogue(context):
    llm = Recorder(["done"], focus=False)
    session(context, llm).ask("fit the decay")
    assert len(llm.offered[0]) == len(build_default_registry().names())
    assert "find_tools" not in llm.offered[0]


def test_the_local_provider_focuses(tmp_path, monkeypatch):
    from chisurf.core.settings import ai_settings

    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: tmp_path / "ai.json")
    assert LLMSettings.from_provider("local").focus_tools
    assert not LLMSettings.from_provider("mistral").focus_tools


@pytest.mark.parametrize(
    "question, tool",
    [
        ("what does the gamma factor correct for?", "search_documentation"),
        ("export the results as csv", "export_fit_results"),
        ("save the project", "save_project"),
        ("plot the fit", "plot_fit"),
        ("convert the file with the vendor command", "run_command"),
    ],
)
def test_routine_wordings_reach_their_tool(question, tool):
    assert tool in tool_focus.focus_for(question)
