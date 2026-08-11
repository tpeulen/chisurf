"""Whoever writes the question, it passes the same grounding check."""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.misc.games.lumis_quest.api import providers, review_bridge

PAGE = """
# Anisotropy

The fundamental anisotropy of a fluorophore describes how much polarisation
memory survives the excited-state lifetime, and it is bounded above by two
fifths for a single absorbing transition dipole.

Rotational correlation time governs how quickly that memory is lost, so a
larger molecule tumbling slowly retains polarisation for longer than a small
one in the same solvent at the same temperature.
"""

GOOD = json.dumps([{
    "span": "Rotational correlation time governs how quickly that memory is lost",
    "prompt": "Rotational _____ time governs how quickly that memory is lost",
    "options": ["correlation", "coherence", "collection", "conversion"],
    "answer": 0,
}])

INVENTED = json.dumps([{
    "span": "The anisotropy is always exactly one half in every solvent.",
    "prompt": "The anisotropy is always exactly one _____ in every solvent.",
    "options": ["half", "third", "quarter", "fifth"],
    "answer": 0,
}])


def test_a_grounded_answer_is_accepted():
    """The span is really in the page."""
    found, rejected = providers.parse(GOOD, PAGE, 2)
    assert len(found) == 1 and rejected == 0
    assert found[0].is_correct(0)


def test_an_invented_quote_is_rejected():
    """The failure a language model actually makes here, caught by code.

    A model will quote a sentence the page does not contain, confidently, and
    nothing downstream can tell the difference. So the check is mechanical and
    the rejects are counted.
    """
    found, rejected = providers.parse(INVENTED, PAGE, 2)
    assert found == [] and rejected == 1


def test_malformed_answers_are_rejected_not_raised():
    """A model returning prose, or the wrong shape, must not break the game."""
    assert providers.parse("I'm sorry, I can't do that.", PAGE, 1) == ([], 0)
    assert providers.parse("[]", PAGE, 1) == ([], 0)

    bad_shape = json.dumps([{"span": "Rotational correlation time governs",
                             "prompt": "no blank here",
                             "options": ["a", "b", "c", "d"], "answer": 0}])
    found, rejected = providers.parse(bad_shape, PAGE, 1)
    assert found == [] and rejected == 1

    bad_index = json.dumps([{"span": "Rotational correlation time governs",
                             "prompt": "Rotational _____ time governs",
                             "options": ["a", "b", "c", "d"], "answer": 9}])
    assert providers.parse(bad_index, PAGE, 1)[1] == 1


def test_a_recorded_provider_is_re_verified():
    """A fixture cannot smuggle an ungrounded question past the check."""
    honest = providers.RecordedProvider({"h1": GOOD})
    assert len(honest.generate(PAGE, "h1", 1)) == 1
    assert honest.rejected == 0

    lying = providers.RecordedProvider({"h1": INVENTED})
    assert lying.generate(PAGE, "h1", 1) == []
    assert lying.rejected == 1

    assert providers.RecordedProvider({}).generate(PAGE, "missing", 1) == []


def test_an_unconfigured_model_yields_nothing_rather_than_raising(monkeypatch):
    """The caller has a working fallback; refusing to run would be worse.

    The absence of a provider is forced rather than assumed: relying on this
    machine having no AI configured makes the test pass or fail depending on
    whose laptop it runs on.
    """
    agent = providers.AgentProvider()
    monkeypatch.setattr(agent, "_make_client", lambda: None)
    assert agent.generate(PAGE, "h", 1) == []


def test_a_failing_client_is_caught():
    """A model that is down must not stop the game."""

    class Broken:
        def complete(self, messages):
            raise RuntimeError("no route to host")

    assert providers.AgentProvider(client=Broken()).generate(PAGE, "h", 1) == []


def test_a_live_client_answer_is_parsed_and_verified():
    """The model path end to end, with a stand-in client."""

    class Model:
        def __init__(self, payload):
            self.payload = payload

        def complete(self, messages):
            assert "PAGE:" in messages[0]["content"]
            return type("R", (), {"text": self.payload})()

    assert len(providers.AgentProvider(client=Model(GOOD)).generate(PAGE, "h", 1)) == 1

    liar = providers.AgentProvider(client=Model(INVENTED))
    assert liar.generate(PAGE, "h", 1) == []
    assert liar.rejected == 1


def test_encounters_are_cached_by_content_hash(tmp_path):
    """Reproducible, and self-invalidating when the page changes."""
    found, _ = providers.parse(GOOD, PAGE, 1)
    providers.store("hash-a", found, tmp_path)

    back = providers.cached("hash-a", tmp_path)
    assert back and back[0].prompt == found[0].prompt
    assert providers.cached("hash-b", tmp_path) is None


def test_a_corrupt_cache_entry_is_ignored(tmp_path):
    """A bad cache must not be worse than no cache."""
    (tmp_path / "hash-c.json").write_text("{ not json", encoding="utf-8")
    assert providers.cached("hash-c", tmp_path) is None

    (tmp_path / "hash-d.json").write_text(json.dumps([{"prompt": "x"}]), encoding="utf-8")
    assert providers.cached("hash-d", tmp_path) is None


def test_the_bridge_falls_back_when_a_provider_returns_nothing(tmp_path):
    """A model that is down means a simpler question, not no game."""
    page = tmp_path / "page.md"
    page.write_text(PAGE, encoding="utf-8")

    class Silent:
        def generate(self, text, content_hash, count):
            return []

    found, content_hash = review_bridge.challenge_for(
        page, provider=Silent(), cache_dir=tmp_path / "cache"
    )
    assert found, "the deterministic provider must cover for a silent model"
    assert content_hash


def test_the_bridge_serves_the_cache_on_a_second_visit(tmp_path):
    """And regenerates once the page changes."""
    page = tmp_path / "page.md"
    page.write_text(PAGE, encoding="utf-8")
    cache = tmp_path / "cache"

    calls = []

    class Counting:
        def generate(self, text, content_hash, count):
            calls.append(content_hash)
            return providers.DeterministicProvider().generate(text, content_hash, count)

    first, hash_one = review_bridge.challenge_for(page, provider=Counting(), cache_dir=cache)
    second, hash_two = review_bridge.challenge_for(page, provider=Counting(), cache_dir=cache)
    assert first and second and hash_one == hash_two
    assert len(calls) == 1, "the second visit must come from the cache"

    page.write_text(PAGE + "\n\nA new paragraph changes the hash entirely.\n", encoding="utf-8")
    _, hash_three = review_bridge.challenge_for(page, provider=Counting(), cache_dir=cache)
    assert hash_three != hash_one
    assert len(calls) == 2, "a changed page must regenerate"


def test_llm_status_reports_wired_and_unconfigured_states(monkeypatch):
    """llm_status must return structured info, green/red indicators, and setup guidance."""
    status = providers.llm_status()
    assert "wired" in status
    assert "indicator" in status
    assert status["indicator"] in ("●", "○")
    assert "hover_info" in status
    assert "Settings -> AI" in status["hover_info"]
