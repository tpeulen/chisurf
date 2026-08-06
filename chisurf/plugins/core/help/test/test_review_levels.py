"""The sign-off ladder: nothing, an agent, a human.

An agent can read a page end to end and correct what it can verify against the
source; it cannot open the application, so it cannot tell whether a screenshot
still matches the interface. That is a real state between "nobody has looked at
this" and "a human vouches for it", and collapsing it into *unreviewed* throws
away the only signal that says which pages still need the **first** pass.

These tests pin the three properties that make the distinction worth having:
an agent's sign-off does not clear the release gate, it never overwrites a
human's, and either level goes stale the moment the page is edited.
"""

import pathlib

import pytest

from chisurf.plugins.core.help.api import review


@pytest.fixture
def tracked_page(tmp_path, monkeypatch):
    """A documentation page inside a temporary tracked directory."""
    docs = tmp_path / "docs"
    manual = docs / "manual"
    manual.mkdir(parents=True)
    page = manual / "page.rst"
    page.write_text("Title\n=====\n\nBody.\n", encoding="utf-8")
    monkeypatch.setattr(review, "docs_root", lambda: docs)
    return page


def test_ladder_is_ordered_weakest_first():
    assert review.REVIEW_LEVELS == (
        review.STATUS_UNREVIEWED,
        review.STATUS_AI_REVIEWED,
        review.STATUS_REVIEWED,
    )
    assert review.STATUS_AI_REVIEWED in review.SIGNED_STATUSES


def test_a_fresh_page_is_unreviewed(tracked_page):
    assert review.status_of(tracked_page).status == review.STATUS_UNREVIEWED


def test_ai_review_is_recorded_with_its_kind(tracked_page):
    assert review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    status = review.status_of(tracked_page)
    assert status.status == review.STATUS_AI_REVIEWED
    assert status.reviewer_kind == "ai"
    assert status.date


def test_ai_review_does_not_clear_the_release_gate(tracked_page):
    review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    report = review.scan()
    assert len(report.ai_reviewed) == 1
    assert report.blocking, "an agent's read must not ship as a human's review"
    assert not report.ok
    assert "AI-reviewed" in report.summary()


def test_a_human_sign_off_replaces_an_agents(tracked_page):
    review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    review.set_status(tracked_page, review.STATUS_REVIEWED, "a-person")
    status = review.status_of(tracked_page)
    assert status.status == review.STATUS_REVIEWED
    assert status.reviewer_kind == "human"
    assert review.scan().ok


def test_an_agent_never_overwrites_a_human(tracked_page):
    """A sweep over the whole manual must not erase what somebody checked."""
    review.set_status(tracked_page, review.STATUS_REVIEWED, "a-person")
    assert review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    status = review.status_of(tracked_page)
    assert status.status == review.STATUS_REVIEWED
    assert status.reviewer == "a-person"


def test_editing_a_page_makes_either_level_stale(tracked_page):
    for level in (review.STATUS_AI_REVIEWED, review.STATUS_REVIEWED):
        review.set_status(tracked_page, review.STATUS_UNREVIEWED)
        review.set_status(tracked_page, level, "somebody")
        assert review.status_of(tracked_page).status == level
        tracked_page.write_text(
            tracked_page.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8"
        )
        status = review.status_of(tracked_page)
        assert status.status == review.STATUS_STALE
        # And it remembers what it was, so the reader knows what expired.
        assert status.previous_status == level


def test_a_stale_agent_review_can_be_renewed(tracked_page):
    review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    tracked_page.write_text("Title\n=====\n\nEdited.\n", encoding="utf-8")
    assert review.status_of(tracked_page).status == review.STATUS_STALE
    review.set_status(tracked_page, review.STATUS_AI_REVIEWED, "agent")
    assert review.status_of(tracked_page).status == review.STATUS_AI_REVIEWED


def test_registries_written_before_the_ai_level_still_load(tracked_page):
    """An old record has no ``reviewer_kind``; it was a human's."""
    import json

    directory = tracked_page.parent
    (directory / review.REGISTRY_NAME).write_text(
        json.dumps(
            {
                "page.rst": {
                    "status": "reviewed",
                    "reviewer": "a-person",
                    "date": "2026-01-01",
                    "sha256": review.content_hash(
                        tracked_page.read_text(encoding="utf-8")
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    status = review.status_of(tracked_page)
    assert status.status == review.STATUS_REVIEWED
    assert status.reviewer_kind == "human"


def test_the_shipped_manual_records_its_ai_review():
    """The pass made over the manual is recorded, not merely described."""
    report = review.scan()
    if not report.pages:
        pytest.skip("no manual in this checkout")
    assert not report.unreviewed, [p.rel_path for p in report.unreviewed]
    assert not report.stale, [p.rel_path for p in report.stale]
    # And it is still honest about needing a human.
    assert not report.ok
