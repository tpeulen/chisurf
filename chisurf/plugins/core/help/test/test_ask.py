"""The documentation assistant: what it may touch, and what it cites.

A model is scripted here rather than called, so the loop is checked without a
key and without a network. What is being tested is not the prose — that is the
model's — but the two properties the module exists to guarantee:

* the assistant **cannot reach** anything but the documentation, enforced by
  the registry rather than by the prompt;
* the pages it cites are the pages it **actually read**, taken from the tool
  invocations, because a model will happily footnote a page it never opened.
"""

from __future__ import annotations

from chisurf.core.agent.llm import LLMResponse, ToolCall
from chisurf.core.agent.runtime import AgentConfig, AgentSession
from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_READ
from chisurf.plugins.core.help.api import ask as ask_api


class ScriptedLLM:
    """Replays a fixed list of turns in place of a provider.

    Parameters
    ----------
    script : list
        Each entry is a string (a final answer) or a ``(tool, arguments)``
        tuple (a turn requesting one tool).
    """

    def __init__(self, script):
        from chisurf.core.agent.llm import LLMSettings

        self.settings = LLMSettings(
            base_url="http://test", model="test-model", supports_tools=True
        )
        self.script = list(script)

    def complete(self, messages, tools=None):
        """Return the next scripted turn."""
        self.messages = list(messages)
        self.offered_tools = tools
        if not self.script:
            return LLMResponse(text="(script exhausted)")
        step = self.script.pop(0)
        if isinstance(step, str):
            return LLMResponse(text=step, raw_message={"role": "assistant", "content": step})
        name, arguments = step
        call = ToolCall(id="call_0", name=name, arguments=arguments)
        return LLMResponse(
            text="",
            tool_calls=[call],
            raw_message={"role": "assistant", "content": "", "tool_calls": []},
        )


def _session(script) -> AgentSession:
    """Return a documentation session driven by *script*."""
    from chisurf.core.agent.skills import SkillLibrary

    library = SkillLibrary.discover()
    skill = library.get(ask_api.SKILL)
    instructions = ask_api.INSTRUCTIONS
    if skill is not None:
        instructions = f"{ask_api.INSTRUCTIONS}\n{skill.rendered()}"
    return AgentSession(
        ScriptedLLM(script),
        registry=ask_api.build_registry(),
        config=AgentConfig(
            max_steps=ask_api.MAX_STEPS,
            max_tool_calls=ask_api.MAX_STEPS * 2,
            max_safety=SAFETY_READ,
            auto_load_skills=False,
        ),
        extra_instructions=instructions,
        skills=library,
    )


# ── what it may touch ─────────────────────────────────────────────────


def test_it_has_only_the_documentation_tools():
    """A reader must not be able to start a fit because a page mentioned one."""
    names = set(ask_api.build_registry().names())
    assert names == set(ask_api.DOC_TOOLS)
    assert not names & {"load_data", "create_fit", "run_fit", "run_python", "write_file"}


def test_every_tool_it_has_is_read_only():
    for spec in ask_api.build_registry().tools.values():
        assert spec.safety == SAFETY_READ
        assert spec.safety != SAFETY_DANGEROUS


def test_the_procedure_is_in_the_prompt():
    """The skill is loaded up front, not left to a trigger word."""
    session = _session(["done"])
    assert "documentation assistant" in session.extra_instructions
    assert "browse_documentation" in session.extra_instructions
    assert "cite" in session.extra_instructions.lower() or (
        "which page" in session.extra_instructions
    )


# ── what it cites ─────────────────────────────────────────────────────


def test_it_cites_the_pages_it_read():
    session = _session(
        [
            ("browse_documentation", {"kind": "Concept", "tag": "fret"}),
            ("read_documentation", {"document": "docs/concepts/accurate_fret.md"}),
            "The gamma factor corrects for the different detection efficiencies "
            "and quantum yields of donor and acceptor.",
        ]
    )
    answer = ask_api.ask("what does gamma correct for?", session=session)

    assert answer.ok
    assert "gamma" in answer.text.lower()
    assert [page["document"] for page in answer.pages] == [
        "docs/concepts/accurate_fret.md"
    ]
    assert answer.pages[0]["type"] == "Concept"


def test_a_page_it_only_searched_for_is_not_cited():
    """Citations come from the reads, not from what went past in a result."""
    session = _session(
        [
            ("search_documentation", {"query": "burst fusion"}),
            "Bursts can be fused; see the guide.",
        ]
    )
    answer = ask_api.ask("how do I fuse bursts?", session=session)

    assert answer.pages == []
    assert answer.searched == ["burst fusion"]


def test_the_same_page_is_cited_once():
    session = _session(
        [
            ("read_documentation", {"document": "docs/concepts/fret.md"}),
            ("read_documentation",
             {"document": "docs/concepts/fret.md", "section": "Efficiency"}),
            "…",
        ]
    )
    answer = ask_api.ask("what is FRET?", session=session)
    assert len(answer.pages) == 1


def test_a_run_that_never_read_anything_is_visible_as_such():
    """A run that read nothing is distinguishable from one that did.

    Telling an answer from the pages apart from an answer from the model's
    memory is the whole point of recording the reads.
    """
    session = _session(["FRET is energy transfer between two dyes."])
    answer = ask_api.ask("what is FRET?", session=session)
    assert answer.ok
    assert answer.pages == []


# ── a citation must be a real page ────────────────────────────────────


def test_a_named_page_that_does_not_exist_is_struck_and_reported():
    """The worst failure mode, seen against a real provider.

    Asked what the code editor's assistant does, the model answered from
    nothing and closed with "— *Python scripting in ChiSurf*
    (`docs/guides/10_python_scripting.md`)" — a page that has never existed. A
    fabricated citation is worse than no citation, because the citation is what
    a reader checks the answer by.
    """
    session = _session(
        [
            ("read_documentation", {"document": "docs/concepts/fret.md"}),
            "See docs/guides/10_python_scripting.md for the rest.",
        ]
    )
    answer = ask_api.ask("what is FRET?", session=session)

    assert answer.fabricated == ["docs/guides/10_python_scripting.md"]
    assert "10_python_scripting" not in answer.text
    assert "[no such page]" in answer.text


def test_a_real_page_named_in_the_prose_is_left_alone():
    session = _session(
        [
            ("read_documentation", {"document": "docs/concepts/fret.md"}),
            "The theory is in docs/concepts/fret.md.",
        ]
    )
    answer = ask_api.ask("what is FRET?", session=session)
    assert answer.fabricated == []
    assert "docs/concepts/fret.md" in answer.text


def test_verify_citations_is_usable_on_its_own():
    text, bad = ask_api.verify_citations(
        "See docs/concepts/fret.md and docs/nope/missing.md."
    )
    assert bad == ["docs/nope/missing.md"]
    assert "docs/concepts/fret.md" in text


# ── reading is not optional ───────────────────────────────────────────


def test_an_answer_with_no_read_is_sent_back_once():
    """Prompting alone did not stop it answering from search excerpts."""
    session = _session(
        [
            ("search_documentation", {"query": "simulate photon stream"}),
            "ChiSurf can probably simulate photons.",
            ("read_documentation", {"document": "docs/concepts/photophysics_simulation.md"}),
            "ChiSurf simulates photon streams; see the concept page.",
        ]
    )
    answer = ask_api.ask("can ChiSurf simulate a photon stream?", session=session)

    assert answer.grounded
    assert [p["document"] for p in answer.pages] == [
        "docs/concepts/photophysics_simulation.md"
    ]
    assert "simulates photon streams" in answer.text
    # Both turns count as one answer: the search from the first is still
    # reported, and the steps are the sum.
    assert answer.searched == ["simulate photon stream"]
    assert answer.steps >= 2


def test_the_push_happens_once_and_then_gives_up():
    """A model that will not read after being told to is not asked a third time."""
    session = _session(["I know the answer already.", "I still know it."])
    answer = ask_api.ask("what is FRET?", session=session)
    assert not answer.grounded
    assert answer.pages == []


def test_a_run_that_read_is_not_pushed():
    session = _session(
        [("read_documentation", {"document": "docs/concepts/fret.md"}), "Energy transfer."]
    )
    answer = ask_api.ask("what is FRET?", session=session)
    assert answer.grounded
    assert answer.steps == 2


# ── failures the user has to be able to read ──────────────────────────


def test_an_empty_question_is_refused():
    answer = ask_api.ask("   ")
    assert not answer.ok
    assert answer.error


def test_a_provider_failure_is_reported_not_raised(monkeypatch):
    class Failing(ScriptedLLM):
        def complete(self, messages, tools=None):
            raise RuntimeError("the API key was rejected")

    session = _session([])
    session.llm = Failing([])
    answer = ask_api.ask("what is FRET?", session=session)
    assert not answer.ok
    assert "rejected" in answer.error


def test_availability_explains_itself_when_nothing_is_configured(monkeypatch):
    from chisurf.core.agent import llm as llm_module

    class Bare:
        base_url = ""
        api_key = ""

    monkeypatch.setattr(llm_module.LLMSettings, "from_provider",
                        classmethod(lambda cls, *a, **k: Bare()))
    available, reason = ask_api.is_available()
    assert not available
    assert "Settings" in reason


def test_the_answer_serialises_for_the_transport():
    session = _session([("read_documentation", {"document": "docs/concepts/fret.md"}), "hi"])
    payload = ask_api.ask("what is FRET?", session=session).to_dict()
    import json

    assert json.loads(json.dumps(payload))["pages"][0]["document"] == "docs/concepts/fret.md"


# ── the surfaces it is reachable through ──────────────────────────────


def test_the_rpc_method_is_declared_in_the_manifest():
    import json
    import pathlib

    from chisurf.plugins.core.help.api.contract import METHOD_ASK, contract_descriptor

    manifest = json.loads(
        (pathlib.Path(__file__).parent.parent / "manifest.json").read_text(encoding="utf-8")
    )
    assert METHOD_ASK in {method["name"] for method in manifest["rpc_methods"]}
    assert METHOD_ASK in contract_descriptor()["methods"]


def test_the_backend_rejects_a_call_with_no_question():
    from chisurf.plugins.core.help.backend import services

    result = services._ask_handler({})
    assert not result.get("ok", True)


def test_the_cli_exposes_it():
    from chisurf.plugins.core.help.cli.main import cli

    assert "ask" in cli.commands
