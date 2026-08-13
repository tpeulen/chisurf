"""PyMOL's object panel, drawn inside the viewport instead of beside it.

PyMOL puts its object list *in* the 3-D window: the names and their A/S/H/L/C
menus sit over the scene in the top-right corner, and the sequence runs along
the top. That is not decoration. A panel docked next to the view is a second
widget with its own font, its own metrics and its own idea of how much room it
needs, and it drifts out of step with the thing it is describing -- which is why
the spacing of five buttons became a question at all.

Drawn here, the panel is part of the picture: it scales with the view, it costs
no layout negotiation, and a screenshot of the viewport contains it.

The geometry is deliberately separate from the drawing. Layout and hit-testing
are plain arithmetic over rectangles and can be tested without a GL context or a
window; only :meth:`InternalGui.paint` needs a painter. Every click is turned
into a **command string** rather than a direct call, so the panel drives the
viewer through exactly the path a typed command takes, and nothing can be done
here that could not be scripted.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from ..mouse_modes import BUTTON_COLUMNS, DEFAULT_RING, MODE_NAMES, next_mode, rows_for
from ..object_menus import OBJECT_MENUS, MenuEntry, quote_selection_name
from .ui.command_line import HINT, PROMPT, CommandLine
from .ui.text_field import TextField
from .ui.progress import ProgressOverlay
from .ui.painter import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
)

from ..host.events import CONTROL_MODIFIER, SHIFT_MODIFIER

_CHAR_WIDTH: float | None = None

#: The point size the glyph atlas was baked at, and therefore the size at which
#: :func:`char_width` returns the atlas' own advance. Everything else is a
#: multiple of it.
BASE_FONT_PT: float = 8.0


def char_width(font_pt: int) -> float:
    """Advance width of one character of the chrome font, in pixels.

    Parameters
    ----------
    font_pt : int
        Point size, i.e. ``InternalGui.FONT_PT``.

    Returns
    -------
    float

    Notes
    -----
    Read from the baked glyph atlas, because that is what actually draws the
    text. It used to be ``font_pt * 0.62``, a guess that is **22 % narrow**:
    Menlo at 10 pt advances 8.5 px and the layout budgeted 6.2. Every box in
    the panel is sized in multiples of this, so the whole chrome was laid out
    into boxes too small for their own contents -- ``assign sec. structure``
    was given 130 px and needs 177, and because a menu is clamped against the
    right edge of the window the overflow ran *off-screen* rather than merely
    overlapping. The truncated mouse-mode block (``Mouse Mode 3-Button
    Viewin…``) and the cramped sequence strip are the same constant.

    The baked advance is what the font *is*; ``font_pt`` scales it, so the one
    knob that makes the chrome smaller (``InternalGui.FONT_PT``) reaches all
    fourteen call sites without any of them knowing about it.

    Cached: the atlas is read on every layout pass and is immutable.
    """
    global _CHAR_WIDTH
    if _CHAR_WIDTH is None:
        from .ui.font import load_atlas

        _CHAR_WIDTH = load_atlas().advance()
    return _CHAR_WIDTH * (float(font_pt) / BASE_FONT_PT)

# PyMOL's palette, read off its internal GUI.
PANEL_BG = (0, 0, 0, 190)
HEADER_BG = (128, 128, 128, 220)
HEADER_FG = (0, 0, 0)
ENABLED_FG = (0, 224, 0)
DISABLED_FG = (112, 112, 112)
BUTTON_BG = (157, 157, 255)
BUTTON_FG = (16, 16, 96)
BUTTON_EDGE = (32, 32, 96)
HOVER_BG = (192, 192, 255)
#: The same boxes on a switched-off object: still there, visibly inactive.
BUTTON_OFF_BG = (78, 78, 116)
BUTTON_OFF_FG = (150, 150, 170)
MENU_BG = (58, 58, 58, 244)
MENU_FG = (240, 240, 240)
MENU_DISABLED_FG = (144, 144, 144)
MENU_SEL_BG = (74, 74, 138)
MENU_EDGE = (144, 144, 144)
SPLITTER_FG = (96, 96, 96, 230)
SEQ_BG = (0, 0, 0, 210)
SEQ_FG = (224, 224, 224)
SEQ_NAME_FG = (0, 224, 0)
SEQ_NUMBER_FG = (144, 144, 144)
SEQ_SELECTED_BG = (255, 96, 176)
SEQ_SELECTED_FG = (0, 0, 0)
SEQ_TRACK_BG = (64, 64, 64, 230)
SEQ_THUMB_BG = (128, 128, 128, 240)

# In-viewport windows, in Dear ImGui's dark palette (`StyleColorsDark`,
# `junk/imgui/imgui_draw.cpp:187`). Its *look* is what was wanted, not its
# immediate-mode core: chimol's chrome is retained -- panels persist between
# frames -- so the IM protocol would have meant rewriting every existing panel
# to gain nothing the quad painter does not already do.
#: The zones a window press can land in, reported as `Hit.row`.
_WINDOW_TITLE = 0
_WINDOW_BODY = 1
_WINDOW_RESIZE = 2
_WINDOW_COLLAPSE = 3
_WINDOW_CLOSE = 4

# The menu bar across the top of the scene. PyMOL keeps File/Edit/Display/... in
# the window's own bar; chimol draws it, so the desktop and the browser get the
# same menus -- and on macOS a Qt bar is taken away to the *system* bar at the
# top of the screen, where it is not in the 3-D view at all.
#: The toolbar under the menu bar. Same family as the bar, one step lighter so
#: the two read as separate rows rather than one tall band.
TOOLBAR_BG = (38, 38, 44, 236)
TOOLBAR_FG = (226, 226, 230)
TOOLBAR_HOVER_BG = (58, 58, 66, 255)
#: A toolbar button that is currently *on*.
TOOLBAR_ON_BG = (41, 74, 122, 235)
TOOLBAR_ON_FG = (245, 225, 128)

MENUBAR_BG = (28, 28, 32, 236)
MENUBAR_FG = (240, 240, 240)
MENUBAR_DIM_FG = (196, 196, 200)
MENUBAR_SEL_BG = (41, 74, 122, 255)

WINDOW_BG = (15, 15, 15, 240)
WINDOW_TITLE_BG = (10, 10, 10, 255)
WINDOW_TITLE_ACTIVE_BG = (41, 74, 122, 255)
WINDOW_BORDER = (110, 110, 128, 128)
#: The snap hint: the band along an edge a dragged window is glued to, and
#: the border the glued window itself takes while the drag lasts.
SNAP_HINT = (66, 150, 250, 220)
#: How thick the edge band draws, in logical pixels.
SNAP_HINT_BAND = 3.0
WINDOW_GRIP = (66, 150, 250, 128)
WINDOW_FG = (255, 255, 255)
WINDOW_DIM_FG = (160, 160, 160)

# The system-info panel, bottom-left. Grey rather than black for the same
# reason as the prompt: it floats over the scene, and the scene's background is
# a setting -- a semi-transparent grey darkens white and lightens black, so one
# fill is readable at both ends. Overridable from the display config's
# `info_overlay` section, which is where these were already written.
#: The guided tour's ring and bubble. Deliberately the one warm accent in a
#: cool chrome: the ring has to be findable at a glance in a viewport that is
#: already full of blue selection highlights.
TOUR_RING = (255, 176, 32, 255)
TOUR_BG = (26, 26, 30, 244)
TOUR_TITLE_FG = (255, 208, 96)
TOUR_FG = (235, 235, 240)
TOUR_DIM_FG = (150, 150, 160)
TOUR_BUTTON_BG = (41, 74, 122, 255)

INFO_BG = (50, 50, 50, 199)
INFO_FG = (255, 255, 255)
INFO_EDGE = (255, 255, 255, 79)
INFO_BAR_TRACK = (255, 255, 255, 26)
INFO_BAR_THUMB = (150, 150, 160, 190)


def _wrap_lines(text: str, width: int) -> list[str]:
    """Break *text* into lines of at most *width* characters.

    The chrome's font is monospace, so a character count is a width. Existing
    newlines are kept -- the info text is written as lines -- and a long run
    with nowhere to break is cut rather than allowed to run off the panel,
    which is what a file path does.

    It must not invent blank lines, and that is not hypothetical: this split on
    ``" "``, so the *padding* in a column-aligned listing became a run of empty
    "words". Each one appended a space, the line overflowed at exactly the wrap
    width, and the remainder came out as a whitespace-only line -- so
    ``help_settings`` was double-spaced, with every third name cut mid-word
    (``cartoon_flat_she``). Any text laid out in columns hit it.
    """
    out: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        if not paragraph.strip():
            # A real blank line in the source, kept: `help` separates its
            # heading from its listing with one.
            out.append("")
            continue
        rest = paragraph
        while len(rest) > width:
            # Break at the last space that fits, so a name is not cut in half.
            cut = rest.rfind(" ", 0, width + 1)
            if cut <= 0:
                cut = width          # one unbroken run: cut it, as a path needs
            out.append(rest[:cut].rstrip())
            rest = rest[cut:].lstrip(" ")
            if not rest:
                break
        if rest:
            out.append(rest.rstrip())
    return out

# The bottom-right block's palette. Deliberately *not* PyMOL's green/salmon/
# blue any more: the block is chimol's own chrome now and reads in the same
# family as the rest of it -- the accent blue for the lines you can click,
# muted warm grey for headings, plain light grey for the reference cells.
MODE_TITLE_FG = (96, 168, 250)
MODE_HEAD_FG = (200, 168, 110)
MODE_KEY_FG = (150, 152, 170)
MODE_ACTION_FG = (222, 224, 228)
SELECT_FG = (96, 168, 250)
SELECT_MODE_FG = (235, 200, 120)
STATE_FG = (170, 174, 184)
MOVIE_FG = (200, 168, 110)
MOVIE_BG = (48, 48, 48, 230)

# The in-viewport command line. Green for what the user typed and for the
# prompt itself, PyMOL's colour for its own internal feedback; red for a
# refusal, because a command that did nothing has to say so where the eye
# already is rather than in a console behind the window.
# Grey, not black. The prompt floats over the scene and the scene's background
# is a setting: a black bar is invisible on a black background -- the prompt
# read as text lying directly on the molecule -- and unnecessarily heavy on a
# white one. A semi-transparent mid-grey darkens white and lightens black, so
# one fill works at both ends. Same reasoning, and the same value, as the
# system-info panel's backdrop.
CMD_BG = (50, 50, 50, 199)
CMD_PROMPT_FG = (0, 224, 0)
CMD_TEXT_FG = (240, 240, 240)
CMD_HINT_FG = (128, 128, 128)
CMD_ECHO_FG = (0, 224, 0)
CMD_MESSAGE_FG = (208, 208, 208)
CMD_ERROR_FG = (240, 128, 128)
CMD_CARET_FG = (0, 224, 0)

#: The movie transport, left to right: glyph and the command it runs.
MOVIE_BUTTONS: tuple[tuple[str, str], ...] = (
    ("|\u25c0", "frame 1"),
    ("\u25c0", "frame -1"),
    ("\u25a0", "mstop"),
    ("\u25b6", "mplay"),
    ("\u25b6\u25b6", "frame +1"),
    ("\u25b6|", "frame last"),
    # PyMOL's three at the right of the transport, which were missing: the
    # sequence, rocking, and full screen.
    ("S", "set seq_view, toggle"),
    ("\u25bc", "rock"),
    ("F", "full_screen"),
)

#: The C button's rainbow, left to right.
#:
#: RGB triples rather than the ``"#ff0000"`` strings they were: parsing a hex
#: colour was the last thing in the panel that needed ``QColor``, and the
#: values are identical either way.
COLOR_BUTTON_STOPS = (
    (255, 0, 0),
    (255, 255, 0),
    (0, 255, 0),
    (0, 255, 255),
    (0, 0, 255),
)


def _grey_of(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return the dimmed grey a disabled ``C`` button shows instead of *colour*.

    Parameters
    ----------
    colour : tuple of int
        An RGB triple, 0-255.

    Returns
    -------
    tuple of int
        A neutral grey of the same lightness band.

    Notes
    -----
    ``QColor.value()`` is HSV *value*, which is simply the largest of the three
    components -- so the original ``value() // 3 + 60`` is reproduced exactly
    without a toolkit. Every rainbow stop is fully saturated, so this is 145
    for all five of them: the disabled button is a flat grey, which is the
    point.
    """
    grey = max(colour[:3]) // 3 + 60
    return grey, grey, grey


@dataclass
class GuiWindow:
    """A draggable window drawn inside the viewport.

    The mechanism the rest of the UI work needs: chimol's panels are moving out
    of Qt docks and into the scene so that the desktop app and the browser run
    one code path, and a panel that cannot be moved or folded away is not a
    replacement for a dock.

    Behaviour is Dear ImGui's, from its own source rather than from memory:
    a 32x32 floor (`WindowMinSize`), a 1-pixel border, a **4-pixel** grab
    reach outside the edge so a resize is catchable (`WindowBorderHoverPadding`
    -- an edge exactly one pixel wide is not a target), a corner grip roughly
    1.1 line-heights across, and **double-clicking the title bar collapses**.

    Attributes
    ----------
    key : str
        Identity, for hit reporting and for whoever owns the contents.
    title : str
        Drawn in the title bar.
    x, y, w, h : float
        Frame rectangle in logical pixels. ``h`` is the *uncollapsed* height and
        is kept while collapsed, so unfolding restores the size.
    collapsed : bool
        Only the title bar is drawn.
    visible : bool
        Off means not drawn and not hit-testable.
    closable, resizable, movable : bool
        Which decorations the window carries.
    body : callable or None
        ``(painter, rect) -> None``, drawing the contents. Kept as a callback so
        this class stays what it is -- a frame -- and knows nothing about
        density contours or hierarchies.
    on_press, on_drag : callable or None
        ``(x, y, rect) -> bool``, the input half of ``body``. A panel that can
        be drawn but not touched is a picture, and every panel moving in here
        has something to drag -- a contour level, a hierarchy row. Returning
        true consumes the event, which is what stops a drag inside a window
        also rotating the molecule behind it.
    on_release : callable or None
        ``() -> None``, for a panel that batches work until the drag ends --
        which is how a contour drag avoids rebuilding an isosurface per mouse
        move.
    lines : list of str
        Drawn instead when there is no ``body``; enough for a text panel.
    """

    key: str
    title: str = ""
    x: float = 40.0
    y: float = 40.0
    w: float = 260.0
    h: float = 160.0
    collapsed: bool = False
    visible: bool = True
    closable: bool = True
    #: What this window was created with, for `reset_windows`. Filled in when
    #: it is added, so a layout dragged into a corner can always be undone.
    defaults: Optional[dict] = None
    #: The size the window asked for, kept so a clamp can be undone.
    #:
    #: `layout_windows` used to clamp `w`/`h` in place, which is destructive:
    #: the clamp only ever shrinks, so a viewport that was briefly narrow --
    #: including the **0x0** one every window sees before the first frame is
    #: laid out -- collapsed the window to `WINDOW_MIN_W` at (0, 0) forever.
    #: A window opened before the first draw was 102px wide with its close
    #: button nowhere near where it appeared to be. Clamping from this instead
    #: means a window shrinks to fit and grows back when there is room.
    desired_w: float = 0.0
    desired_h: float = 0.0
    #: Whether Escape and a click elsewhere put this window away.
    #:
    #: False for chrome -- the object list and the mouse block are *part of the
    #: viewport*, and dismissing them with a stray click is how someone loses
    #: the panel they were using and has to find the menu entry that brings it
    #: back. True for a window that is consulted and closed, like Settings.
    #: Distinct from `closable`, which only says whether the title bar has an
    #: `x`: the chrome windows have one and still must not vanish on a miss.
    transient: bool = False
    resizable: bool = True
    movable: bool = True
    #: A corner this window is glued to ("top-right", "bottom-left", ...).
    #: Set when a drag snaps it into a corner, cleared when a drag takes it
    #: away; an anchored window follows its corner when the viewport resizes.
    anchor: str | None = None
    body: Optional[Callable[[object, "Rect"], None]] = None
    on_press: Optional[Callable[[float, float, "Rect"], bool]] = None
    on_drag: Optional[Callable[[float, float, "Rect"], bool]] = None
    on_release: Optional[Callable[[], None]] = None
    #: ``(x, y, rect) -> str | None``: what the control under the cursor does,
    #: for the chrome's hover tooltip. The body knows its own controls.
    on_tooltip: Optional[Callable[[float, float, "Rect"], Optional[str]]] = None
    lines: list[str] = field(default_factory=list)


@dataclass
class SequenceRow:
    """One object's sequence, as the strip shows it.

    Attributes
    ----------
    name : str
        Object name, drawn at the left as PyMOL's ``seq_view_label_mode 0`` does.
    codes : str
        One-letter residue codes -- PyMOL's ``seq_view_format 0``, its default.
    numbers : list of int
        Residue numbers, labelled every ``LABEL_SPACING`` as PyMOL labels them.
    selected : set of int
        Indices currently selected, highlighted the way PyMOL highlights them.
    """

    name: str
    codes: str
    #: The object this row belongs to, so its colours can be re-read without
    #: going back through the window that built the row.
    object_id: str = ""
    #: The chain this row is, or ``""`` for an object with none. PyMOL's
    #: sequence viewer is one row **per chain**, and its label is the object
    #: and the chain in slash syntax (`1f5n/A`) -- a single row per object
    #: cannot say which chain a residue number belongs to, and residue numbers
    #: repeat across chains.
    chain: str = ""
    #: Column -> residue index in the *object*. A per-chain row is a slice of
    #: the object's residues, so its columns are not the object's indices and
    #: everything downstream -- the selection, the 3-D highlight -- speaks the
    #: object's.
    residue_indices: list[int] = field(default_factory=list)
    numbers: list[int] = field(default_factory=list)
    selected: set[int] = field(default_factory=set)
    #: Per-residue RGB, as the structure is coloured. A sequence in one colour
    #: is a different picture from the molecule it indexes: colouring by chain
    #: or by spectrum means nothing if the strip does not show it.
    colors: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class WizardRow:
    """One line of the wizard panel, in PyMOL's own shape.

    PyMOL's `Wizard.get_panel` returns `[code, label, action]` per row, where
    the code is 1 for the banner, 2 for a button whose action is a command, and
    3 for a pop-up whose action names a menu the wizard supplies. That is the
    whole vocabulary, and it is enough for every wizard it ships -- so it is
    the vocabulary here, with the codes spelled out.

    Attributes
    ----------
    kind : {"title", "button", "menu"}
        What the row is.
    label : str
        What it says. A pop-up row carries its current value in the label, as
        PyMOL's do (`Mutate to LYS`, `Hydrogens: auto`), because there is
        nowhere else to show it.
    action : str
        A command for a button; a menu **tag** for a pop-up, resolved by
        whoever supplied the panel.
    """

    kind: str
    label: str
    action: str = ""


@dataclass
class GuiRow:
    """One line of the panel: a molecule, a group, or the ``all`` header."""

    name: str
    enabled: bool = True
    is_header: bool = False
    is_group: bool = False
    #: Whether a group row is expanded. Drawn as the disclosure marker, and it
    #: is what a click on the name toggles -- a group has no visibility of its
    #: own to switch, so the click has to mean something else than it does on a
    #: molecule.
    group_open: bool = True
    #: PyMOL's ``sele`` pseudo-object: always present, pinned to the bottom of
    #: the list, and not backed by a real molecule.
    is_selection: bool = False
    #: A measurement (`distance`, `angle`, ...). Listed under `sele` because a
    #: measurement **is an object** in PyMOL -- it has a name and an on/off
    #: switch -- and they are derived from the molecules above them.
    is_measurement: bool = False
    indent: int = 0
    detail: str = ""


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle in widget pixels."""

    x: float
    y: float
    w: float
    h: float

    def contains(self, px: float, py: float) -> bool:
        """Whether ``(px, py)`` lies inside."""
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


@dataclass(frozen=True)
class Hit:
    """What sits under the cursor."""

    kind: str            # "name" | "button" | "menu" | "" (nothing)
    row: int = -1
    key: str = ""        # button key, for kind == "button"
    entry: MenuEntry | None = None
    submenu: bool = False


@dataclass
class _OpenMenu:
    """A menu currently on screen.

    Attributes
    ----------
    owner : MenuEntry or None
        The parent's entry this menu hangs off. Held by identity rather than by
        label: two submenus at different depths share a label -- ``by element``
        opens a menu whose one entry is also ``by element`` -- and matching on
        the text kept the wrong one open.
    affinity : int
        Which side of its parent the menu was placed on: ``+1`` right, ``-1``
        left. PyMOL's ``PlacementAffinity``, and inherited for the same reason:
        once a chain has flipped left against the window edge, its own children
        keep going left rather than zig-zagging back across the parent.
    """

    title: str
    target: str
    entries: Sequence[MenuEntry]
    x: float
    y: float
    parent: _OpenMenu | None = None
    item_rects: list[tuple[Rect, MenuEntry]] = field(default_factory=list)
    rect: Rect = Rect(0, 0, 0, 0)
    owner: MenuEntry | None = None
    affinity: int = 1
    #: Pixels the content is shifted up when the menu is taller than the
    #: window, and how far it may go. PyMOL scrolls a long pop-up rather than
    #: wrapping it into columns, because the column break lands wherever the
    #: window height happens to put it and takes the grouping with it.
    scroll: float = 0.0
    max_scroll: float = 0.0
    #: Height of one screenful of entries, set by the layout. A menu too tall
    #: for the window is read a **page** at a time -- the arrows in its title
    #: row turn the page -- because a wheel is not available to every hand and
    #: a menu whose remainder can only be reached by scrolling is a menu whose
    #: remainder most people never see.
    page_px: float = 0.0


class InternalGui:
    """The object panel, laid out and drawn in the viewport.

    Parameters
    ----------
    run_command : callable, optional
        Receives a command string. Everything the panel does goes through it.
    """

    ROW_H = 17
    BUTTON_W = 17
    PAD = 6
    MARGIN = 8
    FONT_PT = 8
    MENU_ITEM_H = 18
    MENU_PAD = 6
    #: The gap a separator leaves between two groups of entries.
    SEPARATOR_H = 5
    #: Gap between a submenu and the parent it hangs off, on either side.
    CHILD_GAP = 3
    #: How far one wheel notch scrolls a menu too tall for the window. PyMOL's
    #: `CPopUp::release` translates the block by ten pixels a notch; a row is
    #: the better unit, because ten pixels is not a multiple of the row height
    #: and every notch then slices the rows at both edges in half.
    MENU_SCROLL_PX = float(MENU_ITEM_H)
    #: Residue numbers every this many columns -- PyMOL's
    #: ``seq_view_label_spacing``, whose default is 5.
    LABEL_SPACING = 5
    #: Height of one sequence line.
    SEQ_ROW_H = 15
    #: Height of the scrollbar under the strip.
    #: The most of the viewport the sequence strip may take.
    SEQ_MAX_FRACTION = 0.33
    SEQ_BAR_H = 9
    #: Line height inside the mouse-mode block. Tighter than a panel row: it is
    #: a dense reference table, and PyMOL sets it close enough that the whole
    #: matrix reads as one thing rather than eight loose lines.
    BLOCK_ROW_H = 14
    #: Grab width of the splitter, in pixels.
    SPLITTER_W = 6
    #: Height of one row of the command line and of its feedback log.
    CMD_ROW_H = 16
    #: How narrow and how wide the column may be dragged.
    #: The transport needs a hit target per button, whatever else is in the
    #: column: below this the buttons stop being clickable rather than merely
    #: looking cramped.
    MIN_BUTTON_W = 14.0
    MAX_COLUMN_FRACTION = 0.6

    #: Every length the chrome is laid out with, at scale 1.0. `set_ui_scale`
    #: multiplies each of them onto the instance, so the whole panel -- text,
    #: rows, menus, title bars -- changes size together. Scaling the font alone
    #: leaves 17-pixel rows around 11-pixel text, which is not smaller chrome,
    #: only emptier chrome.
    SCALED_LENGTHS = (
        "ROW_H", "BUTTON_W", "PAD", "MARGIN", "FONT_PT", "MENU_ITEM_H",
        "MENU_PAD", "SEPARATOR_H", "CHILD_GAP", "MENU_SCROLL_PX", "SEQ_ROW_H",
        "SEQ_BAR_H", "MOUSE_LINE_H", "MENUBAR_H", "TOOLBAR_H",
        "WINDOW_TITLE_H", "WINDOW_MIN_W", "WINDOW_MIN_H", "WINDOW_GRIP",
    )

    #: How big the chrome is drawn, as a multiple of the sizes above. Smaller
    #: than one by default: the chrome is read at a glance and then looked
    #: past, and every pixel it takes is a pixel of the molecule it covers.
    DEFAULT_UI_SCALE = 1.0

    #: What the slider (and `set_ui_scale`) will accept.
    UI_SCALE_MIN = 0.5
    UI_SCALE_MAX = 2.0

    #: The scales the **slider** snaps to. Not every value between 0.5 and 2.0
    #: is worth stopping at: the glyph atlas is baked once, so a scale that
    #: puts a character's advance on a fractional pixel resamples every glyph
    #: and the text goes soft. That is what made 0.85 look pixelated.
    #:
    #: The baked advance is 7 px, so a whole-pixel advance means the scale is a
    #: multiple of 1/7 -- which is the ladder below. Typing an exact value with
    #: ``set internal_gui_scale`` is still honoured to the digit: this snapping
    #: is for the *gesture*, where the user is choosing a size by eye and has
    #: no reason to land between two crisp ones.
    UI_SCALE_STEPS: tuple[float, ...] = tuple(
        round(n / 7.0, 3) for n in range(4, 15)
    )

    @classmethod
    def snap_ui_scale(cls, value: float) -> float:
        """The nearest scale that draws text on whole pixels.

        Parameters
        ----------
        value : float
            A scale, typically from a slider position.

        Returns
        -------
        float
            The closest entry of :data:`UI_SCALE_STEPS`.
        """
        value = min(max(float(value), cls.UI_SCALE_MIN), cls.UI_SCALE_MAX)
        return min(cls.UI_SCALE_STEPS, key=lambda step: abs(step - value))

    @classmethod
    def suggest_ui_scale(cls, pixel_ratio: float = 1.0) -> float:
        """A starting scale for this display.

        The chrome is already drawn at the device pixel ratio, so on a HiDPI
        screen the *effective* magnification is ``pixel_ratio * ui_scale``. Text
        is crisp when that lands on a whole number, so the answer is the scale
        that makes it so -- 1.0 on an ordinary display, and on a fractional
        ratio (1.5, say) the scale that brings the product back to an integer
        rather than leaving every glyph resampled.

        Parameters
        ----------
        pixel_ratio : float, optional
            Device pixels per logical pixel, from the canvas.

        Returns
        -------
        float
            A scale from :data:`UI_SCALE_STEPS`.
        """
        ratio = float(pixel_ratio) if pixel_ratio and pixel_ratio > 0 else 1.0
        if abs(ratio - round(ratio)) < 1e-3:
            return 1.0          # already whole: 1.0 keeps the baked size
        target = round(ratio) / ratio
        return cls.snap_ui_scale(target)

    def set_ui_scale(self, scale: float) -> float:
        """Scale the whole chrome -- text and the boxes around it.

        Parameters
        ----------
        scale : float
            Multiplier on the class' own lengths. Clamped to a range that
            stays legible at one end and leaves room for the scene at the
            other.

        Returns
        -------
        float
            The scale actually applied.
        """
        scale = min(max(float(scale), self.UI_SCALE_MIN), self.UI_SCALE_MAX)
        if scale == getattr(self, "ui_scale", None):
            return scale
        self.ui_scale = scale
        cls = type(self)
        for name in self.SCALED_LENGTHS:
            base = getattr(cls, name, None)
            if base is None:
                continue
            # `MENU_SCROLL_PX` is a float and `ROW_H` an int; keeping each
            # one's own type matters, because a fractional row height puts
            # every row below the first on a half pixel. `FONT_PT` is the
            # exception and stays fractional: it is what `char_width` divides
            # by, so rounding it there would budget boxes for text of a size
            # nothing draws.
            value = base * scale
            keep_int = isinstance(base, int) and name != "FONT_PT"
            setattr(self, name, int(round(value)) if keep_int else float(value))
        self._menus = []
        return scale

    def __init__(self, run_command: Callable[[str], None] | None = None) -> None:
        self.visible = True
        #: Set before anything is laid out, so a panel that is never told a
        #: scale is still smaller than the baked one rather than being the one
        #: place the default does not apply.
        self.ui_scale = 1.0
        self.set_ui_scale(self.DEFAULT_UI_SCALE)
        #: Docked into a column of its own, PyMOL-style. Off by default since
        #: the object list and the mouse block became windows of their own --
        #: draggable, closable, snapped to the right-hand corners at first
        #: start -- but the column code remains for whoever turns it back on.
        self.docked = False
        self.rows: list[GuiRow] = []
        #: The wizard panel, PyMOL's `get_panel()`: rows drawn under the object
        #: list while a wizard is running, and nothing at all when none is.
        self.wizard_rows: list[WizardRow] = []
        #: PyMOL's `get_prompt()`: the line in the top-left of the viewport
        #: telling you what the wizard is waiting for. It is the whole of the
        #: instruction, and a wizard without one is a panel of buttons whose
        #: order nobody can guess.
        self.wizard_prompt: list[str] = []
        #: Resolves a pop-up row's tag into menu entries, supplied with the
        #: panel by whoever is running the wizard.
        self.wizard_menu: Callable[[str], Sequence[MenuEntry]] | None = None
        self._wizard_rect = Rect(0, 0, 0, 0)
        self._wizard_row_rects: list[tuple[Rect, WizardRow]] = []
        self._run_command = run_command
        self._row_rects: list[Rect] = []
        self._button_rects: list[dict[str, Rect]] = []
        self._eye_rects: list[Rect] = []
        #: The hover tooltip: ``(x, y, text)`` while something explains itself.
        self._tooltip: tuple[float, float, str] | None = None

        #: The running guided tour (`chimol.tour.Tour`), or None. A tour points
        #: at one real control at a time and waits for the user to use it; see
        #: :mod:`chimol.tour` for why it waits on *commands* rather than on the
        #: painted control it rings.
        self.tour = None
        self._tour_rect = Rect(0, 0, 0, 0)
        self._tour_next_rect = Rect(0, 0, 0, 0)
        self._tour_close_rect = Rect(0, 0, 0, 0)
        #: The control the current step points at, resolved during paint so the
        #: ring follows a chrome that has since been resized or scrolled.
        self._tour_target = Rect(0, 0, 0, 0)
        self._panel = Rect(0, 0, 0, 0)
        self._hover = Hit("")
        self._menus: list[_OpenMenu] = []
        #: Modal progress reporting. Public, because everything that takes long
        #: enough to notice drives it -- a load, a trace, a surface -- and none
        #: of those live in this class.
        self.progress = ProgressOverlay()
        #: Whether the developer instruments are drawn -- the chrome-size
        #: slider and the frame-rate readout. A figure does not want either.
        self.debug_overlays = False
        #: Frames per second, pushed by the renderer. 0 means "not measured",
        #: which is what a still frame and a headless host both are.
        self.fps = 0.0
        self._width = 0
        self._height = 0
        #: Widest name seen, so the panel does not change width every frame.
        self._name_width = 90.0
        #: The mouse mode the bottom-right block describes.
        self.mouse_mode = "three_button_viewing"
        #: Which ring the mode line cycles within.
        self.mouse_ring = DEFAULT_RING
        #: What a click selects, and where the movie is -- both shown there.
        self.selecting = "Residues"
        self.state = (1, 1)
        #: Frames advanced per playback step, and the window a trajectory is
        #: averaged over. PyMOL has neither: a long trajectory is watched at
        #: whatever rate it was written, and a noisy one jitters. Both are
        #: shown in the block and clicking cycles them.
        self.stride = 1
        self.average = 0
        self._stride_rect = Rect(0, 0, 0, 0)
        self._timeline_track = Rect(0, 0, 0, 0)
        self._timeline_thumb = Rect(0, 0, 0, 0)
        self._dragging_timeline = False
        #: Called with a 1-based frame when the timeline is dragged.
        self.on_frame_change: Callable[[int], None] | None = None
        self._average_rect = Rect(0, 0, 0, 0)
        #: Grooves under the stride and average cells, and which one a drag
        #: is holding. Sliders, because these are values people sweep until
        #: the picture is right rather than step one at a time.
        self._stride_groove = Rect(0, 0, 0, 0)
        self._average_groove = Rect(0, 0, 0, 0)
        self._dragging_playback: str | None = None
        #: Called with ``(stride, average)`` when either is clicked.
        self.on_playback_change: Callable[[int, int], None] | None = None
        #: Called with ``(line, placeholder)`` for a menu entry that needs a
        #: typed value. The host puts the line in its command box with the
        #: placeholder selected; there is nowhere in the viewport to type.
        self.on_prompt_command: Callable[[str, str], None] | None = None
        #: Called with ``(line, mode, title, name_filter)`` for a menu entry
        #: that names a **file**. The host opens its file dialog, fills
        #: ``{text}`` with the chosen path and runs the line; left unset (the
        #: browser has no dialog) the entry falls back to the command-line
        #: placeholder like any other prompted value.
        self.on_file_prompt: Callable[[str, str, str, str], None] | None = None
        self._mode_rect = Rect(0, 0, 0, 0)
        self._selecting_rect = Rect(0, 0, 0, 0)
        #: Width of the column the panel and the block live in. The scene is
        #: rendered to the *left* of it, as PyMOL does, rather than under it:
        #: an overlay hides the molecule it is describing, and the part it hides
        #: is the part you just moved out of the way.
        #: PyMOL's `internal_gui_width`, as a *starting* value: `layout` raises
        #: it to `minimum_column_width()` when the contents need more, which at
        #: this font is 267.
        self.column_width = 220.0
        # Folding the fixed docks was built and **removed** on 2026-08-11, at
        # the user's request: "do not allow to fold, difficult to unfold". A
        # folded dock leaves only a chevron, and a 14-pixel chevron at the edge
        # of a dark viewport is not a target anyone finds -- so the fold was a
        # one-way door in practice. The docks are shown or hidden as wholes
        # instead (`set seq_view, off`, the panel's own visibility), which is
        # reversible by a control that is still there.
        self._splitter = Rect(0, 0, 0, 0)
        self._dragging_splitter = False
        #: PyMOL's `seq_view`, off by default there and here.
        self.sequence_visible = False
        self.sequences: list[SequenceRow] = []
        #: How many chains the object *has*, when the host handed over fewer
        #: rows than that. The host truncates (an integrative model has
        #: hundreds) and the chrome truncates again to what fits, so neither
        #: alone knows the real number -- and "and 1 more" under a strip that
        #: is hiding 238 is worse than no message.
        self.sequence_total = 0
        self._seq_strip = Rect(0, 0, 0, 0)
        self._seq_rows: list[Rect] = []
        self._seq_origin = 0.0
        self._seq_scroll = 0
        self._seq_drag: tuple[int, int] | None = None
        #: The residue a shift-click extends from -- PyMOL's ``Seeker`` keeps
        #: the previous drag gesture alive for a shift continuation.
        self._seq_anchor: int | None = None
        #: Whether the press that started the drag carried a modifier, so the
        #: drag merges instead of replacing.
        self._seq_drag_additive = False
        self._seq_track = Rect(0, 0, 0, 0)
        self._seq_thumb = Rect(0, 0, 0, 0)
        self._dragging_thumb = False
        self._dragging_timeline = False
        #: Called with ``(object name, indices, additive)`` when the strip
        #: selects. Kept separate from `run_command`: a selection is not a
        #: command string, and round-tripping one through the parser would lose
        #: the indices.
        self.on_select: Callable[[str, list[int], bool], None] | None = None
        self._movie_rects: list[tuple[Rect, str]] = []
        self._block = Rect(0, 0, 0, 0)
        #: PyMOL's *internal* prompt: the command line drawn in the viewport,
        #: bottom-left of the scene. The docked console is the external one, and
        #: both drive the same command layer -- which is what lets a browser,
        #: where there is no console to dock, still be typed at.
        self.command_line = CommandLine(run_command)
        self._cmd_rect = Rect(0, 0, 0, 0)
        self._cmd_log_rect = Rect(0, 0, 0, 0)
        #: The system-info panel: what is loaded, from where, how big. Chrome
        #: like everything else here, so it is drawn by the same GPU path and
        #: laid out by the same object that places the prompt -- which is what
        #: stops the two overlapping. It was a `QPlainTextEdit` stacked on the
        #: surface, and a Qt widget cannot see chrome painted *into* the
        #: surface, so it sat on top of the prompt.
        self.info_visible = False
        #: Given a name from the info panel, a one-line description -- filled in
        #: by the host, which is what knows the command registry and the setting
        #: registry. ``None`` for a word that names neither.
        self.info_describe: Callable[[str], str | None] | None = None
        #: Called when the panel closes itself, so the host can clear the flag
        #: it is re-asserted from every frame. Without it the panel cannot be
        #: closed by anything except the control that owns that flag.
        self.on_info_close: Callable[[], None] | None = None
        #: Where the panel's text actually lives. `refresh_gui_state` copies
        #: the viewer's `_info_text` onto this chrome every frame, so a listing
        #: written straight to `info_text` survives exactly one frame -- the
        #: same trap `on_info_close` exists for.
        self.on_info_text: Callable[[str], None] | None = None
        #: Whether the user *asked* for the info panel, as opposed to something
        #: opening it for them. A pinned panel is not dismissed by a click in
        #: empty space -- only by the control that pinned it. Auto-shows (a
        #: structure finishing loading, `help` answering) leave it unpinned, so
        #: clicking away still puts them down.
        self.info_pinned = False
        #: Typing a scale instead of aiming at it. Every slider should offer
        #: this: a drag is for choosing by eye, and a keyboard is for the times
        #: the user already knows the number. Double-click opens it.
        self.ui_scale_field = TextField(placeholder="scale")
        #: The listing behind the info panel, as ``(name, description)`` pairs.
        #: Set by `help` and `help_settings`; empty for prose answers, which is
        #: what decides whether a filter box is drawn at all.
        self._info_items: list[tuple[str, str]] = []
        #: The listing's heading, e.g. ``"Commands"``.
        self._info_title = ""
        #: The filter. A field rather than a prompt because it filters *as you
        #: type* -- 178 commands is a list you search, not one you read.
        self.info_filter = TextField(
            on_change=lambda _text: self._rebuild_info_listing(),
            placeholder="filter",
        )
        #: Given a toolbar button's command, whether it is currently *on*, or
        #: ``None`` for a button that is an action rather than a state. Set by
        #: the host for the things the chrome cannot see (a representation);
        #: the chrome answers for its own panels itself.
        self.toolbar_state: Callable[[str], bool | None] | None = None
        #: Given a name from the info panel, do something with it. The host
        #: wires this to the command line, so clicking a name in `help` types
        #: it at the prompt rather than running it -- a listing is something you
        #: browse, and a click that ran `delete` would be unforgivable.
        self.on_info_activate: Callable[[str], None] | None = None
        self.info_text = ""
        #: Overridable from the display config; see `INFO_BG`.
        self.info_colors: dict = {}
        self._info_rect = Rect(0, 0, 0, 0)
        self._info_lines: list[str] = []
        #: First line drawn, so a panel taller than its box can be read. `help`
        #: is routed here and prints far more than a corner of the viewport
        #: holds, which is what made scrolling necessary rather than pleasant.
        self._info_scroll = 0
        #: The menu bar's ``(title, entries)`` pairs, left to right. Empty
        #: until the host supplies them -- the panel owns *drawing* menus, not
        #: knowing which ones an application has.
        self.menubar: list = []
        #: `(label, command, tooltip)` per button, left to right. Filled by the
        #: host for the same reason as `menubar`: the panel draws a toolbar, it
        #: does not know which buttons an application has.
        self.toolbar: list = []
        self._toolbar_rects: list = []
        self.menus_visible = True
        #: The chrome, piece by piece -- each fed from its display setting
        #: (`show_menubar`, `show_toolbar`, `show_status`) so an embedded or
        #: kiosk view can strip down to the bare 3-D scene.
        self.menubar_visible = True
        self.toolbar_visible = True
        self.status_visible = True
        #: Where the chrome-size slider sits, bottom-right in the status band.
        self._ui_scale_rect = Rect(0, 0, 0, 0)
        #: The groove within it: what a drag position maps onto.
        self._ui_scale_groove = Rect(0, 0, 0, 0)
        #: True while it is being dragged, and the track pinned for that drag.
        self._dragging_ui_scale = False
        self._ui_scale_track = None
        #: The own status line, bottom-right: what the Qt status bar used to
        #: say (object, atom, residue counts), drawn by the chrome so it also
        #: exists in the browser and can be switched off like the rest.
        self.status_text = ""
        self._menubar_rects: list = []
        #: Which title is showing its menu, or ``-1``.
        self._menubar_open = -1
        #: In-viewport windows, back to front -- the last one is on top and
        #: takes the click where two overlap.
        #: The text field with the caret, if any -- a window's search box. One
        #: at a time and owned here rather than by the window, because the key
        #: arrives at the panel and something has to say where it goes.
        self.focused_field: Optional[object] = None
        self.windows: list[GuiWindow] = []
        #: Cleared while rendering for export. `ray` and `png` produce a picture
        #: of the *scene*, and a floating panel across it is not part of the
        #: molecule -- the same reason PyMOL's ray output carries no GUI.
        self.draw_windows = True
        self._window_drag: tuple[str, float, float] | None = None
        self._window_resize: tuple[str, float, float, float, float] | None = None
        #: The window whose *body* is mid-drag, if any.
        self._window_body_drag: str | None = None

        #: Saved window placements. Empty until :meth:`enable_persistence` --
        #: the shipped app turns it on; a bare `InternalGui()` in a test never
        #: touches the user's settings, which is exactly the class of test
        #: that once rewrote real preferences.
        self._window_states: dict = {}
        self._persist_enabled = False
        #: Whether dragged windows snap to the viewport's edges. Fed each
        #: frame from the `window_snap` display setting, so toggling it in
        #: the settings panel takes effect on the next drag.
        self.window_snap = True
        #: The edges the window being dragged is snapped against right now
        #: ("left", "top", ...) -- the visual hint's data. Empty when the
        #: drag is in the open, or there is no drag.
        self._snap_hint: tuple[str, ...] = ()
        #: Windows the dragged one is snapped flush against, for the hint.
        self._snap_hint_keys: set[str] = set()
        #: The stuck group riding along with the current window drag, as
        #: ``(key, offset_x, offset_y)`` from the lead window.
        self._drag_followers: list[tuple[str, float, float]] = []
        #: Whether the press that may start a window drag held shift -- a
        #: shift-drag moves the window alone, out of its stuck group.
        self._press_shift = False
        #: The object list and the mouse block, as windows. Auto-sized to
        #: their content (so not resizable), anchored to the right-hand
        #: corners until the user drags them elsewhere.
        # The mouse block first, the object list second: on a viewport too
        # small to keep them apart they overlap, and the list -- the thing
        # clicks act on -- must be the one on top.
        self.mouse_window = self.add_window(GuiWindow(
            key="mouse", title="Mouse",
            resizable=False, anchor="bottom-right",
            body=lambda p, rect: self._paint_block(p),
        ))
        self.objects_window = self.add_window(GuiWindow(
            key="objects", title="Object List",
            resizable=False, anchor="top-right",
            body=lambda p, rect: self._paint_panel(p),
        ))

    # ── model ────────────────────────────────────────────────────────────
    def set_run_command(self, run_command: Callable[[str], None] | None) -> None:
        """Set the sink every click is turned into a command for.

        The in-viewport prompt gets the same sink: a line typed there and a
        button pressed here are the same command, and giving them separate
        routes is how the two stop agreeing about what a click means.
        """
        self._run_command = run_command
        self.command_line.set_run(run_command)

    # ------------------------------------------------------------------ #
    # Guided tours
    # ------------------------------------------------------------------ #
    def start_tour(self, tour) -> None:
        """Begin a guided tour (see :mod:`chimol.tour`)."""
        self.tour = tour

    def end_tour(self) -> None:
        """Stop the running tour and clear its rectangles.

        The rectangles matter as much as the tour: they are hit-tested, and a
        bubble that is no longer drawn but still claims its area would swallow
        clicks on the chrome underneath it.
        """
        self.tour = None
        self._tour_rect = Rect(0, 0, 0, 0)
        self._tour_next_rect = Rect(0, 0, 0, 0)
        self._tour_close_rect = Rect(0, 0, 0, 0)
        self._tour_target = Rect(0, 0, 0, 0)

    def advance_tour(self) -> None:
        """Move to the next step, ending the tour after the last one."""
        if self.tour is None:
            return
        self.tour.advance()
        if self.tour.finished:
            self.end_tour()

    def observe_command(self, line: str) -> bool:
        """Tell the running tour that *line* was executed.

        Returns
        -------
        bool
            Whether it advanced the tour, so a caller can redraw.
        """
        if self.tour is None:
            return False
        moved = self.tour.observe(line)
        if moved and self.tour.finished:
            self.end_tour()
        return moved

    def tour_target_rect(self, target: dict) -> "Rect":
        """The painted control a tour step points at.

        The vocabulary, and it is deliberately small -- a tour that can point
        anywhere is a tour nobody can read:

        ``{}``
            nothing in particular; the bubble is centred.
        ``{"menu": "File"}``
            a menu-bar title.
        ``{"toolbar": "Ray"}``
            a toolbar button, matched on its label.
        ``{"command": true}``
            the command prompt, which is where most steps point because most
            of this viewer is reached by typing.
        ``{"object": "148l"}``
            a row of the object list, matched on its name.
        ``{"movie": true}``
            the playback transport.
        ``{"sequence": true}``
            the sequence strip.

        An unresolvable target returns an empty rectangle rather than raising:
        a chrome piece may simply be switched off (`show_toolbar`), and a tour
        that died because a panel was hidden would be worse than one that
        points at nothing for a step.
        """
        empty = Rect(0, 0, 0, 0)
        if not target:
            return empty
        try:
            name = str(target.get("menu", "")).strip().lower()
            if name:
                for rect, title, *_rest in self._menubar_rects:
                    if str(title).strip().lower() == name:
                        return rect
                return empty

            label = str(target.get("toolbar", "")).strip().lower()
            if label:
                for rect, button, *_rest in self._toolbar_rects:
                    if label in str(button).strip().lower():
                        return rect
                return empty

            if target.get("command"):
                return self._cmd_rect
            if target.get("movie"):
                return self._timeline_track
            if target.get("sequence"):
                return self._seq_strip

            wanted = str(target.get("object", "")).strip().lower()
            if wanted:
                for index, row in enumerate(self.rows):
                    if str(getattr(row, "name", "")).strip().lower() == wanted:
                        if index < len(self._row_rects):
                            return self._row_rects[index]
                return empty
        except Exception:  # noqa: BLE001 - a tour must never break a frame
            return empty
        return empty

    def set_rows(self, rows: Sequence[GuiRow]) -> None:
        """Replace the panel's contents."""
        self.rows = list(rows)
        self.close_menus()

    def has_menu(self) -> bool:
        """Whether a menu is currently open."""
        return bool(self._menus)

    def close_menus(self) -> None:
        """Dismiss any open menu, and unlight the bar title that opened it."""
        self._menubar_open = -1
        self._menus = []

    # ── layout ───────────────────────────────────────────────────────────
    def layout(self, width: int, height: int, name_width: float | None = None) -> None:
        """Place the rows for a viewport of *width* x *height*.

        Anchored top-right, as PyMOL's is. Rows are laid out downward from the
        top margin; the panel is exactly as wide as it needs to be, because a
        fixed width either truncates a long name or wastes the view.
        """
        self._width, self._height = int(width), int(height)
        if name_width is not None:
            self._name_width = float(name_width)

        if self.docked:
            # The column must be at least as wide as the things inside it. It
            # starts at PyMOL's `internal_gui_width` of 220, and only the
            # *splitter drag* used to consult `minimum_column_width` -- so until
            # someone dragged it, the mouse-mode block was laid out wider than
            # the column that positions it and ran off the right edge of the
            # window (`Mouse Mode 3-Button Viewin...`).
            #
            # Not capped to the window. On a viewport narrower than the panel's
            # own minimum the two cannot both be satisfied, and the minimum
            # wins: a panel that overhangs a 200 px window is still readable,
            # where one truncated to fit it is the defect this whole clamp
            # exists to prevent.
            self.column_width = max(self.column_width, self.minimum_column_width())

        column = self.effective_column_width()
        self._splitter = Rect(
            width - column - self.SPLITTER_W / 2, 0.0, self.SPLITTER_W, float(height)
        ) if self.docked else Rect(0, 0, 0, 0)

        buttons_w = self.BUTTON_W * len(OBJECT_MENUS)
        # One extra button-width at the left: the eye. Visibility moved off
        # the name (users toggled objects while trying to select them) onto
        # an explicit control, like the density panel's.
        panel_w = (self.PAD + self.BUTTON_W + self._name_width
                   + self.PAD + buttons_w + self.PAD)
        if self.docked:
            panel_w = max(panel_w, column)
        panel_h = self.ROW_H * len(self.rows) + 2 * self.PAD if self.rows else 0
        if self.docked:
            self._panel = Rect(width - column, 0.0, column, panel_h)
        else:
            # The object list is a window now: auto-sized to its rows, placed
            # wherever the user left it (its corner anchor keeps it glued
            # top-right until a drag takes it away), and the panel rectangle
            # is simply that window's body.
            win = self.objects_window
            win.w = panel_w
            win.h = self.WINDOW_TITLE_H + panel_h
            self._apply_window_anchor(win, width, height)
            if win.visible and not win.collapsed:
                self._panel = Rect(
                    win.x, win.y + self.WINDOW_TITLE_H, panel_w, panel_h
                )
            else:
                # A closed or folded window keeps no live hit rectangles, or
                # clicks would land on rows that are not on screen.
                self._panel = Rect(0, 0, 0, 0)
                panel_h = 0

        self._row_rects = []
        self._button_rects = []
        self._eye_rects = []
        y = self._panel.y + self.PAD
        for row in self.rows if panel_h else ():
            self._row_rects.append(Rect(self._panel.x, y, panel_w, self.ROW_H))
            self._eye_rects.append(Rect(
                self._panel.x + self.PAD, y, self.BUTTON_W, self.ROW_H
            ))
            bx = self._panel.x + panel_w - self.PAD - buttons_w
            keys: dict[str, Rect] = {}
            for index, (key, _title, _entries) in enumerate(OBJECT_MENUS):
                keys[key] = Rect(
                    bx + index * self.BUTTON_W, y, self.BUTTON_W, self.ROW_H
                )
            self._button_rects.append(keys)
            y += self.ROW_H

        self.layout_menubar(width, height)
        self.layout_toolbar(width, height)
        self.layout_wizard(width, height)
        self.layout_block(width, height)
        self.layout_sequence(width, height)
        self.layout_command(width, height)
        # After the command line: the info panel sits above it, and asking
        # where "above it" is means the prompt has to be placed first.
        self.layout_info(width, height)
        self.layout_windows(width, height)

    def layout_command(self, width: int, height: int) -> None:
        """Place the command line along the bottom of the scene.

        An *overlay*, not a band the scene gives up. The prompt is one row of a
        viewport that is usually a thousand pixels tall, and taking that row
        away from the molecule would change the camera's aspect every time the
        prompt was shown -- so it is drawn over the scene, as PyMOL's is, and
        the renderer needs to know nothing about it.

        Left of the panel column, because the column is where the object list
        already is and a prompt underneath it would be reading the two as one
        block.
        """
        self._width, self._height = int(width), int(height)
        line = self.command_line
        if not line.visible:
            self._cmd_rect = Rect(0, 0, 0, 0)
            self._cmd_log_rect = Rect(0, 0, 0, 0)
            return

        scene_w = max(float(width) - self.effective_column_width(), 1.0)
        rows = len(line.visible_log())
        bottom = float(height) - self.MARGIN
        self._cmd_rect = Rect(
            0.0, bottom - self.CMD_ROW_H, scene_w, float(self.CMD_ROW_H)
        )
        self._cmd_log_rect = Rect(
            0.0, self._cmd_rect.y - rows * self.CMD_ROW_H,
            scene_w, float(rows * self.CMD_ROW_H),
        )

    #: Widest the info panel may get, in characters. PyMOL's own equivalent is
    #: a fixed column; this keeps a long path from taking half the viewport.
    INFO_MAX_CHARS = 42
    #: And the shortest it is worth drawing at all.
    INFO_MIN_CHARS = 22
    #: Beyond this many lines the panel stops hugging its content and takes the
    #: whole band -- the difference between reading `help` and glimpsing it.
    INFO_TALL_AFTER = 8
    #: Columns a long answer may use.
    #:
    #: Wide enough for the three-column listings `help` and `help_settings`
    #: produce: the longest setting name is 26 characters and `_columns` pads
    #: to the longest plus two, so three of them plus the two-space indent need
    #: 86. At 78 every such line wrapped, and a wrapped line loses the column
    #: alignment that made the listing readable -- the continuation starts at
    #: the left margin and reads as a row of its own.
    #:
    #: It is still a ceiling, not a width: the panel takes the lesser of this
    #: and the room actually available, so a narrow viewport still wraps.
    INFO_WIDE_CHARS = 88
    #: Leading for the info panel's own lines.
    #:
    #: It used ``CMD_ROW_H``, which is the *prompt's* row height -- sized for
    #: one editable line with a caret in it, and 1.8x the font. Over a hundred
    #: lines of `help` that reads as a page of gaps: the listing is dense text
    #: and wants dense leading, which is what every other listing in this panel
    #: (the object rows, the mouse block) already uses.
    INFO_ROW_H = 12

    def layout_info(self, width: int, height: int) -> None:
        """Place the system-info panel above the prompt, bottom-left.

        Above the prompt because this object lays out both: when the panel was
        a Qt widget it could only guess where the prompt was, and guessed
        wrong. The bottom left is also the emptiest corner of a framed
        structure -- the strip and the object list already own the top.
        """
        if not self.info_visible or not self.info_text:
            self._info_rect = Rect(0, 0, 0, 0)
            self._info_lines = []
            return

        char_w = char_width(self.FONT_PT)
        room = max(float(width) - self.effective_column_width(), 1.0)
        # A long answer gets a wider box as well as a taller one: 42 columns
        # wraps a docstring into a ribbon, and the reading is the point.
        # A *listing* always gets the wide ceiling, however few rows survive the
        # filter: its rows are fixed-width columns, so narrowing the box wraps
        # them and the continuation lands at the left margin, reading as a row
        # of its own. Filtering 178 commands down to 13 did exactly that.
        ceiling = (
            self.INFO_WIDE_CHARS
            if (self._info_items
                or len(str(self.info_text).splitlines()) > self.INFO_TALL_AFTER)
            else self.INFO_MAX_CHARS
        )
        max_chars = int(min(ceiling,
                            max((room - 2 * self.MARGIN) / char_w, 1)))
        wrapped = _wrap_lines(self.info_text, max(max_chars, 1))
        if wrapped != self._info_lines:
            # New text starts at the top: a scroll position carried over from
            # the previous answer lands in the middle of this one.
            self._info_scroll = 0
        self._info_lines = wrapped
        if not self._info_lines:
            self._info_rect = Rect(0, 0, 0, 0)
            return

        longest = max(len(line) for line in self._info_lines)
        box_w = max(longest, self.INFO_MIN_CHARS) * char_w + 2 * self.PAD
        box_h = len(self._info_lines) * self.INFO_ROW_H + 2 * self.PAD

        # The strip owns the top of the scene and the prompt the bottom; the
        # panel gets what is between them and is *clipped* to it rather than
        # growing past either. A viewport too short to hold even one line
        # leaves the panel out entirely -- a box drawn over the strip or the
        # prompt is worse than no box, and both of those are how the widget
        # this replaced behaved.
        top = self.top_band_height() + self.MARGIN
        bottom = float(height) - self.command_area_height() - self.MARGIN
        available = bottom - top
        if available < self.CMD_ROW_H + 2 * self.PAD:
            self._info_rect = Rect(0, 0, 0, 0)
            self._info_lines = []
            return
        # Take the room rather than hug the content. The panel is where `help`
        # answers now, and a box sized to a two-line summary showed the first
        # fifteen lines of a hundred-line answer -- reported as "the help text
        # should occupy more vertical space, must fit in the window". Long text
        # therefore fills the band between the strip and the prompt; a short
        # summary still shrinks to fit, because a mostly-empty box over the
        # molecule is its own defect.
        if len(self._info_lines) > self.INFO_TALL_AFTER:
            box_h = available
        else:
            box_h = min(box_h, available)
        self._info_rect = Rect(self.MARGIN, bottom - box_h, box_w, box_h)
        self._info_scroll = min(self._info_scroll, self.info_max_scroll())

    def info_visible_rows(self) -> int:
        """How many lines the info panel can show at its current height."""
        if self._info_rect.h <= 0.0:
            return 0
        room = self._info_rect.h - 2 * self.PAD
        if self._info_items:
            room -= self.INFO_ROW_H + 2.0        # the filter box
        return max(int(room // self.INFO_ROW_H), 0)

    def info_max_scroll(self) -> int:
        """The furthest the info panel may be scrolled, in lines."""
        return max(len(self._info_lines) - self.info_visible_rows(), 0)

    def info_token_at(self, x: float, y: float) -> str | None:
        """The word under ``(x, y)`` in the info panel, if there is one.

        ``help`` and ``help_settings`` answer with names laid out in fixed-width
        columns, so what looks like a table is a list of strings. Making those
        names live needs only the inverse of the way they are drawn: the font is
        monospaced, so a point maps to a line and a character offset, and the
        word is whatever whitespace-delimited run contains that offset.

        Deliberately generic rather than parsing the column layout that
        :meth:`Cmd._columns` happens to use today. A hit test written against
        that layout answers confidently and wrongly the moment a listing is
        formatted any other way, and nothing about the wrong answer looks wrong.

        Parameters
        ----------
        x, y : float
            A point in viewport pixels.

        Returns
        -------
        str or None
            The word, or ``None`` when the point is outside the panel, past the
            end of a line, or on whitespace.
        """
        if not self.info_contains(x, y):
            return None
        rect = self._info_rect
        row = int((y - rect.y - self.PAD) // self.INFO_ROW_H)
        index = self._info_scroll + row
        if row < 0 or not (0 <= index < len(self._info_lines)):
            return None
        line = self._info_lines[index]

        char_w = char_width(self.FONT_PT)
        if char_w <= 0.0:
            return None
        column = int((x - rect.x - self.PAD) // char_w)
        if column < 0 or column >= len(line) or line[column].isspace():
            return None

        start = column
        while start > 0 and not line[start - 1].isspace():
            start -= 1
        end = column
        while end < len(line) and not line[end].isspace():
            end += 1
        token = line[start:end].strip()
        # Punctuation is layout, not a name: the listings put a colon after a
        # heading and parentheses around a count.
        token = token.strip("():,.")
        return token or None

    def dismiss_overlays(self, x: float, y: float) -> bool:
        """Close the info panel, and any closable window, that ``(x, y)`` misses.

        What a reader expects of anything that covers the view: clicking away
        puts it down. The panel and the Settings window both had to be closed
        by the command that opened them, which means leaving the thing being
        read in order to dismiss it.

        Menus are **not** included: they close through their own path, which
        also has to handle a click landing on a parent menu rather than outside
        the whole stack.

        Parameters
        ----------
        x, y : float
            Where the press landed.

        Returns
        -------
        bool
            Whether anything was closed -- so the caller can consume the press
            rather than also rotating the molecule.
        """
        closed = False
        if self.info_visible and not self.info_pinned and not self.info_contains(x, y):
            self.hide_info()
            closed = True
        for win in list(self.windows):
            if not (win.visible and win.transient) or self._window_suppressed(win):
                continue
            if not self.window_frame(win).contains(x, y):
                win.visible = False
                closed = True
        if closed:
            self.persist_windows()
        return closed

    #: Toolbar commands that toggle a window this chrome owns, by window key.
    #: The chrome can answer for these without asking the host, which is what
    #: keeps a button's light honest when the panel is closed by other means --
    #: Escape, a click outside, or its own close box.
    TOOLBAR_WINDOWS = {
        "density_panel toggle": "density",
        "hierarchy_panel toggle": "hierarchy",
        "settings_panel": "settings",
        "settings_panel toggle": "settings",
        # The toolbar's *Cfg* runs `config`, which is an alias for
        # `settings_panel`. Keyed on the command the button actually runs, not
        # on the one it means: the button stayed dark with the panel open
        # because the alias was missing here.
        "config": "settings",
    }

    def toolbar_checked(self, command: str) -> bool | None:
        """Whether a toolbar button is *on*, or ``None`` if it has no state.

        Parameters
        ----------
        command : str
            The command the button runs.

        Returns
        -------
        bool or None
        """
        key = str(command).strip()
        if key.startswith("info_panel"):
            return bool(self.info_visible)
        window_key = self.TOOLBAR_WINDOWS.get(key)
        if window_key is not None:
            win = self.window(window_key)
            return bool(win is not None and win.visible)
        if self.toolbar_state is not None:
            try:
                return self.toolbar_state(key)
            except Exception:  # noqa: BLE001 - a light is not worth a frame
                logger.debug("toolbar state lookup failed", exc_info=True)
        return None

    def reset_windows(self) -> int:
        """Put every window back where it was authored, and forget the saved layout.

        The escape hatch for a layout that has gone wrong: a window dragged
        off-screen, collapsed and forgotten, or -- as happened here -- saved at
        a size a bug produced. Without it the only remedy is finding and
        deleting a JSON file, which is not a remedy a user has.

        Both halves are needed. Restoring the windows fixes *this* session;
        clearing the saved states is what stops the bad layout coming back on
        the next run, since the placement is re-applied from that file whenever
        a window is added.

        Returns
        -------
        int
            How many windows were restored.
        """
        restored = 0
        for win in self.windows:
            if not win.defaults:
                continue
            win.x = float(win.defaults["x"])
            win.y = float(win.defaults["y"])
            win.w = float(win.defaults["w"])
            win.h = float(win.defaults["h"])
            win.visible = bool(win.defaults["visible"])
            win.collapsed = bool(win.defaults["collapsed"])
            win.anchor = win.defaults["anchor"]
            # Cleared, not restored: an auto-sized window measures itself again
            # on the next layout, and a stale desired size would fight it.
            win.desired_w = 0.0
            win.desired_h = 0.0
            restored += 1

        self._window_states = {}
        from .window_state import state_path  # noqa: PLC0415

        path = state_path()
        try:
            if path is not None and path.is_file():
                path.unlink()
        except OSError:
            logger.debug("could not remove the saved window layout", exc_info=True)

        if self._width and self._height:
            self.layout_windows(self._width, self._height)
        return restored

    #: Names per row in a filtered listing.
    INFO_COLUMNS = 3

    def set_info_listing(self, title: str, items) -> None:
        """Show a filterable listing in the info panel.

        Parameters
        ----------
        title : str
            The heading, e.g. ``"Commands"``.
        items : iterable of (str, str)
            ``(name, description)``. The description is not drawn -- it is what
            the filter also searches, so typing ``colour`` finds ``spectrum``
            even though the word is not in its name.
        """
        self._info_title = str(title)
        self._info_items = [(str(n), str(d or "")) for n, d in items]
        self.info_filter.text = ""
        self.info_filter.cursor = 0
        self._rebuild_info_listing()

    def _rebuild_info_listing(self) -> None:
        """Re-lay the listing for the current filter."""
        if not self._info_items:
            return
        query = self.info_filter.text.strip().lower()
        matched = [
            name for name, doc in self._info_items
            if not query or query in name.lower() or query in doc.lower()
        ]
        heading = f"{self._info_title} ({len(matched)}"
        heading += f" of {len(self._info_items)}):" if query else "):"
        if matched:
            width = max(len(n) for n in matched) + 2
            rows = [
                "  " + "".join(n.ljust(width) for n in matched[i:i + self.INFO_COLUMNS])
                for i in range(0, len(matched), self.INFO_COLUMNS)
            ]
        else:
            rows = ["  (nothing matches)"]
        text = heading + "\n\n" + "\n".join(rows)
        self.info_text = text
        if self.on_info_text is not None:
            try:
                self.on_info_text(text)
            except Exception:  # noqa: BLE001 - a listing is not worth a frame
                logger.debug("info text callback failed", exc_info=True)

    def info_filter_box(self) -> "Rect":
        """Where the filter box sits, or an empty rect when there is none."""
        rect = self._info_rect
        if not self._info_items or rect.w <= 0:
            return Rect(0, 0, 0, 0)
        return Rect(rect.x + self.PAD, rect.y + self.PAD,
                    max(rect.w - 2 * self.PAD, 1.0), float(self.INFO_ROW_H))

    def press_info_filter(self, x: float, y: float) -> bool:
        """Give the filter box the keyboard if the press landed in it."""
        box = self.info_filter_box()
        if box.w <= 0 or not box.contains(x, y):
            return False
        self.focus_field(self.info_filter)
        return True

    def clear_info_listing(self) -> None:
        """Forget the listing, so the panel shows prose again.

        Called when something writes plain text into the panel: without it the
        listing keeps ownership of `info_text` and the next `help <name>` shows
        the previous command list.
        """
        self._info_items = []
        self._info_title = ""
        self.info_filter.text = ""
        self.info_filter.cursor = 0
        if self.focused_field is self.info_filter:
            self.focus_field(None)

    def _commit_ui_scale_field(self) -> None:
        """Apply the typed scale, if it is a number, and close the field.

        A value typed by hand is **not** snapped to the slider's ladder: the
        snapping exists because a drag cannot aim, and someone who typed 1.15
        meant 1.15.
        """
        text = self.ui_scale_field.text.strip()
        self.focus_field(None)
        try:
            value = float(text)
        except ValueError:
            return
        value = min(max(value, self.UI_SCALE_MIN), self.UI_SCALE_MAX)
        if self._run_command is None:
            self.set_ui_scale(value)
        else:
            self._run_command(f"set internal_gui_scale, {value}")

    def _set_ui_scale_from(self, x: float) -> None:
        """Set the chrome scale from a pointer position on the slider.

        Through the command layer, like every other control here: typing
        ``set internal_gui_scale, 1.2`` and dragging this have to end in the
        same place, and the slider draws whatever the setting says.

        Parameters
        ----------
        x : float
            Pointer position in viewport pixels.
        """
        rect = (getattr(self, "_ui_scale_track", None)
                or getattr(self, "_ui_scale_groove", None)
                or self._ui_scale_rect)
        if rect.w <= 0:
            return
        fraction = min(max((x - rect.x) / rect.w, 0.0), 1.0)
        value = self.UI_SCALE_MIN + fraction * (self.UI_SCALE_MAX - self.UI_SCALE_MIN)
        # Snap to a scale that draws on whole pixels; see `UI_SCALE_STEPS`.
        value = self.snap_ui_scale(value)
        if abs(value - float(self.ui_scale)) < 5e-3:
            return
        if self._run_command is None:
            self.set_ui_scale(value)
            return
        self._run_command(f"set internal_gui_scale, {value}")

    def drag_ui_scale(self, x: float) -> bool:
        """Continue a slider drag. Returns whether it is active."""
        if not self._dragging_ui_scale:
            return False
        self._set_ui_scale_from(x)
        return True

    def hide_info(self) -> None:
        """Put the info panel away and forget where it was scrolled to.

        The scroll is reset because the panel is reused for every answer: kept,
        it would open the next one part-way down for no reason the reader can
        see.
        """
        self.info_visible = False
        self.info_pinned = False
        self._info_scroll = 0
        # And tell whoever *owns* that flag. `refresh_gui_state` re-asserts
        # `gui.info_visible` from the viewer's `_info_visible` on every frame,
        # so clearing only the chrome's copy closed the panel for exactly one
        # frame and the next one put it straight back -- which is why the panel
        # appeared to ignore Escape, a click outside and a click on a name,
        # while the Info button (which flips the viewer's flag) worked.
        if self.on_info_close is not None:
            try:
                self.on_info_close()
            except Exception:  # noqa: BLE001 - closing must not raise
                logger.debug("info close callback failed", exc_info=True)

    def info_contains(self, x: float, y: float) -> bool:
        """Whether the info panel is showing and covers ``(x, y)``.

        Separate from :meth:`scroll_info` because "the pointer is over the
        panel" and "the panel moved" are different questions, and a wheel
        router that conflates them sends the notch to the molecule behind the
        panel whenever the text is already at one end of its travel.

        Parameters
        ----------
        x, y : float
            A point in viewport pixels.

        Returns
        -------
        bool
        """
        return bool(self.info_visible) and self._info_rect.contains(x, y)

    def scroll_info(self, x: float, y: float, steps: int) -> bool:
        """Scroll the info panel under the cursor. Returns whether it moved.

        The panel became scrollable when `help` started printing into it: the
        command list is far longer than a corner of the viewport, and a panel
        that silently shows the first fifteen lines of an answer is worse than
        one that says nothing.
        """
        if not self.info_visible or not self._info_rect.contains(x, y):
            return False
        ceiling = self.info_max_scroll()
        if ceiling <= 0:
            return False
        before = self._info_scroll
        self._info_scroll = min(max(self._info_scroll - int(steps), 0), ceiling)
        return self._info_scroll != before

    #: Width of the info panel's scroll bar, and its two colours.
    INFO_BAR_W = 6.0

    def _paint_info(self, p) -> None:
        """Draw the system-info panel."""
        rect = self._info_rect
        if rect.w <= 0.0 or not self._info_lines:
            return
        colours = self.info_colors or {}
        back = colours.get("background", INFO_BG)
        fore = colours.get("text", INFO_FG)
        edge = colours.get("border", INFO_EDGE)

        p.stroke_rect(rect.x, rect.y, rect.w, rect.h, edge, fill=back)
        rows = self.info_visible_rows()
        total = len(self._info_lines)
        # The panel has scrolled since it learned to hold `help`, and nothing
        # said so: a wheel is not discoverable and a page of text that ends
        # mid-sentence reads as truncated rather than scrolled.
        bar = self.INFO_BAR_W if total > rows else 0.0
        text_w = rect.w - 2 * self.PAD - bar

        # The filter box, when this is a listing rather than prose.
        box = self.info_filter_box()
        text_top = rect.y + self.PAD
        if box.w > 0:
            focused = self.focused_field is self.info_filter
            p.stroke_rect(box.x, box.y, box.w, box.h,
                          INFO_BAR_THUMB if focused else edge, fill=PANEL_BG)
            shown = self.info_filter.text or self.info_filter.placeholder
            colour = fore if self.info_filter.text else MODE_HEAD_FG
            p.text(box.x + 4.0, box.y, max(box.w - 8.0, 1.0), box.h,
                   ALIGN_VCENTER | ALIGN_LEFT, shown, colour)
            text_top = box.y + box.h + 2.0

        p.push_clip(rect.x, rect.y, rect.w, rect.h)
        try:
            first = self._info_scroll
            for index, line in enumerate(
                self._info_lines[first: first + max(rows, 0)]
            ):
                p.text(
                    rect.x + self.PAD,
                    text_top + index * self.INFO_ROW_H,
                    text_w,
                    float(self.INFO_ROW_H),
                    ALIGN_VCENTER | ALIGN_LEFT,
                    line,
                    fore,
                )
            if bar:
                track_x = rect.x + rect.w - self.PAD - self.INFO_BAR_W
                track_y = rect.y + self.PAD
                track_h = max(rect.h - 2 * self.PAD, 1.0)
                p.fill_rect(track_x, track_y, self.INFO_BAR_W, track_h,
                            INFO_BAR_TRACK)
                thumb_h = max(track_h * rows / float(total), 14.0)
                travel = max(track_h - thumb_h, 0.0)
                offset = travel * (
                    self._info_scroll / float(max(self.info_max_scroll(), 1))
                )
                p.fill_rect(track_x, track_y + offset, self.INFO_BAR_W,
                            thumb_h, INFO_BAR_THUMB)
        finally:
            p.pop_clip()

    # ── in-viewport windows ──────────────────────────────────────────────
    #: Title-bar height and the floor a window may shrink to. ImGui's own
    #: `WindowMinSize` is 32x32.
    WINDOW_TITLE_H = 20.0
    WINDOW_MIN_W = 120.0
    WINDOW_MIN_H = 32.0
    #: Reach *outside* the corner that still grabs the resize grip. ImGui's
    #: `WindowBorderHoverPadding`, and the reason it exists: an edge one pixel
    #: wide is not something a mouse can be expected to hit.
    WINDOW_GRAB_PAD = 4.0
    #: Corner grip, ~1.1 line-heights across, as ImGui sizes it.
    WINDOW_GRIP = 14.0

    def add_window(self, window: GuiWindow) -> GuiWindow:
        """Add or replace a window by key, on top. Returns it.

        A placement saved by a previous run is applied here, so every window
        comes back where the user left it -- including hidden, which is what
        makes closing a panel stick across restarts.
        """
        # Snapshot what the window was *authored* with, before a saved state
        # overwrites it. This is what `reset_windows` puts back, and it has to
        # be taken here because nothing else remembers it: the panels build
        # their window fresh each time, so the defaults live only in the call
        # that made it.
        if window.defaults is None:
            window.defaults = {
                "x": float(window.x), "y": float(window.y),
                "w": float(window.w), "h": float(window.h),
                "visible": bool(window.visible),
                "collapsed": bool(window.collapsed),
                "anchor": window.anchor,
            }
        self._apply_saved_state(window)
        if not window.desired_w:
            window.desired_w = float(window.w)
        if not window.desired_h:
            window.desired_h = float(window.h)
        self.windows = [w for w in self.windows if w.key != window.key]
        self.windows.append(window)
        return window

    def _apply_saved_state(self, window: GuiWindow) -> None:
        """Restore one window's remembered placement, if there is one."""
        saved = self._window_states.get(window.key)
        if not isinstance(saved, dict):
            return
        for field_name in ("x", "y"):
            if field_name in saved:
                try:
                    setattr(window, field_name, float(saved[field_name]))
                except (TypeError, ValueError):
                    pass
        if window.resizable:
            for field_name in ("w", "h"):
                if field_name in saved:
                    try:
                        setattr(window, field_name, float(saved[field_name]))
                    except (TypeError, ValueError):
                        pass
        if "visible" in saved:
            window.visible = bool(saved["visible"])
        if "collapsed" in saved:
            window.collapsed = bool(saved["collapsed"])
        if "anchor" in saved:
            anchor = saved["anchor"]
            window.anchor = str(anchor) if anchor else None

    def enable_persistence(self) -> None:
        """Load saved window states and start saving changes.

        Called by the shipped application, deliberately not by the
        constructor: window states live beside the user's real settings, and
        every test that builds a bare panel would otherwise read -- and on the
        first drag, rewrite -- the preferences of whoever runs the suite.
        """
        from .window_state import load_states  # noqa: PLC0415

        self._window_states = load_states()
        self._persist_enabled = True
        for win in self.windows:
            self._apply_saved_state(win)

    def persist_windows(self) -> None:
        """Save every window's placement for the next run, when enabled."""
        if not self._persist_enabled:
            return
        from .window_state import save_states  # noqa: PLC0415

        for win in self.windows:
            self._window_states[win.key] = {
                "x": float(win.x), "y": float(win.y),
                "w": float(win.w), "h": float(win.h),
                "visible": bool(win.visible),
                "collapsed": bool(win.collapsed),
                "anchor": win.anchor,
            }
        save_states(self._window_states)

    def window(self, key: str) -> GuiWindow | None:
        """The window with *key*, or ``None``."""
        for win in self.windows:
            if win.key == key:
                return win
        return None

    def remove_window(self, key: str) -> bool:
        """Drop a window. Returns whether there was one."""
        before = len(self.windows)
        self.windows = [w for w in self.windows if w.key != key]
        return len(self.windows) != before

    def raise_window(self, key: str) -> None:
        """Bring a window to the front."""
        found = self.window(key)
        if found is None or self.windows[-1] is found:
            return
        self.windows = [w for w in self.windows if w is not found] + [found]

    def window_frame(self, win: GuiWindow) -> Rect:
        """The window's outline, collapsed to its title bar when folded."""
        height = self.WINDOW_TITLE_H if win.collapsed else max(
            win.h, self.WINDOW_TITLE_H
        )
        return Rect(win.x, win.y, win.w, height)

    def window_body(self, win: GuiWindow) -> Rect:
        """Where the contents go; empty while collapsed."""
        if win.collapsed:
            return Rect(0, 0, 0, 0)
        return Rect(
            win.x, win.y + self.WINDOW_TITLE_H,
            win.w, max(win.h - self.WINDOW_TITLE_H, 0.0),
        )

    def layout_windows(self, width: int, height: int) -> None:
        """Keep every window inside the viewport, and no smaller than the floor.

        Clamped rather than free: a window dragged off the edge of a viewport
        that is then resized smaller is unreachable, and there is no window
        manager underneath to get it back.
        """
        if width <= 0 or height <= 0:
            # No viewport yet -- every window is created before the first frame
            # is laid out, and clamping against 0 collapses them all.
            return
        floor = float(height) - self._bottom_chrome_height()
        for win in self.windows:
            if win.resizable:
                # A user-sized window is restored from what it asked for, not
                # from what it was last squeezed to, so widening the viewport
                # gives the width back.
                if not win.desired_w:
                    win.desired_w = float(win.w)
                if not win.desired_h:
                    win.desired_h = float(win.h)
                win.w = float(win.desired_w)
                win.h = float(win.desired_h)
            # An auto-sized window (`resizable=False`) is measured from its
            # contents by `layout_block` / `layout_panel` every frame, and that
            # measurement is the authority -- restoring a remembered size here
            # overwrote it with the dataclass default, which drew the mouse
            # block's first row underneath its own title bar and made the mode
            # line unclickable.
            win.w = max(float(win.w), self.WINDOW_MIN_W)
            win.h = max(float(win.h), self.WINDOW_MIN_H)
            win.w = min(win.w, max(float(width) - 2 * self.MARGIN, self.WINDOW_MIN_W))
            if win.anchor:
                self._apply_window_anchor(win, width, height)
            frame = self.window_frame(win)
            # The bands a window may not land in: the menu bar, the toolbar and
            # the sequence strip along the top, and the prompt and status line
            # along the bottom. Only *anchored* windows respected the top band
            # (through `_apply_window_anchor`), so a window dragged upwards
            # parked its title bar under the menus -- where its own close box
            # and drag handle are unreachable, because the menu bar is hit-
            # tested first and takes the press.
            ceiling = self._top_chrome_height()
            win.x = min(max(float(win.x), 0.0), max(float(width) - frame.w, 0.0))
            win.y = min(
                max(float(win.y), ceiling),
                max(floor - frame.h, ceiling),
            )

    def _top_chrome_height(self) -> float:
        """Where the top-anchored windows begin: below the fixed top chrome.

        The menu bar, the toolbar and the sequence strip all live along the
        top edge; a window anchored "top-right" that ignored them would sit on
        the sequence it is not about.
        """
        top = float(self.menubar_height() + self.toolbar_height())
        if self.sequence_visible and self.sequences:
            try:
                top += float(self.sequence_height())
            except Exception:
                pass
        return top

    def _bottom_chrome_height(self) -> float:
        """Where the windows must stop: above the prompt and the status line.

        A window dragged over the command row hides the one place errors are
        reported, and one over the status line hides what the app is saying
        about itself -- so the band is out of bounds for windows the same way
        the top chrome is.
        """
        # The prompt and the status line **stack**; they do not overlap. This
        # took the `max` of the two and counted one row for whichever was
        # showing, so a window snapped to the bottom edge sat squarely on the
        # status line -- the one place the app reports what it just did.
        #
        # `command_area_height` is the authority for the prompt, because it
        # reserves the feedback log's rows as well: a prompt that has just
        # printed three lines is three rows taller than one that has not, and
        # a band measured at one row is wrong the moment anything is echoed.
        bottom = self.command_area_height()
        if self.status_visible and self.status_text:
            bottom += float(self.CMD_ROW_H)
        if bottom:
            bottom += 4.0        # a hair of air above the band
        return bottom

    def _apply_window_anchor(self, win: GuiWindow, width: int, height: int) -> None:
        """Glue an anchored window to its corner of this viewport."""
        if not win.anchor:
            return
        from .window_state import anchored_position  # noqa: PLC0415

        frame_h = self.WINDOW_TITLE_H if win.collapsed else win.h
        win.x, win.y = anchored_position(
            win.anchor, win.x, win.y, win.w, frame_h,
            float(width), float(height) - self._bottom_chrome_height(),
            self._top_chrome_height(),
        )

    def _window_hit(self, x: float, y: float) -> Hit | None:
        """What a press at ``(x, y)`` would do to a window, front to back."""
        if not self.draw_windows:
            return None
        for win in reversed(self.windows):
            if not win.visible:
                continue
            if self._window_suppressed(win):
                continue
            frame = self.window_frame(win)
            if win.resizable and not win.collapsed:
                grip = Rect(
                    frame.x + frame.w - self.WINDOW_GRIP,
                    frame.y + frame.h - self.WINDOW_GRIP,
                    self.WINDOW_GRIP + self.WINDOW_GRAB_PAD,
                    self.WINDOW_GRIP + self.WINDOW_GRAB_PAD,
                )
                if grip.contains(x, y):
                    return Hit("window", key=win.key, row=_WINDOW_RESIZE)
            if not frame.contains(x, y):
                continue
            if y <= frame.y + self.WINDOW_TITLE_H:
                right = frame.x + frame.w
                if win.closable and x >= right - self.WINDOW_TITLE_H:
                    return Hit("window", key=win.key, row=_WINDOW_CLOSE)
                if x <= frame.x + self.WINDOW_TITLE_H:
                    return Hit("window", key=win.key, row=_WINDOW_COLLAPSE)
                return Hit("window", key=win.key, row=_WINDOW_TITLE)
            if win.key == "objects":
                # The body is the object list; resolve its rows and buttons
                # here, where the window's z-order has already been decided --
                # falling through to the flat hit list let an overlapping
                # block eat the row underneath it on a small viewport.
                return self._panel_sub_hit(x, y)
            if win.key == "mouse":
                return self._block_sub_hit(x, y)
            return Hit("window", key=win.key, row=_WINDOW_BODY)
        return None

    def _panel_sub_hit(self, x: float, y: float) -> Hit:
        """What the object list would do with a press at ``(x, y)``."""
        for index, rect in enumerate(self._row_rects):
            if not rect.contains(x, y):
                continue
            if (index < len(self._eye_rects)
                    and self._eye_rects[index].contains(x, y)):
                return Hit("eye", row=index)
            for key, brect in self._button_rects[index].items():
                if brect.contains(x, y):
                    return Hit("button", row=index, key=key)
            return Hit("name", row=index)
        return Hit("panel")

    def _block_sub_hit(self, x: float, y: float) -> Hit:
        """What the mouse block would do with a press at ``(x, y)``."""
        if self._mode_rect.contains(x, y):
            return Hit("mode")
        if self._selecting_rect.contains(x, y):
            return Hit("selecting")
        if self._timeline_track.contains(x, y):
            return Hit("timeline")
        if self._stride_rect.contains(x, y):
            return Hit("stride")
        if self._stride_groove.contains(x, y):
            return Hit("playback_slider", key="stride")
        if self._average_groove.contains(x, y):
            return Hit("playback_slider", key="average")
        if self._average_rect.contains(x, y):
            return Hit("average")
        for rect, command in self._movie_rects:
            if rect.contains(x, y):
                return Hit("movie", key=command)
        return Hit("block")

    #: How near two window edges must be to count as touching (stuck), and to
    #: snap flush while dragging.
    WINDOW_STICK = 8.0

    def _frames_touch(self, a: "Rect", b: "Rect", slack: float = 2.0) -> bool:
        """Whether two frames share an edge (flush within ``slack``, spans
        overlapping) -- the geometric definition of *stuck*."""
        h_overlap = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
        v_overlap = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
        beside = (abs((a.x + a.w) - b.x) <= slack
                  or abs((b.x + b.w) - a.x) <= slack)
        stacked = (abs((a.y + a.h) - b.y) <= slack
                   or abs((b.y + b.h) - a.y) <= slack)
        return (beside and v_overlap > 0) or (stacked and h_overlap > 0)

    def _stuck_group(self, win: GuiWindow) -> list[GuiWindow]:
        """The windows transitively touching ``win``, including it.

        Stuck is read off the geometry rather than kept as links: two windows
        that sit flush are a group, and pulling one flush against another is
        all it takes to join them. Shift-drag is how one leaves.
        """
        candidates = [
            other for other in self.windows
            if other.visible and other.movable
            and not self._window_suppressed(other)
        ]
        group = {win.key}
        ordered = [win]
        grew = True
        while grew:
            grew = False
            for other in candidates:
                if other.key in group:
                    continue
                frame = self.window_frame(other)
                if any(self._frames_touch(self.window_frame(member), frame)
                       for member in ordered):
                    group.add(other.key)
                    ordered.append(other)
                    grew = True
        return ordered

    def _snap_to_windows(self, win: GuiWindow, x: float, y: float,
                         skip: set[str]) -> tuple[float, float, set[str]]:
        """Snap a dragged frame flush against other windows' edges.

        Returns the adjusted position and the keys of the windows it landed
        against, for the visual hint. Followers of the current drag are
        skipped -- a group must not snap against itself.
        """
        frame = self.window_frame(win)
        w, h = frame.w, frame.h
        hit_keys: set[str] = set()
        for other in self.windows:
            if other.key == win.key or other.key in skip:
                continue
            if not other.visible or self._window_suppressed(other):
                continue
            of = self.window_frame(other)
            v_overlap = min(y + h, of.y + of.h) - max(y, of.y)
            h_overlap = min(x + w, of.x + of.w) - max(x, of.x)
            snapped = False
            if v_overlap > 0:
                if abs((x + w) - of.x) <= self.WINDOW_STICK:
                    x = of.x - w
                    snapped = True
                elif abs((of.x + of.w) - x) <= self.WINDOW_STICK:
                    x = of.x + of.w
                    snapped = True
            if h_overlap > 0:
                if abs((y + h) - of.y) <= self.WINDOW_STICK:
                    y = of.y - h
                    snapped = True
                elif abs((of.y + of.h) - y) <= self.WINDOW_STICK:
                    y = of.y + of.h
                    snapped = True
            if snapped:
                # Align the perpendicular edge too when it is nearly level --
                # a stuck pair with a two-pixel step reads as a mistake.
                if abs(y - of.y) <= self.WINDOW_STICK:
                    y = of.y
                if abs(x - of.x) <= self.WINDOW_STICK:
                    x = of.x
                hit_keys.add(other.key)
        return x, y, hit_keys

    def _window_suppressed(self, win: GuiWindow) -> bool:
        """Whether a window is off-duty in the current chrome mode.

        The object-list and mouse windows stand down when the panel column is
        docked (the column already shows their content) or when the panel as a
        whole is hidden (`internal_gui off` hides the reference chrome, and a
        floating copy of it defeats the point).
        """
        return win.key in ("objects", "mouse") and (self.docked or not self.visible)

    def _press_window(self, hit: Hit, x: float, y: float, double: bool) -> bool:
        """Apply a press that landed on a window."""
        win = self.window(hit.key)
        if win is None:
            return False
        self.raise_window(win.key)
        zone = hit.row
        if zone == _WINDOW_CLOSE:
            win.visible = False
            self.persist_windows()
            return True
        if zone == _WINDOW_COLLAPSE:
            win.collapsed = not win.collapsed
            self.persist_windows()
            return True
        if zone == _WINDOW_TITLE:
            if double:
                # ImGui folds on a double-click of the title bar, which is the
                # gesture people already try.
                win.collapsed = not win.collapsed
                return True
            if win.movable:
                self._window_drag = (win.key, x - win.x, y - win.y)
                # Windows that touch the dragged one move with it -- stuck is
                # geometric, read off the frames at the moment the drag
                # starts, so nothing has to be linked or unlinked explicitly.
                # A shift-drag takes the window alone, which is how a stuck
                # pair is pulled apart.
                if self._press_shift:
                    self._drag_followers = []
                else:
                    self._drag_followers = [
                        (other.key, other.x - win.x, other.y - win.y)
                        for other in self._stuck_group(win)
                        if other.key != win.key
                    ]
            return True
        if zone == _WINDOW_RESIZE and win.resizable:
            self._window_resize = (win.key, x, y, win.w, win.h)
            return True
        if zone == _WINDOW_BODY and win.on_press is not None:
            # The contents get the press in the window's own coordinates. A
            # panel that can be drawn and not touched is a picture.
            try:
                if win.on_press(x, y, self.window_body(win)):
                    self._window_body_drag = win.key
            except Exception:
                logger.debug("window body refused a press", exc_info=True)
        return True

    def _drag_window(self, x: float, y: float) -> bool:
        """Continue a window move or resize. Returns whether anything moved."""
        if self._window_body_drag is not None:
            win = self.window(self._window_body_drag)
            if win is None or win.on_drag is None:
                self._window_body_drag = None
                return False
            try:
                return bool(win.on_drag(x, y, self.window_body(win)))
            except Exception:
                logger.debug("window body refused a drag", exc_info=True)
                return False

        if self._window_drag is not None:
            key, dx, dy = self._window_drag
            win = self.window(key)
            if win is None:
                self._window_drag = None
                return False
            followers = [
                (other_key, offx, offy)
                for other_key, offx, offy in (self._drag_followers or [])
                if self.window(other_key) is not None
            ]
            if not self.window_snap:
                # Snapping is off: the window goes exactly where it is
                # dropped, owns its position, and follows no edge. Stuck
                # windows still travel with it -- stickiness and snapping
                # are different promises.
                win.x, win.y = x - dx, y - dy
                win.anchor = None
                self._snap_hint = ()
                self._snap_hint_keys = set()
            else:
                from .window_state import snap  # noqa: PLC0415

                skip = {key} | {other_key for other_key, _o, _y in followers}
                new_x, new_y, stuck_keys = self._snap_to_windows(
                    win, x - dx, y - dy, skip
                )
                frame = self.window_frame(win)
                new_x, new_y, anchor = snap(
                    new_x, new_y, frame.w, frame.h,
                    float(self._width),
                    float(self._height) - self._bottom_chrome_height(),
                    self._top_chrome_height(),
                )
                win.x, win.y = new_x, new_y
                # A drag onto an edge or into a corner glues the window
                # there; a drag anywhere else frees it. The anchor is what
                # keeps the object list on the top-right through a resize.
                win.anchor = anchor
                # The visual hints: bands along glued viewport edges, and an
                # accent border on the windows this one is stuck to.
                self._snap_hint = tuple(anchor.split("-")) if anchor else ()
                self._snap_hint_keys = stuck_keys
            # The stuck group rides along at its offsets from the lead.
            for other_key, offx, offy in followers:
                other = self.window(other_key)
                other.x = win.x + offx
                other.y = win.y + offy
                other.anchor = None
            self.layout_windows(self._width, self._height)
            return True
        if self._window_resize is not None:
            key, ox, oy, ow, oh = self._window_resize
            win = self.window(key)
            if win is None:
                self._window_resize = None
                return False
            win.w = max(ow + (x - ox), self.WINDOW_MIN_W)
            win.h = max(oh + (y - oy), self.WINDOW_MIN_H)
            # A drag is the user *asking* for this size, so it becomes the size
            # the clamp works from. Without this the next layout would restore
            # whatever the window was created with and the resize would appear
            # to snap back.
            win.desired_w = win.w
            win.desired_h = win.h
            self.layout_windows(self._width, self._height)
            return True
        return False

    def _paint_windows(self, p) -> None:
        """Draw the windows back to front, in ImGui's dark palette."""
        if not self.draw_windows:
            return
        active = self.windows[-1] if self.windows else None
        for win in self.windows:
            if not win.visible:
                continue
            if self._window_suppressed(win):
                continue
            frame = self.window_frame(win)
            body = self.window_body(win)
            if not win.collapsed:
                p.fill_rect(frame.x, frame.y, frame.w, frame.h, WINDOW_BG)
            title_bg = (
                WINDOW_TITLE_ACTIVE_BG if win is active else WINDOW_TITLE_BG
            )
            p.fill_rect(frame.x, frame.y, frame.w, self.WINDOW_TITLE_H, title_bg)

            # The fold arrow, in the square at the left of the title bar.
            p.text(
                frame.x, frame.y, self.WINDOW_TITLE_H, self.WINDOW_TITLE_H,
                ALIGN_CENTER, "▶" if win.collapsed else "▼", WINDOW_DIM_FG,
            )
            p.text(
                frame.x + self.WINDOW_TITLE_H, frame.y,
                max(frame.w - 2 * self.WINDOW_TITLE_H, 1.0), self.WINDOW_TITLE_H,
                ALIGN_VCENTER | ALIGN_LEFT, win.title or win.key, WINDOW_FG,
            )
            if win.closable:
                # `x`, not `×`: the baked chrome atlas has no multiplication
                # sign, and a glyph it does not have draws as *nothing* -- which
                # is why every window seemed to lack a close button.
                p.text(
                    frame.x + frame.w - self.WINDOW_TITLE_H, frame.y,
                    self.WINDOW_TITLE_H, self.WINDOW_TITLE_H,
                    ALIGN_CENTER, "x", WINDOW_FG,
                )

            if not win.collapsed:
                p.push_clip(body.x, body.y, body.w, body.h)
                try:
                    if win.body is not None:
                        win.body(p, body)
                    else:
                        for index, line in enumerate(win.lines):
                            top = body.y + self.PAD + index * self.CMD_ROW_H
                            if top > body.y + body.h:
                                break
                            p.text(
                                body.x + self.PAD, top,
                                body.w - 2 * self.PAD, float(self.CMD_ROW_H),
                                ALIGN_VCENTER | ALIGN_LEFT, line, WINDOW_FG,
                            )
                finally:
                    p.pop_clip()
                if win.resizable:
                    # ImGui draws the grip as a corner triangle; three stacked
                    # bars read the same at this size and cost three quads.
                    for step in range(3):
                        size = self.WINDOW_GRIP - step * 4.0
                        p.fill_rect(
                            frame.x + frame.w - size,
                            frame.y + frame.h - 2.0 - step * 4.0,
                            size, 2.0, WINDOW_GRIP,
                        )
            dragging_this = (
                self._window_drag is not None and self._window_drag[0] == win.key
            )
            glued = dragging_this and (self._snap_hint or self._snap_hint_keys)
            partner = (
                self._window_drag is not None
                and win.key in self._snap_hint_keys
            )
            if glued or partner:
                # The glued window -- and the window it stuck to -- announce
                # themselves in the accent colour while the drag lasts.
                p.stroke_rect(frame.x, frame.y, frame.w, frame.h, SNAP_HINT)
            else:
                p.stroke_rect(frame.x, frame.y, frame.w, frame.h, WINDOW_BORDER)
        self._paint_snap_hint(p)

    def _paint_snap_hint(self, p) -> None:
        """Bands along the edges a dragged window is snapped against.

        The visual half of stickiness: without it a snap is a small jump the
        eye may miss, and whether the window is *glued* (will follow the edge
        through resizes) or merely *near* is invisible. A lit band along the
        edge, live while the drag lasts, is the difference stated out loud.
        """
        if not self._snap_hint or self._window_drag is None:
            return
        width = float(self._width)
        height = float(self._height)
        top = self._top_chrome_height()
        band = SNAP_HINT_BAND
        for edge in self._snap_hint:
            if edge == "left":
                p.fill_rect(0.0, top, band, height - top, SNAP_HINT)
            elif edge == "right":
                p.fill_rect(width - band, top, band, height - top, SNAP_HINT)
            elif edge == "top":
                p.fill_rect(0.0, top, width, band, SNAP_HINT)
            elif edge == "bottom":
                p.fill_rect(0.0, height - band, width, band, SNAP_HINT)

    def command_area_height(self) -> float:
        """Height the prompt and its feedback can ever take, in logical pixels.

        The **maximum**, not the current one: the log grows and shrinks as
        commands are run, and anything laying itself out around this -- the
        system-info panel, which is a Qt widget over the same corner -- would
        otherwise have to be told every time a line was printed, and would
        overlap the prompt in the window between the line appearing and the
        next relayout. `visible_log` is capped at `feedback`, so the ceiling is
        a constant and reserving it needs no upkeep.
        """
        line = self.command_line
        if not line.visible:
            return 0.0
        rows = max(int(getattr(line, "feedback", 0)), 0)
        return float(self.MARGIN + self.CMD_ROW_H * (1 + rows))

    def command_rect(self) -> Rect:
        """Where the prompt sits, for a host that wants to place a caret."""
        return self._cmd_rect

    # ── the command line ─────────────────────────────────────────────────
    def focus_field(self, field) -> None:
        """Give the caret to *field*, or take it away with ``None``.

        Taking the prompt's focus with it: two carets on screen is two places a
        keystroke could be going, and the user cannot tell which.
        """
        if field is not None:
            self.focus_command(False)
        self.focused_field = field

    def focus_command(self, focused: bool = True) -> None:
        """Give the prompt the keyboard, or take it away.

        Closing any open menu with it: a menu and a text cursor both claim the
        next keystroke, and the one that is drawn on top is not necessarily the
        one that would get it.
        """
        if focused:
            self.close_menus()
        self.command_line.set_focus(focused)

    def _cmd_cursor_at(self, x: float) -> int:
        """Character index under *x* on the prompt line.

        The chrome font is monospaced -- it is Menlo, and the whole panel's
        layout arithmetic already assumes a single advance width -- so this is
        division rather than a walk over glyph metrics.
        """
        advance = char_width(self.FONT_PT)
        origin = self._cmd_rect.x + self.MARGIN + advance * (len(PROMPT) + 1)
        return max(0, min(
            int(round((float(x) - origin) / max(advance, 1e-6))),
            len(self.command_line.text),
        ))

    def key_press(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Offer a key to the chrome. Returns whether it was consumed.

        Every host calls this before its own shortcuts, and the answer decides
        whether they run. Three things can take a key: an open menu takes
        Escape, a focused prompt takes everything, and an unfocused prompt takes
        Return -- which is how it gets focus without the mouse, and the only
        gesture a browser page can offer that costs nothing else.

        Parameters
        ----------
        key : int
            One of :mod:`chimol.host.keys`' constants, ``0`` for a key that only
            produces text.
        text : str
            The character produced, if any.
        modifiers : int
            A mask of :mod:`chimol.host.events`' ``*_MODIFIER`` values.
        """
        from ..host.keys import KEY_ENTER, KEY_ESCAPE, KEY_RETURN

        if key == KEY_ESCAPE and self._menus:
            self.close_menus()
            return True
        # Then the info panel. `help` fills it with something that covers most
        # of the viewport, and the only way to put it away was the command that
        # opened it -- so the reader had to leave the thing they were reading in
        # order to type. Escape is what every other panel here already answers
        # to, and it is what a reader tries first.
        #
        # After the menu and before the prompt: a menu drawn *over* the panel
        # must close first, and Escape must still be able to leave a focused
        # prompt rather than closing the panel behind it.
        if (key == KEY_ESCAPE and self.info_visible
                and self.focused_field is None and not self.command_line.focused):
            self.hide_info()
            return True
        # Then a floating window -- the Settings panel is one, and it had no way
        # to close from the keyboard at all. Topmost first, and only closable
        # ones: the object list and the mouse block are chrome, not dialogs.
        if key == KEY_ESCAPE and not self.command_line.focused:
            for win in reversed(self.windows):
                if win.visible and win.transient and not self._window_suppressed(win):
                    win.visible = False
                    self.persist_windows()
                    return True
        # A focused text field takes everything, exactly as the prompt does --
        # a search box with a caret in it must get the `r` that was typed
        # rather than the representation switching underneath.
        field = self.focused_field
        if field is not None:
            if key == KEY_ESCAPE:
                self.focus_field(None)
                return True
            if field is self.ui_scale_field and key in (KEY_RETURN, KEY_ENTER):
                self._commit_ui_scale_field()
                return True
            try:
                return bool(field.key(key, text, modifiers))
            except Exception:
                logger.debug("text field refused a key", exc_info=True)
                return False
        if self.command_line.focused:
            return self.command_line.key(key, text, modifiers)
        if key in (KEY_RETURN, KEY_ENTER) and self.command_line.visible:
            self.focus_command(True)
            return True
        return False

    def layout_wizard(self, width: int, height: int) -> None:
        """Place the wizard panel directly under the object list.

        Where PyMOL puts it: the wizard is a *block* in the internal GUI
        column, below the object list and above the mouse-mode block, so the
        thing you are being asked to do sits next to the objects you would do
        it to.
        """
        self._wizard_row_rects = []
        if not self.wizard_rows:
            self._wizard_rect = Rect(0, 0, 0, 0)
            return
        column = self.effective_column_width() or max(self._panel.w, 160.0)
        top = self._panel.y + self._panel.h + self.PAD
        panel_h = self.PAD + self.ROW_H * len(self.wizard_rows) + self.PAD
        x = width - column if self.docked else self._panel.x
        self._wizard_rect = Rect(x, top, column, panel_h)

        y = top + self.PAD
        for row in self.wizard_rows:
            self._wizard_row_rects.append((Rect(x, y, column, self.ROW_H), row))
            y += self.ROW_H

    def set_sequences(self, rows: Sequence[SequenceRow]) -> None:
        """Replace the sequences the strip shows."""
        self.sequences = list(rows)

    # ── the toolbar ──────────────────────────────────────────────────────
    TOOLBAR_H = 22.0

    def toolbar_height(self) -> float:
        """Height the toolbar takes from the top of the scene."""
        if not (self.menus_visible and self.toolbar_visible and self.toolbar):
            return 0.0
        return self.TOOLBAR_H

    def layout_toolbar(self, width: int, height: int) -> None:
        """Lay the buttons out left to right, under the menu bar."""
        self._toolbar_rects = []
        if not self.toolbar_height():
            return
        char_w = char_width(self.FONT_PT)
        x = self.PAD
        top = self.menubar_height()
        for label, command, note in self.toolbar:
            w = len(label) * char_w + 2 * self.MENU_PAD
            self._toolbar_rects.append(
                (Rect(x, top, w, self.TOOLBAR_H), label, command, note)
            )
            x += w + 2.0

    def _toolbar_hit(self, x: float, y: float):
        if not self.toolbar_height():
            return None
        for index, (rect, *_rest) in enumerate(self._toolbar_rects):
            if rect.contains(x, y):
                return index
        return None

    def press_toolbar(self, index: int) -> bool:
        """Run the button's command."""
        if not (0 <= index < len(self._toolbar_rects)):
            return False
        _rect, _label, command, _note = self._toolbar_rects[index]
        if not command or self._run_command is None:
            return False
        self._run_command(command)
        return True

    def _paint_toolbar(self, p) -> None:
        if not self.toolbar_height():
            return
        width = float(self._width) - self.effective_column_width()
        top = self.menubar_height()
        p.fill_rect(0.0, top, max(width, 1.0), self.TOOLBAR_H, TOOLBAR_BG)
        hover = self._hover.row if self._hover.kind == "toolbar" else -1
        for index, (rect, label, command, _note) in enumerate(self._toolbar_rects):
            checked = self.toolbar_checked(command)
            if checked:
                # A pressed-in button, not merely a brighter label: the whole
                # point is to answer "is this on?" at a glance, and a colour
                # shift alone is invisible next to the hover highlight.
                p.fill_rect(rect.x, rect.y, rect.w, rect.h, TOOLBAR_ON_BG)
            if index == hover:
                p.fill_rect(rect.x, rect.y, rect.w, rect.h, TOOLBAR_HOVER_BG)
            p.text(rect.x, rect.y, rect.w, rect.h, ALIGN_CENTER, label,
                   TOOLBAR_ON_FG if checked else TOOLBAR_FG)
            if checked:
                # An underline as well as the fill, so the state survives a
                # colour-blind reader and a washed-out projector.
                p.fill_rect(rect.x + 3.0, rect.y + rect.h - 2.0,
                            max(rect.w - 6.0, 1.0), 1.0, TOOLBAR_ON_FG)

    # ── the menu bar ─────────────────────────────────────────────────────
    MENUBAR_H = 20.0

    def menubar_height(self) -> float:
        """Height the menu bar takes from the top of the scene."""
        if not (self.menus_visible and self.menubar_visible and self.menubar):
            return 0.0
        return self.MENUBAR_H

    def layout_menubar(self, width: int, height: int) -> None:
        """Lay the titles out left to right along the top."""
        self._menubar_rects = []
        if not self.menubar_height():
            return
        char_w = char_width(self.FONT_PT)
        x = self.PAD
        for title, entries in self.menubar:
            w = len(title) * char_w + 2 * self.MENU_PAD
            self._menubar_rects.append((Rect(x, 0.0, w, self.MENUBAR_H), title, entries))
            x += w

    def _menubar_hit(self, x: float, y: float):
        """The bar entry under ``(x, y)``, or ``None``."""
        if not self.menubar_height():
            return None
        for index, (rect, _title, _entries) in enumerate(self._menubar_rects):
            if rect.contains(x, y):
                return index
        return None

    def open_context_menu(self, x: float, y: float, target: str = "sele") -> bool:
        """Open the object menus at the cursor -- a right-click in the scene.

        PyMOL's own mouse-mode block promises this: the `SnglClk` row reads
        `R  Menu`. The five per-object menus were reachable only from the object
        list's buttons, so the promise on screen was not kept anywhere.

        Parameters
        ----------
        x, y : float
            Where to open it.
        target : str, optional
            What the entries act on -- the picked object, or `sele`.
        """
        self.close_menus()
        entries = tuple(
            MenuEntry(title, None, "", children=tuple(rows))
            for _key, title, rows in OBJECT_MENUS
        )
        self._open_menu(f"{target}:", target, entries, x, y)
        return True

    def open_menubar(self, index: int) -> bool:
        """Drop the menu at *index* open under its title."""
        if not (0 <= index < len(self._menubar_rects)):
            return False
        rect, title, entries = self._menubar_rects[index]
        self.close_menus()
        if not entries:
            return False
        self._menubar_open = index
        self._open_menu(f"{title}:", "", entries, rect.x, rect.y + rect.h)
        return True

    def _paint_menubar(self, p) -> None:
        """Draw the bar; the open title stays lit while its menu is down."""
        if not self.menubar_height():
            return
        width = float(self._width) - self.effective_column_width()
        p.fill_rect(0.0, 0.0, max(width, 1.0), self.MENUBAR_H, MENUBAR_BG)
        hover = self._hover.row if self._hover.kind == "menubar" else -1
        for index, (rect, title, _entries) in enumerate(self._menubar_rects):
            lit = index == self._menubar_open or index == hover
            if lit:
                p.fill_rect(rect.x, rect.y, rect.w, rect.h, MENUBAR_SEL_BG)
            p.text(rect.x, rect.y, rect.w, rect.h, ALIGN_CENTER, title,
                   MENUBAR_FG if lit else MENUBAR_DIM_FG)

    def top_band_height(self) -> float:
        """Everything the chrome takes off the top of the scene.

        The menu bar and the sequence strip stack, and the renderer needs one
        number for where the 3-D view starts -- asking for the strip alone put
        the molecule under the bar.
        """
        return self.menubar_height() + self.toolbar_height() + self.sequence_height()

    def effective_column_width(self) -> float:
        """What the object column actually takes, folded or not.

        Every place that reserved `column_width` has to ask this instead, or a
        folded panel keeps its space and the fold does nothing visible -- which
        is the whole point of folding it.
        """
        if not (self.visible and self.docked):
            return 0.0
        return self.column_width

    def sequence_height(self) -> float:
        """Height the strip takes from the top of the scene.

        Zero when there is nothing to show. PyMOL's ``seq_view_overlay`` is off
        by default, meaning the sequence gets a band of its own rather than
        covering the molecule -- so this is height the scene does not get, and
        the renderer has to know it.
        """
        if not (self.sequence_visible and self.sequences):
            return 0.0
        # Bounded: the strip is reference material, and an integrative model
        # with a row per chain took the whole viewport and left no molecule.
        # A third of the height at most, whatever the host hands over.
        rows = min(len(self.sequences), self.max_sequence_rows())
        if len(self.sequences) > rows:
            rows += 1                      # the "and N more" line
        return self.SEQ_ROW_H * (rows + 1) + self.SEQ_BAR_H + 2 * self.PAD

    def max_sequence_rows(self) -> int:
        """How many rows the strip may draw at the current height."""
        room = max(float(self._height) * self.SEQ_MAX_FRACTION, self.SEQ_ROW_H)
        return max(int((room - self.SEQ_BAR_H - 2 * self.PAD) // self.SEQ_ROW_H) - 1, 1)

    def layout_sequence(self, width: int, height: int) -> None:
        """Place the strip across the top of the scene, left of the column."""
        strip_h = self.sequence_height()
        scene_w = width - self.effective_column_width()
        # Under the menu bar, not over it.
        self._seq_strip = Rect(
            0.0, self.menubar_height() + self.toolbar_height(),
            max(scene_w, 1.0), strip_h,
        )
        self._seq_rows = []
        if not strip_h:
            return

        char_w = char_width(self.FONT_PT)
        name_w = max(
            [len(row.name) for row in self.sequences] + [4]
        ) * char_w + self.PAD
        self._seq_origin = self.PAD + name_w
        # From the strip's own top, not from the window's: the strip moved down
        # when the toolbar arrived, and rows placed from an absolute origin
        # stayed where they were -- drawn over the toolbar while the strip's
        # background sat correctly below it.
        y = self._seq_strip.y + self.PAD + self.SEQ_ROW_H
        for _row in self.sequences[: self.max_sequence_rows()]:
            self._seq_rows.append(
                Rect(self._seq_origin, y, self._seq_strip.w - self._seq_origin,
                     self.SEQ_ROW_H)
            )
            y += self.SEQ_ROW_H
        if max(self.sequence_total, len(self.sequences)) > len(self._seq_rows):
            # Leave the "and N more" line its own row, or the scrollbar is
            # drawn straight over it.
            y += self.SEQ_ROW_H

        # The scrollbar, under the rows. Without it a long sequence simply ends
        # at the edge of the window with nothing to say there is more of it.
        track_w = self._seq_strip.w - self._seq_origin - self.PAD
        self._seq_track = Rect(self._seq_origin, y + 2, max(track_w, 1.0), self.SEQ_BAR_H)
        longest = max((len(row.codes) for row in self.sequences), default=0)
        visible = self.visible_columns()
        if longest > visible > 0:
            span = track_w * visible / float(longest)
            offset = track_w * self._seq_scroll / float(longest)
            self._seq_thumb = Rect(
                self._seq_track.x + offset, self._seq_track.y,
                max(span, 12.0), self.SEQ_BAR_H,
            )
        else:
            self._seq_thumb = Rect(self._seq_track.x, self._seq_track.y,
                                   self._seq_track.w, self.SEQ_BAR_H)

    def sequence_strip_contains(self, x: float, y: float) -> bool:
        """Whether ``(x, y)`` is over the sequence strip."""
        return bool(self.sequence_visible and self._seq_strip.contains(x, y))

    def _emit_select(self, row, columns, additive: bool) -> None:
        """Report a strip selection in the *object's* terms.

        A row is one chain, so its columns are a slice of the object's residues
        -- ``row.residue_indices`` is the map, and without it a click on chain
        B's third residue would select the object's third, which is chain A's.
        The row is identified by ``object_id`` rather than by its label for the
        same reason: the label now carries the chain (`1f5n/A`), and two
        objects may share a name where they cannot share an id.
        """
        if self.on_select is None:
            return
        mapping = getattr(row, "residue_indices", None)
        if mapping:
            # Negative entries are the chain-id markers: columns that name no
            # residue. Clicking one must select nothing, not residue -1.
            indices = [
                int(mapping[c]) for c in columns
                if 0 <= int(c) < len(mapping) and int(mapping[c]) >= 0
            ]
        else:
            indices = [int(c) for c in columns]
        self.on_select(row.object_id or row.name, indices, additive)

    def clear_selection(self) -> None:
        """Drop every selected residue and tell whoever is listening.

        Clicking empty space clears the selection, as it does in PyMOL: a
        selection you cannot see the edges of is one you cannot get rid of.
        """
        changed = any(row.selected for row in self.sequences)
        for row in self.sequences:
            row.selected = set()
        if changed and self.on_select is not None:
            for row in self.sequences:
                try:
                    self._emit_select(row, [], False)
                except Exception:
                    pass

    def visible_columns(self) -> int:
        """How many residues fit across the strip."""
        char_w = char_width(self.FONT_PT)
        return max(int((self._seq_strip.w - self._seq_origin - self.PAD) / char_w), 1)

    def max_scroll(self) -> int:
        """Return the furthest the sequence can be scrolled."""
        longest = max((len(row.codes) for row in self.sequences), default=0)
        return max(longest - self.visible_columns(), 0)

    def scroll_sequence(self, columns: int) -> bool:
        """Scroll by *columns*; returns whether anything moved."""
        before = self._seq_scroll
        self._seq_scroll = min(max(self._seq_scroll + int(columns), 0), self.max_scroll())
        if self._seq_scroll != before:
            self.layout_sequence(self._width, self._height)
        return self._seq_scroll != before

    def sequence_index_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Return ``(row, residue index)`` under the cursor, or ``None``."""
        char_w = char_width(self.FONT_PT)
        for index, rect in enumerate(self._seq_rows):
            if not rect.contains(x, y):
                continue
            column = int((x - rect.x) / char_w) + self._seq_scroll
            row = self.sequences[index]
            if 0 <= column < len(row.codes):
                return index, column
            return None
        return None

    def _seek_to(self, x: float) -> None:
        """Jump the movie to the frame under the cursor."""
        track = self._timeline_track
        if track.w <= 0:
            return
        _current, total = self.state
        span = max(int(total), 1)
        fraction = min(max((x - track.x) / track.w, 0.0), 1.0)
        frame = int(round(fraction * (span - 1))) + 1
        if frame != self.state[0]:
            self.state = (frame, span)
            self.layout_block(self._width, self._height)
            if self.on_frame_change is not None:
                try:
                    self.on_frame_change(frame)
                except Exception:
                    pass

    def _scroll_to(self, x: float) -> None:
        """Put the thumb under the cursor and scroll to match."""
        track = self._seq_track
        if track.w <= 0:
            return
        fraction = min(max((x - track.x) / track.w, 0.0), 1.0)
        target = int(round(fraction * self.max_scroll()))
        if target != self._seq_scroll:
            self._seq_scroll = target
            self.layout_sequence(self._width, self._height)

    def _toggle_residue(self, row_index: int, column: int) -> None:
        """Flip one residue in and out of the selection.

        PyMOL's ``Seeker`` toggles on a click: a selected column is deselected,
        an unselected one selected. The whole selected set is emitted, because
        whoever mirrors the strip into the 3-D view replaces, not merges.
        """
        row = self.sequences[row_index]
        if column in row.selected:
            row.selected.discard(column)
        else:
            row.selected.add(column)
        if self.on_select is not None:
            try:
                self._emit_select(row, sorted(row.selected), False)
            except Exception:
                pass

    def _select_range(self, row_index: int, start: int, end: int, additive: bool) -> None:
        """Select the residues between *start* and *end* on one row."""
        row = self.sequences[row_index]
        lo, hi = (start, end) if start <= end else (end, start)
        chosen = set(range(lo, hi + 1))
        row.selected = (row.selected | chosen) if additive else chosen
        if self.on_select is not None:
            try:
                self._emit_select(row, sorted(row.selected), additive)
            except Exception:
                pass

    @property
    def movie_panel_visible(self) -> bool:
        """Whether there is a movie to scrub, and therefore a panel for it.

        PyMOL's own rule, from ``MovieGetPanelHeight`` (``layer1/Movie.cpp``):
        the panel has zero height unless a movie is defined or the scene has
        more than one frame. In chimol ``mset`` sets the frame count, so the two
        conditions collapse into one.

        Without it a single-state PDB -- the ordinary case -- got a full-width
        scrubber and a nine-button transport for a timeline of one, which is the
        loudest thing in the panel and controls nothing.
        """
        return int(self.state[1]) > 1

    def layout_block(self, width: int, height: int) -> None:
        """Place the mouse-mode block and the movie transport, bottom-right.

        Where PyMOL puts them, and for the same reason: it is reference material
        you glance at without leaving the view, so it belongs in the view.
        """
        char_w = char_width(self.FONT_PT)
        line_h = self.BLOCK_ROW_H
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        # Wide enough for **both** rows, not just the widest-looking one. The
        # binding grid needs `label + 4 cells`; the title row needs
        # `label + one cell` of right-aligned "Mouse Mode" and then the mode
        # *name* beside it -- and the longest of those is 16 characters, one
        # more than the grid leaves. Sized from the grid alone (as it was), the
        # title row overflowed by a character in nine of the ten modes, so
        # "3-Button Viewing" drew as "3-Button Viewin" and the `Wheel` heading
        # lost its `l`. Clipped at the window edge it read as a rendering fault
        # rather than a window a character too narrow.
        widest_mode = max((len(name) for name in MODE_NAMES.values()), default=0)
        block_w = self.PAD + max(
            label_w + 4 * cell_w,
            label_w + cell_w + widest_mode * char_w,
        ) + self.PAD
        # title, the L/M/R/Wheel heading, six binding rows, selecting, state
        rows = len(rows_for(self.mouse_mode))
        movie = self.movie_panel_visible
        # +6, not +5: the stride and averaging sliders take a line of their own
        # under the cells that label them. Sized here rather than overlapped --
        # laid on the line below without growing the block, the grooves landed
        # on the timeline track and every press went to the scrubber instead.
        block_h = self.PAD + line_h * (rows + 6) + self.PAD
        if movie:
            block_h += self.SEQ_BAR_H + 4 + self.ROW_H + self.PAD

        if self.docked:
            column = self.effective_column_width()
            block_w = max(block_w, column)
            self._block = Rect(
                width - column, height - block_h, block_w, block_h
            )
        else:
            # The mouse block is a window: auto-sized, glued bottom-right by
            # its anchor until the user drags it, its rectangle the window's
            # body.
            win = self.mouse_window
            win.w = block_w
            win.h = self.WINDOW_TITLE_H + block_h
            self._apply_window_anchor(win, width, height)
            if win.visible and not win.collapsed:
                self._block = Rect(
                    win.x, win.y + self.WINDOW_TITLE_H, block_w, block_h
                )
            else:
                self._block = Rect(0, 0, 0, 0)
        if self._block.w <= 0:
            # A hidden or folded mouse window leaves no live hit rectangles;
            # its sub-rects are all placed relative to the block and would
            # otherwise pile up clickable ghosts at the origin.
            self._mode_rect = Rect(0, 0, 0, 0)
            self._selecting_rect = Rect(0, 0, 0, 0)
            self._stride_rect = Rect(0, 0, 0, 0)
            self._average_rect = Rect(0, 0, 0, 0)
            self._stride_groove = Rect(0, 0, 0, 0)
            self._average_groove = Rect(0, 0, 0, 0)
            self._timeline_track = Rect(0, 0, 0, 0)
            self._timeline_thumb = Rect(0, 0, 0, 0)
            self._movie_rects = []
            return
        self._mode_rect = Rect(
            self._block.x + self.PAD, self._block.y + self.PAD, block_w, line_h
        )
        # The "Selecting" row, two lines under the last binding row (the title
        # and the "Buttons" header come first). PyMOL cycles the selection
        # level from this line, and until it was hit-testable the word was
        # decorative -- it said "Residues" and residues was all a click could
        # ever select.
        self._selecting_rect = Rect(
            self._block.x,
            self._block.y + self.PAD + line_h * (rows + 2),
            block_w,
            line_h,
        )

        # Stride and average share the line under the state.
        stride_y = self._block.y + self.PAD + line_h * (rows + 4)
        char_w = char_width(self.FONT_PT)
        split = self.PAD + 10.0 * char_w + 5 * char_w      # label column + one cell
        self._stride_rect = Rect(self._block.x, stride_y, split, line_h)
        self._average_rect = Rect(
            self._block.x + split, stride_y, block_w - split, line_h
        )
        # A groove under each. Both were click-to-step only, which is fine for
        # 1 -> 2 and useless for 1 -> 30: a smoothing window is a value people
        # sweep until the jitter goes, not click at thirty times.
        slider_y = stride_y + line_h
        groove_w = (block_w - 3 * self.PAD) * 0.5
        self._stride_groove = Rect(
            self._block.x + self.PAD, slider_y, groove_w, line_h
        )
        self._average_groove = Rect(
            self._block.x + 2 * self.PAD + groove_w, slider_y, groove_w, line_h
        )

        self._movie_rects = []
        if not movie:
            # Nothing to play: no track, no thumb, no buttons -- and an empty
            # rect fails `contains`, so the hit tests fall through by themselves.
            self._timeline_track = Rect(0, 0, 0, 0)
            self._timeline_thumb = Rect(0, 0, 0, 0)
            return

        # The timeline runs the width of the block, above the transport: the
        # state counter says *where* you are, and this is how you get somewhere
        # else without stepping frame by frame.
        self._timeline_track = Rect(
            self._block.x + self.PAD,
            self._block.y + block_h - self.PAD - self.ROW_H - self.SEQ_BAR_H - 4,
            block_w - 2 * self.PAD,
            self.SEQ_BAR_H,
        )
        current, total = self.state
        span = max(int(total), 1)
        fraction = (max(int(current), 1) - 1) / max(span - 1, 1)
        thumb_w = max(self._timeline_track.w / span, 10.0)
        self._timeline_thumb = Rect(
            self._timeline_track.x + fraction * (self._timeline_track.w - thumb_w),
            self._timeline_track.y, thumb_w, self.SEQ_BAR_H,
        )

        # The transport sits on the block's last line, spread across its width.
        self._movie_rects = []
        count = len(MOVIE_BUTTONS)
        button_w = min(28.0, (block_w - 2 * self.PAD) / count - 2)
        gap = ((block_w - 2 * self.PAD) - button_w * count) / max(count - 1, 1)
        bx = self._block.x + self.PAD
        by = self._block.y + block_h - self.PAD - self.ROW_H
        for glyph, command in MOVIE_BUTTONS:
            self._movie_rects.append((Rect(bx, by, button_w, self.ROW_H), command))
            bx += button_w + gap

    @property
    def block_rect(self) -> Rect:
        """Where the mouse-mode block currently sits."""
        return self._block

    def minimum_column_width(self) -> float:
        """Return the narrowest the column can be and still show what it holds.

        Measured from the contents rather than fixed: the object rows need the
        widest name plus five boxes, the mouse-mode block needs its label column
        and four action columns, and the transport needs a clickable target for
        each of its nine buttons. A constant floor either cuts one of them off
        or stops the splitter well before it needs to.
        """
        char_w = char_width(self.FONT_PT)
        rows_w = (
            self.PAD + self._name_width + self.PAD
            + self.BUTTON_W * len(OBJECT_MENUS) + self.PAD
        )
        # Same two rows as `layout_block`, and it has to agree with it: the
        # docked column and the floating window show identical content, so a
        # floor derived from a different formula makes one of them clip.
        widest_mode = max((len(name) for name in MODE_NAMES.values()), default=0)
        block_w = self.PAD + max(
            10.0 * char_w + 4 * (5 * char_w),
            10.0 * char_w + 5 * char_w + widest_mode * char_w,
        ) + self.PAD
        transport_w = 2 * self.PAD + self.MIN_BUTTON_W * len(MOVIE_BUTTONS)
        return max(rows_w, block_w, transport_w)

    def cycle_mouse_mode(self) -> None:
        """Step to the next mode in the ring, as PyMOL's mode line does.

        Within the ring, not through all ten modes: a viewing ring steps
        viewing -> editing -> viewing and never lands on lights or maestro
        unless the ring is changed, which is the point of having one.
        """
        self.mouse_mode = next_mode(self.mouse_mode, self.mouse_ring)

    def cycle_selecting(self, back: bool = False) -> None:
        """Step the selection level, and tell the viewer through the setting.

        The level is a *setting* (`mouse_selection_mode`), not panel state, so
        this goes out as a command rather than being written here: typing
        ``set mouse_selection_mode, chains`` and clicking the row have to end
        up in the same place, and the word drawn on this line is read back from
        the viewer. Right-click steps back, as the stride and average rows do.
        """
        from ..mouse_modes import SELECTION_LEVELS, normalize_selection_level

        current = normalize_selection_level(self.selecting)
        step = -1 if back else 1
        index = (SELECTION_LEVELS.index(current) + step) % len(SELECTION_LEVELS)
        wanted = SELECTION_LEVELS[index]
        if self._run_command is None:
            # No command sink (a bare panel in a test): still move, so the row
            # is not dead where the rest of the block works.
            self.selecting = wanted
            return
        self._run_command(f"set mouse_selection_mode, {wanted}")

    @property
    def panel_rect(self) -> Rect:
        """Where the panel currently sits."""
        return self._panel

    # ── hit testing ──────────────────────────────────────────────────────
    def hit_test(self, x: float, y: float) -> Hit:
        """Return what is under ``(x, y)``, menus first.

        Menus are tested before the panel and the panel before the scene, which
        is simply front-to-back: an open menu is drawn over everything, so it
        must also receive the click that lands on it.
        """
        # The tour bubble is drawn over the chrome and takes its own clicks, so
        # it is tested before everything except an open menu -- the tour points
        # *at* menus, and a bubble that swallowed the click it just asked for
        # would be a trap.
        depth, entry = self._menu_at(x, y)
        if depth is None:
            if self._tour_next_rect.contains(x, y):
                return Hit("tour", key="next")
            if self._tour_close_rect.contains(x, y):
                return Hit("tour", key="close")
            if self._tour_rect.contains(x, y):
                return Hit("tour")
            bar = self._menubar_hit(x, y)
            if bar is not None:
                return Hit("menubar", row=bar)
            button = self._toolbar_hit(x, y)
            if button is not None:
                return Hit("toolbar", row=button)
            # Windows float over the panels, so they are tested before them and
            # after an open menu -- a menu is drawn over everything.
            window_hit = self._window_hit(x, y)
            if window_hit is not None:
                return window_hit
            # The chrome-size slider in the status band.
            if self._ui_scale_rect.contains(x, y):
                return Hit("uiscale")
            # The info panel, *below* the windows and above the scene. It had no
            # hit kind at all, so a press over a page of `help` fell through to
            # the camera and rotated the molecule under the text being read.
            #
            # Order matters and cost a test: tried above the windows first, and
            # a `help` listing tall enough to reach the mouse block then swallowed
            # every click meant for it -- the mode line stopped cycling. Hit
            # order has to match paint order, and the windows are painted last.
            if self.info_contains(x, y):
                return Hit("info")
        if depth is not None:
            if entry is None:
                return Hit("menu")
            return Hit("menu", entry=entry, submenu=entry.is_submenu)

        # Before the panel's own visibility gate: the prompt is drawn when the
        # panel is hidden, and a control that draws and cannot be clicked is
        # worse than one that is not drawn at all.
        if self.command_line.visible and self._cmd_rect.contains(x, y):
            return Hit("command")

        if not self.visible:
            return Hit("")

        if self.sequence_visible and self._seq_track.contains(x, y):
            return Hit("scrollbar")

        if self.sequence_visible and self._seq_strip.contains(x, y):
            found = self.sequence_index_at(x, y)
            if found is not None:
                return Hit("residue", row=found[0], key=str(found[1]))
            return Hit("sequence")

        for index, (rect, row) in enumerate(self._wizard_row_rects):
            if rect.contains(x, y):
                # A title row takes the click and does nothing, so a stray
                # press on the wizard's banner does not fall through to the
                # scene and start rotating the molecule behind it.
                return Hit("wizard", row=index, key=row.kind)
        if self._wizard_rect.contains(x, y):
            return Hit("wizard")

        if self.docked and self._splitter.contains(x, y):
            return Hit("splitter")

        if self._mode_rect.contains(x, y):
            return Hit("mode")
        if self._selecting_rect.contains(x, y):
            return Hit("selecting")
        if self._timeline_track.contains(x, y):
            return Hit("timeline")
        if self._stride_rect.contains(x, y):
            return Hit("stride")
        if self._stride_groove.contains(x, y):
            return Hit("playback_slider", key="stride")
        if self._average_groove.contains(x, y):
            return Hit("playback_slider", key="average")
        if self._average_rect.contains(x, y):
            return Hit("average")
        for rect, command in self._movie_rects:
            if rect.contains(x, y):
                return Hit("movie", key=command)
        if self._block.contains(x, y):
            return Hit("block")     # reference text: takes the click, does nothing

        for rect in self._row_rects:
            if rect.contains(x, y):
                # The same row/eye/button resolution the windowed panel uses,
                # so docked and windowed clicks cannot drift apart.
                return self._panel_sub_hit(x, y)
        return Hit("")

    def _menu_at(self, x: float, y: float) -> tuple[int | None, MenuEntry | None]:
        """Return ``(depth, entry)`` for the deepest open menu under the cursor.

        Deepest first, because a child is drawn over its parent and, on a window
        too narrow to hold the chain, may still be sitting on top of it.
        ``entry`` is ``None`` when the cursor is on the menu but not on a row --
        the title, the padding, or the gap a separator leaves.
        """
        for depth in range(len(self._menus) - 1, -1, -1):
            menu = self._menus[depth]
            for rect, entry in menu.item_rects:
                # A scrolled-out row keeps its rectangle -- it is the same list
                # the painter walks -- so the visibility test has to be here as
                # well, or a menu would take clicks through its own title.
                if rect.contains(x, y) and self._menu_row_visible(menu, rect):
                    return depth, entry
            if menu.rect.contains(x, y):
                return depth, None
        return None, None

    def wants(self, x: float, y: float) -> bool:
        """Whether the panel would take a click here, rather than the camera.

        The whole reason a mouse press has to be offered to the panel first: a
        click that opens a menu must not also start rotating the molecule.
        """
        return bool(self.hit_test(x, y).kind)

    # ── interaction ──────────────────────────────────────────────────────
    def drag(self, x: float, y: float) -> bool:
        """Continue a splitter drag. Returns whether anything moved."""
        if self._dragging_ui_scale:
            self._set_ui_scale_from(x)
            return True
        if (
            self._window_drag is not None
            or self._window_resize is not None
            or self._window_body_drag is not None
            # The chrome-size slider. Without it here the host never calls
            # `drag` for this gesture -- it gates on `is_dragging` -- so the
            # slider took a press and then ignored every movement, which reads
            # as an unresponsive control rather than a missing case.
            or self._dragging_ui_scale
        ):
            return self._drag_window(x, y)

        if self._dragging_timeline:
            self._seek_to(x)
            return True

        if self._dragging_thumb:
            self._scroll_to(x)
            return True

        if self._seq_drag is not None:
            found = self.sequence_index_at(x, y)
            if found is not None and found[0] == self._seq_drag[0]:
                self._select_range(self._seq_drag[0], self._seq_drag[1], found[1],
                                   additive=self._seq_drag_additive)
                return True
            return False

        if not self._dragging_splitter:
            return False
        # The upper bound has to clear the lower one on a narrow window, or the
        # clamp inverts and the column snaps to the *widest* it may be.
        floor = self.minimum_column_width()
        widest = max(self._width * self.MAX_COLUMN_FRACTION, floor)
        self.column_width = min(max(self._width - x, floor), widest)
        self.layout(self._width, self._height)
        return True

    def release(self) -> None:
        """End whichever drag the panel had started."""
        self._dragging_splitter = False
        self._seq_drag = None
        self._seq_drag_additive = False
        self._dragging_thumb = False
        self._dragging_timeline = False
        self._dragging_ui_scale = False
        self._dragging_playback = None
        self._ui_scale_track = None
        if self._window_body_drag is not None:
            win = self.window(self._window_body_drag)
            self._window_body_drag = None
            if win is not None and win.on_release is not None:
                # Where a panel that batched work during the drag does it: a
                # contour rebuild belongs here, not once per mouse move.
                try:
                    win.on_release()
                except Exception:
                    logger.debug("window body refused a release", exc_info=True)
        if self._window_drag is not None or self._window_resize is not None:
            # The drag is over; this placement is the one worth keeping.
            self._window_drag = None
            self._window_resize = None
            self.persist_windows()
        self._window_drag = None
        self._window_resize = None
        self._snap_hint = ()
        self._snap_hint_keys = set()
        self._drag_followers = []

    def is_dragging(self) -> bool:
        """Whether a drag the panel owns is in progress."""
        return (
            self._dragging_splitter
            or self._seq_drag is not None
            or self._dragging_thumb
            or self._dragging_timeline
            or self._window_drag is not None
            or self._window_resize is not None
            or self._window_body_drag is not None
            # The playback sliders. The host gates every drag on this, so a
            # slider missing from the set takes a press and then ignores every
            # movement -- which reads as an unresponsive control.
            or self._dragging_playback is not None
        )

    def mouse_move(self, x: float, y: float) -> bool:
        """Track hover, opening and collapsing submenus. Returns whether to redraw."""
        hit = self.hit_test(x, y)
        changed = hit != self._hover
        self._hover = hit
        # The hover tooltip: what the thing under the cursor does, in words.
        # Suppressed while a menu is open -- the menu rows carry their own
        # meaning and a box floating beside them reads as a second menu.
        tip = None if self._menus else self._tooltip_text_at(x, y, hit)
        new_tip = (x, y, tip) if tip else None
        if new_tip != self._tooltip:
            self._tooltip = new_tip
            changed = True
        # With a menu already down, sliding along the bar opens the next one --
        # every menu bar does this, and without it each title has to be clicked.
        if self._menus and hit.kind == "menubar" and hit.row != self._menubar_open:
            return self.open_menubar(hit.row) or changed
        if self._menus:
            changed = self._track_menu_hover(x, y) or changed
        return changed

    #: What each mouse-mode abbreviation means, for the block's hover tooltip.
    #: PyMOL's own vocabulary, spelled out.
    MODE_ACTION_WORDS: dict[str, str] = {
        "Rota": "rotate the scene",
        "Move": "translate in the view plane",
        "MovZ": "translate along the view axis",
        "Slab": "thicken or thin the slab",
        "MovS": "move the slab",
        "MvSZ": "move slab and zoom",
        "+Box": "box-select: add",
        "-Box": "box-select: subtract",
        "Clip": "move the clipping planes",
        "PkAt": "pick an atom",
        "Pk1": "pick the first atom",
        "Sele": "make the click the selection",
        "Orig": "set the origin",
        "Cent": "centre the view",
        "Menu": "open the context menu",
        "+/-": "toggle in or out of the selection",
        "-": "nothing",
    }

    def _tooltip_text_at(self, x: float, y: float, hit: Hit) -> str | None:
        """The hover tooltip for whatever is under the cursor, or ``None``."""
        # The info panel first: it is a listing of names, and what a reader
        # wants from a name is what it does.
        if self.info_contains(x, y) and self.info_describe is not None:
            token = self.info_token_at(x, y)
            if token:
                try:
                    return self.info_describe(token)
                except Exception:  # noqa: BLE001 - a tooltip is a convenience
                    logger.debug("info describe failed", exc_info=True)
            return None
        # Windows first, matching the hit order: their bodies know their own
        # controls, and the title bar's affordances are the same everywhere.
        for win in reversed(self.windows):
            if not win.visible or self._window_suppressed(win):
                continue
            frame = self.window_frame(win)
            if not frame.contains(x, y):
                continue
            if y <= frame.y + self.WINDOW_TITLE_H:
                right = frame.x + frame.w
                if win.closable and x >= right - self.WINDOW_TITLE_H:
                    return "close this window (reopen it from the menus)"
                if x <= frame.x + self.WINDOW_TITLE_H:
                    return "fold the window to its title bar"
                return ("drag to move -- windows stuck to this one follow; "
                        "shift-drag moves it alone; drop on an edge or "
                        "another window to stick")
            if win.on_tooltip is not None:
                try:
                    tip = win.on_tooltip(x, y, self.window_body(win))
                except Exception:
                    tip = None
                if tip:
                    return str(tip)
            break

        if hit.kind == "toolbar":
            for rect, _label, _command, note in self._toolbar_rects:
                if rect.contains(x, y):
                    return note or None
            return None
        if hit.kind == "eye":
            return "show or hide this object in the 3-D view"
        if hit.kind == "name":
            return ("click to make this the active object; the eye shows or "
                    "hides it; right-click for its action menu")
        if hit.kind == "button":
            return {
                "A": "Actions: presets, zoom, rename, delete…",
                "S": "Show a representation on this object",
                "H": "Hide a representation",
                "L": "Labels",
                "C": "Colour this object",
            }.get(hit.key)
        if hit.kind == "mode":
            return "click to cycle the mouse mode"
        if hit.kind == "selecting":
            return ("what a viewport click selects; click to cycle "
                    "(right-click steps back)")
        if hit.kind == "stride":
            return "play every Nth frame; click to raise, right-click to lower"
        if hit.kind == "average":
            return "smooth playback over N frames; right-click lowers it"
        if hit.kind == "timeline":
            return "drag to scrub through the trajectory"
        if hit.kind == "movie":
            return {
                "mplay": "play", "mstop": "stop", "frame first": "first frame",
                "backward": "step back", "forward": "step forward",
                "frame last": "last frame", "mtoggle": "play / stop",
            }.get(str(hit.key), str(hit.key))
        if hit.kind == "block":
            return self._block_cell_tooltip(x, y)
        if hit.kind == "command":
            return "type a command; Return runs it, Tab completes, Up recalls"
        if hit.kind == "splitter":
            return "drag to resize the panel column"
        return None

    def _block_cell_tooltip(self, x: float, y: float) -> str | None:
        """Spell out the mouse-binding cell under the cursor."""
        block = self._block
        if not block.contains(x, y):
            return None
        char_w = char_width(self.FONT_PT)
        line_h = self.BLOCK_ROW_H
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        row = int((y - (block.y + self.PAD)) // line_h)
        rows = rows_for(self.mouse_mode)
        # Row 0 is the title, row 1 the L/M/R/Wheel header; bindings follow.
        if row < 2 or row - 2 >= len(rows):
            return "the mouse bindings of the current mode, per button and key"
        label, cells = rows[row - 2]
        column = int((x - (block.x + self.PAD + label_w)) // cell_w)
        buttons = ("left", "middle", "right", "wheel")
        if 0 <= column < len(cells):
            word = str(cells[column])
            meaning = self.MODE_ACTION_WORDS.get(word, word)
            key = label.strip().rstrip(":")
            hold = "" if key in ("& Keys",) else f"{key} + "
            return f"{hold}{buttons[column]}: {meaning}"
        return f"bindings while holding {label.strip()}"

    def _track_menu_hover(self, x: float, y: float) -> bool:
        """Open the submenu under the cursor and close the branch it left.

        A submenu opening on hover is only half of the behaviour; PyMOL's
        ``PopUp`` drag also *frees the child* the moment the cursor moves to
        another row of the parent, and walks back up when the cursor re-enters
        it. Without that half, every submenu passed over stayed on screen and
        the menu became a pile of overlapping boxes.

        Returns whether anything opened or closed.
        """
        depth, entry = self._menu_at(x, y)
        if depth is None:
            # Off the menus -- but not off the *gap between* them. A submenu
            # opens beside its parent with `CHILD_GAP` of nothing in between, so
            # the straight line from the parent's row to the child's first item
            # crosses pixels that belong to neither menu. Collapsing on those
            # closed the child under the cursor on its way there, which made
            # every submenu unreachable by the obvious gesture.
            #
            # So the branch still collapses when the cursor genuinely leaves --
            # into the scene, into the object list -- and tolerates the seam.
            if self._within_menu_reach(x, y):
                return False
            return self._collapse_to(1)
        if entry is not None and entry.is_submenu:
            child = self._menus[depth + 1] if len(self._menus) > depth + 1 else None
            if child is not None and child.owner is entry:
                return self._collapse_to(depth + 2)   # its own children, though
            self._collapse_to(depth + 1)
            self._open_submenu(entry)
            return True
        return self._collapse_to(depth + 1)

    def _within_menu_reach(self, x: float, y: float) -> bool:
        """Whether ``(x, y)`` is inside the open menus' bounds, plus the seam.

        Parameters
        ----------
        x, y : float
            Cursor position, in logical pixels.

        Returns
        -------
        bool
            ``True`` for a point between two open menus -- the ``CHILD_GAP``
            seam a diagonal move across has to survive -- and ``False`` for one
            genuinely outside them.
        """
        if not self._menus:
            return False
        pad = float(self.CHILD_GAP) + 1.0
        left = min(menu.rect.x for menu in self._menus) - pad
        right = max(menu.rect.x + menu.rect.w for menu in self._menus) + pad
        top = min(menu.rect.y for menu in self._menus) - pad
        bottom = max(menu.rect.y + menu.rect.h for menu in self._menus) + pad
        return left <= x <= right and top <= y <= bottom

    def _collapse_to(self, depth: int) -> bool:
        """Close every menu deeper than *depth*. Returns whether any was open."""
        if len(self._menus) <= depth:
            return False
        del self._menus[depth:]
        return True

    def mouse_press(
        self,
        x: float,
        y: float,
        right: bool = False,
        modifiers=None,
        double: bool = False,
    ) -> bool:
        """Handle a press. Returns whether the panel consumed it."""
        # The progress overlay is modal and takes every press, including the
        # ones that miss its Cancel button. Letting one through would reach the
        # menu behind the scrim and start a second load on top of the first,
        # which is the failure this widget exists to prevent.
        if self.progress.active:
            return self.progress.handle_press(x, y)
        hit = self.hit_test(x, y)

        try:
            ctrl = bool(modifiers is not None and (modifiers & CONTROL_MODIFIER))
            shift = bool(modifiers is not None and (modifiers & SHIFT_MODIFIER))
        except Exception:
            ctrl = False
            shift = False

        if hit.kind == "tour":
            if hit.key == "close":
                self.end_tour()
            elif hit.key == "next":
                self.advance_tour()
            # Any other press inside the bubble is consumed and does nothing:
            # the bubble sits over the chrome, and a click that fell through it
            # would act on whatever it happens to cover.
            return True

        if hit.kind == "uiscale":
            if double:
                # Type it. The slider spans 0.5 to 2.0 across sixty pixels, so
                # aiming at 1.25 is a fiddle even with the snapping.
                self.ui_scale_field.set_text(f"{self.ui_scale:.2f}")
                self.focus_field(self.ui_scale_field)
                return True
            self._dragging_ui_scale = True
            # Pinned for the whole gesture: changing the scale re-lays out the
            # chrome, which moves and resizes this very slider. Reading the
            # live rect mid-drag makes the track slide out from under the
            # cursor, so the value jumps around instead of following the hand.
            self._ui_scale_track = getattr(self, "_ui_scale_groove", None) or self._ui_scale_rect
            self._set_ui_scale_from(x)
            return True

        if hit.kind == "info":
            if self.press_info_filter(x, y):
                return True
            token = self.info_token_at(x, y)
            if token and self.on_info_activate is not None:
                self.on_info_activate(token)
                # And put the listing away. Picking a name out of it is the
                # thing the listing was opened *for*, so leaving it up covers
                # the prompt the name was just typed into -- the reader has to
                # dismiss it before they can see what they chose. The panel
                # closes on all three: Escape, a click outside, and a hit.
                self.hide_info()
            # Consumed either way: a press on the panel is a press on the panel,
            # and letting a miss reach the camera means the text slides.
            return True

        if hit.kind == "toolbar":
            self.close_menus()
            return self.press_toolbar(hit.row)

        if hit.kind == "menubar":
            if self._menubar_open == hit.row and self._menus:
                # A second click on the open title puts it away, which is what
                # every menu bar does.
                self.close_menus()
                return True
            return self.open_menubar(hit.row)

        if hit.kind == "window":
            self.close_menus()
            # Remembered for the drag the press may start: a shift-drag moves
            # a window *alone*, out of whatever it is stuck to.
            self._press_shift = shift
            return self._press_window(hit, x, y, double)

        if hit.kind == "command":
            self.close_menus()
            self.focus_command(True)
            self.command_line.cursor = self._cmd_cursor_at(x)
            return True
        if self.command_line.focused:
            # A press anywhere else takes focus away, so the next ``r`` rotates
            # the representation instead of appearing in a prompt the user has
            # stopped looking at.
            self.focus_command(False)

        if hit.kind == "menu":
            if hit.entry is None or hit.entry.is_separator:
                # The title row's arrows are the page control. Everything else
                # in the frame is deliberately inert -- a press on a menu's own
                # padding must not close it.
                for menu in reversed(self._menus):
                    if menu.max_scroll <= 0.0:
                        continue
                    button = self._menu_page_button(menu)
                    if button.contains(x, y):
                        # The left half goes back, the right half forward.
                        self.page_menu(-1 if x < button.x + button.w * 0.5 else 1,
                                       depth=self._menus.index(menu))
                        break
                return True
            if hit.entry.is_submenu:
                self._open_submenu(hit.entry)
                return True
            if hit.entry.command is None:
                return True          # shown, disabled, and says why
            target = self._menus[-1].target if self._menus else ""
            self._emit(hit.entry.command, target, prompt=hit.entry.prompt,
                       file_prompt=getattr(hit.entry, "file_prompt", None))
            self.close_menus()
            return True

        if hit.kind == "button":
            row = self.rows[hit.row]
            self.close_menus()
            for key, title, entries in OBJECT_MENUS:
                if key == hit.key:
                    rect = self._button_rects[hit.row][key]
                    self._open_menu(f"{title}:", row.name, entries, rect.x, rect.y + rect.h)
                    break
            return True

        if hit.kind == "wizard":
            self.close_menus()
            if hit.row < 0 or hit.row >= len(self._wizard_row_rects):
                return True                        # the panel's own background
            rect, row = self._wizard_row_rects[hit.row]
            if row.kind == "button":
                self._emit(row.action, "")
            elif row.kind == "menu":
                entries = ()
                if self.wizard_menu is not None:
                    try:
                        entries = self.wizard_menu(row.action) or ()
                    except Exception:
                        entries = ()
                if entries:
                    self._open_menu(
                        row.label, "", entries, rect.x, rect.y + rect.h
                    )
            return True

        if hit.kind == "scrollbar":
            self._dragging_thumb = True
            self._scroll_to(x)
            return True

        if hit.kind == "residue":
            row_index, column = hit.row, int(hit.key)
            self._seq_drag = (row_index, column)
            self._seq_drag_additive = bool(ctrl or shift)
            prev_anchor = self._seq_anchor
            self._seq_anchor = column
            if shift and prev_anchor is not None:
                # PyMOL's Seeker: shift continues the previous drag gesture,
                # extending the range from where it left off -- additively.
                self._select_range(row_index, prev_anchor, column, additive=True)
            else:
                # PyMOL's Seeker: a click toggles the residue (ctrl does the
                # same and additionally centres the view).
                self._toggle_residue(row_index, column)
            return True

        if hit.kind == "sequence":
            # PyMOL's Seeker clears the selection on a double-click on blank
            # sequence area.
            if double:
                self.clear_selection()
            return True

        if hit.kind == "splitter":
            self._dragging_splitter = True
            return True

        if hit.kind == "mode":
            self.cycle_mouse_mode()
            return True

        if hit.kind == "selecting":
            self.cycle_selecting(back=right)
            return True

        if hit.kind == "timeline":
            self._dragging_timeline = True
            self._seek_to(x)
            return True

        if hit.kind in ("stride", "average"):
            # Right-click steps back, so a value overshot is one click away
            # rather than a full trip round the cycle.
            step = -1 if right else 1
            if hit.kind == "stride":
                self.stride = max(1, self.stride + step)
            else:
                self.average = max(0, self.average + step)
            if self.on_playback_change is not None:
                try:
                    self.on_playback_change(self.stride, self.average)
                except Exception:
                    pass
            return True

        if hit.kind == "playback_slider":
            self._dragging_playback = str(hit.key)
            self._set_playback_from(x)
            return True

        if hit.kind == "movie":
            self.close_menus()
            self._emit(hit.key, "")
            return True

        if hit.kind == "block":
            return True

        if hit.kind == "panel":
            # The object list's background clears the selection. It took the
            # click and did nothing, which is a dead area in the one panel that
            # is *about* selection -- and "click away to deselect" is what the
            # viewport itself already does.
            self.close_menus()
            self._emit("deselect", "")
            return True

        if hit.kind == "eye":
            # Visibility lives on the eye now, like the density panel's: the
            # name used to toggle the object, so making one *active* switched
            # it off on the way.
            row = self.rows[hit.row]
            self.close_menus()
            if row.is_group:
                self._emit("group {sele}, toggle", row.name)
            elif row.is_measurement:
                self._emit("measurement {sele}, toggle", row.name)
            elif row.is_header:
                self._emit("disable all" if row.enabled else "enable all", "")
            else:
                self._emit("disable {sele}" if row.enabled else "enable {sele}", row.name)
            return True

        if hit.kind == "name":
            row = self.rows[hit.row]
            self.close_menus()
            if right:
                # PyMOL's right-click on a name is its action menu.
                _key, title, entries = OBJECT_MENUS[0]
                self._open_menu(f"{title}:", row.name, entries, x, y)
            elif row.is_group:
                # A group is a container row, so its name is the disclosure
                # control -- the same click the docked panel's marker takes.
                self._emit("group {sele}, toggle", row.name)
            elif row.is_selection or row.is_header:
                pass
            elif row.is_measurement:
                self._emit("measurement {sele}, toggle", row.name)
            else:
                # The name makes the object *active*; the eye is what hides it.
                self._emit("activate {sele}", row.name)
            return True

        if self._menus:
            self.close_menus()
            return True
        return False

    def _emit(self, command: str, target: str, prompt=None,
              file_prompt=None) -> None:
        """Run *command* with ``{sele}`` bound to *target*.

        An entry needing a typed value is written into the **command line**
        instead of being run, with the placeholder selected so the next
        keystroke replaces it. Skipping it -- which is what happened before, on
        the grounds that "a prompted value has no place to be typed in the
        viewport" -- made a menu entry that did nothing at all when clicked, and
        the viewport panel is now the primary one. The command line sits
        directly beneath it, which is where PyMOL would have you type anyway.

        Parameters
        ----------
        command : str
            Template, with ``{sele}`` for the target and ``{text}`` for a value.
        target : str
            Object, group or selection the menu was opened on.
        prompt : tuple of str, optional
            ``(title, question)`` from the menu entry; the question names the
            placeholder, so ``Group name:`` becomes ``<group name>``.
        """
        if self._run_command is None:
            return
        for line in str(command).splitlines():
            line = line.strip()
            if not line:
                continue
            # Quoted unless it is a bare identifier: an object called
            # `EMD-3061` otherwise reaches the selection parser as
            # `EMD` `-` `3061`.
            line = line.replace("{sele}", quote_selection_name(target))
            if "{text}" in line:
                # An entry that names a *file* opens a real dialog on hosts
                # that have one: a filename typed blind lands wherever the
                # process happens to be running. The command line keeps
                # taking paths as text -- the dialog is the menu's
                # affordance, not the CLI's. Hosts without a dialog (the
                # browser) fall through to the placeholder below.
                if file_prompt is not None and self.on_file_prompt is not None:
                    try:
                        mode, title, name_filter = file_prompt
                        self.on_file_prompt(line, mode, title, name_filter)
                    except Exception:
                        pass
                    continue
                question = str((prompt or ("", "value"))[-1]).strip().rstrip(":")
                placeholder = f"<{question.lower() or 'value'}>"
                filled = line.replace("{text}", placeholder)
                # Into the viewport's own prompt first, with the caret on the
                # placeholder. That is the one that exists everywhere: the host
                # console is a desktop widget, and in a browser the entry would
                # otherwise be clickable and inert.
                if self.command_line.visible:
                    self.focus_command(True)
                    self.command_line.set_text(
                        filled, cursor=filled.find(placeholder)
                    )
                if self.on_prompt_command is not None:
                    try:
                        self.on_prompt_command(filled, placeholder)
                    except Exception:
                        pass
                continue
            try:
                self._run_command(line)
            except Exception:
                pass

    # ── menus ────────────────────────────────────────────────────────────
    def _open_menu(self, title, target, entries, x, y, parent=None,
                   owner=None) -> None:
        menu = _OpenMenu(title=title, target=target, entries=list(entries), x=x, y=y,
                         parent=parent, owner=owner,
                         affinity=parent.affinity if parent is not None else 1)
        self._layout_menu(menu)
        self._menus.append(menu)

    def _open_submenu(self, entry: MenuEntry) -> None:
        """Open *entry*'s children beside the row they hang off."""
        if self._menus and self._menus[-1].owner is entry:
            return                       # already open, and on the right row
        for depth in range(len(self._menus) - 1, -1, -1):
            parent = self._menus[depth]
            for rect, candidate in parent.item_rects:
                if candidate is not entry:
                    continue
                del self._menus[depth + 1:]
                # Beside the row, with the child's first *entry* on it rather
                # than the child's title -- PyMOL's `target_y` correction. The
                # x here is a starting point only; `_layout_menu` decides the
                # side, because it is the only place the width is known.
                self._open_menu(
                    entry.label, parent.target, entry.children,
                    parent.rect.x + parent.rect.w + self.CHILD_GAP,
                    rect.y - self.MENU_PAD - self.MENU_ITEM_H,
                    parent, owner=entry,
                )
                return

    def _place_child(
        self, parent: Rect, width: float, affinity: int
    ) -> tuple[float, int]:
        """Return ``(x, affinity)`` for a submenu *width* wide beside *parent*.

        PyMOL's ``PopPlaceChild``: try the preferred side, and if the menu had
        to be shoved back on screen to fit there, flip to the other side and try
        again. That flip is the whole point -- the panel is docked against the
        right edge, so a submenu opened to the right never fits, and clamping it
        into the window instead of flipping is what drew it *on top of its own
        parent*.
        """
        sides = {
            1: parent.x + parent.w + self.CHILD_GAP,
            -1: parent.x - width - self.CHILD_GAP,
        }
        limit = max(self._width - width, 0.0)
        preferred = 1 if affinity >= 0 else -1
        for side in (preferred, -preferred):
            if 0.0 <= sides[side] <= limit:
                return sides[side], side
        # Neither side fits: take the one with more room and clamp into it, so
        # what is lost is at the window edge rather than over the parent.
        side = -1 if parent.x >= self._width - (parent.x + parent.w) else 1
        return min(max(sides[side], 0.0), limit), side

    def _layout_menu(self, menu: _OpenMenu) -> None:
        """Size a menu from its entries and keep every item on screen.

        PyMOL's Action menu is two dozen entries long, which is taller than a
        viewport that is sharing its height with a sequence strip and a console.
        A menu that runs off the bottom is worse than a small font: the entries
        are simply unreachable, and nothing says they are there. So it wraps
        into columns, the way a long menu does everywhere, and the item
        rectangles stay the single source of truth for both drawing and hit
        testing -- they cannot disagree about where an entry is.
        """
        char_w = char_width(self.FONT_PT)
        title_h = self.MENU_ITEM_H
        content = title_h + 2 * self.MENU_PAD + sum(
            self.SEPARATOR_H if e.is_separator else self.MENU_ITEM_H
            for e in menu.entries
        )
        height = min(content, float(self._height))
        # A paged menu's title carries "2/3" and the arrows beside it, and both
        # are in the title *row*: without the allowance the page number is
        # drawn underneath the arrows on any menu whose entries are short.
        paged = content > height
        width = max(
            [len(menu.title) * char_w + (10 * char_w if paged else 0.0)]
            + [len(e.label) * char_w + (18 if e.is_submenu else 0) for e in menu.entries]
        ) + 2 * self.MENU_PAD + 12
        if height < content:
            # A whole number of rows, so the bottom one is not sliced through
            # the middle of its text -- which reads as a rendering fault rather
            # than as "there is more below".
            rows = max(int((height - title_h - 2 * self.MENU_PAD) // self.MENU_ITEM_H), 1)
            height = title_h + 2 * self.MENU_PAD + rows * self.MENU_ITEM_H
        menu.max_scroll = max(content - height, 0.0)
        menu.page_px = max(height - title_h - 2 * self.MENU_PAD, self.MENU_ITEM_H)
        menu.scroll = min(max(menu.scroll, 0.0), menu.max_scroll)

        if menu.parent is None:
            x = min(max(menu.x, 0.0), max(self._width - width, 0.0))
        else:
            # A submenu is placed *beside* its parent, never clamped into it.
            x, menu.affinity = self._place_child(
                menu.parent.rect, width, menu.affinity
            )
        y = min(max(menu.y, 0.0), max(self._height - height, 0.0))
        menu.rect = Rect(x, y, width, height)

        menu.item_rects = []
        iy = y + self.MENU_PAD + title_h - menu.scroll
        for entry in menu.entries:
            if entry.is_separator:
                iy += self.SEPARATOR_H
                continue
            menu.item_rects.append((Rect(x, iy, width, self.MENU_ITEM_H), entry))
            iy += self.MENU_ITEM_H

    @staticmethod
    def menu_pages(menu: _OpenMenu) -> tuple[int, int]:
        """Which page of a too-tall menu is showing, and how many there are.

        Returns
        -------
        tuple of int
            ``(page, pages)``, one-based. ``(1, 1)`` when it all fits.
        """
        if menu.max_scroll <= 0.0 or menu.page_px <= 0.0:
            return (1, 1)
        pages = int(menu.max_scroll // menu.page_px) + 2 \
            if menu.max_scroll % menu.page_px else int(menu.max_scroll // menu.page_px) + 1
        page = int(round(menu.scroll / menu.page_px)) + 1
        return (min(page, pages), pages)

    def page_menu(self, delta: int, depth: int | None = None) -> bool:
        """Turn a too-tall menu's page. Returns whether anything moved.

        Parameters
        ----------
        delta : int
            ``+1`` forward, ``-1`` back.
        depth : int, optional
            Which open menu; the innermost by default.
        """
        if not self._menus:
            return False
        menu = self._menus[depth if depth is not None else -1]
        if menu.max_scroll <= 0.0:
            return False
        wanted = min(max(menu.scroll + delta * menu.page_px, 0.0), menu.max_scroll)
        wanted = self._snap_scroll(menu, wanted)
        if wanted == menu.scroll:
            return False
        menu.scroll = wanted
        # Children hang off a row that has just moved, so they cannot stay.
        del self._menus[self._menus.index(menu) + 1:]
        self._layout_menu(menu)
        return True

    def _menu_page_button(self, menu: _OpenMenu) -> Rect:
        """The arrows in a menu's title row, as a press target."""
        rect = menu.rect
        width = 4.0 * char_width(self.FONT_PT) + self.MENU_PAD
        return Rect(rect.x + rect.w - width, rect.y + self.MENU_PAD,
                    width, self.MENU_ITEM_H)

    def _snap_scroll(self, menu: _OpenMenu, wanted: float) -> float:
        """Round a scroll offset to the nearest row boundary.

        So the first visible row starts flush with the top of the list instead
        of being sliced through its text. The separators are why a fixed step
        cannot do this on its own: they are five pixels, not a row, so the
        entries below one are off the row grid.
        """
        offsets = [0.0]
        y = 0.0
        for entry in menu.entries:
            y += self.SEPARATOR_H if entry.is_separator else self.MENU_ITEM_H
            if y <= menu.max_scroll:
                offsets.append(y)
        offsets.append(menu.max_scroll)
        return min(offsets, key=lambda candidate: abs(candidate - wanted))

    def _menu_row_visible(self, menu: _OpenMenu, rect: Rect) -> bool:
        """Whether a row is inside the menu's window rather than scrolled out."""
        top = menu.rect.y + self.MENU_PAD + self.MENU_ITEM_H
        return rect.y >= top - 1 and rect.y + rect.h <= menu.rect.y + menu.rect.h + 1

    def scroll_menu(self, x: float, y: float, steps: int) -> bool:
        """Scroll the menu under the cursor by *steps* notches. Returns if it moved.

        PyMOL's ``CPopUp::release`` translates the whole pop-up by ten pixels a
        notch rather than wrapping a long menu into columns, and that is the
        behaviour: a wrapped menu loses its **grouping**, which is most of what
        a menu's order is saying. chimol's Action menu wrapped on any short
        window and the two columns then read as one list broken in an arbitrary
        place, with the separators dropped to keep the columns aligned.
        """
        if self.scroll_info(x, y, steps):
            return True
        depth, _entry = self._menu_at(x, y)
        if depth is None:
            return False
        menu = self._menus[depth]
        if menu.max_scroll <= 0.0:
            return False
        before = menu.scroll
        wanted = min(
            max(menu.scroll - steps * self.MENU_SCROLL_PX, 0.0), menu.max_scroll
        )
        menu.scroll = self._snap_scroll(menu, wanted)
        if menu.scroll == before:
            return False
        # The children hang off rows that have just moved, so they are stale.
        del self._menus[depth + 1:]
        self._layout_menu(menu)
        return True

    # ── drawing ──────────────────────────────────────────────────────────
    #: Above this many selected residues the chrome cache stops trying to
    #: fingerprint the selection and simply rebuilds. Hashing a set is exact
    #: but linear, and "select everything" on an integrative model is 234,184
    #: residues -- more than the paint it would be saving.
    SELECTION_HASH_MAX = 4096

    #: Where the stride and averaging sliders top out. A stride past this is a
    #: different way of watching a trajectory (use `frame`), and an averaging
    #: window past it stops being a smoother and starts being a mean structure.
    STRIDE_MAX = 50
    AVERAGE_MAX = 50

    def _set_playback_from(self, x: float) -> None:
        """Set whichever playback slider is being dragged from a cursor x."""
        which = self._dragging_playback
        if which == "stride":
            groove, ceiling, floor = self._stride_groove, self.STRIDE_MAX, 1
        elif which == "average":
            groove, ceiling, floor = self._average_groove, self.AVERAGE_MAX, 0
        else:
            return
        if groove.w <= 0.0:
            return
        fraction = (float(x) - groove.x) / groove.w
        fraction = min(max(fraction, 0.0), 1.0)
        value = int(round(fraction * ceiling))
        value = max(floor, value)
        if which == "stride":
            if value == self.stride:
                return
            self.stride = value
        else:
            if value == self.average:
                return
            self.average = value
        if self.on_playback_change is not None:
            try:
                self.on_playback_change(self.stride, self.average)
            except Exception:  # noqa: BLE001 - a listener is not worth the drag
                pass

    def chrome_fingerprint(self) -> tuple:
        """Everything the chrome draws from, as one comparable value.

        The chrome is immediate mode: :meth:`paint` rebuilds ~2,800 quads from
        scratch every frame, and on a large model that is most of the frame
        while the *molecule* is about a millisecond. But the chrome changes on
        hover, focus and state -- not on camera motion, which is exactly when
        frames matter. So the caller compares this against the previous frame's
        and reuses the vertices when it has not moved.

        The design rule here is **conservative**: it is always safe to include
        something that changes too often (it merely rebuilds), and never safe to
        omit something that changes the picture (it draws a stale one). Where a
        value is expensive to hash -- a sequence row's per-residue colours, of
        which there are 234,184 on the nuclear pore -- the cheap signature
        already computed for it upstream is used rather than the colours.

        Two members deliberately force a rebuild every frame while they are on:
        the progress overlay animates and counts elapsed seconds, and the
        frame-rate readout is a number that changes by construction. Both are
        transient, and both are wrong to freeze.

        Returns
        -------
        tuple
            Comparable with ``==``. Never raises: a member that cannot be read
            contributes ``None``, which is a value like any other.
        """
        def rows_key(rows):
            return tuple(
                (
                    getattr(r, "name", None), getattr(r, "enabled", None),
                    getattr(r, "is_header", None), getattr(r, "is_group", None),
                    getattr(r, "group_open", None), getattr(r, "detail", None),
                    getattr(r, "indent", None), getattr(r, "object_id", None),
                )
                for r in (rows or ())
            )

        def windows_key():
            return tuple(
                (
                    getattr(w, "key", None), getattr(w, "visible", None),
                    getattr(w, "x", None), getattr(w, "y", None),
                    getattr(w, "w", None), getattr(w, "h", None),
                    getattr(w, "collapsed", None), getattr(w, "title", None),
                )
                for w in (getattr(self, "windows", None) or ())
            )

        def menus_key():
            return tuple(
                (
                    getattr(m, "title", None), getattr(m, "scroll", None),
                    getattr(m, "owner", None), getattr(m, "hover", None),
                    len(getattr(m, "entries", ()) or ()),
                )
                for m in (getattr(self, "_menus", None) or ())
            )

        def selection_key(row):
            """A token for one row's selected residues.

            The selection is highlighted in the strip, so it has to be seen --
            and it is mutated **in place** in three different places, so
            watching the set object's identity is not enough either.

            Hashing it is exact and costs O(n), which is fine for what a
            selection normally is (a click, a dragged range) and not fine for
            "select everything" on a 234,184-residue model. So a large
            selection returns a value that is never equal to itself, which
            makes the frame rebuild -- the behaviour there was before any of
            this, and therefore never worse.
            """
            selected = getattr(row, "selected", None)
            if not selected:
                return 0
            count = len(selected)
            if count > self.SELECTION_HASH_MAX:
                return object()
            try:
                return (count, hash(frozenset(selected)))
            except TypeError:
                return object()

        def sequences_key():
            # `_colors_from` is the signature `refresh_gui_state` already
            # computes; hashing the colours again here would cost more than the
            # paint this is trying to avoid.
            return tuple(
                (
                    getattr(r, "object_id", None), getattr(r, "label", None),
                    getattr(r, "name", None), getattr(r, "chain", None),
                    len(getattr(r, "codes", "") or ""),
                    len(getattr(r, "text", "") or ""),
                    getattr(r, "_colors_from", None),
                    getattr(r, "offset", None),
                    selection_key(r),
                )
                for r in (getattr(self, "sequences", None) or ())
            )

        def cmd_log_key():
            line = getattr(self, "command_line", None)
            log = getattr(line, "visible_log", None)
            if not callable(log):
                return None
            try:
                return tuple(
                    (getattr(e, "kind", None), getattr(e, "text", None))
                    for e in (log() or ())
                )
            except Exception:  # noqa: BLE001
                return object()

        field = self.focused_field
        progress = self.progress
        try:
            return (
                self._width, self._height, self.ui_scale, self.docked, self.visible,
                self.sequence_visible, self.status_visible, self.status_text,
                # Set from the display config on every frame by the renderer,
                # so they belong here even though nothing else changes them.
                getattr(self, "menubar_visible", None),
                getattr(self, "toolbar_visible", None),
                getattr(self, "window_snap", None),
                getattr(getattr(self, "command_line", None), "visible", None),
                getattr(getattr(self, "command_line", None), "text", None),
                getattr(getattr(self, "command_line", None), "cursor", None),
                getattr(getattr(self, "command_line", None), "focused", None),
                # The feedback log above the prompt. Every command appends to
                # it, so it is the part of the chrome that changes most often
                # and it is drawn as text -- which is how "select everything"
                # was found redrawing nine quads with nothing else moving. It
                # is a handful of lines, so reading it costs nothing.
                cmd_log_key(),
                self.selecting, self.state, self.mouse_mode, self.mouse_ring,
                self._name_width, self.debug_overlays,
                self.stride, self.average, self._dragging_playback,
                # Changes every frame while it is shown, and should.
                self.fps if self.debug_overlays else None,
                self.info_visible, self.info_text, self._info_scroll,
                len(getattr(self, "_info_items", ()) or ()),
                tuple(self.info_colors or ()) if isinstance(
                    getattr(self, "info_colors", None), (list, tuple)
                ) else None,
                self._hover, self._tooltip,
                # The tour's bubble and ring. Cheap to read, and stale chrome
                # here means a ring left around a control the tour has moved on
                # from -- pointing confidently at the wrong thing.
                (getattr(self.tour, "name", None),
                 getattr(self.tour, "index", None)) if self.tour else None,
                rows_key(self.rows), rows_key(getattr(self, "wizard_rows", None)),
                tuple(getattr(self, "wizard_prompt", None) or ()),
                sequences_key(), windows_key(), menus_key(),
                id(field), getattr(field, "text", None),
                getattr(field, "cursor", None),
                # Animates, and counts seconds.
                (progress.active, progress.title, progress.message,
                 progress.fraction, progress.cancellable, progress.cancelled,
                 progress.status_text() if progress.active else None),
                tuple(sorted(self.toolbar_checked.items()))
                if isinstance(getattr(self, "toolbar_checked", None), dict) else None,
            )
        except Exception:  # noqa: BLE001 - a fingerprint must never break a frame
            # Unique every call, so an unreadable member degrades to "always
            # rebuild" rather than to "never rebuild".
            return (object(),)

    def paint(self, p) -> None:
        """Draw the panel and any open menu.

        Parameters
        ----------
        p : chimol.renderer.ui.painter.Painter
            The surface to draw on. Six operations, each carrying its own
            colour -- see :mod:`chimol.renderer.ui.painter` for why this is not
            a ``QPainter`` with the names changed.
        """
        if not self.visible and not self._menus:
            # The prompt is not part of the panel: PyMOL's `internal_prompt` and
            # `internal_gui` are separate settings, and hiding the object list
            # to see the molecule is not a reason to lose the only way of typing
            # at it -- which in a browser is the *only* way.
            if self.info_visible:
                self._paint_info(p)
            if self.command_line.visible:
                self._paint_command(p)
                self._paint_windows(p)
            self._paint_menubar(p)
            self._paint_toolbar(p)
            return

        if self.info_visible:
            self._paint_info(p)
        if self.sequence_visible and self.sequences:
            self._paint_sequence(p)
        if self.visible and self.docked:
            # One continuous column, not two floating boxes with the scene
            # showing between them: the gap reads as a hole in the panel.
            column = self.effective_column_width()
            p.fill_rect(
                self._width - column, 0.0, column, float(self._height), PANEL_BG,
            )
        if self.docked and self.visible and self.rows:
            # Docked, the panel and block are part of the column; windowed,
            # their windows draw them in the window pass, correctly stacked
            # under whatever floats above.
            self._paint_panel(p)
        if self.visible and self.wizard_rows:
            self._paint_wizard(p)
        if self.docked and self.visible:
            self._paint_block(p)
        if self.wizard_prompt:
            self._paint_prompt(p)
        if self.command_line.visible:
            self._paint_command(p)
        self._paint_windows(p)
        self._paint_menubar(p)
        self._paint_toolbar(p)
        if self.visible and self.docked:
            p.fill_rect(
                self._splitter.x + self.SPLITTER_W / 2 - 1, 0.0,
                2.0, self._height, SPLITTER_FG,
            )
        self._paint_status(p)
        for menu in self._menus:
            self._paint_menu(p, menu)
        # Over the chrome, under an open menu's tooltip: a tour points *at*
        # menus, so it must not cover the one it just told the user to open.
        self._paint_tour(p)
        self._paint_tooltip(p)
        # Last, and after the tooltip: it is modal, so nothing may draw over
        # it. A tooltip surfacing above a scrim would say the chrome beneath is
        # live, which is exactly what the scrim is there to deny.
        self.progress.paint(p, self._width, self._height, self.ui_scale)

    def _paint_tour(self, p) -> None:
        """The guided tour: a ring around the control, and a bubble beside it.

        The ring is the whole point. A bubble alone is a slideshow -- it can be
        read from top to bottom without ever finding the control it describes,
        which is the thing someone actually needs to learn. So the target is
        resolved *here*, at paint time, against rectangles that were laid out
        this frame: the chrome may have been resized, the panel scrolled, or a
        window dragged since the step began.
        """
        tour = self.tour
        step = None if tour is None else tour.current
        if step is None:
            self._tour_rect = Rect(0, 0, 0, 0)
            self._tour_next_rect = Rect(0, 0, 0, 0)
            self._tour_close_rect = Rect(0, 0, 0, 0)
            self._tour_target = Rect(0, 0, 0, 0)
            return

        target = self.tour_target_rect(step.target)
        self._tour_target = target
        if target.w > 0.0 and target.h > 0.0:
            # Two rings rather than one: at this line width a single rectangle
            # against the chrome's own borders reads as a border. Two, with a
            # gap, reads as a marker.
            for inset in (-3.0, -1.0):
                p.stroke_rect(
                    target.x + inset, target.y + inset,
                    target.w - 2 * inset, target.h - 2 * inset,
                    TOUR_RING,
                )

        char_w = char_width(self.FONT_PT)
        row = float(self.CMD_ROW_H)
        columns = 46
        lines: list[tuple[str, tuple]] = [(step.title, TOUR_TITLE_FG)]
        for line in _wrap_lines(step.text, columns):
            lines.append((line, TOUR_FG))
        if step.waits:
            lines.append(("", TOUR_FG))
            for line in _wrap_lines(step.prompt(), columns):
                lines.append((line, TOUR_RING))

        counter = f"{tour.index + 1} / {len(tour.steps)}"
        width = max(
            max((len(text) for text, _c in lines), default=0) * char_w,
            char_w * (len(counter) + 18),
        ) + 2 * self.PAD
        height = (len(lines) + 2) * row + 2 * self.PAD

        bx, by = self._tour_bubble_at(target, width, height)
        self._tour_rect = Rect(bx, by, width, height)

        p.fill_rect(bx, by, width, height, TOUR_BG)
        p.stroke_rect(bx, by, width, height, TOUR_RING)
        for index, (text, colour) in enumerate(lines):
            if not text:
                continue
            p.text(
                bx + self.PAD, by + self.PAD + index * row,
                width - 2 * self.PAD, row,
                ALIGN_VCENTER | ALIGN_LEFT, text, colour,
            )

        # The controls. `Next` is absent while a step waits: offering it would
        # be offering to skip the one action the step exists to teach, and
        # `Close` is always there so waiting is never a trap.
        button_y = by + height - row - self.PAD
        p.text(
            bx + self.PAD, button_y, width - 2 * self.PAD, row,
            ALIGN_VCENTER | ALIGN_LEFT, counter, TOUR_DIM_FG,
        )
        close_w = char_w * 7 + 2 * self.MENU_PAD
        close_x = bx + width - close_w - self.PAD
        self._tour_close_rect = Rect(close_x, button_y, close_w, row)
        p.fill_rect(close_x, button_y, close_w, row, TOUR_BUTTON_BG)
        p.text(close_x, button_y, close_w, row,
               ALIGN_VCENTER | ALIGN_CENTER, "Close", TOUR_FG)

        if step.waits:
            self._tour_next_rect = Rect(0, 0, 0, 0)
        else:
            next_w = char_w * 6 + 2 * self.MENU_PAD
            next_x = close_x - next_w - 4.0
            self._tour_next_rect = Rect(next_x, button_y, next_w, row)
            p.fill_rect(next_x, button_y, next_w, row, TOUR_BUTTON_BG)
            p.text(next_x, button_y, next_w, row,
                   ALIGN_VCENTER | ALIGN_CENTER, "Next", TOUR_FG)

    def _tour_bubble_at(self, target, width: float, height: float):
        """Where to put the tour's bubble so it never covers its own target.

        The first version put the bubble to the right of the ring, or to the
        left when there was no room, and clamped it into the viewport. That is
        right for a small control and wrong for a wide one: the command prompt
        spans the whole width, so neither side fits, the clamp put the bubble
        back over the prompt -- and the step it was covering said *type this at
        the prompt*. A tour that hides the control it is talking about is worse
        than no tour, because the user cannot even see what they are being
        asked to do.

        So all four sides are tried, and a placement is only accepted if it
        clears the target completely. Above and below are what save the wide
        controls; right and left are preferred for the narrow ones because a
        bubble beside a button reads as attached to it.

        Returns
        -------
        tuple of float
            The bubble's top-left corner.
        """
        pad = 12.0
        edge = 4.0
        right = float(self._width) - width - edge
        bottom = float(self._height) - height - edge

        if target.w <= 0.0 or target.h <= 0.0:
            return (0.5 * (float(self._width) - width),
                    0.5 * (float(self._height) - height))

        def clamp(x, y):
            return (min(max(x, edge), max(right, edge)),
                    min(max(y, edge), max(bottom, edge)))

        def clears(x, y):
            """Whether the bubble at (x, y) misses the target entirely."""
            return (
                x + width <= target.x
                or x >= target.x + target.w
                or y + height <= target.y
                or y >= target.y + target.h
            )

        # Beside first, then above or below. A press on the ringed control has
        # to stay reachable, so overlapping is never traded for tidiness.
        beside_y = min(max(target.y - self.CMD_ROW_H, edge), max(bottom, edge))
        candidates = [
            (target.x + target.w + pad, beside_y),
            (target.x - width - pad, beside_y),
            (min(max(target.x, edge), max(right, edge)),
             target.y + target.h + pad),
            (min(max(target.x, edge), max(right, edge)),
             target.y - height - pad),
        ]
        for x, y in candidates:
            if edge <= x <= right and edge <= y <= bottom and clears(x, y):
                return (x, y)

        # Nothing fits cleanly -- a target as large as the viewport. Take the
        # placement that overlaps least, still clamped on screen.
        def overlap(x, y):
            x, y = clamp(x, y)
            wide = max(0.0, min(x + width, target.x + target.w) - max(x, target.x))
            tall = max(0.0, min(y + height, target.y + target.h) - max(y, target.y))
            return wide * tall

        return clamp(*min(candidates, key=lambda c: overlap(*c)))

    def _paint_tooltip(self, p) -> None:
        """The hover tooltip, beside the cursor, above everything else."""
        if self._tooltip is None:
            return
        x, y, text = self._tooltip
        lines = _wrap_lines(str(text), 46)
        char_w = char_width(self.FONT_PT)
        width = max(len(line) for line in lines) * char_w + 2 * self.PAD
        height = len(lines) * self.CMD_ROW_H + 2.0
        # Beside the cursor, flipped to stay on screen.
        bx = min(x + 14.0, float(self._width) - width - 2.0)
        by = min(y + 18.0, float(self._height) - height - 2.0)
        p.fill_rect(bx, by, width, height, MOVIE_BG)
        p.stroke_rect(bx, by, width, height, WINDOW_BORDER)
        for index, line in enumerate(lines):
            p.text(bx + self.PAD, by + 1.0 + index * self.CMD_ROW_H,
                   width - 2 * self.PAD, float(self.CMD_ROW_H),
                   ALIGN_VCENTER | ALIGN_LEFT, line, MODE_ACTION_FG)

    def _paint_status(self, p) -> None:
        """The own status line, bottom-right of the viewport.

        Replaces the toolkit's status bar: drawn by the chrome, so it exists
        in the browser too, and it is a display setting (`show_status`) like
        every other piece of the chrome rather than a strip the toolkit owns.
        """
        height = float(self.CMD_ROW_H)
        y = float(self._height) - height - 2.0
        char_w = char_width(self.FONT_PT)

        # The chrome-size slider and the frame-rate readout are **developer
        # instruments**, so both are behind `debug`. They were shown to
        # everyone, and a permanent slider plus a permanent number in the
        # corner of a figure is chrome that earns its space only while someone
        # is measuring. Off, the status band is just the status band.
        if not self.debug_overlays:
            # An *empty* rect, not None. `Rect(0, 0, 0, 0).contains(...)` is
            # False, which is what "not there" means everywhere else in this
            # class -- and it is what `hit_test` and the drag handler already
            # assume, both of which dereference these without a guard. Using
            # None here made every click raise AttributeError the moment the
            # instruments were switched off, which is the default.
            self._ui_scale_rect = Rect(0, 0, 0, 0)
            self._ui_scale_groove = Rect(0, 0, 0, 0)
            self._paint_status_text(p, y, height, float(self._width) - 2.0)
            return

        # Frame rate, immediately left of the size slider: the two are read
        # together -- the question is always "what does this cost", and the
        # slider is the thing most likely to change the answer.
        fps_w = 0.0
        if self.fps > 0.0:
            fps_label = f"{self.fps:.0f} fps"
            fps_w = char_w * (len(fps_label) + 1) + self.PAD
        char_w = char_width(self.FONT_PT)
        # The number gets its own column and the groove gets the rest. Drawn on
        # top of each other, the thumb crossed the digits and both became hard
        # to read -- and the one thing a slider owes is a legible value.
        label = f"{self.ui_scale:.2f}"
        label_w = char_w * (len(label) + 1)
        groove_w = max(char_w * 10.0, 54.0)
        total_w = groove_w + label_w + 2 * self.PAD
        box_x = float(self._width) - total_w - 2.0
        self._ui_scale_rect = Rect(box_x, y, total_w, height)

        if fps_w > 0.0:
            p.fill_rect(box_x - fps_w, y, fps_w, height, PANEL_BG)
            p.text(box_x - fps_w, y, fps_w - self.PAD, height,
                   ALIGN_VCENTER | ALIGN_RIGHT, fps_label, WINDOW_DIM_FG)

        p.fill_rect(box_x, y, total_w, height, PANEL_BG)
        groove_x = box_x + self.PAD
        low, high = self.UI_SCALE_MIN, self.UI_SCALE_MAX
        fraction = (float(self.ui_scale) - low) / max(high - low, 1e-6)
        fraction = min(max(fraction, 0.0), 1.0)
        mid = y + height * 0.5
        p.fill_rect(groove_x, mid - 1.0, groove_w, 2.0, WINDOW_DIM_FG)
        p.fill_rect(groove_x, mid - 1.0, groove_w * fraction, 2.0, MODE_TITLE_FG)
        thumb = groove_x + fraction * max(groove_w - 5.0, 0.0)
        p.fill_rect(thumb, y + 3.0, 5.0, height - 6.0,
                    MODE_TITLE_FG if self._dragging_ui_scale else ENABLED_FG)
        editing = self.focused_field is self.ui_scale_field
        p.text(groove_x + groove_w + self.PAD, y, label_w, height,
               ALIGN_VCENTER | ALIGN_RIGHT,
               (self.ui_scale_field.text + "|") if editing else label,
               MODE_TITLE_FG if editing else WINDOW_DIM_FG)
        #: The groove alone, which is what a drag maps onto.
        self._ui_scale_groove = Rect(groove_x, y, groove_w, height)

        self._paint_status_text(p, y, height, box_x - fps_w)

    def _paint_status_text(self, p, y: float, height: float, right: float) -> None:
        """The status message, right-aligned against *right*.

        Split out because the band's right edge depends on what else is in it:
        the size slider and the frame counter are debug-only, so with them off
        the message may use the full width.

        This used to end at ``x = track_x - width``, and ``track_x`` is a name
        from a *different* method -- the info panel's scrollbar. Any code that
        set a status message would have raised ``NameError`` from inside the
        paint pass. Nothing sets one today, which is the only reason it was
        never seen.
        """
        if not (self.status_visible and self.status_text):
            return
        text = str(self.status_text)
        width = char_width(self.FONT_PT) * len(text) + 2 * self.PAD
        x = max(right - width - 4.0, 0.0)
        p.fill_rect(x, y, width, height, PANEL_BG)
        p.text(x + self.PAD, y, width - 2 * self.PAD, height,
               ALIGN_VCENTER | ALIGN_RIGHT, text, WINDOW_DIM_FG)

    def _paint_panel(self, p) -> None:
        """Draw the object list: one row per molecule, group or selection."""
        p.fill_rect(self._panel.x, self._panel.y, self._panel.w, self._panel.h,
                    PANEL_BG)

        for index, row in enumerate(self.rows):
            rect = self._row_rects[index]
            if row.is_header:
                p.fill_rect(rect.x, rect.y, rect.w, rect.h, HEADER_BG)

            label = row.name
            if row.is_group:
                label = ("▾ " if row.group_open else "▸ ") + label
            if row.detail:
                label = f"{label} {row.detail}"
            colour = (
                HEADER_FG if row.is_header
                else (ENABLED_FG if row.enabled else DISABLED_FG)
            )
            # The selection row gets an eye like everything else. It was the
            # one row without one, and `sele` is exactly the object a user most
            # often wants to show and hide -- `enable sele` / `disable sele` is
            # what the eye already emits, and PyMOL's own list shows it.
            if index < len(self._eye_rects):
                eye = self._eye_rects[index]
                p.text(
                    eye.x, eye.y, eye.w, eye.h, ALIGN_CENTER,
                    "o" if (row.enabled or row.is_header) else "-",
                    ENABLED_FG if (row.enabled or row.is_header) else DISABLED_FG,
                )
            p.text(
                rect.x + self.PAD + self.BUTTON_W + row.indent * 10, rect.y,
                self._name_width, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, label, colour,
            )

            for key, brect in self._button_rects[index].items():
                self._paint_button(
                    p, key, brect,
                    hovered=(self._hover.kind == "button"
                             and self._hover.row == index
                             and self._hover.key == key),
                    enabled=row.enabled or row.is_header,
                )

    def _paint_wizard(self, p) -> None:
        """Draw the wizard panel, PyMOL's three row kinds and nothing else.

        A banner, pop-ups that carry their current value in the label, and
        buttons. PyMOL draws a pop-up and a button the same way and tells them
        apart by what happens on the click; here a pop-up keeps the menu
        marker, because a row that opens a menu and a row that acts are worth
        distinguishing before the click rather than after it.
        """
        rect = self._wizard_rect
        p.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL_BG)

        for row_rect, row in self._wizard_row_rects:
            hovered = (
                self._hover.kind == "wizard"
                and 0 <= self._hover.row < len(self._wizard_row_rects)
                and self._wizard_row_rects[self._hover.row][1] is row
            )
            if row.kind == "title":
                p.fill_rect(row_rect.x, row_rect.y, row_rect.w, row_rect.h,
                            HEADER_BG)
                colour = HEADER_FG
            else:
                if hovered:
                    p.fill_rect(row_rect.x + 1, row_rect.y,
                                row_rect.w - 2, row_rect.h, MENU_SEL_BG)
                colour = MENU_FG
            p.text(
                row_rect.x + self.PAD, row_rect.y,
                row_rect.w - 2 * self.PAD, row_rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, row.label, colour,
            )
            if row.kind == "menu":
                p.text(
                    row_rect.x, row_rect.y,
                    row_rect.w - self.PAD, row_rect.h,
                    ALIGN_VCENTER | ALIGN_RIGHT, "▾", colour,
                )

    def _paint_prompt(self, p) -> None:
        """Draw the wizard's instruction, top-left of the scene, as PyMOL does.

        Not in the panel: the prompt says what to do *in the view* -- "pick a
        residue" -- and putting it in the corner where the panel is means
        looking away from the molecule to read it.
        """
        if not self.wizard_prompt:
            return
        # Below the sequence strip, not over it. The strip owns a band at the
        # top of the window and the scene starts under it; a prompt at the
        # window's own top edge lands on the residue numbers.
        y = self.sequence_height() + self.MARGIN
        for line in self.wizard_prompt:
            p.text(
                self.MARGIN, y, self._width * 0.6, self.ROW_H,
                ALIGN_VCENTER | ALIGN_LEFT, str(line), MODE_TITLE_FG,
            )
            y += self.ROW_H

    def _paint_command(self, p) -> None:
        """Draw the feedback log and the prompt across the bottom of the scene.

        The caret is a filled rectangle rather than a glyph. A ``|`` sits inside
        a cell and reads as a character of the command; a block between two
        cells reads as a position, which is what it is -- and it needs nothing
        baked into the atlas.
        """
        line = self.command_line
        rect = self._cmd_rect
        if rect.w <= 0.0:
            return

        log = line.visible_log()
        if log:
            box = self._cmd_log_rect
            p.fill_rect(box.x, box.y, box.w, box.h, CMD_BG)
            for index, entry in enumerate(log):
                colour = {
                    "echo": CMD_ECHO_FG,
                    "error": CMD_ERROR_FG,
                }.get(entry.kind, CMD_MESSAGE_FG)
                p.text(
                    box.x + self.MARGIN, box.y + index * self.CMD_ROW_H,
                    box.w - 2 * self.MARGIN, float(self.CMD_ROW_H),
                    ALIGN_VCENTER | ALIGN_LEFT, entry.text, colour,
                )

        p.fill_rect(rect.x, rect.y, rect.w, rect.h, CMD_BG)
        if not line.focused:
            p.text(
                rect.x + self.MARGIN, rect.y, rect.w - 2 * self.MARGIN, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, HINT, CMD_HINT_FG,
            )
            return

        x = rect.x + self.MARGIN
        p.text(x, rect.y, p.text_width(PROMPT), rect.h,
               ALIGN_VCENTER | ALIGN_LEFT, PROMPT, CMD_PROMPT_FG)
        text_x = x + p.text_width(PROMPT + " ")
        p.text(
            text_x, rect.y, max(rect.w - text_x - self.MARGIN, 1.0), rect.h,
            ALIGN_VCENTER | ALIGN_LEFT, line.text, CMD_TEXT_FG,
        )
        caret = text_x + p.text_width(line.text[: line.cursor])
        p.fill_rect(caret, rect.y + 2.0, 1.5, rect.h - 4.0, CMD_CARET_FG)

    def _paint_sequence(self, p) -> None:
        """Draw the sequence strip: numbers, names, residues, selection.

        One-letter codes with a number every fifth column, which is PyMOL's
        default (``seq_view_format 0``, ``seq_view_label_mode 2``,
        ``seq_view_label_spacing 5``).
        """
        strip = self._seq_strip
        p.fill_rect(strip.x, strip.y, strip.w, strip.h, SEQ_BG)

        char_w = char_width(self.FONT_PT)
        visible = max(int((strip.w - self._seq_origin) / char_w), 1)

        # The number line, above the rows it labels.
        first = self.sequences[0] if self.sequences else None
        if first is not None:
            for column in range(self._seq_scroll, min(self._seq_scroll + visible,
                                                      len(first.codes))):
                if column % self.LABEL_SPACING:
                    continue
                number = (
                    first.numbers[column] if column < len(first.numbers) else column + 1
                )
                p.text(
                    self._seq_origin + (column - self._seq_scroll) * char_w,
                    strip.y + self.PAD, char_w * 6, self.SEQ_ROW_H,
                    ALIGN_VCENTER | ALIGN_LEFT, str(number), SEQ_NUMBER_FG,
                )

        hidden = max(self.sequence_total, len(self.sequences)) - len(self._seq_rows)
        if hidden > 0 and self._seq_rows:
            last = self._seq_rows[-1]
            p.text(
                self.PAD, last.y + self.SEQ_ROW_H, self._seq_origin + strip.w,
                self.SEQ_ROW_H, ALIGN_VCENTER | ALIGN_LEFT,
                f"… and {hidden} more chains", SEQ_NUMBER_FG,
            )

        for index, row in enumerate(self.sequences[: len(self._seq_rows)]):
            rect = self._seq_rows[index]
            p.text(
                self.PAD, rect.y, self._seq_origin - self.PAD, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, row.name, SEQ_NAME_FG,
            )
            for column in range(self._seq_scroll,
                                min(self._seq_scroll + visible, len(row.codes))):
                x = self._seq_origin + (column - self._seq_scroll) * char_w
                if column in row.selected:
                    p.fill_rect(x, rect.y, char_w, rect.h, SEQ_SELECTED_BG)
                    colour = SEQ_SELECTED_FG
                else:
                    colour = _residue_color(row, column)
                p.text(x, rect.y, char_w, rect.h,
                       ALIGN_CENTER, row.codes[column], colour)

        track, thumb = self._seq_track, self._seq_thumb
        p.fill_rect(track.x, track.y, track.w, track.h, SEQ_TRACK_BG)
        p.fill_rect(thumb.x, thumb.y, thumb.w, thumb.h, SEQ_THUMB_BG)

    def _paint_block(self, p) -> None:
        """Draw the mouse-mode reference, the state, and the transport."""
        rect = self._block
        p.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL_BG)

        char_w = char_width(self.FONT_PT)
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        left = rect.x + self.PAD
        line = rect.y + self.PAD

        gutter = char_w          # between a right-aligned label and its values

        def draw(x, y, text, colour, width=None, right=False):
            box_w = width or cell_w
            if right:
                # Shrink from the right so the text ends a gutter short of the
                # column beside it; right-aligning into the full width puts the
                # last glyph hard against the first value ("ButtonsL").
                box_w -= gutter
            p.text(
                x, y, box_w, self.BLOCK_ROW_H,
                ALIGN_VCENTER | (ALIGN_RIGHT if right else ALIGN_LEFT),
                text, colour,
            )

        draw(left, line, "Mouse Mode", MODE_TITLE_FG, label_w + cell_w, right=True)
        draw(left + label_w + cell_w, line,
             MODE_NAMES.get(self.mouse_mode, self.mouse_mode), MODE_TITLE_FG,
             rect.w)
        line += self.BLOCK_ROW_H

        draw(left, line, "Buttons", MODE_HEAD_FG, label_w, right=True)
        for index, (_key, heading) in enumerate(BUTTON_COLUMNS):
            draw(left + label_w + index * cell_w, line, heading, MODE_HEAD_FG)
        line += self.BLOCK_ROW_H

        for label, cells in rows_for(self.mouse_mode):
            colour = MODE_HEAD_FG if label == "& Keys" else MODE_KEY_FG
            draw(left, line, label, colour, label_w, right=True)
            for index, cell in enumerate(cells):
                if cell:
                    draw(left + label_w + index * cell_w, line, cell, MODE_ACTION_FG)
            line += self.BLOCK_ROW_H

        draw(left, line, "Selecting", SELECT_FG, label_w, right=True)
        draw(left + label_w, line, self.selecting, SELECT_MODE_FG, rect.w)
        line += self.BLOCK_ROW_H
        current, total = self.state
        draw(left, line, "State", STATE_FG, label_w, right=True)
        draw(left + label_w, line, f"{current} / {total}", MODE_ACTION_FG, cell_w * 3)
        line += self.BLOCK_ROW_H

        # Stride and averaging: PyMOL has neither, and a long or noisy
        # trajectory needs both -- one to watch it end to end without waiting,
        # the other to see the motion rather than the jitter.
        draw(left, line, "Stride", STATE_FG, label_w, right=True)
        draw(left + label_w, line, f"x{self.stride}", MODE_ACTION_FG, cell_w)
        draw(left + label_w + cell_w, line, "Avg", STATE_FG, cell_w)
        draw(left + label_w + cell_w * 2, line,
             "off" if self.average <= 1 else str(self.average),
             MODE_ACTION_FG, cell_w * 2)

        for groove, value, ceiling, held in (
            (self._stride_groove, self.stride, self.STRIDE_MAX, "stride"),
            (self._average_groove, self.average, self.AVERAGE_MAX, "average"),
        ):
            if groove.w <= 0.0:
                continue
            fraction = min(max(float(value) / float(ceiling), 0.0), 1.0)
            mid = groove.y + groove.h * 0.5
            p.fill_rect(groove.x, mid - 1.0, groove.w, 2.0, WINDOW_DIM_FG)
            p.fill_rect(groove.x, mid - 1.0, groove.w * fraction, 2.0, MODE_TITLE_FG)
            thumb = groove.x + fraction * max(groove.w - 5.0, 0.0)
            p.fill_rect(
                thumb, groove.y + 2.0, 5.0, groove.h - 4.0,
                MODE_TITLE_FG if self._dragging_playback == held else ENABLED_FG,
            )

        if not self.movie_panel_visible:
            return

        track, thumb = self._timeline_track, self._timeline_thumb
        p.fill_rect(track.x, track.y, track.w, track.h, SEQ_TRACK_BG)
        p.fill_rect(thumb.x, thumb.y, thumb.w, thumb.h, MOVIE_FG)

        for button_rect, _command in self._movie_rects:
            p.stroke_rect(button_rect.x, button_rect.y,
                          button_rect.w, button_rect.h,
                          BUTTON_EDGE, fill=MOVIE_BG)
            p.text(button_rect.x, button_rect.y, button_rect.w, button_rect.h,
                   ALIGN_CENTER, _glyph_of(_command), MOVIE_FG)

    def _paint_button(self, p, key, rect, hovered, enabled=True) -> None:
        """Draw one A/S/H/L/C box.

        A switched-off object keeps its boxes -- they are how it gets switched
        back on -- but they are drawn dim, so the row says at a glance which
        state it is in rather than only in the colour of its name.
        """
        x, y = rect.x, rect.y + 1
        w, h = rect.w, rect.h - 2
        if key == "C":
            stops = [
                _grey_of(stop) if not enabled else stop
                for stop in COLOR_BUTTON_STOPS
            ]
            p.gradient_rect(x, y, w, h, stops, edge=BUTTON_EDGE)
        elif not enabled:
            p.stroke_rect(x, y, w, h, BUTTON_EDGE, fill=BUTTON_OFF_BG)
        else:
            p.stroke_rect(x, y, w, h, BUTTON_EDGE,
                          fill=(HOVER_BG if hovered else BUTTON_BG))
        if key == "C":
            colour = (0, 0, 0) if enabled else (70, 70, 70)
        else:
            colour = BUTTON_FG if enabled else BUTTON_OFF_FG
        p.text(x, y, w, h, ALIGN_CENTER, key, colour)

    def _paint_menu(self, p, menu: _OpenMenu) -> None:
        """Draw one open menu, its title row, and its scroll marks."""
        rect = menu.rect
        p.stroke_rect(rect.x, rect.y, rect.w, rect.h, MENU_EDGE, fill=MENU_BG)

        page, pages = self.menu_pages(menu)
        title = menu.title if pages == 1 else f"{menu.title}  {page}/{pages}"
        room = rect.w - (self._menu_page_button(menu).w if pages > 1 else 0.0)
        p.text(
            rect.x + self.MENU_PAD, rect.y + self.MENU_PAD,
            max(room - self.MENU_PAD, 1.0), self.MENU_ITEM_H,
            ALIGN_VCENTER | ALIGN_LEFT, title, MENU_FG, bold=True,
        )

        # Say which way there is more, when the menu is taller than the window.
        # In the *title* row, not at the edges of the list: an arrow on the last
        # row would sit on top of that row's own text and its submenu marker.
        # PyMOL draws nothing at all and simply scrolls, which leaves a menu
        # that is silently cut off at the window edge -- the complaint that the
        # column-wrapping this replaces was trying to answer.
        if menu.max_scroll > 0.0:
            # `▴`/`▾`, not `◂`/`▸`: the baked atlas has the vertical pair (the
            # scroll marks these replace used them) and only one of the
            # horizontal one -- `▸` is the submenu marker. A glyph the atlas
            # does not have draws as nothing, so the "back" arrow was simply
            # absent on every page but the first.
            marks = ("▴" if menu.scroll > 0.0 else " ") + " " + (
                "▾" if menu.scroll < menu.max_scroll else " "
            )
            button = self._menu_page_button(menu)
            p.fill_rect(button.x, button.y, button.w, button.h, MENU_SEL_BG)
            p.text(
                rect.x, rect.y + self.MENU_PAD,
                rect.w - self.MENU_PAD, self.MENU_ITEM_H,
                ALIGN_VCENTER | ALIGN_RIGHT, marks, MENU_FG,
            )

        # Below the title, so a scrolled row cannot be drawn over it.
        p.push_clip(
            rect.x,
            rect.y + self.MENU_PAD + self.MENU_ITEM_H,
            rect.w,
            max(rect.h - self.MENU_PAD - self.MENU_ITEM_H, 0.0),
        )
        try:
            for item_rect, entry in menu.item_rects:
                hovered = (self._hover.kind == "menu" and self._hover.entry is entry)
                if hovered and (entry.command is not None or entry.is_submenu):
                    p.fill_rect(item_rect.x + 1, item_rect.y,
                                item_rect.w - 2, item_rect.h, MENU_SEL_BG)
                enabled = entry.is_submenu or entry.command is not None
                colour = MENU_FG if enabled else MENU_DISABLED_FG
                p.text(
                    item_rect.x + self.MENU_PAD, item_rect.y,
                    item_rect.w - 2 * self.MENU_PAD, item_rect.h,
                    ALIGN_VCENTER | ALIGN_LEFT, entry.label, colour,
                )
                if entry.is_submenu:
                    p.text(
                        item_rect.x, item_rect.y,
                        item_rect.w - self.MENU_PAD, item_rect.h,
                        ALIGN_VCENTER | ALIGN_RIGHT, "▸", colour,
                    )
        finally:
            p.pop_clip()


def _glyph_of(command: str) -> str:
    """Return the transport glyph bound to *command*."""
    for glyph, bound in MOVIE_BUTTONS:
        if bound == command:
            return glyph
    return "?"


def _residue_color(row: SequenceRow, index: int) -> tuple[int, int, int]:
    """Return the colour a residue is drawn in, from the structure's own.

    A sequence in one flat colour is a different picture from the molecule it
    indexes: colouring by chain or by spectrum says nothing if the strip does
    not show the same thing.
    """
    if index < len(row.colors):
        red, green, blue = row.colors[index][:3]
        return (
            int(max(0.0, min(1.0, red)) * 255),
            int(max(0.0, min(1.0, green)) * 255),
            int(max(0.0, min(1.0, blue)) * 255),
        )
    return SEQ_FG
