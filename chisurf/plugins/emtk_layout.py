"""Layout helpers the emtk tool windows share: capped field widths, one label column, wrapped button rows.

AutoForm's grid gives every row of a column the same width and one label column per run of fields, so a form
whose fields differ (a stride beside a file name beside a choice) stretches the short ones across the whole
window and starts each group's fields at its own x. The helpers here work on the spec *after* it is loaded
(the ``*.view.json`` files stay as the Qt AutoForm reads them):

- :func:`cap_widths` declares a ``width`` for number, text and choice fields;
- :func:`group_by_width` puts each run of same-kind fields in a grid of its own so those widths hold;
- :class:`LabelColumn` pads the captions of every field to the widest one, and gives the hand-drawn rows
  (file rows, matrices) the same label x;
- :func:`button_row` draws actions in one row that wraps instead of stacking one button per line;
- :func:`icon_label` sets a pictogram clear of its caption.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Sequence

from emtk import im

#: Widest a number field / a choice / a free-text field is drawn (pixels): a stride is a few digits, not a window wide.
NUMBER_WIDTH = 110.0
CHOICE_WIDTH = 170.0
TEXT_WIDTH = 320.0
#: Between a colour pictogram and its caption (the glyph is drawn wider than the font measures it).
ICON_GAP = "  "


def icon_label(icon: str, text: str) -> str:
    """A button caption with its pictogram set clear of the text (``💾  Save``).

    A colour pictogram is drawn wider than the font measures it, so it takes two spaces; a plain geometric
    glyph (the ▶ of a run button) one.
    """
    return f"{icon}{' ' if 0x25A0 <= ord(icon[0]) <= 0x25FF else ICON_GAP}{text}"


def labelled(sections: Sequence[dict]) -> Iterator[dict]:
    """The field sections of a spec that carry a caption the form's grid aligns."""
    for section in sections:
        if section.get("type") in ("value", "choice") and section.get("label"):
            yield section
        yield from labelled(section.get("sections", []))


def cap_widths(sections: Sequence[dict]) -> None:
    """Declare a width for number, text and choice fields that have none (paths stay as wide as the window)."""
    for section in sections:
        kind = section.get("type")
        if kind == "value" and not section.get("width") and not section.get("read_only"):
            if section.get("kind") in ("int", "float"):
                section["width"] = NUMBER_WIDTH
            elif section.get("kind") not in ("directory", "file"):
                section["width"] = TEXT_WIDTH
        elif kind == "choice" and not section.get("width") and section.get("style") not in ("radio", "radio_list"):
            section["width"] = CHOICE_WIDTH
        cap_widths(section.get("sections", []))


def _width_class(section: dict) -> str | None:
    kind = section.get("type")
    if kind == "value":
        if section.get("kind") in ("int", "float"):
            return "number"
        return "path" if section.get("kind") in ("directory", "file") else "text"
    if kind == "choice":
        return "choice"
    return None


def group_by_width(sections: list, toggles_join: bool = True) -> list:
    """Wrap each run of same-kind fields in an untitled panel, so each run is a grid of its own.

    A grid gives one width to a whole column, so a number field, a text field and a choice (each its own
    width) cannot sit in the same grid without all being the widest. A toggle takes no width of its own and
    joins the run it follows, so it stays indented under the fields' column like the others of its form
    (*toggles_join* false: a narrow panel keeps them at the left edge, where their caption has room).
    """
    sections = [dict(s, sections=group_by_width(s["sections"], toggles_join)) if isinstance(s.get("sections"), list) else s
                for s in sections]
    def width_class(section):
        if not toggles_join and section.get("type") in ("toggle", "toggle_row"):
            return "toggle"
        return _width_class(section)

    if len({c for c in map(width_class, sections) if c}) < 2:
        return sections
    out: list = []
    run: list = []
    run_class = None
    for section in sections + [None]:
        cls = width_class(section) if section else None
        joins = toggles_join and section is not None and section.get("type") in ("toggle", "toggle_row")
        if joins and run:
            run.append(section)
            continue
        if run and cls != run_class:
            out.append({"type": "panel", "title": "", "n_col": 1, "sections": run})
            run = []
        if cls:
            run.append(section)
            run_class = cls
        elif section:
            out.append(section)
    return out


def layout_spec(spec: dict) -> dict:
    """*spec* laid out as the tool windows are: capped widths, one grid per kind of field."""
    cap_widths(spec["sections"])
    spec["sections"] = group_by_width(spec["sections"])
    return spec


class LabelColumn:
    """One caption column for every field row of a window (needs a live emtk context to measure).

    The first :meth:`measure` takes the widest caption, and :meth:`pad` pads every field caption of a spec to
    it with trailing spaces (they measure as space), so the fields of separate grids start at the same x as
    the hand-drawn rows, which read :attr:`x` for theirs.
    """

    def __init__(self) -> None:
        self.text_w: float | None = None

    @property
    def ready(self) -> bool:
        return self.text_w is not None

    def measure(self, captions: Sequence[str]) -> None:
        self.text_w = max((im.calc_text_size(c)[0] for c in captions), default=0.0)

    @property
    def x(self) -> float:
        """Where the fields start, relative to the left edge: the widest caption and the gap the grid leaves."""
        return (self.text_w or 0.0) + im.get_style().item_inner_spacing[0]

    def pad(self, sections: Sequence[dict]) -> None:
        """Pad the field captions of *sections* to the column (idempotent)."""
        space = im.calc_text_size(" ")[0] or 1.0
        for section in labelled(sections):
            text = section["label"].rstrip()
            gap = (self.text_w or 0.0) - im.calc_text_size(text)[0]
            section["label"] = text + " " * max(int(gap // space), 0)
        self.text_w = max([self.text_w or 0.0] + [im.calc_text_size(s["label"])[0] for s in labelled(sections)])


def button_width(label: str) -> float:
    """The width ``im.button(label)`` takes."""
    return im.calc_text_size(label)[0] + 2.0 * im.get_style().frame_padding[0]


def button_row(buttons: Sequence[dict], width: float | None = None,
               remember: Callable[[str], None] | None = None) -> str | None:
    """Draw actions in one row that wraps at *width* (default: the room left); the key of the one pressed.

    Each button is a dict: ``label``, ``key`` (what is returned and remembered; defaults to the label),
    ``tip``, ``enabled`` (default True; a disabled button is greyed and cannot be pressed), ``colours``
    (``(button, hovered, active)`` to push) and ``keys`` (more names to remember it under).
    """
    width = float(im.get_content_region_avail()[0] if width is None else width)
    spacing = im.get_style().item_spacing[0]
    pressed = None
    used = 0.0
    for i, button in enumerate(buttons):
        label = button["label"]
        w = button_width(label)
        if i and used + spacing + w <= width:
            im.same_line()
            used += spacing + w
        else:
            used = w
        key = button.get("key", label)
        colours = button.get("colours")
        if colours:
            from emtk.im_core import Col

            for col, rgba in zip((Col.BUTTON, Col.BUTTON_HOVERED, Col.BUTTON_ACTIVE), colours):
                im.push_style_color(col, rgba)
        enabled = button.get("enabled", True)
        if not enabled:                    # (begin_disabled(False) would re-enable inside a disabled parent)
            im.begin_disabled(True)
        if im.button(label) and enabled:
            pressed = key
        if not enabled:
            im.end_disabled()
        if colours:
            im.pop_style_color(3)
        if button.get("tip"):
            im.set_item_tooltip(button["tip"])
        if remember is not None:
            for name in (key, *button.get("keys", ())):
                remember(name)
    return pressed


__all__ = ["CHOICE_WIDTH", "ICON_GAP", "LabelColumn", "NUMBER_WIDTH", "TEXT_WIDTH", "button_row", "button_width",
           "cap_widths", "group_by_width", "icon_label", "labelled", "layout_spec"]
