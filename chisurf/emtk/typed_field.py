"""A keyboard-editable number field for emtk apps.

``im.input_int`` / ``im.input_float`` are drag widgets: they never take the keyboard, so a user cannot type a value.
This field is an ``input_text`` whose in-progress text lives in a caller-owned *buffers* dict (a frame never wipes
the caret's text) and that commits on Enter or a click elsewhere, parsed and clamped.
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

    ``committed`` is the parsed, clamped number when the user pressed Enter or clicked away after typing, else
    ``None``. ``error`` is the message for committed text that is not a number (the value is then left unchanged).
    *key* is the field's ImGui id and its key in *buffers*; *label*, when given, is drawn beside the field.
    *description* supplies translated domain help; otherwise the tooltip explains numeric entry and bounds.
    """
    flags = int(im.InputTextFlags.ENTER_RETURNS_TRUE) | int(im.InputTextFlags.AUTO_SELECT_ALL)
    shown = buffers.get(key, str(value) if integer else format(value, "g"))
    entered, typed = im.input_text(str(label) + "##" + str(key), shown, "", flags)
    if description and str(description).strip():
        tooltip = tr(str(description))
    else:
        tooltip = (
            tr("Enter a whole number. Press Enter or click elsewhere to commit.")
            if integer
            else tr("Enter a number. Press Enter or click elsewhere to commit.")
        )
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
    im.set_item_tooltip(tooltip)
    if typed != shown:
        buffers[key] = typed
    clicked_away = im.get_io().mouse_clicked[0] and not im.is_item_hovered()
    if key not in buffers or not (entered or clicked_away):
        return None, ""
    text = buffers.pop(key)
    try:
        return parse_number(text, integer, minimum, maximum), ""
    except ValueError:
        return None, f"{text!r} is not {'a whole number' if integer else 'a number'}"
