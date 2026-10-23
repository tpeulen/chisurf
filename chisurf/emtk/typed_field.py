"""A number field for emtk apps.

Whole numbers and floats are typed the same way: an ``input_text`` whose in-progress
text lives in a caller-owned *buffers* dict (a frame never wipes the caret's text)
and that commits on Enter or a click elsewhere, parsed and clamped. A whole-number
field refuses a fraction rather than rounding what the user did not type.

The field acts as a spinbox -- clamped entry, a step -- so it is drawn as one:
up/down arrows beside the text, and the arrow keys step the focused field.
The stepping itself is pyqtgraph's (:func:`emtk.im_widgets.spin_step_by`).
"""

from __future__ import annotations

from emtk import im
from emtk.im_core import get_current_context
from emtk.i18n import tr
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_RETURN, KEY_UP


def parse_number(text, integer=True, minimum=None, maximum=None):
    """*text* as an int (``integer``) or float, clamped to ``[minimum, maximum]``.

    Raises ``ValueError`` for text that is not a number, and for a fractional value where an integer is required
    (rounding ``1.5`` silently would store a value the user did not type).
    """
    stripped = str(text).strip()
    if integer:
        try:
            value = int(stripped)
        except ValueError:
            number = float(stripped)
            if not number.is_integer():
                raise ValueError(f"{stripped!r} is not a whole number") from None
            value = int(number)
    else:
        value = float(stripped)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def typed_number_field(
    key, value, buffers, integer=True, minimum=None, maximum=None, label="", description=""
):
    """Draw the field for *value*; return ``(committed, error)``.

    ``committed`` is the parsed, clamped number when the value moved this frame -- the
    user pressed Enter or clicked away after typing, clicked one of the up/down
    arrows, or stepped the focused field with the arrow keys -- else ``None``.
    ``error`` is the message for committed text that is not a number of the
    field's kind -- a whole-number field refuses a fraction -- and the value is
    then left unchanged. *key* is the field's ImGui id and the key of its
    in-progress text in *buffers*. *label*, when given, is drawn beside the
    field. *description* supplies translated domain help; otherwise the tooltip
    explains how the field is edited and its bounds.
    """
    kind = tr("whole number") if integer else tr("number")
    flags = int(im.InputTextFlags.ENTER_RETURNS_TRUE) | int(im.InputTextFlags.AUTO_SELECT_ALL)
    shown = buffers.get(key, format(value, "d" if integer else "g"))
    # Reserve the row's end for the two step arrows, so the text field and the
    # arrows share one row and the label keeps its place.
    avail, _ = im.get_content_region_avail()
    frame = im.get_frame_height()
    im.set_next_item_width(max(avail - 2.0 * frame - 8.0, 40.0))
    entered, typed = im.input_text(str(label) + "##" + str(key), shown, "", flags)
    input_rect = im.get_item_rect()
    input_hovered = im.is_item_hovered()
    input_id = im.get_item_id()
    tooltip = _number_tooltip(
        description,
        tr(f"Enter a {kind}. Press Enter or click elsewhere to commit."),
        minimum, maximum,
    )
    im.set_item_tooltip(tooltip)
    ctx = get_current_context()
    # A click on an arrow, or the arrow keys on the focused field, steps by
    # pyqtgraph's SpinBox logic: a hundredth of the value's own magnitude for
    # a float, a whole 1 for an integer, clamped to the bounds.
    from emtk.im_widgets import spin_step_by

    im.same_line(0.0, 4.0)
    up = im.arrow_button(f"step up##{key}", int(im.Dir.UP))
    im.same_line(0.0, 4.0)
    down = im.arrow_button(f"step down##{key}", int(im.Dir.DOWN))
    if ctx.io.key in (KEY_RETURN, KEY_ENTER):
        # Return is the text edit's commit key; the navigation layer would
        # also press whichever arrow holds its focus, and Enter must never step.
        up = down = False
    # The field's rect stays the text field's -- what a caller records with
    # ``get_item_rect`` after this returns is where the number is typed, with
    # the arrows beside it, not the last arrow drawn.
    ctx.item_add(input_rect, input_id)
    if typed != shown:
        buffers[key] = typed
    # Enter commits what was typed before anything steps: the one key belongs
    # to the text, not to an arrow.
    if entered and key in buffers:
        text = buffers.pop(key)
        try:
            return parse_number(text, integer, minimum, maximum), ""
        except ValueError:
            return None, f"{text!r} is not a {kind}"
    steps = 0
    if up:
        steps = 1
    elif down:
        steps = -1
    else:
        focused = (
            ctx.state(("focus",)).get("id") == input_id
            or ctx.is_nav_focused(input_id)
        )
        if focused and ctx.io.key in (KEY_UP, KEY_DOWN):
            steps = 1 if ctx.io.key == KEY_UP else -1
            pressed = ctx.io.key
            ctx.io.key = 0
            ctx.io.key_events[:] = [
                event for event in ctx.io.key_events if event[0] != pressed
            ]
            ctx.request_frame()
    if steps:
        # A step replaces text in progress: the field shows the stepped value.
        buffers.pop(key, None)
        candidate = spin_step_by(
            value, steps, integer=integer, bounds=(minimum, maximum)
        )
        if candidate != value:
            return candidate, ""
        return None, ""
    clicked_away = (
        im.get_io().mouse_clicked[0]
        and not input_hovered
        and not up
        and not down
    )
    if key not in buffers or not (entered or clicked_away):
        return None, ""
    text = buffers.pop(key)
    try:
        return parse_number(text, integer, minimum, maximum), ""
    except ValueError:
        return None, f"{text!r} is not a {kind}"


def _number_tooltip(description, how, minimum, maximum):
    """The field's tooltip: *description*, else *how*, plus the clamp bounds."""
    if description and str(description).strip():
        return tr(str(description))
    tooltip = how
    if minimum is not None and maximum is not None:
        tooltip += " " + tr("Values are clamped between {minimum} and {maximum}.").format(
            minimum=minimum, maximum=maximum
        )
    elif minimum is not None:
        tooltip += " " + tr("Values below {minimum} are clamped to {minimum}.").format(
            minimum=minimum
        )
    elif maximum is not None:
        tooltip += " " + tr("Values above {maximum} are clamped to {maximum}.").format(
            maximum=maximum
        )
    return tooltip
