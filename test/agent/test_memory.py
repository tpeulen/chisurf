"""Long-term memory: recall before a request, the two memory tools, and safety.

The memory is the user's shared Mnemosyne store. These tests use a real
Mnemosyne on a temporary database (and the whole run's default store is a
hermetic one, set in the root ``conftest.py``), so nothing here reaches the
user's real memories.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from chisurf.core.agent import AgentConfig, AgentSession
from chisurf.core.agent.memory import AgentMemory, default_memory, looks_secret
from chisurf.core.agent.runtime import recovery_lesson
from test.agent.test_grilling import ScriptedLLM

mnemosyne = pytest.importorskip("mnemosyne.core.memory")


@pytest.fixture()
def memory(tmp_path):
    """A real Mnemosyne on a database of this test's own."""
    store = mnemosyne.Mnemosyne(session_id="test", db_path=tmp_path / "memory.db")
    return AgentMemory(store)


def test_the_test_run_never_opens_the_users_real_store():
    real = pathlib.Path.home() / ".hermes" / "mnemosyne"
    data_dir = pathlib.Path(os.environ["MNEMOSYNE_DATA_DIR"])
    assert real not in data_dir.parents and data_dir != real / "data"
    store = default_memory()._open()
    assert store is not None
    assert pathlib.Path(store.db_path).parent == data_dir


def test_memories_are_recalled_into_the_context_before_a_request(context, memory):
    memory.remember(
        "the MT200 DNA decays need two lifetime components",
        "one component left structured residuals",
        kind="lesson",
    )
    model = ScriptedLLM([{"text": "Fitted with two components."}])
    agent = AgentSession(model, context=context, memory=memory)
    agent.ask("fit the DNA decays with lifetime components")
    system = model.prompts[0][0]["content"]
    assert "What you remember" in system
    assert "two lifetime components" in system
    assert "## Memory" in system and "memory_remember" in system


def test_the_remember_tool_stores_one_fact_with_why(context, memory):
    model = ScriptedLLM(
        [
            {
                "calls": [
                    {
                        "id": "m1",
                        "name": "memory_remember",
                        "arguments": {
                            "fact": "this user wants FRET histograms as PNG and CSV",
                            "why": "they put both in their reports",
                            "kind": "preference",
                        },
                    }
                ]
            },
            {"text": "Noted."},
        ]
    )
    agent = AgentSession(model, context=context, memory=memory)
    assert agent.ask("from now on export FRET histograms as PNG and CSV").ok
    assert agent.registry.get("memory_remember") is not None
    found = memory.recall("FRET histograms PNG CSV")
    assert found and "PNG and CSV" in found[0].content
    assert "why: they put both" in found[0].content


def test_the_recall_tool_answers(context, memory):
    memory.remember("gamma is 0.82 for the Alexa488/647 setup", "calibrated 2026-10")
    agent = AgentSession(ScriptedLLM([]), context=context, memory=memory)
    spec = agent.registry.get("memory_recall")
    result = spec.handler(context, query="gamma Alexa488")
    assert result["count"] >= 1 and "0.82" in result["memories"][0]


@pytest.mark.parametrize(
    ("fact", "message"),
    [
        ("my api_key is sk-abcdefghijk", "credential"),
        ('Traceback (most recent call last):\n  File "x.py", line 1', "stack trace"),
        ("x" * 700, "one fact per memory"),
        ("", "the fact itself"),
    ],
)
def test_noise_and_secrets_are_refused(memory, fact, message):
    with pytest.raises(ValueError) as excinfo:
        memory.remember(fact, "why")
    assert message in str(excinfo.value)
    assert looks_secret("password=hunter2")


class _Broken:
    def recall(self, *args, **kwargs):
        raise RuntimeError("database is locked")

    def remember(self, *args, **kwargs):
        raise RuntimeError("database is locked")


def test_a_failing_store_leaves_the_agent_working(context):
    model = ScriptedLLM([{"text": "Answered without memory."}])
    agent = AgentSession(model, context=context, memory=AgentMemory(_Broken()))
    result = agent.ask("fit the decays")
    assert result.ok and result.text == "Answered without memory."
    assert "What you remember" not in model.prompts[0][0]["content"]


def test_without_mnemosyne_the_tools_say_why(context, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_mnemosyne(name, *args, **kwargs):
        if name.startswith("mnemosyne"):
            raise ImportError("No module named 'mnemosyne'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mnemosyne)
    memory = AgentMemory()
    assert not memory.available and "ImportError" in memory.why_unavailable
    assert memory.recall("anything") == []
    agent = AgentSession(ScriptedLLM([{"text": "ok"}]), context=context, memory=memory)
    assert agent.ask("fit the decays").ok
    from chisurf.core.agent.spec import ToolError

    with pytest.raises(ToolError, match="not available"):
        agent.registry.get("memory_remember").handler(context, fact="x", why="y")


def test_memory_off_means_no_recall_and_no_store(context, memory):
    memory.remember("the user likes three components", "test")
    model = ScriptedLLM([{"text": "ok"}])
    agent = AgentSession(
        model, context=context, memory=memory, config=AgentConfig(use_memory=False)
    )
    agent.ask("fit with components")
    assert agent.memory is None
    assert "What you remember" not in model.prompts[0][0]["content"]


def test_a_recovery_from_a_failure_keeps_one_lesson(context, memory):
    model = ScriptedLLM(
        [
            {"calls": [{"id": "a", "name": "list_files", "arguments": {"directory": "nope"}}]},
            {"calls": [{"id": "b", "name": "list_files", "arguments": {"directory": "."}}]},
            {"text": "Found them."},
        ]
    )
    agent = AgentSession(model, context=context, memory=memory)
    result = agent.ask("list my files")
    assert result.ok
    assert not result.invocations[0].ok, "the scripted first call must fail"
    lesson = recovery_lesson(result)
    assert lesson is not None and "list_files" in lesson[0]
    agent._lesson_thread.join(10)
    found = memory.recall("list_files worked after failing")
    assert any("list_files" in m.content for m in found)


def test_no_lesson_without_a_recovery(context, memory):
    model = ScriptedLLM([{"text": "Nothing to do."}])
    agent = AgentSession(model, context=context, memory=memory)
    result = agent.ask("hello")
    assert recovery_lesson(result) is None
    assert agent._lesson_thread is None
