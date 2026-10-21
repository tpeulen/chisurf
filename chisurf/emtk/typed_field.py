"""A number field for emtk apps.

Integer fields are ``im.input_int`` spinboxes: drag them or press Up/Down (hold the
modifier for the fast step) to change the value, which commits as soon as it moves.
Float fields keep a typed ``input_text`` whose in-progress text lives in a
caller-owned *buffers* dict (a frame never wipes the caret's text) and that commits
on Enter or a click elsewhere, parsed and clamped.
"""

from __future__ import annotations

from emtk import im
from emtk.i18n import tr


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

    ``committed`` is the parsed, clamped number when the value moved this frame (an
    integer field: a drag or an Up/Down arrow; a float field: the user pressed Enter
    or clicked away after typing), else ``None``. ``error`` is the message for
    committed text that is not a number (the value is then left unchanged); an
    integer field never errors, the spinbox only ever holds whole numbers.
    *key* is the field's ImGui id; for a float field it is also the key in *buffers*.
    *label*, when given, is drawn beside the field. *description* supplies translated
    domain help; otherwise the tooltip explains how the field is edited and its bounds.
    """
    if integer:
        return _integer_field(key, value, minimum, maximum, label, description)
    flags = int(im.InputTextFlags.ENTER_RETURNS_TRUE) | int(im.InputTextFlags.AUTO_SELECT_ALL)
    shown = buffers.get(key, format(value, "g"))
    entered, typed = im.input_text(str(label) + "##" + str(key), shown, "", flags)
    tooltip = _number_tooltip(
        description, tr("Enter a number. Press Enter or click elsewhere to commit."),
        minimum, maximum,
    )
    im.set_item_tooltip(tooltip)
    if typed != shown:
        buffers[key] = typed
    clicked_away = im.get_io().mouse_clicked[0] and not im.is_item_hovered()
    if key not in buffers or not (entered or clicked_away):
        return None, ""
    text = buffers.pop(key)
    try:
        return parse_number(text, False, minimum, maximum), ""
    except ValueError:
        return None, f"{text!r} is not a number"


def _integer_field(key, value, minimum, maximum, label, description):
    """The integer spinbox: drag, or Up/Down arrows step by one and commit at once.

    ``im.drag_int`` (not ``input_int``, whose arrow step rides the float path) keeps
    the field plain -- the -/+ steppers would crowd the half-width paired fields this
    helper draws -- while the keyboard arrows and the bounds still work.
    """
    current = int(value)
    changed, stepped = im.drag_int(
        str(label) + "##" + str(key), current, 1.0, minimum, maximum, "%d"
    )
    im.set_item_tooltip(
        _number_tooltip(
            description,
            tr("Drag, or press Up/Down to step by one."),
            minimum, maximum,
        )
    )
    if not changed:
        return None, ""
    new = _clamp(int(stepped), minimum, maximum)
    return (new, "") if new != _clamp(current, minimum, maximum) else (None, "")


def _clamp(value, minimum, maximum):
    """*value* clamped to ``[minimum, maximum]`` (either side may be ``None``)."""
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


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
