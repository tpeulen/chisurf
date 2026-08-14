"""The `sele` row's eye hides what the selection covers.

The report
----------
"Click on eye hide of `sele` in obj list -> unknown object: sele. Action that
should occur -> hide what is covered in sele."

The object list gives every row an eye and emits `disable <name>` for it, and
`disable` looked its argument up as an **object**. `sele` is not one, so the row
a user reaches for most often answered "Unknown object: sele" and did nothing.
It is not a naming slip: hiding a selection is a different operation from
hiding an object, and the row was drawn as though they were the same.

What it does now
----------------
`enable`/`disable` fall through to a **selection** when the name is not an
object, and hide the atoms it covers -- by row visibility rather than by
representation, so it round-trips: a boolean mask restores exactly what was
there, where `hide everything` followed by `show` would have to guess which
representations to bring back.

What this pins
--------------
* the reported click, through the real chrome, with no error;
* that it **toggles** -- the first version hid and then hid again, because the
  row's `enabled` was a constant and the eye read its next action from it;
* that the panel actually re-reads: hiding rows is a visibility change, and
  without bumping `objects_revision` the row kept its old state whatever the
  viewer knew;
* that a word which is neither an object nor a selection still says so.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe


@pytest.fixture(scope="module")
def measured():
    return probe('''
        app = open_app(size=(760, 520))
        errors, messages = [], []
        app.cmd.set_error_callback(errors.append)
        app.cmd.set_message_callback(messages.append)
        app.cmd.do("fetch 148L")
        app.cmd.do("select sele, resi 1-20")
        gui = app.renderer._internal_gui
        app.renderer.draw_frame()

        def hidden():
            entry = app.viewer._objects[app.viewer.get_active_object_id()]
            mask = getattr(entry.state, "hidden_mask", None)
            return 0 if mask is None else int(np.asarray(mask).sum())

        def sele_shown():
            return [r.enabled for r in gui.rows if r.name == "sele"][0]

        def click_eye():
            names = [r.name for r in gui.rows]
            eye = gui._eye_rects[names.index("sele")]
            errors.clear()
            gui.mouse_press(eye.x + eye.w / 2, eye.y + eye.h / 2)
            gui.release()
            app.renderer.draw_frame()

        emit("start", (hidden(), sele_shown()))
        click_eye()
        emit("after_one", (hidden(), sele_shown()))
        emit("errors_on_click", "; ".join(errors) or "none")
        click_eye()
        emit("after_two", (hidden(), sele_shown()))
        click_eye()
        emit("after_three", (hidden(), sele_shown()))

        # The command behind the click, and its neighbours.
        errors.clear()
        messages.clear()
        app.cmd.do("disable resi 30-40")
        emit("expression", (messages[-1] if messages else "") )
        emit("expression_hidden", hidden())
        app.cmd.do("enable resi 30-40")

        errors.clear()
        app.cmd.do("disable notathing")
        emit("nonsense", "; ".join(errors) or "none")
    ''')


def test_clicking_the_eye_hides_the_selection(measured):
    """The report: it used to answer "unknown object: sele" and do nothing."""
    assert measured["errors_on_click"] == "none", measured["errors_on_click"]
    hidden, shown = eval(measured["after_one"])  # noqa: S307 - our own emit
    assert hidden > 0, "clicking the eye hid nothing"
    assert shown is False, "the eye still shows as open over a hidden selection"


def test_the_eye_toggles_rather_than_repeating_itself(measured):
    """The row's state has to come from the viewer, or the next click repeats.

    The first version of this hid, and then hid the same atoms again: the row
    carried a constant `enabled=True`, and the eye reads its next action from
    exactly that.
    """
    start = eval(measured["start"])  # noqa: S307
    one = eval(measured["after_one"])  # noqa: S307
    two = eval(measured["after_two"])  # noqa: S307
    three = eval(measured["after_three"])  # noqa: S307

    assert start == (0, True)
    assert two == start, f"a second click did not restore the atoms: {two}"
    assert three == one, f"the third click did not hide them again: {three}"


def test_it_works_for_any_selection_expression(measured):
    """`sele` is one selection; the fall-through is not special-cased to it."""
    assert "Hid" in measured["expression"], measured["expression"]
    assert int(measured["expression_hidden"]) > 0


def test_a_word_that_is_neither_still_says_so(measured):
    """The fall-through must not turn a typo into silence."""
    assert "Unknown object: notathing" in measured["nonsense"]


def test_the_eye_is_drawn_rather_than_typed():
    """It was the letter `o` and a hyphen; both are legible and say nothing.

    Unicode has an eye -- U+1F441 -- but it is an emoji, so the only fonts
    carrying it are colour ones and the atlas rasterises monochrome masks: it
    comes out blank. Everything else that looks close is a circle. So the
    pictogram is drawn from rectangles, and this pins that it is a *picture*
    with ink in it rather than a character that silently went missing.
    """
    from chimol.renderer.internal_gui import Rect
    from chimol.cmtk.icons import (
        CLOSED_EYE, OPEN_EYE, draw_glyph,
    )

    for name, glyph in (("open", OPEN_EYE), ("closed", CLOSED_EYE)):
        widths = {len(row) for row in glyph}
        assert len(widths) == 1, f"the {name} eye's rows are ragged: {widths}"
        assert any("#" in row for row in glyph), f"the {name} eye has no ink"

    # And it draws inside the cell it is given, at whole-pixel scale.
    drawn: list[tuple] = []

    class Recorder:
        def fill_rect(self, x, y, w, h, colour):
            drawn.append((x, y, w, h))

    cell = Rect(10.0, 20.0, 14.0, 15.0)
    draw_glyph(Recorder(), cell, OPEN_EYE, (255, 255, 255, 255))
    assert drawn, "the eye drew nothing"
    for x, y, w, h in drawn:
        assert x >= cell.x and x + w <= cell.x + cell.w + 1e-6, "wider than its cell"
        assert y >= cell.y and y + h <= cell.y + cell.h + 1e-6, "taller than its cell"
    # Whole pixels: a fractional scale blurs a one-pixel outline into grey.
    assert all(float(h).is_integer() for _x, _y, _w, h in drawn)
