"""Widget tests for the AI assistant panel wired to the ChiSurf agent."""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import SAFETY_DANGEROUS, SAFETY_WRITE
from chisurf.plugins.core.code_editor.agent_panel import AgentMode, AgentPanelWidget


class TestAgentPanelWidget:
    """The panel exposes the agent's modes and renders its events."""

    def test_modes_map_to_safety_tiers(self):
        """Each mode grants exactly the tool tier its label promises."""
        assert AgentMode.CHISURF_TOOLS.safety == SAFETY_WRITE
        assert AgentMode.FULL_CONTROL.safety == SAFETY_DANGEROUS

    def test_panel_offers_the_three_modes(self, qapp):
        """The mode selector lists chat, tools and full control."""
        panel = AgentPanelWidget()
        values = [panel.mode_combo.itemData(i) for i in range(panel.mode_combo.count())]
        assert values == [
            AgentMode.CHAT_ONLY.value,
            AgentMode.CHISURF_TOOLS.value,
            AgentMode.FULL_CONTROL.value,
        ]

    def test_context_grants_code_execution_only_in_full_control(self, qapp):
        """Code execution and confirmation are tied to full-control mode."""
        panel = AgentPanelWidget()

        tools_context = panel._build_agent_context(AgentMode.CHISURF_TOOLS)
        assert tools_context.allow_code_execution is False
        assert tools_context.confirm is None

        full_context = panel._build_agent_context(AgentMode.FULL_CONTROL)
        assert full_context.allow_code_execution is True
        assert full_context.confirm is not None

    def test_provider_status_is_reported(self, qapp):
        """The status dot always carries an explanation in its tooltip."""
        panel = AgentPanelWidget()
        panel._check_provider_status()
        assert panel.rpc_status_label.toolTip()

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
        assert expected in AgentPanelWidget._tool_highlight({"result": result})

    def test_a_loaded_skill_is_announced(self, qapp):
        """The user should see which procedure the assistant is following."""
        panel = AgentPanelWidget()
        panel._on_runtime_event("skill.loaded", {"skill": "fit-decay", "trigger": "auto"})
        transcript = panel.transcript.toPlainText()
        assert "fit-decay" in transcript
        assert "matched" in transcript

    def test_runtime_events_reach_the_transcript(self, qapp):
        """Tool and completion events are rendered without raising."""
        panel = AgentPanelWidget()
        panel._on_runtime_event("agent.started", {"question": "fit my data"})
        panel._on_runtime_event(
            "tool.started", {"tool": "load_data", "arguments": {"directory": "d"}}
        )
        panel._on_runtime_event(
            "tool.completed",
            {"tool": "load_data", "ok": True, "elapsed_ms": 5, "result": {"n_loaded": 3}},
        )
        panel._on_runtime_event("tool.failed", {"tool": "run_fit", "error": "no fits"})
        panel._on_runtime_event("message.completed", {"content": "Done."})
        panel._on_runtime_event(
            "agent.completed", {"stop_reason": "answer", "steps": 2, "tools": ["load_data"]}
        )

        transcript = panel.transcript.toPlainText()
        assert "load_data" in transcript
        assert "3 dataset(s)" in transcript
        assert "no fits" in transcript
        assert "Done." in transcript

    def test_a_missing_provider_is_reported_instead_of_crashing(self, qapp, monkeypatch):
        """An unusable provider yields no session and an explanatory message."""
        from chisurf.core.agent import LLMSettings

        monkeypatch.setattr(
            LLMSettings, "from_provider", classmethod(lambda cls, *a, **k: LLMSettings())
        )
        panel = AgentPanelWidget()
        assert panel._agent_session_for(AgentMode.CHISURF_TOOLS) is None
        assert "not configured" in panel.transcript.toPlainText()

    def test_session_is_reused_across_questions(self, qapp, monkeypatch):
        """The conversation persists so follow-up questions keep context."""
        panel = AgentPanelWidget()
        first = panel._agent_session_for(AgentMode.CHISURF_TOOLS)
        if first is None:
            pytest.skip("no AI provider configured in this environment")
        assert panel._agent_session_for(AgentMode.CHISURF_TOOLS) is first

    def test_changing_mode_starts_a_new_session(self, qapp):
        """Switching modes drops the conversation, since the tool set changes."""
        panel = AgentPanelWidget()
        panel._agent_session = object()
        panel.mode_combo.setCurrentIndex(1)
        assert panel._agent_session is None

    def test_the_agent_tool_schemas_are_json_serialisable(self):
        """Whatever the panel sends to a provider must be valid JSON."""
        from chisurf.core.agent import build_default_registry

        json.dumps(build_default_registry().to_openai_tools())

    def test_the_panel_offers_the_shipped_example_prompts(self, qapp):
        """A new user's hardest question is what to ask it."""
        from chisurf.core.agent.example_prompts import starter_prompts

        panel = AgentPanelWidget()
        actions = [action.text() for action in panel.examples_btn.menu().actions()]
        assert actions
        assert actions[0] == starter_prompts(limit=1)[0].title

    def test_choosing_an_example_fills_the_input(self, qapp):
        """It is put in the box to edit, not sent behind the user's back."""
        panel = AgentPanelWidget()
        panel._use_example("Fit the decay in this folder.")
        assert panel.input.toPlainText() == "Fit the decay in this folder."
