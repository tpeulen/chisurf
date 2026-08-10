"""Challenges are grounded in the page, and deterministic."""

from __future__ import annotations

from chisurf.plugins.misc.games.lumis_quest.api import challenge

PAGE = """
# Anisotropy

The fundamental anisotropy of a fluorophore describes how much polarisation
memory survives the excited-state lifetime, and it is bounded above by two
fifths for a single absorbing transition dipole.

Rotational correlation time governs how quickly that memory is lost, so a
larger molecule tumbling slowly retains polarisation for longer than a small
one in the same solvent at the same temperature.

- Key literature: cite the textbook treatment here.
"""


def test_a_challenge_is_built_from_the_page():
    """The question, its options, and the answer among them."""
    made = challenge.generate(PAGE, "seed-a", count=1)
    assert made
    question = made[0]
    assert "_____" in question.prompt
    assert len(question.options) == 4
    assert question.is_correct(question.answer)
    assert not question.is_correct((question.answer + 1) % 4)


def test_the_span_is_verifiably_in_the_page():
    """The property that stops a generator inventing a quote."""
    for question in challenge.generate(PAGE, "seed-b", count=2):
        assert challenge.verify_span(question.span, PAGE)


def test_verification_survives_markup_but_rejects_invention():
    """Regression: normalising only one side rejected everything.

    The sentences this module builds are markup-stripped, so comparing them
    against the raw source failed on any page with an equation or a code span --
    and the only symptom was a page that asked nothing at all.
    """
    source = "The Forster radius $R_0$ sets the *scale* of the `transfer` rate."
    assert challenge.verify_span("The Forster radius R 0 sets the scale of the rate.", source)
    assert not challenge.verify_span("The Forster radius is exactly nine nanometres.", source)
    assert not challenge.verify_span("", source)


def test_the_same_page_always_asks_the_same_thing():
    """Keyed by content hash, so an encounter is reproducible."""
    first = challenge.generate(PAGE, "seed-c", count=2)
    second = challenge.generate(PAGE, "seed-c", count=2)
    assert [q.prompt for q in first] == [q.prompt for q in second]
    assert [q.options for q in first] == [q.options for q in second]


def test_a_changed_page_asks_something_new():
    """A different hash is a different encounter."""
    first = challenge.generate(PAGE, "hash-one", count=1)
    second = challenge.generate(PAGE, "hash-two", count=1)
    assert first and second
    assert first[0].prompt != second[0].prompt or first[0].options != second[0].options


def test_a_page_with_no_prose_asks_nothing():
    """A stub is not a failure; the caller decides what to do about it."""
    assert challenge.generate("# Title\n\n| a | b |\n", "seed-d") == []
    assert challenge.generate("", "seed-e") == []


def test_structure_is_not_questioned():
    """Blanking a word out of a bullet asks about formatting, not content."""
    for question in challenge.generate(PAGE, "seed-f", count=4):
        assert "Key literature" not in question.span


def test_the_answer_is_not_a_stopword():
    """Blanking out `the` is not a question about anything."""
    for question in challenge.generate(PAGE, "seed-g", count=4):
        assert question.options[question.answer] not in challenge.STOPWORDS
