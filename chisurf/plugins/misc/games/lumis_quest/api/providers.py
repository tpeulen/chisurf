"""Where a page's questions come from, and the gate they all pass through.

There are three providers and they are interchangeable, because the property
that matters is not which one wrote the question -- it is that **every question
survives the same grounding check**. A challenge whose quoted span cannot be
found in the page is discarded, whoever produced it.

* :class:`DeterministicProvider` needs no model. It blanks a distinctive term
  out of the page's own prose. It tests attention rather than understanding,
  and it is what ships so the game works offline.
* :class:`AgentProvider` asks the configured language model. It writes better
  questions, and it is also the one that will confidently quote a sentence the
  page does not contain -- which is exactly why the check is code rather than
  trust, and why this module counts what it rejects.
* :class:`RecordedProvider` replays captured responses, so the model-backed
  path is testable with no key, no network and no nondeterminism.

Results are cached under the page's ``sha256``, the same hash the review sidecar
stores, so an encounter is reproducible and **self-invalidates the moment the
page changes**.
"""

from __future__ import annotations

import json
import pathlib
from typing import Protocol

from .challenge import Challenge, generate, verify_span

#: Where generated encounters are cached.
CACHE_DIR = pathlib.Path.home() / ".chisurf" / "lumis_quest_encounters"

#: What the model is asked for. Deliberately small: one JSON array, no prose
#: around it, and an explicit instruction to quote rather than paraphrase --
#: because the span is the only part that can be verified.
PROMPT = """You are setting a reading-comprehension question about a documentation page.

Return ONLY a JSON array of {count} objects, no prose around it. Each object:
  "span":    one sentence copied EXACTLY from the page, verbatim, no paraphrase
  "prompt":  that sentence with one important word replaced by _____
  "options": four single-word answers, one correct, three plausible but wrong
  "answer":  the index (0-3) of the correct option

The span must appear in the page character for character. Do not invent text.

PAGE:
{page}
"""


class ChallengeProvider(Protocol):
    """Anything that can set questions about a page."""

    def generate(self, text: str, content_hash: str, count: int) -> list[Challenge]:
        """Produce challenges for a page.

        Parameters
        ----------
        text : str
            The page source.
        content_hash : str
            The page's content hash.
        count : int
            How many to produce.

        Returns
        -------
        list of Challenge
            May be shorter than asked for.
        """
        ...


class DeterministicProvider:
    """Questions built from the page's own prose, with no model."""

    name = "deterministic"

    def generate(self, text: str, content_hash: str, count: int = 1) -> list[Challenge]:
        """Produce challenges.

        Parameters
        ----------
        text : str
            The page source.
        content_hash : str
            Seeds the generator.
        count : int, optional
            How many.

        Returns
        -------
        list of Challenge
            Grounded by construction.
        """
        return generate(text, content_hash, count=count)


class RecordedProvider:
    """Replays captured model output.

    Parameters
    ----------
    payloads : dict
        Content hash to the raw JSON text a model returned for it.
    """

    name = "recorded"

    def __init__(self, payloads: dict[str, str]) -> None:
        self.payloads = payloads
        self.rejected = 0

    def generate(self, text: str, content_hash: str, count: int = 1) -> list[Challenge]:
        """Replay and re-verify.

        The recorded output goes through the *same* grounding check as a live
        model's, so a fixture cannot smuggle in an ungrounded question and make
        the test pass where production would refuse.

        Parameters
        ----------
        text : str
            The page source.
        content_hash : str
            Which recording to replay.
        count : int, optional
            How many.

        Returns
        -------
        list of Challenge
            Grounded ones only.
        """
        raw = self.payloads.get(content_hash)
        if raw is None:
            return []
        found, rejected = parse(raw, text, count)
        self.rejected += rejected
        return found


class AgentProvider:
    """Questions from the configured language model.

    Parameters
    ----------
    client : object, optional
        Something with ``complete(messages)``. Omitted builds one from the
        application's stored AI provider settings.
    """

    name = "agent"

    def __init__(self, client=None) -> None:
        self._client = client
        self.rejected = 0

    def _make_client(self):
        """Build a client from the stored provider settings.

        Returns
        -------
        object or None
            ``None`` when no provider is configured, which is not an error --
            the caller falls back to the deterministic provider.
        """
        if self._client is not None:
            return self._client
        try:
            from chisurf.core.agent.llm import LLMClient, LLMSettings

            settings = LLMSettings.from_provider()
            settings.validate()
            self._client = LLMClient(settings)
        except Exception:
            self._client = None
        return self._client

    def generate(self, text: str, content_hash: str, count: int = 1) -> list[Challenge]:
        """Ask the model, then verify every span it quoted.

        Parameters
        ----------
        text : str
            The page source.
        content_hash : str
            The page's content hash.
        count : int, optional
            How many.

        Returns
        -------
        list of Challenge
            Only the grounded ones. An unconfigured provider, a transport
            failure or a malformed answer all yield an empty list rather than
            raising: the caller has a working fallback, and a game that refuses
            to run because a model is down is worse than one asking a simpler
            question.
        """
        client = self._make_client()
        if client is None:
            return []
        prompt = PROMPT.format(count=count, page=text[:12000])
        try:
            response = client.complete([{"role": "user", "content": prompt}])
        except Exception:
            return []
        raw = getattr(response, "text", None) or ""
        found, rejected = parse(raw, text, count)
        self.rejected += rejected
        return found


def parse(raw: str, text: str, count: int) -> tuple[list[Challenge], int]:
    """Turn a model's answer into verified challenges.

    Parameters
    ----------
    raw : str
        Whatever the model returned.
    text : str
        The page, to check quoted spans against.
    count : int
        How many to keep.

    Returns
    -------
    tuple
        ``(challenges, rejected)``. ``rejected`` counts entries thrown away for
        failing the grounding check -- worth surfacing, because a provider that
        mostly invents its quotes is a provider to stop using.
    """
    body = raw.strip()
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end <= start:
        return [], 0
    try:
        entries = json.loads(body[start: end + 1])
    except ValueError:
        return [], 0
    if not isinstance(entries, list):
        return [], 0

    found: list[Challenge] = []
    rejected = 0
    for entry in entries:
        if not isinstance(entry, dict):
            rejected += 1
            continue
        span = str(entry.get("span", ""))
        prompt = str(entry.get("prompt", ""))
        options = entry.get("options")
        answer = entry.get("answer")
        if (
            not isinstance(options, list)
            or len(options) != 4
            or not isinstance(answer, int)
            or not 0 <= answer < 4
            or "_____" not in prompt
        ):
            rejected += 1
            continue
        # The whole reason this module exists. A model will quote a sentence the
        # page does not contain, confidently, and nothing downstream can tell.
        if not verify_span(span, text):
            rejected += 1
            continue
        found.append(
            Challenge(
                prompt=prompt,
                options=tuple(str(option) for option in options),
                answer=answer,
                span=span,
            )
        )
        if len(found) >= count:
            break
    return found, rejected


def cached(content_hash: str, cache_dir: pathlib.Path | None = None) -> list[Challenge] | None:
    """Read a cached encounter.

    Parameters
    ----------
    content_hash : str
        The page's content hash.
    cache_dir : pathlib.Path, optional
        Where encounters live.

    Returns
    -------
    list of Challenge or None
        ``None`` when nothing is cached for this hash.
    """
    path = (cache_dir or CACHE_DIR) / f"{content_hash}.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return [
            Challenge(
                prompt=entry["prompt"],
                options=tuple(entry["options"]),
                answer=int(entry["answer"]),
                span=entry["span"],
            )
            for entry in entries
        ]
    except (KeyError, TypeError, ValueError):
        return None


def store(content_hash: str, challenges: list[Challenge],
          cache_dir: pathlib.Path | None = None) -> None:
    """Cache an encounter under its page's hash.

    Parameters
    ----------
    content_hash : str
        The page's content hash.
    challenges : list of Challenge
        What to store.
    cache_dir : pathlib.Path, optional
        Where encounters live.
    """
    if not challenges or not content_hash:
        return
    directory = cache_dir or CACHE_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{content_hash}.json").write_text(
            json.dumps(
                [
                    {
                        "prompt": c.prompt,
                        "options": list(c.options),
                        "answer": c.answer,
                        "span": c.span,
                    }
                    for c in challenges
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        # A cache that cannot be written is a slower game, not a broken one.
        pass


def best_available(prefer_model: bool = True) -> ChallengeProvider:
    """The provider to use, given what is configured.

    Parameters
    ----------
    prefer_model : bool, optional
        Whether to try the model first.

    Returns
    -------
    ChallengeProvider
        The agent provider when one is configured, otherwise the deterministic
        one. The game never refuses to run for want of a model.
    """
    if prefer_model:
        agent = AgentProvider()
        if agent._make_client() is not None:
            return agent
    return DeterministicProvider()
