"""Voices for the people of the world: every speaker has a backstory.

With the model switched on (the same MODE-tab switch that governs questions),
an inhabitant's dialogue is written by the configured language model **in
character**: a keeper speaks as someone who has read and vouched for their own
page, an emissary argues their order's doctrine, a smith complains about
glass. With it off — the default — everyone falls back to their authored
lines, so the world is never mute for want of a network.

The same discipline as the question providers applies:

* **A gate, in code.** Whatever the model returns is parsed and checked —
  line count, line length, no stage directions, no breaking character markers.
  A reply that fails the gate is discarded and the authored lines stand.
* **Cached.** A character's voice is fetched once per situation and kept, so
  a conversation costs a network call the first time and nothing after.
* **Never in the frame loop.** Fetches run on a background thread; the first
  talk shows the authored lines while the model thinks, and the character has
  found their voice by the next visit. A game that stalls mid-dialogue on a
  network call is worse than one that speaks plainly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import threading

from .story import ORDERS

#: Where fetched voices live between sessions.
CACHE_DIR = pathlib.Path.home() / ".chisurf" / "lumis_quest_voices"

#: The one premise every character lives inside. Kept short: the backstory
#: carries the individual, this carries the world.
WORLD_BRIEF = (
    "The world of Lumis Quest: everything alive carries light — a quantum it "
    "holds, spends, and gives back changed. Knowledge is the same substance: "
    "a page somebody read and vouched for burns steadily with its keeper at "
    "the door; a page nobody opened goes dark. The Fading is light leaving "
    "the world, a lamp at a time. Iris, a probe — a photon given a body — has "
    "come to find where the light is going, with Lumi, a hound of light, at "
    "her heel."
)

PROMPT = """{world}

You are voicing one character in this world.

CHARACTER: {name}
BACKSTORY: {backstory}
SITUATION: {situation}

Write what this character says to Iris, in character, in their own voice.
Rules:
- Return ONLY a JSON array of 2 to 4 strings, no prose around it.
- Each string is one thing they say, at most 160 characters, no newlines.
- No stage directions, no asterisks, no quotation marks around lines.
- Never mention being an AI, a model, or a game.
"""


@dataclasses.dataclass(frozen=True)
class Persona:
    """One character, ready to be voiced.

    Attributes
    ----------
    key : str
        Stable identity for caching (survives restarts).
    name : str
        Display name.
    backstory : str
        Who they are — the part that makes the voice theirs.
    situation : str
        What is true right now, coarse enough to cache on.
    """

    key: str
    name: str
    backstory: str
    situation: str

    @property
    def cache_token(self) -> str:
        """Filename-safe digest of everything the voice depends on.

        Returns
        -------
        str
            Hex digest; a changed backstory or situation is a new voice.
        """
        payload = "\n".join((self.key, self.backstory, self.situation))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def persona_for(npc, land_title: str = "", prosperity: float | None = None,
                counts: dict | None = None) -> Persona | None:
    """Build the persona behind an inhabitant, if they have one.

    Parameters
    ----------
    npc : chisurf.plugins.misc.games.lumis_quest.api.npcs.Npc
        Who is speaking.
    land_title : str, optional
        The land they stand in, e.g. ``The Great Library``.
    prosperity : float, optional
        Their village's reviewed fraction, for keepers and townsfolk.
    counts : dict, optional
        World room-state tally, for situation colour.

    Returns
    -------
    Persona or None
        ``None`` for things that should never be model-voiced: beasts and
        animals do not talk, and the scripted waking scene (the elder, the
        dim hound) stays authored so the opening cannot drift.
    """
    if npc.kind in ("beast", "animal", "lumi") or npc.role in ("elder", "lumi"):
        return None

    tone = ""
    if prosperity is not None:
        tone = (
            "Their village is well tended and mostly lit."
            if prosperity > 0.4
            else "Their village is half dark; most houses have no keeper."
        )
    where = f"They stand in {land_title}." if land_title else ""
    dark = ""
    if counts:
        dark = (f"Across the world, {counts.get('wild', 0)} rooms are dark, "
                f"{counts.get('settled', 0)} are kept lit.")

    if npc.role.startswith("emissary:"):
        order = ORDERS.get(npc.role.split(":", 1)[1], {})
        backstory = (
            f"An emissary of {order.get('name', 'an order')}. "
            f"Creed: {order.get('creed', '')} "
            f"They believe: {order.get('belief', '')} "
            f"They want {order.get('wants', 'the work done')}. "
            "They are recruiting Iris and genuinely believe their doctrine is "
            "the one that saves the world."
        )
    elif npc.role == "healer":
        backstory = (
            "The recovery warden of this village. They keep the glowing pad "
            "just inside the gate where spent light comes back — recovery "
            "after bleaching is their whole craft, and they have seen too "
            "many probes walk into the wilds already dim."
        )
    elif npc.kind == "villager":
        backstory = (
            f"The keeper of the page '{npc.name}'. They read it end to end, "
            "vouched for every line of it, and now live beside it; its lamp "
            "burns because they came. They are quietly proud of that and "
            "worry about the dark houses around theirs."
        )
    elif npc.kind == "townsfolk":
        backstory = (
            f"A villager known as {npc.name}. Their own words about their "
            f"life: \"{npc.line}\" They are not a keeper — just someone who "
            "lives here, with work of their own and opinions about the dark."
        )
    else:
        return None

    situation = " ".join(part for part in (
        "Iris has stopped to talk to them.", where, tone, dark) if part)
    return Persona(
        key=f"{npc.kind}:{npc.role or npc.name}:{npc.address or npc.name}",
        name=npc.name,
        backstory=backstory,
        situation=situation,
    )


def parse(raw: str) -> tuple[str, ...] | None:
    """Gate a model reply into usable dialogue lines.

    Parameters
    ----------
    raw : str
        Whatever the model returned.

    Returns
    -------
    tuple of str or None
        Two to four clean lines, or ``None`` when the reply fails the gate —
        in which case the authored lines stand.
    """
    body = raw.strip()
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        entries = json.loads(body[start:end + 1])
    except ValueError:
        return None
    if not isinstance(entries, list):
        return None
    lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, str):
            return None
        line = " ".join(entry.split())
        if not line or len(line) > 200 or line.startswith(("*", "(", "[")):
            return None
        lines.append(line)
    if not 2 <= len(lines) <= 4:
        return None
    return tuple(lines)


class DialogueDirector:
    """Fetches, gates and caches character voices off the frame loop.

    Parameters
    ----------
    client : object, optional
        Something with ``complete(messages)``. Omitted builds one from the
        application's stored AI provider settings on first use.
    cache_dir : pathlib.Path, optional
        Where voices persist. Tests pass a temporary directory.
    """

    def __init__(self, client=None, cache_dir: pathlib.Path | None = None) -> None:
        self._client = client
        self._client_built = client is not None
        self.cache_dir = cache_dir or CACHE_DIR
        self._memory: dict[str, tuple[str, ...]] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self.rejected = 0

    def _make_client(self):
        """Build the model client once, or settle on ``None``.

        Returns
        -------
        object or None
            ``None`` when no provider is configured, which is not an error.
        """
        if not self._client_built:
            self._client_built = True
            try:
                from chisurf.core.agent.llm import LLMClient, LLMSettings

                settings = LLMSettings.from_provider()
                settings.validate()
                self._client = LLMClient(settings)
            except Exception:
                self._client = None
        return self._client

    def _cache_path(self, persona: Persona) -> pathlib.Path:
        return self.cache_dir / f"{persona.cache_token}.json"

    def lines_for(self, persona: Persona) -> tuple[str, ...] | None:
        """Return the character's fetched voice, if it is ready.

        Never blocks. A miss starts a background fetch and returns ``None``;
        the caller speaks the authored lines this time, and the voice is
        there for the next visit.

        Parameters
        ----------
        persona : Persona
            Who wants voicing.

        Returns
        -------
        tuple of str or None
            Gated dialogue lines, or ``None`` while nothing is ready.
        """
        with self._lock:
            ready = self._memory.get(persona.cache_token)
        if ready is not None:
            return ready

        stored = self._read_cache(persona)
        if stored is not None:
            with self._lock:
                self._memory[persona.cache_token] = stored
            return stored

        with self._lock:
            if persona.cache_token in self._pending:
                return None
            self._pending.add(persona.cache_token)
        threading.Thread(target=self._fetch, args=(persona,), daemon=True).start()
        return None

    def fetch_now(self, persona: Persona) -> tuple[str, ...] | None:
        """Fetch synchronously — the testable core of :meth:`lines_for`.

        Parameters
        ----------
        persona : Persona
            Who wants voicing.

        Returns
        -------
        tuple of str or None
            Gated lines, or ``None`` on no client, transport failure, or a
            reply the gate refused.
        """
        client = self._make_client()
        if client is None:
            return None
        prompt = PROMPT.format(
            world=WORLD_BRIEF, name=persona.name,
            backstory=persona.backstory, situation=persona.situation,
        )
        try:
            response = client.complete([{"role": "user", "content": prompt}])
        except Exception:
            return None
        lines = parse(getattr(response, "text", None) or "")
        if lines is None:
            self.rejected += 1
            return None
        self._write_cache(persona, lines)
        with self._lock:
            self._memory[persona.cache_token] = lines
        return lines

    def _fetch(self, persona: Persona) -> None:
        """Background half of :meth:`lines_for`."""
        try:
            self.fetch_now(persona)
        finally:
            with self._lock:
                self._pending.discard(persona.cache_token)

    def _read_cache(self, persona: Persona) -> tuple[str, ...] | None:
        try:
            entries = json.loads(self._cache_path(persona).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (isinstance(entries, list)
                and 2 <= len(entries) <= 4
                and all(isinstance(entry, str) for entry in entries)):
            return tuple(entries)
        return None

    def _write_cache(self, persona: Persona, lines: tuple[str, ...]) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(persona).write_text(
                json.dumps(list(lines), indent=2), encoding="utf-8"
            )
        except OSError:
            # A cache that cannot be written is a slower voice, not a mute one.
            pass
