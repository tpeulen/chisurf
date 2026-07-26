"""Getting a usable action out of a model that misformats one.

Three failures cost whole turns in real runs against Mistral, and each has a
cheap, bounded recovery:

* the model narrated the call instead of making it, leaving the name in the
  message text with the arguments beside it;
* it put a paragraph of reasoning where the function name goes;
* it wrapped its scratch work in ``<think>`` tags inside the answer.

Recovery is deliberately narrow. Only a *known* tool name is ever routed, and
a near miss has to reduce to the same identifier — guessing further would run
the wrong operation, which is worse than an error.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentConfig, AgentContext, AgentSession
from chisurf.core.agent.llm import strip_reasoning


@pytest.fixture()
def session(clean_session, tmp_path):
    """Return a session with no language model behind it."""
    return AgentSession(
        llm=None,
        context=AgentContext(working_directory=str(tmp_path)),
        config=AgentConfig(),
    )


# ── stripping ─────────────────────────────────────────────────────────


def test_a_think_block_is_removed():
    text = "<think>maybe the IRF is missing</think>The lifetime is 1.85 ns."
    assert strip_reasoning(text) == "The lifetime is 1.85 ns."


def test_an_unclosed_block_takes_the_rest_with_it():
    """A truncated response looks exactly like this."""
    assert strip_reasoning("Answer first. <think>then it was cut off") == "Answer first."


def test_ordinary_text_is_untouched():
    assert strip_reasoning("R = 51 A, and R0 < 60 A") == "R = 51 A, and R0 < 60 A"


def test_a_thinking_chunk_is_dropped_but_text_is_kept():
    from chisurf.core.agent.llm import message_text

    content = [
        {"type": "thinking", "thinking": "I should check the IRF"},
        {"type": "text", "text": "The lifetime is 1.85 ns."},
    ]
    assert message_text(content) == "The lifetime is 1.85 ns."


# ── rerouting a narrated call ─────────────────────────────────────────


def test_a_call_written_as_prose_is_recovered(session):
    """The shape seen live: name and arguments run together in the text."""
    call = session._recover_tool_call('I will check the plugins now list_plugins{"query": "kappa"}')

    assert call is not None
    assert call.name == "list_plugins"
    assert call.arguments == {"query": "kappa"}


def test_a_nested_single_key_object_is_unwrapped(session):
    """The other shape: ``{'run_python': {...}}`` as the whole payload."""
    call = session._recover_tool_call("{'run_python': {'code': 'result = 6 * 7'}}")

    assert call is not None
    assert call.name == "run_python"
    assert call.arguments == {"code": "result = 6 * 7"}


def test_the_text_protocol_form_is_still_recovered(session):
    call = session._recover_tool_call('{"tool": "list_fits", "arguments": {}}')
    assert call is not None and call.name == "list_fits"


def test_trailing_prose_after_the_object_does_not_break_it(session):
    call = session._recover_tool_call(
        'list_plugins{"query": "burst"} — then I will read the source.'
    )
    assert call is not None and call.arguments == {"query": "burst"}


def test_prose_alone_is_not_a_call(session):
    assert session._recover_tool_call("I will now list the plugins and read one.") is None


def test_an_unknown_name_is_not_invented(session):
    """Only tools that exist are ever routed."""
    assert session._recover_tool_call('frobnicate{"x": 1}') is None


def test_json_in_an_answer_is_not_mistaken_for_a_call(session):
    text = 'The fit returned {"chi2r": 1.03, "tau": 1.85}.'
    assert session._recover_tool_call(text) is None


# ── rerouting a near-miss name ────────────────────────────────────────


@pytest.mark.parametrize(
    "written",
    ["list_plugin", "List_Plugins", "functions.list_plugins", "listplugins"],
)
def test_a_misspelled_tool_name_routes_to_the_real_one(session, written):
    corrected = session._nearest_tool(written)
    assert corrected is not None and corrected.name == "list_plugins"


def test_a_genuinely_unknown_name_is_refused(session):
    assert session._nearest_tool("frobnicate") is None
    assert session._nearest_tool("") is None


def test_the_correction_does_not_cross_between_real_tools(session):
    """``run_fit`` and ``run_python`` must never be confused for each other."""
    assert session._nearest_tool("run_fit").name == "run_fit"
    assert session._nearest_tool("run_python").name == "run_python"
