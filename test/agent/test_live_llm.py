r"""End-to-end agent tests against a real language model.

These are the only tests that prove the *whole* harness works: prompt, tool
schemas, provider protocol, tool execution and the model's ability to pick
the right calls. They cost money and need network, so they run only when an
API key is configured::

    OPENROUTER_API_KEY=... pytest test/agent/test_live_llm.py -m live_llm

**Any provider can drive them.** Tool calling is the part most likely to
differ between providers, so running the same suite against a second one is
the cheapest way to find a dialect problem::

    CHISURF_AGENT_TEST_PROVIDER=mistral \
    CHISURF_AGENT_TEST_MODEL=mistral-small-latest \
        pytest test/agent/test_live_llm.py -m live_llm

The key is taken from the provider's environment variable (see
:func:`chisurf.core.settings.ai_settings.provider_key_env_names`), and the
suite skips when none is set.
"""

from __future__ import annotations

import os

import pytest

from chisurf.core.agent import AgentConfig, AgentSession, LLMClient, LLMSettings

pytestmark = pytest.mark.live_llm

#: Provider and model under test; override to exercise another provider.
PROVIDER = os.environ.get("CHISURF_AGENT_TEST_PROVIDER", "openrouter")
DEFAULT_MODELS = {
    "openrouter": "openai/gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "mistral": "mistral-small-latest",
}
MODEL = os.environ.get("CHISURF_AGENT_TEST_MODEL") or DEFAULT_MODELS.get(PROVIDER, "")
TCSPC = "tcspc/EasyTau300"


@pytest.fixture()
def live_session(context):
    """Return an agent session wired to the configured provider, or skip."""
    from chisurf.core.settings.ai_settings import provider_key_env_names

    settings = LLMSettings.from_provider(PROVIDER, model=MODEL or None)
    if not settings.api_key:
        pytest.skip(
            f"no API key for provider {PROVIDER!r} (looked in {provider_key_env_names(PROVIDER)})"
        )
    return AgentSession(
        LLMClient(settings),
        context=context,
        config=AgentConfig(max_steps=16, time_budget_s=300.0),
    )


#: Failures that say nothing about the agent — the provider was unavailable,
#: out of credit or rate-limiting. These skip; a genuinely wrong answer fails.
UNAVAILABLE = (
    "http 402",
    "http 429",
    "http 5",
    "credit",
    "quota",
    "rate limit",
    "capacity",
    "timed out",
    "connection",
    "unreachable",
)


def require_reachable(result):
    """Skip when the provider was unreachable rather than the agent wrong.

    These prompts are documentation as much as tests: they must fail loudly
    when the agent misbehaves, and stay quiet when nobody is answering.

    Parameters
    ----------
    result : object
        The result of :meth:`AgentSession.ask`.
    """
    if result.ok:
        return
    message = f"{result.stop_reason} {result.error}".lower()
    if any(marker in message for marker in UNAVAILABLE):
        pytest.skip(f"provider unavailable: {result.error}")


def test_the_provider_is_configured_for_tool_calling(live_session):
    """A provider that cannot be reached fails every other test confusingly."""
    assert live_session.llm.settings.model, f"no model configured for {PROVIDER!r}"
    assert live_session.native_tools


def test_the_model_loads_and_fits_a_folder(live_session):
    """The headline request: 'fit the decays in this folder'."""
    result = live_session.ask(
        f"Load the .dat files in the folder {TCSPC} and fit the fluorescence "
        f"decays with the model 'Lifetime'. Report the reduced chi2."
    )

    require_reachable(result)
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
    require_reachable(result)
    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    assert len(live_session.context.datasets) > 0


def test_the_model_uses_python_for_something_no_tool_covers(live_session):
    """The scripting escape hatch works and its output comes back."""
    result = live_session.ask(
        "Using run_python, print the sum of the numbers 1 to 10 and tell me the value."
    )
    require_reachable(result)
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
    require_reachable(result)
    assert result.ok, f"agent stopped early: {result.stop_reason} {result.error}"
    assert "set_irf" in result.tool_names(), "a decay fit without an IRF is wrong"

    from chisurf.core.agent.tools.decay import assess_fit

    verdict = assess_fit(live_session.context.fits[0])
    assert verdict["quality"] in ("good", "acceptable"), verdict


def test_the_right_skill_is_loaded_from_the_request(live_session):
    """Routing happens before the model is called, so it is deterministic."""
    live_session.ask(f"Have a look at what is in the folder {TCSPC}.")
    assert "explore-data" in live_session.active_skills

    live_session.ask("Now fit the donor decay and give me its lifetime.")
    assert "fit-decay" in live_session.active_skills


def test_a_loaded_skill_reaches_the_model(live_session):
    """The procedure must be in the request, not merely in the library."""
    live_session.ask(f"Fit the decay {TCSPC}/215-268 D0.dat.")
    system_prompt = live_session.messages[0]["content"]
    assert "Skill: fit-decay" in system_prompt
    assert "instrument response" in system_prompt.lower()


def test_the_model_reports_parameters_of_a_fit(live_session):
    """A follow-up question in the same conversation reuses the state."""
    live_session.ask(f"Load '{TCSPC}/215-268 D0.dat' and fit it with 'Lifetime'.")
    result = live_session.ask("What is the fitted lifetime, in nanoseconds?")
    require_reachable(result)
    assert result.ok
    assert any(character.isdigit() for character in result.text)
