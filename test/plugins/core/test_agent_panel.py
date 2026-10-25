"""The agent panel: the flow works headless, the manifest resolves.

The user opens the agent from the Tools menu; these tests pin the two things
that can silently break — the panel's ask flow (thread, queue, transcript,
clarification as a normal turn) and the plugin's discovery (manifest parses,
the entrypoint imports, the session builder exposes the full registry).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chisurf.plugins.core.agent.gui.panel import ROLE_AGENT, ROLE_ERROR, AgentApp, make_app


class FakeResult:
    def __init__(self, text):
        self.text = text
        self.stop_reason = "answer"


class FakeSession:
    """Records the asks; answers from a script."""

    def __init__(self):
        self.asked: list[str] = []
        self.replies = ["42 bursts found; R = 43.1 A."]
        self.cancelled = False

    def ask(self, text):
        self.asked.append(text)
        time.sleep(0.01)
        return FakeResult(self.replies[min(len(self.asked) - 1, len(self.replies) - 1)])

    def cancel(self):
        self.cancelled = True


@pytest.fixture()
def panel():
    session = FakeSession()
    app = AgentApp(session_factory=lambda: session)
    app._session = session
    return app, session


def test_a_submit_reaches_the_session_and_the_answer_lands(panel):
    app, session = panel
    assert app.submit("do a burstwise analysis of the data in xy") is True
    assert app.busy
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.poll()
        time.sleep(0.005)
    assert not app.busy
    assert [m["role"] for m in app.transcript] == ["user", ROLE_AGENT]
    assert "43.1" in app.transcript[-1]["text"]


def test_an_empty_or_duplicate_submit_is_refused(panel):
    app, _ = panel
    assert app.submit("   ") is False
    assert app.submit("question") is True
    assert app.submit("second while busy") is False


def test_a_clarification_round_is_an_answer_and_the_thread_continues(panel):
    """The questions are the agent's turn; the next submit answers in-session."""
    app, session = panel
    session.replies = ["Before I continue I need a few answers:\n1. Which R0?"]
    app.submit("the owner's example")
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.poll()
        time.sleep(0.005)
    assert "Which R0?" in app.transcript[-1]["text"]
    # The user answers; the same session (the same conversation) gets it.
    session.replies = ["R = 43.3 A with your R0."]
    app.submit("R0 = 52 A, one Gaussian")
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.poll()
        time.sleep(0.005)
    assert session.asked == ["the owner's example", "R0 = 52 A, one Gaussian"]
    assert "43.3" in app.transcript[-1]["text"]


def test_a_failure_becomes_an_error_turn(panel):
    class Broken(FakeSession):
        def ask(self, text):
            raise RuntimeError("no provider key")

    app = AgentApp(session_factory=Broken)
    app.submit("anything")
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.poll()
        time.sleep(0.005)
    assert app.transcript[-1]["role"] == ROLE_ERROR
    assert "no provider key" in app.transcript[-1]["text"]


def test_stop_cancels_the_session(panel):
    app, session = panel
    app.stop()
    assert session.cancelled


def test_make_app_and_manifest_resolve():
    """The Tools-menu entry can actually build the panel."""
    manifest = json.loads(
        (Path(__file__).parents[3] / "chisurf/plugins/core/agent/manifest.json").read_text()
    )
    assert manifest["id"] == "agent"
    assert "Tools" in manifest["categories"]
    module_name, _, attribute = manifest["entrypoints"]["emtk"].partition(":")
    import importlib

    factory = getattr(importlib.import_module(module_name), attribute)
    assert callable(factory)


def test_the_panel_session_carries_the_full_registry():
    """The workflow registry, not a restricted one: the burst chain is reachable."""
    from chisurf.plugins.core.agent.api.session import build_registry

    names = set(build_registry().names())
    for expected in (
        "run_burst_analysis",
        "select_species",
        "extract_subensemble_decay",
        "fit_distance_distribution",
        "ask_user",
        "run_python",
        "load_data",
        "create_fit",
    ):
        assert expected in names, f"the panel cannot reach {expected}"
