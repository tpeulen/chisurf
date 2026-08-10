"""Every speaker has a backstory, and every model reply passes a gate."""

from __future__ import annotations

import json

from chisurf.plugins.misc.games.lumis_quest.api import npcs, personas


def _npc(kind: str, role: str = "", name: str = "someone",
         line: str = "hello", address: str = "") -> npcs.Npc:
    return npcs.Npc(kind=kind, name=name, x=0.0, y=0.0, home=(0.0, 0.0),
                    radius=0.0, line=line, address=address, role=role)


class _Client:
    """A fake model that returns a scripted reply."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return type("R", (), {"text": self._text})()


def test_a_keeper_persona_carries_their_page():
    """A keeper's backstory is about the page they keep, not generic villager."""
    npc = _npc("villager", name="Burst Selection", address="docs/guides/11.md")
    persona = personas.persona_for(npc, land_title="The Pilgrim Road",
                                   prosperity=0.1)
    assert persona is not None
    assert "Burst Selection" in persona.backstory
    assert "keeper" in persona.backstory.lower()
    assert "half dark" in persona.situation


def test_an_emissary_persona_argues_their_doctrine():
    """The order's creed and wants are the backstory."""
    persona = personas.persona_for(_npc("emissary", role="emissary:rigour",
                                        name="Merel, Voice of Rigour"))
    assert persona is not None
    assert "Rigour" in persona.backstory
    assert "recruiting" in persona.backstory


def test_the_scripted_scene_is_never_model_voiced():
    """The waking cannot drift: elder, hound, beasts and animals stay authored."""
    assert personas.persona_for(_npc("villager", role="elder")) is None
    assert personas.persona_for(_npc("lumi", role="lumi")) is None
    assert personas.persona_for(_npc("beast")) is None
    assert personas.persona_for(_npc("animal")) is None


def test_the_gate_refuses_what_it_should():
    """Malformed, empty, oversized and stage-directed replies all die."""
    assert personas.parse("not json") is None
    assert personas.parse("[]") is None
    assert personas.parse(json.dumps(["one line"])) is None, "monologue minimum is 2"
    assert personas.parse(json.dumps(["a", "b", "c", "d", "e"])) is None
    assert personas.parse(json.dumps(["fine", "x" * 500])) is None
    assert personas.parse(json.dumps(["*waves*", "hello there"])) is None
    assert personas.parse(json.dumps([1, 2])) is None

    good = personas.parse(json.dumps(["Well met.", "The lamps hold, for now."]))
    assert good == ("Well met.", "The lamps hold, for now.")


def test_the_director_fetches_gates_and_caches(tmp_path):
    """One network call per voice, then the cache answers."""
    reply = json.dumps(["The lamps hold.", "Mind the dark past the gate."])
    client = _Client(reply)
    director = personas.DialogueDirector(client=client, cache_dir=tmp_path)
    persona = personas.persona_for(_npc("townsfolk", name="the smith"))

    lines = director.fetch_now(persona)
    assert lines == ("The lamps hold.", "Mind the dark past the gate.")
    assert client.calls == 1

    # A second director with no client still answers, from disk.
    cold = personas.DialogueDirector(client=None, cache_dir=tmp_path)
    cold._client_built = True  # never build a real client in tests
    assert cold.lines_for(persona) == lines


def test_a_refused_reply_leaves_the_authored_lines_standing(tmp_path):
    """A director with a babbling model returns None and counts the rejection."""
    director = personas.DialogueDirector(client=_Client("I am an AI and"),
                                         cache_dir=tmp_path)
    persona = personas.persona_for(_npc("townsfolk", name="the carter"))
    assert director.fetch_now(persona) is None
    assert director.rejected == 1


def test_no_client_means_no_voice_and_no_error(tmp_path):
    """The world is never mute for want of a network."""
    director = personas.DialogueDirector(cache_dir=tmp_path)
    director._client_built = True  # simulate "no provider configured"
    persona = personas.persona_for(_npc("townsfolk", name="the gardener"))
    assert director.fetch_now(persona) is None
