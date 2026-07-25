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
        config=AgentConfig(max_steps=16, time_budget_s=300.0),
    )


def test_the_model_loads_and_fits_a_folder(live_session):
    """The headline request: 'fit the decays in this folder'."""
    result = live_session.ask(
        f"Load the .dat files in the folder {TCSPC} and fit the fluorescence "
        f"decays with the model 'Lifetime (new)'. Report the reduced chi2."
    )

    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    called = result.tool_names()
    assert "load_data" in called
    assert "create_fit" in called
    assert "run_fit" in called, "the model must optimise, not just create fits"
    assert len(live_session.context.datasets) == 4

    fitted = [
        str(getattr(getattr(fit, "data", None), "name", "")).lower()
        for fit in live_session.context.fits
    ]
    assert len(fitted) >= 2, f"expected the two sample decays to be fitted, got {fitted}"
    # The folder holds two decays and their two IRF measurements. An IRF is a
    # reference, not a sample: fitting one is a mistake the tool results warn
    # about, so it must not happen.
    assert not any("irf" in name for name in fitted), f"an IRF was fitted: {fitted}"


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


def test_the_model_reaches_a_good_decay_fit_on_its_own(live_session):
    """The scientific end-to-end: a naive request must produce a usable fit.

    Getting there needs the IRF attached and more than one lifetime; the tool
    results say so, and the model has to act on that without being told.
    """
    result = live_session.ask(
        f"I measured a fluorescence decay in {TCSPC}/215-268 D0.dat, and the "
        f"instrument response is in the same folder. Fit it properly and tell "
        f"me the lifetimes."
    )
    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    assert "set_irf" in result.tool_names(), "a decay fit without an IRF is wrong"

    from chisurf.core.agent.tools.decay import assess_fit

    verdict = assess_fit(live_session.context.fits[0])
    assert verdict["quality"] in ("good", "acceptable"), verdict


def test_the_model_reports_parameters_of_a_fit(live_session):
    """A follow-up question in the same conversation reuses the state."""
    live_session.ask(f"Load '{TCSPC}/215-268 D0.dat' and fit it with 'Lifetime (new)'.")
    result = live_session.ask("What is the fitted lifetime, in nanoseconds?")
    assert result.ok
    assert any(character.isdigit() for character in result.text)
