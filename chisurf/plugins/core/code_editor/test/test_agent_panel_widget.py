"""The editor's AI assistant (emtk ``ChatModel`` / ``ChatGui``) wired to the ChiSurf agent.

Ported from the retired Qt ``AgentPanelWidget`` tests: the modes and their tool tiers, the
greeting, the transcript of a tool run, the provider status, sessions, example prompts.
"""

from __future__ import annotations

import json

import pytest
from emtk.testing import Driver

from chisurf.core.agent import SAFETY_DANGEROUS, SAFETY_WRITE
from chisurf.plugins.core.code_editor.agent_modes import AgentMode, greeting_for, tool_highlight
from chisurf.plugins.core.code_editor.gui.chat_app import MODES, ChatApp, ChatModel


@pytest.fixture
def chat():
    model = ChatModel()
    yield model
    model.close()


def _settle(model):
    model.process_events()
    return model.transcript_text()


class TestAssistant:
    """The assistant exposes the agent's modes and renders its events."""

    def test_modes_map_to_safety_tiers(self):
        """Each mode grants exactly the tool tier its label promises."""
        assert AgentMode.CHISURF_TOOLS.safety == SAFETY_WRITE
        assert AgentMode.FULL_CONTROL.safety == SAFETY_DANGEROUS

    def test_the_assistant_offers_the_three_modes(self):
        """The mode selector lists chat, tools and full control, in that order."""
        assert MODES == [
            AgentMode.CHAT_ONLY.value,
            AgentMode.CHISURF_TOOLS.value,
            AgentMode.FULL_CONTROL.value,
        ]
        app = ChatApp()
        try:
            driver = Driver(app, (500, 700))
            driver.frame(2)
            driver.click("ChiSurf tools")
            drawn = [t[5] for t in driver.frame(2).texts]
            assert "Chat only" in drawn and "Full control" in drawn
        finally:
            app.close()

    def test_context_grants_code_execution_only_in_full_control(self, chat):
        """Code execution and confirmation are tied to full-control mode."""
        tools_context = chat.build_agent_context(AgentMode.CHISURF_TOOLS)
        assert tools_context.allow_code_execution is False
        assert tools_context.confirm is None
        full_context = chat.build_agent_context(AgentMode.FULL_CONTROL)
        assert full_context.allow_code_execution is True
        assert full_context.confirm is not None

    def test_provider_status_is_reported(self, chat):
        """The status dot always carries an explanation in its tooltip."""
        for provider in ("acp", "openai", "local"):
            chat.provider = provider
            ready, why = chat.provider_status()
            assert isinstance(ready, bool) and why

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            ({"n_loaded": 4}, "4 dataset(s)"),
            ({"n_created": 2}, "2 fit(s)"),
            ({"results": [{"chi2r": 1.2}, {"chi2r": 3.4}]}, "chi2r 1.2, 3.4"),
            ({"path": "/tmp/out/results.csv"}, "results.csv"),
            ({"n_components": 3}, "3 component(s)"),
            ({"irf": {"name": "sample irf.dat"}}, "IRF: sample irf.dat"),
            ({"assessment": {"chi2r": 1.03, "quality": "good"}}, "chi2r 1.03 (good)"),
            ({"ok": True}, ""),
        ],
    )
    def test_tool_results_are_summarised_for_the_transcript(self, result, expected):
        """Only the numbers a user watches for are echoed into the transcript."""
        assert expected in tool_highlight({"result": result})

    def test_a_loaded_skill_is_announced(self, chat):
        """The user should see which procedure the assistant is following."""
        chat._on_runtime_event("skill.loaded", {"skill": "fit-decay", "trigger": "auto"})
        transcript = _settle(chat)
        assert "fit-decay" in transcript and "matched" in transcript

    def test_runtime_events_reach_the_transcript(self, chat):
        """Tool and completion events are rendered without raising."""
        chat._on_runtime_event("agent.started", {"question": "fit my data"})
        chat.history.add_message("assistant", "")  # the turn's message the tool calls attach to
        chat._on_runtime_event(
            "tool.started", {"tool": "load_data", "arguments": {"directory": "d"}}
        )
        chat._on_runtime_event(
            "tool.completed",
            {"tool": "load_data", "ok": True, "elapsed_ms": 5, "result": {"n_loaded": 3}},
        )
        chat._on_runtime_event("tool.started", {"tool": "run_fit", "arguments": {}})
        chat._on_runtime_event("tool.failed", {"tool": "run_fit", "error": "no fits"})
        chat._on_runtime_event("message.completed", {"content": "Done."})
        chat._on_runtime_event(
            "agent.completed", {"stop_reason": "answer", "steps": 2, "tools": ["load_data"]}
        )
        transcript = _settle(chat)
        assert "load_data" in transcript
        assert "3 dataset(s)" in transcript
        assert "no fits" in transcript
        assert "Done." in transcript

    def test_a_missing_provider_is_reported_instead_of_crashing(self, chat, monkeypatch):
        """An unusable provider yields no session and an explanatory message."""
        from chisurf.core.agent import LLMSettings

        def refuse(cls, *a, **k):
            raise ValueError("AI provider is not configured")

        monkeypatch.setattr(LLMSettings, "from_provider", classmethod(refuse))
        chat.provider = "openai"
        assert chat.agent_session_for(AgentMode.CHISURF_TOOLS) is None
        assert "not configured" in chat.transcript_text()

    def test_session_is_reused_across_questions(self, chat):
        """The conversation persists so follow-up questions keep context."""
        chat.provider = "local"
        first = chat.agent_session_for(AgentMode.CHISURF_TOOLS)
        if first is None:
            pytest.skip("no AI provider configured in this environment")
        assert chat.agent_session_for(AgentMode.CHISURF_TOOLS) is first

    def test_changing_mode_starts_a_new_session(self, chat):
        """Switching modes drops the conversation, since the tool set changes."""
        chat._agent_session = object()
        chat.set_mode("full_control")
        assert chat._agent_session is None

    def test_the_agent_tool_schemas_are_json_serialisable(self):
        """Whatever the assistant sends to a provider must be valid JSON."""
        from chisurf.core.agent import build_default_registry

        json.dumps(build_default_registry().to_openai_tools())

    def test_the_assistant_offers_the_shipped_example_prompts(self):
        """A new user's hardest question is what to ask it: Things to ask lists the starters."""
        from chisurf.core.agent.example_prompts import starter_prompts

        app = ChatApp()
        try:
            driver = Driver(app, (600, 700))
            driver.frame(2)
            driver.click("💡 Things to ask")
            drawn = [t[5].strip() for t in driver.frame(2).texts]
            assert starter_prompts(limit=1)[0].title in drawn
        finally:
            app.close()

    def test_choosing_an_example_fills_the_input(self):
        """It is put in the box to edit, not sent behind the user's back."""
        from chisurf.core.agent.example_prompts import starter_prompts

        app = ChatApp()
        try:
            driver = Driver(app, (600, 700))
            driver.frame(2)
            driver.click("💡 Things to ask")
            example = starter_prompts(limit=1)[0]
            row = next(t[5] for t in driver.frame(2).texts if t[5].strip() == example.title)
            driver.click(row)
            driver.frame(2)
            assert app.chat_gui.model.input_text == example.prompt.strip()
            assert not app.chat_gui.model.is_generating
        finally:
            app.close()


class TestTheGreetingFollowsTheMode:
    """The banner is the only text that says what the assistant is for."""

    def test_chat_only_talks_about_the_editor(self):
        assert "editor" in greeting_for(AgentMode.CHAT_ONLY).lower()

    @pytest.mark.parametrize("mode_name", ["CHISURF_TOOLS", "FULL_CONTROL"])
    def test_a_tool_mode_talks_about_operating_chisurf(self, mode_name):
        text = greeting_for(getattr(AgentMode, mode_name))
        assert "select code in the editor" not in text.lower()
        assert "fit" in text.lower()

    def test_full_control_says_it_will_ask_first(self):
        assert "asks you first" in greeting_for(AgentMode.FULL_CONTROL).lower()

    def test_switching_mode_re_greets(self, chat):
        """The banner is refreshed, not left describing the previous mode."""
        chat.set_mode("chat_only")
        assert "select code in the editor" in chat.transcript_text().lower()  # the empty pane
        chat.history.add_message("user", "hello")
        chat.set_mode("chisurf_tools")
        assert "operate chisurf" in chat.history.messages[-1].content.lower()  # in a conversation

    def test_the_empty_pane_shows_the_greeting(self):
        app = ChatApp()
        try:
            drawn = " ".join(t[5] for t in Driver(app, (600, 700)).frame(2).texts)
            assert "operate ChiSurf" in drawn
        finally:
            app.close()

    def test_provider_settings_open_the_ai_settings_form(self):
        """The Provider settings… button hosts the AI settings form (it raised ImportError)."""
        app = ChatApp()
        try:
            driver = Driver(app, (700, 800))
            driver.frame(2)
            driver.click("Provider settings…")
            drawn = [t[5] for t in driver.frame(2).texts]
            assert app.chat_gui.provider_settings_open
            assert app.chat_gui.provider_settings is not None
            assert "Use settings and close" in drawn
        finally:
            app.close()


class TestClarificationAndBadges:
    """A clarification round reads as a question, and a finished turn reads as finished."""

    QUESTIONS = (
        "Before I run this, a few choices are yours:\n"
        "1. Förster radius R0 (Å)?\n"
        "2. Donor-only lifetime (ns)?"
    )

    def test_the_questions_appear_as_the_assistants_turn(self, chat):
        """needs_input shows the rendered questions, not a bare 'Stopped' line."""
        chat._on_runtime_event("tool.started", {"tool": "ask_user", "arguments": {}})
        chat._on_runtime_event(
            "tool.completed", {"tool": "ask_user", "ok": True, "result": {"status": "waiting"}}
        )
        chat._on_runtime_event("agent.needs_input", {"questions": [{"id": "r0"}]})
        chat._on_runtime_event(
            "agent.completed",
            {
                "stop_reason": "needs_input",
                "steps": 1,
                "tools": ["ask_user"],
                "text": self.QUESTIONS,
            },
        )
        chat._handle_finished("needs_input")
        _settle(chat)
        last = chat.history.messages[-1]
        assert last.role == "assistant"
        assert "Förster radius R0" in last.content
        assert "Stopped" not in chat.transcript_text()

    def test_the_answer_resumes_the_same_session(self, chat):
        """Through send_prompt: the questions show, and the user's reply resumes the run."""
        from chisurf.core.agent import AgentConfig, AgentSession
        from test.agent.test_grilling import ScriptedLLM, _ask_user_call

        model = ScriptedLLM(
            [
                {"calls": [_ask_user_call()]},
                {"text": "Using R0 = 52 A and one Gaussian."},
            ]
        )
        chat.provider = "local"
        mode = AgentMode(chat.mode)
        chat._agent_session = AgentSession(
            model,
            context=chat.build_agent_context(mode),
            config=AgentConfig(max_safety=mode.safety),
        )
        chat._agent_key = (chat.provider, mode.value, chat.model_name, chat.temperature)

        def turn(text):
            chat.send_prompt(text)
            chat._in_process_thread.join(timeout=30)
            return _settle(chat)

        turn("do a burstwise analysis of the data located in xy")
        assert chat.history.messages[-1].role == "assistant"
        assert "Förster radius R0" in chat.history.messages[-1].content
        assert chat.is_generating is False, "the panel waits for the user, not for the run"

        transcript = turn("R0 = 52 A, one Gaussian component.")
        assert "Using R0 = 52 A" in transcript
        resumed = model.prompts[-1]
        assert [m.get("role") for m in resumed].count("tool") >= 1, "the open round was resumed"
        assert any("one Gaussian" in str(m.get("content")) for m in resumed if m["role"] == "user")

    def test_a_finished_tool_draws_ok_not_a_failure(self, chat):
        """emtk draws [ok] only for 'success'; a completed tool must use that word."""
        chat.history.add_message("assistant", "", status="streaming")
        chat._on_runtime_event("tool.started", {"tool": "load_data", "arguments": {}})
        chat._on_runtime_event(
            "tool.completed", {"tool": "load_data", "ok": True, "result": {"n_loaded": 1}}
        )
        chat._on_runtime_event("tool.started", {"tool": "run_fit", "arguments": {}})
        chat._on_runtime_event("tool.failed", {"tool": "run_fit", "error": "no fits"})
        _settle(chat)
        states = {c["name"]: c["status"] for c in chat.history.messages[-1].tool_calls}
        assert states == {"load_data": "success", "run_fit": "error"}

    @pytest.mark.parametrize(
        ("reported", "drawn"),
        [
            ("pending", "running"),
            ("in_progress", "running"),
            ("completed", "success"),
            ("complete", "success"),
            ("failed", "error"),
        ],
    )
    def test_acp_tool_states_map_onto_the_widgets_words(self, chat, reported, drawn):
        """An ACP agent's states are mapped too ('completed' is not a failure)."""
        chat._on_acp_tool_call("s", {"toolCallId": "t1", "title": "read", "status": reported})
        _settle(chat)
        assert chat.history.messages[-1].tool_calls[0]["status"] == drawn

    def test_thinking_clears_on_every_message_when_the_turn_ends(self, chat):
        """The tool-call message stops streaming even when the answer follows it."""
        chat.is_generating = True
        chat._on_runtime_event("tool.started", {"tool": "load_data", "arguments": {}})
        chat._on_runtime_event("tool.completed", {"tool": "load_data", "ok": True, "result": {}})
        _settle(chat)
        chat.history.add_message("assistant", "Done.")
        chat.history.add_message("system", "— 1 step(s), 1 tool call(s): load_data")
        chat._handle_finished("answer")
        assert all(m.status != "streaming" for m in chat.history.messages)
        assert chat.is_generating is False

    def test_a_cancelled_turn_leaves_no_tool_running(self, chat):
        """Cancel ends the open message and marks its unfinished tool as not done."""
        chat._on_runtime_event("tool.started", {"tool": "run_fit", "arguments": {}})
        _settle(chat)
        chat.history.add_message("system", "📘 Skill fit-decay (matched)")
        chat.cancel()
        calls = [c for m in chat.history.messages for c in m.tool_calls]
        assert calls and all(c["status"] == "error" for c in calls)
        assert all(m.status != "streaming" for m in chat.history.messages)

    def test_badges_keep_non_ascii_characters(self, chat):
        """A result with Å or ö reads as such, not as JSON escapes."""
        chat.history.add_message("assistant", "", status="streaming")
        chat._on_runtime_event("tool.started", {"tool": "custom", "arguments": {}})
        chat._on_runtime_event(
            "tool.completed", {"tool": "custom", "ok": True, "result": {"note": "R0 52 Å, Förster"}}
        )
        _settle(chat)
        output = chat.history.messages[-1].tool_calls[0]["output"]
        assert "Å" in output and "Förster" in output and "\\u" not in output

    def test_every_provider_the_settings_know_is_offered(self):
        """The panel lists each provider of the AI settings, Z.ai included, ACP first."""
        from chisurf.core.settings import ai_settings
        from chisurf.plugins.core.code_editor.gui.chat_app import PROVIDER_LABELS, PROVIDERS

        keys = {key for key, *_ in ai_settings.PROVIDERS.values()}
        assert set(PROVIDERS) == keys
        assert PROVIDERS[0] == "acp"
        assert "zai" in PROVIDERS and "Z.ai" in PROVIDER_LABELS["zai"]
