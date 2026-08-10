"""The challenge a page puts to you, and the rule that keeps it honest.

This is the half of the encounter that touches the documentation. Beating the
guardian is spectroscopy; **clearing the room is reading the page**, and the
challenge is what stops that being a rubber stamp.

Two rules hold it together:

* **Every challenge is span-grounded.** A question may only be asked about text
  that is verifiably in the page, and the check is mechanical: the quoted span
  is looked up in the source. A challenge whose span cannot be found is
  discarded rather than shown. That is what a language model gets wrong most
  often here -- confidently quoting something that is not there -- so the
  verification is code, not trust.
* **A challenge is keyed by the page's content hash**, the same ``sha256`` the
  review sidecar already stores. So an encounter is reproducible, testable
  without a model, and **self-invalidating the moment the page changes** -- by
  exactly the rule that already downgrades a stale review.

A provider generates the questions. The one here is deterministic and needs no
model: it blanks a distinctive term out of the page's own prose. It is weaker
than a model's question -- it tests attention rather than understanding -- but
it is grounded by construction, it works offline, and it makes the review bridge
real today instead of after an integration.
"""

from __future__ import annotations

import dataclasses
import random
import re

#: Words too common to be worth blanking, or to serve as a distractor.
STOPWORDS = frozenset("""
a an and are as at be been but by can for from has have how in into is it its
may not of on or that the their then there these this to was were what when
which who will with you your each such using used than more most also if both
""".split())

#: A candidate term: a word of real length, not a number, not markup.
_TERM = re.compile(r"[A-Za-z][A-Za-z\-]{4,}")

#: Lines that are structure rather than prose. List items are skipped too:
#: a bullet is usually a fragment or a citation directive, and blanking a
#: word out of one produces a question about formatting rather than content.
_SKIP_LINE = re.compile(r"^\s*(#|\||```|:::|\.\.|-|\*|>|=|\d+\.)")


@dataclasses.dataclass(frozen=True)
class Challenge:
    """One question about a page.

    Attributes
    ----------
    prompt : str
        The sentence with the term blanked out.
    options : tuple of str
        Answers to choose between, in display order.
    answer : int
        Index of the correct option.
    span : str
        The exact text from the page the question was built from. Verified to
        be present before the challenge is ever shown.
    """

    prompt: str
    options: tuple[str, ...]
    answer: int
    span: str

    def is_correct(self, choice: int) -> bool:
        """Whether a chosen option is the right one.

        Parameters
        ----------
        choice : int
            Index into :attr:`options`.

        Returns
        -------
        bool
            True when correct.
        """
        return choice == self.answer


def _normalise(text: str) -> str:
    """Reduce prose to what a quote should be compared on.

    Markup is removed and whitespace collapsed, on **both** sides of a
    comparison. Doing it to only one side is a silent disaster: the sentences
    this module builds are markup-stripped, so checking them against the raw
    source rejected every question on any page containing an equation or a
    code span -- and the only symptom was a page that asked nothing.

    Parameters
    ----------
    text : str
        Prose or a quoted span.

    Returns
    -------
    str
        Normalised text.
    """
    # Roles, links and images go whole, before the punctuation strip. Removing
    # only the punctuation leaves the role *name* behind as a word, which is
    # how prompts ended up reading "src , _____ E and distance conversions
    # src , ..." -- three stray role names and no sentence.
    stripped = re.sub(r"[{:][a-zA-Z:+._-]+[}:]\s*`[^`]*`", " ", text)
    stripped = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", stripped)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"`[^`]*`", " ", stripped)
    stripped = re.sub(r"https?://\S+", " ", stripped)
    stripped = re.sub(r"[*_\[\]{}<>$]", " ", stripped)
    return " ".join(stripped.split())


def verify_span(span: str, text: str) -> bool:
    """Whether a quoted span really occurs in the page.

    Markup and whitespace are normalised on both sides, because a quote that
    differs only in how a line wrapped -- or in whether an inline equation kept
    its delimiters -- is still the same sentence, and refusing it throws away
    good questions for no gain.

    Parameters
    ----------
    span : str
        The quoted text.
    text : str
        The page source.

    Returns
    -------
    bool
        True when the span is present.
    """
    if not span.strip():
        return False
    return _normalise(span) in _normalise(text)


def _sentences(text: str) -> list[str]:
    """Prose sentences from a page, structure removed.

    Parameters
    ----------
    text : str
        The page source.

    Returns
    -------
    list of str
        Sentences long enough to build a question from.
    """
    lines = [line for line in text.splitlines() if not _SKIP_LINE.match(line)]
    prose = _normalise(" ".join(lines))
    found = []
    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        cleaned = " ".join(sentence.split())
        if not 60 <= len(cleaned) <= 240:
            continue
        if len(_TERM.findall(cleaned)) < 4:
            continue
        if _is_mathy(cleaned) or _is_a_list(cleaned):
            continue
        found.append(cleaned)
    return found


def _is_a_list(sentence: str) -> bool:
    """Whether a "sentence" is really a flattened list of fragments.

    A bullet list joined into prose reads as a run of comma-separated
    fragments. Blanking a word out of one produces a prompt with no grammar for
    the player to reason from, which is a worse question than none. Continuation
    lines of a bullet are indented, so the line-level filter never sees them.

    Parameters
    ----------
    sentence : str
        A candidate sentence.

    Returns
    -------
    bool
        True when it should not be questioned.
    """
    if sentence[:1] in ",;:.-":
        return True
    breaks = sentence.count(",") + sentence.count(";")
    return breaks >= 4 or breaks / max(len(sentence.split()), 1) > 0.18


def _is_mathy(sentence: str) -> bool:
    """Whether a sentence is really a formula.

    Blanking a word out of a rendered equation asks the player to recall
    notation, not to have read anything -- and the prompt comes out as a wall
    of stray LaTeX. Structural line filters do not catch these, because an
    equation is usually written inline inside an ordinary paragraph.

    Parameters
    ----------
    sentence : str
        A candidate sentence.

    Returns
    -------
    bool
        True when it should not be questioned.
    """
    if sentence.count("\\") >= 2:
        return True
    symbols = sum(1 for char in sentence if char in "=+^/|~")
    return symbols >= 3 or symbols / max(len(sentence), 1) > 0.03


def generate(text: str, content_hash: str, count: int = 1) -> list[Challenge]:
    """Build challenges from a page, deterministically.

    Parameters
    ----------
    text : str
        The page source.
    content_hash : str
        The page's content hash. Seeds the generator, so the same page always
        asks the same thing and a changed page asks something new.
    count : int, optional
        How many to build.

    Returns
    -------
    list of Challenge
        May be shorter than ``count``, or empty for a page with too little
        prose -- a page that cannot be questioned is not a failure, it is a
        stub, and the caller decides what to do about it.
    """
    sentences = _sentences(text)
    if not sentences:
        return []

    rng = random.Random(content_hash)
    vocabulary = sorted(
        {
            word.lower()
            for sentence in sentences
            for word in _TERM.findall(sentence)
            if word.lower() not in STOPWORDS
        }
    )
    if len(vocabulary) < 4:
        return []

    challenges: list[Challenge] = []
    for sentence in rng.sample(sentences, min(len(sentences), count * 4)):
        terms = [
            word for word in _TERM.findall(sentence) if word.lower() not in STOPWORDS
        ]
        if not terms:
            continue
        target = max(terms, key=len)
        prompt = re.sub(rf"\b{re.escape(target)}\b", "_____", sentence, count=1)
        if "_____" not in prompt:
            continue

        distractors = [
            word for word in rng.sample(vocabulary, min(len(vocabulary), 12))
            if word.lower() != target.lower()
        ][:3]
        if len(distractors) < 3:
            continue

        options = [target.lower(), *distractors]
        rng.shuffle(options)
        # Grounded by construction -- but verified anyway, because "the span is
        # in the page" is the property that matters and asserting it here is
        # what lets a model-backed provider be dropped in behind the same check.
        if not verify_span(sentence, text):
            continue
        challenges.append(
            Challenge(
                prompt=prompt,
                options=tuple(options),
                answer=options.index(target.lower()),
                span=sentence,
            )
        )
        if len(challenges) >= count:
            break
    return challenges
