"""The documented example prompts, run for real.

Every example in ``chisurf/core/agent/examples/prompts.yaml`` is documentation
*and* a test. The catalogue tests below run offline and always apply; the live
ones put each prompt to a real model and check what it did.

The live ones are **allowed not to run**: no API key, no network, or an
unreachable provider is a skip, not a failure, because a documentation example
should never break a build on a machine that has no model configured. What
they will not do is pass quietly when the assistant does the wrong thing —
each example names the tools that must be used and the skills its wording must
pull in.

Run them with a provider configured::

    pytest test/agent/test_example_prompts.py -m live_llm

"""

from __future__ import annotations

import pathlib
import shutil
import zipfile

import pytest

from chisurf.core.agent import (
    AgentConfig,
    AgentContext,
    AgentSession,
    LLMClient,
    LLMSettings,
    build_default_registry,
)
from chisurf.core.agent.example_prompts import (
    CATALOGUE_PATH,
    ExamplePrompt,
    describe_examples,
    get_example,
    load_examples,
    markdown_table,
    starter_prompts,
)
from chisurf.core.agent.skills import SkillLibrary
from chisurf.core.agent.tools import data as data_tools
from test.agent.conftest import DATA_DIR

EXAMPLES = load_examples()
SOURCE_DECAY = DATA_DIR / "tcspc" / "EasyTau300" / "215-268 D0.dat"
SOURCE_IRF = DATA_DIR / "tcspc" / "EasyTau300" / "215-268 D0 irf.dat"


# ── the catalogue itself (offline, always runs) ───────────────────────


def test_the_catalogue_is_shipped_and_readable():
    assert CATALOGUE_PATH.is_file()
    assert len(EXAMPLES) >= 10


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_every_example_is_complete(example: ExamplePrompt):
    assert example.title, f"{example.id} has no title"
    assert example.prompt.strip(), f"{example.id} has no prompt"
    assert example.explanation.strip(), f"{example.id} has no explanation"
    assert example.must_call, f"{example.id} asserts nothing about what should happen"
    assert example.safety in ("read", "write", "dangerous")


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_every_example_names_real_tools(example: ExamplePrompt):
    known = set(build_default_registry().names())
    unknown = [tool for tool in example.must_call + example.should_call if tool not in known]
    assert not unknown, f"{example.id} names tools that do not exist: {unknown}"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_every_example_names_real_skills(example: ExamplePrompt):
    known = set(SkillLibrary.discover().names())
    unknown = [skill for skill in example.expect_skills if skill not in known]
    assert not unknown, f"{example.id} expects skills that do not exist: {unknown}"


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_the_wording_routes_to_the_expected_skills(example: ExamplePrompt):
    """Routing runs before the model, so this is checkable without one."""
    if not example.expect_skills:
        pytest.skip("this example makes no routing claim")
    matched = {skill.name for skill in SkillLibrary.discover().match(example.prompt, limit=3)}
    missing = set(example.expect_skills) - matched
    assert not missing, (
        f"{example.id}: the wording does not reach {sorted(missing)} (matched {sorted(matched)})"
    )


def test_example_ids_are_unique():
    identifiers = [example.id for example in EXAMPLES]
    assert len(identifiers) == len(set(identifiers))


def test_the_catalogue_renders_for_documentation_and_the_terminal():
    table = markdown_table()
    assert table.startswith("| Ask it |")
    assert all(example.prompt.split()[0] in table for example in EXAMPLES[:3])
    assert EXAMPLES[0].id in describe_examples()


def test_starter_prompts_lead_with_what_works_from_empty():
    starters = starter_prompts(limit=4)
    assert starters
    assert not starters[0].needs_session, "a new user has an empty session"


def test_an_unknown_example_is_reported():
    assert get_example("no-such-example") is None


# ── running them for real ─────────────────────────────────────────────


def _scenario(example: ExamplePrompt, root: pathlib.Path) -> pathlib.Path:
    """Build the working directory an example expects.

    Scenarios are assembled from the existing sample data rather than being
    committed as extra copies.

    Parameters
    ----------
    example : ExamplePrompt
        The example being run.
    root : pathlib.Path
        A scratch directory.

    Returns
    -------
    pathlib.Path
        The directory to run the example in.
    """
    workspace = root / example.id
    workspace.mkdir(parents=True, exist_ok=True)
    data = example.data.strip()

    if data == "tcspc/single-decay":
        shutil.copy(SOURCE_DECAY, workspace)
        shutil.copy(SOURCE_IRF, workspace)
    elif data == "tcspc/repeats":
        # Two repeat measurements of one sample: the case where a shared
        # lifetime is physically justified, which is what linking is for.
        shutil.copy(SOURCE_DECAY, workspace / "sample_run1.dat")
        shutil.copy(SOURCE_DECAY, workspace / "sample_run2.dat")
        shutil.copy(SOURCE_IRF, workspace / "sample irf.dat")
    elif data == "tcspc/zipped":
        archive = workspace / "measurement.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.write(SOURCE_DECAY, SOURCE_DECAY.name)
            bundle.write(SOURCE_IRF, SOURCE_IRF.name)
    elif data:
        source = DATA_DIR / data
        assert source.is_dir(), f"{example.id} names sample data that does not exist: {source}"
        shutil.copytree(source, workspace, dirs_exist_ok=True)
    return workspace


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_the_scenario_of_every_example_can_be_built(example, tmp_path):
    """Offline guard: a live example must have data it can actually run on."""
    workspace = _scenario(example, tmp_path)
    assert workspace.is_dir()
    if example.data:
        assert any(workspace.iterdir()), f"{example.id} produced an empty workspace"


@pytest.fixture()
def live_provider():
    """Return settings for the configured provider, or skip when unusable."""
    import os

    provider = os.environ.get("CHISURF_AGENT_TEST_PROVIDER", "openrouter")
    model = os.environ.get("CHISURF_AGENT_TEST_MODEL")
    settings = LLMSettings.from_provider(provider, model=model or None)
    if not settings.api_key or not settings.model:
        pytest.skip(f"no usable API key for provider {provider!r}")
    return settings


@pytest.mark.live_llm
@pytest.mark.parametrize(
    "example", [e for e in EXAMPLES if not e.needs_session], ids=lambda e: e.id
)
def test_an_example_prompt_does_what_it_documents(example, live_provider, tmp_path, clean_session):
    """Run the documented prompt and check what the assistant actually did."""
    from chisurf.core.agent.llm import LLMError

    workspace = _scenario(example, tmp_path)
    context = AgentContext(
        working_directory=str(workspace),
        allow_code_execution=example.safety == "dangerous",
    )
    agent = AgentSession(
        LLMClient(live_provider),
        context=context,
        config=AgentConfig(max_steps=28, time_budget_s=600.0, max_safety=example.safety),
    )

    try:
        result = agent.ask(example.prompt)
    except LLMError as error:  # unreachable provider, exhausted credit, ...
        pytest.skip(f"provider unavailable: {error}")

    if result.stop_reason == "error":
        pytest.skip(f"provider unavailable: {result.error}")

    called = set(result.tool_names())
    missing = [tool for tool in example.must_call if tool not in called]
    assert not missing, (
        f"{example.id}: expected {missing} to be used; the assistant called "
        f"{sorted(called)} and answered: {result.text[:300]}"
    )

    for skill in example.expect_skills:
        assert skill in agent.active_skills, f"{example.id}: skill {skill} was not loaded"

    for pattern in example.writes:
        assert list(workspace.rglob(pattern)), (
            f"{example.id}: nothing matching {pattern} was written"
        )

    assert result.text.strip(), f"{example.id}: the assistant answered nothing"


@pytest.mark.live_llm
@pytest.mark.parametrize("example", [e for e in EXAMPLES if e.needs_session], ids=lambda e: e.id)
def test_an_example_that_needs_a_session(example, live_provider, tmp_path, clean_session):
    """The same, for prompts that only make sense with data already loaded."""
    from chisurf.core.agent.llm import LLMError

    workspace = tmp_path / example.id
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy(SOURCE_DECAY, workspace)
    shutil.copy(SOURCE_IRF, workspace)

    context = AgentContext(
        working_directory=str(workspace),
        allow_code_execution=example.safety == "dangerous",
    )
    data_tools.load_data(context, directory=".", pattern="*.dat")
    if example.needs_fit:
        # "Is this fit any good?" presupposes a fit; without one the
        # assistant reasonably makes its own and the example proves nothing.
        from chisurf.core.agent.tools import decay as decay_tools

        # No dataset index: the tool picks the measurement rather than the
        # IRF, which sorts first in this directory.
        decay_tools.auto_fit_decay(context, max_components=2)

    agent = AgentSession(
        LLMClient(live_provider),
        context=context,
        config=AgentConfig(max_steps=16, time_budget_s=300.0, max_safety=example.safety),
    )
    try:
        result = agent.ask(example.prompt)
    except LLMError as error:
        pytest.skip(f"provider unavailable: {error}")
    if result.stop_reason == "error":
        pytest.skip(f"provider unavailable: {result.error}")

    called = set(result.tool_names())
    missing = [tool for tool in example.must_call if tool not in called]
    assert not missing, f"{example.id}: expected {missing}; called {sorted(called)}"
    for pattern in example.writes:
        assert list(workspace.rglob(pattern)), f"{example.id}: no {pattern} written"
