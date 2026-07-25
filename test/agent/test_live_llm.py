"""End-to-end agent tests against a real language model.

These are the only tests that prove the *whole* harness works: prompt, tool
schemas, provider protocol, tool execution and the model's ability to pick
the right calls. They cost money and need network, so they run only when an
API key is configured::

    OPENROUTER_API_KEY=... pytest test/agent/test_live_llm.py -m live_llm

Set ``CHISURF_AGENT_TEST_MODEL`` to try a different model.
"""

from __future__ import annotations

import os

import pytest

from chisurf.core.agent import AgentConfig, AgentSession, LLMClient, LLMSettings

pytestmark = pytest.mark.live_llm

MODEL = os.environ.get("CHISURF_AGENT_TEST_MODEL", "openai/gpt-4o-mini")
TCSPC = "tcspc/EasyTau300"


@pytest.fixture()
def live_session(context):
    """Return an agent session wired to OpenRouter, or skip without a key."""
    settings = LLMSettings.from_provider("openrouter", model=MODEL)
    if not settings.api_key:
        pytest.skip("OPENROUTER_API_KEY is not set")
    return AgentSession(
        LLMClient(settings),
        context=context,
        config=AgentConfig(max_steps=12, time_budget_s=300.0),
    )


def test_the_model_loads_and_fits_a_folder(live_session):
    """The headline request: 'fit everything in this folder'."""
    result = live_session.ask(
        f"Load every .dat file in the folder {TCSPC} and fit each one with the "
        f"model 'Lifetime (new)'. Then report the reduced chi2 of each fit."
    )

    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    called = result.tool_names()
    assert "load_data" in called
    assert "create_fit" in called
    assert "run_fit" in called, "the model must optimise, not just create fits"
    assert len(live_session.context.datasets) == 4
    assert len(live_session.context.fits) == 4


def test_the_model_recovers_from_a_wrong_path(live_session):
    """A bad path must lead to a correct one, not to a loop of retries.

    Whether the model probes the missing folder first or checks with
    ``list_files`` is up to it; what matters is that it finishes and ends up
    with the real data loaded.
    """
    result = live_session.ask(
        "Load the data in the folder 'tcspc/DoesNotExist'. If that folder is "
        f"missing, load '{TCSPC}' instead."
    )
    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    assert len(live_session.context.datasets) > 0


def test_the_model_uses_python_for_something_no_tool_covers(live_session):
    """The scripting escape hatch works and its output comes back."""
    result = live_session.ask(
        "Using run_python, print the sum of the numbers 1 to 10 and tell me the value."
    )
    assert result.ok
    assert "run_python" in result.tool_names()
    assert "55" in result.text


def test_the_model_reports_parameters_of_a_fit(live_session):
    """A follow-up question in the same conversation reuses the state."""
    live_session.ask(f"Load '{TCSPC}/215-268 D0.dat' and fit it with 'Lifetime (new)'.")
    result = live_session.ask("What is the fitted lifetime, in nanoseconds?")
    assert result.ok
    assert any(character.isdigit() for character in result.text)
