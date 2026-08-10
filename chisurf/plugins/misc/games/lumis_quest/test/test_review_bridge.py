"""The one place the game writes to the documentation, and its guards."""

from __future__ import annotations

import pytest

from chisurf.plugins.core.help.api import review
from chisurf.plugins.misc.games.lumis_quest.api import review_bridge

PAGE = """
# Crosstalk

Spectral crosstalk describes the fraction of donor emission that reaches the
acceptor detection channel, and correcting for it is a prerequisite for any
quantitative efficiency measurement in a two-colour experiment.

The correction factor is measured on a donor-only sample, because that is the
one condition in which every photon arriving in the acceptor channel must have
come from the donor rather than from direct excitation.
"""


@pytest.fixture
def page(tmp_path, monkeypatch):
    """A tracked page in a temporary docs tree.

    Returns
    -------
    pathlib.Path
        The page. The review system is pointed at the temporary tree, so no
        test ever writes to the repository's own sidecars.
    """
    docs = tmp_path / "docs" / "concepts"
    docs.mkdir(parents=True)
    target = docs / "crosstalk.md"
    target.write_text(PAGE, encoding="utf-8")
    monkeypatch.setattr(review, "docs_root", lambda: tmp_path / "docs")
    monkeypatch.setattr(review, "tracked_dirs", lambda: [docs])
    return target


def _answered(target, correct=True):
    """Build a challenge for a page and pick an answer.

    Returns
    -------
    tuple
        ``(challenge, choice, content_hash)``.
    """
    challenges, content_hash = review_bridge.challenge_for(target)
    assert challenges, "this fixture page must be questionable"
    question = challenges[0]
    choice = question.answer if correct else (question.answer + 1) % len(question.options)
    return question, choice, content_hash


def test_training_never_signs_anything_off(page):
    """Learning fluorescence is not reviewing a page."""
    question, choice, content_hash = _answered(page)
    verdict = review_bridge.clear_page(
        page, review_bridge.TRAINING, question, choice, content_hash
    )
    assert not verdict.signed_off and verdict.reason == "training"
    assert review.status_of(page).status != review.STATUS_REVIEWED


def test_expert_signs_off_a_correct_answer(page):
    """And records it as a human, not an agent."""
    question, choice, content_hash = _answered(page)
    verdict = review_bridge.clear_page(
        page, review_bridge.EXPERT, question, choice, content_hash, reviewer="tester"
    )
    assert verdict.signed_off and verdict.reason == "signed"

    status = review.status_of(page)
    assert status.status == review.STATUS_REVIEWED
    assert status.reviewer_kind == "human"
    assert status.reviewer == "tester"


def test_a_wrong_answer_signs_nothing(page):
    """Clearing a room is not the same as having read the page."""
    question, choice, content_hash = _answered(page, correct=False)
    verdict = review_bridge.clear_page(
        page, review_bridge.EXPERT, question, choice, content_hash
    )
    assert not verdict.signed_off and verdict.reason == "wrong"
    assert review.status_of(page).status != review.STATUS_REVIEWED


def test_no_challenge_is_never_a_sign_off(page):
    """A rubber stamp is exactly the failure this guards against."""
    _, _, content_hash = _answered(page)
    verdict = review_bridge.clear_page(
        page, review_bridge.EXPERT, None, None, content_hash
    )
    assert not verdict.signed_off and verdict.reason == "wrong"


def test_a_page_edited_mid_encounter_is_refused(page):
    """Signing off text nobody has now read is the stale approval the review
    system already guards against."""
    question, choice, content_hash = _answered(page)
    page.write_text(PAGE + "\n\nAn extra paragraph nobody has read.\n", encoding="utf-8")

    verdict = review_bridge.clear_page(
        page, review_bridge.EXPERT, question, choice, content_hash
    )
    assert not verdict.signed_off and verdict.reason == "stale"
    assert review.status_of(page).status != review.STATUS_REVIEWED


def test_an_untracked_page_is_refused(tmp_path, monkeypatch):
    """The game does not invent sidecars outside the reviewed directories."""
    docs = tmp_path / "docs" / "concepts"
    docs.mkdir(parents=True)
    stray = tmp_path / "elsewhere.md"
    stray.write_text(PAGE, encoding="utf-8")
    monkeypatch.setattr(review, "docs_root", lambda: tmp_path / "docs")
    monkeypatch.setattr(review, "tracked_dirs", lambda: [docs])

    challenges, content_hash = review_bridge.challenge_for(stray)
    verdict = review_bridge.clear_page(
        stray, review_bridge.EXPERT, challenges[0], challenges[0].answer, content_hash
    )
    assert not verdict.signed_off and verdict.reason == "untracked"


def test_an_unreadable_page_degrades(tmp_path):
    """A missing file is reported, not raised."""
    missing = tmp_path / "gone.md"
    challenges, content_hash = review_bridge.challenge_for(missing)
    assert challenges == [] and content_hash == ""
