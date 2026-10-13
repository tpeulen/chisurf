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
- :func:`icon_label` sets a pictogram clear of its caption;
- :data:`ACTIONS`, :func:`action_button` and :func:`sound_toggle` are the one UI vocabulary for the actions
  every window shares (Help, Guide, Sound, Restart, Run, Save, Open, Browse, Export, Copy, Reset, Cancel,
  Close, Load example): one icon, one English source label, one tooltip and one widget kind each, so the
  same action looks the same in every app. Declared button rows take the same table through
  :func:`action_item`. The vocabulary and its rationale: ``okf/subsystems/ui-vocabulary.md``; the guard
  that keeps hand-drawn variants out: ``test/test_ui_vocabulary.py``.
"""

from __future__ import annotations

#: Routing read by imaging app_base/pixel_app and TTTRImageBrowserApp: these
#: fields describe native host regions, not toolkit form controls.
LAYOUT_KEYS = frozenset({"name", "dock", "tab", "window", "page", "panels"})
#: Native plotting apps read their raw plot declarations before drawing them.
#: FCS saturation (_plot_sections/_plot) and FLC2D (_draw_series) share these.
APP_SECTION_KEYS = {
    "plot": frozenset(
        {"source", "title", "description", "x_label", "y_label", "log_x", "log_y", "legend"}
    ),
}

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Sequence

from emtk import im
from emtk.i18n import tr
from emtk.view_form import icon_caption

#: Widest a number field / a choice / a free-text field is drawn (pixels): a stride is a few digits, not a window wide.
NUMBER_WIDTH = 110.0
CHOICE_WIDTH = 170.0
TEXT_WIDTH = 320.0
#: Between a colour pictogram and its caption (the glyph is drawn wider than the font measures it).
ICON_GAP = "  "


def window_size(spec: dict, default: tuple[int, int]) -> tuple[int, int]:
    """Read a bounded logical-pixel window declaration or the app family default.

    Parameters
    ----------
    spec : dict
        Loaded view specification, optionally declaring ``window``.
    default : tuple[int, int]
        Width and height used when the declaration is absent.

    Returns
    -------
    tuple[int, int]
        Initial host dimensions; saved user geometry takes precedence later.

    Raises
    ------
    ValueError
        The declaration is incomplete, misspelled, or outside 120–8192 pixels.
    """
    if "window" not in spec:
        return default
    declaration = spec["window"]
    if (
        not isinstance(declaration, dict)
        or set(declaration) != {"width", "height"}
        or any(
            type(declaration[key]) is not int or not 120 <= declaration[key] <= 8192
            for key in ("width", "height")
        )
    ):
        raise ValueError("window requires integer width and height between 120 and 8192")
    return declaration["width"], declaration["height"]


def icon_label(icon: str, text: str) -> str:
    """A button caption with its pictogram set clear of the text (``💾  Save``).

    A colour pictogram is drawn wider than the font measures it, so it takes two spaces; a plain geometric
    glyph (the ▶ of a run button) one. The same rule declared button rows apply to an entry's ``icon``
    (:func:`emtk.view_form.icon_caption`).
    """
    return icon_caption(icon, text)


@dataclass(frozen=True)
class Action:
    """One shared action: how it looks and what its tooltip says, wherever it is drawn.

    ``label`` and ``tooltip`` are English source text and go through ``tr()`` when drawn. ``kind`` is the
    widget: ``"button"`` or ``"toggle"`` (a button that stays pressed while on). ``fixed_tooltip`` actions
    mean the same thing in every window, so their tooltip cannot be replaced; the others name *what* is
    run/saved/opened in that tool, so a caller may pass a tool-specific tooltip instead of the default.
    """

    icon: str
    label: str
    tooltip: str
    kind: str = "button"
    fixed_tooltip: bool = False


#: The shared action vocabulary. Keys are stable identifiers, not captions. The icons are the canonical
#: glyphs of :class:`chisurf.core.glyphs.Glyphs`, so a Qt label and an emtk button agree; they are spelled
#: out because importing ``chisurf.gui`` loads Qt, and ``test/test_ui_vocabulary.py`` pins them equal.
ACTIONS: dict[str, Action] = {
    "help": Action("❓", "Help", "Open the help for this window.", fixed_tooltip=True),
    "guide": Action(
        "📖",
        "Guide",
        "Start a step-by-step tour that points at the real controls.",
        fixed_tooltip=True,
    ),
    "sound": Action(
        "🔊",
        "Sound",
        "Music and sound effects (off by default).",
        kind="toggle",
        fixed_tooltip=True,
    ),
    "restart": Action("🔁", "Restart", "Start over from the beginning."),
    "close": Action("✕", "Close", "Close this window."),
    "run": Action("▶\ufe0f", "Run", "Run with the current settings."),
    "cancel": Action("✕", "Cancel", "Stop or dismiss without applying the change."),
    "reset": Action("♻\ufe0f", "Reset", "Restore the default settings."),
    "save": Action("💾", "Save", "Save the result to a file."),
    "open": Action("📂", "Open…", "Open a file."),
    "browse": Action("📂", "Browse…", "Choose a file or folder."),
    "export": Action("📤", "Export…", "Export the result to a file."),
    "copy": Action("📋", "Copy", "Copy to the clipboard."),
    "example": Action("🧪", "Load example", "Load a built-in example to try this tool."),
}
#: The muted state of the Sound toggle, and its tooltip when the window has no audio output.
SOUND_OFF_ICON = "🔇"
SOUND_UNAVAILABLE = "No sound here: this window has no audio output."
#: Appended to a tooltip that names its keyboard shortcut (``{key}`` is the key).
SHORTCUT = "Shortcut: {key}"


_catalogue_installed = False


def _install_catalogue() -> None:
    """Make the vocabulary's six-locale rows available, once, in apps that never install the shared ones."""
    global _catalogue_installed
    if not _catalogue_installed:
        from chisurf.emtk.shared_i18n import install_shared_translations

        install_shared_translations()
        _catalogue_installed = True


def action_caption(key: str, icon: str | None = None) -> str:
    """The drawn caption of action *key*: its icon, then its translated label (``"❓  Help"``)."""
    _install_catalogue()
    action = ACTIONS[key]
    return icon_label(action.icon if icon is None else icon, tr(action.label))


def action_tooltip(key: str, tooltip: str | None = None, shortcut: str | None = None) -> str:
    """The translated tooltip of action *key*: the canonical one, or *tooltip* where the action allows it.

    *tooltip* is already translated by the caller. *shortcut* appends ``Shortcut: <key>``.

    Raises
    ------
    ValueError
        *tooltip* was given for an action whose tooltip is the same in every window.
    """
    _install_catalogue()
    action = ACTIONS[key]
    if tooltip and action.fixed_tooltip:
        raise ValueError(f"the {key!r} tooltip is shared by every window and cannot be replaced")
    text = tooltip or tr(action.tooltip)
    if shortcut:
        text = f"{text} {tr(SHORTCUT).format(key=shortcut)}"
    return text


def action_button(
    key: str,
    *,
    tooltip: str | None = None,
    shortcut: str | None = None,
    id: str | None = None,
    size: tuple[float, float] | None = None,
    enabled: bool = True,
) -> bool:
    """Draw shared action *key* as its canonical button; True on the frame it is pressed.

    Parameters
    ----------
    key : str
        An :data:`ACTIONS` key (``"help"``, ``"guide"``, ``"save"`` …).
    tooltip : str, optional
        A translated, tool-specific tooltip for actions whose tooltip is not fixed.
    shortcut : str, optional
        The keyboard shortcut named at the end of the tooltip.
    id : str, optional
        The ImGui id suffix (default *key*); give one when the same action is drawn twice in a window.
    size : tuple of float, optional
        Explicit button size, as for ``im.button``.
    enabled : bool
        A disabled button is greyed and cannot be pressed.

    Returns
    -------
    bool
        Whether the button was pressed (never while disabled).
    """
    if ACTIONS[key].kind != "button":
        raise ValueError(f"{key!r} is a {ACTIONS[key].kind}, not a button")
    if not enabled:  # (begin_disabled(False) would re-enable inside a disabled parent)
        im.begin_disabled(True)
    pressed = im.button(f"{action_caption(key)}###{id or key}", size)
    if not enabled:
        im.end_disabled()
    im.set_item_tooltip(action_tooltip(key, tooltip, shortcut))
    return pressed and enabled


def sound_toggle(enabled: bool, *, available: bool = True, shortcut: str | None = None) -> bool:
    """Draw the shared Sound toggle; True on the frame it is clicked (the caller flips its own state).

    The icon shows the state (🔊 on, 🔇 off) and the button stays pressed while sound is on. Without an
    audio output (*available* False) it is greyed and says so: a switch that changes nothing must not look
    like one that works.
    """
    icon = ACTIONS["sound"].icon if enabled else SOUND_OFF_ICON
    if not available:
        im.begin_disabled(True)
    clicked, _ = im.toggle_button(f"{action_caption('sound', icon)}###sound", bool(enabled))
    if not available:
        im.end_disabled()
    im.set_item_tooltip(
        action_tooltip("sound", shortcut=shortcut) if available else tr(SOUND_UNAVAILABLE)
    )
    return clicked and available


def action_item(key: str, action: str, description: str | None = None) -> dict:
    """A declared ``button_row`` entry for shared action *key* calling model method *action*.

    The entry carries the canonical ``icon``, English ``label`` and ``description`` exactly as a
    ``*.view.json`` file must spell them (the guard compares the files against this).
    """
    entry = ACTIONS[key]
    if description and entry.fixed_tooltip:
        raise ValueError(f"the {key!r} tooltip is shared by every window and cannot be replaced")
    return {
        "action": action,
        "label": entry.label,
        "icon": entry.icon,
        "description": description or entry.tooltip,
    }


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
        elif (
            kind == "choice"
            and not section.get("width")
            and section.get("style") not in ("radio", "radio_list")
        ):
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
    sections = [
        dict(s, sections=group_by_width(s["sections"], toggles_join))
        if isinstance(s.get("sections"), list)
        else s
        for s in sections
    ]

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
        joins = (
            toggles_join and section is not None and section.get("type") in ("toggle", "toggle_row")
        )
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
        # The column holds what is drawn: the translated captions, not their sources.
        self.text_w = max((im.calc_text_size(_shown(c))[0] for c in captions), default=0.0)

    @property
    def x(self) -> float:
        """Where the fields start, relative to the left edge: the widest caption and the gap the grid leaves.

        The gap is a full item spacing, as emtk's form grid leaves after its label column; with the inner
        spacing the hand-drawn rows started 4 px left of the grid fields they are meant to align with.
        """
        return (self.text_w or 0.0) + im.get_style().item_spacing[0]

    def pad(self, sections: Sequence[dict]) -> None:
        """Pad the field captions of *sections* to the column (idempotent)."""
        space = im.calc_text_size(" ")[0] or 1.0
        for section in labelled(sections):
            # The source stays the source (the form translates it, keeping the padding);
            # the padding is measured against the translation that is drawn.
            text = section["label"].rstrip()
            gap = (self.text_w or 0.0) - im.calc_text_size(_shown(text))[0]
            section["label"] = text + " " * max(int(gap // space), 0)
        self.text_w = max(
            [self.text_w or 0.0]
            + [im.calc_text_size(_shown(s["label"]))[0] for s in labelled(sections)]
        )


def _shown(caption: str) -> str:
    """A field caption as the form draws it: its words translated, its padding kept."""
    text = str(caption)
    core = text.strip()
    if not core:
        return text
    return text[: len(text) - len(text.lstrip())] + tr(core) + text[len(text.rstrip()) :]


def button_width(label: str) -> float:
    """The width ``im.button(label)`` takes.

    ``im.button`` draws ``tr(label)``, so that is what is measured: measuring the English source let a row of
    longer translations ("Enregistrer les réglages" for "Save settings") run past the right edge of its dock.
    """
    shown = tr(str(label).split("##", 1)[0])
    return im.calc_text_size(shown)[0] + 2.0 * im.get_style().frame_padding[0]


def same_line_or_wrap(label: str) -> None:
    """Continue the current row for a button captioned *label*, or start a new row when it would not fit.

    An unwrapped ``im.same_line()`` pushes a trailing button past the right edge of a narrow dock,
    where it can be neither seen nor scrolled to.
    """
    im.same_line()
    if im.get_content_region_avail()[0] < button_width(label):
        im.new_line()


def button_row(
    buttons: Sequence[dict],
    width: float | None = None,
    remember: Callable[[str], None] | None = None,
) -> str | None:
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
        key = button.get("key", button["label"])
        # Measured and drawn translated, with the key as the id ("###"): the id no longer comes
        # from the caption, so two buttons whose captions translate alike stay two buttons, and
        # the row wraps at the width of the text that is drawn.
        text, _sep, ident = str(button["label"]).partition("##")
        label = f"{_shown(text)}###{ident.lstrip('#') or key}"
        w = button_width(label)
        if i and used + spacing + w <= width:
            im.same_line()
            used += spacing + w
        else:
            used = w
        colours = button.get("colours")
        if colours:
            from emtk.im_core import Col

            for col, rgba in zip((Col.BUTTON, Col.BUTTON_HOVERED, Col.BUTTON_ACTIVE), colours):
                im.push_style_color(col, rgba)
        enabled = button.get("enabled", True)
        if not enabled:  # (begin_disabled(False) would re-enable inside a disabled parent)
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


__all__ = [
    "ACTIONS",
    "Action",
    "CHOICE_WIDTH",
    "ICON_GAP",
    "LabelColumn",
    "NUMBER_WIDTH",
    "TEXT_WIDTH",
    "action_button",
    "action_caption",
    "action_item",
    "action_tooltip",
    "button_row",
    "same_line_or_wrap",
    "button_width",
    "cap_widths",
    "group_by_width",
    "icon_label",
    "labelled",
    "layout_spec",
    "sound_toggle",
]
