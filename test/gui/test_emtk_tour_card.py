"""The guided-tour card must not hide the control a step points at, and the user can move it."""

from __future__ import annotations

import itertools

import pytest

from chisurf.emtk.help_guide import EmTkGuidedTour, place_tour_card

VIEW = (1200.0, 800.0)
CARD = (480.0, 195.0)


def _overlaps(card, target):
    cx, cy = card
    tx, ty, tw, th = target
    return not (cx + CARD[0] <= tx or cx >= tx + tw or cy + CARD[1] <= ty or cy >= ty + th)


@pytest.mark.parametrize(
    "tx,ty", list(itertools.product((10, 300, 600, 1000), (10, 300, 600, 740)))
)
def test_the_card_never_covers_its_target(tx, ty):
    target = (tx, ty, 120.0, 26.0)
    assert not _overlaps(place_tour_card(target, *VIEW, *CARD), target)


def test_a_wide_target_still_gets_an_uncovered_card():
    target = (0.0, 380.0, 1200.0, 40.0)  # a toolbar across the whole width
    assert not _overlaps(place_tour_card(target, *VIEW, *CARD), target)


def test_without_a_target_the_card_leaves_the_middle_free():
    x, y = place_tour_card(None, *VIEW, *CARD)
    assert not _overlaps((x, y), (480.0, 300.0, 240.0, 200.0))


def _drawn_tour(rects):
    from emtk import im
    from emtk.app import ImApp
    from emtk.testing import RecordingPainter

    tour = EmTkGuidedTour(
        [{"title": "t", "text": "x", "target": "add"}], get_target_rect=lambda k: rects.get(k)
    )
    tour.start()
    app = ImApp(lambda: (im.begin("W", (0, 0, 1200, 800)), tour.draw(1200, 800), im.end()))
    return tour, app, RecordingPainter


def test_the_user_can_drag_the_card_and_it_stays_there():
    tour, app, Painter = _drawn_tour({"add": (20.0, 20.0, 100.0, 26.0)})
    for _ in range(3):
        app.draw(Painter(), 0, 0, 1200, 800)
    x0, y0 = place_tour_card((20.0, 20.0, 100.0, 26.0), 1200.0, 800.0, 480.0, 195.0)
    app.hover(x0 + 100, y0 + 10)
    app.draw(Painter(), 0, 0, 1200, 800)
    app.press(x0 + 100, y0 + 10)
    app.draw(Painter(), 0, 0, 1200, 800)
    app.hover(x0 + 100 - 60, y0 + 10 + 90)  # drag by (-60, +90)
    app.draw(Painter(), 0, 0, 1200, 800)
    app.release()
    for _ in range(2):
        app.draw(Painter(), 0, 0, 1200, 800)
    dx, dy = tour.card_offset
    assert (round(dx), round(dy)) == (-60, 90)
